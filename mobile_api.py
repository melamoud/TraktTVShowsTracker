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

from models import (
    MobileLoginToken, Notification, StreamingService, User, UserPreference,
    UserSession, UserStreamingService, db,
)
from services.mobile_payloads import (
    found_on_choice_links,
    found_on_service_choices,
    serialize_alert_card,
    serialize_alert_entry,
    serialize_media_detail,
    serialize_media_item,
    serialize_progress,
)
from services.seed import COMMON_GENRES
from services.streaming_matcher import (
    get_user_excluded_genres,
    get_user_genres_keywords,
    serialize_prefs,
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


def _serialize_calendar(cal):
    """Convert a web calendar context into a JSON-friendly Android payload."""
    if not cal:
        return None

    def _iso(value):
        return value.isoformat() if value else None

    return {
        'period': cal.get('period'),
        'label': cal.get('label'),
        'anchor': _iso(cal.get('anchor')),
        'prev_anchor': _iso(cal.get('prev_anchor')),
        'next_anchor': _iso(cal.get('next_anchor')),
        'today': _iso(cal.get('today')),
        'weekdays': cal.get('weekdays') or [],
        'extra_months': cal.get('extra_months') or [],
        'days': [
            {
                'date': _iso(day.get('date')),
                'in_month': bool(day.get('in_month')),
                'is_today': bool(day.get('is_today')),
                'events': [
                    {
                        'trakt_id': ev.get('trakt_id'),
                        'media_type': ev.get('media_type'),
                        'title': ev.get('title'),
                        'poster_url': ev.get('poster_url'),
                        'label': ev.get('label'),
                    }
                    for ev in (day.get('events') or [])
                ],
            }
            for day in (cal.get('days') or [])
        ],
    }


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
        'calendar': _serialize_calendar(ctx.get('calendar')),
        'title': ctx.get('title'),
        'found_on_choices': found_on_service_choices(current_user),
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
        'actor_q': ctx.get('actor_q') or '',
        'actor_id': ctx.get('actor_id') or None,
        'actor_name': ctx.get('actor_name') or '',
        'search_type': ctx.get('search_type') or 'both',
        'items': items,
        'page': ctx.get('page') or 1,
        'pages': ctx.get('pages') or 1,
        'per_page': ctx.get('per_page') or 20,
        'total': ctx.get('total') or 0,
        'hide_watched': bool(ctx.get('hide_watched')),
        'hide_lists': bool(ctx.get('hide_lists')),
        'year': ctx.get('year') or '',
        'genres': ctx.get('filter_genres') or [],
        'genre_choices': ctx.get('genre_choices') or [],
        'fetch_error': ctx.get('fetch_error'),
        'found_on_choices': found_on_service_choices(current_user),
    })


@mobile_api_bp.route('/catalog/<media_type>/<int:trakt_id>', methods=['GET'])
@login_required
def api_catalog_detail(media_type, trakt_id):
    from routes.catalog_routes import load_media_detail
    result = load_media_detail(media_type, trakt_id)
    if not result.get('ok'):
        return jsonify({
            'success': False,
            'message': result.get('message') or 'Title not found.',
        }), int(result.get('status') or 404)
    payload = serialize_media_detail(
        result['row'],
        media_type,
        result.get('cast') or [],
        found_on_service_choices(current_user),
    )
    return jsonify({'success': True, **payload})


@mobile_api_bp.route('/widget', methods=['GET'])
@login_required
def api_widget():
    from services.widget_feed import build_widget_feed
    return jsonify(build_widget_feed(current_user, request.args.get('mode') or 'shows'))


@mobile_api_bp.route('/found-on/choices', methods=['GET'])
@login_required
def api_found_on_choices():
    title = (request.args.get('title') or '').strip() or None
    year = None
    try:
        raw_year = (request.args.get('year') or '').strip()
        if raw_year:
            year = int(raw_year)
    except (TypeError, ValueError):
        year = None
    choices = found_on_service_choices(current_user)
    return jsonify({
        'success': True,
        'choices': choices,
        'choice_links': found_on_choice_links(title, year, choices),
    })


@mobile_api_bp.route('/found-on/<media_type>/<int:trakt_id>', methods=['POST'])
@login_required
def api_found_on(media_type, trakt_id):
    from routes.catalog_routes import api_found_on as impl
    return impl(media_type, trakt_id)


@mobile_api_bp.route('/favorite-actor/<int:person_id>', methods=['POST'])
@login_required
def api_favorite_actor(person_id):
    from routes.catalog_routes import api_favorite_actor as impl
    return impl(person_id)


