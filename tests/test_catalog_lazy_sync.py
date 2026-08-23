"""Lazy Latest catalog sync: bootstrap, marker depth, older pages on demand."""

from datetime import datetime
from unittest.mock import patch

from models import CachedMedia, CatalogFeedSync, ReviewMarker, User, db
from services import sync_jobs


def _update_item(trakt_id: int, title: str, updated_at: str) -> dict:
    return {
        'updated_at': updated_at,
        'movie': {
            'title': title,
            'year': 2026,
            'ids': {'trakt': trakt_id},
        },
    }


def test_bootstrap_initial_fetches_newest_pages_only(app):
    """Initial bootstrap takes newest N pages, not the entire window at once."""
    with app.app_context():
        pages = {
            i: [_update_item(i, f'Title {i}', f'2026-07-{10+i:02d}T00:00:00.000Z')]
            for i in range(1, 11)
        }

        def fake_probe(media_type, start_date):
            return {
                'page_count': 10,
                'item_count': 1000,
                'limit': 100,
                'page1': None,
            }

        def fake_pages(media_type, start_date, from_page, to_page, page1_cache=None, extended='full'):
            out = []
            for p in range(from_page, to_page + 1):
                out.extend(pages[p])
            return out

        with patch('services.sync_jobs.trakt_client.probe_updates_pagination', side_effect=fake_probe), patch(
            'services.sync_jobs.trakt_client.fetch_updates_pages', side_effect=fake_pages
        ) as mocked_pages, patch('services.sync_jobs.enrich_media_details', return_value=0):
            count = sync_jobs.bootstrap_catalog_initial('movie')

        assert count == sync_jobs.INITIAL_BOOTSTRAP_PAGES
        mocked_pages.assert_called()
        # Newest 1 of 10 => page 10 only
        assert mocked_pages.call_args.args[2:4] == (10, 10)
        cursor = db.session.get(CatalogFeedSync, 'movie')
        assert cursor is not None
        assert cursor.oldest_fetched_page == 10
        assert cursor.newest_fetched_page == 10
        assert cursor.bootstrapped_at is not None
        assert sync_jobs.catalog_has_more_older('movie') is True


def test_reconcile_feed_cursor_reopens_lazy_older_path(app):
    """A bogus oldest=1/page_count=1 cursor is repaired so older pages can load."""
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='movie',
            trakt_id=1,
            title='Today Only',
            feed_source='trakt_db_updates',
            trakt_listed_at=datetime(2026, 8, 2, 16, 0, 0),
        ))
        db.session.add(CatalogFeedSync(
            media_type='movie',
            start_date=sync_jobs._updates_start_date(),
            page_count=1,
            oldest_fetched_page=1,
            newest_fetched_page=1,
            bootstrapped_at=datetime(2026, 8, 2, 12, 0, 0),
        ))
        db.session.commit()

        with patch(
            'services.sync_jobs.trakt_client.probe_updates_pagination',
            return_value={'page_count': 100, 'item_count': 10000, 'limit': 100, 'page1': []},
        ):
            cur = sync_jobs.reconcile_feed_cursor('movie')

        assert cur is not None
        assert cur.page_count == 100
        assert cur.oldest_fetched_page == 100
        assert sync_jobs.catalog_has_more_older('movie') is True


def test_ensure_through_marker_refreshes_inflated_page_count(app, user):
    """limit=1 leftover page_count must not skip Newest (TTL would hide it)."""
    with app.app_context():
        u = db.session.get(User, user)
        db.session.add(CachedMedia(
            media_type='movie',
            trakt_id=1,
            title='Cached',
            feed_source='trakt_db_updates',
            trakt_listed_at=datetime(2026, 8, 1, 12, 0, 0),
        ))
        db.session.add(CatalogFeedSync(
            media_type='movie',
            start_date=sync_jobs._updates_start_date(),
            page_count=137011,
            oldest_fetched_page=135985,
            newest_fetched_page=137011,
            bootstrapped_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        ))
        db.session.commit()

        with patch(
            'services.sync_jobs.trakt_client.probe_updates_pagination',
            return_value={'page_count': 1371, 'item_count': 137011, 'limit': 100, 'page1': None},
        ), patch(
            'services.sync_jobs.refresh_catalog_newest', return_value=7,
        ) as refresh:
            added = sync_jobs.ensure_catalog_through_marker('movie', u)
        assert added == 7
        refresh.assert_called_once()


