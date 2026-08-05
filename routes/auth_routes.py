"""
Authentication routes: Login with TraktTV (OAuth2).
"""

import secrets
from datetime import datetime

from flask import (
    Blueprint, current_app, flash, redirect, render_template, request,
    session, url_for,
)
from flask_login import login_required, login_user, logout_user

from models import User, UserPreference, UserSession, db
from services.admin_bootstrap import maybe_grant_admin
from services.crypto_tokens import encrypt_token
from services import trakt_client
from services.sync_jobs import sync_user_media_state

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login')
def login():
    """Show login page with Trakt OAuth button and account setup help."""
    if not current_app.config.get('TRAKT_CLIENT_ID'):
        flash(
            'Trakt API is not configured yet. See docs/SETUP.md to create a Trakt API app '
            'and set TRAKT_CLIENT_ID / TRAKT_CLIENT_SECRET in .env.',
            'warning',
        )
    return render_template('login.html')


@auth_bp.route('/auth/trakt')
def auth_trakt():
    """Start Trakt OAuth authorize redirect."""
    if not current_app.config.get('TRAKT_CLIENT_ID'):
        flash('Missing TRAKT_CLIENT_ID. Configure .env first.', 'danger')
        return redirect(url_for('auth.login'))
    state = secrets.token_urlsafe(24)
    session['oauth_state'] = state
    return redirect(trakt_client.oauth_authorize_url(state))


@auth_bp.route('/auth/callback')
def auth_callback():
    """Handle Trakt OAuth callback, create/update local user, establish session."""
    error = request.args.get('error')
    if error:
        flash(f'Trakt login failed: {error}', 'danger')
        return redirect(url_for('auth.login'))

    state = request.args.get('state')
    if not state or state != session.pop('oauth_state', None):
        flash('Invalid OAuth state. Please try logging in again.', 'danger')
        return redirect(url_for('auth.login'))

    code = request.args.get('code')
    if not code:
        flash('Missing authorization code from Trakt.', 'danger')
        return redirect(url_for('auth.login'))

    try:
        tokens = trakt_client.exchange_code_for_tokens(code)
        settings = trakt_client.get_user_settings(tokens['access_token'])
    except trakt_client.TraktError as exc:
        current_app.logger.exception('Trakt OAuth failed: %s', exc)
        flash('Could not complete Trakt login. Check API credentials and try again.', 'danger')
        return redirect(url_for('auth.login'))

    user_block = (settings.get('user') or {})
    ids = user_block.get('ids') or {}
    # Trakt /users/settings returns ids.uuid + ids.slug (not always numeric ids.trakt).
    trakt_uuid = ids.get('uuid') or ids.get('slug')
    username = user_block.get('username') or ids.get('slug')
    slug = ids.get('slug') or username
    numeric_trakt_id = ids.get('trakt')
    if not trakt_uuid or not username:
        current_app.logger.error(
            'Unexpected Trakt settings profile keys=%s ids=%s',
            list(user_block.keys()), ids,
        )
        flash('Trakt did not return a valid user profile.', 'danger')
        return redirect(url_for('auth.login'))

    user = User.query.filter_by(trakt_uuid=str(trakt_uuid)).first()
    if not user and slug:
        user = User.query.filter_by(slug=slug).first()
    if not user:
        user = User.query.filter_by(username=username).first()
    is_new_user = False
    if not user:
        is_new_user = True
        user = User(trakt_uuid=str(trakt_uuid), username=username)
        db.session.add(user)
        db.session.flush()
        db.session.add(UserPreference(user_id=user.id))

    user.trakt_uuid = str(trakt_uuid)
    user.username = username
    user.name = user_block.get('name') or user.name
    user.slug = slug or user.slug
    if numeric_trakt_id:
        user.trakt_id = int(numeric_trakt_id)
    user.last_login_at = datetime.utcnow()
    user.access_token_enc = encrypt_token(tokens.get('access_token'))
    user.refresh_token_enc = encrypt_token(tokens.get('refresh_token'))
    from datetime import timedelta
    user.token_expires_at = datetime.utcnow() + timedelta(seconds=int(tokens.get('expires_in') or 0) - 60)
    db.session.commit()

    if not user.is_active_account:
        flash('Your account has been disabled by an administrator.', 'danger')
        return redirect(url_for('auth.login'))

    maybe_grant_admin(user)

    if is_new_user:
        try:
            from services.alerts import notify_admins_new_user
            notify_admins_new_user(user)
        except Exception as exc:
            current_app.logger.warning('New-user admin alert failed: %s', exc)

    session_token = secrets.token_hex(32)
    db.session.add(UserSession(
        user_id=user.id,
        session_token=session_token,
        ip_address=request.headers.get('X-Forwarded-For', request.remote_addr),
        user_agent=(request.headers.get('User-Agent') or '')[:400],
    ))
    db.session.commit()
    session['app_session_token'] = session_token

    login_user(user, remember=True)
    try:
        sync_user_media_state(user)
    except Exception as exc:
        current_app.logger.warning('Initial media sync failed: %s', exc)

    flash(f'Welcome, {user.username}!', 'success')
    # First-run: send users without genres/keywords through the match-filter wizard.
    prefs = user.preferences
    if prefs is None:
        return redirect(url_for('user.preferences_setup'))
    from services.streaming_matcher import user_has_match_prefs
    if not user_has_match_prefs(user) and not prefs.onboarding_completed_at:
        return redirect(url_for('user.preferences_setup'))
    return redirect(url_for('catalog.home'))


@auth_bp.route('/logout')
@login_required
def logout():
    """End local session and log out."""
    from flask_login import current_user
    token = session.pop('app_session_token', None)
    if token:
        row = UserSession.query.filter_by(session_token=token, user_id=current_user.id).first()
        if row:
            row.ended_at = datetime.utcnow()
            db.session.commit()
    logout_user()
    flash('Logged out.', 'info')
    return redirect(url_for('auth.login'))
