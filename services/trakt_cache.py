"""
Shared Trakt read-cache helpers.

TTL and write-through are keyed by object (title state, progress, calendar,
list metadata), not by which screen was open. All pages and the alerts job
read the same SQLite rows.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta

from models import (
    UserMediaState,
    UserRecommendationCache,
    UserSearchCache,
    UserTraktList,
    db,
)

logger = logging.getLogger('app')

DEFAULT_TRAKT_READ_CACHE_HOURS = 2.0
MIN_TRAKT_READ_CACHE_HOURS = 0.25
MAX_TRAKT_READ_CACHE_HOURS = 168.0


def get_trakt_read_cache_hours() -> float:
    """Admin TTL in hours (default 2)."""
    try:
        from services.sync_jobs import get_or_create_scheduler_config
        row = get_or_create_scheduler_config()
        hours = float(getattr(row, 'trakt_read_cache_hours', None) or DEFAULT_TRAKT_READ_CACHE_HOURS)
    except Exception:
        hours = DEFAULT_TRAKT_READ_CACHE_HOURS
    return max(MIN_TRAKT_READ_CACHE_HOURS, min(MAX_TRAKT_READ_CACHE_HOURS, hours))


def get_trakt_read_cache_ttl() -> timedelta:
    """Admin TTL as a timedelta."""
    return timedelta(hours=get_trakt_read_cache_hours())


def cache_is_fresh(stamp: datetime | None, ttl: timedelta | None = None) -> bool:
    """True when ``stamp`` is within the read-cache TTL."""
    if stamp is None:
        return False
    age_limit = ttl if ttl is not None else get_trakt_read_cache_ttl()
    return stamp >= datetime.utcnow() - age_limit


def bump_user_sync_stamp(user) -> None:
    """Mark bulk membership cache fresh after a local write (no Trakt GET)."""
    user.last_sync_at = datetime.utcnow()


def cache_http_span():
    """Return a callable that reports Trakt HTTP attempts since this point."""
    from services.trakt_client import trakt_http_count
    start = trakt_http_count()
    return lambda: trakt_http_count() - start


def log_cache_event(
    obj: str,
    result: str,
    *,
    user=None,
    reason: str | None = None,
    item: str | None = None,
    calls: int | None = None,
) -> None:
    """
    One INFO line per cache object decision (hit / probe / fetch / patch).

    Example: Cache user_media hit user=friend calls=0 source=http GET /my/shows
    """
    from services.trakt_client import current_trakt_source

    if isinstance(user, str):
        who = user or '-'
    else:
        who = getattr(user, 'username', None) or '-'
    bits = [f'Cache {obj} {result}', f'user={who}']
    if item:
        bits.append(f'id={item}')
    if reason:
        bits.append(f'reason={reason}')
    if calls is not None:
        bits.append(f'calls={int(calls)}')
    bits.append(f'source={current_trakt_source()}')
    logger.info(' '.join(bits))


# --- Personal list metadata -------------------------------------------------


def replace_cached_personal_lists(user_id: int, lists: list[dict]) -> None:
    """Replace cached Trakt list id/name/slug rows for one user."""
    wanted = {str(lst.get('id')) for lst in lists if lst.get('id') is not None}
    existing = UserTraktList.query.filter_by(user_id=user_id).all()
    by_id = {row.list_id: row for row in existing}
    now = datetime.utcnow()
    for lst in lists:
        lid = str(lst.get('id') or '')
        if not lid:
            continue
        row = by_id.get(lid)
        name = (lst.get('name') or f'List {lid}').strip() or f'List {lid}'
        slug = (lst.get('slug') or '') or ''
        count = int(lst.get('item_count') or 0)
        if row is None:
            db.session.add(UserTraktList(
                user_id=user_id,
                list_id=lid,
                name=name,
                slug=slug,
                item_count=count,
                updated_at=now,
            ))
        else:
            row.name = name
            row.slug = slug
            row.item_count = count
            row.updated_at = now
    for row in existing:
        if row.list_id not in wanted:
            db.session.delete(row)


def cached_personal_lists(user) -> list[dict]:
    """Return cached personal lists in the same shape as Trakt ``get_personal_lists``."""
    rows = (
        UserTraktList.query
        .filter_by(user_id=user.id)
        .order_by(UserTraktList.name.asc())
        .all()
    )
    return [
        {
            'id': row.list_id,
            'name': row.name,
            'slug': row.slug or '',
            'item_count': int(row.item_count or 0),
        }
        for row in rows
    ]


def personal_lists_for_user(user, *, force: bool = False) -> list[dict]:
    """
    Personal lists from SQLite when the membership TTL is fresh.

    Fetches from Trakt only when never synced, TTL expired, or ``force``.
    """
    if not force and cache_is_fresh(getattr(user, 'last_sync_at', None)):
        return cached_personal_lists(user)
    from services import trakt_client
    span = cache_http_span()
    try:
        lists = trakt_client.get_personal_lists(user)
    except Exception:
        cached = cached_personal_lists(user)
        if cached:
            return cached
        raise
    replace_cached_personal_lists(user.id, lists)
    log_cache_event('lists', 'fetch', user=user, reason='force' if force else 'stale', calls=span())
    return lists


# --- Show progress payload --------------------------------------------------


def _keys_to_tuples(raw) -> set[tuple[int, int]]:
    out: set[tuple[int, int]] = set()
    for item in raw or []:
        try:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                out.add((int(item[0]), int(item[1])))
        except (TypeError, ValueError):
            continue
    return out


def load_progress_payload(user_id: int, trakt_id: int) -> dict | None:
    """Return stored progress JSON for a show, or None."""
    row = UserMediaState.query.filter_by(
        user_id=user_id, media_type='show', trakt_id=int(trakt_id),
    ).first()
    if row is None or not row.progress_payload_json:
        return None
    try:
        data = json.loads(row.progress_payload_json)
    except (TypeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def progress_cache_is_fresh(user_id: int, trakt_id: int) -> bool:
    """True when this show's progress payload is within TTL."""
    row = UserMediaState.query.filter_by(
        user_id=user_id, media_type='show', trakt_id=int(trakt_id),
    ).first()
    if row is None or not row.progress_payload_json:
        return False
    return cache_is_fresh(row.progress_detail_at)


