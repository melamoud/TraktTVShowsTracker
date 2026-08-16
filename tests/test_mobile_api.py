"""Smoke tests for the Android /api/v1 JSON API."""

from datetime import datetime, timedelta
from unittest.mock import patch

from models import CachedMedia, MediaFoundOn, MobileLoginToken, Notification, User, UserMediaState, db
from tests.conftest import login_client


def test_me_requires_login(client):
    resp = client.get('/api/v1/me')
    assert resp.status_code == 401
    assert resp.get_json()['success'] is False


def test_search_requires_login(client):
    resp = client.get('/api/v1/search?q=test')
    assert resp.status_code == 401


def test_auth_start_returns_authorize_url(client):
    resp = client.get('/api/v1/auth/start')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'auth/trakt' in data['authorize_url']
    assert 'client=android' in data['authorize_url']


def test_auth_complete_rejects_bad_token(client):
    resp = client.post('/api/v1/auth/complete', json={'token': 'nope'})
    assert resp.status_code == 401
    assert resp.get_json()['success'] is False


def test_auth_complete_exchanges_token(app, client, user):
    with app.app_context():
        db.session.add(MobileLoginToken(
            token='good-token',
            user_id=user,
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        ))
        db.session.commit()
    resp = client.post('/api/v1/auth/complete', json={'token': 'good-token'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['user']['username'] == 'friend'
    me = client.get('/api/v1/me')
    assert me.status_code == 200
    assert me.get_json()['user']['username'] == 'friend'


def test_my_movies_and_alerts_json(app, client, user):
    login_client(client, app, user)
    movies = client.get('/api/v1/my/movies')
    assert movies.status_code == 200
    body = movies.get_json()
    assert body['success'] is True
    assert body['media_type'] == 'movie'
    assert 'items' in body
    assert 'filter_lists' in body

    shows = client.get('/api/v1/my/shows')
    assert shows.status_code == 200
    assert shows.get_json()['media_type'] == 'show'

    alerts = client.get('/api/v1/alerts')
    assert alerts.status_code == 200
    assert alerts.get_json()['success'] is True


def test_alerts_json_includes_found_on(app, client, user):
    login_client(client, app, user)
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show', trakt_id=42, title='The Bear', year=2022,
        ))
        db.session.add(Notification(
            user_id=user,
            alert_type='episode_aired',
            title='The Bear',
            message='S03E01 — Next',
            media_type='show',
            trakt_id=42,
        ))
        db.session.add(MediaFoundOn(
            user_id=user, media_type='show', trakt_id=42, service_label='Hulu',
        ))
        db.session.add(UserMediaState(
            user_id=user, media_type='show', trakt_id=42, on_watchlist=True,
            last_episode_aired_at=datetime(2026, 8, 14),
            last_episode_label='S03E01 — Next',
        ))
        db.session.commit()
    data = client.get('/api/v1/alerts').get_json()
    assert data['success'] is True
    item = next(row for row in data['items'] if row['trakt_id'] == 42)
    assert item['found_on'] == ['Hulu']
    links = item.get('found_on_links') or []
    assert links and links[0]['label'] == 'Hulu'
    assert links[0]['url'] and 'hulu.com' in links[0]['url']
    assert item['last_episode_label'] == 'S03E01 — Next'
    assert (item.get('last_episode_aired_at') or '').startswith('2026-08-14')


def test_catalog_detail_json(app, client, user):
    """Android title page loads the same decorated row + cast as the website."""
    login_client(client, app, user)
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show', trakt_id=42, title='The Bear', year=2022,
            overview='A Chicago restaurant.', runtime=30, network='FX',
            imdb_id='tt14452776', slug='the-bear', homepage='https://fx.com/the-bear',
        ))
        db.session.add(MediaFoundOn(
            user_id=user, media_type='show', trakt_id=42, service_label='Hulu',
        ))
        db.session.commit()

    fake_cast = [{
        'trakt_id': 9, 'name': 'Jeremy Allen White', 'characters': ['Carmy'],
        'episode_count': 28, 'favorited': False, 'headshot_url': '/cache/actors/9',
    }]
    with patch('services.sync_jobs.enrich_media_details_for_display'), \
         patch('routes.catalog_routes.sync_providers_for_media'), \
         patch('services.cast_service.cast_for_detail', return_value=fake_cast):
        resp = client.get('/api/v1/catalog/show/42')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['item']['title'] == 'The Bear'
    assert data['item']['found_on'] == ['Hulu']
    assert data['homepage'] == 'https://fx.com/the-bear'
    assert data['imdb_url'] == 'https://www.imdb.com/title/tt14452776/'
    assert 'trakt.tv/shows/the-bear' in data['trakt_url']
    assert data['cast'][0]['name'] == 'Jeremy Allen White'
    assert 'found_on_choices' in data
    assert data['match']['matched'] is False

    with patch('services.trakt_client.fetch_media_summary', side_effect=RuntimeError('missing')):
        missing = client.get('/api/v1/catalog/movie/999999')
    assert missing.status_code == 404
    bad = client.get('/api/v1/catalog/book/1')
    assert bad.status_code == 400


def test_found_on_v1_updates_labels(app, client, user):
    login_client(client, app, user)
    resp = client.post(
        '/api/v1/found-on/show/42',
        json={'service_labels': ['toFlx', 'Hulu']},
    )
    assert resp.status_code == 200
    assert resp.get_json()['found_on'] == ['toFlx', 'Hulu']


def test_alerts_mark_read(app, client, user):
    login_client(client, app, user)
    with app.app_context():
        n = Notification(
            user_id=user,
            alert_type='release_day',
            title='Released',
            message='A movie is out',
            media_type='movie',
            trakt_id=9,
        )
        db.session.add(n)
        db.session.commit()
        nid = n.id
    resp = client.post(f'/api/v1/alerts/{nid}/read')
    assert resp.status_code == 200
    assert resp.get_json()['is_read'] is True
    with app.app_context():
        row = db.session.get(Notification, nid)
        assert row.is_read is True


def test_search_json_empty_query(app, client, user):
    login_client(client, app, user)
    resp = client.get('/api/v1/search')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['items'] == []
    assert 'year' in data
    assert 'genres' in data
    assert data['genre_choices']


def test_search_json_year_and_genre_filter(app, client, user):
    login_client(client, app, user)

    def fake_search(_user, media_type, query, *, limit=20):
        return [
            {
                'type': 'movie', 'score': 2,
                'movie': {
                    'title': 'Old Drama', 'year': 2010, 'genres': ['drama'],
                    'ids': {'trakt': 21},
                },
            },
            {
                'type': 'movie', 'score': 1,
                'movie': {
                    'title': 'New Drama', 'year': 2019, 'genres': ['drama'],
                    'ids': {'trakt': 23},
                },
            },
        ]

    with patch('services.user_media_sync.ensure_user_media_fresh', return_value=False), \
         patch('services.trakt_client.search_titles', side_effect=fake_search), \
         patch('services.sync_jobs.enrich_media_list_for_display', return_value=[]), \
         patch('services.sync_jobs.sync_providers_for_media', return_value=[]):
        resp = client.get(
            '/api/v1/search?q=film&type=movie&hide_watched=0&hide_lists=0'
            '&year=2015-2020&genre=drama'
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['year'] == '2015-2020'
    assert data['genres'] == ['drama']
    ids = [item['trakt_id'] for item in data['items']]
    assert 23 in ids
    assert 21 not in ids
