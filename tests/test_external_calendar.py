"""Google Calendar meetings for Wishlist and Auto-select lists."""

from datetime import datetime, timedelta

from models import (
    CachedMedia,
    CachedPerson,
    CalendarStreamingSeen,
    ExternalCalendarEvent,
    MediaCastMember,
    MediaProviderAvailability,
    StreamingService,
    User,
    UserCalendarEvent,
    UserGoogleCalendar,
    UserListMembership,
    UserMediaState,
    UserPreference,
    UserStreamingService,
    db,
)
from services.external_calendar import sync_external_calendar
from services.google_calendar import GoogleCalendarError
from services.local_time import local_today
from tests.conftest import login_client


class FakeGoogle:
    def __init__(self):
        self.inserted = []
        self.patched = []
        self.deleted = []
        self._n = 0

    def insert_event(self, calendar_id, body):
        self._n += 1
        event_id = f'g{self._n}'
        self.inserted.append((calendar_id, event_id, body))
        return event_id

    def patch_event(self, calendar_id, event_id, body):
        self.patched.append((calendar_id, event_id, body))

    def delete_event(self, calendar_id, event_id):
        self.deleted.append((calendar_id, event_id))

    def list_calendars(self):
        return [{'id': 'cal-1', 'name': 'Personal', 'primary': True}]


def _user(user_id):
    return db.session.get(User, user_id)


def _link(user_id):
    db.session.add(UserGoogleCalendar(
        user_id=user_id,
        account_email='me@gmail.com',
        access_token_enc='enc',
        refresh_token_enc='enc',
        calendar_id='cal-1',
        calendar_name='Personal',
        connected_at=datetime.utcnow(),
    ))


def _netflix(user_id):
    svc = StreamingService.query.filter_by(name='Netflix').first()
    if not svc:
        svc = StreamingService(name='Netflix', is_default=True)
        db.session.add(svc)
        db.session.flush()
    db.session.add(UserStreamingService(
        user_id=user_id, streaming_service_id=svc.id, is_custom=False,
    ))
    return svc


def _movie(trakt_id, title, released, *, overview='A desert epic.', with_cast=True):
    media = CachedMedia(
        media_type='movie',
        trakt_id=trakt_id,
        title=title,
        year=released.year if released else 2026,
        overview=overview,
        runtime=155,
        genres_json='["Science Fiction"]',
        released_at=released,
    )
    db.session.add(media)
    db.session.flush()
    if with_cast:
        person = CachedPerson(trakt_id=9000 + trakt_id, name='Zendaya')
        db.session.add(person)
        db.session.flush()
        db.session.add(MediaCastMember(
            cached_media_id=media.id,
            person_id=person.id,
            characters_json='["Chani"]',
            sort_order=0,
        ))
    return media


def _provider(media, name):
    db.session.add(MediaProviderAvailability(
        cached_media_id=media.id,
        provider_name=name,
        offer_type='flatrate',
        region='US',
        checked_at=datetime.utcnow(),
    ))


def test_theater_meeting_includes_cast_for_wishlist(app, user):
    today = local_today()
    with app.app_context():
        _link(user)
        media = _movie(42, 'Dune', today + timedelta(days=40))
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=42, on_watchlist=True,
        ))
        db.session.commit()
        fake = FakeGoogle()
        result = sync_external_calendar(_user(user), client=fake)
        assert result['created'] == 1
        _cal, _eid, body = fake.inserted[0]
        assert body['summary'] == 'In theaters: Dune (2026)'
        assert 'Zendaya as Chani' in body['description']
        assert 'A desert epic.' in body['description']
        assert 'Science Fiction' in body['description']
        assert 'Runtime: 155 min' in body['description']
        assert body['start']['date'] == (today + timedelta(days=40)).isoformat()
        assert ExternalCalendarEvent.query.filter_by(user_id=user, trakt_id=42).count() == 1

        again = sync_external_calendar(_user(user), client=fake)
        assert again['created'] == 0
        assert len(fake.inserted) == 1
        assert media.id


def test_other_personal_list_is_skipped_default_list_is_not(app, user):
    today = local_today()
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["10"]'
        _link(user)
        parked = _movie(7, 'Parked', today + timedelta(days=10), with_cast=False)
        chosen = _movie(8, 'Chosen', today + timedelta(days=12), with_cast=False)
        db.session.add(UserListMembership(
            user_id=user, list_id='55', media_type='movie', trakt_id=parked.trakt_id,
        ))
        db.session.add(UserListMembership(
            user_id=user, list_id='10', media_type='movie', trakt_id=chosen.trakt_id,
        ))
        db.session.commit()
        fake = FakeGoogle()
        sync_external_calendar(_user(user), client=fake)
        summaries = [body['summary'] for _c, _e, body in fake.inserted]
        assert summaries == ['In theaters: Chosen (2026)']


