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
from datetime import date, datetime
from typing import Iterable

from flask import Flask
from models import (
    AlertEvent,
    CachedMedia,
    MediaProviderAvailability,
    Notification,
    User,
    UserListMembership,
    UserMediaState,
    db,
)
from services import trakt_client
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
# Cap Trakt season fetches per job run (personal tracker scale).
MAX_SHOWS_PER_EPISODE_PASS = 40


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


def _provider_label(names: Iterable[str]) -> str:
    cleaned = [n for n in names if n]
    if not cleaned:
        return 'Streaming service unknown'
    return ', '.join(cleaned)


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
    kind = 'Movie' if media_type == 'movie' else 'Show'
    if _notify(
        user.id,
        ALERT_RELEASE_DAY,
        title=f'Released: {media.title}',
        message=f'{kind} release date was {released.isoformat()}.',
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


def _check_episodes(user: User, trakt_id: int, media: CachedMedia) -> int:
    try:
        seasons = trakt_client.get_show_seasons(trakt_id)
    except Exception as exc:
        logger.warning('Episode alert fetch failed for show %s: %s', trakt_id, exc)
        return 0

    today = date.today()
    providers = _streaming_provider_names(media)
    # Refresh providers opportunistically when empty and TMDB is available.
    if not providers and tmdb_configured() and media.tmdb_id:
        sync_providers_for_media(media)
        providers = _streaming_provider_names(media)
    provider_msg = _provider_label(providers)

    baseline_key = 'baseline:episodes'
    first_seen = not _event_exists(
        user.id, ALERT_EPISODE_AIRED, 'show', trakt_id, baseline_key
    )

    created = 0
    aired_episode_keys: list[tuple[int, int, date]] = []
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
            aired_episode_keys.append((s_num, e_num, air))
        if ep_rows:
            seasons_meta.append({'number': s_num, 'episodes': ep_rows})

    if first_seen:
        _record_event(user.id, ALERT_EPISODE_AIRED, 'show', trakt_id, baseline_key)
        for s_num, e_num, _air in aired_episode_keys:
            _record_event(
                user.id, ALERT_EPISODE_AIRED, 'show', trakt_id, f'ep:{s_num}:{e_num}'
            )
        for season in seasons_meta:
            air_dates = {air for _n, air, _ep in season['episodes']}
            if len(air_dates) == 1:
                _record_event(
                    user.id, ALERT_SEASON_AIRED, 'show', trakt_id,
                    f'season:{season["number"]}',
                )
        return 0

    for season in seasons_meta:
        s_num = season['number']
        ep_rows = season['episodes']
        air_dates = {air for _n, air, _ep in ep_rows}
        season_payload = f'season:{s_num}'
        # Full season drop: every aired episode shares one calendar day, and that
        # day is within the release grace window (or we still haven't reported it).
        if len(air_dates) == 1 and len(ep_rows) >= 2:
            drop_day = next(iter(air_dates))
            if (today - drop_day).days <= RELEASE_GRACE_DAYS or not _event_exists(
                user.id, ALERT_SEASON_AIRED, 'show', trakt_id, season_payload
            ):
                # If already reported as season, skip episode spam via recording eps.
                if _notify(
                    user.id,
                    ALERT_SEASON_AIRED,
                    title=f'Season {s_num} out: {media.title}',
                    message=(
                        f'Full season {s_num} published on {drop_day.isoformat()}. '
                        f'Available on: {provider_msg}'
                    ),
                    link=f'/shows/{trakt_id}/progress',
                    media_type='show',
                    trakt_id=trakt_id,
                    payload_key=season_payload,
                ):
                    created += 1
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
            ep_label = f'S{s_num:02d}E{e_num:02d}'
            if title:
                ep_label = f'{ep_label} — {title}'
            if _notify(
                user.id,
                ALERT_EPISODE_AIRED,
                title=f'New episode: {media.title}',
                message=f'{ep_label} aired {air.isoformat()}. Available on: {provider_msg}',
                link=f'/shows/{trakt_id}/progress',
                media_type='show',
                trakt_id=trakt_id,
                payload_key=f'ep:{s_num}:{e_num}',
            ):
                created += 1
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
    shows_checked = 0
    for media_type in ('movie', 'show'):
        for trakt_id in collection_trakt_ids(user.id, media_type):
            if is_finished(user.id, media_type, trakt_id):
                continue
            media = CachedMedia.query.filter_by(
                media_type=media_type, trakt_id=trakt_id
            ).first()
            if not media:
                continue
            created += _check_release_day(user, media_type, trakt_id, media)
            created += _check_new_streaming(user, media_type, trakt_id, media)
            if media_type == 'show' and shows_checked < MAX_SHOWS_PER_EPISODE_PASS:
                created += _check_episodes(user, trakt_id, media)
                shows_checked += 1
    return created
