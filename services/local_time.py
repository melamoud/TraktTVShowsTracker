"""App-local timezone for display and 'has this aired?' checks.

Naive datetimes in the DB are UTC. Date-only values (and midnight-UTC
datetimes, which Trakt uses as calendar days) stay on that calendar date so a
Netflix drop labeled 2026-08-20 does not shift to the 19th in Eastern.

Timed UTC stamps (HBO 01:00Z) convert to Admin → Scheduler timezone
(default America/New_York).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from flask import current_app, has_app_context, has_request_context

DEFAULT_TZ = 'America/New_York'


def app_zone() -> ZoneInfo:
    """IANA zone from scheduler config, else ALERTS_TIMEZONE, else New York."""
    if has_request_context():
        from flask import g
        cached = getattr(g, '_trakttv_zone', None)
        if cached is not None:
            return cached
    name = DEFAULT_TZ
    if has_app_context():
        name = current_app.config.get('ALERTS_TIMEZONE') or DEFAULT_TZ
        try:
            from models import SchedulerConfig
            row = SchedulerConfig.query.order_by(SchedulerConfig.id).first()
            if row and getattr(row, 'media_alerts_timezone', None):
                name = (row.media_alerts_timezone or name).strip() or name
        except Exception:
            pass
    try:
        zone = ZoneInfo(name)
    except Exception:
        zone = ZoneInfo(DEFAULT_TZ)
    if has_request_context():
        from flask import g
        g._trakttv_zone = zone
    return zone


def as_utc(dt: datetime) -> datetime:
    """Treat naive datetimes as UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_local(dt: datetime) -> datetime:
    return as_utc(dt).astimezone(app_zone())


def local_now() -> datetime:
    return datetime.now(app_zone())


def local_today() -> date:
    return local_now().date()


def is_calendar_midnight(dt: datetime) -> bool:
    """True for naive midnight — Trakt's date-only / calendar-day stamp."""
    return (
        dt.tzinfo is None
        and dt.hour == 0
        and dt.minute == 0
        and dt.second == 0
        and dt.microsecond == 0
    )


def parse_trakt_datetime(value) -> datetime | None:
    """Parse a Trakt date or ISO timestamp to naive UTC (midnight = date-only)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    text = str(value).strip()
    if not text:
        return None
    try:
        if len(text) == 10 and text[4] == '-' and text[7] == '-':
            return datetime.fromisoformat(text)
        iso = text.replace('Z', '+00:00')
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        try:
            return datetime.fromisoformat(text[:10])
        except ValueError:
            return None


def local_date(value) -> date | None:
    """Calendar date in the app timezone (or the stored date for date-only values)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if is_calendar_midnight(value):
            return value.date()
        return to_local(value).date()
    if isinstance(value, date):
        return value
    return None


def format_local_date(value) -> str:
    """YYYY-MM-DD in the app timezone, or ''."""
    day = local_date(value)
    return day.isoformat() if day else ''


def has_aired_at(value, *, now: datetime | None = None) -> bool:
    """True when the air timestamp is in the past in the app timezone."""
    if value is None:
        return False
    now = now or local_now()
    if isinstance(value, datetime) and not is_calendar_midnight(value):
        return to_local(value) <= now
    day = local_date(value)
    if day is None:
        return False
    return day <= now.date()
