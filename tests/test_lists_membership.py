"""Trakt personal lists + Set lists membership API tests."""

from unittest.mock import patch

from models import UserListMembership, UserMediaState, UserPreference, db
from tests.conftest import login_client


def test_lists_membership_get_wishlist_first(app, client, user):
    """GET membership returns Wishlist first, then visible personal lists."""
    with app.app_context():
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=42, on_watchlist=True
        ))
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.hidden_list_ids_json = '["99"]'
        prefs.default_selected_list_ids_json = '["watchlist"]'
        db.session.commit()

    login_client(client, app, user)
    personal = [
        {'id': '10', 'slug': 'maybe', 'name': 'Maybe later', 'item_count': 3},
        {'id': '99', 'slug': 'ignore', 'name': 'Ignore me', 'item_count': 1},
    ]
    with patch('routes.catalog_routes.trakt_client.get_personal_lists', return_value=personal), \
         patch('routes.catalog_routes.trakt_client.list_contains_item') as contains:
        resp = client.get('/api/lists/membership/movie/42')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    ids = [row['id'] for row in data['lists']]
    assert ids[0] == 'watchlist'
    assert data['lists'][0]['selected'] is True
    assert ids == ['watchlist', '10']
    assert '99' not in ids
    assert data['defaults'] == ['watchlist']
    # Dialog open must not paginate personal lists (hangs on 2nd+ title).
    contains.assert_not_called()


def test_lists_membership_get_applies_default_selected(app, client, user):
    """Defaults pre-check lists when the title is not on any list yet."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist", "10"]'
        db.session.commit()

    login_client(client, app, user)
    personal = [
        {'id': '10', 'slug': 'a', 'name': 'List 1', 'item_count': 1},
        {'id': '20', 'slug': 'b', 'name': 'List 2', 'item_count': 1},
    ]
    with patch('routes.catalog_routes.trakt_client.get_personal_lists', return_value=personal), \
         patch('routes.catalog_routes.trakt_client.list_contains_item', return_value=False):
        resp = client.get('/api/lists/membership/movie/99')
    data = resp.get_json()
    by_id = {row['id']: row for row in data['lists']}
    assert by_id['watchlist']['selected'] is True
    assert by_id['watchlist']['on_list'] is False
    assert by_id['10']['selected'] is True
    assert by_id['20']['selected'] is False
    assert data['defaults'] == ['watchlist', '10']


def test_lists_membership_get_actual_when_already_on_list(app, client, user):
    """When already on a list, selected mirrors membership — not Auto-select defaults."""
    with app.app_context():
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=88, on_watchlist=True
        ))
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist", "10"]'
        db.session.commit()

    login_client(client, app, user)
    personal = [
        {'id': '10', 'slug': 'a', 'name': 'List 1', 'item_count': 1},
        {'id': '20', 'slug': 'b', 'name': 'List 2', 'item_count': 1},
    ]
    with patch('routes.catalog_routes.trakt_client.get_personal_lists', return_value=personal), \
         patch('routes.catalog_routes.trakt_client.list_contains_item', return_value=False):
        resp = client.get('/api/lists/membership/movie/88')
    data = resp.get_json()
    by_id = {row['id']: row for row in data['lists']}
    assert by_id['watchlist']['selected'] is True
    assert by_id['watchlist']['on_list'] is True
    assert by_id['10']['selected'] is False
    assert by_id['10']['on_list'] is False
    assert by_id['20']['selected'] is False
    assert data['defaults'] == ['watchlist', '10']


def test_lists_membership_get_actual_personal_only(app, client, user):
    """On a personal list only: defaults that are off-list stay unchecked."""
    with app.app_context():
        db.session.add(UserListMembership(
            user_id=user, list_id='20', media_type='show', trakt_id=5
        ))
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist", "10"]'
        db.session.commit()

    login_client(client, app, user)
    personal = [
        {'id': '10', 'slug': 'a', 'name': 'List 1', 'item_count': 1},
        {'id': '20', 'slug': 'b', 'name': 'List 2', 'item_count': 1},
    ]
    with patch('routes.catalog_routes.trakt_client.get_personal_lists', return_value=personal):
        resp = client.get('/api/lists/membership/show/5')
    by_id = {row['id']: row for row in resp.get_json()['lists']}
    assert by_id['watchlist']['selected'] is False
    assert by_id['10']['selected'] is False
    assert by_id['20']['selected'] is True
    assert by_id['20']['on_list'] is True


def test_lists_membership_get_wishlist_not_default_when_off(app, client, user):
    """Wishlist can stay in the menu without being auto-selected."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["10"]'
        db.session.commit()

    login_client(client, app, user)
    personal = [{'id': '10', 'slug': 'a', 'name': 'List 1', 'item_count': 1}]
    with patch('routes.catalog_routes.trakt_client.get_personal_lists', return_value=personal), \
         patch('routes.catalog_routes.trakt_client.list_contains_item', return_value=False):
        resp = client.get('/api/lists/membership/movie/5')
    by_id = {row['id']: row for row in resp.get_json()['lists']}
    assert by_id['watchlist']['selected'] is False
    assert by_id['10']['selected'] is True


