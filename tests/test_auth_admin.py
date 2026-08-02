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
