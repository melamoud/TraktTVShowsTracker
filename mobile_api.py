"""
JSON API for the native Android client.

Session cookies are the same Flask-Login session used by the website.
Mutating /api/v1 routes are CSRF-exempt (the app sends X-TVTracker-Client).
"""

import secrets
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf.csrf import generate_csrf

from models import MobileLoginToken, Notification, User, UserSession, db
from services.mobile_payloads import (
    serialize_alert_card,
    serialize_media_item,
    serialize_progress,
)

mobile_api_bp = Blueprint('mobile_api', __name__, url_prefix='/api/v1')


@mobile_api_bp.before_request
def _log_android_request():
    current_app.logger.info(
        '[ANDROID-API] %s %s ip=%s client=%s ua=%s',
        request.method,
        request.path,
        request.remote_addr,
        request.headers.get('X-TVTracker-Client', '-'),
        (request.headers.get('User-Agent') or '-')[:120],
    )


def _json_body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _user_payload():
    unread = Notification.query.filter_by(
        user_id=current_user.id, is_read=False,
    ).count()
    return {
        'id': current_user.id,
        'username': current_user.username,
        'is_admin': bool(getattr(current_user, 'is_admin', False)),
        'csrf_token': generate_csrf(),
        'unread_alerts': unread,
    }


def _start_user_session(user):
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


@mobile_api_bp.route('/auth/start', methods=['GET', 'POST'])
def api_auth_start():
    """Return the server Trakt authorize URL for a Custom Tab."""
    if not current_app.config.get('TRAKT_CLIENT_ID'):
        return jsonify({
            'success': False,
            'message': 'Trakt API is not configured on the server.',
        }), 503
    authorize_url = url_for('auth.auth_trakt', client='android', _external=True)
    return jsonify({'success': True, 'authorize_url': authorize_url})


@mobile_api_bp.route('/auth/complete', methods=['POST'])
def api_auth_complete():
    """Exchange the one-time OAuth handoff token for a Flask session cookie."""
    data = _json_body()
    token = (data.get('token') or request.args.get('token') or '').strip()
    if not token:
        return jsonify({'success': False, 'message': 'Missing login token'}), 400
    row = MobileLoginToken.query.filter_by(token=token).first()
    if (
        not row
        or row.used_at
        or not row.expires_at
        or row.expires_at < datetime.utcnow()
    ):
        return jsonify({
            'success': False,
            'message': 'Login token expired. Try logging in again.',
        }), 401
    user = db.session.get(User, row.user_id)
    if not user or not user.is_active_account:
        return jsonify({'success': False, 'message': 'Account unavailable'}), 401
    row.used_at = datetime.utcnow()
    db.session.commit()
    _start_user_session(user)
    current_app.logger.info(
        '[ANDROID-API] login complete username=%r user_id=%s',
        user.username, user.id,
    )
    return jsonify({'success': True, 'user': _user_payload()})


@mobile_api_bp.route('/logout', methods=['POST'])
@login_required
def api_logout():
    token = session.pop('app_session_token', None)
    if token:
        row = UserSession.query.filter_by(
            session_token=token, user_id=current_user.id,
        ).first()
        if row:
            row.ended_at = datetime.utcnow()
            db.session.commit()
    logout_user()
    return jsonify({'success': True})


@mobile_api_bp.route('/me', methods=['GET'])
@login_required
def api_me():
    return jsonify({'success': True, 'user': _user_payload()})


@mobile_api_bp.route('/my/<media_type>', methods=['GET'])
@login_required
def api_my_media(media_type):
    if media_type not in ('movies', 'shows'):
        return jsonify({'success': False, 'message': 'Use movies or shows'}), 400
    from routes.user_routes import _my_media
    singular = 'movie' if media_type == 'movies' else 'show'
    ctx = _my_media(singular)
    items = [
        serialize_media_item(row, singular) for row in (ctx.get('rows') or [])
    ]
    return jsonify({
        'success': True,
        'media_type': singular,
        'items': items,
        'filter': ctx.get('filt'),
        'filter_lists': ctx.get('filter_lists_payload') or [],
        'selected_lists': ctx.get('selected_lists') or [],
        'selected_names': ctx.get('selected_names') or [],
        'page': ctx.get('page') or 1,
        'pages': ctx.get('pages') or 1,
        'per_page': ctx.get('per_page') or 50,
        'total': ctx.get('total') or 0,
        'q': ctx.get('search_q') or '',
        'avail': ctx.get('avail') or '',
        'display': ctx.get('display_mode') or 'list',
        'title': ctx.get('title'),
    })


