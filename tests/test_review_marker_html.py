"""Review marker classes in rendered Latest HTML include the clicked row."""

from datetime import datetime
from unittest.mock import patch

from flask_login import login_user

from models import CachedMedia, ReviewMarker, User, UserMediaState, db
from routes.catalog_routes import _latest_visible_rows
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
        resp = client.get('/latest/movies?hide_watched=0&per_page=50&show_reviewed=1')
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
        resp = client.get('/latest/movies?hide_watched=0&per_page=10&show_reviewed=1')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    # Movie 15 is at index 10 (0-based) in the descending listed_at order, so page 2.
    assert 'class="pill marker-page"' in html
    assert 'href="?page=2' in html


def _feed_movie(trakt_id, title, listed_at):
    return CachedMedia(
        media_type='movie', trakt_id=trakt_id, title=title,
        trakt_listed_at=listed_at, feed_source='trakt_db_updates', overview='x',
    )


def test_latest_cutoff_keeps_newer_rows_and_other_filters(app, client, user):
    """Default Latest loads trakt_listed_at >= marker, then Python drops ties under it.

    Show reviewed still includes older titles. Hide watched still applies
    to the rows that remain.
    """
    ts = datetime(2026, 8, 2, 12, 0, 0)
    with app.app_context():
        # Insert order assigns ids. Higher id sorts above on a timestamp tie.
        db.session.add_all([
            _feed_movie(1, 'Same Time Below', ts),
            _feed_movie(2, 'Clicked Marker', ts),
            _feed_movie(3, 'Same Time Above', ts),
            _feed_movie(4, 'Newer', datetime(2026, 8, 2, 13, 0, 0)),
            _feed_movie(5, 'Older Than Marker', datetime(2026, 8, 2, 11, 0, 0)),
            _feed_movie(6, 'Watched Newer', datetime(2026, 8, 2, 14, 0, 0)),
        ])
        db.session.add(ReviewMarker(
            user_id=user, media_type='movie', trakt_id=2,
            trakt_listed_at=ts, title='Clicked Marker',
        ))
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=6, watched=True,
        ))
        db.session.commit()

    login_client(client, app, user)
    with app.test_request_context('/latest/movies'):
        login_user(db.session.get(User, user))
        hidden, hidden_stats = _latest_visible_rows(
            'movie', hide_watched=True, match_only=False, hide_lists=False,
            include_reviewed=False,
        )
        shown, _stats = _latest_visible_rows(
            'movie', hide_watched=False, match_only=False, hide_lists=False,
            include_reviewed=True,
        )
    # Older Than Marker is excluded in SQL, so it is not part of the loaded set.
    assert hidden_stats['after_year'] == 5
    hidden_titles = {r['media'].title for r in hidden if not r['older_than_marker']}
    shown_titles = {r['media'].title for r in shown}
    assert hidden_titles == {'Newer', 'Same Time Above'}
    flagged = {r['media'].title for r in hidden if r['older_than_marker']}
    assert flagged == {'Clicked Marker', 'Same Time Below'}
    assert 'Older Than Marker' in shown_titles
    assert 'Same Time Below' in shown_titles
    assert 'Clicked Marker' in shown_titles
    assert 'Watched Newer' in shown_titles

    with patch('routes.catalog_routes.ensure_catalog_through_marker'), patch(
        'routes.catalog_routes.catalog_has_more_older', return_value=False
    ), patch('services.sync_jobs.enrich_media_list_for_display'):
        page = client.get('/latest/movies?hide_watched=0').get_data(as_text=True)
        reviewed = client.get(
            '/latest/movies?hide_watched=0&show_reviewed=1',
        ).get_data(as_text=True)
    assert 'data-title="Older Than Marker"' not in page
    assert 'data-title="Same Time Below"' not in page
    assert 'data-title="Clicked Marker"' not in page
    assert 'data-title="Newer"' in page
    assert 'data-title="Same Time Above"' in page
    assert 'data-title="Older Than Marker"' in reviewed
