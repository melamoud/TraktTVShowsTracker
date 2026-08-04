"""My movies/shows multi-list filter tests."""

from unittest.mock import patch

from models import UserListMembership, UserMediaState, UserPreference, db
from tests.conftest import login_client


def _seed_state(user_id, *, media_type='movie', trakt_id=1, on_watchlist=False, watched=False):
    db.session.add(UserMediaState(
        user_id=user_id,
        media_type=media_type,
        trakt_id=trakt_id,
        on_watchlist=on_watchlist,
        watched=watched,
    ))


def test_my_movies_defaults_to_auto_selected_lists(app, client, user):
    """Without lists_set, My movies uses Preferences auto-select defaults."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist", "10"]'
        prefs.hidden_list_ids_json = '["99"]'
        _seed_state(user, trakt_id=1, on_watchlist=True)
        _seed_state(user, trakt_id=2, on_watchlist=False)
        db.session.add(UserListMembership(
            user_id=user, list_id='10', media_type='movie', trakt_id=2
        ))
        db.session.add(UserListMembership(
            user_id=user, list_id='99', media_type='movie', trakt_id=3
        ))
        _seed_state(user, trakt_id=3, on_watchlist=False)
        db.session.commit()

    login_client(client, app, user)
    personal = [
        {'id': '10', 'slug': 'a', 'name': 'List 1', 'item_count': 1},
        {'id': '99', 'slug': 'h', 'name': 'Hidden', 'item_count': 1},
    ]
    with patch('routes.user_routes.sync_user_media_state'), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=personal), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get('/my/movies')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'List 1' in html
    assert 'Hidden' not in html
    # Default filter includes watchlist (1) and list 10 (2), not hidden list title 3.
    assert 'data-trakt-id="1"' in html
    assert 'data-trakt-id="2"' in html
    assert 'data-trakt-id="3"' not in html


def test_my_movies_lists_set_overrides_defaults(app, client, user):
    """lists_set=1 uses explicit multi-select, not Preferences defaults."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        _seed_state(user, trakt_id=1, on_watchlist=True)
        _seed_state(user, trakt_id=2, on_watchlist=False)
        db.session.add(UserListMembership(
            user_id=user, list_id='10', media_type='movie', trakt_id=2
        ))
        db.session.commit()

    login_client(client, app, user)
    personal = [{'id': '10', 'slug': 'a', 'name': 'List 1', 'item_count': 1}]
    with patch('routes.user_routes.sync_user_media_state'), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=personal), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get('/my/movies?lists_set=1&lists=10&filter=lists')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'data-trakt-id="2"' in html
    assert 'data-trakt-id="1"' not in html


def test_my_movies_pages_current_slice_only(app, client, user):
    """My movies loads only the requested page of results."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        for tid in range(1, 26):
            _seed_state(user, trakt_id=tid, on_watchlist=True)
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.sync_user_media_state'), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached') as ensure, \
         patch('routes.user_routes.enrich_media_list_for_display') as enrich:
        resp = client.get('/my/movies?lists_set=1&lists=watchlist&filter=lists&per_page=10&page=2')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'page 2/3' in html
    assert html.count('class="media-row"') == 10
    # Enrichment only asked for the current page ids.
    ensured_ids = ensure.call_args.args[1]
    assert len(ensured_ids) == 10
    enrich.assert_called_once()
    assert len(enrich.call_args.args[0]) <= 10
