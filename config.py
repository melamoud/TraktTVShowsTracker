"""
Application configuration for TraktTV Shows Tracker.
"""

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

_INSECURE_SECRET_KEYS = frozenset({
    'your-secret-key-change-in-production',
    'CHANGE_ME_NOW__GENERATE_A_RANDOM_64_CHARS',
})


def _load_secret_key():
    """Load a strong Flask SECRET_KEY from env or a persistent local file."""
    env_key = (os.environ.get('SECRET_KEY') or '').strip()
    if env_key and env_key not in _INSECURE_SECRET_KEYS and len(env_key) >= 32:
        return env_key

    key_path = BASE_DIR / '.flask_secret_key'
    if key_path.is_file():
        try:
            file_key = key_path.read_text(encoding='utf-8').strip()
            if file_key and file_key not in _INSECURE_SECRET_KEYS and len(file_key) >= 32:
                return file_key
        except OSError:
            pass

    new_key = secrets.token_hex(32)
    try:
        key_path.write_text(new_key, encoding='utf-8')
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass
    except OSError as exc:
        raise RuntimeError(
            'Could not write .flask_secret_key and no valid SECRET_KEY env is set.'
        ) from exc
    return new_key


def _csv_env(name, default=''):
    """Parse a comma-separated env var into a list of stripped strings."""
    raw = os.environ.get(name, default) or ''
    return [part.strip() for part in raw.split(',') if part.strip()]


class Config:
    """Base configuration class."""

    SECRET_KEY = _load_secret_key()
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        f'sqlite:///{(BASE_DIR / "instance" / "trakttv.db").as_posix()}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    HOST = os.environ.get('HOST', '0.0.0.0')
    PORT = int(os.environ.get('PORT', '8300'))
    PUBLIC_HOST = os.environ.get('PUBLIC_HOST', 'tvtracker.melamoud.com')
    DEBUG = os.environ.get('DEBUG', '1') not in ('0', 'false', 'False')

    SSL_CERT_FILE = os.environ.get('SSL_CERT_FILE', str(BASE_DIR / 'cert.pem'))
    SSL_KEY_FILE = os.environ.get('SSL_KEY_FILE', str(BASE_DIR / 'key.pem'))

    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', '1') not in ('0', 'false', 'False')
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')

    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None

    LOG_DIR = str(BASE_DIR / 'logs')
    LOG_FILE = str(BASE_DIR / 'logs' / 'app.log')
    PID_FILE = str(BASE_DIR / '.server.pid')

    # Trakt API (create app at https://trakt.tv/oauth/applications)
    TRAKT_CLIENT_ID = os.environ.get('TRAKT_CLIENT_ID', '')
    TRAKT_CLIENT_SECRET = os.environ.get('TRAKT_CLIENT_SECRET', '')
    TRAKT_REDIRECT_URI = os.environ.get(
        'TRAKT_REDIRECT_URI',
        f'https://localhost:{os.environ.get("PORT", "8300")}/auth/callback',
    )
    TRAKT_API_BASE = 'https://api.trakt.tv'
    TRAKT_API_VERSION = '2'

    # TMDB Watch Providers (region US for MVP)
    TMDB_API_KEY = os.environ.get('TMDB_API_KEY', '')
    TMDB_API_BASE = 'https://api.themoviedb.org/3'
    STREAMING_REGION = os.environ.get('STREAMING_REGION', 'US')

    # Admin bootstrap: Trakt usernames that become admin on first login.
    # After an admin exists, env promotion is ignored unless ADMIN_ALLOW_ENV_PROMOTE=1.
    ADMIN_TRAKT_USERNAMES = [u.lower() for u in _csv_env('ADMIN_TRAKT_USERNAMES')]
    ADMIN_ALLOW_ENV_PROMOTE = os.environ.get('ADMIN_ALLOW_ENV_PROMOTE', '0') in ('1', 'true', 'True')

    DEFAULT_PER_PAGE = 50
    ALLOWED_PER_PAGE = (10, 50, 100)

    # Background sync
    CATALOG_SYNC_INTERVAL_MINUTES = int(os.environ.get('CATALOG_SYNC_INTERVAL_MINUTES', '60'))
    PROVIDER_SYNC_INTERVAL_HOURS = int(os.environ.get('PROVIDER_SYNC_INTERVAL_HOURS', '12'))
    # Media alerts (release day / streaming / episodes): run at startup, then on this cadence.
    ALERTS_INTERVAL_HOURS = float(os.environ.get('ALERTS_INTERVAL_HOURS', '4'))
    ALERTS_TIMEZONE = os.environ.get('ALERTS_TIMEZONE', 'America/New_York')
    ALERTS_STARTUP_DELAY_SECONDS = int(os.environ.get('ALERTS_STARTUP_DELAY_SECONDS', '0'))
