"""
One-off: put show calendar days back on the date Trakt labeled.

Opening My Shows treated every ``00:00Z`` episode time as 8pm Eastern and
moved the saved calendar day to the evening before. ``01:00Z`` (9pm) rows
were already on the right evening and are left alone.

Usage (from project root):
    python scripts/fix_calendar_midnight_shift.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import app
from models import UserCalendarEvent, UserMediaState, db


def _utc_midnight_day(value):
    """UTC calendar date when the stamp is exactly 00:00:00Z, else None."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text.endswith('Z'):
        return None
    try:
        dt = datetime.fromisoformat(text[:-1] + '+00:00').astimezone(timezone.utc)
    except ValueError:
        return None
    if dt.hour or dt.minute or dt.second or dt.microsecond:
        return None
    return dt.date()


def _labeled_days():
    """(user_id, trakt_id, season, episode) -> UTC date for midnight-Z air times."""
    found = {}
    rows = UserMediaState.query.filter(
        UserMediaState.media_type == 'show',
        UserMediaState.progress_payload_json.isnot(None),
    ).all()
    for row in rows:
        try:
            data = json.loads(row.progress_payload_json or '')
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        for season in data.get('seasons_meta') or []:
            number = season.get('number')
            if number is None:
                continue
            for ep in season.get('episodes') or []:
                ep_no = ep.get('number')
                day = _utc_midnight_day(ep.get('first_aired') or ep.get('released'))
                if ep_no is None or day is None:
                    continue
                found[(int(row.user_id), int(row.trakt_id), int(number), int(ep_no))] = day
    return found


def main():
    with app.app_context():
        labeled = _labeled_days()
        events = UserCalendarEvent.query.filter_by(media_type='show').all()
        moved = 0
        skipped = 0
        for event in events:
            if event.season_number is None or event.episode_number is None:
                continue
            key = (
                int(event.user_id), int(event.trakt_id),
                int(event.season_number), int(event.episode_number),
            )
            day = labeled.get(key)
            if day is None or event.event_date == day:
                continue
            clash = UserCalendarEvent.query.filter_by(
                user_id=event.user_id,
                media_type='show',
                trakt_id=event.trakt_id,
                event_date=day,
                season_number=event.season_number,
                episode_number=event.episode_number,
            ).first()
            if clash is not None:
                db.session.delete(event)
                skipped += 1
                print(
                    f'drop duplicate user={event.user_id} show={event.trakt_id} '
                    f'S{event.season_number}E{event.episode_number} '
                    f'{event.event_date} (already on {day})'
                )
                continue
            print(
                f'user={event.user_id} show={event.trakt_id} '
                f'S{event.season_number}E{event.episode_number} '
                f'{event.event_date} -> {day}'
            )
            event.event_date = day
            moved += 1
        db.session.commit()
        print(f'restored {moved}, dropped {skipped} duplicate')


if __name__ == '__main__':
    main()
