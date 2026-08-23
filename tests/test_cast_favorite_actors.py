"""Cast cache + favorite-actor preference tests."""

from unittest.mock import patch

from models import CachedMedia, CachedPerson, MediaCastMember, UserFavoriteActor, db
from tests.conftest import login_client


def _seed_media(app, *, tmdb_id=None):
    with app.app_context():
        media = CachedMedia(
            media_type='movie',
            trakt_id=100,
            title='Test Movie',
            year=2020,
            tmdb_id=tmdb_id,
        )
        db.session.add(media)
        db.session.commit()
        return media.id


SAMPLE_PEOPLE = {
    'cast': [
        {
            'characters': ['Hero'],
            'person': {
                'name': 'Ada Actor',
                'ids': {'trakt': 501, 'slug': 'ada-actor', 'tmdb': 9001, 'imdb': 'nm1'},
            },
        },
        {
            'characters': ['Villain'],
            'person': {
                'name': 'Bea Player',
                'ids': {'trakt': 502, 'slug': 'bea-player', 'tmdb': 9002},
            },
        },
        {
            'character': 'Sidekick',
            'person': {
                'name': 'Cara Cast',
                'ids': {'trakt': 503, 'slug': 'cara-cast'},
            },
        },
    ],
}


def test_media_detail_shows_cast_and_expand(app, client, user):
    """Detail page fetches Trakt people and renders main cast."""
    _seed_media(app)
    login_client(client, app, user)
    with patch(
        'services.trakt_client.fetch_media_people',
        return_value=SAMPLE_PEOPLE,
    ) as fetch, patch(
        'services.sync_jobs.enrich_media_details_for_display',
    ), patch(
        'routes.catalog_routes.sync_providers_for_media',
    ), patch(
        'services.cast_service.ensure_cast_headshots', return_value=0,
    ):
        resp = client.get('/catalog/movie/100')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Ada Actor' in html
    assert 'Bea Player' in html
    assert 'favorite-actor-add' in html
    fetch.assert_called_once()

    with app.app_context():
        assert CachedPerson.query.filter_by(trakt_id=501).one().name == 'Ada Actor'
        media = CachedMedia.query.filter_by(media_type='movie', trakt_id=100).one()
        assert media.cast_fetched_at is not None
        assert MediaCastMember.query.filter_by(cached_media_id=media.id).count() == 3


def test_ensure_cast_headshots_uses_credits_once_and_skips_cached(app, user):
    """One TMDB credits call; download only missing people; second pass is a no-op."""
    from pathlib import Path

    from services.cast_service import ensure_cast_headshots, sync_cast_for_media

    _seed_media(app, tmdb_id=55)
    with app.app_context():
        media = CachedMedia.query.filter_by(media_type='movie', trakt_id=100).one()
        with patch('services.trakt_client.fetch_media_people', return_value=SAMPLE_PEOPLE):
            credits = sync_cast_for_media(media)

        profiles = {
            9001: 'https://image.tmdb.org/t/p/w185/ada.jpg',
            9002: 'https://image.tmdb.org/t/p/w185/bea.jpg',
        }
        cached_ids: set[int] = set()

        def fake_download(pid, url):
            cached_ids.add(int(pid))
            return f'/cache/actors/{pid}'

        def fake_path(pid):
            return Path(f'person_{pid}.jpg') if int(pid) in cached_ids else None

        with patch('services.tmdb_client.is_configured', return_value=True), \
             patch('services.tmdb_client.get_cast_profile_urls', return_value=profiles) as credits_api, \
             patch('services.cast_service.cache_remote_headshot', side_effect=fake_download) as download, \
             patch('services.cast_service.local_actor_path', side_effect=fake_path):
            n = ensure_cast_headshots(media, credits)
        assert n == 2
        credits_api.assert_called_once_with('movie', 55)
        assert download.call_count == 2

        ada = CachedPerson.query.filter_by(trakt_id=501).one()
        assert ada.headshot_url == '/cache/actors/501'

        with patch('services.tmdb_client.is_configured', return_value=True), \
             patch('services.tmdb_client.get_cast_profile_urls') as credits_api2, \
             patch('services.cast_service.cache_remote_headshot') as download2, \
             patch('services.cast_service.local_actor_path', side_effect=fake_path):
            n2 = ensure_cast_headshots(media, credits)
        assert n2 == 0
        credits_api2.assert_not_called()
        download2.assert_not_called()


def test_api_favorite_actor_toggles_and_prefs_remove(app, client, user):
    """Favorite actor API stores locally; Preferences can remove."""
    _seed_media(app)
    login_client(client, app, user)
    with patch('services.trakt_client.fetch_media_people', return_value=SAMPLE_PEOPLE), \
         patch('services.sync_jobs.enrich_media_details_for_display'), \
         patch('routes.catalog_routes.sync_providers_for_media'), \
         patch('services.cast_service.ensure_cast_headshots', return_value=0):
        client.get('/catalog/movie/100')

    with patch('services.cast_service.ensure_person_headshot', return_value=None):
        resp = client.post('/api/favorite-actor/501', json={'action': 'add'})
    assert resp.status_code == 200
    assert resp.get_json()['favorited'] is True

    with app.app_context():
        person = CachedPerson.query.filter_by(trakt_id=501).one()
        assert UserFavoriteActor.query.filter_by(
            user_id=user, person_id=person.id,
        ).count() == 1

    prefs = client.get('/preferences')
    assert prefs.status_code == 200
    assert 'Ada Actor' in prefs.get_data(as_text=True)

    resp = client.post('/preferences', data={
        'remove_favorite_actor_ids': ['501'],
        'lists_prefs_present': '1',
        'alerts_prefs_present': '1',
        'alert_release_day': '1',
        'alert_new_streaming': '1',
        'alert_episode_aired': '1',
        'alert_list_add': '1',
    }, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        assert UserFavoriteActor.query.filter_by(user_id=user).count() == 0


def test_api_favorite_actor_unknown_person(app, client, user):
    """Favoriting an actor never seen in cast returns 400."""
    login_client(client, app, user)
    resp = client.post('/api/favorite-actor/99999', json={'action': 'add'})
    assert resp.status_code == 400
    assert 'Unknown actor' in resp.get_json()['message']
