"""Auto media alerts: release day, new streaming, season/episode, prefs, admin."""

from datetime import date, datetime, timedelta
from unittest.mock import patch

from models import (
    AlertEvent,
    CachedMedia,
    Notification,
    User,
    UserListMembership,
    UserMediaState,
    UserPreference,
    db,
)
from services.alerts import (
    ALERT_EPISODE_AIRED,
    ALERT_NEW_STREAMING,
    ALERT_NEW_USER_LOGIN,
    ALERT_RELEASE_DAY,
    ALERT_SEASON_AIRED,
    notify_admins_new_user,
    run_media_alerts,
)
from tests.conftest import login_client


def _watchlist(user_id: int, media_type: str, trakt_id: int, *, watched=False):
    db.session.add(UserMediaState(
        user_id=user_id,
        media_type=media_type,
        trakt_id=trakt_id,
        on_watchlist=True,
        watched=watched,
    ))


def test_release_day_notifies_and_dedups(app, user):
    with app.app_context():
        media = CachedMedia(
            media_type='movie', trakt_id=9101, title='Out Today',
            released_at=date.today(), trakt_listed_at=datetime.utcnow(),
        )
        db.session.add(media)
        _watchlist(user, 'movie', 9101)
        db.session.commit()

        n1 = run_media_alerts(app)
        assert n1 >= 1
        notes = Notification.query.filter_by(user_id=user, alert_type=ALERT_RELEASE_DAY).all()
        assert len(notes) == 1
        assert 'Out Today' in notes[0].title

        n2 = run_media_alerts(app)
        assert n2 == 0
        assert Notification.query.filter_by(user_id=user, alert_type=ALERT_RELEASE_DAY).count() == 1


def test_release_day_skips_watched_movie(app, user):
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='movie', trakt_id=9102, title='Already Seen',
            released_at=date.today(),
        ))
        _watchlist(user, 'movie', 9102, watched=True)
        db.session.commit()
        assert run_media_alerts(app) == 0
        assert Notification.query.filter_by(user_id=user).count() == 0


def test_new_streaming_baselines_then_alerts_delta(app, user):
    with app.app_context():
        media = CachedMedia(
            media_type='movie', trakt_id=9201, title='Stream Me',
            tmdb_id=555, trakt_listed_at=datetime.utcnow(),
        )
        db.session.add(media)
        _watchlist(user, 'movie', 9201)
        db.session.commit()

        first = [
            {
                'provider_name': 'Netflix',
                'tmdb_provider_id': 8,
                'offer_type': 'flatrate',
                'region': 'US',
            }
        ]
        second = first + [
            {
                'provider_name': 'Hulu',
                'tmdb_provider_id': 15,
                'offer_type': 'flatrate',
                'region': 'US',
            }
        ]

        with patch('services.alerts.tmdb_configured', return_value=True), patch(
            'services.sync_jobs.tmdb_configured', return_value=True
        ), patch('services.sync_jobs.get_watch_providers', return_value=first):
            assert run_media_alerts(app) == 0  # baseline only

        assert Notification.query.filter_by(user_id=user, alert_type=ALERT_NEW_STREAMING).count() == 0
        assert AlertEvent.query.filter_by(
            user_id=user, alert_type=ALERT_NEW_STREAMING, payload_key='provider:Netflix'
        ).count() == 1

        with patch('services.alerts.tmdb_configured', return_value=True), patch(
            'services.sync_jobs.tmdb_configured', return_value=True
        ), patch('services.sync_jobs.get_watch_providers', return_value=second):
            created = run_media_alerts(app)

        assert created == 1
        notes = Notification.query.filter_by(user_id=user, alert_type=ALERT_NEW_STREAMING).all()
        assert len(notes) == 1
        assert 'Hulu' in notes[0].title


def test_pref_off_records_event_without_notification(app, user):
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.alert_release_day = False
        db.session.add(CachedMedia(
            media_type='movie', trakt_id=9301, title='Quiet Release',
            released_at=date.today(),
        ))
        _watchlist(user, 'movie', 9301)
        db.session.commit()

        run_media_alerts(app)
        assert Notification.query.filter_by(user_id=user).count() == 0
        assert AlertEvent.query.filter_by(
            user_id=user, alert_type=ALERT_RELEASE_DAY
        ).count() == 1