def save_progress_payload(
    user_id: int,
    trakt_id: int,
    *,
    watched_keys: set[tuple[int, int]],
    aired_keys: set[tuple[int, int]],
    seasons_meta: list,
) -> UserMediaState:
    """Persist the shared progress object and stamp ``progress_detail_at``."""
    from services.sync_jobs import apply_show_episode_progress

    row = UserMediaState.query.filter_by(
        user_id=user_id, media_type='show', trakt_id=int(trakt_id),
    ).first()
    if row is None:
        row = UserMediaState(
            user_id=user_id, media_type='show', trakt_id=int(trakt_id),
        )
        db.session.add(row)
        db.session.flush()
    payload = {
        'watched_keys': [list(k) for k in sorted(watched_keys)],
        'aired_keys': [list(k) for k in sorted(aired_keys)],
        'seasons_meta': seasons_meta or [],
    }
    row.progress_payload_json = json.dumps(payload)
    aired, completed, next_episode = summarize_progress(
        seasons_meta or [], watched_keys, aired_keys,
    )
    apply_show_episode_progress(
        user_id,
        int(trakt_id),
        aired=aired,
        completed=completed,
        next_episode=next_episode,
    )
    return row


def invalidate_show_progress(user_id: int, trakt_id: int) -> None:
    """Force the next Progress/Alerts reader to re-fetch this show from Trakt."""
    row = UserMediaState.query.filter_by(
        user_id=user_id, media_type='show', trakt_id=int(trakt_id),
    ).first()
    if row is None:
        return
    row.progress_detail_at = None
    row.progress_payload_json = None
    log_cache_event('progress', 'invalidate', item=str(int(trakt_id)), reason='no-payload')


def summarize_progress(
    seasons_meta: list,
    watched_keys: set[tuple[int, int]],
    aired_keys: set[tuple[int, int]],
) -> tuple[int, int, dict | None]:
    """Return (aired, completed, next_episode) for regular seasons."""
    total_aired = 0
    total_completed = 0
    next_regular = None
    next_special = None
    for season in seasons_meta or []:
        number = season.get('number')
        if number is None:
            continue
        number = int(number)
        is_specials = number == 0
        for ep in season.get('episodes') or []:
            ep_no = ep.get('number')
            if ep_no is None:
                continue
            ep_no = int(ep_no)
            key = (number, ep_no)
            is_aired = key in aired_keys if aired_keys else False
            if not is_aired:
                continue
            if not is_specials:
                total_aired += 1
                if key in watched_keys:
                    total_completed += 1
                elif next_regular is None:
                    next_regular = {
                        'season': number,
                        'number': ep_no,
                        'title': ep.get('title'),
                    }
            elif key not in watched_keys and next_special is None:
                next_special = {
                    'season': number,
                    'number': ep_no,
                    'title': ep.get('title'),
                }
    return total_aired, total_completed, next_regular or next_special


