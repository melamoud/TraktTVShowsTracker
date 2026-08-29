"""Review marker classes in rendered Latest HTML include the clicked row."""

from datetime import datetime
from unittest.mock import patch

from models import CachedMedia, ReviewMarker, db
from tests.conftest import login_client


def test_latest_movies_dims_marker_row_in_html(app, client, user):
    """Clicked marker row and the next row both get the dimmed class."""
    with app.app_context():
        ts = datetime(2026, 8, 2, 12, 0, 0)
        db.session.add_all([
            CachedMedia(
                media_type='movie', trakt_id=501, title='Above Marker',
                trakt_listed_at=datetime(2026, 8, 2, 13, 0, 0),
                feed_source='trakt_db_updates', overview='Newer',
            ),
            CachedMedia(
                media_type='movie', trakt_id=502, title='Clicked Marker',
                trakt_listed_at=ts, feed_source='trakt_db_updates', overview='Boundary',
            ),
            CachedMedia(
                media_type='movie', trakt_id=503, title='Below Marker',
                trakt_listed_at=datetime(2026, 8, 2, 11, 0, 0),
                feed_source='trakt_db_updates', overview='Older',
            ),
            ReviewMarker(
                user_id=user, media_type='movie', trakt_id=502,
                trakt_listed_at=ts, title='Clicked Marker',
            ),
        ])
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.catalog_routes.sync_catalog'), patch(
        'routes.catalog_routes.ensure_catalog_through_marker'
    ), patch(
        'routes.catalog_routes.ensure_catalog_for_offset', return_value=False
    ), patch(
        'routes.catalog_routes.catalog_has_more_older', return_value=False
    ), patch(
        'services.sync_jobs.enrich_media_list_for_display'
    ):
        resp = client.get('/latest/movies?hide_watched=0&per_page=50')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    # Three rows, one page — pager hidden until pages > 1.
    assert 'Above Marker' in html
    assert 'Clicked Marker' in html

    parts = html.split('<article class="media-row')
    assert len(parts) >= 4  # preamble + 3 rows
    rows_html = parts[1:4]
    # Order is listed_at desc: Above, Clicked, Below
    assert 'Above Marker' in rows_html[0]
    assert 'dimmed' not in rows_html[0].split('>', 1)[0]
    assert 'Clicked Marker' in rows_html[1]
    assert 'dimmed' in rows_html[1].split('>', 1)[0]
    assert 'marker-line' in rows_html[1].split('>', 1)[0]
    assert 'Below Marker' in rows_html[2]
    assert 'dimmed' in rows_html[2].split('>', 1)[0]


def test_latest_movies_underlines_marker_page(app, client, user):
    """Pagination underlines the page containing the review marker."""
    with app.app_context():
        for i in range(1, 26):
            db.session.add(CachedMedia(
                media_type='movie', trakt_id=500 + i,
                title=f'Movie {i}',
                trakt_listed_at=datetime(2026, 8, 2, 12, 0, i),
                feed_source='trakt_db_updates', overview='x',
            ))
        db.session.add(ReviewMarker(
            user_id=user, media_type='movie', trakt_id=515,
            trakt_listed_at=datetime(2026, 8, 2, 12, 0, 15), title='Movie 15',
        ))
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.catalog_routes.feed_count', return_value=25), patch(
        'routes.catalog_routes.ensure_catalog_through_marker'
    ), patch(
        'routes.catalog_routes.ensure_catalog_for_offset', return_value=False
    ), patch(
        'routes.catalog_routes.catalog_has_more_older', return_value=False
    ), patch(
        'services.sync_jobs.enrich_media_list_for_display'
    ):
        resp = client.get('/latest/movies?hide_watched=0&per_page=10')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    # Movie 15 is at index 10 (0-based) in the descending listed_at order, so page 2.
    assert 'class="pill marker-page"' in html
    assert 'href="?page=2' in html
