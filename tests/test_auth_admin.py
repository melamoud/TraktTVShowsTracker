"""Tests for admin bootstrap and admin route protection."""

from models import AppMeta, User, db
from services.admin_bootstrap import maybe_grant_admin, mark_admin_bootstrapped
from tests.conftest import login_client


def test_admin_bootstrap_grants_listed_user(app):
    """Configured Trakt username becomes admin when none exist yet."""
    with app.app_context():
        u = User(trakt_uuid='uuid-9', trakt_id=9, username='adminuser', is_admin=False)
        db.session.add(u)
        db.session.commit()
        assert maybe_grant_admin(u) is True
        assert u.is_admin is True


def test_admin_bootstrap_locked_after_first(app):
    """Env list cannot promote others after bootstrap without override."""
    with app.app_context():
        first = User(trakt_uuid='uuid-1', trakt_id=1, username='adminuser', is_admin=True)
        db.session.add(first)
        db.session.commit()
        mark_admin_bootstrapped()

        # Already bootstrapped + admin exists → env list cannot promote strangers
        stranger = User(trakt_uuid='uuid-3', trakt_id=3, username='stranger', is_admin=False)
        db.session.add(stranger)
        db.session.commit()
        assert maybe_grant_admin(stranger) is False


def test_admin_routes_forbidden_for_normal_user(app, client, user):
    """Non-admin receives 403 on admin dashboard."""
    login_client(client, app, user)
    resp = client.get('/admin/')
    assert resp.status_code == 403


def test_admin_dashboard_ok(app, client, admin_user):
    """Admin can open dashboard."""
    login_client(client, app, admin_user)
    resp = client.get('/admin/')
    assert resp.status_code == 200
    assert b'Admin' in resp.data


def test_trakt_log_forbidden_for_normal_user(app, client, user):
    """Non-admin cannot open the Trakt call log."""
    login_client(client, app, user)
    assert client.get('/admin/trakt-log').status_code == 403
    assert client.get('/admin/trakt-log.json').status_code == 403


def test_trakt_log_json_returns_parsed_calls(app, client, admin_user, tmp_path):
    """Admin JSON viewer tails Trakt lines and honors a substring filter."""
    log = tmp_path / 'app.log'
    log.write_text(
        '\n'.join([
            '2026-08-13 12:00:01,001 - app - INFO - Seeded 11 default streaming services',
            '2026-08-13 12:00:02,002 - app - INFO - Cache user_media hit user=friend calls=0 source=http GET /my/shows',
            '2026-08-13 12:00:03,003 - app - WARNING - Trakt GET /movies/updates/2026-08-01 page=1 status=429 user=- source=scheduler catalog_sync',
            '2026-08-13 12:00:04,004 - app - INFO - Cache user_media fetch user=friend reason=force calls=8 source=http GET /my/shows?refresh=1',
        ]) + '\n',
        encoding='utf-8',
    )
    app.config['LOG_FILE'] = str(log)
    login_client(client, app, admin_user)

    page = client.get('/admin/trakt-log')
    assert page.status_code == 200
    assert b'Trakt cache log' in page.data

    all_rows = client.get('/admin/trakt-log.json').get_json()
    assert all_rows['shown'] == 3
    assert all_rows['lines'][0]['result'] == 'hit'
    assert all_rows['lines'][1]['result'] == 'error'
    assert all_rows['stats']['hits'] == 1
    assert all_rows['stats']['fetches'] == 1

    filtered = client.get('/admin/trakt-log.json?q=scheduler').get_json()
    assert filtered['shown'] == 1
    assert filtered['lines'][0]['source'] == 'scheduler catalog_sync'
