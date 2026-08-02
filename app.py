"""
TraktTV Shows Tracker - Flask application factory / app instance.
"""

import logging
import os
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
        # Local poster cache may be cached briefly; HTML/API stay no-store.
        if request.path.startswith('/cache/posters/'):
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
        if getattr(current_user, 'is_authenticated', False):
            from models import Notification, StreamingService, UserStreamingService
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
        return {
            'app_name': 'TraktTV Shows Tracker',
            'unread_notifications': unread,
            'user_streaming_service_names': user_service_names,
            'found_on_service_choices': found_on_service_choices,
        }

    from routes import register_routes
    register_routes(app)

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
        if 'cached_media' not in insp.get_table_names():
            return
        cols = {c['name'] for c in insp.get_columns('cached_media')}
        if 'feed_source' not in cols:
            with db.engine.begin() as conn:
                conn.execute(text(
                    'ALTER TABLE cached_media ADD COLUMN feed_source VARCHAR(32)'
                ))
            app.logger.info('Added cached_media.feed_source column')
    except Exception as exc:
        app.logger.warning('Schema ensure failed: %s', exc)


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
