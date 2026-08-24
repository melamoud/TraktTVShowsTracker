"""
One-off: clear show premiere dates that were overwritten with a later episode.

Theater / Upcoming chips and Public release use CachedMedia.released_at.
A calendar/list upsert used to stamp the episode air day on the show row
(e.g. Outer Banks 2020 → 2026-08-20). Show premieres never move later in
upsert now; this heals rows that already drifted.

If raw_json still has an earlier show.first_aired / released, restore that.
Otherwise set released_at to NULL so the next summary fetch can refill it.

Usage (from project root):
    python scripts/fix_show_released_at.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import app
from models import CachedMedia, db
from services.local_time import local_date, parse_trakt_datetime


def _premiere_from_raw(raw_json: str | None) -> date | None:
    try:
        raw = json.loads(raw_json or '{}')
    except json.JSONDecodeError:
        return None
    entity = raw.get('show') or raw
    value = entity.get('released') or entity.get('first_aired')
    parsed = parse_trakt_datetime(value)
    return local_date(parsed) if parsed is not None else None


def _year_mismatch(row: CachedMedia) -> bool:
    if row.released_at is None or row.year is None:
        return False
    try:
        year_i = int(row.year)
    except (TypeError, ValueError):
        return False
    return row.released_at.year > year_i + 1


def main() -> int:
    with app.app_context():
        rows = CachedMedia.query.filter_by(media_type='show').all()
        fixed = 0
        skipped = 0
        for row in rows:
            if not _year_mismatch(row):
                skipped += 1
                continue
            old = row.released_at
            restored = _premiere_from_raw(row.raw_json)
            if restored is not None and restored.year <= int(row.year) + 1:
                row.released_at = restored
                print(f'{row.title} ({row.trakt_id}): {old} -> {restored}')
            else:
                row.released_at = None
                print(f'{row.title} ({row.trakt_id}): {old} -> NULL')
            fixed += 1
        db.session.commit()
        print(f'Healed {fixed} show released_at rows; left {skipped} unchanged.')
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
