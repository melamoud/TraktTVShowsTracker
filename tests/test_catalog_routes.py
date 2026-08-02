"""Catalog and review-marker API tests (Trakt mocked where needed)."""

from datetime import datetime

from models import CachedMedia, MediaFoundOn, ReviewMarker, User, db
from tests.conftest import login_client


def test_login_page_loads(client):
    """Login page is public."""
    resp = client.get('/login')
    assert resp.status_code == 200
    assert b'Login with TraktTV' in resp.data


def test_latest_movies_requires_auth(client):
    """Latest movies redirects when anonymous."""
    resp = client.get('/latest/movies', follow_redirects=False)
    assert resp.status_code in (302, 401)


def test_review_marker_api(app, client, user):
    """Setting a review marker stores one row per media type."""
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='movie',
            trakt_id=77,
            title='Marker Film',
            trakt_listed_at=datetime(2026, 1, 15),
        ))
        db.session.commit()

    login_client(client, app, user)
    resp = client.post('/api/review-marker/movie/77', json={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True

    with app.app_context():
        markers = ReviewMarker.query.filter_by(user_id=user, media_type='movie').all()
        assert len(markers) == 1
        assert markers[0].trakt_id == 77


def test_found_on_multi_replace(app, client, user):
    """Found-on API replaces the full local label set for a title."""
    login_client(client, app, user)
    resp = client.post('/api/found-on/movie/77', json={'service_labels': ['Netflix', 'toFlx']})
    assert resp.status_code == 200
    assert resp.get_json()['found_on'] == ['Netflix', 'toFlx']

    resp = client.post('/api/found-on/movie/77', json={'service_labels': ['Prime Video']})
    assert resp.status_code == 200
    with app.app_context():
        rows = MediaFoundOn.query.filter_by(user_id=user, media_type='movie', trakt_id=77).all()
        assert [r.service_label for r in rows] == ['Prime Video']


def test_help_page(app, client, user):
    """User help overview renders."""
    login_client(client, app, user)
    resp = client.get('/help/overview')
    assert resp.status_code == 200
    assert b'Getting started' in resp.data