def test_lists_membership_post_updates_watchlist_and_list(app, client, user):
    """POST applies watchlist + personal list add/remove diffs."""
    with app.app_context():
        db.session.add(UserMediaState(
            user_id=user, media_type='show', trakt_id=7, on_watchlist=True
        ))
        db.session.commit()

    login_client(client, app, user)
    personal = [
        {'id': '55', 'slug': 'keepers', 'name': 'Keepers', 'item_count': 2},
    ]

    with patch('routes.catalog_routes.trakt_client.get_personal_lists', return_value=personal), \
         patch('routes.catalog_routes.trakt_client.list_contains_item') as contains, \
         patch('routes.catalog_routes.trakt_client.remove_from_watchlist') as rm_wl, \
         patch('routes.catalog_routes.trakt_client.add_to_watchlist') as add_wl, \
         patch('routes.catalog_routes.trakt_client.add_to_list') as add_list, \
         patch('routes.catalog_routes.trakt_client.remove_from_list') as rm_list:
        resp = client.post(
            '/api/lists/membership/show/7',
            json={'selected': ['55']},
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['on_watchlist'] is False
    rm_wl.assert_called_once()
    add_wl.assert_not_called()
    add_list.assert_called_once()
    rm_list.assert_not_called()
    contains.assert_not_called()

    with app.app_context():
        st = UserMediaState.query.filter_by(user_id=user, media_type='show', trakt_id=7).one()
        assert st.on_watchlist is False


def test_lists_membership_post_watchlist_plus_list_no_duplicate_state(app, client, user):
    """
    Adding Wishlist + a personal list must not double-insert UserMediaState.

    set_list_membership/_upsert_state creates the row; membership POST used to
    INSERT again from a stale ``st is None`` and hit UNIQUE constraint.
    """
    login_client(client, app, user)
    personal = [{'id': '55', 'slug': 'keepers', 'name': 'Keepers', 'item_count': 1}]

    with patch('routes.catalog_routes.trakt_client.get_personal_lists', return_value=personal), \
         patch('routes.catalog_routes.trakt_client.add_to_watchlist') as add_wl, \
         patch('routes.catalog_routes.trakt_client.add_to_list') as add_list, \
         patch('routes.catalog_routes.trakt_client.remove_from_watchlist'), \
         patch('routes.catalog_routes.trakt_client.remove_from_list'), \
         patch('services.user_media_sync.note_user_media_write'):
        resp = client.post(
            '/api/lists/membership/movie/4965',
            json={'selected': ['watchlist', '55']},
        )

    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()['success'] is True
    assert resp.get_json()['on_watchlist'] is True
    add_wl.assert_called_once()
    add_list.assert_called_once()
    with app.app_context():
        rows = UserMediaState.query.filter_by(
            user_id=user, media_type='movie', trakt_id=4965,
        ).all()
        assert len(rows) == 1
        assert rows[0].on_watchlist is True


def test_lists_membership_post_errors_are_sanitized(app, client, user):
    """API failures must not return SQLAlchemy / SQL details to the client."""
    login_client(client, app, user)
    with patch('routes.catalog_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch(
             'routes.catalog_routes.trakt_client.add_to_watchlist',
             side_effect=RuntimeError('UNIQUE constraint failed: user_media_state'),
         ):
        resp = client.post(
            '/api/lists/membership/movie/1',
            json={'selected': ['watchlist']},
        )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'UNIQUE' not in data['message']
    assert 'user_media_state' not in data['message']
    assert 'Could not update lists' in data['message']


def test_lists_membership_post_empty_selected_removes_all(app, client, user):
    """Uncheck all + Save removes Wishlist and personal-list membership."""
    from models import UserListMembership

    with app.app_context():
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=9, on_watchlist=True
        ))
        db.session.add(UserListMembership(
            user_id=user, list_id='55', media_type='movie', trakt_id=9,
        ))
        db.session.commit()

    login_client(client, app, user)
    personal = [
        {'id': '55', 'slug': 'keepers', 'name': 'Keepers', 'item_count': 2},
        {'id': '66', 'slug': 'later', 'name': 'Later', 'item_count': 4},
    ]

    with patch('routes.catalog_routes.trakt_client.get_personal_lists', return_value=personal), \
         patch('routes.catalog_routes.trakt_client.list_contains_item') as contains, \
         patch('routes.catalog_routes.trakt_client.remove_from_watchlist') as rm_wl, \
         patch('routes.catalog_routes.trakt_client.add_to_watchlist') as add_wl, \
         patch('routes.catalog_routes.trakt_client.add_to_list') as add_list, \
         patch('routes.catalog_routes.trakt_client.remove_from_list') as rm_list, \
         patch('services.user_media_sync.note_user_media_write'):
        resp = client.post(
            '/api/lists/membership/movie/9',
            json={'selected': []},
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['on_watchlist'] is False
    assert data['selected'] == []
    rm_wl.assert_called_once()
    rm_list.assert_called_once()
    add_wl.assert_not_called()
    add_list.assert_not_called()
    # Clear-all must not paginate every personal list (that was the hang).
    contains.assert_not_called()

    with app.app_context():
        st = UserMediaState.query.filter_by(
            user_id=user, media_type='movie', trakt_id=9,
        ).one()
        assert st.on_watchlist is False
        left = UserListMembership.query.filter_by(
            user_id=user, media_type='movie', trakt_id=9,
        ).count()
        assert left == 0


def test_lists_membership_post_removes_watchlist_even_if_local_stale(app, client, user):
    """Unchecked Wishlist always calls Trakt remove (local cache may be wrong)."""
    login_client(client, app, user)
    personal = []

    with patch('routes.catalog_routes.trakt_client.get_personal_lists', return_value=personal), \
         patch('routes.catalog_routes.trakt_client.remove_from_watchlist') as rm_wl, \
         patch('routes.catalog_routes.trakt_client.add_to_watchlist') as add_wl:
        resp = client.post(
            '/api/lists/membership/show/3',
            json={'selected': []},
        )

    assert resp.status_code == 200
    assert resp.get_json()['on_watchlist'] is False
    rm_wl.assert_called_once()
    add_wl.assert_not_called()


def test_preferences_list_show_and_default(app, client, user):
    """Preferences stores show/hide and auto-select independently."""
    login_client(client, app, user)
    personal = [
        {'id': '10', 'slug': 'a', 'name': 'Alpha', 'item_count': 1},
        {'id': '20', 'slug': 'b', 'name': 'Beta', 'item_count': 2},
        {'id': '30', 'slug': 'c', 'name': 'Gamma', 'item_count': 0},
    ]
    with patch('routes.user_routes.trakt_client.get_personal_lists', return_value=personal):
        resp = client.post('/preferences', data={
            'lists_prefs_present': '1',
            'known_list_ids': ['10', '20', '30'],
            'show_list_ids': ['10', '20'],  # 30 hidden
            'default_list_ids': ['watchlist', '10'],  # 20 shown but not auto
            'genres': '',
            'keywords': '',
        }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        assert prefs.hidden_list_ids_json == '["30"]'
        assert prefs.default_selected_list_ids_json == '["10", "watchlist"]'
