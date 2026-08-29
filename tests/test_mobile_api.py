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
    assert 'found_on_choices' in body

    shows = client.get('/api/v1/my/shows')
    assert shows.status_code == 200
    assert shows.get_json()['media_type'] == 'show'
    assert 'found_on_choices' in shows.get_json()

    alerts = client.get('/api/v1/alerts')
    assert alerts.status_code == 200
    assert alerts.get_json()['success'] is True


def test_alerts_json_includes_found_on(app, client, user):
    login_client(client, app, user)
    with app.app_context():
        from models import UserPreference
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.genres_json = '["drama"]'
        db.session.add(CachedMedia(
            media_type='show', trakt_id=42, title='The Bear', year=2022,
            genres_json='["drama"]',
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
    match = item.get('match') or {}
    assert match.get('matched') is True
    assert 'drama' in (match.get('genres') or [])


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
    choice_links = data['item'].get('found_on_choice_links') or []
    assert choice_links
    hulu_choice = next((row for row in choice_links if row['label'] == 'Hulu'), None)
    assert hulu_choice and 'hulu.com' in (hulu_choice.get('url') or '')
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
    assert 'found_on_choices' in data


def test_found_on_choices_v1(app, client, user):
    login_client(client, app, user)
    resp = client.get('/api/v1/found-on/choices')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert isinstance(data['choices'], list)
    assert data['choices']
    assert isinstance(data.get('choice_links'), list)
    assert data['choice_links']
    netflix = next((row for row in data['choice_links'] if row['label'] == 'Netflix'), None)
    assert netflix is not None
    assert netflix.get('url')

    titled = client.get('/api/v1/found-on/choices?title=Silo&year=2023')
    assert titled.status_code == 200
    silo = next(
        (row for row in titled.get_json()['choice_links'] if row['label'] == 'Netflix'),
        None,
    )
    assert silo is not None
    assert 'Silo' in (silo.get('url') or '')
    assert '2023' in (silo.get('url') or '')


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
    drama = next(item for item in data['items'] if item['trakt_id'] == 23)
    assert 'found_on' in drama
    assert drama.get('found_on_choice_links')


def test_widget_requires_login(client):
    resp = client.get('/api/v1/widget?mode=shows')
    assert resp.status_code == 401


def test_widget_shows_movies_alerts_and_does_not_persist_display(app, client, user):
    login_client(client, app, user)
    with app.app_context():
        from services import view_prefs
        from models import User
        user_obj = db.session.get(User, user)
        view_prefs.update_view(user_obj, 'my_shows', display='list')
        db.session.add(CachedMedia(
            media_type='show', trakt_id=42, title='The Bear', year=2022,
        ))
        db.session.add(UserMediaState(
            user_id=user, media_type='show', trakt_id=42, on_watchlist=True,
            episodes_aired=10, episodes_completed=8,
            next_episode_season=3, next_episode_number=2,
            next_episode_title='Forks',
            last_episode_aired_at=datetime.utcnow() - timedelta(days=1),
        ))
        db.session.add(CachedMedia(
            media_type='show', trakt_id=99, title='All Caught Up', year=2020,
        ))
        db.session.add(UserMediaState(
            user_id=user, media_type='show', trakt_id=99, on_watchlist=True,
            episodes_aired=8, episodes_completed=8,
            last_episode_aired_at=datetime.utcnow() - timedelta(days=2),
        ))
        db.session.add(CachedMedia(
            media_type='movie', trakt_id=9, title='Old Film', year=2020,
            released_at=datetime.utcnow().date() - timedelta(days=10),
        ))
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=9, on_watchlist=True,
            watched=False,
        ))
        db.session.add(Notification(
            user_id=user, alert_type='episode_aired', title='The Bear S3E1',
            message='S03E01 aired', media_type='show', trakt_id=42,
            payload_key='ep:3:1',
        ))
        db.session.add(Notification(
            user_id=user, alert_type='episode_aired', title='The Bear S3E2',
            message='S03E02 aired', media_type='show', trakt_id=42,
            payload_key='ep:3:2',
        ))
        db.session.commit()

    shows = client.get('/api/v1/widget?mode=shows')
    assert shows.status_code == 200
    show_body = shows.get_json()
    assert show_body['mode'] == 'shows'
    assert show_body['items']
    row = show_body['items'][0]
    assert row['title'] == 'The Bear'
    assert row['can_watch'] is True
    assert row['season'] == 3
    assert 'more to watch' in (row.get('remaining_label') or '')
    assert all(item['title'] != 'All Caught Up' for item in show_body['items'])

    movies = client.get('/api/v1/widget?mode=movies')
    assert movies.status_code == 200
    movie_body = movies.get_json()
    assert movie_body['mode'] == 'movies'
    assert movie_body['items'][0]['title'] == 'Old Film'
    assert movie_body['items'][0]['can_watch'] is True

    alerts = client.get('/api/v1/widget?mode=alerts')
    assert alerts.status_code == 200
    alert_body = alerts.get_json()
    assert alert_body['mode'] == 'alerts'
    group = next(item for item in alert_body['items'] if item['kind'] == 'group')
    assert group['expandable'] is True
    assert group['child_count'] == 2
    assert group['items']

    with app.app_context():
        from services import view_prefs
        from models import User
        user_obj = db.session.get(User, user)
        assert view_prefs.get_view(user_obj, 'my_shows').get('display') == 'list'
