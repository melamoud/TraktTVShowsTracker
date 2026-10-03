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
from services.trakt_cache import bump_user_sync_stamp, cache_http_span, cache_is_fresh, log_cache_event

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


_ALL_MEDIA_TYPES = ('movie', 'show')


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


def _full_fingerprint(activities: dict) -> dict:
    """Persist movie+show clocks from one last_activities GET."""
    return activity_fingerprint(activities, _ALL_MEDIA_TYPES)


def _changed_fingerprint_keys(new_fp: dict, stored: dict) -> list[str]:
    return [k for k in new_fp if new_fp.get(k) != stored.get(k)]


def ensure_user_media_fresh(
    user,
    media_types: tuple[str, ...] | None = None,
    *,
    force: bool = False,
    probe: bool = False,
) -> bool:
    """
    Sync watchlist/watched/lists from Trakt when that object is stale.

    Page loads (``probe=False``) use SQLite while ``last_sync_at`` is within the
    admin TTL. The hourly catalog job and Set lists pass ``probe=True`` so a
    cheap ``last_activities`` check still picks up trakt.tv / other-device
    changes. ``force=True`` is Refresh from Trakt (always full pull).
    """
    types = media_types or ('movie', 'show')
    span = cache_http_span()

    if not force and not probe and cache_is_fresh(getattr(user, 'last_sync_at', None)):
        log_cache_event('user_media', 'hit', user=user, calls=0)
        return False

    def _persist(fp: dict) -> None:
        if not fp:
            return
        merged = dict(_stored_fingerprint(user))
        for key, value in fp.items():
            if value is not None:
                merged[key] = value
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
                _persist(_full_fingerprint(activities))
            except Exception as exc:
                logger.warning('Could not store activities after forced sync: %s', exc)
        else:
            logger.warning(
                'Forced media sync incomplete for user %s; leaving activities fingerprint unchanged',
                user.id,
            )
        log_cache_event('user_media', 'fetch', user=user, reason='force', calls=span())
        return True

    need_sync = False
    reason = 'fingerprint'
    fingerprint: dict = {}
    full_fp: dict = {}
    changed_keys: list[str] = []
    try:
        activities = get_last_activities(user)
        full_fp = _full_fingerprint(activities)
        fingerprint = activity_fingerprint(activities, types)
        stored = _stored_fingerprint(user)
        if not user.last_sync_at:
            need_sync = True
            reason = 'empty'
        else:
            changed_keys = _changed_fingerprint_keys(fingerprint, stored)
            if changed_keys:
                need_sync = True
                reason = 'fingerprint:' + '+'.join(changed_keys)
    except Exception as exc:
        logger.warning('last_activities check failed for user %s: %s', user.id, exc)
        # Fallback: periodic sync if activities probe fails.
        if not user.last_sync_at or user.last_sync_at < datetime.utcnow() - _FALLBACK_MAX_AGE:
            need_sync = True
            reason = 'fallback'

    if not need_sync:
        _persist(full_fp)
        log_cache_event('user_media', 'probe', user=user, reason='unchanged', calls=span())
        if 'show' in types:
            try:
                from services.shows_cache import seed_new_shows_inline
                seed_new_shows_inline(user)
            except Exception as exc:
                logger.warning('Latest-aired seed on cache hit failed: %s', exc)
        return False

    ok = sync_user_media_state(user, media_types=types)
    if ok and full_fp:
        _persist(full_fp)
    elif not ok:
        logger.warning(
            'Media sync incomplete for user %s; not advancing activities fingerprint',
            user.id,
        )
    log_cache_event('user_media', 'fetch', user=user, reason=reason, calls=span())
    return True


def sync_all_users_media_membership() -> dict:
    """
    Hourly: last_activities for every active user; full pull only if clocks moved.

    Page loads stay on SQLite. Cross-device / trakt.tv edits land on the next
    catalog run (or Refresh from Trakt / Set lists).
    """
    from models import User

    users = User.query.filter_by(is_active_account=True).all()
    synced = 0
    unchanged = 0
    failed = 0
    for user in users:
        try:
            if ensure_user_media_fresh(user, probe=True):
                synced += 1
            else:
                unchanged += 1
        except Exception as exc:
            failed += 1
            logger.warning('Membership sync failed for user %s: %s', user.id, exc)
    logger.info(
        'Catalog membership check: users=%s synced=%s unchanged=%s failed=%s',
        len(users), synced, unchanged, failed,
    )
    return {
        'users': len(users),
        'synced': synced,
        'unchanged': unchanged,
        'failed': failed,
    }


def note_user_media_write(
    user,
    media_types: tuple[str, ...] | None = None,
    *,
    aspects: tuple[str, ...] | None = None,
) -> None:
    """
    After a local write that already updated the DB cache (watchlist / lists /
    watched / ratings / favorites), bump ``last_sync_at`` and store the current
    ``last_activities`` fingerprint.

    Without that fingerprint, the next My Shows load treats this write as a
    remote change and full-pulls lists. A lagging Trakt GET can put a title
    back on Wishlist / default lists after the user already moved it off.

    ``aspects`` / ``media_types`` are accepted for call-site compatibility.
    """
    try:
        bump_user_sync_stamp(user)
        try:
            activities = get_last_activities(user)
            fp = _full_fingerprint(activities)
            if fp:
                merged = dict(_stored_fingerprint(user))
                for key, value in fp.items():
                    if value is not None:
                        merged[key] = value
                user.trakt_activities_json = json.dumps(merged)
        except Exception as exc:
            logger.warning(
                'Could not refresh activities after media write for user %s: %s',
                user.id, exc,
            )
        db.session.commit()
    except Exception as exc:
        logger.warning('Could not note media write for user %s: %s', user.id, exc)
        try:
            db.session.rollback()
        except Exception:
            pass
