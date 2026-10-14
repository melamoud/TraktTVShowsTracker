"""
Push movie and episode dates onto the user's chosen Google Calendar.

Eligible titles are on Wishlist or a list marked Auto-select (a default list).
A title that sits only on some other personal list is ignored.

Meetings are created when a date is known:

- Movie in theaters or with an upcoming release → all-day meeting on that date
- Movie that later appears on one of the user's streaming services → all-day
  meeting that day. A future release uses the release date. Movies already
  streaming the first time they are seen do not get a catch-up meeting
- Show episode with an air date today or later, and the show is on one of the
  user's streaming services → all-day meeting on the air date

The description includes the overview, genres, runtime, cast, and which of the
user's services have it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from models import (
    CachedMedia,
    CalendarStreamingSeen,
    ExternalCalendarEvent,
    User,
    UserCalendarEvent,
    UserGoogleCalendar,
    db,
)
from services.availability import THEATER_DAYS
from services.google_calendar import (
    GoogleCalendarError,
    google_configured,
    load_client,
)
from services.local_time import local_today
from services.streaming_matcher import (
    WATCHLIST_LIST_ID,
    get_default_selected_list_ids,
    media_genres,
    split_providers_for_user,
)
from services.sync_jobs import alert_collection_trakt_ids

logger = logging.getLogger('app')

_CAST_LIMIT = 12
_STREAMING_OFFERS = ('flatrate', 'ads', 'free')
_REMINDER_METHODS = ('popup', 'email', 'none')
_REMINDER_UNITS = ('minutes', 'hours', 'days')
_MAX_REMINDER_MINUTES = 40320  # 28 days, Google Calendar's limit
_DEFAULT_REMINDER_MINUTES = 1440  # 1 day before the all-day meeting


@dataclass
class PlannedMeeting:
    """One Google Calendar event we want to exist."""

    media_type: str
    trakt_id: int
    kind: str
    season_number: int
    episode_number: int
    event_date: date
    summary: str
    description: str

    @property
    def key(self) -> tuple:
        return (
            self.media_type,
            int(self.trakt_id),
            self.kind,
            int(self.season_number),
            int(self.episode_number),
        )

    @property
    def content_hash(self) -> str:
        blob = f'{self.event_date.isoformat()}\n{self.summary}\n{self.description}'
        return hashlib.sha256(blob.encode('utf-8')).hexdigest()


def meeting_reminder(user: User) -> tuple[str, int]:
    """Notification method and minutes-before for every meeting."""
    prefs = getattr(user, 'preferences', None)
    method = 'popup'
    minutes = _DEFAULT_REMINDER_MINUTES
    if prefs is not None:
        raw = (getattr(prefs, 'calendar_reminder_method', None) or 'popup').strip().lower()
        if raw in _REMINDER_METHODS:
            method = raw
        raw_minutes = getattr(prefs, 'calendar_reminder_minutes', None)
        if raw_minutes is not None:
            try:
                minutes = int(raw_minutes)
            except (TypeError, ValueError):
                minutes = _DEFAULT_REMINDER_MINUTES
    return method, max(0, min(minutes, _MAX_REMINDER_MINUTES))


def split_reminder_minutes(minutes: int) -> tuple[int, str]:
    """Turn stored minutes into a number plus minutes, hours, or days."""
    minutes = max(0, min(int(minutes), _MAX_REMINDER_MINUTES))
    if minutes and minutes % 1440 == 0:
        return minutes // 1440, 'days'
    if minutes and minutes % 60 == 0:
        return minutes // 60, 'hours'
    return minutes, 'minutes'


def combine_reminder_minutes(amount, unit: str) -> int:
    """Validate a lead time. Raises GoogleCalendarError when it is not usable."""
    unit = (unit or '').strip().lower()
    if unit not in _REMINDER_UNITS:
        raise GoogleCalendarError('Choose minutes, hours, or days.')
    try:
        count = int(amount)
    except (TypeError, ValueError):
        raise GoogleCalendarError('Enter a whole number for how long before.')
    if count < 0:
        raise GoogleCalendarError('Time before cannot be negative.')
    factor = {'minutes': 1, 'hours': 60, 'days': 1440}[unit]
    minutes = count * factor
    if minutes > _MAX_REMINDER_MINUTES:
        raise GoogleCalendarError('Reminders can be at most 28 days before the meeting.')
    return minutes


def reminder_label(method: str, minutes: int) -> str:
    if method == 'none':
        return 'No reminder'
    amount, unit = split_reminder_minutes(minutes)
    word = {'minutes': 'minute', 'hours': 'hour', 'days': 'day'}[unit] if amount == 1 else unit
    kind = 'Email' if method == 'email' else 'Popup'
    return f'{kind}, {amount} {word} before'


def calendar_list_ids(user: User) -> list[str]:
    """Wishlist, plus every list the user marked Auto-select."""
    ids = list(get_default_selected_list_ids(user))
    if WATCHLIST_LIST_ID not in ids:
        ids.insert(0, WATCHLIST_LIST_ID)
    return ids


def _clip(text: str, limit: int) -> str:
    text = (text or '').strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + '…'


def _characters(raw: str | None) -> list[str]:
    try:
        data = json.loads(raw or '[]')
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item).strip() for item in data if str(item).strip()]


def _cast_lines(media: CachedMedia, user: User) -> list[str]:
    favorites = {row.person_id for row in (user.favorite_actors or [])}
    credits = sorted(media.cast_members or [], key=lambda c: (c.sort_order or 0, c.id or 0))
    lines: list[str] = []
    seen: set[int] = set()
    for credit in credits:
        person = credit.person
        if not person or person.id in seen:
            continue
        seen.add(person.id)
        chars = _characters(credit.characters_json)
        line = person.name or 'Unknown'
        if chars:
            line += ' as ' + ', '.join(chars)
        if person.id in favorites:
            line += ' (favorite)'
        lines.append(line)
        if len(lines) >= _CAST_LIMIT:
            break
    return lines


def _my_vendors(user: User, media: CachedMedia) -> list[str]:
    names = [
        p.provider_name
        for p in (media.providers or [])
        if (getattr(p, 'offer_type', None) or 'flatrate') in _STREAMING_OFFERS
        and (p.provider_name or '').strip()
    ]
    mine, _other = split_providers_for_user(names, user)
    return mine


def _tracker_url(media: CachedMedia) -> str:
    from flask import current_app, has_app_context

    if not has_app_context():
        return ''
    host = (current_app.config.get('PUBLIC_HOST') or 'localhost').strip()
    try:
        port = int(current_app.config.get('PORT') or 8300)
    except (TypeError, ValueError):
        port = 8300
    if host in ('localhost', '127.0.0.1'):
        base = f'https://localhost:{port}'
    elif port in (80, 443):
        scheme = 'https' if port == 443 else 'http'
        base = f'{scheme}://{host}'
    else:
        base = f'https://{host}:{port}'
    return f'{base}/catalog/{media.media_type}/{int(media.trakt_id)}'


def _description(
    media: CachedMedia,
    user: User,
    *,
    headline: str,
    vendors: list[str],
) -> str:
    lines = [headline]
    year_bit = f' ({media.year})' if media.year else ''
    if year_bit and year_bit not in headline:
        lines[0] = headline
    overview = _clip(media.overview or '', 1500)
    if overview:
        lines.append('')
        lines.append(overview)
    meta: list[str] = []
    if media.runtime:
        meta.append(f'Runtime: {int(media.runtime)} min')
    genres = media_genres(media)
    if genres:
        meta.append('Genres: ' + ', '.join(genres))
    if media.network:
        meta.append(f'Network: {media.network}')
    if meta:
        lines.append('')
        lines.extend(meta)
    cast = _cast_lines(media, user)
    if cast:
        lines.append('')
        lines.append('Cast:')
        lines.extend(f'- {line}' for line in cast)
    if vendors:
        lines.append('')
        lines.append('On your streaming services: ' + ', '.join(vendors))
    url = _tracker_url(media)
    if url:
        lines.append('')
        lines.append(url)
    return '\n'.join(lines)


def _title_with_year(media: CachedMedia) -> str:
    title = (media.title or 'Untitled').strip()
    if media.year:
        return f'{title} ({media.year})'
    return title


def _theater_date(media: CachedMedia, today: date) -> date | None:
    released = getattr(media, 'released_at', None)
    if not isinstance(released, date):
        return None
    if released >= today - timedelta(days=THEATER_DAYS):
        return released
    return None


def _providers_known(media: CachedMedia) -> bool:
    """True once TMDB providers have been stored for this title."""
    if getattr(media, 'provider_checked_at', None):
        return True
    return bool(list(media.providers or []))


def _seen_streaming_vendors(user: User) -> dict[int, set[str]]:
    rows = CalendarStreamingSeen.query.filter_by(user_id=user.id).all()
    found: dict[int, set[str]] = {}
    for row in rows:
        try:
            names = json.loads(row.vendors_json or '[]')
        except (TypeError, json.JSONDecodeError):
            names = []
        found[int(row.trakt_id)] = {str(name).casefold() for name in names}
    return found


def _remember_streaming_vendors(user: User, media: CachedMedia, vendors: list[str]) -> None:
    row = CalendarStreamingSeen.query.filter_by(
        user_id=user.id, trakt_id=int(media.trakt_id),
    ).first()
    payload = json.dumps(vendors)
    if row:
        row.vendors_json = payload
        row.updated_at = datetime.utcnow()
        return
    db.session.add(CalendarStreamingSeen(
        user_id=user.id,
        trakt_id=int(media.trakt_id),
        vendors_json=payload,
    ))


def _streaming_date(
    media: CachedMedia,
    today: date,
    vendors: list[str],
    seen: set[str] | None,
    existing: date | None,
) -> date | None:
    """
    Date for a streaming meeting, or None when no meeting should exist.

    A future release is booked on that date. A title already on the user's
    service the first time providers are known is only recorded, not booked.
    A service that shows up after that gets a meeting on the day it appears.
    """
    if not vendors:
        return None
    released = getattr(media, 'released_at', None)
    if isinstance(released, date) and released > today:
        return released
    if seen is None:
        return None
    fresh = any(name.casefold() not in seen for name in vendors)
    if existing and not fresh:
        return existing
    if fresh:
        return existing or today
    return None


def _eligible_ids(user: User, media_type: str) -> set[int]:
    return alert_collection_trakt_ids(user.id, media_type, calendar_list_ids(user))


def _load_media(media_type: str, trakt_ids: set[int]) -> list[CachedMedia]:
    if not trakt_ids:
        return []
    return CachedMedia.query.filter(
        CachedMedia.media_type == media_type,
        CachedMedia.trakt_id.in_(trakt_ids),
    ).all()


def plan_meetings(user: User, today: date | None = None) -> list[PlannedMeeting]:
    """Meetings that should exist for this user's eligible titles."""
    today = today or local_today()
    movie_ids = _eligible_ids(user, 'movie')
    show_ids = _eligible_ids(user, 'show')
    planned: list[PlannedMeeting] = []

    existing_stream = {
        int(row.trakt_id): row.event_date
        for row in ExternalCalendarEvent.query.filter_by(
            user_id=user.id, media_type='movie', kind='streaming',
        ).all()
        if row.event_date
    }
    seen_vendors = _seen_streaming_vendors(user)

    for media in _load_media('movie', movie_ids):
        vendors = _my_vendors(user, media)
        theater = _theater_date(media, today)
        titled = _title_with_year(media)
        if theater:
            planned.append(PlannedMeeting(
                media_type='movie',
                trakt_id=int(media.trakt_id),
                kind='theater',
                season_number=0,
                episode_number=0,
                event_date=theater,
                summary=_clip(f'In theaters: {titled}', 180),
                description=_description(
                    media, user,
                    headline=f'In theaters {theater.isoformat()}: {titled}',
                    vendors=vendors,
                ),
            ))
        stream_day = _streaming_date(
            media,
            today,
            vendors,
            seen_vendors.get(int(media.trakt_id)),
            existing_stream.get(int(media.trakt_id)),
        )
        if stream_day:
            if len(vendors) == 1:
                summary = f'Streaming on {vendors[0]}: {titled}'
            else:
                summary = f'Streaming: {titled}'
            planned.append(PlannedMeeting(
                media_type='movie',
                trakt_id=int(media.trakt_id),
                kind='streaming',
                season_number=0,
                episode_number=0,
                event_date=stream_day,
                summary=_clip(summary, 180),
                description=_description(
                    media, user,
                    headline=f'Streaming {stream_day.isoformat()}: {titled}',
                    vendors=vendors,
                ),
            ))

    if not show_ids:
        return planned

    episodes = UserCalendarEvent.query.filter(
        UserCalendarEvent.user_id == user.id,
        UserCalendarEvent.media_type == 'show',
        UserCalendarEvent.trakt_id.in_(show_ids),
        UserCalendarEvent.event_date >= today,
        UserCalendarEvent.season_number.isnot(None),
        UserCalendarEvent.episode_number.isnot(None),
    ).all()
    by_show: dict[int, list] = {}
    for row in episodes:
        by_show.setdefault(int(row.trakt_id), []).append(row)

    for media in _load_media('show', show_ids):
        vendors = _my_vendors(user, media)
        if not vendors:
            continue
        titled = _title_with_year(media)
        for row in by_show.get(int(media.trakt_id), []):
            season = int(row.season_number)
            episode = int(row.episode_number)
            ep_title = (row.episode_title or '').strip()
            label = f'S{season:02d}E{episode:02d}'
            if ep_title:
                label = f'{label} — {ep_title}'
            planned.append(PlannedMeeting(
                media_type='show',
                trakt_id=int(media.trakt_id),
                kind='episode',
                season_number=season,
                episode_number=episode,
                event_date=row.event_date,
                summary=_clip(f'{titled} {label}', 180),
                description=_description(
                    media, user,
                    headline=f'{titled}\n{label}\nAirs {row.event_date.isoformat()}',
                    vendors=vendors,
                ),
            ))
    return planned


