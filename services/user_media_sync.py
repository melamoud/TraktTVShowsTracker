"""
Automatic My movies/shows cache invalidation via Trakt /sync/last_activities.

The local DB is a cache — it must refresh when Trakt activity advances, without
requiring a manual “Refresh from Trakt” click.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from models import db
from services import trakt_client
from services.sync_jobs import sync_user_media_state

logger = logging.getLogger('app')

# If last_activities is unreachable, still re-sync after this age.
_FALLBACK_MAX_AGE = timedelta(minutes=30)

# Aspects that local writes can touch (maps to fingerprint keys).
_ASPECT_WATCHLIST = 'watchlist'
_ASPECT_LISTS = 'lists'
_ASPECT_WATCHED = 'watched'
_ASPECT_RATINGS = 'ratings'
_ASPECT_FAVORITES = 'favorites'


def get_last_activities(user) -> dict:
    """Return Trakt /sync/last_activities for the user."""
    return trakt_client.api_request('GET', '/sync/last_activities', user=user) or {}


def activity_fingerprint(activities: dict, media_types: tuple[str, ...]) -> dict:
    """Extract comparable timestamps that affect My movies/shows listings."""
    types = tuple(media_types) or ('movie', 'show')
    watchlist = activities.get('watchlist') or {}
    lists = activities.get('lists') or {}
    movies = activities.get('movies') or {}
    shows = activities.get('shows') or {}
    episodes = activities.get('episodes') or {}
    ratings = activities.get('ratings') or {}
    favorites = activities.get('favorites') or {}
    fp = {
        'watchlist': watchlist.get('updated_at'),
        'lists': lists.get('updated_at'),
        'ratings': ratings.get('updated_at'),
        'favorites': favorites.get('updated_at'),
    }
    if 'movie' in types:
        fp['movies_watched'] = movies.get('watched_at')
        fp['movies_watchlisted'] = movies.get('watchlisted_at')
        fp['movies_rated'] = movies.get('rated_at')
    if 'show' in types:
        fp['episodes_watched'] = episodes.get('watched_at')
        fp['shows_watchlisted'] = shows.get('watchlisted_at')
        fp['shows_rated'] = shows.get('rated_at')
    return fp


def fingerprint_keys_for_aspects(
    aspects: tuple[str, ...],
    media_types: tuple[str, ...],
) -> set[str]:
    """Fingerprint keys touched by a local write of the given aspects."""
    types = tuple(media_types) or ('movie', 'show')
    keys: set[str] = set()
    for aspect in aspects:
        if aspect == _ASPECT_WATCHLIST:
            keys.add('watchlist')
            if 'movie' in types:
                keys.add('movies_watchlisted')
            if 'show' in types:
                keys.add('shows_watchlisted')
        elif aspect == _ASPECT_LISTS:
            keys.add('lists')
        elif aspect == _ASPECT_WATCHED:
            if 'movie' in types:
                keys.add('movies_watched')
            if 'show' in types:
                keys.add('episodes_watched')
        elif aspect == _ASPECT_RATINGS:
            keys.add('ratings')
            if 'movie' in types:
                keys.add('movies_rated')
            if 'show' in types:
                keys.add('shows_rated')
        elif aspect == _ASPECT_FAVORITES:
            keys.add('favorites')
    return keys


def _stored_fingerprint(user) -> dict:
    raw = getattr(user, 'trakt_activities_json', None) or '{}'
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_fingerprint(user, fingerprint: dict) -> None:
    user.trakt_activities_json = json.dumps(fingerprint)
    user.last_sync_at = datetime.utcnow()


def ensure_user_media_fresh(
    user,
    media_types: tuple[str, ...] | None = None,
    *,
    force: bool = False,
) -> bool:
    """
    Sync watchlist/watched/lists from Trakt when stale.

    Uses a cheap ``/sync/last_activities`` check. Returns True when a sync ran.
    ``force=True`` always syncs (manual Refresh button).

    Fingerprint is only advanced after a successful sync so a failed pull cannot
    mark the cache “fresh” and hide remote wishlist/list adds.
    """
    types = media_types or ('movie', 'show')

    def _persist(fp: dict) -> None:
        if not fp:
            return
        merged = dict(_stored_fingerprint(user))
        merged.update(fp)
        _save_fingerprint(user, merged)
        try:
            db.session.commit()
        except Exception as exc:
            logger.warning('Could not store activities after sync: %s', exc)
            db.session.rollback()

    if force:
        ok = sync_user_media_state(user, media_types=types)
        if ok:
            try:
                activities = get_last_activities(user)
                _persist(activity_fingerprint(activities, types))
            except Exception as exc:
                logger.warning('Could not store activities after forced sync: %s', exc)
        else:
            logger.warning(
                'Forced media sync incomplete for user %s; leaving activities fingerprint unchanged',
                user.id,
            )
        return True

    need_sync = False
    fingerprint: dict = {}
    try:
        activities = get_last_activities(user)
        fingerprint = activity_fingerprint(activities, types)
        stored = _stored_fingerprint(user)
        if not user.last_sync_at:
            need_sync = True
        elif any(fingerprint.get(k) != stored.get(k) for k in fingerprint):
            need_sync = True
    except Exception as exc:
        logger.warning('last_activities check failed for user %s: %s', user.id, exc)
        # Fallback: periodic sync if activities probe fails.
        if not user.last_sync_at or user.last_sync_at < datetime.utcnow() - _FALLBACK_MAX_AGE:
            need_sync = True

    if not need_sync:
        return False

    ok = sync_user_media_state(user, media_types=types)
    if ok and fingerprint:
        _persist(fingerprint)
    elif not ok:
        logger.warning(
            'Media sync incomplete for user %s; not advancing activities fingerprint',
            user.id,
        )
    return True


def note_user_media_write(
    user,
    media_types: tuple[str, ...] | None = None,
    *,
    aspects: tuple[str, ...] | None = None,
) -> None:
    """
    After a local write that already updated the DB cache (watchlist / lists /
    watched / ratings / favorites), refresh only the fingerprint keys for those
    aspects so the next page load does not immediately re-pull that slice.

    Important: do **not** copy unrelated Trakt activity timestamps. Doing so
    would mark remote watchlist/list adds as “already synced” without importing
    them (e.g. rating something in-app after adding a show on Trakt.tv).
    """
    types = media_types or ('movie', 'show')
    # Default: assume watchlist-shaped writes when callers omit aspects (legacy).
    write_aspects = aspects or (_ASPECT_WATCHLIST,)
    keys = fingerprint_keys_for_aspects(write_aspects, types)
    if not keys:
        return
    try:
        activities = get_last_activities(user)
        fp = activity_fingerprint(activities, types)
        if not fp:
            return
        merged = dict(_stored_fingerprint(user))
        for key in keys:
            if key in fp:
                merged[key] = fp[key]
        _save_fingerprint(user, merged)
        db.session.commit()
    except Exception as exc:
        logger.warning('Could not note media write for user %s: %s', user.id, exc)
        try:
            db.session.rollback()
        except Exception:
            pass