def test_sync_catalog_clamps_inflated_newest_page(app):
    """limit=1 leftover newest=137011 must not be kept after a real limit=100 fetch."""
    with app.app_context():
        start = sync_jobs._updates_start_date()
        db.session.add(CatalogFeedSync(
            media_type='movie',
            start_date=start,
            page_count=137011,
            oldest_fetched_page=135985,
            newest_fetched_page=137011,
            bootstrapped_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        ))
        db.session.commit()

        with patch(
            'services.sync_jobs.trakt_client.probe_updates_pagination',
            return_value={'page_count': 1371, 'item_count': 137011, 'limit': 100, 'page1': None},
        ), patch(
            'services.sync_jobs.trakt_client.fetch_updates_pages',
            return_value=[_update_item(9, 'Newest Real', '2026-08-23T12:00:00.000Z')],
        ) as mocked_pages, patch('services.sync_jobs.enrich_media_details', return_value=0):
            sync_jobs.refresh_catalog_newest('movie')

        mocked_pages.assert_called_once()
        assert mocked_pages.call_args.args[2:4] == (1371, 1371)
        cursor = db.session.get(CatalogFeedSync, 'movie')
        assert cursor.page_count == 1371
        assert cursor.newest_fetched_page == 1371
        assert cursor.oldest_fetched_page == 1371


def test_ensure_through_marker_does_not_walk_older_pages(app, user):
    """Page load must not eagerly walk Trakt pages down to the review marker."""
    with app.app_context():
        u = db.session.get(User, user)
        db.session.add(ReviewMarker(
            user_id=u.id,
            media_type='movie',
            trakt_id=10,
            trakt_listed_at=datetime(2026, 7, 15, 12, 0, 0),
            title='Marker Movie',
        ))
        db.session.add(CachedMedia(
            media_type='movie',
            trakt_id=99,
            title='Newest Only',
            feed_source='trakt_db_updates',
            trakt_listed_at=datetime(2026, 8, 1, 12, 0, 0),
        ))
        db.session.add(CatalogFeedSync(
            media_type='movie',
            start_date=sync_jobs._updates_start_date(),
            page_count=3,
            oldest_fetched_page=3,
            newest_fetched_page=3,
            bootstrapped_at=datetime(2026, 8, 1, 0, 0, 0),
            updated_at=datetime.utcnow(),  # fresh — skip throttled refresh
        ))
        db.session.commit()

        with patch('services.sync_jobs.trakt_client.fetch_updates_pages') as mocked_pages, patch(
            'services.sync_jobs.trakt_client.probe_updates_pagination',
            return_value={'page_count': 3, 'item_count': 3, 'limit': 100, 'page1': []},
        ):
            sync_jobs.ensure_catalog_through_marker('movie', u)

        mocked_pages.assert_not_called()
        assert CachedMedia.query.filter_by(trakt_id=10, media_type='movie').first() is None
        cursor = db.session.get(CatalogFeedSync, 'movie')
        assert cursor.oldest_fetched_page == 3


def test_ensure_catalog_for_offset_fetches_one_older_page(app):
    """Lazy pagination pulls the next older Trakt page only."""
    with app.app_context():
        start = sync_jobs._updates_start_date(29)
        db.session.add(CachedMedia(
            media_type='movie',
            trakt_id=99,
            title='Newest',
            feed_source='trakt_db_updates',
            trakt_listed_at=datetime(2026, 8, 1, 12, 0, 0),
        ))
        db.session.add(CatalogFeedSync(
            media_type='movie',
            start_date=start,
            page_count=3,
            oldest_fetched_page=3,
            newest_fetched_page=3,
            bootstrapped_at=datetime(2026, 8, 1, 0, 0, 0),
        ))
        db.session.commit()

        older = [_update_item(50, 'Older Page', '2026-07-20T00:00:00.000Z')]

        with patch(
            'services.sync_jobs.trakt_client.fetch_updates_pages',
            return_value=older,
        ) as mocked:
            ok = sync_jobs.ensure_catalog_for_offset('movie', days_back=29)

        assert ok is True
        mocked.assert_called_once()
        assert mocked.call_args.args[2:4] == (2, 2)
        assert CachedMedia.query.filter_by(trakt_id=50).first() is not None
        cursor = db.session.get(CatalogFeedSync, 'movie')
        assert cursor.oldest_fetched_page == 2
        assert sync_jobs.catalog_has_more_older('movie') is True
