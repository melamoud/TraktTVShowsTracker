"""
SQLAlchemy models for TraktTV Shows Tracker.
"""

from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """Local user linked to a TraktTV account."""

    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    # Trakt settings expose ids.uuid (stable). Numeric ids.trakt is often absent.
    trakt_uuid = db.Column(db.String(64), unique=True, nullable=False, index=True)
    trakt_id = db.Column(db.Integer, unique=True, nullable=True, index=True)
    username = db.Column(db.String(120), unique=True, nullable=False, index=True)
    name = db.Column(db.String(200))
    slug = db.Column(db.String(120))
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active_account = db.Column(db.Boolean, default=True, nullable=False)
    access_token_enc = db.Column(db.Text)
    refresh_token_enc = db.Column(db.Text)
    token_expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_login_at = db.Column(db.DateTime)
    last_sync_at = db.Column(db.DateTime)

    preferences = db.relationship('UserPreference', backref='user', uselist=False, cascade='all, delete-orphan')
    streaming_services = db.relationship('UserStreamingService', backref='user', cascade='all, delete-orphan')
    review_markers = db.relationship('ReviewMarker', backref='user', cascade='all, delete-orphan')
    found_on = db.relationship('MediaFoundOn', backref='user', cascade='all, delete-orphan')
    notifications = db.relationship('Notification', backref='user', cascade='all, delete-orphan')
    release_watches = db.relationship('ReleaseWatch', backref='user', cascade='all, delete-orphan')
    sessions = db.relationship('UserSession', backref='user', cascade='all, delete-orphan')

    def get_id(self):
        """Flask-Login user id."""
        return str(self.id)

    @property
    def is_active(self):
        """Flask-Login active flag (disabled users cannot authenticate)."""
        return bool(self.is_active_account)


class UserPreference(db.Model):
    """Per-user genre/keyword preference configuration."""

    __tablename__ = 'user_preferences'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    genres_json = db.Column(db.Text, default='[]')  # JSON list of genre strings
    keywords_json = db.Column(db.Text, default='[]')  # JSON list of keyword strings
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class StreamingService(db.Model):
    """Global / default streaming service catalog (admin-managed)."""

    __tablename__ = 'streaming_services'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    url = db.Column(db.String(500))
    note = db.Column(db.Text)
    tmdb_provider_id = db.Column(db.Integer)  # TMDB watch-provider id when known
    is_default = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class UserStreamingService(db.Model):
    """Streaming services a user owns / uses (default pick or custom)."""

    __tablename__ = 'user_streaming_services'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    streaming_service_id = db.Column(db.Integer, db.ForeignKey('streaming_services.id'))
    custom_name = db.Column(db.String(120))
    custom_url = db.Column(db.String(500))
    custom_note = db.Column(db.Text)
    is_custom = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    service = db.relationship('StreamingService')

    @property
    def display_name(self):
        """Human-readable service name."""
        if self.is_custom:
            return self.custom_name or 'Custom service'
        return self.service.name if self.service else 'Unknown'


class StreamingServiceSuggestion(db.Model):
    """User-suggested streaming service awaiting admin approval."""

    __tablename__ = 'streaming_service_suggestions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    url = db.Column(db.String(500))
    note = db.Column(db.Text)
    status = db.Column(db.String(32), default='pending', nullable=False)  # pending/approved/rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = db.Column(db.DateTime)
    resolved_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    user = db.relationship('User', foreign_keys=[user_id])


