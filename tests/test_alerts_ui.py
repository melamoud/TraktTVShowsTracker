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
    assert 'S3E1' in html and 'Into the Fire' in html
    assert 'Apple TV+' in html                       # streaming tag
    assert 'Streaming:' in html
    assert 'Found on:' in html and 'toFlx' in html
    assert 'data-action="progress-open"' in html     # drawer, not page nav
    assert 'data-trakt-id="7701"' in html
    assert '/catalog/show/7701' in html              # details link
    assert 'New episode' in html                     # type tag label
    assert 'Hiding read' in html
    assert 'alert-title' in html and 'alert-ep' in html
    assert 'alert-ep-code' in html
    assert html.find('S3E1') < html.find('Into the Fire')
    assert 'alert-kind-badge' in html and 'Episode' in html
    assert 'alert-also' in html or 'Streaming:' in html
    assert 'alert-services' in html
    # Also streaming / Streaming is its own row above Found on / Plays on.
    also_at = html.find('Streaming:')
    found_at = html.find('Found on:')
    assert also_at != -1 and found_at != -1 and also_at < found_at


def test_streaming_movie_alert_shows_vendor_not_blurb(app, client, user):
    """Now-streaming movies list the vendor on the title line, not 'available on'."""
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
    assert 'Streaming' in html
    assert 'YouTube Free' in html
    assert 'is available on' not in html
    assert 'data-action="progress-open"' not in html


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
    assert 'S1E5' in html and 'Are We Bad People?' in html
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
    assert 'Admin' in html
    assert 'alert-kind-badge' in html


def _two_episode_alerts(app, user, *, pinned=False):
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show', trakt_id=501, title='The Agency', year=2024,
        ))
        st = UserMediaState(
            user_id=user, media_type='show', trakt_id=501, on_watchlist=True,
            alerts_pinned=pinned,
        )
        db.session.add(st)
        db.session.add(Notification(
            user_id=user, alert_type='episode_aired',
            title='New episode: The Agency',
            message='S03E05 — Night Work · aired 2026-08-20',
            media_type='show', trakt_id=501, payload_key='ep:3:5',
            is_read=False, created_at=datetime(2026, 8, 20, 10, 0),
        ))
        db.session.add(Notification(
            user_id=user, alert_type='episode_aired',
            title='New episode: The Agency',
            message='S03E06 — Aftermath · aired 2026-08-21',
            media_type='show', trakt_id=501, payload_key='ep:3:6',
            is_read=False, created_at=datetime(2026, 8, 21, 10, 0),
        ))
        db.session.add(Notification(
            user_id=user, alert_type='release_day',
            title='Released: Other Film',
            message='Movie release date was 2026-08-22.',
            media_type='movie', trakt_id=88,
            is_read=False, created_at=datetime(2026, 8, 22, 10, 0),
        ))
        db.session.add(CachedMedia(
            media_type='movie', trakt_id=88, title='Other Film', year=2026,
        ))
        db.session.commit()


def test_alerts_group_show_episodes(app, client, user):
    """Two episode alerts for one show collapse; movie stays its own row."""
    _two_episode_alerts(app, user)
    login_client(client, app, user)
    html = client.get('/notifications').get_data(as_text=True)
    assert 'alert-group' in html
    assert 'The Agency' in html
    assert 'S3E5' in html and 'S3E6' in html
    assert 'Show 2 alerts' in html
    assert 'data-action="alert-group-toggle"' in html
    assert 'data-action="alerts-pin-add"' in html
    assert 'Other Film' in html
    assert 'Movie' in html
    # Children stay in the expanded body for per-episode actions.
    assert 'data-action="progress-open"' in html
    assert 'Mark read' in html


def test_alerts_ungroup_shows_each_row(app, client, user):
    _two_episode_alerts(app, user)
    login_client(client, app, user)
    html = client.get('/notifications?group_shows=0').get_data(as_text=True)
    assert 'alert-group' not in html
    assert 'One row each' in html
    assert html.count('alert-ep-code') >= 2


