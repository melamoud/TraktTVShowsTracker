"""
Backfill overview/genres and locally cached posters for catalog stubs.

Usage (from project root):
    .venv\\Scripts\\python.exe scripts\\backfill_media_details.py
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import app
from models import CachedMedia, db
from services.poster_cache import is_local_poster_url
from services.sync_jobs import enrich_media_details_for_display


def main() -> int:
    with app.app_context():
        rows = (
            CachedMedia.query
            .filter(CachedMedia.feed_source == 'trakt_db_updates')
            .order_by(CachedMedia.trakt_listed_at.desc())
            .all()
        )
        print(f'Backfilling {len(rows)} catalog rows...')
        updated = 0
        for i, row in enumerate(rows, 1):
            before = (row.overview, row.poster_url, row.genres_json)
            try:
                enrich_media_details_for_display(row)
            except Exception as exc:
                print(f'  FAIL {row.media_type}/{row.trakt_id} {row.title}: {exc}')
                continue
            after = (row.overview, row.poster_url, row.genres_json)
            ok = bool(row.overview) and is_local_poster_url(row.poster_url)
            if after != before or ok:
                updated += 1
            if i % 10 == 0 or i == len(rows):
                db.session.commit()
                print(f'  … {i}/{len(rows)} (changed/ok-ish {updated})')
        db.session.commit()
        with_local = CachedMedia.query.filter(
            CachedMedia.poster_url.like('/cache/posters/%')
        ).count()
        with_overview = CachedMedia.query.filter(
            CachedMedia.overview.isnot(None),
            CachedMedia.overview != '',
            CachedMedia.feed_source == 'trakt_db_updates',
        ).count()
        print(f'Done. local posters={with_local}, overviews={with_overview}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
