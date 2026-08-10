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


def test_api_episode_rating_does_not_touch_user_media_state(app, client, user):
    """Episode ratings sync to Trakt only (no UserMediaState row)."""
    login_client(client, app, user)
    with patch('routes.catalog_routes.trakt_client.add_rating', return_value={}) as add:
        resp = client.post('/api/rating/episode/501', json={'rating': 7})
    assert resp.status_code == 200
    assert resp.get_json()['rating'] == 7
    assert add.call_args.args[1:] == ('episode', 501, 7)

    with app.app_context():
        assert UserMediaState.query.filter_by(
            user_id=user, media_type='episode', trakt_id=501,
        ).count() == 0


def test_api_comment_posts_to_trakt(app, client, user):
    """POST comment writes to Trakt and returns comment id."""
    login_client(client, app, user)
    with patch(
        'routes.catalog_routes.trakt_client.add_comment',
        return_value={'id': 88, 'review': True},
    ) as add:
        resp = client.post('/api/comment/show/12', json={
            'comment': 'Really enjoyed this season a lot',
            'spoiler': True,
        })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['comment_id'] == 88
    assert data['review'] is True
    add.assert_called_once()
    assert add.call_args.args[1:4] == ('show', 12, 'Really enjoyed this season a lot')
    assert add.call_args.kwargs.get('spoiler') is True


def test_api_comment_rejects_short_text(app, client, user):
    """Trakt 5-word minimum surfaces as a 400."""
    login_client(client, app, user)
    with patch(
        'routes.catalog_routes.trakt_client.add_comment',
        side_effect=ValueError('Comment must be at least 5 words'),
    ) as add:
        resp = client.post('/api/comment/movie/3', json={'comment': 'too short'})
    assert resp.status_code == 400
    assert '5 words' in resp.get_json()['message']
    add.assert_called_once()


def test_api_feedback_returns_rating_and_comment(app, client, user):
    """GET feedback lazy-loads Trakt rating + comment for one episode."""
    login_client(client, app, user)
    with patch(
        'routes.catalog_routes.trakt_client.get_media_feedback',
        return_value={
            'rating': 9,
            'comment_id': 55,
            'comment': 'Really enjoyed this episode a lot',
            'spoiler': False,
            'review': True,
        },
    ) as get_fb:
        resp = client.get('/api/feedback/episode/902')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['rating'] == 9
    assert data['comment_id'] == 55
    assert 'enjoyed' in data['comment']
    get_fb.assert_called_once()


def test_api_comment_updates_existing(app, client, user):
    """POST with comment_id updates instead of creating a duplicate."""
    login_client(client, app, user)
    with patch(
        'routes.catalog_routes.trakt_client.update_comment',
        return_value={'id': 55, 'review': True},
    ) as upd, patch(
        'routes.catalog_routes.trakt_client.add_comment',
    ) as add:
        resp = client.post('/api/comment/episode/902', json={
            'comment': 'Updated thoughts on this episode now',
            'spoiler': True,
            'comment_id': 55,
        })
    assert resp.status_code == 200
    assert resp.get_json()['comment_id'] == 55
    upd.assert_called_once()
    add.assert_not_called()


def test_get_media_feedback_prefers_comment_user_rating():
    """Comment user_rating avoids a second ratings scan when present."""
    from services import trakt_client

    class _User:
        id = 1

    with patch.object(
        trakt_client,
        'find_user_comment',
        return_value={
            'id': 1,
            'comment': 'five words are enough here',
            'spoiler': False,
            'review': False,
            'user_rating': 8,
        },
    ), patch.object(trakt_client, 'find_user_rating') as rating:
        out = trakt_client.get_media_feedback(_User(), 'episode', 9)
    assert out['rating'] == 8
    assert out['comment_id'] == 1
    rating.assert_not_called()


def test_add_comment_requires_five_words():
    """Client helper enforces Trakt's minimum before calling the API."""
    from services import trakt_client

    class _User:
        id = 1

    with patch.object(trakt_client, 'api_request') as api:
        try:
            trakt_client.add_comment(_User(), 'movie', 1, 'too short')
            assert False, 'expected ValueError'
        except ValueError as exc:
            assert '5 words' in str(exc)
        api.assert_not_called()


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
