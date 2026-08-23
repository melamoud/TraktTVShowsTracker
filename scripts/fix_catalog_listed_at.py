"""
One-off: reset Latest sort keys that were stamped with theatrical dates.

Future / midnight release dates pinned unreleased titles at the top of Latest
and hid real Trakt /updates. Catalog rows should sort by raw updated_at.

Usage (from project root):
    python scripts/fix_catalog_listed_at.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import app
from models import CachedMedia, db
from services.sync_jobs import _parse_trakt_dt


def main() -> int:
    cap = datetime.utcnow() + timedelta(hours=12)
    with app.app_context():
        rows = CachedMedia.query.filter_by(feed_source='trakt_db_updates').all()
        fixed = 0
        skipped = 0
        for row in rows:
            raw = {}
            try:
                raw = json.loads(row.raw_json or '{}')
            except json.JSONDecodeError:
                pass
            updated = _parse_trakt_dt(raw.get('updated_at'))
            entity = raw.get(row.media_type) or raw
            if not updated:
                updated = _parse_trakt_dt(entity.get('updated_at'))
            if not updated or updated > cap:
                listed_from_payload = _parse_trakt_dt(raw.get('listed_at'))
                if listed_from_payload and listed_from_payload <= cap:
                    updated = listed_from_payload
            listed = row.trakt_listed_at
            needs = listed is None or listed > cap
            if (
                not needs
                and row.released_at
                and listed
                and listed.date() == row.released_at
                and listed.hour == 0
                and listed.minute == 0
                and updated
                and updated != listed
            ):
                needs = True
            if not needs:
                skipped += 1
                continue
            if not updated or updated > cap:
                # Still a future cinema date and no usable timestamp — bury it
                # so it cannot pin Latest until the next real /updates fetch.
                updated = datetime.utcnow() - timedelta(days=14)
            row.trakt_listed_at = updated
            fixed += 1
        db.session.commit()
        print(f'Fixed {fixed} catalog listed_at rows; left {skipped} unchanged.')
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
