"""Cache-first Trakt reads: TTL gate, write-through, shared objects across screens."""

import json
from datetime import datetime, timedelta
from unittest.mock import patch

from models import Notification, User, UserMediaState, UserRecommendationCache, db
from services.alerts import ALERT_EPISODE_AIRED, _mark_watched_alerts_read
from services.trakt_cache import (
    cache_is_fresh,
    patch_episode_watched,
    save_progress_payload,
)
from services.user_media_sync import ensure_user_media_fresh
from tests.conftest import login_client


def test_ensure_user_media_fresh_skips_trakt_when_ttl_fresh(app, user):
    """Page loads use SQLite while last_sync_at is within the admin TTL."""
    with app.app_context():
        user_obj = db.session.get(User, user)
        user_obj.last_sync_at = datetime.utcnow()
        db.session.commit()
        with patch('services.user_media_sync.get_last_activities') as probe, \
             patch('services.user_media_sync.sync_user_media_state') as sync:
            ran = ensure_user_media_fresh(user_obj, media_types=('movie',), force=False)
        assert ran is False
        probe.assert_not_called()
        sync.assert_not_called()


def test_ensure_user_media_fresh_probe_syncs_when_watchlist_moved(app, user):
    """Hourly job / Set lists still pull when last_activities moved, even if TTL is fresh."""
    with app.app_context():
        user_obj = db.session.get(User, user)
        user_obj.last_sync_at = datetime.utcnow()
        user_obj.trakt_activities_json = json.dumps({
            'watchlist': '2026-08-01T00:00:00.000Z',
            'lists': '2026-08-01T00:00:00.000Z',
            'movies_watched': '2026-08-01T00:00:00.000Z',
            'movies_watchlisted': '2026-08-01T00:00:00.000Z',
        })
        db.session.commit()
        activities = {
            'watchlist': {'updated_at': '2026-08-16T22:00:00.000Z'},
            'lists': {'updated_at': '2026-08-16T22:00:00.000Z'},
            'movies': {
                'watched_at': '2026-08-01T00:00:00.000Z',
                'watchlisted_at': '2026-08-16T22:00:00.000Z',
            },
        }
        with patch('services.user_media_sync.get_last_activities', return_value=activities), \
             patch('services.user_media_sync.sync_user_media_state', return_value=True) as sync:
            ran = ensure_user_media_fresh(
                user_obj, media_types=('movie',), force=False, probe=True,
            )
        assert ran is True
        sync.assert_called_once()


def test_ensure_user_media_fresh_skips_full_sync_after_local_write(app, user):
    """Fingerprint saved after Set lists must not full-pull and restore leftover Favs."""
    from services.user_media_sync import note_user_media_write

    with app.app_context():
        user_obj = db.session.get(User, user)
        user_obj.last_sync_at = datetime(2026, 8, 1)
        user_obj.trakt_activities_json = json.dumps({
            'watchlist': '2026-08-01T00:00:00.000Z',
            'lists': '2026-08-01T00:00:00.000Z',
        })
        db.session.commit()
        activities = {
            'watchlist': {'updated_at': '2026-08-16T22:10:00.000Z'},
            'lists': {'updated_at': '2026-08-16T22:10:00.000Z'},
        }
        with patch('services.user_media_sync.get_last_activities', return_value=activities), \
             patch('services.user_media_sync.sync_user_media_state') as sync:
            note_user_media_write(user_obj, media_types=('movie',), aspects=('watchlist', 'lists'))
            ran = ensure_user_media_fresh(user_obj, media_types=('movie',), force=False)
        assert ran is False
        sync.assert_not_called()


T0 = '2026-10-03T09:18:00.000Z'
T_EP = '2026-10-03T10:44:00.000Z'


def _last_activities(*, watchlist=T0, lists=T0, episodes_watched=T0, movies_watched=T0):
    return {
        'watchlist': {'updated_at': watchlist},
        'lists': {'updated_at': lists},
        'ratings': {'updated_at': T0},
        'favorites': {'updated_at': T0},
        'movies': {
            'watched_at': movies_watched,
            'watchlisted_at': T0,
            'rated_at': T0,
        },
        'shows': {'watchlisted_at': T0, 'rated_at': T0},
        'episodes': {'watched_at': episodes_watched},
    }


