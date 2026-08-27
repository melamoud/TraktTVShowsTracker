"""Auto media alerts: release day, new streaming, season/episode, prefs, admin."""

from datetime import date, datetime, timedelta
from unittest.mock import patch

from models import (
    AlertEvent,
    CachedMedia,
    CachedPerson,
    MediaCastMember,
    Notification,
    User,
    UserCalendarEvent,
    UserFavoriteActor,
    UserListMembership,
    UserMediaState,
    UserPreference,
    db,
)
from services.alerts import (
    ALERT_EPISODE_AIRED,
    ALERT_FAVORITE_ACTOR,
    ALERT_LIST_ADD,
    ALERT_NEW_STREAMING,
    ALERT_SEASON_STREAMING,
    ALERT_NEW_USER_LOGIN,
    ALERT_RELEASE_DAY,
    ALERT_SEASON_AIRED,
    normalize_streaming_provider_key,
    notify_admins_new_user,
    notify_lists_added,
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


def test_alert_refresh_marks_watched_movie_release_read(app, user):
    """Unread movie release alert clears on next run after the movie is watched."""
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='movie', trakt_id=9103, title='Watch Me',
            released_at=date.today(),
        ))
        _watchlist(user, 'movie', 9103, watched=False)
        db.session.commit()

        with patch('services.alerts.ensure_user_calendar_fresh'), \
             patch('services.sync_jobs.sync_user_media_state', return_value=True):
            assert run_media_alerts(app) >= 1
        note = Notification.query.filter_by(
            user_id=user, alert_type=ALERT_RELEASE_DAY, trakt_id=9103,
        ).one()
        assert note.is_read is False
        assert note.payload_key and note.payload_key.startswith('release:')

        st = UserMediaState.query.filter_by(
            user_id=user, media_type='movie', trakt_id=9103,
        ).one()
        st.watched = True
        db.session.commit()

        with patch('services.alerts.ensure_user_calendar_fresh'), \
             patch('services.sync_jobs.sync_user_media_state', return_value=True):
            assert run_media_alerts(app) == 0
        assert db.session.get(Notification, note.id).is_read is True


def test_alert_refresh_marks_watched_episode_read(app, user):
    """Unread episode alert clears on next run after that episode is watched."""
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show', trakt_id=9301, title='Weekly Show',
        ))
        _watchlist(user, 'show', 9301)
        db.session.add(Notification(
            user_id=user,
            alert_type=ALERT_EPISODE_AIRED,
            title='New episode: Weekly Show',
            message='S02E04 — Cliff · aired 2026-08-12',
            media_type='show',
            trakt_id=9301,
            payload_key='ep:2:4',
            is_read=False,
        ))
        db.session.add(Notification(
            user_id=user,
            alert_type=ALERT_EPISODE_AIRED,
            title='New episode: Weekly Show',
            message='S02E05 — Still Open · aired 2026-08-13',
            media_type='show',
            trakt_id=9301,
            payload_key='ep:2:5',
            is_read=False,
        ))
        db.session.commit()

        progress = {
            'seasons': [{
                'number': 2,
                'episodes': [
                    {'number': 4, 'completed': True, 'last_watched_at': '2026-08-13T01:00:00.000Z'},
                    {'number': 5, 'completed': False},
                ],
            }],
        }
        with patch('services.alerts.ensure_user_calendar_fresh'), \
             patch('services.alerts.trakt_client.get_show_progress', return_value=progress), \
             patch('services.alerts.alert_collection_trakt_ids', return_value=set()):
            run_media_alerts(app)

        notes = {
            n.payload_key: n
            for n in Notification.query.filter_by(user_id=user, trakt_id=9301).all()
        }
        assert notes['ep:2:4'].is_read is True
        assert notes['ep:2:5'].is_read is False