def _google_body(plan: PlannedMeeting, method: str, minutes: int) -> dict:
    end = plan.event_date + timedelta(days=1)
    if method == 'none':
        reminders = {'useDefault': False, 'overrides': []}
    else:
        reminders = {
            'useDefault': False,
            'overrides': [{'method': method, 'minutes': minutes}],
        }
    return {
        'summary': plan.summary,
        'description': plan.description[:8000],
        'start': {'date': plan.event_date.isoformat()},
        'end': {'date': end.isoformat()},
        'reminders': reminders,
        'extendedProperties': {
            'private': {
                'tvtracker': (
                    f'{plan.media_type}:{plan.trakt_id}:{plan.kind}:'
                    f'{plan.season_number}:{plan.episode_number}'
                ),
            },
        },
    }


def _stored_hash(plan: PlannedMeeting, method: str, minutes: int) -> str:
    blob = f'{plan.content_hash}\n{method}\n{minutes}'
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()


def _row_key(row: ExternalCalendarEvent) -> tuple:
    return (
        row.media_type,
        int(row.trakt_id),
        row.kind,
        int(row.season_number or 0),
        int(row.episode_number or 0),
    )


def sync_external_calendar(user: User, client=None) -> dict:
    """
    Create, update, or remove Google meetings so they match known dates.

    ``client`` is injectable for tests. Upcoming meetings that no longer apply
    (title left Wishlist / default lists, or the date was dropped) are deleted.
    Meetings whose date is already in the past are left on the calendar.
    """
    link = UserGoogleCalendar.query.filter_by(user_id=user.id).first()
    if not link or not link.calendar_id or not link.refresh_token_enc:
        return {'skipped': True, 'created': 0, 'updated': 0, 'deleted': 0}
    if client is None:
        client = load_client(link)

    today = local_today()
    reminder_method, reminder_minutes = meeting_reminder(user)
    planned = {item.key: item for item in plan_meetings(user, today)}
    for media in _load_media('movie', _eligible_ids(user, 'movie')):
        if _providers_known(media):
            _remember_streaming_vendors(user, media, _my_vendors(user, media))
    existing = {
        _row_key(row): row
        for row in ExternalCalendarEvent.query.filter_by(user_id=user.id).all()
    }
    created = updated = deleted = 0

    for key, plan in planned.items():
        row = existing.get(key)
        body = _google_body(plan, reminder_method, reminder_minutes)
        event_hash = _stored_hash(plan, reminder_method, reminder_minutes)
        if (
            row
            and row.google_event_id
            and row.calendar_id == link.calendar_id
            and row.event_date == plan.event_date
            and row.content_hash == event_hash
        ):
            continue
        try:
            if row and row.google_event_id and row.calendar_id and row.calendar_id != link.calendar_id:
                try:
                    client.delete_event(row.calendar_id, row.google_event_id)
                except GoogleCalendarError:
                    logger.warning(
                        'Could not remove meeting %s from previous calendar',
                        row.google_event_id,
                    )
                row.google_event_id = None
            if row and row.google_event_id and row.calendar_id == link.calendar_id:
                try:
                    client.patch_event(link.calendar_id, row.google_event_id, body)
                except GoogleCalendarError as exc:
                    if exc.status_code != 404:
                        raise
                    row.google_event_id = client.insert_event(link.calendar_id, body)
                updated += 1
            else:
                event_id = client.insert_event(link.calendar_id, body)
                if not row:
                    row = ExternalCalendarEvent(
                        user_id=user.id,
                        media_type=plan.media_type,
                        trakt_id=plan.trakt_id,
                        kind=plan.kind,
                        season_number=plan.season_number,
                        episode_number=plan.episode_number,
                    )
                    db.session.add(row)
                row.google_event_id = event_id
                created += 1
        except GoogleCalendarError as exc:
            logger.warning(
                'Skipped meeting %s %s for user %s: %s',
                plan.media_type, plan.trakt_id, user.id, exc,
            )
            if row is not None:
                state = db.inspect(row)
                if state.persistent:
                    db.session.refresh(row)
            continue
        row.event_date = plan.event_date
        row.calendar_id = link.calendar_id
        row.content_hash = event_hash
        row.updated_at = datetime.utcnow()
        db.session.commit()

    for key, row in existing.items():
        if key in planned:
            continue
        if row.event_date and row.event_date < today:
            continue
        if row.google_event_id and (row.calendar_id or link.calendar_id):
            try:
                client.delete_event(row.calendar_id or link.calendar_id, row.google_event_id)
            except GoogleCalendarError as exc:
                logger.warning(
                    'Could not delete Google meeting %s for user %s: %s',
                    row.google_event_id, user.id, exc,
                )
                continue
        db.session.delete(row)
        deleted += 1
        db.session.commit()

    db.session.commit()
    logger.info(
        'Google Calendar sync user=%s created=%s updated=%s deleted=%s',
        user.id, created, updated, deleted,
    )
    return {'skipped': False, 'created': created, 'updated': updated, 'deleted': deleted}