def test_episode_watch_without_snapshot_makes_latest_movies_full_pull(app, user, caplog):
    """17:26 Latest movies: episode watch moved Trakt watchlist clock; we never stored it."""
    import logging

    with app.app_context():
        user_obj = db.session.get(User, user)
        user_obj.last_sync_at = datetime.utcnow()
        user_obj.trakt_activities_json = json.dumps({
            'watchlist': T0,
            'lists': T0,
            'ratings': T0,
            'favorites': T0,
            'movies_watched': T0,
            'movies_watchlisted': T0,
            'movies_rated': T0,
            'episodes_watched': T0,
            'shows_watchlisted': T0,
            'shows_rated': T0,
        })
        db.session.commit()
        caplog.set_level(logging.INFO, logger='app')
        # Trakt auto-drops a show from Wishlist on first episode play.
        after_episode = _last_activities(watchlist=T_EP, episodes_watched=T_EP)
        with patch('services.user_media_sync.get_last_activities', return_value=after_episode), \
             patch('services.user_media_sync.sync_user_media_state', return_value=True) as sync:
            ran = ensure_user_media_fresh(
                user_obj, media_types=('movie',), force=False, probe=True,
            )
        assert ran is True
        sync.assert_called_once()
        assert 'reason=fingerprint:watchlist' in caplog.text


def test_movie_probe_persists_episode_clock_so_show_page_does_not_pull(app, user, caplog):
    """A movie last_activities GET must store episodes_watched too (18:08 Set lists)."""
    import logging
    from services.user_media_sync import activity_fingerprint

    with app.app_context():
        user_obj = db.session.get(User, user)
        stored = activity_fingerprint(_last_activities(), ('movie', 'show'))
        user_obj.last_sync_at = datetime.utcnow()
        user_obj.trakt_activities_json = json.dumps(stored)
        db.session.commit()
        live = _last_activities(episodes_watched=T_EP)
        caplog.set_level(logging.INFO, logger='app')
        with patch('services.user_media_sync.get_last_activities', return_value=live), \
             patch('services.user_media_sync.sync_user_media_state') as sync:
            movie_ran = ensure_user_media_fresh(
                user_obj, media_types=('movie',), force=False, probe=True,
            )
            show_ran = ensure_user_media_fresh(
                user_obj, media_types=('show',), force=False, probe=True,
            )
        assert movie_ran is False
        assert show_ran is False
        sync.assert_not_called()
        db.session.refresh(user_obj)
        saved = json.loads(user_obj.trakt_activities_json)
        assert saved.get('episodes_watched') == T_EP


def test_last_activities_one_second_later_is_treated_as_changed(app, user):
    """Lag: snapshot too early, next GET is 1s newer → we currently full-pull."""
    with app.app_context():
        user_obj = db.session.get(User, user)
        user_obj.last_sync_at = datetime.utcnow()
        user_obj.trakt_activities_json = json.dumps({
            'watchlist': T0,
            'lists': T0,
            'movies_watched': T0,
            'movies_watchlisted': T0,
            'movies_rated': T0,
            'ratings': T0,
            'favorites': T0,
        })
        db.session.commit()
        later = _last_activities(watchlist='2026-10-03T09:18:01.000Z')
        with patch('services.user_media_sync.get_last_activities', return_value=later), \
             patch('services.user_media_sync.sync_user_media_state', return_value=True) as sync:
            ran = ensure_user_media_fresh(
                user_obj, media_types=('movie',), force=False, probe=True,
            )
        assert ran is True
        sync.assert_called_once()


def test_last_activities_z_vs_offset_is_treated_as_changed(app, user):
    """Same instant, different string → string compare currently full-pulls."""
    with app.app_context():
        user_obj = db.session.get(User, user)
        user_obj.last_sync_at = datetime.utcnow()
        user_obj.trakt_activities_json = json.dumps({
            'watchlist': '2026-10-03T09:18:00.000Z',
            'lists': T0,
            'movies_watched': T0,
            'movies_watchlisted': T0,
            'movies_rated': T0,
            'ratings': T0,
            'favorites': T0,
        })
        db.session.commit()
        same_instant = _last_activities(watchlist='2026-10-03T09:18:00.000+00:00')
        with patch('services.user_media_sync.get_last_activities', return_value=same_instant), \
             patch('services.user_media_sync.sync_user_media_state', return_value=True) as sync:
            ran = ensure_user_media_fresh(
                user_obj, media_types=('movie',), force=False, probe=True,
            )
        assert ran is True
        sync.assert_called_once()


