"""Personal-list tags appear on all pages that show title cards."""

from datetime import datetime
from unittest.mock import patch

from models import CachedMedia, UserListMembership, UserMediaState, db
from tests.conftest import login_client


def _seed_title(media_type, trakt_id, title, user):
    db.session.add(CachedMedia(
        media_type=media_type, trakt_id=trakt_id, title=title, year=2024,
    ))
    db.session.add(UserMediaState(
        user_id=user, media_type=media_type, trakt_id=trakt_id, on_watchlist=False,
    ))
    db.session.add(UserListMembership(
        user_id=user, list_id='10', media_type=media_type, trakt_id=trakt_id,
    ))


def test_detail_page_shows_personal_list_tags(app, client, user):
    with app.app_context():
        _seed_title('show', 159815, 'Outer Banks', user)
        db.session.commit()

    login_client(client, app, user)
    with patch('services.sync_jobs.enrich_media_details_for_display'), \
         patch('services.sync_jobs.sync_providers_for_media'), \
         patch('routes.catalog_routes.trakt_client.get_personal_lists', return_value=[
             {'id': '10', 'name': 'TV Show Favs', 'slug': 'tv-show-favs'},
         ]):
        resp = client.get('/catalog/show/159815')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'TV Show Favs' in html


def test_latest_page_shows_personal_list_tags(app, client, user):
    with app.app_context():
        m = CachedMedia.query.filter_by(media_type='movie', trakt_id=5).first()
        if not m:
            m = CachedMedia(
                media_type='movie', trakt_id=5, title='Listed Movie', year=2026,
                trakt_listed_at=datetime(2026, 8, 6), feed_source='trakt_db_updates',
            )
            db.session.add(m)
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=5, on_watchlist=False,
        ))
        db.session.add(UserListMembership(
            user_id=user, list_id='10', media_type='movie', trakt_id=5,
        ))
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.catalog_routes.feed_count', return_value=1), \
         patch('routes.catalog_routes.ensure_catalog_through_marker'), \
         patch('routes.catalog_routes.catalog_has_more_older', return_value=False), \
         patch('services.sync_jobs.enrich_media_list_for_display'), \
         patch('routes.catalog_routes.trakt_client.get_personal_lists', return_value=[
             {'id': '10', 'name': 'TV Show Favs', 'slug': 'tv-show-favs'},
         ]):
        resp = client.get('/latest/movies?hide_lists=0')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Listed Movie' in html
    assert 'TV Show Favs' in html


def test_search_page_shows_personal_list_tags(app, client, user):
    with app.app_context():
        _seed_title('show', 7, 'Listed Show', user)
        db.session.commit()

    def fake_search(_user, media_type, query, *, limit=20):
        return [
            {
                'type': 'show',
                'score': 100,
                'show': {
                    'title': 'Listed Show', 'year': 2024, 'ids': {'trakt': 7, 'slug': 'listed-show'},
                },
            },
        ]

    login_client(client, app, user)
    with patch('routes.catalog_routes.trakt_client.search_titles', side_effect=fake_search), \
         patch('services.sync_jobs.enrich_media_list_for_display'), \
         patch('routes.catalog_routes.trakt_client.get_personal_lists', return_value=[
             {'id': '10', 'name': 'TV Show Favs', 'slug': 'tv-show-favs'},
         ]):
        resp = client.get('/search?q=listed&type=show')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Listed Show' in html
    assert 'TV Show Favs' in html


def test_recommendations_page_shows_personal_list_tags(app, client, user):
    with app.app_context():
        _seed_title('movie', 9, 'Listed Rec', user)
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.catalog_routes.trakt_client.get_recommendations', return_value=[
        {
            'title': 'Listed Rec', 'year': 2024, 'overview': 'A',
            'ids': {'trakt': 9, 'slug': 'listed-rec'},
        },
    ]), patch('services.sync_jobs.enrich_media_list_for_display'), \
         patch('routes.catalog_routes.trakt_client.get_personal_lists', return_value=[
             {'id': '10', 'name': 'TV Show Favs', 'slug': 'tv-show-favs'},
         ]):
        resp = client.get('/recommendations/movies')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Listed Rec' in html
    assert 'TV Show Favs' in html
