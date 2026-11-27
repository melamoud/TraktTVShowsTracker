"""
One-off: copy Trakt's primary country from raw_json onto cached_media.country.

Titles that never stored a country stay blank. The list filter keeps those
visible. Later summary fetches fill them.

Usage (from project root, once per environment):
    python scripts/fill_media_country.py
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import or_

from app import app
from models import CachedMedia, db
from services.countries import country_from_raw_json


def main() -> int:
    with app.app_context():
        rows = CachedMedia.query.filter(or_(
            CachedMedia.country.is_(None),
            CachedMedia.country == '',
        )).all()
        filled = 0
        for row in rows:
            code = country_from_raw_json(row.raw_json, row.media_type)
            if not code:
                continue
            row.country = code
            filled += 1
        db.session.commit()
        still = CachedMedia.query.filter(or_(
            CachedMedia.country.is_(None),
            CachedMedia.country == '',
        )).count()
        print(f'filled {filled} from stored Trakt payloads; {still} still have no country')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