@mobile_api_bp.route('/feedback/<media_type>/<int:trakt_id>', methods=['GET'])
@login_required
def api_feedback(media_type, trakt_id):
    from routes.catalog_routes import api_feedback as impl
    return impl(media_type, trakt_id)


@mobile_api_bp.route('/comment/<media_type>/<int:trakt_id>', methods=['POST'])
@login_required
def api_comment(media_type, trakt_id):
    from routes.catalog_routes import api_comment as impl
    return impl(media_type, trakt_id)


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
        'sort': ctx.get('sort') or 'desc',
        'group_shows': bool(ctx.get('group_shows')),
        'items': [serialize_alert_card(card) for card in (ctx.get('cards') or [])],
        'entries': [serialize_alert_entry(e) for e in (ctx.get('entries') or [])],
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
    from services.alerts import set_notification_read
    row = Notification.query.filter_by(
        id=notif_id, user_id=current_user.id,
    ).first()
    if not row:
        return jsonify({'success': False, 'message': 'Alert not found'}), 404
    set_notification_read(current_user.id, row, True)
    db.session.commit()
    return jsonify({'success': True, 'is_read': True})


@mobile_api_bp.route('/alerts/<int:notif_id>/unread', methods=['POST'])
@login_required
def api_alert_unread(notif_id):
    from services.alerts import set_notification_read
    row = Notification.query.filter_by(
        id=notif_id, user_id=current_user.id,
    ).first()
    if not row:
        return jsonify({'success': False, 'message': 'Alert not found'}), 404
    set_notification_read(current_user.id, row, False)
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


@mobile_api_bp.route('/alerts/pin/<media_type>/<int:trakt_id>', methods=['POST'])
@login_required
def api_alerts_pin(media_type, trakt_id):
    from routes.user_routes import api_alerts_pin as impl
    return impl(media_type, trakt_id)


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


@mobile_api_bp.route('/latest/<media_type>', methods=['GET'])
@login_required
def api_latest_media(media_type):
    """Latest movies or shows feed (Trakt DB updates) for the Android client."""
    if media_type not in ('movies', 'shows'):
        return jsonify({'success': False, 'message': 'Use movies or shows'}), 400
    from routes.catalog_routes import _ensure_latest_catalog, _latest_page_data

    singular = 'movie' if media_type == 'movies' else 'show'
    _ensure_latest_catalog(singular, load_older=(request.args.get('load_older') == '1'))
    ctx = _latest_page_data(singular)
    items = [
        serialize_media_item(row, singular) for row in (ctx.get('rows') or [])
    ]
    marker = ctx.get('marker')
    marker_payload = None
    if marker:
        marker_payload = {
            'trakt_id': marker.trakt_id,
            'title': marker.title,
            'listed_at': (
                marker.trakt_listed_at.isoformat()
                if marker.trakt_listed_at else None
            ),
        }
    return jsonify({
        'success': True,
        'media_type': singular,
        'items': items,
        'page': ctx.get('page') or 1,
        'pages': ctx.get('pages') or 1,
        'per_page': ctx.get('per_page') or 50,
        'total': ctx.get('total') or 0,
        'q': ctx.get('search_q') or '',
        'avail': ctx.get('avail') or '',
        'title': ctx.get('title'),
        'found_on_choices': found_on_service_choices(current_user),
        'hide_watched': ctx.get('hide_watched'),
        'hide_lists': ctx.get('hide_lists'),
        'match_only': ctx.get('match_only'),
        'recent_years': ctx.get('recent_years'),
        'has_more_older': ctx.get('has_more_older'),
        'marker': marker_payload,
        'marker_page': ctx.get('marker_page'),
    })


@mobile_api_bp.route('/recommendations/<media_type>', methods=['GET'])
@login_required
def api_recommendations(media_type):
    """Personalized Trakt recommendations for the Android client."""
    if media_type not in ('movies', 'shows'):
        return jsonify({'success': False, 'message': 'Use movies or shows'}), 400
    from routes.catalog_routes import _recommendations_page_data

    singular = 'movie' if media_type == 'movies' else 'show'
    ctx = _recommendations_page_data(singular)
    items = [
        serialize_media_item(row, singular) for row in (ctx.get('rows') or [])
    ]
    return jsonify({
        'success': True,
        'media_type': singular,
        'items': items,
        'page': ctx.get('page') or 1,
        'pages': ctx.get('pages') or 1,
        'per_page': ctx.get('per_page') or 50,
        'total': ctx.get('total') or 0,
        'q': ctx.get('search_q') or '',
        'avail': ctx.get('avail') or '',
        'title': ctx.get('title'),
        'found_on_choices': found_on_service_choices(current_user),
        'categories': ctx.get('categories') or [],
        'category': ctx.get('category') or 'all',
        'hide_watched': ctx.get('hide_watched'),
        'hide_wishlist': ctx.get('hide_wishlist'),
        'on_my_services': ctx.get('on_my_services'),
        'match_only': ctx.get('match_only'),
        'has_match_prefs': ctx.get('has_match_prefs'),
        'user_service_names': ctx.get('user_service_names') or [],
        'filter_genres': ctx.get('filter_genres') or [],
        'year': ctx.get('year') or '',
    })