def test_wishlist_counts_even_when_not_auto_selected(app, user):
    today = local_today()
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["10"]'
        _link(user)
        _movie(3, 'Wish', today + timedelta(days=5), with_cast=False)
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=3, on_watchlist=True,
        ))
        db.session.commit()
        fake = FakeGoogle()
        sync_external_calendar(_user(user), client=fake)
        assert len(fake.inserted) == 1


def test_already_streaming_movie_is_not_backfilled(app, user):
    today = local_today()
    with app.app_context():
        _link(user)
        _netflix(user)
        mine = _movie(11, 'On Netflix', today - timedelta(days=400), with_cast=False)
        other = _movie(12, 'On Hulu', today - timedelta(days=400), with_cast=False)
        _provider(mine, 'Netflix')
        _provider(other, 'Hulu')
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=11, on_watchlist=True,
        ))
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=12, on_watchlist=True,
        ))
        db.session.commit()
        fake = FakeGoogle()
        sync_external_calendar(_user(user), client=fake)
        assert fake.inserted == []
        seen = CalendarStreamingSeen.query.filter_by(user_id=user, trakt_id=11).one()
        assert 'Netflix' in seen.vendors_json
        sync_external_calendar(_user(user), client=fake)
        assert fake.inserted == []


def test_movie_newly_on_my_service_gets_a_meeting(app, user):
    today = local_today()
    with app.app_context():
        _link(user)
        _netflix(user)
        media = _movie(11, 'On Netflix', today - timedelta(days=400), with_cast=False)
        media.provider_checked_at = datetime.utcnow()
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=11, on_watchlist=True,
        ))
        db.session.commit()
        fake = FakeGoogle()
        sync_external_calendar(_user(user), client=fake)
        assert fake.inserted == []
        _provider(media, 'Netflix')
        db.session.commit()
        sync_external_calendar(_user(user), client=fake)
        assert len(fake.inserted) == 1
        body = fake.inserted[0][2]
        assert body['summary'] == 'Streaming on Netflix: On Netflix (2025)'
        assert body['start']['date'] == today.isoformat()


def test_catchup_streaming_meetings_are_removed(app, user):
    today = local_today()
    with app.app_context():
        _link(user)
        _netflix(user)
        media = _movie(11, 'On Netflix', today - timedelta(days=400), with_cast=False)
        _provider(media, 'Netflix')
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=11, on_watchlist=True,
        ))
        db.session.add(ExternalCalendarEvent(
            user_id=user, media_type='movie', trakt_id=11, kind='streaming',
            season_number=0, episode_number=0, event_date=today,
            google_event_id='old1', calendar_id='cal-1',
        ))
        db.session.commit()
        fake = FakeGoogle()
        result = sync_external_calendar(_user(user), client=fake)
        assert result['deleted'] == 1
        assert fake.deleted == [('cal-1', 'old1')]
        assert fake.inserted == []


def test_future_release_streaming_meeting_uses_release_date(app, user):
    today = local_today()
    release = today + timedelta(days=40)
    with app.app_context():
        _link(user)
        _netflix(user)
        media = _movie(11, 'Soon', release, with_cast=False)
        _provider(media, 'Netflix')
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=11, on_watchlist=True,
        ))
        db.session.commit()
        fake = FakeGoogle()
        sync_external_calendar(_user(user), client=fake)
        streaming = [
            body for _c, _e, body in fake.inserted
            if body['summary'].startswith('Streaming on Netflix')
        ]
        assert len(streaming) == 1
        assert streaming[0]['start']['date'] == release.isoformat()


