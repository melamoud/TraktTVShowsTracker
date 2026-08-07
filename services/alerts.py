"""
Auto in-app alerts for collection titles (Wishlist + personal lists).

Alert types:
  release_day      — release/first-aired date arrived
  new_streaming    — a new TMDB stream provider appeared (per provider)
  episode_aired    — a new episode aired
  season_aired     — full season published on one calendar day
  new_user_login   — admin: first login of a new local user

Dedup / baselines live in AlertEvent so jobs never re-fire the same event.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Iterable

from flask import Flask
from models import (
    AlertEvent,
    CachedMedia,
    MediaProviderAvailability,
    Notification,
    User,
    UserCalendarEvent,
    UserListMembership,
    UserMediaState,
    db,
)
from services import trakt_client
from services.calendar_view import ensure_user_calendar_fresh
from services.sync_jobs import sync_providers_for_media
from services.tmdb_client import is_configured as tmdb_configured

logger = logging.getLogger(__name__)

ALERT_RELEASE_DAY = 'release_day'
ALERT_NEW_STREAMING = 'new_streaming'
ALERT_EPISODE_AIRED = 'episode_aired'
ALERT_SEASON_AIRED = 'season_aired'
ALERT_NEW_USER_LOGIN = 'new_user_login'

STREAMING_OFFER_TYPES = ('flatrate', 'ads', 'free')
RELEASE_GRACE_DAYS = 3


def alert_pref_enabled(user: User, alert_type: str) -> bool:
    """Return whether the user wants this alert type (default on)."""
    prefs = user.preferences
    if prefs is None:
        return True
    if alert_type == ALERT_RELEASE_DAY:
        return bool(getattr(prefs, 'alert_release_day', True))
    if alert_type == ALERT_NEW_STREAMING:
        return bool(getattr(prefs, 'alert_new_streaming', True))
    if alert_type in (ALERT_EPISODE_AIRED, ALERT_SEASON_AIRED):
        return bool(getattr(prefs, 'alert_episode_aired', True))
    if alert_type == ALERT_NEW_USER_LOGIN:
        return bool(getattr(prefs, 'alert_new_user_login', True))
    return True


def collection_trakt_ids(user_id: int, media_type: str) -> set[int]:
    """Titles on Wishlist or any cached personal list for this user."""
    ids: set[int] = set()
    for tid, in UserMediaState.query.filter_by(
        user_id=user_id, media_type=media_type, on_watchlist=True
    ).with_entities(UserMediaState.trakt_id).all():
        ids.add(int(tid))
    for tid, in UserListMembership.query.filter_by(
        user_id=user_id, media_type=media_type
    ).with_entities(UserListMembership.trakt_id).all():
        ids.add(int(tid))
    return ids


def is_finished(user_id: int, media_type: str, trakt_id: int) -> bool:
    """
    True when alerts should stop for this title.

    Movies: marked watched on Trakt.
    Shows: progress_percent >= 100 when known (started ≠ finished).
    """
    state = UserMediaState.query.filter_by(
        user_id=user_id, media_type=media_type, trakt_id=trakt_id
    ).first()
    if not state:
        return False
    if media_type == 'movie':
        return bool(state.watched)
    if state.progress_percent is not None and state.progress_percent >= 100.0:
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
    db.session.add(Notification(
        user_id=user_id,
        alert_type=alert_type,
        title=title,
        message=message,
        link=link,
        media_type=media_type or None,
        trakt_id=int(trakt_id) if trakt_id else None,
    ))
    return True


def _streaming_provider_names(media: CachedMedia) -> list[str]:
    rows = (
        MediaProviderAvailability.query
        .filter(
            MediaProviderAvailability.cached_media_id == media.id,
            MediaProviderAvailability.offer_type.in_(STREAMING_OFFER_TYPES),
        )
        .all()
    )
    return sorted({r.provider_name for r in rows if r.provider_name})


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
        return dt.date()
    except ValueError:
        pass
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


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
    today = date.today()
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
    names = _streaming_provider_names(media)
    baseline_key = 'baseline:streaming'
    first_seen = not _event_exists(
        user.id, ALERT_NEW_STREAMING, media_type, trakt_id, baseline_key
    )
    if first_seen:
        _record_event(
            user.id, ALERT_NEW_STREAMING, media_type, trakt_id, baseline_key
        )
        for name in names:
            _record_event(
                user.id, ALERT_NEW_STREAMING, media_type, trakt_id, f'provider:{name}'
            )
        return 0

    created = 0
    for name in names:
        payload = f'provider:{name}'
        if _notify(
            user.id,
            ALERT_NEW_STREAMING,
            title=f'Now on {name}: {media.title}',
            message=f'{media.title} is available on {name}.',
            link=f'/catalog/{media_type}/{trakt_id}',
            media_type=media_type,
            trakt_id=trakt_id,
            payload_key=payload,
        ):
            created += 1
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
    """One Trakt call: verify every aired episode of the season shares one day."""
    try:
        seasons = trakt_client.get_show_seasons(trakt_id)
    except Exception as exc:
        logger.warning('Season-drop confirm failed for show %s: %s', trakt_id, exc)
        return None
    today = date.today()
    for s in seasons or []:
        if s.get('number') is None or int(s['number']) != season:
            continue
        aired = []
        for ep in s.get('episodes') or []:
            air = _parse_air_date(ep.get('first_aired') or ep.get('released'))
            if air and air <= today:
                aired.append(air)
        if len(aired) >= 2 and len(set(aired)) == 1:
            return aired[0]
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
    today = date.today()
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
        logger.warning('Episode alert fetch failed for show %s: %s', trakt_id, exc)
        return 0

    today = date.today()
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


def run_media_alerts(app: Flask) -> int:
    """
    Scan all active users' collection titles and create due notifications.

    Returns total notifications created.
    """
    notified = 0
    with app.app_context():
        users = User.query.filter_by(is_active_account=True).all()
        for user in users:
            try:
                notified += _run_alerts_for_user(user)
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


def _run_alerts_for_user(user: User) -> int:
    created = 0
    today = date.today()
    win_start = today - timedelta(days=RELEASE_GRACE_DAYS)

    # One bulk pull: /calendars/my covers every watchlisted or in-progress show.
    show_events: dict[int, list] = {}
    calendar_ok = False
    try:
        ensure_user_calendar_fresh(user, win_start, RELEASE_GRACE_DAYS + 1)
        calendar_ok = True
    except Exception as exc:
        logger.warning('Alert calendar sync failed for user %s: %s', user.id, exc)
    if calendar_ok:
        for e in UserCalendarEvent.query.filter(
            UserCalendarEvent.user_id == user.id,
            UserCalendarEvent.media_type == 'show',
            UserCalendarEvent.event_date >= win_start,
            UserCalendarEvent.event_date <= today,
        ).all():
            show_events.setdefault(int(e.trakt_id), []).append(e)

    show_ids = sorted(collection_trakt_ids(user.id, 'show'))
    states = {
        int(st.trakt_id): st
        for st in UserMediaState.query.filter(
            UserMediaState.user_id == user.id,
            UserMediaState.media_type == 'show',
            UserMediaState.trakt_id.in_(show_ids or [-1]),
        ).all()
    }

    for trakt_id in sorted(collection_trakt_ids(user.id, 'movie')):
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
        if is_finished(user.id, 'show', trakt_id):
            continue
        media = CachedMedia.query.filter_by(
            media_type='show', trakt_id=trakt_id
        ).first()
        if not media:
            continue
        # No release_day for shows: the S01E01 episode alert already announces
        # a premiere — a separate "Released" alert only duplicates it.
        created += _check_new_streaming(user, 'show', trakt_id, media)
        st = states.get(trakt_id)
        covered = bool(st and (st.on_watchlist or st.watched))
        if calendar_ok and covered:
            created += _check_episodes_from_calendar(
                user, trakt_id, media, show_events.get(trakt_id, []),
            )
        else:
            # List-only never-watched shows (or calendar fetch failed): per-show fetch.
            created += _check_episodes(user, trakt_id, media)
    return created
