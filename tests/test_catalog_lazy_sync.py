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
                'item_count': 10,
                'limit': 100,
                'page1': pages[1],
            }

        def fake_pages(media_type, start_date, from_page, to_page, page1_cache=None):
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
        # Newest 3 of 10 => pages 8-10
        assert mocked_pages.call_args.args[2:4] == (8, 10)
        cursor = db.session.get(CatalogFeedSync, 'movie')
        assert cursor is not None
        assert cursor.oldest_fetched_page == 8
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


def test_ensure_through_marker_walks_older_pages(app, user):
    """With a marker not yet cached, sync walks from newest toward older pages."""
    with app.app_context():
        u = db.session.get(User, user)
        db.session.add(ReviewMarker(
            user_id=u.id,
            media_type='movie',
            trakt_id=10,
            trakt_listed_at=datetime(2026, 7, 15, 12, 0, 0),
            title='Marker Movie',
        ))
        # Newest edge already cached (two dates so oldest-window seed does not short-circuit).
        db.session.add_all([
            CachedMedia(
                media_type='movie',
                trakt_id=99,
                title='Newest Only',
                feed_source='trakt_db_updates',
                trakt_listed_at=datetime(2026, 8, 1, 12, 0, 0),
            ),
            CachedMedia(
                media_type='movie',
                trakt_id=98,
                title='Also Recent',
                feed_source='trakt_db_updates',
                trakt_listed_at=datetime(2026, 7, 31, 12, 0, 0),
            ),
        ])
        db.session.add(CatalogFeedSync(
            media_type='movie',
            start_date=sync_jobs._updates_start_date(),
            page_count=3,
            oldest_fetched_page=3,
            newest_fetched_page=3,
            bootstrapped_at=datetime(2026, 8, 1, 0, 0, 0),
        ))
        db.session.commit()

        page2 = [_update_item(10, 'Marker Movie', '2026-07-15T12:00:00.000Z')]
        page1 = [_update_item(1, 'Oldest', '2026-07-10T00:00:00.000Z')]

        def fake_probe(media_type, start_date):
            return {'page_count': 3, 'item_count': 3, 'limit': 100, 'page1': page1}

        def fake_pages(media_type, start_date, from_page, to_page, page1_cache=None):
            mapping = {1: page1, 2: page2, 3: [_update_item(99, 'Newest Only', '2026-08-01T12:00:00.000Z')]}
            out = []
            for p in range(from_page, to_page + 1):
                out.extend(mapping[p])
            return out

        with patch('services.sync_jobs.trakt_client.probe_updates_pagination', side_effect=fake_probe), patch(
            'services.sync_jobs.trakt_client.fetch_updates_pages', side_effect=fake_pages
        ), patch('services.sync_jobs.enrich_media_details', return_value=0):
            sync_jobs.ensure_catalog_through_marker('movie', u)

        assert CachedMedia.query.filter_by(trakt_id=10, media_type='movie').first() is not None
        cursor = db.session.get(CatalogFeedSync, 'movie')
        assert cursor.oldest_fetched_page <= 2


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
