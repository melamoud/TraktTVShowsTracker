"""
TraktTV Shows Tracker - Flask application factory / app instance.
"""

import json
import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler

from flask import Flask, flash, jsonify, redirect, request, url_for
from flask_login import LoginManager
from flask_wtf.csrf import CSRFError, CSRFProtect

from config import Config
from models import User, db
from services.seed import seed_default_streaming_services

csrf = CSRFProtect()
login_manager = LoginManager()


def create_app(config_object=Config):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(config_object)

    os.makedirs(app.config['LOG_DIR'], exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(__file__), 'instance'), exist_ok=True)

    _configure_logging(app)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in with TraktTV to continue.'

    @login_manager.user_loader
    def load_user(user_id):
        """Load user for Flask-Login."""
        return db.session.get(User, int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        """JSON 401 for the Android API; HTML redirect for the website."""
        if request.path.startswith('/api/v1'):
            return jsonify({'success': False, 'message': 'Login required'}), 401
        return redirect(url_for('auth.login'))

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        """Friendly CSRF failure response."""
        wants_json = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or (request.accept_mimetypes.best and 'application/json' in request.accept_mimetypes.best)
        )
        message = 'Your session expired or the form was invalid. Please refresh and try again.'
        if wants_json:
            return jsonify({'success': False, 'message': message}), 400
        flash(message, 'danger')
        return redirect(request.referrer or url_for('auth.login'))

    @app.after_request
    def add_security_headers(response):
        """Disable caching of authenticated pages and set basic security headers."""
        # Local poster / actor caches may be cached briefly; HTML/API stay no-store.
        if request.path.startswith('/cache/posters/') or request.path.startswith('/cache/actors/'):
            response.headers['Cache-Control'] = 'public, max-age=604800'
            response.headers['X-Content-Type-Options'] = 'nosniff'
            return response
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        if app.config.get('SESSION_COOKIE_SECURE'):
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    @app.context_processor
    def inject_globals():
        """Template globals."""
        from flask_login import current_user
        from sqlalchemy.orm import joinedload

        unread = 0
        user_service_names = []
        found_on_service_choices = []
        found_on_service_urls = {}
        found_on_search_templates = {}
        show_prefs_reminder = False
        favorite_actors = []
        if getattr(current_user, 'is_authenticated', False):
            from models import Notification, StreamingService, UserStreamingService
            from services.cast_service import list_favorite_actors
            from services.found_on_links import service_link_maps
            from services.streaming_matcher import user_needs_prefs_reminder
            unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
            owned = (
                UserStreamingService.query
                .options(joinedload(UserStreamingService.service))
                .filter_by(user_id=current_user.id)
                .order_by(UserStreamingService.id)
                .all()
            )
            user_service_names = [row.display_name for row in owned if row.display_name]
            # Found-on picker: user prefs first, then remaining catalog defaults.
            seen = {n.lower() for n in user_service_names}
            found_on_service_choices = list(user_service_names)
            for svc in StreamingService.query.order_by(StreamingService.name).all():
                if svc.name and svc.name.lower() not in seen:
                    found_on_service_choices.append(svc.name)
                    seen.add(svc.name.lower())
            found_on_service_urls, found_on_search_templates = service_link_maps(current_user)
            # Skip reminder on the setup wizard itself.
            if request.endpoint != 'user.preferences_setup':
                show_prefs_reminder = user_needs_prefs_reminder(current_user)
            favorite_actors = list_favorite_actors(current_user)
        return {
            'app_name': 'TraktTV Shows Tracker',
            'unread_notifications': unread,
            'user_streaming_service_names': user_service_names,
            'found_on_service_choices': found_on_service_choices,
            'found_on_service_urls': found_on_service_urls,
            'found_on_search_templates': found_on_search_templates,
            'show_prefs_reminder': show_prefs_reminder,
            'favorite_actors': favorite_actors,
        }

    from services.found_on_links import found_on_open_url as _found_on_open_url
    app.add_template_global(_found_on_open_url, name='found_on_open_url')
    from routes.catalog_routes import media_detail_url as _media_detail_url
    app.add_template_global(_media_detail_url, name='media_detail_url')

    from routes import register_routes
    register_routes(app)

    from mobile_api import mobile_api_bp
    csrf.exempt(mobile_api_bp)
    app.register_blueprint(mobile_api_bp)
    app.logger.info('[ANDROID-API] blueprint registered prefix=/api/v1')

    with app.app_context():
        db.create_all()
        _ensure_schema(app)
        inserted = seed_default_streaming_services()
        if inserted:
            app.logger.info('Seeded %s default streaming services', inserted)

    app.logger.info('TraktTV Shows Tracker started')
    return app