def test_progress_watch_marks_episode_alert_read_immediately(app, client, user):
    """Progress Watch button clears the matching episode alert without a refresh."""
    from services.alerts import mark_episode_alerts_read

    with app.app_context():
        db.session.add(Notification(
            user_id=user,
            alert_type=ALERT_EPISODE_AIRED,
            title='New episode: Show',
            message='S01E02 — Two · aired 2026-08-12',
            media_type='show',
            trakt_id=4401,
            payload_key='ep:1:2',
            is_read=False,
        ))
        db.session.add(Notification(
            user_id=user,
            alert_type=ALERT_EPISODE_AIRED,
            title='New episode: Show',
            message='S01E03 — Three · aired 2026-08-13',
            media_type='show',
            trakt_id=4401,
            payload_key='ep:1:3',
            is_read=False,
        ))
        db.session.commit()

        assert mark_episode_alerts_read(db.session.get(User, user), 4401, 1, 2) == 1
        notes = {
            n.payload_key: n.is_read
            for n in Notification.query.filter_by(user_id=user, trakt_id=4401).all()
        }
        assert notes['ep:1:2'] is True
        assert notes['ep:1:3'] is False

    login_client(client, app, user)
    with patch('routes.user_routes.trakt_client.mark_episode_watched', return_value={'added': {'episodes': 1}}):
        resp = client.post(
            '/api/episode/watched',
            json={
                'ids': {'trakt': 99},
                'action': 'add',
                'show_trakt_id': 4401,
                'season': 1,
                'episode': 3,
            },
        )
    assert resp.status_code == 200
    with app.app_context():
        note = Notification.query.filter_by(
            user_id=user, trakt_id=4401, payload_key='ep:1:3',
        ).one()
        assert note.is_read is True


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
            user_id=user, alert_type=ALERT_NEW_STREAMING, payload_key='provider:netflix'
        ).count() == 1

        with patch('services.alerts.tmdb_configured', return_value=True), patch(
            'services.sync_jobs.tmdb_configured', return_value=True
        ), patch('services.sync_jobs.get_watch_providers', return_value=second):
            created = run_media_alerts(app)

        assert created == 1
        notes = Notification.query.filter_by(user_id=user, alert_type=ALERT_NEW_STREAMING).all()
        assert len(notes) == 1
        assert 'Hulu' in (notes[0].message or '') or 'Hulu' in (notes[0].title or '')
        notes[0].is_read = True
        db.session.commit()

        third = second + [
            {
                'provider_name': 'Disney Plus',
                'tmdb_provider_id': 337,
                'offer_type': 'flatrate',
                'region': 'US',
            }
        ]
        with patch('services.alerts.tmdb_configured', return_value=True), patch(
            'services.sync_jobs.tmdb_configured', return_value=True
        ), patch('services.sync_jobs.get_watch_providers', return_value=third):
            created = run_media_alerts(app)
        assert created == 1
        notes = Notification.query.filter_by(user_id=user, alert_type=ALERT_NEW_STREAMING).all()
        assert len(notes) == 1
        assert notes[0].is_read is False
        assert 'Disney' in (notes[0].message or '')


def test_normalize_streaming_provider_key_collapses_channels():
    assert normalize_streaming_provider_key('Paramount Plus Apple TV Channel ') == 'paramount plus'
    assert normalize_streaming_provider_key('Paramount Plus Apple TV channel') == 'paramount plus'
    assert normalize_streaming_provider_key('Paramount Plus Premium') == 'paramount plus'
    assert normalize_streaming_provider_key('Paramount+ Roku Premium Channel') == 'paramount plus'
    assert normalize_streaming_provider_key('Starz Apple TV channel') == 'starz'
    assert normalize_streaming_provider_key('HBO Max Amazon Channel') == 'max'
    assert normalize_streaming_provider_key('Netflix') == 'netflix'


def test_streaming_channel_rename_does_not_realert(app, user):
    """TMDB channel/tier renames must not fire another Now-on alert."""
    with app.app_context():
        media = CachedMedia(
            media_type='show', trakt_id=300597, title='Red Alert',
            tmdb_id=301809, trakt_listed_at=datetime.utcnow(),
        )
        db.session.add(media)
        _watchlist(user, 'show', 300597)
        db.session.commit()

        first = [{
            'provider_name': 'Paramount Plus Apple TV Channel ',
            'tmdb_provider_id': 1853,
            'offer_type': 'flatrate',
            'region': 'US',
        }]
        renamed = [{
            'provider_name': 'Paramount Plus Apple TV channel',
            'tmdb_provider_id': 1853,
            'offer_type': 'flatrate',
            'region': 'US',
        }, {
            'provider_name': 'Paramount Plus Premium',
            'tmdb_provider_id': 2303,
            'offer_type': 'flatrate',
            'region': 'US',
        }]

        with patch('services.alerts.tmdb_configured', return_value=True), patch(
            'services.sync_jobs.tmdb_configured', return_value=True
        ), patch('services.sync_jobs.get_watch_providers', return_value=first), patch(
            'services.tmdb_client.get_season_watch_providers', return_value=[],
        ):
            assert run_media_alerts(app) == 0

        with patch('services.alerts.tmdb_configured', return_value=True), patch(
            'services.sync_jobs.tmdb_configured', return_value=True
        ), patch('services.sync_jobs.get_watch_providers', return_value=renamed), patch(
            'services.tmdb_client.get_season_watch_providers', return_value=[],
        ):
            assert run_media_alerts(app) == 0

        assert Notification.query.filter_by(
            user_id=user, alert_type=ALERT_NEW_STREAMING,
        ).count() == 0


