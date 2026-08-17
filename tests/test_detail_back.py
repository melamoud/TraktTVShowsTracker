"""Title-page ← Back returns to Search / My / Recs / Alerts, not always Latest."""

from unittest.mock import patch

from models import CachedMedia, db
from routes.catalog_routes import safe_internal_back
from tests.conftest import login_client


def _seed_movie(app, trakt_id=100, title='Back Test'):
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='movie', trakt_id=trakt_id, title=title, year=2024,
        ))
        db.session.commit()


def _get_detail(client, path, **kwargs):
    with patch('services.sync_jobs.enrich_media_details_for_display'), \
         patch('routes.catalog_routes.sync_providers_for_media'):
        return client.get(path, **kwargs)


def test_safe_internal_back_allows_listings_only(app):
    with app.test_request_context('/catalog/movie/1', base_url='http://localhost'):
        assert safe_internal_back('/search?q=silo') == '/search?q=silo'
        assert safe_internal_back('http://localhost/search?q=silo') == '/search?q=silo'
        assert safe_internal_back('/my/shows?filter=lists') == '/my/shows?filter=lists'
        assert safe_internal_back('/notifications?hide_read=1') == '/notifications?hide_read=1'
        assert safe_internal_back('https://evil.example/search') is None
        assert safe_internal_back('//evil.example/search') is None
        assert safe_internal_back('/catalog/movie/2') is None
        assert safe_internal_back('/api/v1/search') is None


def test_detail_back_defaults_to_latest(app, client, user):
    _seed_movie(app)
    login_client(client, app, user)
    resp = _get_detail(client, '/catalog/movie/100')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert '<p><a href="/latest/movies">← Back</a></p>' in html


def test_detail_back_uses_next_from_search(app, client, user):
    _seed_movie(app)
    login_client(client, app, user)
    resp = _get_detail(client, '/catalog/movie/100', query_string={'next': '/search?q=silo'})
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert '<p><a href="/search?q=silo">← Back</a></p>' in html


def test_detail_back_uses_referrer_when_next_missing(app, client, user):
    _seed_movie(app)
    login_client(client, app, user)
    resp = _get_detail(
        client,
        '/catalog/movie/100',
        headers={'Referer': 'http://localhost/search?q=dune'},
    )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert '<p><a href="/search?q=dune">← Back</a></p>' in html


def test_detail_back_rejects_external_next(app, client, user):
    _seed_movie(app)
    login_client(client, app, user)
    resp = _get_detail(client, '/catalog/movie/100?next=https://evil.example/phish')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'evil.example' not in html
    assert '<p><a href="/latest/movies">← Back</a></p>' in html
