"""Tests for models and default seed data."""

from models import MediaProviderAvailability, StreamingService, User, db
from services.seed import seed_default_streaming_services
from services.streaming_matcher import match_preferences, serialize_prefs
from models import CachedMedia, UserPreference, UserStreamingService


def test_seed_default_services(app):
    """Default streaming services are seeded at app start and are idempotent."""
    with app.app_context():
        assert StreamingService.query.filter_by(name='Netflix').first() is not None
        # Second call inserts nothing
        assert seed_default_streaming_services() == 0


def test_preference_match_highlight(app, user):
    """Genre/keyword preferences produce a match highlight."""
    with app.app_context():
        u = db.session.get(User, user)
        prefs = u.preferences or UserPreference(user_id=u.id)
        g, k = serialize_prefs(['drama'], ['heist'])
        prefs.genres_json = g
        prefs.keywords_json = k
        db.session.add(prefs)

        media = CachedMedia(
            media_type='movie',
            trakt_id=42,
            title='Ocean Job',
            overview='A clever heist in the city',
            genres_json='["drama","crime"]',
        )
        db.session.add(media)
        db.session.commit()

        result = match_preferences(media, u)
        assert result['matched'] is True
        assert 'drama' in [x.lower() for x in result['genres']] or result['keywords']


def test_preference_match_ignores_streaming(app, user):
    """Owned streaming services alone must not purple-highlight a title."""
    with app.app_context():
        u = db.session.get(User, user)
        netflix = StreamingService.query.filter_by(name='Netflix').first()
        assert netflix is not None
        db.session.add(UserStreamingService(
            user_id=u.id,
            streaming_service_id=netflix.id,
            custom_name=None,
        ))

        media = CachedMedia(
            media_type='movie',
            trakt_id=99,
            title='Random Flick',
            overview='No preference keywords here',
            genres_json='["comedy"]',
        )
        db.session.add(media)
        db.session.flush()
        db.session.add(MediaProviderAvailability(
            cached_media_id=media.id,
            provider_name='Netflix',
            offer_type='flatrate',
        ))
        db.session.commit()

        result = match_preferences(media, u)
        assert result['matched'] is False
        assert result['streaming'] == []