@mobile_api_bp.route('/search', methods=['GET'])
@login_required
def api_search():
    from routes.catalog_routes import _search_catalog
    ctx = _search_catalog()
    items = []
    for row in ctx.get('rows') or []:
        mt = row.get('media_type') or getattr(row.get('media'), 'media_type', None)
        items.append(serialize_media_item(row, mt))
    return jsonify({
        'success': True,
        'q': ctx.get('q') or '',
        'search_type': ctx.get('search_type') or 'both',
        'items': items,
        'page': ctx.get('page') or 1,
        'pages': ctx.get('pages') or 1,
        'per_page': ctx.get('per_page') or 20,
        'total': ctx.get('total') or 0,
        'hide_watched': bool(ctx.get('hide_watched')),
        'hide_lists': bool(ctx.get('hide_lists')),
        'fetch_error': ctx.get('fetch_error'),
    })


@mobile_api_bp.route('/shows/<int:trakt_id>/progress', methods=['GET'])
@login_required
def api_progress(trakt_id):
    from routes.user_routes import _load_progress_data
    result = _load_progress_data(trakt_id)
    if not result.get('ok'):
        return jsonify({
            'success': False,
            'message': result.get('message') or 'Could not load progress.',
        }), int(result.get('status') or 502)
    ctx = {k: v for k, v in result.items() if k != 'ok'}
    return jsonify({'success': True, **serialize_progress(ctx)})


@mobile_api_bp.route('/alerts', methods=['GET'])
@login_required
def api_alerts():
    from routes.user_routes import _collect_alert_cards
    ctx = _collect_alert_cards()
    return jsonify({
        'success': True,
        'unread_count': ctx.get('unread_count') or 0,
        'hide_read': bool(ctx.get('hide_read')),
        'items': [serialize_alert_card(card) for card in (ctx.get('cards') or [])],
    })


@mobile_api_bp.route('/alerts/read-all', methods=['POST'])
@login_required
def api_alerts_read_all():
    Notification.query.filter_by(
        user_id=current_user.id, is_read=False,
    ).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})


@mobile_api_bp.route('/alerts/<int:notif_id>/read', methods=['POST'])
@login_required
def api_alert_read(notif_id):
    row = Notification.query.filter_by(
        id=notif_id, user_id=current_user.id,
    ).first()
    if not row:
        return jsonify({'success': False, 'message': 'Alert not found'}), 404
    row.is_read = True
    db.session.commit()
    return jsonify({'success': True, 'is_read': True})


@mobile_api_bp.route('/alerts/<int:notif_id>/unread', methods=['POST'])
@login_required
def api_alert_unread(notif_id):
    row = Notification.query.filter_by(
        id=notif_id, user_id=current_user.id,
    ).first()
    if not row:
        return jsonify({'success': False, 'message': 'Alert not found'}), 404
    row.is_read = False
    db.session.commit()
    return jsonify({'success': True, 'is_read': False})


@mobile_api_bp.route('/episode/watched', methods=['POST'])
@login_required
def api_episode_watched():
    from routes.user_routes import api_episode_watched as impl
    return impl()


@mobile_api_bp.route(
    '/shows/<int:trakt_id>/seasons/<int:season_number>/watched',
    methods=['POST'],
)
@login_required
def api_season_watched(trakt_id, season_number):
    from routes.user_routes import api_season_watched as impl
    return impl(trakt_id, season_number)


@mobile_api_bp.route(
    '/shows/<int:trakt_id>/seasons/<int:season_number>/unwatched',
    methods=['POST'],
)
@login_required
def api_season_unwatched(trakt_id, season_number):
    from routes.user_routes import api_season_unwatched as impl
    return impl(trakt_id, season_number)


@mobile_api_bp.route('/pin/<media_type>/<int:trakt_id>', methods=['POST'])
@login_required
def api_pin(media_type, trakt_id):
    from routes.user_routes import api_pin_media
    return api_pin_media(media_type, trakt_id)


@mobile_api_bp.route('/watched/<media_type>/<int:trakt_id>', methods=['POST'])
@login_required
def api_watched(media_type, trakt_id):
    from routes.catalog_routes import api_watched as impl
    return impl(media_type, trakt_id)


@mobile_api_bp.route('/rating/<media_type>/<int:trakt_id>', methods=['POST'])
@login_required
def api_rating(media_type, trakt_id):
    from routes.catalog_routes import api_rating as impl
    return impl(media_type, trakt_id)


@mobile_api_bp.route('/favorite/<media_type>/<int:trakt_id>', methods=['POST'])
@login_required
def api_favorite(media_type, trakt_id):
    from routes.catalog_routes import api_favorite as impl
    return impl(media_type, trakt_id)


@mobile_api_bp.route(
    '/lists/membership/<media_type>/<int:trakt_id>',
    methods=['GET', 'POST'],
)
@login_required
def api_lists_membership(media_type, trakt_id):
    from routes.catalog_routes import api_lists_membership as impl
    return impl(media_type, trakt_id)
