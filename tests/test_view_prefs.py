"""Per-user UI view settings persistence."""

from unittest.mock import patch

from models import UserMediaState, UserPreference, db
from tests.conftest import login_client


def test_my_shows_remembers_filter_after_bare_nav(app, client, user):
    """Choosing Unwatched episodes persists for the next plain /my/shows visit."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        db.session.add(UserMediaState(
            user_id=user, media_type='show', trakt_id=1, on_watchlist=True,
        ))
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get('/my/shows?filter=unwatched_episodes&lists_set=1&lists=watchlist')
        assert resp.status_code == 200
        assert b'Unwatched episodes' in resp.data

        resp2 = client.get('/my/shows')
    assert resp2.status_code == 200
    html = resp2.get_data(as_text=True)
    # Active pill for unwatched should be on.
    assert 'filter=unwatched_episodes' in html
    assert 'pill on' in html
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        assert 'unwatched_episodes' in (prefs.ui_view_settings_json or '')


def test_my_shows_remembers_per_page(app, client, user):
    """Page size choice is stored per user and reused without query args."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        for tid in range(1, 15):
            db.session.add(UserMediaState(
                user_id=user, media_type='show', trakt_id=tid, on_watchlist=True,
            ))
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get('/my/shows?per_page=10&lists_set=1&lists=watchlist')
        assert resp.status_code == 200
        assert b'page 1/' in resp.data

        resp2 = client.get('/my/shows')
    assert resp2.status_code == 200
    html = resp2.get_data(as_text=True)
    assert 'page 1/' in html
    assert '>10</strong> of' in html or '10 / page' in html


def test_my_shows_api_keeps_saved_filter_when_omitted(app, client, user):
    """Android must omit filter= on first load or it overwrites the saved status."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        db.session.add(UserMediaState(
            user_id=user, media_type='show', trakt_id=1, on_watchlist=True,
        ))
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        saved = client.get(
            '/api/v1/my/shows?filter=unwatched_episodes&lists_set=1&lists=watchlist'
        )
        assert saved.status_code == 200
        assert saved.get_json()['filter'] == 'unwatched_episodes'

        bare = client.get('/api/v1/my/shows')
        assert bare.status_code == 200
        assert bare.get_json()['filter'] == 'unwatched_episodes'

        wiped = client.get('/api/v1/my/shows?filter=lists')
        assert wiped.get_json()['filter'] == 'lists'


def test_my_shows_remembers_avail_filter(app, client, user):
    """Availability filter is stored like status / display."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        db.session.add(UserMediaState(
            user_id=user, media_type='show', trakt_id=1, on_watchlist=True,
        ))
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get('/my/shows?avail=streaming&lists_set=1&lists=watchlist')
        assert resp.status_code == 200

        bare = client.get('/api/v1/my/shows')
    assert bare.status_code == 200
    assert bare.get_json()['avail'] == 'streaming'
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        assert '"avail": "streaming"' in (prefs.ui_view_settings_json or '') or \
            '"avail":"streaming"' in (prefs.ui_view_settings_json or '')


def test_latest_remembers_hide_watched_off(app, client, user):
    """Latest Show watched toggle persists across bare navigation."""
    login_client(client, app, user)
    empty_stats = {
        'cached_total': 0, 'after_year': 0, 'after_watched': 0, 'after_lists': 0, 'visible': 0,
    }
    with patch('routes.catalog_routes.feed_count', return_value=1), \
         patch('routes.catalog_routes.ensure_catalog_through_marker'), \
         patch('routes.catalog_routes.catalog_has_more_older', return_value=False), \
         patch('routes.catalog_routes._latest_visible_rows', return_value=([], empty_stats)), \
         patch('services.sync_jobs.enrich_media_list_for_display'):
        resp = client.get('/latest/shows?hide_watched=0&match_only=0&recent_years=1')
        assert resp.status_code == 200

        resp2 = client.get('/latest/shows')
    assert resp2.status_code == 200
    html = resp2.get_data(as_text=True)
    assert 'Showing watched' in html
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        data = prefs.ui_view_settings_json or ''
        assert 'latest_shows' in data
        assert '"hide_watched": false' in data or '"hide_watched":false' in data
