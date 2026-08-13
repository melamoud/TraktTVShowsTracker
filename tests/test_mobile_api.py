"""Smoke tests for the Android /api/v1 JSON API."""

from datetime import datetime, timedelta

from models import MobileLoginToken, Notification, User, db
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