def test_season_streaming_alerts_recent_season(app, user):
    """A season that just aired on a service gets one Season-on-stream card."""
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show', trakt_id=1401, title='Fauda', tmdb_id=77,
        ))
        _watchlist(user, 'show', 1401)
        db.session.add(UserCalendarEvent(
            user_id=user, media_type='show', trakt_id=1401,
            event_date=date.today(), season_number=5, episode_number=1,
            episode_title='The beginning',
        ))
        db.session.commit()
        season_providers = [
            {'provider_name': 'Netflix', 'offer_type': 'flatrate', 'region': 'US'},
        ]
        with patch('services.alerts.tmdb_configured', return_value=True), \
             patch('services.sync_jobs.tmdb_configured', return_value=True), \
             patch('services.sync_jobs.get_watch_providers', return_value=[]), \
             patch(
                 'services.tmdb_client.get_season_watch_providers',
                 return_value=season_providers,
             ), \
             patch('services.alerts.ensure_user_calendar_fresh', return_value=True):
            run_media_alerts(app)
        note = Notification.query.filter_by(
            user_id=user, alert_type=ALERT_SEASON_STREAMING,
        ).one()
        assert note.payload_key == 'seasonstream:5'
        assert 'Netflix' in note.message
        assert note.is_read is False


def test_season_streaming_new_vendor_after_baseline(app, user):
    """Old season is baselined silently; a later vendor marks the card unread."""
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show', trakt_id=1401, title='Fauda', tmdb_id=77,
        ))
        _watchlist(user, 'show', 1401)
        db.session.add(UserCalendarEvent(
            user_id=user, media_type='show', trakt_id=1401,
            event_date=date.today() - timedelta(days=40),
            season_number=5, episode_number=1,
        ))
        db.session.commit()
        prime = [{'provider_name': 'Prime Video', 'offer_type': 'flatrate'}]
        both = prime + [{'provider_name': 'Netflix', 'offer_type': 'flatrate'}]
        with patch('services.alerts.tmdb_configured', return_value=True), \
             patch('services.sync_jobs.tmdb_configured', return_value=True), \
             patch('services.sync_jobs.get_watch_providers', return_value=[]), \
             patch(
                 'services.tmdb_client.get_season_watch_providers',
                 return_value=prime,
             ), \
             patch('services.alerts.ensure_user_calendar_fresh', return_value=True):
            run_media_alerts(app)
        assert Notification.query.filter_by(
            user_id=user, alert_type=ALERT_SEASON_STREAMING,
        ).count() == 0

        with patch('services.alerts.tmdb_configured', return_value=True), \
             patch('services.sync_jobs.tmdb_configured', return_value=True), \
             patch('services.sync_jobs.get_watch_providers', return_value=[]), \
             patch(
                 'services.tmdb_client.get_season_watch_providers',
                 return_value=both,
             ), \
             patch('services.alerts.ensure_user_calendar_fresh', return_value=True):
            created = run_media_alerts(app)
        assert created == 1
        note = Notification.query.filter_by(
            user_id=user, alert_type=ALERT_SEASON_STREAMING,
        ).one()
        assert 'Netflix' in note.message
        assert note.is_read is False


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
        # List-only (not watchlisted/watched) → per-show fallback path.
        db.session.add(UserListMembership(
            user_id=user, list_id='55', media_type='show', trakt_id=9401,
        ))
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.alert_enabled_list_ids_json = '["55"]'
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

        with patch('services.alerts.ensure_user_calendar_fresh', return_value=True), \
             patch('services.alerts.tmdb_configured', return_value=False), patch(
            'services.alerts.trakt_client.get_show_seasons', return_value=seasons_baseline
        ):
            run_media_alerts(app)  # baseline

        with patch('services.alerts.ensure_user_calendar_fresh', return_value=True), \
             patch('services.alerts.tmdb_configured', return_value=False), patch(
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
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.alert_enabled_list_ids_json = '["99"]'
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

        with patch('services.alerts.ensure_user_calendar_fresh', return_value=True), \
             patch('services.alerts.tmdb_configured', return_value=False), patch(
            'services.alerts.trakt_client.get_show_seasons', return_value=baseline
        ):
            run_media_alerts(app)

        with patch('services.alerts.ensure_user_calendar_fresh', return_value=True), \
             patch('services.alerts.tmdb_configured', return_value=False), patch(
            'services.alerts.trakt_client.get_show_seasons', return_value=after
        ):
            created = run_media_alerts(app)

        assert created == 1
        note = Notification.query.filter_by(
            user_id=user, alert_type=ALERT_EPISODE_AIRED
        ).one()
        assert 'S01E02' in note.message


def test_first_pass_alerts_recent_episode(app, user):
    """First-ever scan must still alert episodes inside the grace window."""
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show', trakt_id=9601, title='Silo',
            trakt_listed_at=datetime.utcnow(),
        ))
        # List-only membership → per-show fallback path.
        db.session.add(UserListMembership(
            user_id=user, list_id='55', media_type='show', trakt_id=9601,
        ))
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.alert_enabled_list_ids_json = '["55"]'
        db.session.commit()

        today = date.today().isoformat()
        old = (date.today() - timedelta(days=30)).isoformat()
        seasons = [{
            'number': 3,
            'episodes': [
                {'number': 1, 'title': 'Old', 'first_aired': f'{old}T00:00:00.000Z'},
                {'number': 2, 'title': 'Today Ep', 'first_aired': f'{today}T08:00:00.000Z'},
            ],
        }]
        with patch('services.alerts.ensure_user_calendar_fresh', return_value=True), \
             patch('services.alerts.tmdb_configured', return_value=False), patch(
            'services.alerts.trakt_client.get_show_seasons', return_value=seasons
        ):
            created = run_media_alerts(app)

        assert created == 1
        note = Notification.query.filter_by(
            user_id=user, alert_type=ALERT_EPISODE_AIRED
        ).one()
        assert 'Silo' in note.title
        assert 'S03E02' in note.message
        # Old episode recorded silently, never alerts later.
        assert AlertEvent.query.filter_by(
            user_id=user, alert_type=ALERT_EPISODE_AIRED, payload_key='ep:3:1'
        ).count() == 1


