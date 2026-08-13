"""Cache-first Trakt reads: TTL gate, write-through, shared objects across screens."""

from datetime import datetime, timedelta
from unittest.mock import patch

from models import Notification, User, UserMediaState, db
from services.alerts import ALERT_EPISODE_AIRED, _mark_watched_alerts_read
from services.trakt_cache import (
    cache_is_fresh,
    patch_episode_watched,
    save_progress_payload,
)
from services.user_media_sync import ensure_user_media_fresh
from tests.conftest import login_client


def test_ensure_user_media_fresh_skips_trakt_when_ttl_fresh(app, user):
    """Within TTL, page loads must not call last_activities."""
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


def test_ensure_user_media_fresh_logs_cache_hit(app, user, caplog):
    """TTL-fresh reads log a cache hit with zero Trakt calls."""
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


def test_cache_is_fresh_respects_age():
    assert cache_is_fresh(datetime.utcnow(), timedelta(hours=2)) is True
    assert cache_is_fresh(datetime.utcnow() - timedelta(hours=3), timedelta(hours=2)) is False
    assert cache_is_fresh(None, timedelta(hours=2)) is False
