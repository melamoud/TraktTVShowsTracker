"""Release-watch checker creates in-app notifications when providers appear."""

from datetime import datetime
from unittest.mock import patch

from models import (
    CachedMedia, MediaProviderAvailability, Notification, ReleaseWatch, db,
)
from services.sync_jobs import check_release_watches
from tests.conftest import login_client


def test_check_release_watches_notifies(app, user):
    """When TMDB reports flatrate providers, a notification is created."""
    with app.app_context():
        media = CachedMedia(
            media_type='movie', trakt_id=9001, title='Soon Stream',
            tmdb_id=4242, trakt_listed_at=datetime(2026, 8, 1),
        )
        db.session.add(media)
        db.session.flush()
        db.session.add(ReleaseWatch(
            user_id=user, media_type='movie', trakt_id=9001,
            title='Soon Stream', active=True,
        ))
        db.session.commit()
        media_id = media.id

        fake_providers = [
            {
                'provider_name': 'Netflix',
                'tmdb_provider_id': 8,
                'offer_type': 'flatrate',
                'region': 'US',
            }
        ]
        with patch('services.sync_jobs.tmdb_configured', return_value=True), patch(
            'services.sync_jobs.get_watch_providers', return_value=fake_providers
        ):
            notified = check_release_watches(app)

        assert notified == 1
        notes = Notification.query.filter_by(user_id=user).all()
        assert len(notes) == 1
        assert 'Netflix' in notes[0].message
        watch = ReleaseWatch.query.filter_by(user_id=user, trakt_id=9001).first()
        assert watch.active is False
        assert watch.notified_at is not None
        assert MediaProviderAvailability.query.filter_by(cached_media_id=media_id).count() >= 1


def test_admin_run_release_check(app, client, admin_user):
    """Admin can trigger the release check from the dashboard."""
    login_client(client, app, admin_user)
    resp = client.post('/admin/run-release-check', follow_redirects=True)
    assert resp.status_code == 200
    assert b'Release check finished' in resp.data
