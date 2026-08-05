"""
Admin routes: user management, default streaming services, help, system info.
"""

from datetime import datetime
from functools import wraps

from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template,
    request, url_for,
)
from flask_login import current_user, login_required

from help_utils import get_help_toc, render_help_markdown
from models import (
    Notification, StreamingService, StreamingServiceSuggestion,
    User, UserSession, db,
)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(fn):
    """Decorator: require authenticated admin user."""
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


@admin_bp.route('/')
@admin_required
def dashboard():
    """Admin home dashboard."""
    from models import AlertEvent
    from services.tmdb_client import is_configured as tmdb_is_configured

    stats = {
        'users': User.query.count(),
        'active_users': User.query.filter_by(is_active_account=True).count(),
        'pending_suggestions': StreamingServiceSuggestion.query.filter_by(status='pending').count(),
        'services': StreamingService.query.count(),
        'alert_events': AlertEvent.query.count(),
        'tmdb_configured': tmdb_is_configured(),
    }
    return render_template('admin/dashboard.html', stats=stats)


@admin_bp.route('/run-release-check', methods=['POST'])
@admin_required
def run_release_check():
    """Manually run auto media alerts (release / streaming / episodes)."""
    from services.alerts import run_media_alerts

    try:
        notified = run_media_alerts(current_app._get_current_object())
        flash(f'Alert check finished. Notifications created: {notified}.', 'success')
    except Exception as exc:
        current_app.logger.exception('Manual alert check failed: %s', exc)
        flash(f'Alert check failed: {exc}', 'danger')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/users')
@admin_required
def users():
    """List and manage local users (does not modify Trakt accounts)."""
    rows = User.query.order_by(User.username).all()
    return render_template('admin/users.html', users=rows)


@admin_bp.route('/users/<int:user_id>/toggle-active', methods=['POST'])
@admin_required
def toggle_active(user_id):
    """Enable or disable a local account."""
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot disable your own account.', 'danger')
        return redirect(url_for('admin.users'))
    user.is_active_account = not user.is_active_account
    db.session.commit()
    flash(f'User {user.username} is now {"active" if user.is_active_account else "disabled"}.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/toggle-admin', methods=['POST'])
@admin_required
def toggle_admin(user_id):
    """Promote or demote admin (blocks removing the last admin)."""
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        admin_count = User.query.filter_by(is_admin=True).count()
        if admin_count <= 1:
            flash('Cannot demote the last admin.', 'danger')
            return redirect(url_for('admin.users'))
        user.is_admin = False
    else:
        user.is_admin = True
    db.session.commit()
    flash(f'Admin flag for {user.username} is now {user.is_admin}.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/revoke-sessions', methods=['POST'])
@admin_required
def revoke_sessions(user_id):
    """Revoke all tracked local sessions for a user."""
    user = User.query.get_or_404(user_id)
    now = datetime.utcnow()
    sessions = UserSession.query.filter_by(user_id=user.id, revoked=False).all()
    for s in sessions:
        s.revoked = True
        s.ended_at = now
    # Also clear stored Trakt tokens so they must re-login
    user.access_token_enc = None
    user.refresh_token_enc = None
    user.token_expires_at = None
    db.session.commit()
    flash(f'Revoked sessions for {user.username}.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/delete-local', methods=['POST'])
@admin_required
def delete_local(user_id):
    """Delete local user data (never touches the user's TraktTV account)."""
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot delete your own account while logged in.', 'danger')
        return redirect(url_for('admin.users'))
    if user.is_admin and User.query.filter_by(is_admin=True).count() <= 1:
        flash('Cannot delete the last admin.', 'danger')
        return redirect(url_for('admin.users'))
    username = user.username
    db.session.delete(user)
    db.session.commit()
    flash(f'Deleted local data for {username}. Their Trakt account is unchanged.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/streaming-services', methods=['GET', 'POST'])
@admin_required
def streaming_services():
    """Manage default streaming services and approve user suggestions."""
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            name = (request.form.get('name') or '').strip()
            if name and not StreamingService.query.filter_by(name=name).first():
                db.session.add(StreamingService(
                    name=name,
                    url=(request.form.get('url') or '').strip() or None,
                    note=(request.form.get('note') or '').strip() or None,
                    is_default=True,
                ))
                db.session.commit()
                flash(f'Added service {name}.', 'success')
            else:
                flash('Name missing or already exists.', 'warning')
        elif action == 'approve':
            sug_id = int(request.form.get('suggestion_id'))
            sug = StreamingServiceSuggestion.query.get_or_404(sug_id)
            if not StreamingService.query.filter_by(name=sug.name).first():
                db.session.add(StreamingService(
                    name=sug.name, url=sug.url, note=sug.note, is_default=True
                ))
            sug.status = 'approved'
            sug.resolved_at = datetime.utcnow()
            sug.resolved_by_user_id = current_user.id
            db.session.add(Notification(
                user_id=sug.user_id,
                alert_type='service_suggestion',
                title='Streaming service approved',
                message=f'"{sug.name}" was added to the default streaming services list.',
            ))
            db.session.commit()
            flash('Suggestion approved.', 'success')
        elif action == 'reject':
            sug_id = int(request.form.get('suggestion_id'))
            sug = StreamingServiceSuggestion.query.get_or_404(sug_id)
            sug.status = 'rejected'
            sug.resolved_at = datetime.utcnow()
            sug.resolved_by_user_id = current_user.id
            db.session.commit()
            flash('Suggestion rejected.', 'info')
        return redirect(url_for('admin.streaming_services'))

    services = StreamingService.query.order_by(StreamingService.name).all()
    pending = StreamingServiceSuggestion.query.filter_by(status='pending').order_by(
        StreamingServiceSuggestion.created_at.desc()
    ).all()
    return render_template('admin/streaming_services.html', services=services, pending=pending)


@admin_bp.route('/help/')
@admin_bp.route('/help/<topic>')
@admin_required
def help_page(topic='admin_overview'):
    """Render admin help topic."""
    html = render_help_markdown('admin', topic)
    if html is None:
        flash('Help topic not found.', 'warning')
        return redirect(url_for('admin.help_page', topic='admin_overview'))
    return render_template(
        'help.html', role='admin', topic=topic, content_html=html, toc=get_help_toc('admin')
    )