def _ensure_schema(app):
    """Apply lightweight SQLite column adds for evolving models."""
    from sqlalchemy import inspect, text

    try:
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())
        if 'cached_media' in tables:
            cols = {c['name'] for c in insp.get_columns('cached_media')}
            cm_alters = []
            if 'feed_source' not in cols:
                cm_alters.append(
                    'ALTER TABLE cached_media ADD COLUMN feed_source VARCHAR(32)'
                )
            if 'cast_fetched_at' not in cols:
                cm_alters.append(
                    'ALTER TABLE cached_media ADD COLUMN cast_fetched_at DATETIME'
                )
            if cm_alters:
                with db.engine.begin() as conn:
                    for stmt in cm_alters:
                        conn.execute(text(stmt))
                app.logger.info('Added cached_media feed_source / cast_fetched_at columns')
        if 'user_preferences' in tables:
            cols = {c['name'] for c in insp.get_columns('user_preferences')}
            alters = []
            if 'onboarding_completed_at' not in cols:
                alters.append(
                    'ALTER TABLE user_preferences ADD COLUMN onboarding_completed_at DATETIME'
                )
            if 'prefs_reminder_disabled' not in cols:
                alters.append(
                    'ALTER TABLE user_preferences ADD COLUMN prefs_reminder_disabled '
                    'BOOLEAN DEFAULT 0 NOT NULL'
                )
            if 'prefs_reminder_snooze_until' not in cols:
                alters.append(
                    'ALTER TABLE user_preferences ADD COLUMN prefs_reminder_snooze_until DATETIME'
                )
            if 'hidden_list_ids_json' not in cols:
                alters.append(
                    "ALTER TABLE user_preferences ADD COLUMN hidden_list_ids_json TEXT DEFAULT '[]'"
                )
            if 'default_selected_list_ids_json' not in cols:
                alters.append(
                    "ALTER TABLE user_preferences ADD COLUMN default_selected_list_ids_json "
                    "TEXT DEFAULT '[\"watchlist\"]'"
                )
            if 'ui_view_settings_json' not in cols:
                alters.append(
                    "ALTER TABLE user_preferences ADD COLUMN ui_view_settings_json "
                    "TEXT DEFAULT '{}'"
                )
            for col, ddl in (
                ('alert_release_day', 'ALTER TABLE user_preferences ADD COLUMN alert_release_day BOOLEAN DEFAULT 1 NOT NULL'),
                ('alert_new_streaming', 'ALTER TABLE user_preferences ADD COLUMN alert_new_streaming BOOLEAN DEFAULT 1 NOT NULL'),
                ('alert_episode_aired', 'ALTER TABLE user_preferences ADD COLUMN alert_episode_aired BOOLEAN DEFAULT 1 NOT NULL'),
                ('alert_new_user_login', 'ALTER TABLE user_preferences ADD COLUMN alert_new_user_login BOOLEAN DEFAULT 1 NOT NULL'),
            ):
                if col not in cols:
                    alters.append(ddl)
            if alters:
                with db.engine.begin() as conn:
                    for stmt in alters:
                        conn.execute(text(stmt))
                app.logger.info('Added user_preferences preference columns')
        if 'notifications' in tables:
            ncols = {c['name'] for c in insp.get_columns('notifications')}
            n_alters = []
            for col, ddl in (
                ('alert_type',
                 'ALTER TABLE notifications ADD COLUMN alert_type VARCHAR(32)'),
                ('media_type',
                 'ALTER TABLE notifications ADD COLUMN media_type VARCHAR(16)'),
                ('trakt_id',
                 'ALTER TABLE notifications ADD COLUMN trakt_id INTEGER'),
                ('payload_key',
                 'ALTER TABLE notifications ADD COLUMN payload_key VARCHAR(200)'),
            ):
                if col not in ncols:
                    n_alters.append(ddl)
            if n_alters:
                with db.engine.begin() as conn:
                    for stmt in n_alters:
                        conn.execute(text(stmt))
                app.logger.info('Added notifications columns')
        if 'users' in tables:
            user_cols = {c['name'] for c in insp.get_columns('users')}
            u_user_alters = []
            if 'trakt_activities_json' not in user_cols:
                u_user_alters.append(
                    "ALTER TABLE users ADD COLUMN trakt_activities_json TEXT DEFAULT '{}'"
                )
            if 'calendar_synced_at' not in user_cols:
                u_user_alters.append(
                    'ALTER TABLE users ADD COLUMN calendar_synced_at DATETIME'
                )
            if 'calendar_window_start' not in user_cols:
                u_user_alters.append(
                    'ALTER TABLE users ADD COLUMN calendar_window_start DATE'
                )
            if 'calendar_window_end' not in user_cols:
                u_user_alters.append(
                    'ALTER TABLE users ADD COLUMN calendar_window_end DATE'
                )
            if u_user_alters:
                with db.engine.begin() as conn:
                    for stmt in u_user_alters:
                        conn.execute(text(stmt))
                app.logger.info('Added users calendar / activities cache columns')
        if 'user_media_state' in tables:
            ucols = {c['name'] for c in insp.get_columns('user_media_state')}
            u_alters = []
            for col, ddl in (
                ('episodes_aired',
                 'ALTER TABLE user_media_state ADD COLUMN episodes_aired INTEGER'),
                ('episodes_completed',
                 'ALTER TABLE user_media_state ADD COLUMN episodes_completed INTEGER'),
                ('next_episode_season',
                 'ALTER TABLE user_media_state ADD COLUMN next_episode_season INTEGER'),
                ('next_episode_number',
                 'ALTER TABLE user_media_state ADD COLUMN next_episode_number INTEGER'),
                ('next_episode_title',
                 'ALTER TABLE user_media_state ADD COLUMN next_episode_title VARCHAR(400)'),
                ('progress_detail_at',
                 'ALTER TABLE user_media_state ADD COLUMN progress_detail_at DATETIME'),
                ('pinned',
                 'ALTER TABLE user_media_state ADD COLUMN pinned BOOLEAN DEFAULT 0 NOT NULL'),
                ('pinned_at',
                 'ALTER TABLE user_media_state ADD COLUMN pinned_at DATETIME'),
                ('rating',
                 'ALTER TABLE user_media_state ADD COLUMN rating INTEGER'),
                ('favorited',
                 'ALTER TABLE user_media_state ADD COLUMN favorited BOOLEAN DEFAULT 0 NOT NULL'),
                ('last_episode_aired_at',
                 'ALTER TABLE user_media_state ADD COLUMN last_episode_aired_at DATETIME'),
                ('last_episode_label',
                 'ALTER TABLE user_media_state ADD COLUMN last_episode_label VARCHAR(100)'),
                ('last_aired_checked_at',
                 'ALTER TABLE user_media_state ADD COLUMN last_aired_checked_at DATETIME'),
                ('progress_payload_json',
                 'ALTER TABLE user_media_state ADD COLUMN progress_payload_json TEXT'),
            ):
                if col not in ucols:
                    u_alters.append(ddl)
            if u_alters:
                with db.engine.begin() as conn:
                    for stmt in u_alters:
                        conn.execute(text(stmt))
                app.logger.info('Added user_media_state progress / pin / rating columns')
        if 'user_streaming_services' in tables:
            us_cols = {c['name'] for c in insp.get_columns('user_streaming_services')}
            if 'custom_search_template' not in us_cols:
                with db.engine.begin() as conn:
                    conn.execute(text(
                        'ALTER TABLE user_streaming_services '
                        'ADD COLUMN custom_search_template VARCHAR(500)'
                    ))
                app.logger.info('Added user_streaming_services.custom_search_template')
        if 'scheduler_config' in tables:
            scols = {c['name'] for c in insp.get_columns('scheduler_config')}
            sc_alters = []
            if 'media_alerts_timezone' not in scols:
                sc_alters.append(
                    "ALTER TABLE scheduler_config ADD COLUMN media_alerts_timezone "
                    "VARCHAR(64) DEFAULT 'America/New_York' NOT NULL"
                )
            if 'trakt_read_cache_hours' not in scols:
                sc_alters.append(
                    'ALTER TABLE scheduler_config ADD COLUMN trakt_read_cache_hours '
                    'FLOAT DEFAULT 2.0 NOT NULL'
                )
            if sc_alters:
                with db.engine.begin() as conn:
                    for stmt in sc_alters:
                        conn.execute(text(stmt))
                app.logger.info('Added scheduler_config cache / timezone columns')
    except Exception as exc:
        app.logger.warning('Schema ensure failed: %s', exc)

    _repair_trakt_listed_at(app)


