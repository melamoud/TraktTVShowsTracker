"""
Cast fetch/cache and favorite-actor preferences.

Cast is loaded from Trakt /movies|shows/{id}/people on detail view and stored
locally. Headshots come from one TMDB credits call per title and are downloaded
into instance/actor_cache once per person (skip if file already exists).

Favorite actors are app-local (Preferences), not Trakt favorites — ready for a
future “new titles with your actors” alert path.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from flask import current_app

from models import (
    CachedMedia, CachedPerson, MediaCastMember, User, UserFavoriteActor, db,
)
from services import trakt_client
from services import tmdb_client
from services.actor_cache import (
    cache_remote_headshot,
    is_local_actor_url,
    local_actor_path,
    local_actor_url,
)

logger = logging.getLogger('app')

# Re-fetch cast from Trakt when older than this (cast rarely changes for old titles).
CAST_CACHE_DAYS = 30
# How many cast members to show before “Show all” (2-column grid → ~4 rows).
MAIN_CAST_LIMIT = 8


def _parse_characters(raw) -> list[str]:
    """Normalize Trakt characters field to a list of non-empty strings."""
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        return [text] if text else []
    if isinstance(raw, list):
        out = []
        for item in raw:
            text = str(item or '').strip()
            if text:
                out.append(text)
        return out
    return []


def upsert_person_from_trakt(person_obj: dict | None) -> CachedPerson | None:
    """Create or update CachedPerson from a Trakt person object."""
    if not isinstance(person_obj, dict):
        return None
    ids = person_obj.get('ids') or {}
    try:
        trakt_id = int(ids.get('trakt') or 0)
    except (TypeError, ValueError):
        trakt_id = 0
    if not trakt_id:
        return None
    name = (person_obj.get('name') or '').strip() or f'Person {trakt_id}'
    row = CachedPerson.query.filter_by(trakt_id=trakt_id).first()
    if not row:
        row = CachedPerson(trakt_id=trakt_id, name=name)
        db.session.add(row)
    row.name = name
    row.slug = (person_obj.get('ids') or {}).get('slug') or person_obj.get('slug') or row.slug
    try:
        tmdb_id = ids.get('tmdb')
        row.tmdb_id = int(tmdb_id) if tmdb_id else row.tmdb_id
    except (TypeError, ValueError):
        pass
    imdb = ids.get('imdb')
    if imdb:
        row.imdb_id = str(imdb)
    return row


def sync_cast_for_media(media: CachedMedia, *, force: bool = False) -> list[MediaCastMember]:
    """
    Ensure MediaCastMember rows exist for this title.

    Returns cast members ordered by sort_order. Failures leave existing cache
    intact when present.
    """
    if not media:
        return []
    stale_after = datetime.utcnow() - timedelta(days=CAST_CACHE_DAYS)
    if (
        not force
        and media.cast_fetched_at
        and media.cast_fetched_at >= stale_after
        and media.cast_members
    ):
        return sorted(media.cast_members, key=lambda c: (c.sort_order, c.id))

    try:
        payload = trakt_client.fetch_media_people(media.media_type, media.trakt_id)
    except Exception as exc:
        current_app.logger.warning(
            'Cast fetch failed %s %s: %s', media.media_type, media.trakt_id, exc,
        )
        return sorted(media.cast_members, key=lambda c: (c.sort_order, c.id))

    cast_list = (payload or {}).get('cast') or []
    if not isinstance(cast_list, list):
        cast_list = []

    MediaCastMember.query.filter_by(cached_media_id=media.id).delete(synchronize_session=False)
    rows: list[MediaCastMember] = []
    for idx, entry in enumerate(cast_list):
        if not isinstance(entry, dict):
            continue
        person = upsert_person_from_trakt(entry.get('person'))
        if not person:
            continue
        db.session.flush()
        characters = _parse_characters(entry.get('characters') or entry.get('character'))
        ep_count = entry.get('episode_count')
        try:
            ep_count = int(ep_count) if ep_count is not None else None
        except (TypeError, ValueError):
            ep_count = None
        credit = MediaCastMember(
            cached_media_id=media.id,
            person_id=person.id,
            characters_json=json.dumps(characters),
            episode_count=ep_count,
            sort_order=idx,
        )
        db.session.add(credit)
        rows.append(credit)

    media.cast_fetched_at = datetime.utcnow()
    db.session.commit()
    return rows


def favorite_actor_person_ids(user: User) -> set[int]:
    """Return CachedPerson.id values the user has favorited."""
    if not user or not getattr(user, 'id', None):
        return set()
    rows = UserFavoriteActor.query.filter_by(user_id=user.id).all()
    return {row.person_id for row in rows}


def favorite_actor_trakt_ids(user: User) -> set[int]:
    """
    Return Trakt person ids the user has favorited.

    Useful for future catalog/alert matching against cast credits.
    """
    if not user or not getattr(user, 'id', None):
        return set()
    rows = (
        db.session.query(CachedPerson.trakt_id)
        .join(UserFavoriteActor, UserFavoriteActor.person_id == CachedPerson.id)
        .filter(UserFavoriteActor.user_id == user.id)
        .all()
    )
    return {int(r[0]) for r in rows if r[0]}


def list_favorite_actors(user: User) -> list[CachedPerson]:
    """Favorite actors ordered by name for Preferences."""
    if not user or not getattr(user, 'id', None):
        return []
    return (
        CachedPerson.query
        .join(UserFavoriteActor, UserFavoriteActor.person_id == CachedPerson.id)
        .filter(UserFavoriteActor.user_id == user.id)
        .order_by(CachedPerson.name.asc())
        .all()
    )


def resolve_person_headshot(person: CachedPerson) -> str | None:
    """Return local headshot URL if the cached file exists; do not download."""
    if not person:
        return None
    existing = local_actor_path(person.trakt_id)
    if existing:
        url = local_actor_url(person.trakt_id)
        if person.headshot_url != url:
            person.headshot_url = url
        return url
    # Stale DB pointer (file deleted) — allow a re-download.
    if is_local_actor_url(person.headshot_url):
        person.headshot_url = None
    return None


def ensure_person_headshot(
    person: CachedPerson,
    *,
    remote_url: str | None = None,
) -> str | None:
    """
    Ensure a local headshot exists for this person (download once).

    Prefer ``remote_url`` from a TMDB credits batch; otherwise fall back to a
    single /person lookup when the person has a tmdb_id.
    """
    if not person:
        return None
    existing = resolve_person_headshot(person)
    if existing:
        return existing
    url = remote_url
    if not url and person.tmdb_id and tmdb_client.is_configured():
        try:
            url = tmdb_client.get_person_profile_url(person.tmdb_id)
        except Exception as exc:
            logger.warning('TMDB profile lookup failed person %s: %s', person.trakt_id, exc)
            return person.headshot_url
    if not url:
        return person.headshot_url
    local = cache_remote_headshot(person.trakt_id, url)
    if local:
        person.headshot_url = local
    return person.headshot_url


# Back-compat alias used by favorite toggle / older tests.
ensure_favorite_headshot = ensure_person_headshot


def ensure_cast_headshots(media: CachedMedia, credits: list[MediaCastMember]) -> int:
    """
    Cache missing headshots for this title’s cast.

    Uses one TMDB credits call when ``media.tmdb_id`` is set, then downloads
    only people not already in ``instance/actor_cache``. Returns download count.
    """
    if not media or not credits or not tmdb_client.is_configured():
        return 0

    people = [c.person for c in credits if c.person]
    # Only people with a TMDB id can get a credits profile; others stay initials.
    missing = [
        p for p in people
        if p.tmdb_id and not resolve_person_headshot(p)
    ]
    if not missing:
        db.session.commit()
        return 0

    profile_by_tmdb: dict[int, str] = {}
    if media.tmdb_id:
        try:
            profile_by_tmdb = tmdb_client.get_cast_profile_urls(
                media.media_type, media.tmdb_id,
            )
        except Exception as exc:
            current_app.logger.warning(
                'TMDB credits headshots failed %s %s: %s',
                media.media_type, media.trakt_id, exc,
            )

    downloaded = 0
    for person in missing:
        remote = None
        if person.tmdb_id:
            remote = profile_by_tmdb.get(int(person.tmdb_id))
        # Only fall back to /person when the title has no tmdb_id (no credits map).
        if remote:
            if ensure_person_headshot(person, remote_url=remote):
                downloaded += 1
        elif not media.tmdb_id and person.tmdb_id:
            if ensure_person_headshot(person):
                downloaded += 1

    db.session.commit()
    return downloaded


def set_favorite_actor(user: User, trakt_person_id: int, *, favorited: bool) -> CachedPerson:
    """Add or remove a favorite actor; ensure headshot on add when possible."""
    person = CachedPerson.query.filter_by(trakt_id=int(trakt_person_id)).first()
    if not person:
        raise ValueError('Unknown actor — open a title with this cast first.')
    row = UserFavoriteActor.query.filter_by(user_id=user.id, person_id=person.id).first()
    if favorited:
        if not row:
            db.session.add(UserFavoriteActor(user_id=user.id, person_id=person.id))
        ensure_person_headshot(person)
    elif row:
        db.session.delete(row)
    db.session.commit()
    return person


def cast_for_detail(media: CachedMedia, user: User) -> list[dict]:
    """
    Build cast dicts for the detail template.

    Each item: trakt_id, name, characters, episode_count, favorited, headshot_url.
    Headshots are local-cache URLs when available (filled once per person).
    """
    credits = sync_cast_for_media(media)
    try:
        ensure_cast_headshots(media, credits)
    except Exception as exc:
        current_app.logger.warning('Cast headshot cache failed: %s', exc)
    fav_ids = favorite_actor_person_ids(user)
    out: list[dict] = []
    for credit in credits:
        person = credit.person
        if not person:
            continue
        try:
            characters = json.loads(credit.characters_json or '[]')
        except json.JSONDecodeError:
            characters = []
        if not isinstance(characters, list):
            characters = []
        headshot = resolve_person_headshot(person)
        out.append({
            'trakt_id': person.trakt_id,
            'name': person.name,
            'characters': characters,
            'episode_count': credit.episode_count,
            'favorited': person.id in fav_ids,
            'headshot_url': headshot,
        })
    if any(p.headshot_url for p in (c.person for c in credits if c.person)):
        db.session.commit()
    return out


def _parse_actor_id(raw) -> int | None:
    """Parse a Trakt person id from a form/query value."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def resolve_actor_for_search(
    user: User,
    *,
    actor_id: int | None = None,
    actor_q: str = '',
) -> CachedPerson | None:
    """
    Resolve a person for actor search.

    Prefer an explicit Trakt person id (favorites dropdown / cast link).
    Otherwise match a favorite by name, then Trakt ``/search/person``.
    """
    pid = _parse_actor_id(actor_id)
    if pid:
        person = CachedPerson.query.filter_by(trakt_id=pid).first()
        if person:
            return person
        try:
            payload = trakt_client.fetch_person(pid)
        except Exception as exc:
            current_app.logger.warning('Person fetch failed %s: %s', pid, exc)
            return None
        if payload:
            person = upsert_person_from_trakt(payload)
            if person:
                db.session.commit()
            return person
        return None

    needle = (actor_q or '').strip()
    if len(needle) < 2:
        return None
    folded = needle.casefold()
    favorites = list_favorite_actors(user)
    exact = [p for p in favorites if (p.name or '').casefold() == folded]
    if exact:
        return exact[0]
    partial = [p for p in favorites if folded in (p.name or '').casefold()]
    if len(partial) == 1:
        return partial[0]

    try:
        hits = trakt_client.search_people(user, needle, limit=8)
    except Exception as exc:
        current_app.logger.warning('People search failed %r: %s', needle, exc)
        return None
    for row in hits:
        person = upsert_person_from_trakt((row or {}).get('person'))
        if person:
            db.session.commit()
            return person
    return None