def test_episode_meeting_requires_my_streaming_vendor(app, user):
    today = local_today()
    with app.app_context():
        _link(user)
        _netflix(user)
        show = CachedMedia(
            media_type='show', trakt_id=77, title='The Boys', year=2024,
            overview='A crew takes on superheroes.', runtime=60,
            genres_json='["Action"]', network='Prime Video',
        )
        skipped = CachedMedia(
            media_type='show', trakt_id=78, title='Cable Only', year=2024,
        )
        db.session.add_all([show, skipped])
        db.session.flush()
        person = CachedPerson(trakt_id=501, name='Karl Urban')
        db.session.add(person)
        db.session.flush()
        db.session.add(MediaCastMember(
            cached_media_id=show.id,
            person_id=person.id,
            characters_json='["Billy Butcher"]',
            sort_order=0,
        ))
        _provider(show, 'Netflix')
        _provider(skipped, 'Hulu')
        db.session.add(UserMediaState(
            user_id=user, media_type='show', trakt_id=77, on_watchlist=True,
        ))
        db.session.add(UserMediaState(
            user_id=user, media_type='show', trakt_id=78, on_watchlist=True,
        ))
        db.session.add(UserCalendarEvent(
            user_id=user, media_type='show', trakt_id=77,
            event_date=today + timedelta(days=3),
            season_number=3, episode_number=5, episode_title='The Last Time',
        ))
        db.session.add(UserCalendarEvent(
            user_id=user, media_type='show', trakt_id=77,
            event_date=today - timedelta(days=2),
            season_number=3, episode_number=4, episode_title='Already aired',
        ))
        db.session.add(UserCalendarEvent(
            user_id=user, media_type='show', trakt_id=78,
            event_date=today + timedelta(days=1),
            season_number=1, episode_number=1, episode_title='Nope',
        ))
        db.session.commit()
        fake = FakeGoogle()
        sync_external_calendar(_user(user), client=fake)
        assert len(fake.inserted) == 1
        body = fake.inserted[0][2]
        assert 'The Boys' in body['summary']
        assert 'S03E05' in body['summary']
        assert 'The Last Time' in body['summary']
        assert 'Karl Urban as Billy Butcher' in body['description']
        assert 'On your streaming services: Netflix' in body['description']
        assert 'Already aired' not in body['summary']


def test_leaving_wishlist_removes_upcoming_meeting(app, user):
    today = local_today()
    with app.app_context():
        _link(user)
        _movie(42, 'Dune', today + timedelta(days=10), with_cast=False)
        state = UserMediaState(
            user_id=user, media_type='movie', trakt_id=42, on_watchlist=True,
        )
        db.session.add(state)
        db.session.commit()
        fake = FakeGoogle()
        sync_external_calendar(_user(user), client=fake)
        assert len(fake.inserted) == 1
        state.on_watchlist = False
        db.session.commit()
        sync_external_calendar(_user(user), client=fake)
        assert fake.deleted == [('cal-1', 'g1')]
        assert ExternalCalendarEvent.query.filter_by(user_id=user).count() == 0


def test_preferences_shows_calendar_setup(app, client, user):
    login_client(client, app, user)
    html = client.get('/preferences').get_data(as_text=True)
    assert 'Google Calendar' in html
    assert 'only for TV Tracker' in html
    assert 'not set up on this server' in html

    app.config['GOOGLE_CLIENT_ID'] = 'cid'
    app.config['GOOGLE_CLIENT_SECRET'] = 'secret'
    app.config['GOOGLE_CALENDAR_REDIRECT_URI'] = 'https://localhost:8300/auth/google/callback'
    html = client.get('/preferences').get_data(as_text=True)
    assert 'Connect Google account' in html

    resp = client.post('/auth/google/calendar', follow_redirects=False)
    assert resp.status_code == 302
    assert 'accounts.google.com' in resp.headers['Location']
    assert 'cid' in resp.headers['Location']
    assert 'select_account' in resp.headers['Location']


def test_google_callback_signs_the_user_back_in(app, client, user):
    """Returning from Google must not dump the user on the Trakt login page."""
    from datetime import datetime, timedelta
    from unittest.mock import patch

    from models import GoogleOAuthState

    with app.app_context():
        db.session.add(GoogleOAuthState(
            state='state-1',
            user_id=user,
            client_kind='web',
            expires_at=datetime.utcnow() + timedelta(minutes=10),
        ))
        db.session.commit()
    app.config['GOOGLE_CLIENT_ID'] = 'cid'
    app.config['GOOGLE_CLIENT_SECRET'] = 'secret'
    app.config['GOOGLE_CALENDAR_REDIRECT_URI'] = 'https://localhost:8300/auth/google/callback'
    fake = FakeGoogle()
    with patch(
        'services.google_calendar.exchange_code',
        return_value={'access_token': 'a', 'refresh_token': 'r', 'expires_in': 3600},
    ), patch(
        'services.google_calendar.fetch_email',
        return_value='nir.melamoud@gmail.com',
    ), patch(
        'services.external_calendar.load_client',
        return_value=fake,
    ):
        resp = client.get(
            '/auth/google/callback?state=state-1&code=xyz',
            follow_redirects=True,
        )
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert 'Login with TraktTV' not in html
    assert 'nir.melamoud@gmail.com' in html
    assert 'Use this calendar' in html
    assert 'Disconnect Google account' in html


