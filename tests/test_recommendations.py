"""Tests for recommendations page and streaming-service matching helpers."""

from unittest.mock import patch

from models import (
    CachedMedia,
    MediaProviderAvailability,
    StreamingService,
    UserMediaState,
    UserPreference,
    UserStreamingService,
    db,
)
from services.streaming_matcher import (
    genre_to_trakt_slug,
    names_match,
    split_providers_for_user,
)
from tests.conftest import login_client


def test_genre_to_trakt_slug():
    assert genre_to_trakt_slug('science fiction') == 'science-fiction'
    assert genre_to_trakt_slug('Action') == 'action'
    assert genre_to_trakt_slug('') == ''


def test_names_match_fuzzy():
    assert names_match('Prime Video', 'Amazon Prime Video')
    assert names_match('Netflix', 'netflix')
    assert not names_match('Netflix', 'Hulu')


def test_split_providers_for_user(app, user):
    with app.app_context():
        from models import User

        u = db.session.get(User, user)
        netflix = StreamingService.query.filter_by(name='Netflix').first()
        if not netflix:
            netflix = StreamingService(name='Netflix', is_default=True)
            db.session.add(netflix)
            db.session.flush()
        db.session.add(UserStreamingService(
            user_id=u.id, streaming_service_id=netflix.id, is_custom=False,
        ))
        db.session.commit()
        db.session.refresh(u)

        mine, other = split_providers_for_user(
            ['Netflix', 'Hulu', 'Disney Plus'], u,
        )
        assert mine == ['Netflix']
        assert 'Hulu' in other
        assert 'Disney Plus' in other


def test_recommendations_page_renders(app, client, user):
    login_client(client, app, user)
    fake = [
        {
            'title': 'Rec Movie One',
            'year': 2024,
            'overview': 'A recommended drama.',
            'genres': ['drama', 'thriller'],
            'ids': {'trakt': 9001, 'tmdb': 101, 'slug': 'rec-movie-one'},
        },
        {
            'title': 'Rec Movie Two',
            'year': 2023,
            'overview': 'Already on wishlist.',
            'genres': ['comedy'],
            'ids': {'trakt': 9002, 'tmdb': 102, 'slug': 'rec-movie-two'},
        },
    ]
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).first()
        prefs.genres_json = '["drama"]'
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=9002,
            on_watchlist=True, watched=False,
        ))
        db.session.commit()

    with patch('services.trakt_client.get_recommendations', return_value=fake):
        with patch('services.sync_jobs.enrich_media_list_for_display', return_value=[]):
            with patch('services.sync_jobs.sync_providers_for_media', return_value=[]):
                resp = client.get('/recommendations/movies')

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Recommended Movies' in html
    assert 'Rec Movie One' in html
    # Default hide wishlist — second title should not appear
    assert 'Rec Movie Two' not in html
    assert 'drama' in html.lower()
    assert 'Hiding wishlist' in html


def test_recommendations_show_wishlist_when_toggled(app, client, user):
    login_client(client, app, user)
    fake = [
        {
            'title': 'Wishlisted Rec',
            'year': 2024,
            'overview': 'On list',
            'genres': ['drama'],
            'ids': {'trakt': 9010, 'slug': 'wishlisted-rec'},
        },
    ]
    with app.app_context():
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=9010,
            on_watchlist=True, watched=False,
        ))
        db.session.commit()

    with patch('services.trakt_client.get_recommendations', return_value=fake):
        with patch('services.sync_jobs.enrich_media_list_for_display', return_value=[]):
            with patch('services.sync_jobs.sync_providers_for_media', return_value=[]):
                resp = client.get('/recommendations/movies?hide_wishlist=0')

    assert resp.status_code == 200
    assert 'Wishlisted Rec' in resp.get_data(as_text=True)


def test_recommendations_category_passed_to_trakt(app, client, user):
    login_client(client, app, user)
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).first()
        prefs.genres_json = '["science fiction", "drama"]'
        db.session.commit()

    with patch('services.trakt_client.get_recommendations', return_value=[]) as mock_rec:
        with patch('services.sync_jobs.enrich_media_list_for_display', return_value=[]):
            resp = client.get('/recommendations/shows?category=science-fiction')

    assert resp.status_code == 200
    assert mock_rec.called
    kwargs = mock_rec.call_args.kwargs
    assert kwargs.get('genres') == 'science-fiction'


def test_recommendations_highlights_my_services(app, client, user):
    login_client(client, app, user)
    fake = [
        {
            'title': 'On Netflix Rec',
            'year': 2025,
            'overview': 'Available',
            'genres': ['drama'],
            'ids': {'trakt': 9020, 'tmdb': 2020, 'slug': 'on-netflix-rec'},
        },
    ]
    with app.app_context():
        from models import User

        u = db.session.get(User, user)
        netflix = StreamingService.query.filter_by(name='Netflix').first()
        if not netflix:
            netflix = StreamingService(name='Netflix', is_default=True)
            db.session.add(netflix)
            db.session.flush()
        db.session.add(UserStreamingService(
            user_id=u.id, streaming_service_id=netflix.id, is_custom=False,
        ))
        db.session.commit()

    def _fake_upsert(media_type, entry, **kwargs):
        ids = entry.get('ids') or {}
        row = CachedMedia.query.filter_by(
            media_type=media_type, trakt_id=ids['trakt'],
        ).first()
        if not row:
            row = CachedMedia(
                media_type=media_type,
                trakt_id=ids['trakt'],
                title=entry.get('title') or 'Untitled',
                year=entry.get('year'),
                overview=entry.get('overview'),
                genres_json='["drama"]',
                tmdb_id=ids.get('tmdb'),
            )
            db.session.add(row)
            db.session.flush()
        db.session.add(MediaProviderAvailability(
            cached_media_id=row.id,
            provider_name='Netflix',
            offer_type='flatrate',
            tmdb_provider_id=8,
        ))
        db.session.commit()
        return row

    with patch('services.trakt_client.get_recommendations', return_value=fake):
        with patch('services.sync_jobs.upsert_cached_media', side_effect=_fake_upsert):
            with patch('services.sync_jobs.enrich_media_list_for_display', return_value=[]):
                with patch('services.sync_jobs.sync_providers_for_media', return_value=['Netflix']):
                    resp = client.get('/recommendations/movies')

    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert 'On Netflix Rec' in html
    assert 'Plays on your services' in html
    assert 'stream mine' in html
    assert 'Hide recommendation' in html
    assert 'data-action="recommendation-hide"' in html


def test_hide_recommendation_api(app, client, user):
    login_client(client, app, user)
    with patch('services.trakt_client.hide_recommendation') as mock_hide:
        resp = client.post('/api/recommendations/movie/12345/hide')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['hidden'] is True
    mock_hide.assert_called_once()
    args = mock_hide.call_args.args
    assert args[1] == 'movie'
    assert args[2] == 12345