def test_alerts_sort_oldest_first(app, client, user):
    _two_episode_alerts(app, user)
    login_client(client, app, user)
    html = client.get('/notifications?group_shows=0&sort=asc').get_data(as_text=True)
    assert 'Oldest first' in html
    assert html.find('S3E5') < html.find('S3E6') < html.find('Other Film')


def test_alerts_pin_floats_show_to_top(app, client, user):
    """Pinned show stays above a newer unpinned movie."""
    _two_episode_alerts(app, user, pinned=True)
    login_client(client, app, user)
    html = client.get('/notifications?group_shows=0&sort=desc').get_data(as_text=True)
    assert html.find('The Agency') < html.find('Other Film')
    assert 'is-pinned' in html

    login_client(client, app, user)
    resp = client.post('/api/alerts/pin/show/501', json={'action': 'unpin'})
    assert resp.status_code == 200
    assert resp.get_json()['alerts_pinned'] is False
    html = client.get('/notifications?group_shows=0&sort=desc').get_data(as_text=True)
    assert html.find('Other Film') < html.find('The Agency')


def test_alerts_api_includes_pin_sort_group(app, client, user):
    _two_episode_alerts(app, user, pinned=True)
    login_client(client, app, user)
    data = client.get('/api/v1/alerts?group_shows=1&sort=desc').get_json()
    assert data['success'] is True
    assert data['sort'] == 'desc'
    assert data['group_shows'] is True
    agency = next(row for row in data['items'] if row['trakt_id'] == 501)
    assert agency['episode_code'] in ('S3E5', 'S3E6')
    assert agency['alerts_pinned'] is True
    assert agency['kind_label'] == 'Episode'
    assert 'S3E' in agency['display_title']
    groups = [e for e in data['entries'] if e.get('kind') == 'group']
    assert groups and groups[0]['title'] == 'The Agency'
    assert groups[0]['kind_label'] == 'Episode'
    assert 'S3E5' in groups[0]['episode_codes']


def test_season_alert_badge_and_code_from_title(app, client, user):
    """Season-drop alerts are labeled Season and show S# even without payload_key."""
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show', trakt_id=77, title='Outer Banks', year=2020,
        ))
        db.session.add(Notification(
            user_id=user, alert_type='season_aired',
            title='Season 4 out: Outer Banks',
            message='Full season published on 2026-08-20.',
            media_type='show', trakt_id=77, payload_key=None, is_read=False,
        ))
        db.session.commit()
    login_client(client, app, user)
    html = client.get('/notifications').get_data(as_text=True)
    assert 'Outer Banks' in html
    assert 'S4' in html
    assert 'alert-kind-season' in html
    assert 'Season' in html
    assert 'Season out' in html


def test_watched_episode_alert_cleared_on_page(app, client, user):
    """Opening Alerts marks a watched episode read so it does not stay unread."""
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show', trakt_id=88, title='Lucky', year=2025,
        ))
        db.session.add(UserMediaState(
            user_id=user, media_type='show', trakt_id=88,
            episodes_aired=8, episodes_completed=8,
            progress_payload_json='{"watched_keys": [[1, 1]]}',
        ))
        db.session.add(Notification(
            user_id=user, alert_type='episode_aired',
            title='New episode: Lucky',
            message='S01E01 — Pilot · aired 2026-08-01',
            media_type='show', trakt_id=88, payload_key='ep:1:1',
            is_read=False,
        ))
        db.session.commit()
    login_client(client, app, user)
    html = client.get('/notifications').get_data(as_text=True)
    assert 'Lucky' not in html
    with app.app_context():
        note = Notification.query.filter_by(user_id=user, trakt_id=88).one()
        assert note.is_read is True