def sync_external_calendar_quietly(user: User) -> None:
    """Sync when a calendar is selected. Failures are logged, not raised."""
    try:
        link = UserGoogleCalendar.query.filter_by(user_id=getattr(user, 'id', None)).first()
        if not link or not link.calendar_id or not link.refresh_token_enc:
            return
        sync_external_calendar(user)
    except Exception:
        logger.exception(
            'Google Calendar sync failed for user %s', getattr(user, 'id', None),
        )
        try:
            db.session.rollback()
        except Exception:
            pass


def disconnect_google_calendar(user: User) -> None:
    """
    Stop writing meetings.

    Upcoming meetings this app created are removed. Past meetings stay.
    """
    link = UserGoogleCalendar.query.filter_by(user_id=user.id).first()
    rows = ExternalCalendarEvent.query.filter_by(user_id=user.id).all()
    client = None
    if link and link.refresh_token_enc and link.calendar_id:
        try:
            client = load_client(link)
        except GoogleCalendarError:
            client = None
    today = local_today()
    for row in rows:
        if (
            client
            and row.google_event_id
            and row.event_date
            and row.event_date >= today
        ):
            try:
                client.delete_event(row.calendar_id or link.calendar_id, row.google_event_id)
            except GoogleCalendarError:
                logger.warning(
                    'Could not delete meeting %s while disconnecting user %s',
                    row.google_event_id, user.id,
                )
        db.session.delete(row)
    if link:
        db.session.delete(link)
    db.session.commit()


