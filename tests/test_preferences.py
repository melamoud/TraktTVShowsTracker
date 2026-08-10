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
            'custom_search_template': 'https://example.com/search?q=<title>',
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
        assert row.custom_search_template == 'https://example.com/search?q=<title>'


def test_custom_search_template_update_existing(app, client, user):
    """Existing customs can update search template via preferences fields."""
    with app.app_context():
        row = UserStreamingService(
            user_id=user, is_custom=True, custom_name='toFlx',
            custom_url='https://toflx.com',
        )
        db.session.add(row)
        db.session.commit()
        cid = row.id

    login_client(client, app, user)
    resp = client.post(
        '/preferences',
        data={
            f'custom_search_template_{cid}': 'https://toflx.com/search?q=<title>',
            'keywords': 'heist',
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        row = db.session.get(UserStreamingService, cid)
        assert row.custom_search_template == 'https://toflx.com/search?q=<title>'