def test_legacy_lucky_without_trakt_id_cleared_when_show_finished(app, client, user):
    """Old Lucky episode rows stored title only; still mark read if that show is caught up."""
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show', trakt_id=265812, title='Lucky', year=2025,
        ))
        db.session.add(CachedMedia(
            media_type='show', trakt_id=14758, title='Lucky', year=2013,
        ))
        db.session.add(UserMediaState(
            user_id=user, media_type='show', trakt_id=265812,
            episodes_aired=7, episodes_completed=7,
        ))
        db.session.add(UserMediaState(
            user_id=user, media_type='show', trakt_id=14758,
            episodes_aired=13, episodes_completed=0,
        ))
        db.session.add(Notification(
            user_id=user, alert_type='episode_aired',
            title='New episode: Lucky',
            message='S01E05 — Are We Bad People? aired 2026-08-05.',
            media_type=None, trakt_id=None, payload_key=None, is_read=False,
        ))
        db.session.commit()
    login_client(client, app, user)
    html = client.get('/notifications').get_data(as_text=True)
    assert 'Lucky' not in html
    with app.app_context():
        note = Notification.query.filter_by(user_id=user, alert_type='episode_aired').one()
        assert note.is_read is True


def test_streaming_show_alert_has_progress_and_streaming_badge(app, client, user):
    """A 'now on service' show alert is Streaming, not Episode — Progress still opens the show."""
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show', trakt_id=195577, title='Fire Country', year=2022,
        ))
        db.session.add(Notification(
            user_id=user, alert_type='new_streaming',
            title='Now on Paramount Plus Apple TV channel: Fire Country',
            message='Fire Country is available on Paramount Plus Apple TV channel.',
            media_type='show', trakt_id=195577, is_read=False,
        ))
        db.session.commit()
    login_client(client, app, user)
    html = client.get('/notifications').get_data(as_text=True)
    assert 'Fire Country' in html
    assert 'alert-kind-streaming' in html
    assert 'Now streaming' in html
    assert 'data-action="progress-open"' in html
    assert 'data-trakt-id="195577"' in html
    assert 'S1E' not in html and 'S01E' not in html


def test_notifications_page_renders_list_add_card(app, client, user):
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show', trakt_id=202341, title='The Agency', year=2024,
        ))
        db.session.add(Notification(
            user_id=user, alert_type='list_add',
            title='The Agency',
            message='Added to Wishlist',
            media_type='show', trakt_id=202341, is_read=False,
            payload_key='listadd:test:watchlist',
        ))
        db.session.commit()
    login_client(client, app, user)
    html = client.get('/notifications').get_data(as_text=True)
    assert 'The Agency' in html
    assert 'alert-kind-list' in html
    assert 'Added to list' in html
    assert 'Added to Wishlist' in html
    assert 'data-trakt-id="202341"' in html


def test_streaming_alerts_for_same_title_merge(app, client, user):
    """Two Now-on-X cards for one show render as one unread row listing both vendors."""
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show', trakt_id=157599, title='Lanterns', year=2026,
        ))
        db.session.add(Notification(
            user_id=user, alert_type='new_streaming',
            title='Now on HBO Max: Lanterns',
            message='Lanterns is available on HBO Max.',
            media_type='show', trakt_id=157599, is_read=True,
            payload_key='provider:hbo max',
        ))
        db.session.add(Notification(
            user_id=user, alert_type='new_streaming',
            title='Now on HBO Max Amazon Channel: Lanterns',
            message='Lanterns is available on HBO Max Amazon Channel.',
            media_type='show', trakt_id=157599, is_read=False,
            payload_key='provider:hbo max amazon channel',
        ))
        db.session.commit()
    login_client(client, app, user)
    html = client.get('/notifications?hide_read=0&group_shows=0').get_data(as_text=True)
    assert html.count('Now streaming') == 1
    assert 'HBO Max' in html
    assert 'HBO Max Amazon Channel' in html
    assert html.count('Unread') >= 1
    assert 'Show 2 alerts' not in html