def schedule_external_calendar_sync(user_id: int) -> None:
    """Write meetings after the page has already responded."""
    from flask import current_app

    app = current_app._get_current_object()

    def _run() -> None:
        with app.app_context():
            try:
                user = db.session.get(User, user_id)
                if user is not None:
                    sync_external_calendar(user)
            except Exception:
                logger.exception('Google Calendar sync failed for user %s', user_id)
            finally:
                db.session.remove()

    threading.Thread(
        target=_run, name=f'gcal-sync-{user_id}', daemon=True,
    ).start()


def select_google_calendar(user: User, calendar_id: str) -> str:
    """Save the writable calendar the user picked, then sync known dates."""
    link = UserGoogleCalendar.query.filter_by(user_id=user.id).first()
    if not link or not link.refresh_token_enc:
        raise GoogleCalendarError('Connect a Google account first.')
    calendar_id = (calendar_id or '').strip()
    if not calendar_id:
        raise GoogleCalendarError('Choose a calendar.')
    client = load_client(link)
    match = next((c for c in client.list_calendars() if c['id'] == calendar_id), None)
    if not match:
        raise GoogleCalendarError('That calendar is not on this Google account.')
    link.calendar_id = match['id']
    link.calendar_name = match['name']
    link.updated_at = datetime.utcnow()
    db.session.commit()
    schedule_external_calendar_sync(user.id)
    return match['name']