def test_episode_watched_api_snapshots_last_activities(app, client, user):
    """Progress episode watch must store last_activities or the next page full-pulls."""
    login_client(client, app, user)
    with patch('routes.user_routes.trakt_client.mark_episode_watched', return_value={'added': {'episodes': 1}}), \
         patch('services.user_media_sync.note_user_media_write') as note:
        resp = client.post(
            '/api/episode/watched',
            json={
                'ids': {'trakt': 99},
                'action': 'add',
                'show_trakt_id': 1,
                'season': 1,
                'episode': 1,
            },
        )
    assert resp.status_code == 200
    note.assert_called()


def test_ensure_user_media_fresh_logs_cache_hit(app, user, caplog):
    """TTL-fresh page loads log a cache hit with zero Trakt calls."""
    import logging

    with app.app_context():
        user_obj = db.session.get(User, user)
        user_obj.last_sync_at = datetime.utcnow()
        db.session.commit()
        caplog.set_level(logging.INFO, logger='app')
        with patch('services.user_media_sync.get_last_activities'), \
             patch('services.user_media_sync.sync_user_media_state'):
            ensure_user_media_fresh(user_obj, media_types=('movie',), force=False)
    assert 'Cache user_media hit' in caplog.text
    assert 'calls=0' in caplog.text
    assert 'user=friend' in caplog.text


def test_sync_all_users_media_membership_probes_every_active_user(app, user, admin_user):
    """Catalog job checks last_activities for each active account."""
    from services.user_media_sync import sync_all_users_media_membership

    with app.app_context():
        for uid in (user, admin_user):
            row = db.session.get(User, uid)
            row.last_sync_at = datetime.utcnow()
            row.trakt_activities_json = json.dumps({'watchlist': '2026-08-01T00:00:00.000Z'})
        db.session.commit()
        activities = {'watchlist': {'updated_at': '2026-08-01T00:00:00.000Z'}}
        with patch('services.user_media_sync.get_last_activities', return_value=activities) as probe, \
             patch('services.user_media_sync.sync_user_media_state') as sync:
            stats = sync_all_users_media_membership()
        assert stats['users'] == 2
        assert stats['unchanged'] == 2
        assert stats['synced'] == 0
        assert probe.call_count == 2
        sync.assert_not_called()


def test_sync_all_users_media_membership_skips_inactive(app, user):
    """Disabled accounts are not probed on the hourly catalog run."""
    from services.user_media_sync import sync_all_users_media_membership

    with app.app_context():
        row = db.session.get(User, user)
        row.is_active_account = False
        db.session.commit()
        with patch('services.user_media_sync.get_last_activities') as probe, \
             patch('services.user_media_sync.sync_user_media_state') as sync:
            stats = sync_all_users_media_membership()
        assert stats['users'] == 0
        probe.assert_not_called()
        sync.assert_not_called()


def test_ensure_user_media_fresh_force_ignores_ttl(app, user):
    """Refresh from Trakt still syncs while the TTL is fresh."""
    with app.app_context():
        user_obj = db.session.get(User, user)
        user_obj.last_sync_at = datetime.utcnow()
        db.session.commit()
        with patch('services.user_media_sync.get_last_activities', return_value={}), \
             patch('services.user_media_sync.sync_user_media_state', return_value=True) as sync:
            ran = ensure_user_media_fresh(user_obj, media_types=('movie',), force=True)
        assert ran is True
        sync.assert_called_once()


def test_my_movies_skips_personal_lists_when_ttl_fresh(app, client, user):
    """Browser Back on My movies must not GET /users/me/lists while TTL is fresh."""
    with app.app_context():
        user_obj = db.session.get(User, user)
        user_obj.last_sync_at = datetime.utcnow()
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists') as lists, \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get('/my/movies')
    assert resp.status_code == 200
    lists.assert_not_called()