def test_calendar_event_alerts_without_per_show_fetch(app, user):
    """Watchlisted show with an in-window calendar row alerts via the bulk path."""
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show', trakt_id=9901, title='Cal Show',
            trakt_listed_at=datetime.utcnow(),
        ))
        _watchlist(user, 'show', 9901)
        db.session.add(UserCalendarEvent(
            user_id=user, media_type='show', trakt_id=9901,
            event_date=date.today(), season_number=3, episode_number=8,
            episode_title='Fresh Episode',
        ))
        db.session.commit()

        with patch('services.alerts.ensure_user_calendar_fresh', return_value=True), \
             patch('services.alerts.tmdb_configured', return_value=False), \
             patch('services.alerts.trakt_client.get_show_progress', return_value={}), \
             patch('services.alerts.trakt_client.get_show_seasons'):
            created = run_media_alerts(app)

        assert created == 1
        # Last-aired cache may fetch seasons for today's timed air; the alert
        # itself still came from the calendar row (no per-show episode scan).
        note = Notification.query.filter_by(
            user_id=user, alert_type=ALERT_EPISODE_AIRED
        ).one()
        assert 'Cal Show' in note.title
        assert 'S03E08' in note.message


def test_calendar_same_day_cluster_confirms_season_drop(app, user):
    """>=2 same-day episodes of one season confirm via one Trakt call."""
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show', trakt_id=9902, title='Drop Show',
            trakt_listed_at=datetime.utcnow(),
        ))
        _watchlist(user, 'show', 9902)
        today = date.today()
        for ep in (1, 2, 3):
            db.session.add(UserCalendarEvent(
                user_id=user, media_type='show', trakt_id=9902,
                event_date=today, season_number=2, episode_number=ep,
                episode_title=f'E{ep}',
            ))
        db.session.commit()

        day = today.isoformat()
        seasons = [{
            'number': 2,
            'episodes': [
                {'number': n, 'title': f'E{n}', 'first_aired': f'{day}T08:00:00.000Z'}
                for n in (1, 2, 3)
            ],
        }]
        with patch('services.alerts.ensure_user_calendar_fresh', return_value=True), \
             patch('services.alerts.tmdb_configured', return_value=False), \
             patch('services.alerts.trakt_client.get_show_seasons', return_value=seasons):
            created = run_media_alerts(app)

        assert created == 1
        note = Notification.query.filter_by(
            user_id=user, alert_type=ALERT_SEASON_AIRED
        ).one()
        assert 'Season 2' in note.title
        assert Notification.query.filter_by(
            user_id=user, alert_type=ALERT_EPISODE_AIRED
        ).count() == 0


