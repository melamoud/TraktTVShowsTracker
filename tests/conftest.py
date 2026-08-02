"""
Pytest fixtures: isolated app + DB, authenticated test client helpers.
"""

import os
import sys

import pytest

# Ensure project root is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class TestConfig:
    """Minimal config for automated tests."""

    SECRET_KEY = 'test-secret-key-with-at-least-32-characters!!'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TESTING = True
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    TRAKT_CLIENT_ID = 'test-client-id'
    TRAKT_CLIENT_SECRET = 'test-client-secret'
    TRAKT_REDIRECT_URI = 'https://localhost:8300/auth/callback'
    TRAKT_API_BASE = 'https://api.trakt.tv'
    TRAKT_API_VERSION = '2'
    TMDB_API_KEY = ''
    TMDB_API_BASE = 'https://api.themoviedb.org/3'
    STREAMING_REGION = 'US'
    ADMIN_TRAKT_USERNAMES = ['adminuser']
    ADMIN_ALLOW_ENV_PROMOTE = False
    DEFAULT_PER_PAGE = 50
    ALLOWED_PER_PAGE = (10, 50, 100)
    LOG_DIR = os.path.join(ROOT, 'logs')
    LOG_FILE = os.path.join(ROOT, 'logs', 'test.log')
    PID_FILE = os.path.join(ROOT, '.server.test.pid')
    HOST = '127.0.0.1'
    PORT = 8300
    PUBLIC_HOST = 'localhost'
    DEBUG = False
    CATALOG_SYNC_INTERVAL_MINUTES = 60
    PROVIDER_SYNC_INTERVAL_HOURS = 12
    SSL_CERT_FILE = 'cert.pem'
    SSL_KEY_FILE = 'key.pem'


@pytest.fixture
def app():
    """Create a fresh app with in-memory database."""
    from app import create_app
    from models import db

    application = create_app(TestConfig)
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def user(app):
    """Create a normal non-admin user."""
    from models import User, UserPreference, db

    with app.app_context():
        u = User(trakt_uuid='uuid-friend', trakt_id=1001, username='friend', is_admin=False)
        db.session.add(u)
        db.session.flush()
        db.session.add(UserPreference(user_id=u.id))
        db.session.commit()
        return u.id


@pytest.fixture
def admin_user(app):
    """Create an admin user."""
    from models import User, UserPreference, db

    with app.app_context():
        u = User(trakt_uuid='uuid-admin', trakt_id=1, username='adminuser', is_admin=True)
        db.session.add(u)
        db.session.flush()
        db.session.add(UserPreference(user_id=u.id))
        db.session.commit()
        return u.id


def login_client(client, app, user_id):
    """Log a user into the test client via Flask-Login session."""
    from flask_login import login_user
    from models import User

    with app.app_context():
        from models import db
        user_obj = db.session.get(User, user_id)

        @client.application.login_manager.request_loader
        def load_from_request(request):
            return None

        with client.session_transaction() as sess:
            sess['_user_id'] = str(user_id)
            sess['_fresh'] = True

        # Ensure user_loader resolves
        assert user_obj is not None
    return client