def test_android_connect_returns_account_chooser(app, client, user):
    login_client(client, app, user)
    app.config['GOOGLE_CLIENT_ID'] = 'cid'
    app.config['GOOGLE_CLIENT_SECRET'] = 'secret'
    app.config['GOOGLE_CALENDAR_REDIRECT_URI'] = 'https://localhost:8300/auth/google/callback'
    resp = client.post('/api/v1/google-calendar/connect')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert 'accounts.google.com' in body['authorize_url']
    status = client.get('/api/v1/google-calendar').get_json()
    assert status['configured'] is True
    assert status['connected'] is False
    assert status['reminder_method'] == 'popup'
    assert status['reminder_amount'] == 1
    assert status['reminder_unit'] == 'days'


def test_sync_continues_when_one_google_call_fails(app, user):
    today = local_today()

    class FailPatch(FakeGoogle):
        def patch_event(self, calendar_id, event_id, body):
            raise GoogleCalendarError('Could not reach Google Calendar.')

    with app.app_context():
        _link(user)
        _movie(42, 'Dune', today + timedelta(days=40), with_cast=False)
        _movie(43, 'Arrival', today + timedelta(days=12), with_cast=False)
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=42, on_watchlist=True,
        ))
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=43, on_watchlist=True,
        ))
        db.session.add(ExternalCalendarEvent(
            user_id=user, media_type='movie', trakt_id=42, kind='theater',
            season_number=0, episode_number=0,
            event_date=today + timedelta(days=40),
            google_event_id='old-dune', calendar_id='cal-1',
            content_hash='stale',
        ))
        db.session.commit()
        fake = FailPatch()
        result = sync_external_calendar(_user(user), client=fake)
        assert result['created'] == 1
        assert result['updated'] == 0
        assert fake.inserted[0][2]['summary'].startswith('In theaters: Arrival')
        kept = ExternalCalendarEvent.query.filter_by(user_id=user, trakt_id=42).one()
        assert kept.google_event_id == 'old-dune'
        assert kept.content_hash == 'stale'


def test_default_reminder_is_popup_one_day_before(app, user):
    today = local_today()
    with app.app_context():
        _link(user)
        _movie(42, 'Dune', today + timedelta(days=40), with_cast=False)
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=42, on_watchlist=True,
        ))
        db.session.commit()
        fake = FakeGoogle()
        sync_external_calendar(_user(user), client=fake)
        assert fake.inserted[0][2]['reminders'] == {
            'useDefault': False,
            'overrides': [{'method': 'popup', 'minutes': 1440}],
        }


def test_changing_reminder_updates_the_meeting(app, user):
    today = local_today()
    with app.app_context():
        _link(user)
        _movie(42, 'Dune', today + timedelta(days=40), with_cast=False)
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=42, on_watchlist=True,
        ))
        db.session.commit()
        fake = FakeGoogle()
        sync_external_calendar(_user(user), client=fake)
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.calendar_reminder_method = 'email'
        prefs.calendar_reminder_minutes = 120
        db.session.commit()
        sync_external_calendar(_user(user), client=fake)
        assert fake.patched[0][2]['reminders'] == {
            'useDefault': False,
            'overrides': [{'method': 'email', 'minutes': 120}],
        }
        prefs.calendar_reminder_method = 'none'
        db.session.commit()
        sync_external_calendar(_user(user), client=fake)
        assert fake.patched[-1][2]['reminders'] == {
            'useDefault': False,
            'overrides': [],
        }


def test_preferences_saves_meeting_reminder(app, client, user):
    login_client(client, app, user)
    html = client.get('/preferences').get_data(as_text=True)
    assert 'Save reminder' in html
    assert 'Reminder for every meeting' in html
    saved = client.post('/auth/google/calendar/reminder', data={
        'reminder_method': 'email',
        'reminder_amount': '2',
        'reminder_unit': 'hours',
    })
    assert saved.status_code == 302
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        assert prefs.calendar_reminder_method == 'email'
        assert prefs.calendar_reminder_minutes == 120
    too_far = client.post('/auth/google/calendar/reminder', data={
        'reminder_method': 'popup',
        'reminder_amount': '40',
        'reminder_unit': 'days',
    })
    assert too_far.status_code == 302
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        assert prefs.calendar_reminder_minutes == 120
    api = client.post('/api/v1/google-calendar/reminder', json={
        'method': 'popup',
        'amount': 30,
        'unit': 'minutes',
    })
    assert api.status_code == 200
    assert api.get_json()['message'] == 'Popup, 30 minutes before'