def test_season_drop_one_alert(app, user):
    with app.app_context():
        media = CachedMedia(
            media_type='show', trakt_id=9401, title='Binge Show',
            tmdb_id=777, trakt_listed_at=datetime.utcnow(),
        )
        db.session.add(media)
        _watchlist(user, 'show', 9401)
        db.session.commit()

        drop_day = date.today().isoformat()
        seasons_baseline = [{
            'number': 1,
            'episodes': [
                {'number': 1, 'title': 'A', 'first_aired': '2020-01-01T00:00:00.000Z'},
                {'number': 2, 'title': 'B', 'first_aired': '2020-01-08T00:00:00.000Z'},
            ],
        }]
        seasons_new = seasons_baseline + [{
            'number': 2,
            'episodes': [
                {'number': 1, 'title': 'C', 'first_aired': f'{drop_day}T08:00:00.000Z'},
                {'number': 2, 'title': 'D', 'first_aired': f'{drop_day}T08:00:00.000Z'},
                {'number': 3, 'title': 'E', 'first_aired': f'{drop_day}T08:00:00.000Z'},
            ],
        }]

        with patch('services.alerts.tmdb_configured', return_value=False), patch(
            'services.alerts.trakt_client.get_show_seasons', return_value=seasons_baseline
        ):
            run_media_alerts(app)  # baseline

        with patch('services.alerts.tmdb_configured', return_value=False), patch(
            'services.alerts.trakt_client.get_show_seasons', return_value=seasons_new
        ):
            created = run_media_alerts(app)

        assert created == 1
        season_notes = Notification.query.filter_by(
            user_id=user, alert_type=ALERT_SEASON_AIRED
        ).all()
        assert len(season_notes) == 1
        assert 'Season 2' in season_notes[0].title
        assert Notification.query.filter_by(
            user_id=user, alert_type=ALERT_EPISODE_AIRED
        ).count() == 0


def test_episode_alert_weekly(app, user):
    with app.app_context():
        media = CachedMedia(
            media_type='show', trakt_id=9501, title='Weekly Show',
            trakt_listed_at=datetime.utcnow(),
        )
        db.session.add(media)
        db.session.add(UserListMembership(
            user_id=user, list_id='99', media_type='show', trakt_id=9501,
        ))
        db.session.commit()

        d1 = (date.today() - timedelta(days=7)).isoformat()
        d2 = date.today().isoformat()
        baseline = [{
            'number': 1,
            'episodes': [
                {'number': 1, 'title': 'Pilot', 'first_aired': f'{d1}T00:00:00.000Z'},
            ],
        }]
        after = [{
            'number': 1,
            'episodes': [
                {'number': 1, 'title': 'Pilot', 'first_aired': f'{d1}T00:00:00.000Z'},
                {'number': 2, 'title': 'Next', 'first_aired': f'{d2}T00:00:00.000Z'},
            ],
        }]

        with patch('services.alerts.tmdb_configured', return_value=False), patch(
            'services.alerts.trakt_client.get_show_seasons', return_value=baseline
        ):
            run_media_alerts(app)

        with patch('services.alerts.tmdb_configured', return_value=False), patch(
            'services.alerts.trakt_client.get_show_seasons', return_value=after
        ):
            created = run_media_alerts(app)

        assert created == 1
        note = Notification.query.filter_by(
            user_id=user, alert_type=ALERT_EPISODE_AIRED
        ).one()
        assert 'S01E02' in note.message


def test_notify_admins_new_user(app, admin_user, user):
    with app.app_context():
        # `user` fixture is a normal account; treat as newly created for the alert.
        new_user = db.session.get(User, user)
        count = notify_admins_new_user(new_user)
        assert count == 1
        note = Notification.query.filter_by(
            user_id=admin_user, alert_type=ALERT_NEW_USER_LOGIN
        ).one()
        assert new_user.username in note.title

        # Dedup
        assert notify_admins_new_user(new_user) == 0


def test_admin_run_alert_check(app, client, admin_user):
    login_client(client, app, admin_user)
    resp = client.post('/admin/run-release-check', follow_redirects=True)
    assert resp.status_code == 200
    assert b'Alert check finished' in resp.data


def test_preferences_alert_toggles(app, client, user):
    login_client(client, app, user)
    get = client.get('/preferences')
    assert get.status_code == 200
    assert b'Added to a streaming service' in get.data

    resp = client.post('/preferences', data={
        'alerts_prefs_present': '1',
        # omit checkboxes → all off
        'lists_prefs_present': '0',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        assert prefs.alert_release_day is False
        assert prefs.alert_new_streaming is False
        assert prefs.alert_episode_aired is False
