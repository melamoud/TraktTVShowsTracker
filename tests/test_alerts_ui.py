"""Alerts page cards: poster, S#E#, streaming tags, progress-drawer action."""

from datetime import date, datetime
from unittest.mock import patch

from models import (
    CachedMedia, MediaFoundOn, MediaProviderAvailability, Notification, UserMediaState, db,
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
        db.session.add(MediaFoundOn(
            user_id=user, media_type='show', trakt_id=7701, service_label='toFlx',
        ))
        db.session.commit()

    login_client(client, app, user)
    html = client.get('/notifications').get_data(as_text=True)
    assert 'Silo' in html
    assert 'S03E01' in html and 'Into the Fire' in html
    assert 'Apple TV+' in html                       # streaming tag
    assert 'Streaming:' in html
    assert 'Found on:' in html and 'toFlx' in html
    assert 'data-action="progress-open"' in html     # drawer, not page nav
    assert 'data-trakt-id="7701"' in html
    assert '/catalog/show/7701' in html              # details link
    assert 'New episode' in html                     # type tag label
    assert 'Hiding read' in html
    assert 'alert-title' in html and 'alert-ep' in html
    assert html.find('S03E01') < html.find('Into the Fire')
    assert 'alert-also' in html or 'Streaming:' in html
    assert 'alert-services' in html
    # Also streaming / Streaming is its own row above Found on / Plays on.
    also_at = html.find('Streaming:')
    found_at = html.find('Found on:')
    assert also_at != -1 and found_at != -1 and also_at < found_at


def test_streaming_movie_alert_shows_release_date_not_blurb(app, client, user):
    """Now-streaming movies put the release date on the title line, not 'available on'."""
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='movie', trakt_id=99, title='Altered', year=2014,
            released_at=date(2014, 1, 15),
        ))
        db.session.add(Notification(
            user_id=user, alert_type='new_streaming',
            title='Now on YouTube Free: Altered',
            message='Altered is available on YouTube Free.',
            media_type='movie', trakt_id=99, is_read=False,
        ))
        db.session.commit()

    login_client(client, app, user)
    html = client.get('/notifications').get_data(as_text=True)
    assert 'Altered' in html
    assert 'Now streaming' in html
    assert '2014-01-15' in html
    assert 'is available on' not in html


def test_legacy_episode_alert_hides_available_on_suffix(app, client, user):
    """Older episode messages appended providers; title line keeps S#E# + date only."""
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show', trakt_id=88, title='Lucky', year=2025,
        ))
        db.session.add(Notification(
            user_id=user, alert_type='episode_aired',
            title='New episode: Lucky',
            message=(
                'S01E05 — Are We Bad People? aired 2026-08-05. '
                'Available on: Apple TV, Apple TV Amazon Channel'
            ),
            media_type='show', trakt_id=88, is_read=False,
        ))
        db.session.commit()

    login_client(client, app, user)
    html = client.get('/notifications').get_data(as_text=True)
    assert 'Lucky' in html
    assert 'S01E05' in html and 'Are We Bad People?' in html
    assert '2026-08-05' in html
    assert 'Available on:' not in html
    assert 'Apple TV Amazon Channel' not in html


def test_notifications_hide_read_filter(app, client, user):
    """Hide read (default) drops read alerts; Show read brings them back."""
    with app.app_context():
        db.session.add(Notification(
            user_id=user, alert_type='episode_aired',
            title='Unread show', message='S01E01 · aired today',
            media_type='show', trakt_id=1, is_read=False,
        ))
        db.session.add(Notification(
            user_id=user, alert_type='episode_aired',
            title='Read show', message='S01E02 · aired yesterday',
            media_type='show', trakt_id=2, is_read=True,
        ))
        db.session.commit()

    login_client(client, app, user)
    hidden = client.get('/notifications').get_data(as_text=True)
    assert 'Unread show' in hidden
    assert 'Read show' not in hidden
    assert 'Hiding read' in hidden

    shown = client.get('/notifications?hide_read=0').get_data(as_text=True)
    assert 'Unread show' in shown
    assert 'Read show' in shown
    assert 'Showing all' in shown


def test_legacy_alert_without_trakt_id_still_gets_found_on(app, client, user):
    """Older episode alerts stored title only; Found on still resolves by show name."""
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show', trakt_id=280856, title='Stuart Fails to Save the Universe',
            year=2026,
        ))
        db.session.add(MediaFoundOn(
            user_id=user, media_type='show', trakt_id=280856, service_label='toFlx',
        ))
        db.session.add(Notification(
            user_id=user,
            alert_type='episode_aired',
            title='New episode: Stuart Fails to Save the Universe',
            message='S01E04 — Spoiler · aired 2026-08-14',
            media_type=None,
            trakt_id=None,
        ))
        db.session.commit()
    login_client(client, app, user)
    html = client.get('/notifications').get_data(as_text=True)
    assert 'Stuart Fails to Save the Universe' in html
    assert 'Found on:' in html and 'toFlx' in html
    data = client.get('/api/v1/alerts').get_json()
    item = next(row for row in data['items'] if 'Stuart' in (row.get('title') or ''))
    assert item['found_on'] == ['toFlx']
    assert item['trakt_id'] == 280856
    assert item['media_type'] == 'show'


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