@mobile_api_bp.route('/preferences', methods=['GET'])
@login_required
def api_preferences():
    """Return the current user's minimal preferences for the Android client."""
    prefs = current_user.preferences
    defaults = StreamingService.query.filter_by(is_default=True).order_by(StreamingService.name).all()
    owned = UserStreamingService.query.filter_by(user_id=current_user.id).all()
    selected = {
        row.streaming_service_id
        for row in owned
        if not row.is_custom and row.streaming_service_id
    }
    customs = [
        {
            'id': row.id,
            'name': row.custom_name,
            'url': row.custom_url,
            'search_template': row.custom_search_template,
            'note': row.custom_note,
        }
        for row in owned if row.is_custom
    ]
    user_genres, user_keywords = get_user_genres_keywords(current_user)
    user_excluded = get_user_excluded_genres(current_user)
    from services.cast_service import list_favorite_actors
    return jsonify({
        'success': True,
        'defaults': [
            {'id': svc.id, 'name': svc.name, 'selected': svc.id in selected}
            for svc in defaults
        ],
        'customs': customs,
        'common_genres': COMMON_GENRES,
        'genres': user_genres,
        'keywords': user_keywords,
        'excluded_genres': user_excluded,
        'alerts': {
            'release_day': bool(getattr(prefs, 'alert_release_day', True)),
            'new_streaming': bool(getattr(prefs, 'alert_new_streaming', True)),
            'episode_aired': bool(getattr(prefs, 'alert_episode_aired', True)),
            'list_add': bool(getattr(prefs, 'alert_list_add', True)),
            'season_streaming': bool(getattr(prefs, 'alert_season_streaming', True)),
            'favorite_actor': bool(getattr(prefs, 'alert_favorite_actor', True)),
            'favorite_actor_match_only': bool(getattr(prefs, 'alert_favorite_actor_match_only', True)),
            'new_user_login': bool(getattr(prefs, 'alert_new_user_login', True)) if current_user.is_admin else False,
        },
        'favorite_actors': [
            {'trakt_id': p.trakt_id, 'name': p.name, 'headshot_url': p.headshot_url}
            for p in list_favorite_actors(current_user)
        ],
        'prefs_reminder_disabled': bool(getattr(prefs, 'prefs_reminder_disabled', False)),
    })