def test_progress_get_serves_fresh_payload_without_trakt(app, client, user):
    """Opening Progress uses the shared show payload when it is within TTL."""
    with app.app_context():
        save_progress_payload(
            user,
            501,
            watched_keys={(1, 1)},
            aired_keys={(1, 1), (1, 2)},
            seasons_meta=[{
                'number': 1,
                'episodes': [
                    {'number': 1, 'title': 'Pilot', 'ids': {'trakt': 11}},
                    {'number': 2, 'title': 'Next', 'ids': {'trakt': 12}},
                ],
            }],
        )
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.trakt_client.get_show_progress') as prog, \
         patch('routes.user_routes.trakt_client.get_show_seasons') as seasons, \
         patch('routes.user_routes.trakt_client.get_show_watch_history') as hist, \
         patch('routes.user_routes.trakt_client.get_show_watched_entry') as watched:
        resp = client.get('/shows/501/progress?partial=1')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Pilot' in html
    prog.assert_not_called()
    seasons.assert_not_called()
    hist.assert_not_called()
    watched.assert_not_called()


def test_episode_watch_patches_progress_and_is_finished(app, user):
    """Watching an episode on Progress updates the same object Alerts/My read."""
    from services.alerts import is_finished

    with app.app_context():
        save_progress_payload(
            user,
            502,
            watched_keys={(1, 1)},
            aired_keys={(1, 1), (1, 2)},
            seasons_meta=[{
                'number': 1,
                'episodes': [
                    {'number': 1, 'title': 'A'},
                    {'number': 2, 'title': 'B'},
                ],
            }],
        )
        db.session.commit()
        assert is_finished(user, 'show', 502) is False

        ok = patch_episode_watched(user, 502, 1, 2, watched=True)
        db.session.commit()
        assert ok is True
        row = UserMediaState.query.filter_by(
            user_id=user, media_type='show', trakt_id=502,
        ).one()
        assert row.episodes_completed == 2
        assert is_finished(user, 'show', 502) is True


def test_episode_watch_refreshes_summary_when_payload_cleared(app, user):
    """
    After summary sync clears progress_payload_json (c437a8b), mark-watched
    must still advance next_episode so the widget drops/moves the show —
    same as web Progress reloading from Trakt.
    """
    with app.app_context():
        row = UserMediaState(
            user_id=user, media_type='show', trakt_id=8801,
            episodes_aired=5,
            episodes_completed=2,
            next_episode_season=1,
            next_episode_number=3,
            next_episode_title='Stale next',
            progress_payload_json=None,
            progress_detail_at=None,
        )
        db.session.add(row)
        db.session.commit()

        trakt_progress = {
            'aired': 5,
            'completed': 3,
            'next_episode': {
                'season': 1,
                'number': 4,
                'title': 'Real next',
                'ids': {'trakt': 999001},
            },
        }
        with patch(
            'services.trakt_client.get_show_progress',
            return_value=trakt_progress,
        ) as prog:
            ok = patch_episode_watched(user, 8801, 1, 3, watched=True)
            db.session.commit()
        prog.assert_called()
        assert ok is True
        row = UserMediaState.query.filter_by(
            user_id=user, media_type='show', trakt_id=8801,
        ).one()
        assert row.episodes_completed == 3
        assert row.next_episode_season == 1
        assert row.next_episode_number == 4
        assert row.next_episode_title == 'Real next'


def test_episode_watch_local_advance_when_trakt_refresh_fails(app, user):
    """If Trakt refresh fails with empty payload, still clear the marked next."""
    with app.app_context():
        row = UserMediaState(
            user_id=user, media_type='show', trakt_id=8802,
            episodes_aired=4,
            episodes_completed=1,
            next_episode_season=2,
            next_episode_number=1,
            next_episode_title='Only one left shown',
            progress_payload_json=None,
        )
        db.session.add(row)
        db.session.commit()

        with patch(
            'services.trakt_client.get_show_progress',
            side_effect=RuntimeError('trakt down'),
        ):
            ok = patch_episode_watched(user, 8802, 2, 1, watched=True)
            db.session.commit()
        assert ok is True
        row = UserMediaState.query.filter_by(
            user_id=user, media_type='show', trakt_id=8802,
        ).one()
        assert row.episodes_completed == 2
        assert row.next_episode_season is None
        assert row.next_episode_number is None