def save_calendar_reminder(user: User, method: str, amount, unit: str) -> str:
    """Store the reminder used on every meeting, then update Google in the background."""
    from models import UserPreference

    method = (method or '').strip().lower()
    if method not in _REMINDER_METHODS:
        raise GoogleCalendarError('Choose popup, email, or none.')
    minutes = combine_reminder_minutes(amount, unit)
    prefs = UserPreference.query.filter_by(user_id=user.id).first()
    if not prefs:
        prefs = UserPreference(user_id=user.id)
        db.session.add(prefs)
    prefs.calendar_reminder_method = method
    prefs.calendar_reminder_minutes = minutes
    prefs.updated_at = datetime.utcnow()
    db.session.commit()
    link = UserGoogleCalendar.query.filter_by(user_id=user.id).first()
    if link and link.calendar_id and link.refresh_token_enc:
        schedule_external_calendar_sync(user.id)
    return reminder_label(method, minutes)


def calendar_settings(user: User) -> dict:
    """Preferences / Android payload for the connected account and calendars."""
    link = UserGoogleCalendar.query.filter_by(user_id=user.id).first()
    connected = bool(link and link.refresh_token_enc)
    calendars: list[dict] = []
    error = None
    if connected:
        try:
            calendars = load_client(link).list_calendars()
        except GoogleCalendarError as exc:
            error = str(exc)
        except Exception:
            logger.exception('Could not list Google calendars for user %s', user.id)
            error = 'Could not load calendars from Google.'
    method, minutes = meeting_reminder(user)
    amount, unit = split_reminder_minutes(minutes)
    return {
        'configured': google_configured(),
        'connected': connected,
        'email': link.account_email if link else None,
        'calendar_id': link.calendar_id if link else None,
        'calendar_name': link.calendar_name if link else None,
        'calendars': calendars,
        'error': error,
        'reminder_method': method,
        'reminder_minutes': minutes,
        'reminder_amount': amount,
        'reminder_unit': unit,
    }
