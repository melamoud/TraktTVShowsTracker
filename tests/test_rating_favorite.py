"""Trakt rating + favorites API tests."""

from unittest.mock import patch

from models import UserMediaState, db
from tests.conftest import login_client


def test_api_rating_sets_and_clears(app, client, user):
    """POST rating writes Trakt then caches 1–10 / None locally."""
    login_client(client, app, user)
    with patch('routes.catalog_routes.trakt_client.add_rating', return_value={}) as add, \
         patch('routes.catalog_routes.trakt_client.remove_rating', return_value={}) as rem:
        resp = client.post('/api/rating/movie/42', json={'rating': 8})
        assert resp.status_code == 200
        assert resp.get_json()['rating'] == 8
        add.assert_called_once()
        assert add.call_args.args[1:] == ('movie', 42, 8)

        resp = client.post('/api/rating/movie/42', json={'rating': None})
        assert resp.status_code == 200
        assert resp.get_json()['rating'] is None
        rem.assert_called_once()

    with app.app_context():
        st = UserMediaState.query.filter_by(
            user_id=user, media_type='movie', trakt_id=42,
        ).one()
        assert st.rating is None


def test_api_rating_rejects_out_of_range(app, client, user):
    """Ratings outside 1–10 are rejected without calling Trakt."""
    login_client(client, app, user)
    with patch('routes.catalog_routes.trakt_client.add_rating') as add:
        resp = client.post('/api/rating/show/7', json={'rating': 11})
    assert resp.status_code == 400
    add.assert_not_called()


def test_api_favorite_toggles(app, client, user):
    """Favorite add/remove syncs to Trakt and local flag."""
    login_client(client, app, user)
    with patch('routes.catalog_routes.trakt_client.add_to_favorites', return_value={}) as add, \
         patch('routes.catalog_routes.trakt_client.remove_from_favorites', return_value={}) as rem:
        resp = client.post('/api/favorite/movie/9', json={'action': 'add'})
        assert resp.status_code == 200
        assert resp.get_json()['favorited'] is True
        add.assert_called_once()

        resp = client.post('/api/favorite/movie/9', json={'action': 'remove'})
        assert resp.status_code == 200
        assert resp.get_json()['favorited'] is False
        rem.assert_called_once()

    with app.app_context():
        st = UserMediaState.query.filter_by(
            user_id=user, media_type='movie', trakt_id=9,
        ).one()
        assert st.favorited is False


def test_my_movies_shows_rating_and_favorite_controls(app, client, user):
    """My movies cards expose rate select + favorite button and tags."""
    with app.app_context():
        from models import UserPreference
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=3,
            on_watchlist=True, rating=9, favorited=True,
        ))
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get('/my/movies?lists_set=1&lists=watchlist&filter=lists')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Rated 9/10' in html
    assert 'class="tag favorite"' in html
    assert 'class="rate-select"' in html
    assert 'data-action="favorite-remove"' in html