@mobile_api_bp.route('/preferences', methods=['POST'])
@login_required
def api_preferences_save():
    """Save the current user's minimal preferences from the Android client."""
    prefs = current_user.preferences
    if not prefs:
        prefs = UserPreference(user_id=current_user.id)
        db.session.add(prefs)
        db.session.commit()

    data = _json_body()
    import json

    def _int_ids(key):
        raw = data.get(key) or []
        if not isinstance(raw, list):
            return set()
        out = set()
        for x in raw:
            if isinstance(x, int):
                out.add(x)
            elif isinstance(x, str) and x.isdigit():
                out.add(int(x))
        return out

    selected_ids = _int_ids('service_ids')
    UserStreamingService.query.filter_by(
        user_id=current_user.id, is_custom=False,
    ).delete(synchronize_session=False)
    for sid in selected_ids:
        db.session.add(UserStreamingService(
            user_id=current_user.id, streaming_service_id=sid, is_custom=False,
        ))

    remove_custom_ids = _int_ids('remove_custom_ids')
    if remove_custom_ids:
        UserStreamingService.query.filter(
            UserStreamingService.user_id == current_user.id,
            UserStreamingService.is_custom.is_(True),
            UserStreamingService.id.in_(remove_custom_ids),
        ).delete(synchronize_session=False)

    for custom in data.get('custom_services', []):
        if not isinstance(custom, dict):
            continue
        name = (custom.get('name') or '').strip()
        if not name:
            continue
        existing = UserStreamingService.query.filter_by(
            user_id=current_user.id, is_custom=True, custom_name=name,
        ).first()
        if existing:
            existing.custom_url = (custom.get('url') or '').strip() or None
            existing.custom_search_template = (custom.get('search_template') or '').strip() or None
            existing.custom_note = (custom.get('note') or '').strip() or None
        else:
            db.session.add(UserStreamingService(
                user_id=current_user.id,
                is_custom=True,
                custom_name=name,
                custom_url=(custom.get('url') or '').strip() or None,
                custom_search_template=(custom.get('search_template') or '').strip() or None,
                custom_note=(custom.get('note') or '').strip() or None,
            ))

    genres = [
        g.strip() for g in data.get('genres', [])
        if isinstance(g, str) and g.strip()
    ]
    keywords = [
        k.strip() for k in data.get('keywords', [])
        if isinstance(k, str) and k.strip()
    ]
    excluded = [
        g.strip() for g in data.get('excluded_genres', [])
        if isinstance(g, str) and g.strip()
    ]
    excluded_fold = {g.casefold() for g in excluded}
    genres = [g for g in genres if g.casefold() not in excluded_fold]
    g_json, k_json = serialize_prefs(genres, keywords)
    excluded_json, _ = serialize_prefs(excluded, [])
    prefs.genres_json = g_json
    prefs.keywords_json = k_json
    prefs.excluded_genres_json = excluded_json

    if genres or keywords:
        prefs.onboarding_completed_at = prefs.onboarding_completed_at or datetime.utcnow()
        prefs.prefs_reminder_disabled = False
        prefs.prefs_reminder_snooze_until = None

    alerts = data.get('alerts')
    if isinstance(alerts, dict):
        prefs.alert_release_day = bool(alerts.get('release_day', prefs.alert_release_day))
        prefs.alert_new_streaming = bool(alerts.get('new_streaming', prefs.alert_new_streaming))
        prefs.alert_episode_aired = bool(alerts.get('episode_aired', prefs.alert_episode_aired))
        prefs.alert_list_add = bool(alerts.get('list_add', prefs.alert_list_add))
        prefs.alert_season_streaming = bool(alerts.get('season_streaming', prefs.alert_season_streaming))
        prefs.alert_favorite_actor = bool(alerts.get('favorite_actor', prefs.alert_favorite_actor))
        prefs.alert_favorite_actor_match_only = bool(alerts.get('favorite_actor_match_only', prefs.alert_favorite_actor_match_only))
        if current_user.is_admin:
            prefs.alert_new_user_login = bool(alerts.get('new_user_login', prefs.alert_new_user_login))

    remove_actor_ids = _int_ids('remove_favorite_actor_ids')
    if remove_actor_ids:
        from models import CachedPerson, UserFavoriteActor
        person_ids = [
            p.id for p in CachedPerson.query.filter(
                CachedPerson.trakt_id.in_(remove_actor_ids)
            ).all()
        ]
        if person_ids:
            UserFavoriteActor.query.filter(
                UserFavoriteActor.user_id == current_user.id,
                UserFavoriteActor.person_id.in_(person_ids),
            ).delete(synchronize_session=False)

    if 'prefs_reminder_disabled' in data:
        prefs.prefs_reminder_disabled = bool(data.get('prefs_reminder_disabled'))

    prefs.updated_at = datetime.utcnow()
    db.session.commit()
    db.session.expire(current_user)

    return jsonify({'success': True})


@mobile_api_bp.route('/review-marker/<media_type>/<int:trakt_id>', methods=['POST'])
@login_required
def api_review_marker(media_type, trakt_id):
    from routes.catalog_routes import api_review_marker as impl
    return impl(media_type, trakt_id)


@mobile_api_bp.route('/review-marker/<media_type>/clear', methods=['POST'])
@login_required
def api_review_marker_clear(media_type):
    from routes.catalog_routes import api_review_marker_clear as impl
    return impl(media_type)


@mobile_api_bp.route('/review-marker/<media_type>/caught-up', methods=['POST'])
@login_required
def api_review_marker_caught_up(media_type):
    from routes.catalog_routes import api_review_marker_caught_up as impl
    return impl(media_type)


@mobile_api_bp.route('/sync-catalog/<media_type>', methods=['POST'])
@login_required
def api_sync_catalog(media_type):
    from routes.catalog_routes import api_sync_catalog as impl
    return impl(media_type)


@mobile_api_bp.route('/recommendations/<media_type>/<int:trakt_id>/hide', methods=['POST'])
@login_required
def api_hide_recommendation(media_type, trakt_id):
    from routes.catalog_routes import api_hide_recommendation as impl
    return impl(media_type, trakt_id)


@mobile_api_bp.route('/lists/create', methods=['POST'])
@login_required
def api_create_list():
    from routes.user_routes import api_create_trakt_list as impl
    return impl()


@mobile_api_bp.route('/lists/<list_id>/delete', methods=['POST'])
@login_required
def api_delete_list(list_id):
    from routes.user_routes import api_delete_trakt_list as impl
    return impl(list_id)
