"""
One-off: remember titles already at/below each user's current review marker.

New markers record this when they are set. Markers set before that change
only have a timestamp, so a Trakt edit can still lift those titles back onto
Latest until the marker moves. Run once per environment, then delete.

Usage (from project root):
    python scripts/backfill_reviewed_titles.py
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import app
from models import CachedMedia, ReviewMarker, db
from services.dismissed_titles import record_reviewed_through


def main() -> int:
    with app.app_context():
        db.create_all()
        for marker in ReviewMarker.query.order_by(ReviewMarker.user_id).all():
            media = CachedMedia.query.filter_by(
                media_type=marker.media_type, trakt_id=marker.trakt_id,
            ).first()
            if media is None:
                print(f'user={marker.user_id} {marker.media_type}: marker title missing, skipped')
                continue
            # The marker title may have been re-listed since; use the stored marker time.
            added = record_reviewed_through(
                marker.user_id, marker.media_type, media, listed_at=marker.trakt_listed_at,
            )
            db.session.commit()
            print(
                f'user={marker.user_id} {marker.media_type}: '
                f'remembered {added} reviewed titles (marker "{marker.title}")'
            )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
