"""Alerts page cards: poster, S#E#, streaming tags, progress-drawer action."""

from datetime import date, datetime
from unittest.mock import patch

from models import (
    CachedMedia, MediaProviderAvailability, Notification, UserMediaState, db,
)
from services.alerts import ALERT_EPISODE_AIRED, run_media_alerts
from tests.conftest import login_client


def _episode_alert(app, user) -> None:
    """Create one episode alert via the bulk calendar path."""
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show', trakt_id=7701, title='Silo', year=2023,
            trakt_listed_at=datetime.utcnow(),
        ))
        db.session.add(UserMediaState(
            user_id=user, media_type='show', trakt_id=7701, on_watchlist=True,
        ))
        db.session.commit()
        from models import UserCalendarEvent
        db.session.add(UserCalendarEvent(
            user_id=user, media_type='show', trakt_id=7701,
            event_date=date.today(), season_number=3, episode_number=1,
            episode_title='Into the Fire',
        ))
        db.session.commit()

        with patch('services.alerts.ensure_user_calendar_fresh', return_value=True), \
             patch('services.alerts.tmdb_configured', return_value=False):
            assert run_media_alerts(app) == 1


def test_episode_alert_stores_media_fields(app, user):
    _episode_alert(app, user)
    with app.app_context():
        note = Notification.query.filter_by(
            user_id=user, alert_type=ALERT_EPISODE_AIRED,
        ).one()
        assert note.media_type == 'show'
        assert note.trakt_id == 7701
        assert 'S03E01' in note.message
        assert 'Into the Fire' in note.message
        assert 'Available on' not in note.message  # providers render as tags


def test_notifications_page_renders_episode_card(app, client, user):
    _episode_alert(app, user)
    with app.app_context():
        media = CachedMedia.query.filter_by(media_type='show', trakt_id=7701).one()
        db.session.add(MediaProviderAvailability(
            cached_media_id=media.id, provider_name='Apple TV+',
            offer_type='flatrate',
        ))
        db.session.commit()

    login_client(client, app, user)
    html = client.get('/notifications').get_data(as_text=True)
    assert 'Silo' in html
    assert 'S03E01' in html and 'Into the Fire' in html
    assert 'Apple TV+' in html                       # streaming tag
    assert 'data-action="progress-open"' in html     # drawer, not page nav
    assert 'data-trakt-id="7701"' in html
    assert '/catalog/show/7701' in html              # details link
    assert 'New episode' in html                     # type tag label


def test_notifications_page_without_media_still_works(app, client, user):
    """Login alerts (no media link) render in the single-column layout."""
    with app.app_context():
        db.session.add(Notification(
            user_id=user, alert_type='new_user_login',
            title='New login', message='New login from 1.2.3.4',
        ))
        db.session.commit()
    login_client(client, app, user)
    html = client.get('/notifications').get_data(as_text=True)
    assert 'New login' in html
    assert 'no-poster' in html
