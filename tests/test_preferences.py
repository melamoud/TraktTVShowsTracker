"""Preferences: custom streaming services persist."""

from models import UserStreamingService, db
from tests.conftest import login_client


def test_custom_streaming_service_saved(app, client, user):
    """POST preferences with custom_name creates a local custom service."""
    login_client(client, app, user)
    resp = client.post(
        '/preferences',
        data={
            'custom_name': 'Yes TV',
            'custom_url': 'https://example.com/yes',
            'custom_note': 'cable',
            'keywords': 'heist',
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b'Yes TV' in resp.data

    with app.app_context():
        row = UserStreamingService.query.filter_by(
            user_id=user, is_custom=True, custom_name='Yes TV'
        ).first()
        assert row is not None
        assert row.custom_url == 'https://example.com/yes'
