"""App-local timezone helpers for air dates."""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from services.local_time import format_local_date, has_aired_at, local_date


def test_midnight_utc_stays_calendar_day(app):
    with app.app_context():
        dt = datetime(2026, 8, 20, 0, 0, 0)
        assert local_date(dt) == date(2026, 8, 20)
        assert format_local_date(dt) == '2026-08-20'


def test_hbo_utc_converts_to_eastern_evening(app):
    """2026-08-24 01:00Z is 2026-08-23 21:00 America/New_York."""
    with app.app_context():
        dt = datetime(2026, 8, 24, 1, 0, 0, tzinfo=timezone.utc)
        naive = dt.replace(tzinfo=None)
        assert local_date(naive) == date(2026, 8, 23)
        assert format_local_date(naive) == '2026-08-23'


def test_has_aired_uses_local_clock(app):
    with app.app_context():
        future = datetime(2030, 1, 1, 1, 0, 0)
        past = datetime(2020, 1, 1, 1, 0, 0)
        now = datetime(2026, 8, 23, 22, 0, 0, tzinfo=ZoneInfo('America/New_York'))
        assert has_aired_at(past, now=now) is True
        assert has_aired_at(future, now=now) is False
        e2 = datetime(2026, 8, 24, 1, 0, 0)  # 9pm ET Aug 23
        assert has_aired_at(e2, now=now) is True
        before = datetime(2026, 8, 23, 20, 0, 0, tzinfo=ZoneInfo('America/New_York'))
        assert has_aired_at(e2, now=before) is False


def test_parse_trakt_datetime_midnight_vs_timed(app):
    from services.local_time import parse_trakt_datetime

    with app.app_context():
        midnight = parse_trakt_datetime('2026-08-20T00:00:00.000Z')
        assert midnight == datetime(2026, 8, 20, 0, 0, 0)
        timed = parse_trakt_datetime('2026-08-24T01:00:00.000Z')
        assert timed == datetime(2026, 8, 24, 1, 0, 0)



def test_progress_air_label_uses_local_date_not_utc(app):
    from routes.user_routes import _episode_air_info

    with app.app_context():
        info = _episode_air_info(
            {'first_aired': '2026-08-24T01:00:00.000Z'},
            progress_says_aired=True,
        )
        assert '2026-08-23' in info['air_label']
        assert '2026-08-24' not in info['air_label']