def _patch_or_invalidate(user_id: int, trakt_id: int, mutator) -> bool:
    payload = load_progress_payload(user_id, trakt_id)
    if not payload or not payload.get('seasons_meta'):
        invalidate_show_progress(user_id, trakt_id)
        return False
    watched = _keys_to_tuples(payload.get('watched_keys'))
    aired = _keys_to_tuples(payload.get('aired_keys'))
    mutator(watched, aired, payload.get('seasons_meta') or [])
    save_progress_payload(
        user_id,
        trakt_id,
        watched_keys=watched,
        aired_keys=aired,
        seasons_meta=payload.get('seasons_meta') or [],
    )
    log_cache_event('progress', 'patch', item=str(int(trakt_id)), calls=0)
    return True


def patch_episode_watched(
    user_id: int,
    trakt_id: int,
    season: int,
    episode: int,
    *,
    watched: bool,
) -> bool:
    """Write-through one episode into the shared progress cache."""
    key = (int(season), int(episode))

    def _mut(watched_keys, _aired, _seasons):
        if watched:
            watched_keys.add(key)
        else:
            watched_keys.discard(key)

    return _patch_or_invalidate(user_id, int(trakt_id), _mut)


def patch_season_watched(
    user_id: int,
    trakt_id: int,
    season: int,
    *,
    watched: bool,
) -> bool:
    """Write-through all aired episodes in one season."""
    season_no = int(season)

    def _mut(watched_keys, aired_keys, _seasons):
        for s, e in list(aired_keys):
            if s == season_no:
                if watched:
                    watched_keys.add((s, e))
                else:
                    watched_keys.discard((s, e))

    return _patch_or_invalidate(user_id, int(trakt_id), _mut)


def patch_show_watched(user_id: int, trakt_id: int, *, watched: bool) -> bool:
    """Write-through every aired episode of a show."""

    def _mut(watched_keys, aired_keys, _seasons):
        if watched:
            watched_keys.update(aired_keys)
        else:
            watched_keys.clear()

    return _patch_or_invalidate(user_id, int(trakt_id), _mut)


def watched_keys_from_payload(payload: dict | None) -> set[tuple[int, int]]:
    """Episode keys marked watched in a stored progress payload."""
    if not payload:
        return set()
    return _keys_to_tuples(payload.get('watched_keys'))


# --- Recommendations feed ---------------------------------------------------


def recs_genre_key(genre_filter: str | None) -> str:
    slug = (genre_filter or 'all').strip().lower()
    return slug or 'all'


def load_recommendations_cache(
    user_id: int,
    media_type: str,
    genre_filter: str | None,
) -> list | None:
    """Return cached recs payload when within TTL; else None."""
    slug = recs_genre_key(genre_filter)
    row = UserRecommendationCache.query.filter_by(
        user_id=user_id, media_type=media_type, genre_slug=slug,
    ).first()
    if row is None or not cache_is_fresh(row.fetched_at):
        return None
    try:
        data = json.loads(row.payload_json or '[]')
    except (TypeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, list) else None


def save_recommendations_cache(
    user_id: int,
    media_type: str,
    genre_filter: str | None,
    payload: list,
) -> None:
    slug = recs_genre_key(genre_filter)
    row = UserRecommendationCache.query.filter_by(
        user_id=user_id, media_type=media_type, genre_slug=slug,
    ).first()
    now = datetime.utcnow()
    blob = json.dumps(payload or [])
    if row is None:
        db.session.add(UserRecommendationCache(
            user_id=user_id,
            media_type=media_type,
            genre_slug=slug,
            payload_json=blob,
            fetched_at=now,
        ))
    else:
        row.payload_json = blob
        row.fetched_at = now