class CachedMedia(db.Model):
    """Cached movie/show metadata from Trakt (and optional TMDB ids)."""

    __tablename__ = 'cached_media'
    __table_args__ = (
        db.UniqueConstraint('media_type', 'trakt_id', name='uq_media_type_trakt'),
    )

    id = db.Column(db.Integer, primary_key=True)
    media_type = db.Column(db.String(16), nullable=False, index=True)  # movie | show
    trakt_id = db.Column(db.Integer, nullable=False, index=True)
    slug = db.Column(db.String(200))
    title = db.Column(db.String(400), nullable=False)
    year = db.Column(db.Integer)
    overview = db.Column(db.Text)
    runtime = db.Column(db.Integer)
    network = db.Column(db.String(200))  # broadcast channel / network when known
    genres_json = db.Column(db.Text, default='[]')
    imdb_id = db.Column(db.String(32))
    tmdb_id = db.Column(db.Integer, index=True)
    tvdb_id = db.Column(db.Integer)
    trailer_url = db.Column(db.String(500))
    homepage = db.Column(db.String(500))
    poster_url = db.Column(db.String(500))
    released_at = db.Column(db.Date)  # public release / first aired
    trakt_listed_at = db.Column(db.DateTime, index=True)  # feed sort time (release/premiere)
    feed_source = db.Column(db.String(32), index=True)  # release_calendar | updates | watchlist
    first_seen_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    raw_json = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MediaProviderAvailability(db.Model):
    """Cached TMDB watch-provider availability for a media item (US region)."""

    __tablename__ = 'media_provider_availability'
    __table_args__ = (
        db.UniqueConstraint('cached_media_id', 'provider_name', 'offer_type', name='uq_media_provider'),
    )

    id = db.Column(db.Integer, primary_key=True)
    cached_media_id = db.Column(db.Integer, db.ForeignKey('cached_media.id'), nullable=False, index=True)
    provider_name = db.Column(db.String(120), nullable=False)
    tmdb_provider_id = db.Column(db.Integer)
    offer_type = db.Column(db.String(32), default='flatrate')  # flatrate/rent/buy/ads
    region = db.Column(db.String(8), default='US')
    checked_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    media = db.relationship('CachedMedia', backref=db.backref('providers', cascade='all, delete-orphan'))


class MediaFoundOn(db.Model):
    """User-assigned 'I found this on <service>' local marker."""

    __tablename__ = 'media_found_on'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'media_type', 'trakt_id', 'service_label', name='uq_found_on'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    media_type = db.Column(db.String(16), nullable=False)
    trakt_id = db.Column(db.Integer, nullable=False)
    service_label = db.Column(db.String(120), nullable=False)
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class ReviewMarker(db.Model):
    """Per-user catalog review cursor: reviewed all items older than this Trakt listing."""

    __tablename__ = 'review_markers'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'media_type', name='uq_review_marker'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    media_type = db.Column(db.String(16), nullable=False)  # movie | show
    trakt_id = db.Column(db.Integer, nullable=False)
    trakt_listed_at = db.Column(db.DateTime, nullable=False)
    title = db.Column(db.String(400))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class UserMediaState(db.Model):
    """Cached Trakt watchlist / watched state for highlighting (refreshed from Trakt)."""

    __tablename__ = 'user_media_state'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'media_type', 'trakt_id', name='uq_user_media_state'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    media_type = db.Column(db.String(16), nullable=False)
    trakt_id = db.Column(db.Integer, nullable=False)
    on_watchlist = db.Column(db.Boolean, default=False, nullable=False)
    watched = db.Column(db.Boolean, default=False, nullable=False)
    plays = db.Column(db.Integer, default=0)
    last_watched_at = db.Column(db.DateTime)
    progress_percent = db.Column(db.Float)  # shows: approx watched episode ratio
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ReleaseWatch(db.Model):
    """User wants an alert when an upcoming title appears on any streaming service."""

    __tablename__ = 'release_watches'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'media_type', 'trakt_id', name='uq_release_watch'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    media_type = db.Column(db.String(16), nullable=False)
    trakt_id = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(400))
    active = db.Column(db.Boolean, default=True, nullable=False)
    notified_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Notification(db.Model):
    """In-app notification for a user."""

    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title = db.Column(db.String(300), nullable=False)
    message = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(500))
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class UserSession(db.Model):
    """Trackable login sessions for admin revoke / audit."""

    __tablename__ = 'user_sessions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    session_token = db.Column(db.String(64), unique=True, nullable=False)
    ip_address = db.Column(db.String(64))
    user_agent = db.Column(db.String(400))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    ended_at = db.Column(db.DateTime)
    revoked = db.Column(db.Boolean, default=False, nullable=False)


class AppMeta(db.Model):
    """Key/value app metadata (e.g. admin bootstrap completed)."""

    __tablename__ = 'app_meta'

    key = db.Column(db.String(120), primary_key=True)
    value = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
