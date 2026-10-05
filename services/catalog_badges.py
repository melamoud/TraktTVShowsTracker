"""
Cheap nav-badge counts for Latest and Recommended (offline SQLite only).

x = purple preference matches. y = the same pile, not matches-only.
Never fetches Trakt, TMDB, or catalog enrich — inject-safe with a short TTL.
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import or_

from models import CachedMedia, ReviewMarker, User, UserListMembership, UserMediaState
from services.streaming_matcher import (
    discovery_year_cutoff,
    match_preferences,
    media_has_excluded_genre,
    media_passes_discovery_year,
)

# Actual Latest feed_source (Trakt /updates), not a conceptual "trakt_latest" name.
_FEED_SOURCE = 'trakt_db_updates'
_TTL_SEC = 90.0
_cache: dict[int, tuple[float, dict[str, Any]]] = {}


def invalidate_catalog_badges(user_id: int | None = None) -> None:
    """Drop in-memory badge counts for one user, or everyone."""
    if user_id is None:
        _cache.clear()
        return
    _cache.pop(int(user_id), None)


def catalog_nav_badges(user: User) -> dict[str, dict[str, int | str] | None]:
    """
    Per-page counts: latest_movies, latest_shows, recommended_movies, recommended_shows.

    Each value is ``{matches, remaining, label}`` or ``None`` (hidden / recs cache miss).
    """
    uid = int(user.id)
    now = time.monotonic()
    use_cache = True
    try:
        from flask import current_app, has_app_context
        if has_app_context() and current_app.config.get('TESTING'):
            use_cache = False
    except Exception:
        pass
    if use_cache:
        cached = _cache.get(uid)
        if cached and (now - cached[0]) < _TTL_SEC:
            return cached[1]

    result = {
        'latest_movies': _count_latest(user, 'movie'),
        'latest_shows': _count_latest(user, 'show'),
        'recommended_movies': _count_recs(user, 'movie'),
        'recommended_shows': _count_recs(user, 'show'),
    }
    if use_cache:
        _cache[uid] = (now, result)
    return result


def catalog_badge_labels(user: User) -> dict[str, str | None]:
    """Template strings, e.g. ``3/12``, or None to hide."""
    data = catalog_nav_badges(user)
    return {
        'latest_movies_badge': _label(data.get('latest_movies')),
        'latest_shows_badge': _label(data.get('latest_shows')),
        'recommended_movies_badge': _label(data.get('recommended_movies')),
        'recommended_shows_badge': _label(data.get('recommended_shows')),
    }


def catalog_badge_api_fields(user: User) -> dict[str, int]:
    """``/me`` ints; omitted when that badge is hidden."""
    out: dict[str, int] = {}
    data = catalog_nav_badges(user)
    for key in ('latest_movies', 'latest_shows', 'recommended_movies', 'recommended_shows'):
        row = data.get(key)
        if not row:
            continue
        out[f'{key}_matches'] = int(row['matches'])
        out[f'{key}_remaining'] = int(row['remaining'])
    return out


def _label(row: dict[str, int | str] | None) -> str | None:
    if not row:
        return None
    return str(row.get('label') or '') or None


def _pack(matches: int, remaining: int) -> dict[str, int | str] | None:
    if remaining <= 0:
        return None
    return {
        'matches': int(matches),
        'remaining': int(remaining),
        'label': f'{int(matches)}/{int(remaining)}',
    }


def _watched_ids(user_id: int, media_type: str, trakt_ids: list[int]) -> set[int]:
    if not trakt_ids:
        return set()
    rows = UserMediaState.query.filter(
        UserMediaState.user_id == user_id,
        UserMediaState.media_type == media_type,
        UserMediaState.trakt_id.in_(trakt_ids),
        UserMediaState.watched.is_(True),
    ).with_entities(UserMediaState.trakt_id).all()
    return {int(r[0]) for r in rows}


def _watchlist_ids(user_id: int, media_type: str, trakt_ids: list[int]) -> set[int]:
    if not trakt_ids:
        return set()
    rows = UserMediaState.query.filter(
        UserMediaState.user_id == user_id,
        UserMediaState.media_type == media_type,
        UserMediaState.trakt_id.in_(trakt_ids),
        UserMediaState.on_watchlist.is_(True),
    ).with_entities(UserMediaState.trakt_id).all()
    return {int(r[0]) for r in rows}


def _listed_ids(user_id: int, media_type: str, trakt_ids: list[int]) -> set[int]:
    """Personal Trakt lists only (not watchlist)."""
    if not trakt_ids:
        return set()
    rows = UserListMembership.query.filter(
        UserListMembership.user_id == user_id,
        UserListMembership.media_type == media_type,
        UserListMembership.trakt_id.in_(trakt_ids),
    ).with_entities(UserListMembership.trakt_id).all()
    return {int(r[0]) for r in rows}


def limit_to_marker_timestamp(query, marker):
    """Keep rows with ``trakt_listed_at >=`` the marker timestamp.

    Rows that share that timestamp and sort below the marker stay in the
    result. Callers drop those in Python. No cutoff when the marker is missing.
    Do not use this when the screen is showing reviewed (older) titles.
    """
    listed_at = getattr(marker, 'trakt_listed_at', None) if marker is not None else None
    if listed_at is None:
        return query
    return query.filter(CachedMedia.trakt_listed_at >= listed_at)


def _count_latest(user: User, media_type: str) -> dict[str, int | str] | None:
    """Latest pile: recent years + hide watched + hide personal lists + unreviewed."""
    min_year = discovery_year_cutoff()
    marker = ReviewMarker.query.filter_by(user_id=user.id, media_type=media_type).first()
    query = (
        CachedMedia.query
        .filter_by(media_type=media_type, feed_source=_FEED_SOURCE)
        .filter(or_(
            CachedMedia.year.is_(None),
            CachedMedia.year >= int(min_year),
        ))
        .order_by(
            CachedMedia.trakt_listed_at.desc(),
            CachedMedia.id.desc(),
        )
    )
    query = limit_to_marker_timestamp(query, marker)
    items = [m for m in query.all() if media_passes_discovery_year(m, min_year)]
    ids = [int(m.trakt_id) for m in items]
    watched = _watched_ids(user.id, media_type, ids)
    listed = _listed_ids(user.id, media_type, ids)

    remaining: list[CachedMedia] = []
    for media in items:
        tid = int(media.trakt_id)
        if tid in watched or tid in listed:
            continue
        if media_has_excluded_genre(media, user):
            continue
        remaining.append(media)

    if marker and remaining:
        marker_id = int(marker.trakt_id)
        marker_index = next(
            (i for i, m in enumerate(remaining) if int(m.trakt_id) == marker_id),
            None,
        )
        # Same-timestamp rows at/under the marker are dropped here.
        # If the marker title itself was filtered out, those ties stay.
        if marker_index is not None:
            remaining = remaining[:marker_index]

    y = len(remaining)
    if y <= 0:
        return None
    x = sum(1 for m in remaining if match_preferences(m, user).get('matched'))
    return _pack(x, y)


def _trakt_id_from_rec_entry(entry: Any, media_type: str) -> int | None:
    blob = (entry or {}).get(media_type) or entry or {}
    ids = blob.get('ids') or {}
    try:
        return int(ids.get('trakt'))
    except (TypeError, ValueError):
        return None


def _count_recs(user: User, media_type: str) -> dict[str, int | str] | None:
    """Recs pile: cached remaining after hide watched + lists (incl. wishlist)."""
    from services.trakt_cache import load_recommendations_cache

    payload = load_recommendations_cache(user.id, media_type, None, allow_stale=True)
    if not payload:
        return None

    ordered: list[int] = []
    seen: set[int] = set()
    for entry in payload:
        tid = _trakt_id_from_rec_entry(entry, media_type)
        if tid is None or tid in seen:
            continue
        seen.add(tid)
        ordered.append(tid)
    if not ordered:
        return None

    media_by_id = {
        int(m.trakt_id): m
        for m in CachedMedia.query.filter(
            CachedMedia.media_type == media_type,
            CachedMedia.trakt_id.in_(ordered),
        ).all()
    }
    watched = _watched_ids(user.id, media_type, ordered)
    listed = _listed_ids(user.id, media_type, ordered)
    wishlisted = _watchlist_ids(user.id, media_type, ordered)

    remaining_media: list[CachedMedia | None] = []
    for tid in ordered:
        if tid in watched or tid in listed or tid in wishlisted:
            continue
        media = media_by_id.get(tid)
        if media_has_excluded_genre(media, user):
            continue
        remaining_media.append(media)

    y = len(remaining_media)
    if y <= 0:
        return None
    x = sum(
        1
        for m in remaining_media
        if m is not None and match_preferences(m, user).get('matched')
    )
    return _pack(x, y)