def test_partial_same_day_drop_alerts_per_episode(app, user):
    """Same-day cluster with later unaired eps is weekly/partial — not season drop."""
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show', trakt_id=9905, title='Reacher-like',
            trakt_listed_at=datetime.utcnow(),
        ))
        # Stale "caught up" cache that used to block all alerts.
        _watchlist(user, 'show', 9905, watched=True)
        st = UserMediaState.query.filter_by(
            user_id=user, media_type='show', trakt_id=9905,
        ).one()
        st.progress_percent = 100.0
        st.episodes_aired = 24
        st.episodes_completed = 24
        st.progress_detail_at = datetime.utcnow() - timedelta(days=30)
        today = date.today()
        for ep in (1, 2, 3):
            db.session.add(UserCalendarEvent(
                user_id=user, media_type='show', trakt_id=9905,
                event_date=today, season_number=4, episode_number=ep,
                episode_title=f'E{ep}',
            ))
        db.session.commit()

        day = today.isoformat()
        future = (today + timedelta(days=7)).isoformat()
        seasons = [{
            'number': 4,
            'episodes': [
                {'number': 1, 'title': 'E1', 'first_aired': f'{day}T08:00:00.000Z'},
                {'number': 2, 'title': 'E2', 'first_aired': f'{day}T08:00:00.000Z'},
                {'number': 3, 'title': 'E3', 'first_aired': f'{day}T08:00:00.000Z'},
                {'number': 4, 'title': 'E4', 'first_aired': f'{future}T08:00:00.000Z'},
            ],
        }]
        with patch('services.alerts.ensure_user_calendar_fresh', return_value=True), \
             patch('services.alerts.tmdb_configured', return_value=False), \
             patch('services.alerts.trakt_client.get_show_seasons', return_value=seasons):
            created = run_media_alerts(app)

        assert created == 3
        assert Notification.query.filter_by(
            user_id=user, alert_type=ALERT_SEASON_AIRED
        ).count() == 0
        assert Notification.query.filter_by(
            user_id=user, alert_type=ALERT_EPISODE_AIRED
        ).count() == 3


def test_is_finished_ignores_stale_percent_without_detail(app, user):
    from services.alerts import is_finished

    with app.app_context():
        _watchlist(user, 'show', 9906, watched=True)
        st = UserMediaState.query.filter_by(
            user_id=user, media_type='show', trakt_id=9906,
        ).one()
        st.progress_percent = 100.0
        st.progress_detail_at = None
        db.session.commit()
        assert is_finished(user, 'show', 9906) is False

        st.episodes_aired = 27
        st.episodes_completed = 24
        st.progress_detail_at = datetime.utcnow()
        st.progress_percent = 88.9
        db.session.commit()
        assert is_finished(user, 'show', 9906) is False

        st.episodes_completed = 27
        st.progress_percent = 100.0
        db.session.commit()
        assert is_finished(user, 'show', 9906) is True


def test_calendar_ignores_events_older_than_grace(app, user):
    """Calendar rows older than the grace window never alert."""
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show', trakt_id=9903, title='Old Cal Show',
            trakt_listed_at=datetime.utcnow(),
        ))
        _watchlist(user, 'show', 9903)
        db.session.add(UserCalendarEvent(
            user_id=user, media_type='show', trakt_id=9903,
            event_date=date.today() - timedelta(days=9), season_number=1,
            episode_number=4, episode_title='Old Ep',
        ))
        db.session.commit()

        with patch('services.alerts.ensure_user_calendar_fresh', return_value=True), \
             patch('services.alerts.tmdb_configured', return_value=False):
            assert run_media_alerts(app) == 0
        assert Notification.query.filter_by(user_id=user).count() == 0


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
    assert b'New season on a streaming service' in get.data
    assert b'Added to a list' in get.data
    assert b'New title with a favorite actor' in get.data

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
        assert prefs.alert_season_streaming is False
        assert prefs.alert_episode_aired is False
        assert prefs.alert_list_add is False
        assert prefs.alert_favorite_actor is False


def test_notify_lists_added_creates_alert(app, user):
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show', trakt_id=8801, title='Lanterns',
            trakt_listed_at=datetime.utcnow(),
        ))
        db.session.commit()
        u = db.session.get(User, user)
        assert notify_lists_added(
            u, 'show', 8801, ['Wishlist', 'Keepers'],
            list_ids=['watchlist', '55'],
        ) is True
        db.session.commit()
        note = Notification.query.filter_by(
            user_id=user, alert_type=ALERT_LIST_ADD,
        ).one()
        assert note.title == 'Lanterns'
        assert 'Wishlist' in note.message and 'Keepers' in note.message
        assert note.media_type == 'show'
        assert note.trakt_id == 8801


def test_notify_lists_added_respects_pref_off(app, user):
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.alert_list_add = False
        db.session.commit()
        u = db.session.get(User, user)
        assert notify_lists_added(u, 'movie', 12, ['Wishlist']) is False
        assert Notification.query.filter_by(
            user_id=user, alert_type=ALERT_LIST_ADD,
        ).count() == 0


def test_show_premiere_gets_episode_alert_not_release_day(app, user):
    """Shows never get release_day - S01E01 episode alert covers the premiere."""
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show', trakt_id=9950, title='Fresh Show',
            released_at=date.today(),  # premieres today
            trakt_listed_at=datetime.utcnow(),
        ))
        _watchlist(user, 'show', 9950)
        db.session.add(UserCalendarEvent(
            user_id=user, media_type='show', trakt_id=9950,
            event_date=date.today(), season_number=1, episode_number=1,
            episode_title='Pilot',
        ))
        db.session.commit()

        with patch('services.alerts.ensure_user_calendar_fresh', return_value=True), \
             patch('services.alerts.tmdb_configured', return_value=False):
            created = run_media_alerts(app)

        assert created == 1
        assert Notification.query.filter_by(
            user_id=user, alert_type=ALERT_RELEASE_DAY
        ).count() == 0
        note = Notification.query.filter_by(
            user_id=user, alert_type=ALERT_EPISODE_AIRED
        ).one()
        assert 'S01E01' in note.message


