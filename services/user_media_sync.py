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
    fp = {
        'watchlist': watchlist.get('updated_at'),
        'lists': lists.get('updated_at'),
    }
    if 'movie' in types:
        fp['movies_watched'] = movies.get('watched_at')
        fp['movies_watchlisted'] = movies.get('watchlisted_at')
    if 'show' in types:
        fp['episodes_watched'] = episodes.get('watched_at')
        fp['shows_watchlisted'] = shows.get('watchlisted_at')
    return fp


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
        sync_user_media_state(user, media_types=types)
        try:
            activities = get_last_activities(user)
            _persist(activity_fingerprint(activities, types))
        except Exception as exc:
            logger.warning('Could not store activities after forced sync: %s', exc)
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

    sync_user_media_state(user, media_types=types)
    _persist(fingerprint)
    return True


def note_user_media_write(
    user,
    media_types: tuple[str, ...] | None = None,
) -> None:
    """
    After a local write that already updated the DB cache (watchlist / lists /
    watched), refresh the activities fingerprint so the next page load does not
    immediately re-pull everything from Trakt (rate limits / slow second action).
    """
    types = media_types or ('movie', 'show')
    try:
        activities = get_last_activities(user)
        fp = activity_fingerprint(activities, types)
        if not fp:
            return
        merged = dict(_stored_fingerprint(user))
        merged.update(fp)
        _save_fingerprint(user, merged)
        db.session.commit()
    except Exception as exc:
        logger.warning('Could not note media write for user %s: %s', user.id, exc)
        try:
            db.session.rollback()
        except Exception:
            pass