def _repair_trakt_listed_at(app):
    """
    One-time repair: cached trakt_listed_at was set to future release dates for
    catalog updates, hiding recent updates under future-dated rows.

    Reset trakt_listed_at for trakt_db_updates rows to the actual updated_at from
    the raw JSON. This is idempotent via the app_meta flag.
    """
    from models import AppMeta, CachedMedia

    try:
        flag = AppMeta.query.filter_by(key='trakt_listed_at_repaired').first()
        if flag and flag.value == '1':
            return

        rows = (
            CachedMedia.query
            .filter_by(feed_source='trakt_db_updates')
            .filter(CachedMedia.trakt_listed_at.isnot(None))
            .all()
        )
        fixed = 0
        for row in rows:
            try:
                raw = json.loads(row.raw_json or '{}')
                updated = raw.get('updated_at')
                if not updated:
                    continue
                dt = datetime.fromisoformat(str(updated).replace('Z', '+00:00')).replace(tzinfo=None)
                if dt != row.trakt_listed_at:
                    row.trakt_listed_at = dt
                    fixed += 1
            except Exception:
                continue
        db.session.commit()

        if not flag:
            db.session.add(AppMeta(key='trakt_listed_at_repaired', value='1'))
            db.session.commit()
        app.logger.info('Repaired trakt_listed_at for %s trakt_db_updates rows', fixed)
    except Exception as exc:
        app.logger.warning('trakt_listed_at repair failed: %s', exc)
        db.session.rollback()


def _configure_logging(app):
    """Attach rotating file logger."""
    handler = RotatingFileHandler(
        app.config['LOG_FILE'], maxBytes=10 * 1024 * 1024, backupCount=5
    )
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)


# Default app instance for run.py / flask CLI. Tests call create_app(TestConfig).
app = create_app()
