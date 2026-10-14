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
from services.user_media_sync import ensure_user_media_fresh

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
    if request.args.get('client') == 'android':
        session['oauth_client'] = 'android'
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
        ensure_user_media_fresh(user, force=True)
    except Exception as exc:
        current_app.logger.warning('Initial media sync failed: %s', exc)

    oauth_client = session.pop('oauth_client', None)
    if oauth_client == 'android':
        from datetime import timedelta
        from models import MobileLoginToken
        token = secrets.token_urlsafe(32)
        db.session.add(MobileLoginToken(
            token=token,
            user_id=user.id,
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        ))
        db.session.commit()
        return redirect(url_for('auth.mobile_done', token=token))

    flash(f'Welcome, {user.username}!', 'success')
    # First-run: send users without genres/keywords through the match-filter wizard.
    prefs = user.preferences
    if prefs is None:
        return redirect(url_for('user.preferences_setup'))
    from services.streaming_matcher import user_has_match_prefs
    if not user_has_match_prefs(user) and not prefs.onboarding_completed_at:
        return redirect(url_for('user.preferences_setup'))
    return redirect(url_for('catalog.home'))


@auth_bp.route('/auth/mobile-done')
def mobile_done():
    """Handoff page after Android Trakt OAuth — opens the app via custom scheme."""
    token = (request.args.get('token') or '').strip()
    return render_template('auth_mobile_done.html', token=token)


@auth_bp.route('/auth/google/calendar', methods=['POST'])
@login_required
def google_calendar_start():
    """Start Google OAuth so the user can pick an account."""
    from flask_login import current_user
    from services.google_calendar import GoogleCalendarError, begin_oauth

    try:
        return redirect(begin_oauth(current_user.id, 'web'))
    except GoogleCalendarError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('user.preferences'))


@auth_bp.route('/auth/google/callback')
def google_calendar_callback():
    """Finish Google OAuth from the website or the Android custom tab."""
    from services.google_calendar import GoogleCalendarError, complete_oauth

    if request.args.get('error'):
        return render_template(
            'google_calendar_done.html',
            ok=False,
            message='Google sign-in was cancelled.',
        )
    try:
        user, kind = complete_oauth(
            request.args.get('state') or '',
            request.args.get('code') or '',
        )
    except GoogleCalendarError as exc:
        return render_template(
            'google_calendar_done.html', ok=False, message=str(exc),
        )
    if kind == 'android':
        return render_template(
            'google_calendar_done.html',
            ok=True,
            email=user.google_calendar.account_email if user.google_calendar else '',
        )
    # The browser often drops the session cookie on the hop back from Google.
    # The OAuth state was created while this user was logged in, so sign them
    # back in here instead of sending them through Trakt again.
    from flask_login import login_user
    login_user(user, remember=True)
    session_token = secrets.token_hex(32)
    db.session.add(UserSession(
        user_id=user.id,
        session_token=session_token,
        ip_address=request.headers.get('X-Forwarded-For', request.remote_addr),
        user_agent=(request.headers.get('User-Agent') or '')[:400],
    ))
    db.session.commit()
    session['app_session_token'] = session_token
    email = user.google_calendar.account_email if user.google_calendar else 'your Google account'
    flash(f'Connected {email}. Choose a calendar below.', 'success')
    return redirect(url_for('user.preferences'))


@auth_bp.route('/auth/google/calendar/select', methods=['POST'])
@login_required
def google_calendar_select():
    """Save the calendar the user picked and sync known dates."""
    from flask_login import current_user
    from services.external_calendar import select_google_calendar
    from services.google_calendar import GoogleCalendarError

    try:
        name = select_google_calendar(
            current_user, request.form.get('calendar_id') or '',
        )
    except GoogleCalendarError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('user.preferences'))
    flash(
        f'Calendar set to {name}. Meetings are being added in the background.',
        'success',
    )
    return redirect(url_for('user.preferences'))


@auth_bp.route('/auth/google/calendar/reminder', methods=['POST'])
@login_required
def google_calendar_reminder():
    """Save popup, email, or none, and how long before each meeting."""
    from flask_login import current_user
    from services.external_calendar import save_calendar_reminder
    from services.google_calendar import GoogleCalendarError

    try:
        label = save_calendar_reminder(
            current_user,
            request.form.get('reminder_method') or '',
            request.form.get('reminder_amount') or '',
            request.form.get('reminder_unit') or '',
        )
    except GoogleCalendarError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('user.preferences'))
    flash(f'Meeting reminder set to {label}.', 'success')
    return redirect(url_for('user.preferences'))


@auth_bp.route('/auth/google/calendar/disconnect', methods=['POST'])
@login_required
def google_calendar_disconnect():
    """Stop writing meetings and remove upcoming ones this app created."""
    from flask_login import current_user
    from services.external_calendar import disconnect_google_calendar

    disconnect_google_calendar(current_user)
    flash('Google Calendar disconnected. Past meetings were left in place.', 'success')
    return redirect(url_for('user.preferences'))


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