def test_alert_cleanup_uses_fresh_progress_payload(app, user):
    """Alert job must not GET show progress when that show's cache is fresh."""
    with app.app_context():
        save_progress_payload(
            user,
            503,
            watched_keys={(2, 4)},
            aired_keys={(2, 4), (2, 5)},
            seasons_meta=[{
                'number': 2,
                'episodes': [
                    {'number': 4, 'title': 'Cliff'},
                    {'number': 5, 'title': 'Open'},
                ],
            }],
        )
        db.session.add(Notification(
            user_id=user,
            alert_type=ALERT_EPISODE_AIRED,
            title='New episode',
            message='S02E04',
            media_type='show',
            trakt_id=503,
            payload_key='ep:2:4',
            is_read=False,
        ))
        db.session.add(Notification(
            user_id=user,
            alert_type=ALERT_EPISODE_AIRED,
            title='New episode',
            message='S02E05',
            media_type='show',
            trakt_id=503,
            payload_key='ep:2:5',
            is_read=False,
        ))
        db.session.commit()
        user_obj = db.session.get(User, user)
        with patch('services.alerts.trakt_client.get_show_progress') as prog:
            _mark_watched_alerts_read(user_obj)
        prog.assert_not_called()
        notes = {
            n.payload_key: n
            for n in Notification.query.filter_by(user_id=user, trakt_id=503).all()
        }
        assert notes['ep:2:4'].is_read is True
        assert notes['ep:2:5'].is_read is False


def test_calendar_skips_fetch_when_window_fresh(app, user):
    """My calendar and alerts share one calendar window TTL."""
    from services.calendar_view import ensure_user_calendar_fresh

    with app.app_context():
        user_obj = db.session.get(User, user)
        today = datetime.utcnow().date()
        user_obj.calendar_synced_at = datetime.utcnow()
        user_obj.calendar_window_start = today - timedelta(days=33)
        user_obj.calendar_window_end = today + timedelta(days=33)
        db.session.commit()
        with patch('services.calendar_view.trakt_client.get_calendar_entries') as cal:
            ran = ensure_user_calendar_fresh(user_obj, today, 7)
        assert ran is False
        cal.assert_not_called()


def test_recommendations_use_cached_payload_within_ttl(app, client, user):
    """Recs page does not hit Trakt again while the feed cache is fresh."""
    from services.trakt_cache import save_recommendations_cache

    fake = [{
        'movie': {
            'title': 'Cached Rec',
            'year': 2026,
            'ids': {'trakt': 8801},
        },
    }]
    with app.app_context():
        save_recommendations_cache(user, 'movie', None, fake)
        db.session.commit()

    login_client(client, app, user)
    with patch('services.user_media_sync.ensure_user_media_fresh', return_value=False), \
         patch('services.trakt_client.get_recommendations') as recs, \
         patch('routes.catalog_routes.trakt_client.get_personal_lists', return_value=[]):
        resp = client.get('/recommendations/movies')
    assert resp.status_code == 200
    recs.assert_not_called()
    assert b'Cached Rec' in resp.data


def test_recommendations_fall_back_to_stale_cache_on_trakt_error(app, client, user):
    """When Trakt 500s and the TTL cache is expired, still show the last list."""
    from services.trakt_cache import save_recommendations_cache
    from services.trakt_client import TraktError

    fake = [{
        'movie': {
            'title': 'Stale Rec',
            'year': 2025,
            'ids': {'trakt': 8802},
        },
    }]
    with app.app_context():
        save_recommendations_cache(user, 'movie', None, fake)
        row = UserRecommendationCache.query.filter_by(
            user_id=user, media_type='movie', genre_slug='all',
        ).first()
        row.fetched_at = datetime.utcnow() - timedelta(hours=48)
        db.session.commit()

    login_client(client, app, user)
    with patch('services.user_media_sync.ensure_user_media_fresh', return_value=False), \
         patch(
             'services.trakt_client.get_recommendations',
             side_effect=TraktError('Trakt API error on /recommendations/movies (500)', 500),
         ), \
         patch('routes.catalog_routes.trakt_client.get_personal_lists', return_value=[]):
        resp = client.get('/recommendations/movies')
    assert resp.status_code == 200
    assert b'Stale Rec' in resp.data
    assert b'last cached list' in resp.data


def test_cache_is_fresh_respects_age():
    assert cache_is_fresh(datetime.utcnow(), timedelta(hours=2)) is True
    assert cache_is_fresh(datetime.utcnow() - timedelta(hours=3), timedelta(hours=2)) is False
    assert cache_is_fresh(None, timedelta(hours=2)) is False