def test_movie_release_and_streaming_alerts_both_fire(app, user):
    """Movies keep release-day AND new-streaming alerts."""
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='movie', trakt_id=9960, title='Movie Night',
            released_at=date.today(), tmdb_id=555,
        ))
        _watchlist(user, 'movie', 9960)
        db.session.commit()

        with patch('services.alerts.tmdb_configured', return_value=True), patch(
            'services.sync_jobs.tmdb_configured', return_value=True
        ), patch('services.sync_jobs.get_watch_providers', return_value=[
            {'provider_name': 'Netflix', 'offer_type': 'flatrate'},
        ]):
            run_media_alerts(app)  # streaming baseline + release alert
        assert Notification.query.filter_by(
            user_id=user, alert_type=ALERT_RELEASE_DAY
        ).count() == 1

        with patch('services.alerts.tmdb_configured', return_value=True), patch(
            'services.sync_jobs.tmdb_configured', return_value=True
        ), patch('services.sync_jobs.get_watch_providers', return_value=[
            {'provider_name': 'Netflix', 'offer_type': 'flatrate'},
            {'provider_name': 'Hulu', 'offer_type': 'flatrate'},
        ]):
            run_media_alerts(app)

        assert Notification.query.filter_by(
            user_id=user, alert_type=ALERT_NEW_STREAMING
        ).count() == 1


def test_alerts_skip_titles_only_on_disabled_lists(app, user):
    """Default alert lists = Wishlist only; park-list titles stay quiet."""
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='movie', trakt_id=9201, title='Parked Film',
            released_at=date.today(),
        ))
        db.session.add(CachedMedia(
            media_type='movie', trakt_id=9202, title='Wishlist Film',
            released_at=date.today(),
        ))
        db.session.add(UserListMembership(
            user_id=user, list_id='99', media_type='movie', trakt_id=9201,
        ))
        _watchlist(user, 'movie', 9202)
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.alert_enabled_list_ids_json = '["watchlist"]'
        db.session.commit()

        with patch('services.alerts.ensure_user_calendar_fresh'):
            run_media_alerts(app)

        titles = {
            n.title for n in Notification.query.filter_by(
                user_id=user, alert_type=ALERT_RELEASE_DAY,
            ).all()
        }
        assert any('Wishlist Film' in t for t in titles)
        assert not any('Parked Film' in t for t in titles)

        prefs.alert_enabled_list_ids_json = '["watchlist", "99"]'
        db.session.commit()
        with patch('services.alerts.ensure_user_calendar_fresh'):
            run_media_alerts(app)
        titles = {
            n.title for n in Notification.query.filter_by(
                user_id=user, alert_type=ALERT_RELEASE_DAY,
            ).all()
        }
        assert any('Parked Film' in t for t in titles)


def test_calendar_upsert_does_not_stamp_episode_date_on_show(app):
    """Calendar entries carry the EPISODE first_aired at item level - the show
    row must keep its real premiere date, else release_day fires per episode."""
    from services.sync_jobs import upsert_cached_media

    with app.app_context():
        upsert_cached_media('show', {
            'first_aired': '2026-08-07T00:00:00.000Z',  # episode air date
            'show': {
                'ids': {'trakt': 9970},
                'title': 'Polluted Show',
                'first_aired': '2023-05-05T00:00:00.000Z',
            },
            'episode': {'season': 3, 'number': 6},
        })
        db.session.commit()
        row = CachedMedia.query.filter_by(media_type='show', trakt_id=9970).one()
        assert row.released_at == date(2023, 5, 5)


def test_show_release_date_only_moves_earlier(app):
    """Premiere dates never move later; an earlier entity date self-heals."""
    from services.sync_jobs import upsert_cached_media

    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show', trakt_id=9971, title='Healed Show',
            released_at=date(2026, 8, 7),  # previously polluted by an episode
        ))
        db.session.commit()

        upsert_cached_media('show', {
            'ids': {'trakt': 9971},
            'title': 'Healed Show',
            'first_aired': '2026-08-20T00:00:00.000Z',  # later: ignored
        })
        upsert_cached_media('show', {
            'ids': {'trakt': 9971},
            'title': 'Healed Show',
            'first_aired': '2023-05-05T00:00:00.000Z',  # real premiere: heals
        })
        db.session.commit()
        row = CachedMedia.query.filter_by(media_type='show', trakt_id=9971).one()
        assert row.released_at == date(2023, 5, 5)


