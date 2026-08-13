"""Trakt HTTP 429: abort batch work, short retries, progress drawer UX."""

from unittest.mock import MagicMock, patch

import pytest

from models import User, UserListMembership, db
from services.trakt_client import TraktError, api_request
from tests.conftest import login_client


def _reload_user(user_id):
    return db.session.get(User, user_id)


def _resp(status, *, retry_after=None, payload=None):
    resp = MagicMock()
    resp.status_code = status
    resp.headers = {}
    if retry_after is not None:
        resp.headers['Retry-After'] = str(retry_after)
    resp.text = 'rate limited' if status == 429 else ''
    if payload is None:
        resp.content = b''
        resp.json.return_value = None
    else:
        import json
        body = json.dumps(payload).encode()
        resp.content = body
        resp.json.return_value = payload
    return resp


def test_api_request_retries_short_429(app):
    """Burst 429 with Retry-After <= 1.5s is retried once."""
    limited = _resp(429, retry_after=0)
    ok = _resp(200, payload={'ok': True})
    with app.app_context():
        with patch(
            'services.trakt_client.requests.request', side_effect=[limited, ok]
        ) as req, patch('services.trakt_client.time.sleep') as sleep:
            data = api_request('GET', '/shows/1')
    assert data == {'ok': True}
    assert req.call_count == 2
    sleep.assert_called_once()


def test_api_request_does_not_wait_out_quota_429(app):
    """Quota 429 (Retry-After of minutes) fails immediately — no worker stall."""
    limited = _resp(429, retry_after=120)
    with app.app_context():
        with patch(
            'services.trakt_client.requests.request', return_value=limited
        ) as req, patch('services.trakt_client.time.sleep') as sleep:
            with pytest.raises(TraktError) as err:
                api_request('GET', '/shows/1')
    assert err.value.status_code == 429
    assert req.call_count == 1
    sleep.assert_not_called()


def test_list_membership_sync_does_not_fetch_seasons(app, user):
    """List sync caches membership only; seasons belong to the cache job."""
    from services.sync_jobs import sync_user_list_memberships

    personal = [{'id': '10', 'slug': 'a', 'name': 'List 1', 'item_count': 2}]
    items = [
        {'show': {'ids': {'trakt': 1}, 'title': 'A'}},
        {'show': {'ids': {'trakt': 2}, 'title': 'B'}},
    ]
    with app.app_context():
        with patch(
            'services.sync_jobs.trakt_client.get_personal_lists', return_value=personal
        ), patch(
            'services.sync_jobs.trakt_client.get_list_items', return_value=items
        ), patch(
            'services.sync_jobs._update_latest_aired_for_show'
        ) as seed:
            ok = sync_user_list_memberships(_reload_user(user), media_types=('show',))
        assert ok is True
        seed.assert_not_called()
        assert UserListMembership.query.filter_by(user_id=user, list_id='10').count() == 2


def test_list_membership_sync_stops_on_429(app, user):
    """First list-items 429 must not continue into remaining lists."""
    from services.sync_jobs import sync_user_list_memberships

    personal = [
        {'id': '10', 'slug': 'a', 'name': 'List 1', 'item_count': 1},
        {'id': '20', 'slug': 'b', 'name': 'List 2', 'item_count': 1},
    ]
    err = TraktError('Trakt API error on /users/me/lists (429)', 429)
    with app.app_context():
        with patch(
            'services.sync_jobs.trakt_client.get_personal_lists', return_value=personal
        ), patch(
            'services.sync_jobs.trakt_client.get_list_items', side_effect=err
        ) as get_items, patch(
            'services.sync_jobs._update_latest_aired_for_show'
        ) as seed:
            ok = sync_user_list_memberships(_reload_user(user), media_types=('show',))
        assert ok is False
        assert get_items.call_count == 1
        seed.assert_not_called()


def test_ensure_media_cached_stops_on_429(app):
    """Title backfill must not walk the rest of the id list after a 429."""
    from services.sync_jobs import ensure_media_cached

    err = TraktError('Trakt API error on /shows/1 (429)', 429)
    with app.app_context():
        with patch(
            'services.sync_jobs.trakt_client.fetch_media_summary', side_effect=err
        ) as fetch:
            ensure_media_cached('show', [1, 2, 3])
        assert fetch.call_count == 1


def test_series_progress_partial_429(app, client, user):
    """Drawer fetch returns 429 (not 502) with a retry message, no traceback path."""
    err = TraktError('Trakt API error on /shows/205569/progress/watched (429)', 429)
    login_client(client, app, user)
    with patch(
        'routes.user_routes.trakt_client.get_show_progress', side_effect=err
    ):
        resp = client.get('/shows/205569/progress?partial=1')
    assert resp.status_code == 429
    html = resp.get_data(as_text=True)
    assert 'rate-limiting' in html.lower()
    assert 'retry' in html.lower()


def test_api_request_does_not_info_log_successful_calls(app, user, caplog):
    """Successful Trakt HTTP is counted, not INFO-logged (cache events cover scale)."""
    import logging

    from services.trakt_client import trakt_call_source, trakt_http_count

    ok = _resp(200, payload={'ok': True})
    user_obj = db.session.get(User, user)
    before = trakt_http_count()
    caplog.set_level(logging.INFO, logger='app')
    with patch('services.trakt_client.ensure_access_token', return_value='tok'), patch(
        'services.trakt_client.requests.request', return_value=ok
    ):
        with trakt_call_source('scheduler media_alerts'):
            api_request('GET', '/sync/last_activities', user=user_obj)
    assert 'Trakt GET /sync/last_activities' not in caplog.text
    assert trakt_http_count() == before + 1


def test_api_request_warns_on_429(app, caplog):
    """HTTP errors still log so 429s show in the cache viewer."""
    import logging

    from services.trakt_client import trakt_call_source

    limited = _resp(429, retry_after=120)
    caplog.set_level(logging.WARNING, logger='app')
    with patch('services.trakt_client.requests.request', return_value=limited), patch(
        'services.trakt_client.time.sleep'
    ):
        with trakt_call_source('scheduler catalog_sync'):
            with pytest.raises(TraktError):
                api_request('GET', '/shows/1')
    assert 'Trakt GET /shows/1' in caplog.text
    assert 'status=429' in caplog.text
    assert 'source=scheduler catalog_sync' in caplog.text


def test_http_request_inferred_as_trakt_source(app):
    """Without an explicit tag, the Flask method + path is the source."""
    from services.trakt_client import current_trakt_source, trakt_call_source

    with app.test_request_context('/my/movies?refresh=1'):
        assert current_trakt_source() == 'http GET /my/movies?refresh=1'
        with trakt_call_source('scheduler catalog_sync'):
            assert current_trakt_source() == 'scheduler catalog_sync'
        assert current_trakt_source() == 'http GET /my/movies?refresh=1'
