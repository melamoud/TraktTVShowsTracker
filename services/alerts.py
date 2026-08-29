"""
Auto in-app alerts for titles on alert-enabled lists (default: Wishlist only).

Alert types:
  release_day      — release/first-aired date arrived
  new_streaming    — a new TMDB stream provider appeared (one card per title; unread again on a new vendor)
  season_streaming — a season of a listed show appeared on a streamer
  favorite_actor   — a newly listed catalog title includes a favorite actor
  episode_aired    — a new episode aired
  season_aired     — full season published on one calendar day
  list_add         — user added a title to Wishlist or a personal list
  new_user_login   — admin: first login of a new local user

Dedup / baselines live in AlertEvent so jobs never re-fire the same event.
Unread release/episode alerts are marked read on the next refresh once the
movie or episode is watched on Trakt.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Iterable

from flask import Flask
from services.local_time import local_today
from models import (
    AlertEvent,
    CachedMedia,
    CachedPerson,
    MediaProviderAvailability,
    Notification,
    User,
    UserCalendarEvent,
    UserFavoriteActor,
    UserMediaState,
    db,
)
from services import trakt_client
from services.calendar_view import ensure_user_calendar_fresh
from services.streaming_matcher import get_alert_enabled_list_ids, media_has_excluded_genre
from services.sync_jobs import (
    alert_collection_trakt_ids,
    collection_trakt_ids,
    ensure_local_poster,
    sync_providers_for_media,
)
from services.tmdb_client import is_configured as tmdb_configured

logger = logging.getLogger('app')

ALERT_RELEASE_DAY = 'release_day'
ALERT_NEW_STREAMING = 'new_streaming'
ALERT_SEASON_STREAMING = 'season_streaming'
ALERT_EPISODE_AIRED = 'episode_aired'
ALERT_SEASON_AIRED = 'season_aired'
ALERT_LIST_ADD = 'list_add'
ALERT_FAVORITE_ACTOR = 'favorite_actor'
ALERT_NEW_USER_LOGIN = 'new_user_login'

STREAMING_OFFER_TYPES = ('flatrate', 'ads', 'free')
RELEASE_GRACE_DAYS = 3
FAV_ACTOR_WINDOW_DAYS = 7

# TMDB often lists the same service under channel / tier renames. Alerts key on
# the brand, not the packaging string, so "Paramount Plus Apple TV channel"
# does not re-fire after "Paramount Plus Premium" was already seen.
_PROVIDER_CHANNEL_SUFFIXES = (
    ' apple tv channel',
    ' amazon channel',
    ' roku premium channel',
    ' roku channel',
    ' prime video channel',
)
_PROVIDER_TIER_SUFFIXES = (
    ' premium',
    ' essential',
    ' basic with ads',
    ' with ads',
    ' standard',
    ' basic',
)

_EP_PAYLOAD_RE = re.compile(r'\bS(\d{1,2})E(\d{1,3})\b', re.IGNORECASE)
_SEASON_PAYLOAD_RE = re.compile(r'Full season\s+(\d+)', re.IGNORECASE)
_STREAM_ADDED_DATE_RE = re.compile(
    r'(?:\s*[·•]\s*)(?:added\s+)?(\d{4}-\d{2}-\d{2})\s*$',
    re.IGNORECASE,
)


def normalize_streaming_provider_key(name: str) -> str:
    """Collapse TMDB provider label variants to one alert key.

    Suffixes are stripped until the brand is stable so "Netflix Standard with
    Ads" and a leftover ``netflix standard`` event key both become ``netflix``.
    """
    text = re.sub(r'\s+', ' ', (name or '').strip().lower())
    if not text:
        return ''
    text = text.replace('paramount+', 'paramount plus')
    text = text.replace('disney+', 'disney plus')
    changed = True
    while changed and text:
        changed = False
        for suffix in _PROVIDER_CHANNEL_SUFFIXES:
            if text.endswith(suffix):
                text = text[: -len(suffix)].rstrip()
                changed = True
                break
        if changed:
            continue
        for suffix in _PROVIDER_TIER_SUFFIXES:
            if text.endswith(suffix):
                text = text[: -len(suffix)].rstrip()
                changed = True
                break
    if text in ('hbo max', 'max'):
        return 'max'
    return text


def alert_pref_enabled(user: User, alert_type: str) -> bool:
    """Return whether the user wants this alert type (default on)."""
    prefs = user.preferences
    if prefs is None:
        return True
    if alert_type == ALERT_RELEASE_DAY:
        return bool(getattr(prefs, 'alert_release_day', True))
    if alert_type == ALERT_NEW_STREAMING:
        return bool(getattr(prefs, 'alert_new_streaming', True))
    if alert_type == ALERT_SEASON_STREAMING:
        return bool(getattr(prefs, 'alert_season_streaming', True))
    if alert_type in (ALERT_EPISODE_AIRED, ALERT_SEASON_AIRED):
        return bool(getattr(prefs, 'alert_episode_aired', True))
    if alert_type == ALERT_LIST_ADD:
        return bool(getattr(prefs, 'alert_list_add', True))
    if alert_type == ALERT_FAVORITE_ACTOR:
        return bool(getattr(prefs, 'alert_favorite_actor', True))
    if alert_type == ALERT_NEW_USER_LOGIN:
        return bool(getattr(prefs, 'alert_new_user_login', True))
    return True


def is_finished(user_id: int, media_type: str, trakt_id: int) -> bool:
    """
    True when alerts should stop for this title.

    Movies: marked watched on Trakt.
    Shows: only when episode counts say caught up, or a real Progress summary
    reports 100%. Bare ``progress_percent=100`` from old bulk sync is ignored
    (that falsely skipped shows like Reacher when a new season aired).
    """
    state = UserMediaState.query.filter_by(
        user_id=user_id, media_type=media_type, trakt_id=trakt_id
    ).first()
    if not state:
        return False
    if media_type == 'movie':
        return bool(state.watched)
    aired = state.episodes_aired
    completed = state.episodes_completed
    if aired is not None and completed is not None:
        return int(aired) > 0 and int(completed) >= int(aired)
    if (
        state.progress_detail_at is not None
        and state.progress_percent is not None
        and float(state.progress_percent) >= 100.0
    ):
        return True
    return False


def _event_exists(
    user_id: int,
    alert_type: str,
    media_type: str,
    trakt_id: int,
    payload_key: str,
) -> bool:
    return AlertEvent.query.filter_by(
        user_id=user_id,
        alert_type=alert_type,
        media_type=media_type or '',
        trakt_id=int(trakt_id or 0),
        payload_key=payload_key,
    ).first() is not None


def _record_event(
    user_id: int,
    alert_type: str,
    media_type: str,
    trakt_id: int,
    payload_key: str,
) -> bool:
    """Insert AlertEvent; return True if newly inserted."""
    if _event_exists(user_id, alert_type, media_type, trakt_id, payload_key):
        return False
    db.session.add(AlertEvent(
        user_id=user_id,
        alert_type=alert_type,
        media_type=media_type or '',
        trakt_id=int(trakt_id or 0),
        payload_key=payload_key,
        notified_at=datetime.utcnow(),
    ))
    return True


def _notify(
    user_id: int,
    alert_type: str,
    title: str,
    message: str,
    link: str | None,
    media_type: str,
    trakt_id: int,
    payload_key: str,
) -> bool:
    """
    Create notification + dedup row when prefs allow and event is new.

    When prefs are off, still record the event so turning the type back on
    does not flood with old events.
    """
    if not _record_event(user_id, alert_type, media_type, trakt_id, payload_key):
        return False
    user = db.session.get(User, user_id)
    if user is None or not alert_pref_enabled(user, alert_type):
        return False
    if alert_type != ALERT_NEW_USER_LOGIN and media_type in ('movie', 'show') and trakt_id:
        media = CachedMedia.query.filter_by(
            media_type=media_type, trakt_id=int(trakt_id),
        ).first()
        if media_has_excluded_genre(media, user):
            return False
    db.session.add(Notification(
        user_id=user_id,
        alert_type=alert_type,
        title=title,
        message=message,
        link=link,
        media_type=media_type or None,
        trakt_id=int(trakt_id) if trakt_id else None,
        payload_key=payload_key,
    ))
    if media_type in ('movie', 'show') and trakt_id:
        media = CachedMedia.query.filter_by(
            media_type=media_type, trakt_id=int(trakt_id),
        ).first()
        if media is not None:
            ensure_local_poster(media)
    return True


def _join_list_names(names: list[str]) -> str:
    clean = [n.strip() for n in names if (n or '').strip()]
    if not clean:
        return ''
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f'{clean[0]} and {clean[1]}'
    return f'{", ".join(clean[:-1])}, and {clean[-1]}'


def notify_lists_added(
    user: User,
    media_type: str,
    trakt_id: int,
    list_names: list[str],
    *,
    title: str | None = None,
    list_ids: list[str] | None = None,
) -> bool:
    """Inbox row when the user adds a title to Wishlist and/or personal lists."""
    names = [n.strip() for n in (list_names or []) if (n or '').strip()]
    if not names or media_type not in ('movie', 'show'):
        return False
    media = CachedMedia.query.filter_by(
        media_type=media_type, trakt_id=int(trakt_id),
    ).first()
    display = (title or (media.title if media else '') or f'{media_type} {trakt_id}').strip()
    ids_part = ','.join(sorted({str(x) for x in (list_ids or []) if str(x).strip()}))
    stamp = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
    payload = f'listadd:{stamp}:{ids_part}'[:200]
    return _notify(
        user.id,
        ALERT_LIST_ADD,
        title=display,
        message=f'Added to {_join_list_names(names)}',
        link=f'/catalog/{media_type}/{int(trakt_id)}',
        media_type=media_type,
        trakt_id=int(trakt_id),
        payload_key=payload,
    )


def _notification_payload_key(note: Notification) -> str | None:
    """Prefer stored payload_key; infer from message for older rows."""
    if note.payload_key:
        return str(note.payload_key)
    msg = note.message or ''
    if note.alert_type == ALERT_EPISODE_AIRED:
        m = _EP_PAYLOAD_RE.search(msg)
        if m:
            return f'ep:{int(m.group(1))}:{int(m.group(2))}'
    if note.alert_type == ALERT_SEASON_AIRED:
        m = _SEASON_PAYLOAD_RE.search(msg)
        if m:
            return f'season:{int(m.group(1))}'
    return None


def _season_drop_watched(
    user_id: int,
    trakt_id: int,
    season: int,
    watched_keys: set[tuple[int, int]],
) -> bool:
    """True when every episode recorded for this season drop is watched."""
    season = int(season)
    rows = AlertEvent.query.filter_by(
        user_id=user_id,
        alert_type=ALERT_EPISODE_AIRED,
        media_type='show',
        trakt_id=int(trakt_id),
    ).filter(AlertEvent.payload_key.like(f'ep:{season}:%')).all()
    needed: list[tuple[int, int]] = []
    for row in rows:
        parts = (row.payload_key or '').split(':')
        if len(parts) != 3:
            continue
        try:
            needed.append((int(parts[1]), int(parts[2])))
        except (TypeError, ValueError):
            continue
    if not needed:
        return any(s == season for s, _e in watched_keys)
    return all(key in watched_keys for key in needed)


def mark_episode_alerts_read(
    user: User,
    show_trakt_id: int,
    season: int,
    episode: int,
) -> int:
    """
    Mark unread episode alert(s) read after the user watches that episode here.

    Also clears a season-drop alert when every episode in that drop is now read
    (or is this episode).
    """
    show_trakt_id = int(show_trakt_id)
    season = int(season)
    episode = int(episode)
    payload = f'ep:{season}:{episode}'
    marked = 0
    notes = (
        Notification.query
        .filter(
            Notification.user_id == user.id,
            Notification.is_read.is_(False),
            Notification.media_type == 'show',
            Notification.trakt_id == show_trakt_id,
            Notification.alert_type == ALERT_EPISODE_AIRED,
        )
        .all()
    )
    for note in notes:
        if _notification_payload_key(note) == payload:
            note.is_read = True
            marked += 1

    season_notes = (
        Notification.query
        .filter(
            Notification.user_id == user.id,
            Notification.is_read.is_(False),
            Notification.media_type == 'show',
            Notification.trakt_id == show_trakt_id,
            Notification.alert_type == ALERT_SEASON_AIRED,
        )
        .all()
    )
    for note in season_notes:
        key = _notification_payload_key(note)
        if key != f'season:{season}':
            continue
        # Season drop is cleared when no unread ep alerts remain for its episodes.
        if _season_drop_episodes_cleared(
            user.id, show_trakt_id, season, just_watched=(season, episode),
        ):
            note.is_read = True
            marked += 1

    if marked:
        try:
            db.session.commit()
        except Exception as exc:
            logger.warning('Could not commit episode alert mark-read: %s', exc)
            db.session.rollback()
            return 0
    return marked


def mark_season_alerts_read(user: User, show_trakt_id: int, season: int) -> int:
    """Mark unread episode + season alerts for one season after Mark season watched."""
    show_trakt_id = int(show_trakt_id)
    season = int(season)
    prefix = f'ep:{season}:'
    marked = 0
    notes = (
        Notification.query
        .filter(
            Notification.user_id == user.id,
            Notification.is_read.is_(False),
            Notification.media_type == 'show',
            Notification.trakt_id == show_trakt_id,
            Notification.alert_type.in_((
                ALERT_EPISODE_AIRED, ALERT_SEASON_AIRED, ALERT_SEASON_STREAMING,
            )),
        )
        .all()
    )
    for note in notes:
        key = _notification_payload_key(note)
        if not key:
            continue
        if note.alert_type == ALERT_EPISODE_AIRED and key.startswith(prefix):
            note.is_read = True
            marked += 1
        elif note.alert_type == ALERT_SEASON_AIRED and key == f'season:{season}':
            note.is_read = True
            marked += 1
        elif note.alert_type == ALERT_SEASON_STREAMING and key == f'seasonstream:{season}':
            note.is_read = True
            marked += 1
    if marked:
        try:
            db.session.commit()
        except Exception as exc:
            logger.warning('Could not commit season alert mark-read: %s', exc)
            db.session.rollback()
            return 0
    return marked


def mark_show_alerts_read(user: User, show_trakt_id: int) -> int:
    """Mark all unread episode/season alerts for a show (Mark series watched)."""
    show_trakt_id = int(show_trakt_id)
    notes = (
        Notification.query
        .filter(
            Notification.user_id == user.id,
            Notification.is_read.is_(False),
            Notification.media_type == 'show',
            Notification.trakt_id == show_trakt_id,
            Notification.alert_type.in_((
                ALERT_EPISODE_AIRED, ALERT_SEASON_AIRED, ALERT_SEASON_STREAMING,
            )),
        )
        .all()
    )
    if not notes:
        return 0
    for note in notes:
        note.is_read = True
    try:
        db.session.commit()
    except Exception as exc:
        logger.warning('Could not commit show alert mark-read: %s', exc)
        db.session.rollback()
        return 0
    return len(notes)


def mark_cached_watched_alerts_read(
    user: User,
    notes: list[Notification],
    pair_by_notif: dict[int, tuple] | None = None,
) -> int:
    """
    Mark unread episode/season alerts read using local progress only.

    Used when opening Alerts so a watched episode does not stay unread until
    the next scheduled run. Does not call Trakt. ``pair_by_notif`` supplies
    resolved (media_type, trakt_id) for older rows that never stored them.
    """
    from services.trakt_cache import load_progress_payload, watched_keys_from_payload

    show_notes: dict[int, list[Notification]] = {}
    for note in notes:
        if note.is_read or note.alert_type not in (
            ALERT_EPISODE_AIRED, ALERT_SEASON_AIRED, ALERT_SEASON_STREAMING,
        ):
            continue
        pair = (pair_by_notif or {}).get(note.id)
        media_type = pair[0] if pair else note.media_type
        trakt_id = pair[1] if pair else note.trakt_id
        if media_type != 'show' or not trakt_id:
            continue
        show_notes.setdefault(int(trakt_id), []).append(note)
    if not show_notes:
        return 0

    marked = 0
    for trakt_id, group in show_notes.items():
        finished = is_finished(user.id, 'show', trakt_id)
        watched_keys = watched_keys_from_payload(load_progress_payload(user.id, trakt_id))
        for note in group:
            if finished:
                note.is_read = True
                marked += 1
                continue
            payload = _notification_payload_key(note)
            if not payload:
                continue
            if note.alert_type == ALERT_EPISODE_AIRED and payload.startswith('ep:'):
                try:
                    _prefix, s_raw, e_raw = payload.split(':', 2)
                    key = (int(s_raw), int(e_raw))
                except (TypeError, ValueError):
                    continue
                if key in watched_keys:
                    note.is_read = True
                    marked += 1
            elif note.alert_type == ALERT_SEASON_AIRED and payload.startswith('season:'):
                try:
                    s_num = int(payload.split(':', 1)[1])
                except (TypeError, ValueError):
                    continue
                if _season_drop_watched(user.id, trakt_id, s_num, watched_keys):
                    note.is_read = True
                    marked += 1
            elif note.alert_type == ALERT_SEASON_STREAMING and payload.startswith('seasonstream:'):
                try:
                    s_num = int(payload.split(':', 1)[1])
                except (TypeError, ValueError):
                    continue
                if _season_already_watched(user.id, trakt_id, s_num):
                    note.is_read = True
                    marked += 1
    if marked:
        try:
            db.session.commit()
        except Exception as exc:
            logger.warning('Could not commit cached watched-alert cleanup: %s', exc)
            db.session.rollback()
            return 0
    return marked


def mark_movie_alerts_read(user: User, movie_trakt_id: int) -> int:
    """Mark unread movie release/streaming alerts after Mark watched."""
    movie_trakt_id = int(movie_trakt_id)
    notes = (
        Notification.query
        .filter(
            Notification.user_id == user.id,
            Notification.is_read.is_(False),
            Notification.media_type == 'movie',
            Notification.trakt_id == movie_trakt_id,
            Notification.alert_type.in_((ALERT_RELEASE_DAY, ALERT_NEW_STREAMING)),
        )
        .all()
    )
    if not notes:
        return 0
    for note in notes:
        note.is_read = True
    try:
        db.session.commit()
    except Exception as exc:
        logger.warning('Could not commit movie alert mark-read: %s', exc)
        db.session.rollback()
        return 0
    return len(notes)


def _season_drop_episodes_cleared(
    user_id: int,
    trakt_id: int,
    season: int,
    *,
    just_watched: tuple[int, int] | None = None,
) -> bool:
    """True when no unread episode alerts remain for the season-drop episodes."""
    season = int(season)
    rows = AlertEvent.query.filter_by(
        user_id=user_id,
        alert_type=ALERT_EPISODE_AIRED,
        media_type='show',
        trakt_id=int(trakt_id),
    ).filter(AlertEvent.payload_key.like(f'ep:{season}:%')).all()
    needed: list[str] = []
    for row in rows:
        pk = row.payload_key or ''
        if pk.startswith(f'ep:{season}:'):
            needed.append(pk)
    if not needed:
        return True
    just_payload = None
    if just_watched:
        just_payload = f'ep:{int(just_watched[0])}:{int(just_watched[1])}'
    unread = {
        _notification_payload_key(n)
        for n in Notification.query.filter(
            Notification.user_id == user_id,
            Notification.is_read.is_(False),
            Notification.media_type == 'show',
            Notification.trakt_id == int(trakt_id),
            Notification.alert_type == ALERT_EPISODE_AIRED,
        ).all()
    }
    unread.discard(None)
    for payload in needed:
        if payload == just_payload:
            continue
        if payload in unread:
            return False
    return True


def _mark_watched_alerts_read(user: User, *, rate_limited: bool = False) -> int:
    """
    Mark unread release/episode alerts as read when the movie/episode is watched.

    Runs on each alert refresh so watching on Trakt clears the inbox next pass.
    """
    marked = 0
    movie_notes = (
        Notification.query
        .filter(
            Notification.user_id == user.id,
            Notification.is_read.is_(False),
            Notification.media_type == 'movie',
            Notification.alert_type.in_((ALERT_RELEASE_DAY, ALERT_NEW_STREAMING)),
            Notification.trakt_id.isnot(None),
        )
        .all()
    )
    if movie_notes:
        from services.trakt_cache import cache_http_span, cache_is_fresh, log_cache_event
        if not cache_is_fresh(getattr(user, 'last_sync_at', None)):
            try:
                from services.sync_jobs import sync_user_media_state
                span = cache_http_span()
                sync_user_media_state(user, ('movie',))
                log_cache_event(
                    'user_media', 'fetch', user=user, reason='alerts', calls=span(),
                )
            except Exception as exc:
                logger.warning('Movie watch-state sync before alert cleanup failed: %s', exc)
        movie_ids = {int(n.trakt_id) for n in movie_notes if n.trakt_id}
        watched_ids = {
            int(st.trakt_id)
            for st in UserMediaState.query.filter(
                UserMediaState.user_id == user.id,
                UserMediaState.media_type == 'movie',
                UserMediaState.trakt_id.in_(movie_ids or [-1]),
                UserMediaState.watched.is_(True),
            ).all()
        }
        for note in movie_notes:
            if note.trakt_id and int(note.trakt_id) in watched_ids:
                note.is_read = True
                marked += 1

    show_notes = (
        Notification.query
        .filter(
            Notification.user_id == user.id,
            Notification.is_read.is_(False),
            Notification.media_type == 'show',
            Notification.alert_type.in_((
                ALERT_EPISODE_AIRED, ALERT_SEASON_AIRED, ALERT_SEASON_STREAMING,
            )),
            Notification.trakt_id.isnot(None),
        )
        .all()
    )
    if not show_notes or rate_limited:
        return marked

    by_show: dict[int, list[Notification]] = {}
    for note in show_notes:
        by_show.setdefault(int(note.trakt_id), []).append(note)

    for trakt_id, notes in by_show.items():
        from services.trakt_cache import (
            load_progress_payload,
            progress_cache_is_fresh,
            watched_keys_from_payload,
        )
        watched_keys: set[tuple[int, int]] = set()
        if progress_cache_is_fresh(user.id, trakt_id):
            watched_keys = watched_keys_from_payload(
                load_progress_payload(user.id, trakt_id)
            )
        else:
            try:
                progress = trakt_client.get_show_progress(user, trakt_id)
            except Exception as exc:
                if getattr(exc, 'status_code', None) == 429:
                    logger.warning(
                        'Trakt throttling while clearing watched episode alerts; deferring'
                    )
                    break
                logger.warning(
                    'Could not load progress for show %s while clearing alerts: %s',
                    trakt_id, exc,
                )
                continue
            watched_keys = trakt_client.episode_watched_keys_from_trakt(
                history=None, watched_entry=None, progress=progress or {},
            )
        for note in notes:
            payload = _notification_payload_key(note)
            if not payload:
                continue
            if note.alert_type == ALERT_EPISODE_AIRED and payload.startswith('ep:'):
                try:
                    _prefix, s_raw, e_raw = payload.split(':', 2)
                    key = (int(s_raw), int(e_raw))
                except (TypeError, ValueError):
                    continue
                if key in watched_keys:
                    note.is_read = True
                    marked += 1
            elif note.alert_type == ALERT_SEASON_AIRED and payload.startswith('season:'):
                try:
                    s_num = int(payload.split(':', 1)[1])
                except (TypeError, ValueError):
                    continue
                if _season_drop_watched(user.id, trakt_id, s_num, watched_keys):
                    note.is_read = True
                    marked += 1
            elif note.alert_type == ALERT_SEASON_STREAMING and payload.startswith('seasonstream:'):
                try:
                    s_num = int(payload.split(':', 1)[1])
                except (TypeError, ValueError):
                    continue
                if _season_already_watched(user.id, trakt_id, s_num):
                    note.is_read = True
                    marked += 1
    return marked


def _streaming_provider_names(media: CachedMedia) -> list[str]:
    rows = (
        MediaProviderAvailability.query
        .filter(
            MediaProviderAvailability.cached_media_id == media.id,
            MediaProviderAvailability.offer_type.in_(STREAMING_OFFER_TYPES),
        )
        .all()
    )
    return sorted({(r.provider_name or '').strip() for r in rows if (r.provider_name or '').strip()})


def _provider_keys_by_display(names: Iterable[str]) -> dict[str, str]:
    """Map normalized alert key → shortest display label among variants."""
    by_key: dict[str, str] = {}
    for raw in names:
        name = (raw or '').strip()
        key = normalize_streaming_provider_key(name)
        if not key:
            continue
        prev = by_key.get(key)
        if prev is None or len(name) < len(prev):
            by_key[key] = name
    return by_key


def _seen_streaming_provider_keys(
    user_id: int, media_type: str, trakt_id: int,
) -> set[str]:
    """Normalized provider keys already baselined or notified for this title."""
    keys: set[str] = set()
    rows = AlertEvent.query.filter_by(
        user_id=user_id,
        alert_type=ALERT_NEW_STREAMING,
        media_type=media_type,
        trakt_id=trakt_id,
    ).all()
    for row in rows:
        payload = row.payload_key or ''
        if payload.startswith('provider:'):
            keys.add(normalize_streaming_provider_key(payload[len('provider:'):]))
    return keys


def _parse_air_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith('Z'):
            text = text[:-1] + '+00:00'
        dt = datetime.fromisoformat(text)
        from services.local_time import local_date
        return local_date(dt.replace(tzinfo=None) if dt.tzinfo is None else dt)
    except ValueError:
        pass
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def set_notification_read(user_id: int, row: Notification, is_read: bool) -> None:
    """Mark one alert read/unread. Streaming cards for the same title stay in sync."""
    targets = [row]
    if (
        row.alert_type in (ALERT_NEW_STREAMING, ALERT_SEASON_STREAMING)
        and row.media_type
        and row.trakt_id
    ):
        q = Notification.query.filter_by(
            user_id=user_id,
            alert_type=row.alert_type,
            media_type=row.media_type,
            trakt_id=int(row.trakt_id),
        )
        if row.alert_type == ALERT_SEASON_STREAMING and row.payload_key:
            q = q.filter_by(payload_key=row.payload_key)
        siblings = q.all()
        if siblings:
            targets = siblings
    for note in targets:
        note.is_read = is_read


def notify_admins_new_user(new_user: User) -> int:
    """Notify admins (with pref on) that a new local user completed first login."""
    payload = f'user:{new_user.id}'
    count = 0
    admins = User.query.filter_by(is_admin=True, is_active_account=True).all()
    for admin in admins:
        if admin.id == new_user.id:
            continue
        if _notify(
            admin.id,
            ALERT_NEW_USER_LOGIN,
            title=f'New user: {new_user.username}',
            message=f'{new_user.username} logged in for the first time.',
            link='/admin/users',
            media_type='',
            trakt_id=0,
            payload_key=payload,
        ):
            count += 1
    if count:
        db.session.commit()
    return count


def _check_release_day(user: User, media_type: str, trakt_id: int, media: CachedMedia) -> int:
    """Movie release-day alerts. Shows are skipped: episode/season alerts already
    cover premieres (S01E01), so a show-level release alert only duplicates them."""
    if media_type != 'movie':
        return 0
    if not media.released_at:
        return 0
    today = local_today()
    released = media.released_at
    if released > today:
        return 0
    if (today - released).days > RELEASE_GRACE_DAYS:
        # Too old to be a "just released" alert; mark so we never ping later.
        _record_event(
            user.id, ALERT_RELEASE_DAY, media_type, trakt_id,
            f'release:{released.isoformat()}',
        )
        return 0
    payload = f'release:{released.isoformat()}'
    if _notify(
        user.id,
        ALERT_RELEASE_DAY,
        title=f'Released: {media.title}',
        message=f'Movie release date was {released.isoformat()}.',
        link=f'/catalog/{media_type}/{trakt_id}',
        media_type=media_type,
        trakt_id=trakt_id,
        payload_key=payload,
    ):
        return 1
    return 0


def _check_new_streaming(user: User, media_type: str, trakt_id: int, media: CachedMedia) -> int:
    if not tmdb_configured() or not media.tmdb_id:
        return 0
    sync_providers_for_media(media)
    by_key = _provider_keys_by_display(_streaming_provider_names(media))
    baseline_key = 'baseline:streaming'
    first_seen = not _event_exists(
        user.id, ALERT_NEW_STREAMING, media_type, trakt_id, baseline_key
    )
    if first_seen:
        _record_event(
            user.id, ALERT_NEW_STREAMING, media_type, trakt_id, baseline_key
        )
        for key in by_key:
            _record_event(
                user.id, ALERT_NEW_STREAMING, media_type, trakt_id, f'provider:{key}'
            )
        return 0

    seen = _seen_streaming_provider_keys(user.id, media_type, trakt_id)
    new_items = [(key, display) for key, display in by_key.items() if key not in seen]
    if not new_items:
        return 0
    recorded = False
    for key, _display in new_items:
        if _record_event(
            user.id, ALERT_NEW_STREAMING, media_type, trakt_id, f'provider:{key}',
        ):
            recorded = True
    if not recorded:
        return 0
    return _upsert_streaming_card(
        user, ALERT_NEW_STREAMING, media, trakt_id,
        new_displays=[d for _k, d in new_items],
        payload_key='providers',
        link=f'/catalog/{media_type}/{trakt_id}',
    )


def _upsert_streaming_card(
    user: User,
    alert_type: str,
    media: CachedMedia,
    trakt_id: int,
    *,
    new_displays: list[str],
    payload_key: str,
    link: str,
) -> int:
    """One notification per title (or season). New vendors mark it unread again."""
    if not new_displays:
        return 0
    q = Notification.query.filter_by(
        user_id=user.id,
        alert_type=alert_type,
        media_type=media.media_type,
        trakt_id=int(trakt_id),
    )
    if payload_key != 'providers':
        q = q.filter_by(payload_key=payload_key)
    notes = q.order_by(Notification.id.asc()).all()
    ordered: list[str] = []
    seen_fold: set[str] = set()

    def _add_vendor(name: str) -> None:
        text = (name or '').strip()
        fold = text.casefold()
        brand = normalize_streaming_provider_key(text) or fold
        if (
            not fold or fold in seen_fold or brand in seen_fold
            or fold == (media.title or '').casefold()
            or 'available on' in fold
            or re.fullmatch(r'\d{4}-\d{2}-\d{2}', fold)
            or fold.startswith('added ')
        ):
            return
        seen_fold.add(fold)
        seen_fold.add(brand)
        ordered.append(text)

    for note in notes:
        raw_msg = _STREAM_ADDED_DATE_RE.sub('', note.message or '')
        for part in re.split(r'\s*[·,]\s*|\s+and\s+', raw_msg):
            _add_vendor(part)
        heading = (note.title or '')
        if heading.startswith('Now on ') and ': ' in heading[7:]:
            _add_vendor(heading[7:].split(': ', 1)[0])
    before = len(ordered)
    for name in new_displays:
        _add_vendor(name)
    gained = len(ordered) > before
    if notes and not gained:
        return 0
    vendor_line = _join_list_names(ordered) if len(ordered) <= 2 else ' · '.join(ordered)
    if alert_type == ALERT_SEASON_STREAMING:
        season = payload_key.split(':')[-1] if payload_key.startswith('seasonstream:') else ''
        title = f'Season {season} on stream: {media.title}' if season else f'Season on stream: {media.title}'
        from services.local_time import format_local_date
        added = format_local_date(local_today())
        if added:
            vendor_line = f'{vendor_line} · {added}' if vendor_line else added
    else:
        title = f'Now streaming: {media.title}'
    if not alert_pref_enabled(user, alert_type):
        return 0
    if media_has_excluded_genre(media, user):
        return 0
    ensure_local_poster(media)
    if notes:
        lead = notes[0]
        lead.title = title
        lead.message = vendor_line
        lead.payload_key = payload_key
        lead.link = link
        lead.is_read = False
        lead.created_at = datetime.utcnow()
        for extra in notes[1:]:
            db.session.delete(extra)
        return 1
    db.session.add(Notification(
        user_id=user.id,
        alert_type=alert_type,
        title=title,
        message=vendor_line,
        link=link,
        media_type=media.media_type,
        trakt_id=int(trakt_id),
        payload_key=payload_key,
        is_read=False,
    ))
    return 1


_SEASON_LABEL_RE = re.compile(r'^S(\d{1,2})\b', re.IGNORECASE)


def _season_numbers_to_check(
    user_id: int, trakt_id: int, events: list, state: UserMediaState | None,
) -> set[int]:
    """Latest aired season plus any season with a recently aired episode."""
    today = local_today()
    grace = today - timedelta(days=RELEASE_GRACE_DAYS)
    seasons: set[int] = set()
    for e in events or []:
        if e.season_number:
            seasons.add(int(e.season_number))
    rows = (
        UserCalendarEvent.query
        .filter(
            UserCalendarEvent.user_id == user_id,
            UserCalendarEvent.media_type == 'show',
            UserCalendarEvent.trakt_id == int(trakt_id),
            UserCalendarEvent.season_number.isnot(None),
            UserCalendarEvent.event_date <= today,
        )
        .all()
    )
    latest = 0
    for e in rows:
        s_num = int(e.season_number)
        if s_num > latest:
            latest = s_num
        if e.event_date and e.event_date >= grace:
            seasons.add(s_num)
    if latest:
        seasons.add(latest)
    if state and state.last_episode_label:
        m = _SEASON_LABEL_RE.match(state.last_episode_label.strip())
        if m:
            seasons.add(int(m.group(1)))
    return {s for s in seasons if s >= 1}


def _season_is_recent(user_id: int, trakt_id: int, season: int) -> bool:
    today = local_today()
    grace = today - timedelta(days=RELEASE_GRACE_DAYS)
    row = (
        UserCalendarEvent.query
        .filter(
            UserCalendarEvent.user_id == user_id,
            UserCalendarEvent.media_type == 'show',
            UserCalendarEvent.trakt_id == int(trakt_id),
            UserCalendarEvent.season_number == int(season),
            UserCalendarEvent.event_date >= grace,
            UserCalendarEvent.event_date <= today,
        )
        .first()
    )
    return row is not None


def _season_already_watched(
    user_id: int,
    trakt_id: int,
    season: int,
    state: UserMediaState | None = None,
) -> bool:
    """True when this season is already watched, so season-on-stream is noise."""
    from services.trakt_cache import (
        _keys_to_tuples,
        load_progress_payload,
        watched_keys_from_payload,
    )

    season = int(season)
    if state is None:
        state = UserMediaState.query.filter_by(
            user_id=user_id, media_type='show', trakt_id=int(trakt_id),
        ).first()
    payload = load_progress_payload(user_id, trakt_id)
    if payload:
        watched = watched_keys_from_payload(payload)
        aired = _keys_to_tuples(payload.get('aired_keys'))
        season_aired = {k for k in aired if k[0] == season}
        if season_aired and season_aired <= watched:
            return True
    last_label = (getattr(state, 'last_episode_label', None) or '').strip()
    m = _SEASON_LABEL_RE.match(last_label)
    if m and int(m.group(1)) > season:
        return True
    return False


def _check_season_streaming(
    user: User,
    trakt_id: int,
    media: CachedMedia,
    *,
    events: list,
    state: UserMediaState | None,
) -> int:
    """Alert when a season of a listed show appears (or gains a vendor) on TMDB streaming."""
    if not tmdb_configured() or not media.tmdb_id:
        return 0
    from services.tmdb_client import get_season_watch_providers

    created = 0
    for season in sorted(_season_numbers_to_check(user.id, trakt_id, events, state)):
        try:
            raw = get_season_watch_providers(int(media.tmdb_id), season)
        except Exception as exc:
            logger.warning(
                'Season streaming providers failed for show %s S%s: %s',
                trakt_id, season, exc,
            )
            continue
        names = [
            (p.get('provider_name') or '').strip()
            for p in raw
            if (p.get('offer_type') or '') in STREAMING_OFFER_TYPES
            and (p.get('provider_name') or '').strip()
        ]
        by_key = _provider_keys_by_display(names)
        baseline_key = f'baseline:seasonstream:{season}'
        watched_season = _season_already_watched(user.id, trakt_id, season, state)
        first_seen = not _event_exists(
            user.id, ALERT_SEASON_STREAMING, 'show', trakt_id, baseline_key
        )
        if first_seen:
            _record_event(
                user.id, ALERT_SEASON_STREAMING, 'show', trakt_id, baseline_key
            )
            for key in by_key:
                _record_event(
                    user.id, ALERT_SEASON_STREAMING, 'show', trakt_id,
                    f'seasonstream:{season}:provider:{key}',
                )
            if (
                by_key
                and _season_is_recent(user.id, trakt_id, season)
                and not watched_season
            ):
                created += _upsert_streaming_card(
                    user, ALERT_SEASON_STREAMING, media, trakt_id,
                    new_displays=list(by_key.values()),
                    payload_key=f'seasonstream:{season}',
                    link=f'/shows/{trakt_id}/progress',
                )
            continue
        seen_keys = set()
        for row in AlertEvent.query.filter_by(
            user_id=user.id,
            alert_type=ALERT_SEASON_STREAMING,
            media_type='show',
            trakt_id=int(trakt_id),
        ).all():
            prefix = f'seasonstream:{season}:provider:'
            payload = row.payload_key or ''
            if payload.startswith(prefix):
                seen_keys.add(normalize_streaming_provider_key(payload[len(prefix):]))
        new_items = [(k, d) for k, d in by_key.items() if k not in seen_keys]
        if not new_items:
            continue
        recorded = False
        for key, _display in new_items:
            if _record_event(
                user.id, ALERT_SEASON_STREAMING, 'show', trakt_id,
                f'seasonstream:{season}:provider:{key}',
            ):
                recorded = True
        if not recorded or watched_season:
            continue
        created += _upsert_streaming_card(
            user, ALERT_SEASON_STREAMING, media, trakt_id,
            new_displays=[d for _k, d in new_items],
            payload_key=f'seasonstream:{season}',
            link=f'/shows/{trakt_id}/progress',
        )
    return created


def _ensure_providers(media: CachedMedia) -> None:
    """Warm the provider cache so alert cards can render streaming tags."""
    if _streaming_provider_names(media):
        return
    if tmdb_configured() and media.tmdb_id:
        sync_providers_for_media(media)


def _notify_episode(
    user: User,
    media: CachedMedia,
    trakt_id: int,
    s_num: int,
    e_num: int,
    air: date,
    title: str,
) -> int:
    ep_label = f'S{s_num:02d}E{e_num:02d}'
    if title:
        ep_label = f'{ep_label} — {title}'
    if _notify(
        user.id,
        ALERT_EPISODE_AIRED,
        title=f'New episode: {media.title}',
        message=f'{ep_label} · aired {air.isoformat()}',
        link=f'/shows/{trakt_id}/progress',
        media_type='show',
        trakt_id=trakt_id,
        payload_key=f'ep:{s_num}:{e_num}',
    ):
        return 1
    return 0


def _notify_season_drop(
    user: User,
    media: CachedMedia,
    trakt_id: int,
    s_num: int,
    drop_day: date,
) -> int:
    if _notify(
        user.id,
        ALERT_SEASON_AIRED,
        title=f'Season {s_num} out: {media.title}',
        message=f'Full season {s_num} published on {drop_day.isoformat()}.',
        link=f'/shows/{trakt_id}/progress',
        media_type='show',
        trakt_id=trakt_id,
        payload_key=f'season:{s_num}',
    ):
        return 1
    return 0


def _confirm_full_season_drop(trakt_id: int, season: int) -> date | None:
    """One Trakt call: true full-season drop = every episode aired on one day."""
    try:
        seasons = trakt_client.get_show_seasons(trakt_id)
    except Exception as exc:
        logger.warning('Season-drop confirm failed for show %s: %s', trakt_id, exc)
        return None
    today = local_today()
    for s in seasons or []:
        if s.get('number') is None or int(s['number']) != season:
            continue
        aired_days: list[date] = []
        for ep in s.get('episodes') or []:
            air = _parse_air_date(ep.get('first_aired') or ep.get('released'))
            if air is None:
                return None
            if air > today:
                # Remaining unaired episodes → weekly/partial drop, not season.
                return None
            aired_days.append(air)
        if len(aired_days) >= 2 and len(set(aired_days)) == 1:
            return aired_days[0]
    return None


def _check_episodes_from_calendar(
    user: User,
    trakt_id: int,
    media: CachedMedia,
    events: list,
) -> int:
    """
    Episode/season alerts from cached My-calendar rows (one bulk Trakt call per
    run covers all watchlisted/watched shows). ``events`` are this show's
    UserCalendarEvent rows; only the grace window alerts.
    """
    today = local_today()
    rows = [
        e for e in events
        if e.season_number is not None
        and e.episode_number is not None
        and e.event_date <= today
        and (today - e.event_date).days <= RELEASE_GRACE_DAYS
    ]
    _record_event(user.id, ALERT_EPISODE_AIRED, 'show', trakt_id, 'baseline:episodes')
    if not rows:
        return 0
    _ensure_providers(media)

    created = 0
    by_season: dict[int, list] = {}
    for e in rows:
        by_season.setdefault(int(e.season_number), []).append(e)

    for s_num, eps in by_season.items():
        air_dates = {e.event_date for e in eps}
        if len(air_dates) == 1 and len(eps) >= 2:
            # Suspected full-season drop — confirm with one per-show call so a
            # same-day 2-episode premiere does not masquerade as a season drop.
            drop_day = _confirm_full_season_drop(trakt_id, s_num)
            if drop_day is not None:
                created += _notify_season_drop(
                    user, media, trakt_id, s_num, drop_day,
                )
                for e in eps:
                    _record_event(
                        user.id, ALERT_EPISODE_AIRED, 'show', trakt_id,
                        f'ep:{s_num}:{int(e.episode_number)}',
                    )
                continue
        for e in eps:
            created += _notify_episode(
                user, media, trakt_id, s_num, int(e.episode_number),
                e.event_date, (e.episode_title or '').strip(),
            )
    return created


def _check_episodes(user: User, trakt_id: int, media: CachedMedia) -> int:
    """Per-show fallback for titles the My-calendar bulk feed does not cover."""
    try:
        seasons = trakt_client.get_show_seasons(trakt_id)
    except Exception as exc:
        if getattr(exc, 'status_code', None) == 429:
            raise  # caller stops the whole fallback loop when throttled
        logger.warning('Episode alert fetch failed for show %s: %s', trakt_id, exc)
        return 0

    today = local_today()
    _ensure_providers(media)

    baseline_key = 'baseline:episodes'
    first_seen = not _event_exists(
        user.id, ALERT_EPISODE_AIRED, 'show', trakt_id, baseline_key
    )
    if first_seen:
        # Mark "scanned once" — but do NOT swallow episodes inside the grace
        # window: a fresh install should still alert for yesterday's episode.
        _record_event(user.id, ALERT_EPISODE_AIRED, 'show', trakt_id, baseline_key)

    created = 0
    seasons_meta: list[dict] = []

    for season in seasons or []:
        s_num = season.get('number')
        if s_num is None or int(s_num) <= 0:
            continue  # skip specials
        s_num = int(s_num)
        episodes = season.get('episodes') or []
        ep_rows = []
        for ep in episodes:
            e_num = ep.get('number')
            if e_num is None:
                continue
            e_num = int(e_num)
            air = _parse_air_date(ep.get('first_aired') or ep.get('released'))
            if air is None or air > today:
                continue
            ep_rows.append((e_num, air, ep))
        if ep_rows:
            seasons_meta.append({'number': s_num, 'episodes': ep_rows})

    for season in seasons_meta:
        s_num = season['number']
        ep_rows = season['episodes']
        air_dates = {air for _n, air, _ep in ep_rows}
        season_payload = f'season:{s_num}'
        # Full season drop: every aired episode shares one calendar day.
        if len(air_dates) == 1 and len(ep_rows) >= 2:
            drop_day = next(iter(air_dates))
            if (today - drop_day).days <= RELEASE_GRACE_DAYS:
                created += _notify_season_drop(
                    user, media, trakt_id, s_num, drop_day,
                )
            else:
                # Old drop: record silently so we never backfill-alert it.
                _record_event(
                    user.id, ALERT_SEASON_AIRED, 'show', trakt_id, season_payload,
                )
            # Always mark individual episodes so we never also fire per-ep.
            for e_num, _air, _ep in ep_rows:
                _record_event(
                    user.id, ALERT_EPISODE_AIRED, 'show', trakt_id,
                    f'ep:{s_num}:{e_num}',
                )
            continue

        for e_num, air, ep in ep_rows:
            # Only alert for recently aired episodes (avoid ancient backfill).
            if (today - air).days > RELEASE_GRACE_DAYS:
                _record_event(
                    user.id, ALERT_EPISODE_AIRED, 'show', trakt_id, f'ep:{s_num}:{e_num}'
                )
                continue
            title = (ep.get('title') or '').strip()
            created += _notify_episode(
                user, media, trakt_id, s_num, e_num, air, title,
            )
    return created


def _check_favorite_actor_titles(user: User) -> int:
    """
    Alert when a recently ingested catalog title includes a favorite actor.

    Ingest-only: credits are loaded for new Latest/catalog titles, never by
    polling each actor's filmography. Existing catalog outside the grace
    window is baselined silently. Titles listed before the actor was
    favorited, and titles already on the user's lists or watched, are skipped.
    """
    from services.cast_service import sync_cast_for_media

    fav_rows = (
        db.session.query(UserFavoriteActor, CachedPerson)
        .join(CachedPerson, CachedPerson.id == UserFavoriteActor.person_id)
        .filter(UserFavoriteActor.user_id == user.id)
        .all()
    )
    if not fav_rows:
        return 0

    fav_by_person_id: dict[int, tuple[datetime | None, str]] = {}
    for fav, person in fav_rows:
        fav_by_person_id[person.id] = (
            fav.created_at,
            (person.name or '').strip() or 'Favorite actor',
        )

    cutoff = datetime.utcnow() - timedelta(days=FAV_ACTOR_WINDOW_DAYS)
    titles = CachedMedia.query.filter(
        CachedMedia.media_type.in_(('movie', 'show')),
        CachedMedia.trakt_listed_at.isnot(None),
        CachedMedia.trakt_listed_at >= cutoff,
        CachedMedia.trakt_id.isnot(None),
    ).all()
    if not titles:
        return 0

    owned_movies = collection_trakt_ids(user.id, 'movie')
    owned_shows = collection_trakt_ids(user.id, 'show')
    watched_pairs = {
        (mt, int(tid))
        for mt, tid in UserMediaState.query.filter_by(
            user_id=user.id, watched=True,
        ).with_entities(UserMediaState.media_type, UserMediaState.trakt_id).all()
        if tid
    }
    utc_today = datetime.utcnow().date()
    created = 0
    for media in titles:
        trakt_id = int(media.trakt_id)
        if _event_exists(
            user.id, ALERT_FAVORITE_ACTOR, media.media_type, trakt_id, 'baseline:favactor',
        ):
            continue

        listed_at = media.trakt_listed_at
        listed_day = listed_at.date() if listed_at else None
        too_old = listed_day is None or (utc_today - listed_day).days > RELEASE_GRACE_DAYS
        already_has = (
            (media.media_type, trakt_id) in watched_pairs
            or (media.media_type == 'movie' and trakt_id in owned_movies)
            or (media.media_type == 'show' and trakt_id in owned_shows)
        )
        eligible_ids = set()
        if listed_day is not None:
            for pid, (fav_at, _name) in fav_by_person_id.items():
                if fav_at is None or fav_at.date() <= listed_day:
                    eligible_ids.add(pid)

        if too_old or already_has or not eligible_ids:
            _record_event(
                user.id, ALERT_FAVORITE_ACTOR, media.media_type, trakt_id,
                'baseline:favactor',
            )
            continue

        prefs = user.preferences
        if media_has_excluded_genre(media, user):
            _record_event(
                user.id, ALERT_FAVORITE_ACTOR, media.media_type, trakt_id,
                'baseline:favactor',
            )
            continue
        match_only = bool(getattr(prefs, 'alert_favorite_actor_match_only', True))
        if match_only:
            from services.streaming_matcher import match_preferences
            if not match_preferences(media, user).get('matched'):
                _record_event(
                    user.id, ALERT_FAVORITE_ACTOR, media.media_type, trakt_id,
                    'baseline:favactor',
                )
                continue

        members = list(media.cast_members)
        if not members and media.cast_fetched_at is None:
            members = list(sync_cast_for_media(media))
        elif not members:
            members = list(media.cast_members)

        names: list[str] = []
        seen: set[str] = set()
        for credit in members:
            meta = fav_by_person_id.get(credit.person_id)
            if not meta or credit.person_id not in eligible_ids:
                continue
            _fav_at, actor_name = meta
            fold = actor_name.casefold()
            if fold in seen:
                continue
            seen.add(fold)
            names.append(actor_name)

        _record_event(
            user.id, ALERT_FAVORITE_ACTOR, media.media_type, trakt_id,
            'baseline:favactor',
        )
        if not names:
            continue
        actors = _join_list_names(names)
        created += int(_notify(
            user.id,
            ALERT_FAVORITE_ACTOR,
            title=media.title or 'New title',
            message=actors,
            link=f'/catalog/{media.media_type}/{trakt_id}',
            media_type=media.media_type,
            trakt_id=trakt_id,
            payload_key='favactor',
        ))
    return created


def run_media_alerts(app: Flask) -> int:
    """
    Per-user media cycle: due notifications + My Shows cache refresh.

    Returns total notifications created.
    """
    from services.shows_cache import refresh_shows_cache_for_user

    notified = 0
    with app.app_context():
        users = User.query.filter_by(is_active_account=True).all()
        for user in users:
            try:
                created, rate_limited = _run_alerts_for_user(user)
                notified += created
                # When Trakt throttled the calendar fetch, don't pile per-show
                # calls on top — the next run catches up.
                refresh_shows_cache_for_user(user, skip_per_show=rate_limited)
            except Exception as exc:
                logger.exception('Media alerts failed for user %s: %s', user.id, exc)
                db.session.rollback()
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
    logger.info('Media alerts created %s notifications', notified)
    return notified


def _run_alerts_for_user(user: User) -> tuple[int, bool]:
    """Returns (notifications created, hit Trakt rate limit during this run)."""
    created = 0
    today = local_today()
    win_start = today - timedelta(days=RELEASE_GRACE_DAYS)

    # One bulk pull: /calendars/my covers every watchlisted or in-progress show.
    # Shows only — alerts never read movie calendar rows. The fetch window is
    # ±33 days: the 3-day grace window drives alerts, while the wider pool
    # feeds the My Shows cache (last-aired + upcoming premieres) for free.
    show_events: dict[int, list] = {}
    calendar_ok = False
    rate_limited = False
    try:
        ensure_user_calendar_fresh(
            user, today - timedelta(days=33), 66,
            media_types=('show',), raise_on_rate_limit=True,
        )
        calendar_ok = True
    except Exception as exc:
        logger.warning('Alert calendar sync failed for user %s: %s', user.id, exc)
        rate_limited = getattr(exc, 'status_code', None) == 429
        if rate_limited:
            logger.warning('Trakt is throttling; skipping per-show episode scans this run')
    if calendar_ok:
        for e in UserCalendarEvent.query.filter(
            UserCalendarEvent.user_id == user.id,
            UserCalendarEvent.media_type == 'show',
            UserCalendarEvent.event_date >= win_start,
            UserCalendarEvent.event_date <= today,
        ).all():
            show_events.setdefault(int(e.trakt_id), []).append(e)

    enabled_lists = get_alert_enabled_list_ids(user)
    show_ids = sorted(alert_collection_trakt_ids(user.id, 'show', enabled_lists))
    states = {
        int(st.trakt_id): st
        for st in UserMediaState.query.filter(
            UserMediaState.user_id == user.id,
            UserMediaState.media_type == 'show',
            UserMediaState.trakt_id.in_(show_ids or [-1]),
        ).all()
    }

    for trakt_id in sorted(alert_collection_trakt_ids(user.id, 'movie', enabled_lists)):
        if is_finished(user.id, 'movie', trakt_id):
            continue
        media = CachedMedia.query.filter_by(
            media_type='movie', trakt_id=trakt_id
        ).first()
        if not media:
            continue
        created += _check_release_day(user, 'movie', trakt_id, media)
        created += _check_new_streaming(user, 'movie', trakt_id, media)

    for trakt_id in show_ids:
        media = CachedMedia.query.filter_by(
            media_type='show', trakt_id=trakt_id
        ).first()
        if not media:
            continue
        finished = is_finished(user.id, 'show', trakt_id)
        # Streaming alerts stop when truly caught up; episode alerts still use
        # the calendar so a new season is not skipped by a stale 100% cache.
        if not finished:
            created += _check_new_streaming(user, 'show', trakt_id, media)
        created += _check_season_streaming(
            user, trakt_id, media,
            events=show_events.get(trakt_id, []),
            state=states.get(trakt_id),
        )
        st = states.get(trakt_id)
        covered = bool(st and (st.on_watchlist or st.watched))
        if calendar_ok and covered:
            created += _check_episodes_from_calendar(
                user, trakt_id, media, show_events.get(trakt_id, []),
            )
        elif not finished:
            # List-only never-watched shows (or calendar fetch failed): per-show fetch.
            # When Trakt is throttling, don't pile on — the next run catches up
            # (grace window means nothing is lost).
            if rate_limited:
                continue
            try:
                created += _check_episodes(user, trakt_id, media)
            except Exception as exc:
                if getattr(exc, 'status_code', None) != 429:
                    raise
                rate_limited = True
                logger.warning(
                    'Trakt is throttling; remaining episode scans deferred to next run'
                )
    if not rate_limited:
        try:
            created += _check_favorite_actor_titles(user)
        except Exception as exc:
            if getattr(exc, 'status_code', None) == 429:
                rate_limited = True
                logger.warning('Trakt is throttling; favorite-actor alerts deferred')
            else:
                logger.warning('Favorite-actor alerts failed for user %s: %s', user.id, exc)
    try:
        cleared = _mark_watched_alerts_read(user, rate_limited=rate_limited)
        if cleared:
            logger.info(
                'Marked %s watched movie/episode alert(s) read for user %s',
                cleared, user.id,
            )
    except Exception as exc:
        logger.warning('Watch-based alert cleanup failed for user %s: %s', user.id, exc)
    return created, rate_limited
