"""
My Calendar: cached Trakt /calendars/my entries (episode air dates, movie
releases) filtered to the user's current My movies/shows selection.
"""

from __future__ import annotations

import calendar as _cal
import logging
from datetime import date, datetime, timedelta

from models import UserCalendarEvent, db
from services import trakt_client
from services.sync_jobs import upsert_cached_media
from services.trakt_cache import (
    calendar_window_covers,
    cache_http_span,
    log_cache_event,
    note_calendar_window,
)

logger = logging.getLogger('app')

# Trakt allows up to 33 days per calendar call.
_CAL_CHUNK_DAYS = 33

_HAS_DASH_STRFTIME = None


def parse_calendar_day(value) -> date | None:
    """Parse a YYYY-MM-DD-ish value from Trakt calendar payloads."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _fmt(day: date, fmt: str) -> str:
    """strftime that falls back on Windows (no %-d support)."""
    global _HAS_DASH_STRFTIME
    if _HAS_DASH_STRFTIME is None:
        try:
            datetime(2020, 1, 5).strftime('%-d')
            _HAS_DASH_STRFTIME = True
        except ValueError:
            _HAS_DASH_STRFTIME = False
    if not _HAS_DASH_STRFTIME:
        fmt = fmt.replace('%-d', '%d')
    return day.strftime(fmt)


def week_bounds(day: date) -> tuple[date, date]:
    """Monday-Sunday week containing ``day``."""
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)


def month_bounds(day: date) -> tuple[date, date]:
    start = day.replace(day=1)
    end = start.replace(day=_cal.monthrange(start.year, start.month)[1])
    return start, end


def period_bounds(period: str, day: date) -> tuple[date, date]:
    if period == 'daily':
        return day, day
    if period == 'monthly':
        return month_bounds(day)
    return week_bounds(day)


def _display_bounds(period: str, day: date) -> tuple[date, date]:
    """Grid bounds (weeks padded to full weeks for the month view)."""
    if period == 'monthly':
        m_start, m_end = month_bounds(day)
        grid_start, _ = week_bounds(m_start)
        _, grid_end = week_bounds(m_end)
        return grid_start, grid_end
    return period_bounds(period, day)


def ensure_user_calendar_fresh(
    user,
    start: date,
    days: int,
    *,
    max_age_hours: int | None = None,
    media_types: tuple[str, ...] = ('movie', 'show'),
    raise_on_rate_limit: bool = False,
) -> bool:
    """
    Cache /calendars/my for [start, start+days) into UserCalendarEvent.

    Returns True when a fetch ran. Skips Trakt when a still-fresh fetch already
    covers this window (shared by My calendar views and the alerts job).
    ``max_age_hours`` is accepted for callers; the admin Trakt read-cache TTL
    is the source of truth.
    """
    end = start + timedelta(days=days - 1)
    if calendar_window_covers(user, start, end):
        log_cache_event('calendar', 'hit', user=user, calls=0)
        return False
    span = cache_http_span()
    try:
        if days <= _CAL_CHUNK_DAYS:
            chunks = [(start, days)]
        else:
            chunks = []
            cur = start
            remaining = days
            while remaining > 0:
                step = min(remaining, _CAL_CHUNK_DAYS)
                chunks.append((cur, step))
                cur += timedelta(days=step)
                remaining -= step

        entries: list[tuple[str, dict]] = []
        for media_type in media_types:
            for chunk_start, chunk_days in chunks:
                payload = trakt_client.get_calendar_entries(
                    user, media_type, chunk_start.isoformat(), chunk_days,
                )
                for entry in payload or []:
                    entries.append((media_type, entry))
    except Exception as exc:
        logger.warning('Calendar sync failed for user %s: %s', user.id, exc)
        log_cache_event('calendar', 'error', user=user, reason='fetch', calls=span())
        if raise_on_rate_limit and getattr(exc, 'status_code', None) == 429:
            raise
        return False

    for media_type in media_types:
        UserCalendarEvent.query.filter(
            UserCalendarEvent.user_id == user.id,
            UserCalendarEvent.media_type == media_type,
            UserCalendarEvent.event_date >= start,
            UserCalendarEvent.event_date <= end,
        ).delete(synchronize_session=False)

    for media_type, entry in entries:
        if media_type == 'show':
            air_day = parse_calendar_day(entry.get('first_aired'))
            entity = entry.get('show') or {}
            episode = entry.get('episode') or {}
            season_no = episode.get('season')
            episode_no = episode.get('number')
            episode_title = episode.get('title')
        else:
            air_day = parse_calendar_day(entry.get('released'))
            entity = entry.get('movie') or {}
            season_no = None
            episode_no = None
            episode_title = None
        tid = (entity.get('ids') or {}).get('trakt')
        if not air_day or not tid:
            continue
        tid = int(tid)
        if not (start <= air_day <= end):
            continue
        existing = UserCalendarEvent.query.filter_by(
            user_id=user.id,
            media_type=media_type,
            trakt_id=tid,
            event_date=air_day,
            season_number=season_no,
            episode_number=episode_no,
        ).first()
        if existing:
            existing.episode_title = episode_title or existing.episode_title
            existing.updated_at = datetime.utcnow()
        else:
            db.session.add(UserCalendarEvent(
                user_id=user.id,
                media_type=media_type,
                trakt_id=tid,
                event_date=air_day,
                season_number=season_no,
                episode_number=episode_no,
                episode_title=episode_title,
            ))
        upsert_cached_media(media_type, entry)

    note_calendar_window(user, start, end)
    db.session.commit()
    log_cache_event('calendar', 'fetch', user=user, reason='stale', calls=span())
    return True


def build_calendar_view(
    user_id: int,
    media_type: str,
    period: str,
    anchor: date,
    allowed_trakt_ids: set[int],
) -> dict:
    """
    Build the template structure for the calendar grid from cached events.

    Returns dict with period, anchor, range label, prev/next anchors, today,
    and ``days`` = [{'date', 'in_month', 'is_today', 'events': [...]}].
    Events link to the title detail page via media_type + trakt_id.
    """
    start, end = period_bounds(period, anchor)
    grid_start, grid_end = _display_bounds(period, anchor)

    events_by_day: dict[date, list] = {}
    if allowed_trakt_ids:
        rows = (
            UserCalendarEvent.query
            .filter(
                UserCalendarEvent.user_id == user_id,
                UserCalendarEvent.media_type == media_type,
                UserCalendarEvent.event_date >= grid_start,
                UserCalendarEvent.event_date <= grid_end,
                UserCalendarEvent.trakt_id.in_(allowed_trakt_ids),
            )
            .order_by(UserCalendarEvent.event_date, UserCalendarEvent.id)
            .all()
        )
        from models import CachedMedia
        media_map = {
            m.trakt_id: m
            for m in CachedMedia.query.filter(
                CachedMedia.media_type == media_type,
                CachedMedia.trakt_id.in_([r.trakt_id for r in rows] or [-1]),
            ).all()
        }
        for row in rows:
            media = media_map.get(row.trakt_id)
            label = None
            if media_type == 'show' and row.season_number is not None and row.episode_number is not None:
                label = f'S{row.season_number:02d}E{row.episode_number:02d}'
                if row.episode_title:
                    label = f'{label} · {row.episode_title}'
            events_by_day.setdefault(row.event_date, []).append({
                'trakt_id': row.trakt_id,
                'media_type': media_type,
                'title': media.title if media else f'Trakt #{row.trakt_id}',
                'poster_url': media.poster_url if media else None,
                'label': label,
            })

    days_out = []
    cur = grid_start
    today = date.today()
    month_starts = set()
    while cur <= grid_end:
        days_out.append({
            'date': cur,
            'in_month': period != 'monthly' or cur.month == anchor.month,
            'is_today': cur == today,
            'events': events_by_day.get(cur, []),
        })
        month_starts.add((cur.year, cur.month))
        cur += timedelta(days=1)
    month_starts.discard((anchor.year, anchor.month))

    if period == 'daily':
        label = _fmt(anchor, '%A, %B %-d, %Y')
        prev_anchor = anchor - timedelta(days=1)
        next_anchor = anchor + timedelta(days=1)
    elif period == 'monthly':
        label = anchor.strftime('%B %Y')
        prev_anchor = (anchor.replace(day=1) - timedelta(days=1)).replace(day=1)
        nm = anchor.replace(day=28) + timedelta(days=7)
        next_anchor = nm.replace(day=1)
    else:
        label = f'{_fmt(start, "%b %-d")} – {_fmt(end, "%b %-d, %Y")}'
        prev_anchor = anchor - timedelta(days=7)
        next_anchor = anchor + timedelta(days=7)

    # Non-anchor months visible in a padded monthly grid (e.g. spillover weeks).
    extra_months = [
        date(y, m, 1).strftime('%B %Y')
        for (y, m) in sorted(month_starts)
    ]

    return {
        'period': period,
        'anchor': anchor,
        'label': label,
        'prev_anchor': prev_anchor,
        'next_anchor': next_anchor,
        'today': today,
        'days': days_out,
        'weekdays': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
        'extra_months': extra_months,
    }
