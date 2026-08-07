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
    # Fingerprint of Trakt /sync/last_activities used to auto-invalidate My cache.
    trakt_activities_json = db.Column(db.Text, default='{}')

    preferences = db.relationship('UserPreference', backref='user', uselist=False, cascade='all, delete-orphan')
    streaming_services = db.relationship('UserStreamingService', backref='user', cascade='all, delete-orphan')
    review_markers = db.relationship('ReviewMarker', backref='user', cascade='all, delete-orphan')
    found_on = db.relationship('MediaFoundOn', backref='user', cascade='all, delete-orphan')
    notifications = db.relationship('Notification', backref='user', cascade='all, delete-orphan')
    alert_events = db.relationship('AlertEvent', backref='user', cascade='all, delete-orphan')
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
    # Trakt personal list ids (stringified trakt ids) hidden from Add to lists menu.
    # Empty/default = all lists shown (Wishlist is always shown).
    hidden_list_ids_json = db.Column(db.Text, default='[]')
    # List ids pre-checked when opening Add to lists (includes "watchlist").
    # Default: Wishlist only. Empty array = nothing pre-checked.
    default_selected_list_ids_json = db.Column(db.Text, default='["watchlist"]')
    # Per-screen UI filters / page size (My, Latest, Recs), JSON object keyed by view.
    ui_view_settings_json = db.Column(db.Text, default='{}')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Onboarding / reminder for empty match filters (genres + keywords).
    onboarding_completed_at = db.Column(db.DateTime)  # finished wizard or skipped
    prefs_reminder_disabled = db.Column(db.Boolean, default=False, nullable=False)
    prefs_reminder_snooze_until = db.Column(db.DateTime)  # hide banner until this time
    # Per-type in-app alert toggles (default on).
    alert_release_day = db.Column(db.Boolean, default=True, nullable=False)
    alert_new_streaming = db.Column(db.Boolean, default=True, nullable=False)
    alert_episode_aired = db.Column(db.Boolean, default=True, nullable=False)  # episodes + season drops
    alert_new_user_login = db.Column(db.Boolean, default=True, nullable=False)  # admins only


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


class CatalogFeedSync(db.Model):
    """
    Lazy-sync cursor for Trakt /movies|/shows/updates.

    Trakt pages are oldest-first: page 1 = oldest in the window,
    page_count = newest. We track which page range is already in CachedMedia.
    """

    __tablename__ = 'catalog_feed_sync'

    media_type = db.Column(db.String(16), primary_key=True)  # movie | show
    start_date = db.Column(db.String(16), nullable=False)  # YYYY-MM-DD window start
    page_count = db.Column(db.Integer, default=1, nullable=False)
    oldest_fetched_page = db.Column(db.Integer)  # lowest Trakt page number in cache
    newest_fetched_page = db.Column(db.Integer)  # highest Trakt page number in cache
    bootstrapped_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


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
    # Show episode summary for My Shows cards (filled on page view / Progress page).
    episodes_aired = db.Column(db.Integer)
    episodes_completed = db.Column(db.Integer)
    next_episode_season = db.Column(db.Integer)
    next_episode_number = db.Column(db.Integer)
    next_episode_title = db.Column(db.String(400))
    progress_detail_at = db.Column(db.DateTime)
    # Latest aired episode for the "Newest aired" view (shows with future-only eps hidden).
    last_episode_aired_at = db.Column(db.DateTime)
    last_episode_label = db.Column(db.String(100))
    # Local-only pin to keep “watching now / soon” titles at the top of My pages.
    pinned = db.Column(db.Boolean, default=False, nullable=False)
    pinned_at = db.Column(db.DateTime)
    # Trakt user rating (1–10) and favorites — synced from /sync/ratings + /sync/favorites.
    rating = db.Column(db.Integer)  # None = unrated
    favorited = db.Column(db.Boolean, default=False, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserCalendarEvent(db.Model):
    """Cached Trakt "My calendar" episode air / movie release entry for one user."""

    __tablename__ = 'user_calendar_events'
    __table_args__ = (
        db.UniqueConstraint(
            'user_id', 'media_type', 'trakt_id', 'event_date',
            'season_number', 'episode_number',
            name='uq_user_calendar_event',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    media_type = db.Column(db.String(16), nullable=False)  # movie | show
    trakt_id = db.Column(db.Integer, nullable=False)
    event_date = db.Column(db.Date, nullable=False, index=True)
    season_number = db.Column(db.Integer)   # None for movies
    episode_number = db.Column(db.Integer)  # None for movies
    episode_title = db.Column(db.String(400))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserListMembership(db.Model):
    """Cached membership of a title on a Trakt personal list (not watchlist)."""

    __tablename__ = 'user_list_memberships'
    __table_args__ = (
        db.UniqueConstraint(
            'user_id', 'list_id', 'media_type', 'trakt_id',
            name='uq_user_list_membership',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    list_id = db.Column(db.String(64), nullable=False, index=True)  # Trakt list id as string
    media_type = db.Column(db.String(16), nullable=False)
    trakt_id = db.Column(db.Integer, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AlertEvent(db.Model):
    """
    Dedup / baseline state for auto alerts.

    payload_key examples:
      release:2026-08-04
      provider:Netflix
      ep:2:5
      season:2
      user:42
      baseline:streaming
      baseline:episodes
    """

    __tablename__ = 'alert_events'
    __table_args__ = (
        db.UniqueConstraint(
            'user_id', 'alert_type', 'media_type', 'trakt_id', 'payload_key',
            name='uq_alert_event',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    alert_type = db.Column(db.String(32), nullable=False, index=True)
    media_type = db.Column(db.String(16), default='', nullable=False)  # movie|show|'' for admin
    trakt_id = db.Column(db.Integer, default=0, nullable=False)
    payload_key = db.Column(db.String(200), nullable=False)
    notified_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Notification(db.Model):
    """In-app notification for a user."""

    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    alert_type = db.Column(db.String(32), index=True)  # release_day|new_streaming|…
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