def test_rate_limited_calendar_skips_per_show_fallback(app, user):
    """A 429 on the bulk calendar call must NOT trigger per-show scans."""
    from services.trakt_client import TraktError

    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show', trakt_id=9980, title='Throttled Show',
            trakt_listed_at=datetime.utcnow(),
        ))
        db.session.add(UserListMembership(
            user_id=user, list_id='55', media_type='show', trakt_id=9980,
        ))
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.alert_enabled_list_ids_json = '["55"]'
        db.session.commit()

        with patch(
            'services.alerts.ensure_user_calendar_fresh',
            side_effect=TraktError('Trakt API error on /calendars/my (429)', 429),
        ), patch(
            'services.alerts.trakt_client.get_show_seasons'
        ) as get_seasons:
            run_media_alerts(app)

        get_seasons.assert_not_called()


def test_rate_limit_mid_fallback_stops_remaining_scans(app, user):
    """A 429 from one per-show fetch stops the rest of the fallback loop."""
    from services.trakt_client import TraktError

    with app.app_context():
        for tid in (9981, 9982):
            db.session.add(CachedMedia(
                media_type='show', trakt_id=tid, title=f'Show {tid}',
                trakt_listed_at=datetime.utcnow(),
            ))
            db.session.add(UserListMembership(
                user_id=user, list_id='55', media_type='show', trakt_id=tid,
            ))
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.alert_enabled_list_ids_json = '["55"]'
        db.session.commit()

        with patch('services.alerts.ensure_user_calendar_fresh', return_value=True), \
             patch('services.alerts.tmdb_configured', return_value=False), patch(
            'services.alerts.trakt_client.get_show_seasons',
            side_effect=TraktError('429', 429),
        ) as get_seasons:
            run_media_alerts(app)

        assert get_seasons.call_count == 1


def _seed_favorite_actor_catalog(user_id, *, listed_at, favorited_at, on_list=False, watched=False,
                                 cast_fetched=True):
    person = CachedPerson(trakt_id=501, name='Lior Raz', slug='lior-raz')
    media = CachedMedia(
        media_type='movie', trakt_id=7701, title='Fauda Film',
        trakt_listed_at=listed_at,
        cast_fetched_at=datetime.utcnow() if cast_fetched else None,
    )
    db.session.add_all([person, media])
    db.session.flush()
    db.session.add(UserFavoriteActor(
        user_id=user_id, person_id=person.id, created_at=favorited_at,
    ))
    if cast_fetched:
        db.session.add(MediaCastMember(
            cached_media_id=media.id, person_id=person.id, sort_order=0,
        ))
    if on_list or watched:
        db.session.add(UserMediaState(
            user_id=user_id, media_type='movie', trakt_id=7701,
            on_watchlist=on_list, watched=watched,
        ))
    db.session.commit()
    return person, media


def test_favorite_actor_notifies_new_catalog_title(app, user):
    """Ingested title with a favorite actor creates one alert; second run is a no-op."""
    with app.app_context():
        _seed_favorite_actor_catalog(
            user,
            listed_at=datetime.utcnow(),
            favorited_at=datetime.utcnow() - timedelta(days=10),
        )
        with patch('services.alerts.ensure_user_calendar_fresh', return_value=True), \
             patch('services.alerts.tmdb_configured', return_value=False), \
             patch('services.trakt_client.fetch_media_people') as fetch_people:
            created = run_media_alerts(app)
        assert created == 1
        fetch_people.assert_not_called()
        note = Notification.query.filter_by(
            user_id=user, alert_type=ALERT_FAVORITE_ACTOR,
        ).one()
        assert note.title == 'Fauda Film'
        assert 'Lior Raz' in note.message
        assert note.payload_key == 'favactor'
        with patch('services.alerts.ensure_user_calendar_fresh', return_value=True), \
             patch('services.alerts.tmdb_configured', return_value=False), \
             patch('services.trakt_client.fetch_media_people') as fetch_people:
            assert run_media_alerts(app) == 0
        fetch_people.assert_not_called()
        assert Notification.query.filter_by(
            user_id=user, alert_type=ALERT_FAVORITE_ACTOR,
        ).count() == 1