def drop_recommendation_from_cache(user_id: int, media_type: str, trakt_id: int) -> None:
    """Remove a hidden title from cached recs feeds for this user+type."""
    tid = int(trakt_id)
    rows = UserRecommendationCache.query.filter_by(
        user_id=user_id, media_type=media_type,
    ).all()
    for row in rows:
        try:
            items = json.loads(row.payload_json or '[]')
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(items, list):
            continue
        kept = []
        for entry in items:
            entity = (entry or {}).get(media_type) or entry or {}
            ids = entity.get('ids') or {}
            try:
                if int(ids.get('trakt')) == tid:
                    continue
            except (TypeError, ValueError):
                pass
            kept.append(entry)
        row.payload_json = json.dumps(kept)
        row.fetched_at = datetime.utcnow()


# --- Search / actor filmography --------------------------------------------

_SEARCH_CACHE_KEEP = 40


def search_cache_key(*, q: str, actor_id: int | None, type_raw: str) -> str:
    """Stable key for one Trakt search (title and/or actor + type)."""
    import hashlib
    raw = json.dumps(
        {
            'q': (q or '').strip().casefold(),
            'actor': int(actor_id or 0),
            'type': type_raw or 'both',
        },
        sort_keys=True,
        separators=(',', ':'),
    )
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:40]


def load_search_cache(user_id: int, query_key: str) -> dict | None:
    """Return ``{movie: [ids], show: [ids]}`` when within TTL; else None."""
    row = UserSearchCache.query.filter_by(user_id=user_id, query_key=query_key).first()
    if row is None or not cache_is_fresh(row.fetched_at):
        return None
    try:
        data = json.loads(row.payload_json or '{}')
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    out = {'movie': [], 'show': []}
    for kind in ('movie', 'show'):
        ids = data.get(kind) or []
        if not isinstance(ids, list):
            continue
        clean = []
        for tid in ids:
            try:
                clean.append(int(tid))
            except (TypeError, ValueError):
                continue
        out[kind] = clean
    return out


def save_search_cache(user_id: int, query_key: str, payload: dict) -> None:
    """Store search ids and drop oldest extra rows for this user."""
    blob = json.dumps({
        'movie': [int(x) for x in (payload or {}).get('movie') or []],
        'show': [int(x) for x in (payload or {}).get('show') or []],
    })
    now = datetime.utcnow()
    row = UserSearchCache.query.filter_by(user_id=user_id, query_key=query_key).first()
    if row is None:
        db.session.add(UserSearchCache(
            user_id=user_id,
            query_key=query_key,
            payload_json=blob,
            fetched_at=now,
        ))
    else:
        row.payload_json = blob
        row.fetched_at = now
    extras = (
        UserSearchCache.query
        .filter_by(user_id=user_id)
        .order_by(UserSearchCache.fetched_at.desc())
        .offset(_SEARCH_CACHE_KEEP)
        .all()
    )
    for old in extras:
        db.session.delete(old)


def media_from_search_ids(payload: dict, types: list[str]) -> list[tuple[str, object]]:
    """Load CachedMedia rows in cached order (skip missing)."""
    from models import CachedMedia

    out: list[tuple[str, object]] = []
    for media_type in types:
        ids = (payload or {}).get(media_type) or []
        if not ids:
            continue
        rows = CachedMedia.query.filter(
            CachedMedia.media_type == media_type,
            CachedMedia.trakt_id.in_(ids),
        ).all()
        by_id = {int(m.trakt_id): m for m in rows}
        for tid in ids:
            media = by_id.get(int(tid))
            if media:
                out.append((media_type, media))
    return out


# --- Calendar window coverage ----------------------------------------------


def calendar_window_covers(user, start: date, end: date) -> bool:
    """True when a fresh calendar fetch already covers [start, end]."""
    if not cache_is_fresh(getattr(user, 'calendar_synced_at', None)):
        return False
    win_start = getattr(user, 'calendar_window_start', None)
    win_end = getattr(user, 'calendar_window_end', None)
    if win_start is None or win_end is None:
        return False
    return win_start <= start and win_end >= end


def note_calendar_window(user, start: date, end: date) -> None:
    """Record a successful calendar fetch, expanding a still-fresh window."""
    now = datetime.utcnow()
    if (
        cache_is_fresh(getattr(user, 'calendar_synced_at', None))
        and user.calendar_window_start
        and user.calendar_window_end
    ):
        if start < user.calendar_window_start:
            user.calendar_window_start = start
        if end > user.calendar_window_end:
            user.calendar_window_end = end
    else:
        user.calendar_window_start = start
        user.calendar_window_end = end
    user.calendar_synced_at = now
