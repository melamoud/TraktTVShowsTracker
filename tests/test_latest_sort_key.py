import json
from datetime import datetime, timedelta, timezone

import pytest

from models import CachedMedia, db
from services.sync_jobs import _upsert_update_items, upsert_cached_media


def _dt(days_offset=0):
    return (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=days_offset)).replace(microsecond=0)


def test_upsert_update_overrides_stale_release_date(app, user):
    """Catalog /updates must always use updated_at, not an old future release date."""
    with app.app_context():
        future_release = _dt(14)
        updated_at = _dt(-1)

        # Simulate title first cached from a feed that set listed_at to release date.
        upsert_cached_media(
            'movie',
            {
                'title': 'Future Release',
                'year': 2026,
                'ids': {'trakt': 1001},
                'released': future_release.date().isoformat(),
                'updated_at': None,
            },
            listed_at=None,
            feed_source='release_calendar',
        )
        row = CachedMedia.query.filter_by(trakt_id=1001, media_type='movie').first()
        assert row.trakt_listed_at.date() == future_release.date()

        # Now the same title comes through /updates with a stale updated_at.
        _upsert_update_items(
            'movie',
            [
                {
                    'title': 'Future Release',
                    'year': 2026,
                    'ids': {'trakt': 1001},
                    'released': future_release.date().isoformat(),
                    'updated_at': updated_at.isoformat() + 'Z',
                }
            ],
        )
        row = CachedMedia.query.filter_by(trakt_id=1001, media_type='movie').first()
        assert row.trakt_listed_at == updated_at.replace(microsecond=0)
        assert row.trakt_listed_at < future_release


def test_upsert_update_preserves_updated_at_on_repeated_sync(app, user):
    """A later catalog update with an older updated_at should still be respected."""
    with app.app_context():
        first = _dt(-1)
        second = _dt(-3)
        _upsert_update_items(
            'movie',
            [
                {
                    'title': 'Updated Movie',
                    'year': 2026,
                    'ids': {'trakt': 1002},
                    'updated_at': first.isoformat() + 'Z',
                }
            ],
        )
        row = CachedMedia.query.filter_by(trakt_id=1002, media_type='movie').first()
        assert row.trakt_listed_at == first.replace(microsecond=0)

        # A second sync that returns an older update time (e.g. window overlap).
        _upsert_update_items(
            'movie',
            [
                {
                    'title': 'Updated Movie',
                    'year': 2026,
                    'ids': {'trakt': 1002},
                    'updated_at': second.isoformat() + 'Z',
                }
            ],
        )
        row = CachedMedia.query.filter_by(trakt_id=1002, media_type='movie').first()
        assert row.trakt_listed_at == second.replace(microsecond=0)


def test_catalog_listed_at_not_bumped_by_future_release(app, user):
    """Watchlist/summary upserts must not pin Latest with a theatrical date."""
    with app.app_context():
        updated_at = _dt(-1)
        future_release = _dt(90)
        _upsert_update_items(
            'movie',
            [
                {
                    'updated_at': updated_at.isoformat() + 'Z',
                    'movie': {
                        'title': 'Doomsday',
                        'year': 2026,
                        'ids': {'trakt': 1003},
                        'released': future_release.date().isoformat(),
                    },
                }
            ],
        )
        row = CachedMedia.query.filter_by(trakt_id=1003, media_type='movie').first()
        assert row.trakt_listed_at == updated_at.replace(microsecond=0)

        upsert_cached_media(
            'movie',
            {
                'title': 'Doomsday',
                'year': 2026,
                'ids': {'trakt': 1003},
                'released': future_release.date().isoformat(),
            },
            listed_at=None,
            feed_source='trakt_db_updates',
        )
        row = CachedMedia.query.filter_by(trakt_id=1003, media_type='movie').first()
        assert row.trakt_listed_at == updated_at.replace(microsecond=0)
        assert row.released_at == future_release.date()


def test_list_upsert_does_not_rewrite_catalog_sort_or_raw(app, user):
    """Watchlist payloads must not pin Latest or wipe /updates JSON."""
    with app.app_context():
        updated_at = _dt(-2)
        _upsert_update_items(
            'movie',
            [
                {
                    'updated_at': updated_at.isoformat() + 'Z',
                    'movie': {
                        'title': 'Doomsday',
                        'year': 2026,
                        'ids': {'trakt': 1004},
                        'released': _dt(90).date().isoformat(),
                    },
                }
            ],
        )
        upsert_cached_media(
            'movie',
            {
                'type': 'movie',
                'listed_at': _dt(-1).isoformat() + 'Z',
                'rank': 1,
                'movie': {
                    'title': 'Doomsday',
                    'year': 2026,
                    'ids': {'trakt': 1004},
                    'released': _dt(90).date().isoformat(),
                },
            },
        )
        row = CachedMedia.query.filter_by(trakt_id=1004, media_type='movie').first()
        assert row.trakt_listed_at == updated_at.replace(microsecond=0)
        raw = json.loads(row.raw_json or '{}')
        assert raw.get('updated_at')
        assert 'rank' not in raw


def test_updates_page_count_converts_limit_1_probe(app):
    """Old limit=1 probes reported page_count ≈ item count; fetch uses 100/page."""
    from services.sync_jobs import _updates_page_count

    assert _updates_page_count({
        'page_count': 137011, 'item_count': 137011, 'limit': 1,
    }) == 1371
    assert _updates_page_count({
        'page_count': 100, 'item_count': 10000, 'limit': 100,
    }) == 100