def test_favorite_actor_fetches_credits_for_uncached_title_not_filmography(app, user):
    """Missing cast cache uses one title people lookup, not an actor filmography poll."""
    with app.app_context():
        person, media = _seed_favorite_actor_catalog(
            user,
            listed_at=datetime.utcnow(),
            favorited_at=datetime.utcnow() - timedelta(days=10),
            cast_fetched=False,
        )
        payload = {
            'cast': [{
                'characters': ['Doron'],
                'person': {
                    'name': 'Lior Raz',
                    'ids': {'trakt': 501, 'slug': 'lior-raz'},
                },
            }],
        }
        with patch('services.alerts.ensure_user_calendar_fresh', return_value=True), \
             patch('services.alerts.tmdb_configured', return_value=False), \
             patch('services.trakt_client.fetch_media_people', return_value=payload) as fetch_people:
            created = run_media_alerts(app)
        assert created == 1
        fetch_people.assert_called_once_with('movie', 7701)
        assert Notification.query.filter_by(
            user_id=user, alert_type=ALERT_FAVORITE_ACTOR,
        ).one().message == 'Lior Raz'


def test_favorite_actor_pref_off_records_event_only(app, user):
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.alert_favorite_actor = False
        _seed_favorite_actor_catalog(
            user,
            listed_at=datetime.utcnow(),
            favorited_at=datetime.utcnow() - timedelta(days=10),
        )
        with patch('services.alerts.ensure_user_calendar_fresh', return_value=True), \
             patch('services.alerts.tmdb_configured', return_value=False):
            assert run_media_alerts(app) == 0
        assert Notification.query.filter_by(
            user_id=user, alert_type=ALERT_FAVORITE_ACTOR,
        ).count() == 0
        assert AlertEvent.query.filter_by(
            user_id=user, alert_type=ALERT_FAVORITE_ACTOR,
            payload_key='baseline:favactor',
        ).count() == 1


def test_favorite_actor_skips_listed_and_old_and_pre_favorite(app, user):
    with app.app_context():
        _seed_favorite_actor_catalog(
            user,
            listed_at=datetime.utcnow(),
            favorited_at=datetime.utcnow() - timedelta(days=10),
            on_list=True,
        )
        with patch('services.alerts.ensure_user_calendar_fresh', return_value=True), \
             patch('services.alerts.tmdb_configured', return_value=False), \
             patch('services.trakt_client.fetch_media_people') as fetch_people:
            assert run_media_alerts(app) == 0
        fetch_people.assert_not_called()
        assert Notification.query.filter_by(user_id=user).count() == 0

        db.session.query(AlertEvent).delete()
        db.session.query(UserMediaState).delete()
        media = CachedMedia.query.filter_by(trakt_id=7701).one()
        media.trakt_listed_at = datetime.utcnow() - timedelta(days=5)
        db.session.commit()
        with patch('services.alerts.ensure_user_calendar_fresh', return_value=True), \
             patch('services.alerts.tmdb_configured', return_value=False), \
             patch('services.trakt_client.fetch_media_people') as fetch_people:
            assert run_media_alerts(app) == 0
        fetch_people.assert_not_called()

        db.session.query(AlertEvent).delete()
        media.trakt_listed_at = datetime.utcnow()
        fav = UserFavoriteActor.query.filter_by(user_id=user).one()
        fav.created_at = datetime.utcnow() + timedelta(days=1)
        db.session.commit()
        with patch('services.alerts.ensure_user_calendar_fresh', return_value=True), \
             patch('services.alerts.tmdb_configured', return_value=False), \
             patch('services.trakt_client.fetch_media_people') as fetch_people:
            assert run_media_alerts(app) == 0
        fetch_people.assert_not_called()
        assert Notification.query.filter_by(
            user_id=user, alert_type=ALERT_FAVORITE_ACTOR,
        ).count() == 0


def test_season_streaming_respects_pref_off(app, user):
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.alert_season_streaming = False
        prefs.alert_episode_aired = False
        db.session.add(CachedMedia(
            media_type='show', trakt_id=1401, title='Fauda', tmdb_id=77,
        ))
        _watchlist(user, 'show', 1401)
        db.session.add(UserCalendarEvent(
            user_id=user, media_type='show', trakt_id=1401,
            event_date=date.today(), season_number=5, episode_number=1,
        ))
        db.session.commit()
        season_providers = [
            {'provider_name': 'Netflix', 'offer_type': 'flatrate', 'region': 'US'},
        ]
        with patch('services.alerts.tmdb_configured', return_value=True), \
             patch('services.sync_jobs.tmdb_configured', return_value=True), \
             patch('services.sync_jobs.get_watch_providers', return_value=[]), \
             patch(
                 'services.tmdb_client.get_season_watch_providers',
                 return_value=season_providers,
             ), \
             patch('services.alerts.ensure_user_calendar_fresh', return_value=True):
            assert run_media_alerts(app) == 0
        assert Notification.query.filter_by(
            user_id=user, alert_type=ALERT_SEASON_STREAMING,
        ).count() == 0
        assert AlertEvent.query.filter_by(
            user_id=user, alert_type=ALERT_SEASON_STREAMING,
            payload_key='baseline:seasonstream:5',
        ).count() == 1

