"""
User routes: preferences, my movies/shows, series progress, notifications, help.
"""

import re
from datetime import date, datetime, timedelta

from flask import (
    Blueprint, current_app, flash, jsonify, redirect, render_template,
    request, session, url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import String, and_, case, cast, extract, or_


def _parse_air_datetime(value: str | None) -> datetime | None:
    """Parse Trakt first_aired / released timestamps to naive UTC datetime."""
    if not value:
        return None
    try:
        text = str(value).strip().replace('Z', '+00:00')
        if len(text) == 10 and text[4] == '-' and text[7] == '-':
            return datetime.fromisoformat(text)
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        return None


def _episode_air_info(ep: dict, *, progress_says_aired: bool | None) -> dict:
    """
    Build air-date display fields for an episode.

    Returns aired (bool), air_date (datetime|None), air_label (str).

    When Trakt progress already marks the episode as aired, trust that over a
    still-future first_aired timestamp (timezone / same-day air-time skew).
    """
    air_dt = _parse_air_datetime(ep.get('first_aired')) or _parse_air_datetime(ep.get('released'))
    now = datetime.utcnow()
    if air_dt is not None:
        label = air_dt.strftime('%Y-%m-%d')
        if progress_says_aired is not None:
            is_aired = bool(progress_says_aired)
        else:
            is_aired = air_dt <= now
        if is_aired:
            air_label = f'Aired {label}'
        else:
            air_label = f'Airs {label} · Not aired yet'
    elif progress_says_aired is not None:
        is_aired = bool(progress_says_aired)
        air_label = 'Aired' if is_aired else 'Not aired yet'
        air_dt = None
    else:
        is_aired = True
        air_label = 'Air date unknown'
        air_dt = None
    return {'aired': is_aired, 'air_date': air_dt, 'air_label': air_label}

from help_utils import get_help_toc, render_help_markdown
from models import (
    CachedMedia, MediaFoundOn, MediaProviderAvailability, Notification,
    ReviewMarker, StreamingService, StreamingServiceSuggestion,
    UserCalendarEvent, UserListMembership, UserMediaState, UserPreference,
    UserStreamingService, db,
)
from services import trakt_client
from services.alerts import STREAMING_OFFER_TYPES
from services.seed import COMMON_GENRES
from services.streaming_matcher import (
    WATCHLIST_LIST_ID,
    filter_visible_list_ids,
    get_alert_enabled_list_ids,
    get_default_selected_list_ids,
    get_hidden_list_ids,
    get_user_genres_keywords,
    serialize_prefs,
    split_csv_terms,
    user_has_match_prefs,
)
from routes.catalog_routes import _pagination_pages, _per_page
from services.sync_jobs import (
    ensure_media_cached,
    enrich_media_list_for_display,
)
from services.user_media_sync import ensure_user_media_fresh

user_bp = Blueprint('user', __name__)


def _personal_lists(user) -> list[dict]:
    """Personal lists from SQLite when the membership TTL is fresh."""
    from services.trakt_cache import (
        cached_personal_lists,
        cache_is_fresh,
        replace_cached_personal_lists,
    )
    if cache_is_fresh(getattr(user, 'last_sync_at', None)):
        return cached_personal_lists(user)
    lists = trakt_client.get_personal_lists(user)
    replace_cached_personal_lists(user.id, lists)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    return lists


def _ensure_prefs() -> UserPreference:
    """Return the current user's preference row, creating it if needed."""
    prefs = current_user.preferences
    if not prefs:
        prefs = UserPreference(user_id=current_user.id)
        db.session.add(prefs)
        db.session.commit()
    return prefs


@user_bp.route('/preferences/setup', methods=['GET', 'POST'])
@login_required
def preferences_setup():
    """First-login wizard: pick genres and keywords for purple Latest filtering."""
    prefs = _ensure_prefs()
    if request.method == 'POST':
        action = (request.form.get('action') or 'save').strip()
        if action == 'skip':
            prefs.onboarding_completed_at = datetime.utcnow()
            prefs.prefs_reminder_snooze_until = datetime.utcnow() + timedelta(days=1)
            db.session.commit()
            flash(
                'Skipped for now. Latest will show everything until you add genres/keywords. '
                'We’ll remind you tomorrow — without filters, preference matching stays off.',
                'warning',
            )
            return redirect(url_for('catalog.home'))

        genres = split_csv_terms(request.form.get('genres', ''))
        genres.extend(request.form.getlist('genre_checks'))
        keywords = split_csv_terms(request.form.get('keywords', ''))
        g_json, k_json = serialize_prefs(genres, keywords)
        import json
        if not (json.loads(g_json or '[]') or json.loads(k_json or '[]')):
            flash('Pick at least one genre or keyword so Latest can filter to matches.', 'danger')
            return redirect(url_for('user.preferences_setup'))
        prefs.genres_json = g_json
        prefs.keywords_json = k_json
        prefs.updated_at = datetime.utcnow()
        prefs.onboarding_completed_at = datetime.utcnow()
        prefs.prefs_reminder_disabled = False
        prefs.prefs_reminder_snooze_until = None
        db.session.commit()
        flash('Preferences saved. Latest defaults to purple matches only — use Show all anytime.', 'success')
        return redirect(url_for('catalog.latest_movies'))

    import json
    user_genres = json.loads(prefs.genres_json or '[]')
    user_keywords = json.loads(prefs.keywords_json or '[]')
    return render_template(
        'preferences_setup.html',
        common_genres=COMMON_GENRES,
        user_genres=user_genres,
        user_keywords=user_keywords,
        keywords_text=', '.join(user_keywords),
    )


@user_bp.route('/api/prefs-reminder', methods=['POST'])
@login_required
def api_prefs_reminder():
    """Snooze or permanently disable the empty-prefs reminder banner."""
    prefs = _ensure_prefs()
    payload = request.json or {}
    action = (payload.get('action') or '').strip()
    if action == 'snooze':
        prefs.prefs_reminder_snooze_until = datetime.utcnow() + timedelta(days=1)
        db.session.commit()
        return jsonify({'success': True, 'action': 'snooze'})
    if action == 'disable':
        prefs.prefs_reminder_disabled = True
        prefs.onboarding_completed_at = prefs.onboarding_completed_at or datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True, 'action': 'disable'})
    if action == 'enable':
        prefs.prefs_reminder_disabled = False
        prefs.prefs_reminder_snooze_until = None
        db.session.commit()
        return jsonify({'success': True, 'action': 'enable'})
    return jsonify({'success': False, 'message': 'action must be snooze, disable, or enable'}), 400


@user_bp.route('/preferences', methods=['GET', 'POST'])
@login_required
def preferences():
    """Configure streaming services, genres, and keywords."""
    prefs = _ensure_prefs()

    defaults = StreamingService.query.filter_by(is_default=True).order_by(StreamingService.name).all()
    marker_prompt = False

    if request.method == 'POST':
        selected_ids = set(int(x) for x in request.form.getlist('service_ids') if x.isdigit())
        remove_custom_ids = set(
            int(x) for x in request.form.getlist('remove_custom_ids') if x.isdigit()
        )

        # Replace default-service picks (leave customs alone unless removed).
        UserStreamingService.query.filter_by(
            user_id=current_user.id, is_custom=False
        ).delete(synchronize_session=False)
        for sid in selected_ids:
            db.session.add(UserStreamingService(
                user_id=current_user.id, streaming_service_id=sid, is_custom=False
            ))

        if remove_custom_ids:
            UserStreamingService.query.filter(
                UserStreamingService.user_id == current_user.id,
                UserStreamingService.is_custom.is_(True),
                UserStreamingService.id.in_(remove_custom_ids),
            ).delete(synchronize_session=False)

        custom_name = (request.form.get('custom_name') or '').strip()
        custom_url = (request.form.get('custom_url') or '').strip() or None
        custom_search_template = (request.form.get('custom_search_template') or '').strip() or None
        custom_note = (request.form.get('custom_note') or '').strip() or None
        if custom_name:
            existing = UserStreamingService.query.filter_by(
                user_id=current_user.id, is_custom=True, custom_name=custom_name
            ).first()
            if existing:
                existing.custom_url = custom_url
                existing.custom_search_template = custom_search_template
                existing.custom_note = custom_note
            else:
                db.session.add(UserStreamingService(
                    user_id=current_user.id,
                    is_custom=True,
                    custom_name=custom_name,
                    custom_url=custom_url,
                    custom_search_template=custom_search_template,
                    custom_note=custom_note,
                ))
            if request.form.get('suggest_default') == '1':
                already = StreamingServiceSuggestion.query.filter_by(
                    user_id=current_user.id, name=custom_name, status='pending'
                ).first()
                if not already:
                    db.session.add(StreamingServiceSuggestion(
                        user_id=current_user.id,
                        name=custom_name,
                        url=custom_url,
                        note=custom_note,
                    ))
                    from models import User
                    for admin in User.query.filter_by(is_admin=True, is_active_account=True).all():
                        db.session.add(Notification(
                            user_id=admin.id,
                            alert_type='service_suggestion',
                            title='New streaming service suggestion',
                            message=(
                                f'{current_user.username} suggested '
                                f'"{custom_name}" as a default service.'
                            ),
                            link='/admin/streaming-services',
                        ))
            flash(f'Custom service "{custom_name}" saved.', 'success')

        # Update search templates on existing customs (even when not adding a new one).
        for row in UserStreamingService.query.filter_by(
            user_id=current_user.id, is_custom=True
        ).all():
            field = f'custom_search_template_{row.id}'
            if field not in request.form:
                continue
            row.custom_search_template = (request.form.get(field) or '').strip() or None

        old_genres, old_keywords = get_user_genres_keywords(current_user)
        genres = split_csv_terms(request.form.get('genres', ''))
        genres.extend(request.form.getlist('genre_checks'))
        keywords = split_csv_terms(request.form.get('keywords', ''))
        g_json, k_json = serialize_prefs(genres, keywords)
        prefs.genres_json = g_json
        prefs.keywords_json = k_json

        # List prefs: show in menu, auto-select, and which lists generate alerts.
        import json
        if request.form.get('lists_prefs_present') == '1':
            known_list_ids = {
                str(x).strip()
                for x in request.form.getlist('known_list_ids')
                if str(x).strip()
            }
            shown_list_ids = {
                str(x).strip()
                for x in request.form.getlist('show_list_ids')
                if str(x).strip()
            }
            default_raw = {
                str(x).strip()
                for x in request.form.getlist('default_list_ids')
                if str(x).strip()
            }
            alert_raw = {
                str(x).strip()
                for x in request.form.getlist('alert_list_ids')
                if str(x).strip()
            }
            if known_list_ids:
                hidden_ids = sorted(known_list_ids - shown_list_ids)
                prefs.hidden_list_ids_json = json.dumps(hidden_ids)
                # Auto-select / Alerts only apply to Wishlist + lists still shown.
                allowed_defaults = {WATCHLIST_LIST_ID} | shown_list_ids
            else:
                allowed_defaults = {WATCHLIST_LIST_ID} | set(
                    lid for lid in (default_raw | alert_raw)
                    if lid != WATCHLIST_LIST_ID
                )
            default_ids = sorted(
                lid for lid in default_raw
                if lid in allowed_defaults
            )
            alert_ids = sorted(
                lid for lid in alert_raw
                if lid in allowed_defaults
            )
            prefs.default_selected_list_ids_json = json.dumps(default_ids)
            prefs.alert_enabled_list_ids_json = json.dumps(alert_ids)

        if request.form.get('alerts_prefs_present') == '1':
            prefs.alert_release_day = request.form.get('alert_release_day') == '1'
            prefs.alert_new_streaming = request.form.get('alert_new_streaming') == '1'
            prefs.alert_episode_aired = request.form.get('alert_episode_aired') == '1'
            prefs.alert_list_add = request.form.get('alert_list_add') == '1'
            if current_user.is_admin:
                prefs.alert_new_user_login = request.form.get('alert_new_user_login') == '1'

        # Favorite actors: remove via Preferences checkboxes (add from title detail).
        remove_actor_ids = {
            int(x) for x in request.form.getlist('remove_favorite_actor_ids') if str(x).isdigit()
        }
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

        prefs.updated_at = datetime.utcnow()
        new_genres = json.loads(g_json or '[]')
        new_keywords = json.loads(k_json or '[]')
        match_filters_changed = (
            sorted(x.lower() for x in old_genres) != sorted(x.lower() for x in new_genres)
            or sorted(x.lower() for x in old_keywords) != sorted(x.lower() for x in new_keywords)
        )
        if new_genres or new_keywords:
            prefs.onboarding_completed_at = prefs.onboarding_completed_at or datetime.utcnow()
            prefs.prefs_reminder_disabled = False
            prefs.prefs_reminder_snooze_until = None
        db.session.commit()
        db.session.expire(current_user)
        flash('Preferences saved.', 'success')
        if match_filters_changed:
            session['marker_prompt_after_prefs'] = True
            return redirect(url_for('user.preferences', marker_prompt=1))
        return redirect(url_for('user.preferences'))

    owned = UserStreamingService.query.filter_by(user_id=current_user.id).all()
    selected = {
        row.streaming_service_id
        for row in owned
        if not row.is_custom and row.streaming_service_id
    }
    customs = [row for row in owned if row.is_custom]
    import json
    user_genres = json.loads(prefs.genres_json or '[]')
    user_keywords = json.loads(prefs.keywords_json or '[]')
    hidden_list_ids = set(get_hidden_list_ids(current_user))
    default_selected_list_ids = set(get_default_selected_list_ids(current_user))
    alert_enabled_list_ids = set(get_alert_enabled_list_ids(current_user))
    trakt_lists = []
    trakt_lists_error = None
    try:
        trakt_lists = _personal_lists(current_user)
    except Exception as exc:
        current_app.logger.warning('Could not load Trakt lists for preferences: %s', exc)
        trakt_lists_error = str(exc)
    if request.args.get('marker_prompt') == '1' or session.pop('marker_prompt_after_prefs', None):
        marker_prompt = True
    markers = {
        'movie': ReviewMarker.query.filter_by(user_id=current_user.id, media_type='movie').first(),
        'show': ReviewMarker.query.filter_by(user_id=current_user.id, media_type='show').first(),
    }
    from services.cast_service import list_favorite_actors
    favorite_actors = list_favorite_actors(current_user)
    return render_template(
        'preferences.html',
        defaults=defaults,
        selected=selected,
        customs=customs,
        common_genres=COMMON_GENRES,
        user_genres=user_genres,
        user_keywords=user_keywords,
        keywords_text=', '.join(user_keywords),
        marker_prompt=marker_prompt,
        markers=markers,
        prefs_reminder_disabled=bool(prefs.prefs_reminder_disabled),
        trakt_lists=trakt_lists,
        hidden_list_ids=hidden_list_ids,
        default_selected_list_ids=default_selected_list_ids,
        alert_enabled_list_ids=alert_enabled_list_ids,
        watchlist_list_id=WATCHLIST_LIST_ID,
        trakt_lists_error=trakt_lists_error,
        alert_release_day=bool(getattr(prefs, 'alert_release_day', True)),
        alert_new_streaming=bool(getattr(prefs, 'alert_new_streaming', True)),
        alert_episode_aired=bool(getattr(prefs, 'alert_episode_aired', True)),
        alert_list_add=bool(getattr(prefs, 'alert_list_add', True)),
        alert_new_user_login=bool(getattr(prefs, 'alert_new_user_login', True)),
        favorite_actors=favorite_actors,
    )


@user_bp.route('/my/movies')
@login_required
def my_movies():
    """Movies on the user's Trakt watchlist and/or watched history."""
    return render_template('my_media.html', **_my_media('movie'))


@user_bp.route('/my/shows')
@login_required
def my_shows():
    """Shows on the user's Trakt watchlist and/or watched history."""
    return render_template('my_media.html', **_my_media('show'))


def _my_filter_lists(user) -> list[dict]:
    """Wishlist + personal lists shown in Preferences (for My page filter buttons)."""
    hidden = set(get_hidden_list_ids(user))
    out = [{'id': WATCHLIST_LIST_ID, 'name': 'Wishlist', 'kind': 'watchlist'}]
    try:
        for lst in _personal_lists(user):
            if lst['id'] in hidden:
                continue
            out.append({
                'id': lst['id'],
                'name': lst['name'],
                'kind': 'list',
                'slug': lst.get('slug') or '',
            })
    except Exception as exc:
        current_app.logger.warning('Could not load lists for my-media filters: %s', exc)
    return out


def _resolve_selected_lists(user, filter_lists: list[dict], view: str) -> list[str]:
    """Selected list ids from query args, saved view prefs, or Preferences defaults."""
    from services import view_prefs

    shown_ids = {lst['id'] for lst in filter_lists}
    defaults = filter_visible_list_ids(user, get_default_selected_list_ids(user))
    return view_prefs.resolve_lists(
        user, view, shown_ids, defaults=defaults,
    )


def _trakt_ids_for_lists(user_id: int, media_type: str, selected_lists: list[str]) -> set[int]:
    """Union of title ids on the selected Wishlist / personal lists."""
    ids: set[int] = set()
    if WATCHLIST_LIST_ID in selected_lists:
        for tid, in UserMediaState.query.filter_by(
            user_id=user_id, media_type=media_type, on_watchlist=True
        ).with_entities(UserMediaState.trakt_id).all():
            ids.add(int(tid))
    personal_ids = [lid for lid in selected_lists if lid != WATCHLIST_LIST_ID]
    if personal_ids:
        for tid, in UserListMembership.query.filter(
            UserListMembership.user_id == user_id,
            UserListMembership.media_type == media_type,
            UserListMembership.list_id.in_(personal_ids),
        ).with_entities(UserListMembership.trakt_id).all():
            ids.add(int(tid))
    return ids


def _calendar_trakt_ids(
    user_id: int, media_type: str, filt: str, list_trakt_ids: set[int],
) -> set[int]:
    """Title ids on selected lists whose air/release events the calendar should show."""
    if not list_trakt_ids:
        return set()
    if filt == 'watched':
        watched_ids = {
            int(tid)
            for tid, in UserMediaState.query.filter(
                UserMediaState.user_id == user_id,
                UserMediaState.media_type == media_type,
                UserMediaState.watched.is_(True),
                UserMediaState.trakt_id.in_(list_trakt_ids),
            ).with_entities(UserMediaState.trakt_id).all()
        }
        return watched_ids
    if filt in ('unwatched', 'unwatched_episodes'):
        # Same membership set as list/both for calendar — unfinished detail is
        # hard to express for air-date grids; list scope is what matters.
        unfinished = {
            int(tid)
            for tid, in UserMediaState.query.filter(
                UserMediaState.user_id == user_id,
                UserMediaState.media_type == media_type,
                UserMediaState.trakt_id.in_(list_trakt_ids),
                or_(
                    UserMediaState.watched.is_(False),
                    and_(
                        UserMediaState.progress_percent.isnot(None),
                        UserMediaState.progress_percent < 100,
                    ),
                    UserMediaState.progress_detail_at.is_(None),
                ),
            ).with_entities(UserMediaState.trakt_id).all()
        }
        return unfinished
    # lists / both — every selected-list title
    return set(list_trakt_ids)


def _my_media(media_type: str):
    """Shared my-movies / my-shows listing with multi-list + watched filters."""
    import json

    from services import view_prefs

    view = f'my_{media_type}s'
    allowed_filters = ('lists', 'watched', 'both', 'unwatched', 'unwatched_episodes')
    if 'filter' in request.args:
        filt = view_prefs.resolve_choice(
            current_user, view, 'filter', 'filter',
            allowed=allowed_filters, default='lists',
        )
    else:
        stored = view_prefs.get_view(current_user, view).get('filter')
        filt = stored if stored in allowed_filters else 'lists'
    # Legacy bookmark: wishlist → lists mode.
    if filt == 'wishlist':
        filt = 'lists'
    # Movies have no episode progress — map the show filter name if saved/linked.
    if media_type == 'movie' and filt == 'unwatched_episodes':
        filt = 'unwatched'
    if media_type == 'show' and filt == 'unwatched':
        filt = 'unwatched_episodes'

    # Local DB is a cache: auto-sync when Trakt last_activities advanced
    # (wishlist / watched / lists). Manual Refresh forces a full pull and
    # queues a background cycle for progress/episode data (page never blocks).
    try:
        synced = ensure_user_media_fresh(
            current_user,
            media_types=(media_type,),
            force=request.args.get('refresh') == '1',
        )
        if request.args.get('refresh') == '1':
            from services.shows_cache import queue_user_media_cycle
            queue_user_media_cycle(current_app._get_current_object(), current_user.id)
            flash(
                'Updated from Trakt. Episode and progress data refresh in the '
                'background — check back in a minute.',
                'success',
            )
        # New shows discovered by the sync are last-aired-seeded inside
        # sync_user_media_state (bounded), so Newest-aired picks them up.
    except Exception as exc:
        current_app.logger.warning('Sync before my-media failed: %s', exc)
        flash('Could not refresh from Trakt right now. Showing cached titles.', 'warning')

    filter_lists = _my_filter_lists(current_user)
    selected_lists = _resolve_selected_lists(current_user, filter_lists, view)
    list_trakt_ids = _trakt_ids_for_lists(current_user.id, media_type, selected_lists)
    search_q = (request.args.get('q') or '').strip()
    if len(search_q) < 2:
        search_q = ''
    from services.list_filters import (
        advanced_context, parse_year_filter, resolve_advanced,
    )
    year, filter_genres = resolve_advanced(current_user, view)
    year_range = parse_year_filter(year)
    from services.availability import (
        normalize_avail, theater_window_bounds, upcoming_after,
    )
    if 'avail' in request.args:
        avail = normalize_avail(request.args.get('avail'))
        view_prefs.update_view(current_user, view, avail=avail)
    else:
        stored_avail = view_prefs.get_view(current_user, view).get('avail')
        avail = normalize_avail(stored_avail if isinstance(stored_avail, str) else None)

    # View mode: List (rows), calendar grid, or newest-aired sort.
    display_mode = view_prefs.resolve_choice(
        current_user, view, 'display', 'display',
        allowed=('list', 'daily', 'weekly', 'monthly', 'newest_aired'), default='list',
    )
    calendar_ctx = None
    if display_mode in ('daily', 'weekly', 'monthly'):
        from services import calendar_view as cal_view
        try:
            anchor_str = (request.args.get('cal_date') or '').strip()
            anchor = date.fromisoformat(anchor_str) if anchor_str else date.today()
        except ValueError:
            anchor = date.today()
        cal_start, cal_end = cal_view.period_bounds(display_mode, anchor)
        cal_days = (cal_end - cal_start).days + 1
        try:
            cal_view.ensure_user_calendar_fresh(
                current_user, cal_start, cal_days,
            )
        except Exception as exc:
            current_app.logger.warning('Calendar sync failed: %s', exc)
        cal_ids = _calendar_trakt_ids(
            current_user.id, media_type, filt, list_trakt_ids,
        )
        calendar_ctx = cal_view.build_calendar_view(
            current_user.id, media_type, display_mode, anchor, cal_ids,
        )
        if not cal_ids and filt in ('lists', 'unwatched', 'unwatched_episodes', 'watched', 'both'):
            flash(
                'Calendar covers titles on your selected lists — nothing matches '
                'the current filters.',
                'info',
            )

    # My movies/shows are always scoped to selected lists. Watched / Both /
    # Unwatched are status sub-filters within that membership — never pull in
    # watch-history-only titles that are off every selected list.
    q = UserMediaState.query.filter_by(user_id=current_user.id, media_type=media_type)
    if not list_trakt_ids:
        q = q.filter(UserMediaState.trakt_id == -1)
    elif filt == 'watched':
        q = q.filter(
            UserMediaState.trakt_id.in_(list_trakt_ids),
            UserMediaState.watched.is_(True),
        )
    elif filt == 'unwatched':
        q = q.filter(
            UserMediaState.trakt_id.in_(list_trakt_ids),
            UserMediaState.watched.is_(False),
        )
    elif filt == 'unwatched_episodes':
        # Still has something to watch among selected-list titles.
        # Only trust progress>=100 when progress_detail_at was set from a real
        # episode summary (otherwise old fake 100%s hide shows like Lioness).
        trusted_complete = and_(
            UserMediaState.progress_percent.isnot(None),
            UserMediaState.progress_percent >= 100,
            UserMediaState.progress_detail_at.isnot(None),
        )
        q = q.filter(
            UserMediaState.trakt_id.in_(list_trakt_ids),
            ~trusted_complete,
        )
    else:
        # lists / both — every title on the selected lists
        q = q.filter(UserMediaState.trakt_id.in_(list_trakt_ids))

    # Title search and/or availability filters need CachedMedia (before pagination).
    # Backfill missing titles for the filtered candidate set first — otherwise
    # q= cannot match rows that only exist in UserMediaState (Search page used
    # to "unlock" them by upserting CachedMedia as a side effect).
    needs_media_join = bool(search_q) or bool(avail) or bool(year_range) or bool(filter_genres)
    if needs_media_join:
        # Snapshot ids without mutating `q` (legacy Query.with_entities is in-place).
        candidate_ids = [
            int(tid)
            for tid in db.session.scalars(
                q.statement.with_only_columns(
                    UserMediaState.trakt_id,
                    maintain_column_froms=True,
                ).distinct()
            ).all()
        ]
        try:
            ensure_media_cached(media_type, candidate_ids)
        except Exception as exc:
            current_app.logger.warning(
                'Title backfill before my-media filter failed: %s', exc,
            )
        q = q.outerjoin(
            CachedMedia,
            and_(
                CachedMedia.media_type == UserMediaState.media_type,
                CachedMedia.trakt_id == UserMediaState.trakt_id,
            ),
        )
    if search_q:
        like = f'%{search_q}%'
        q = q.filter(or_(
            CachedMedia.title.ilike(like),
            cast(CachedMedia.year, String).ilike(like),
        ))
    if year_range:
        ymin, ymax = year_range
        year_col = CachedMedia.year
        released_year = extract('year', CachedMedia.released_at)
        q = q.filter(or_(
            and_(year_col.isnot(None), year_col >= ymin, year_col <= ymax),
            and_(
                year_col.is_(None),
                CachedMedia.released_at.isnot(None),
                released_year >= ymin,
                released_year <= ymax,
            ),
        ))
    if filter_genres:
        q = q.filter(or_(*[
            CachedMedia.genres_json.ilike(f'%{g}%') for g in filter_genres
        ]))
    if avail == 'upcoming':
        q = q.filter(CachedMedia.released_at >= upcoming_after())
    elif avail == 'theater':
        start, end = theater_window_bounds()
        q = q.filter(
            CachedMedia.released_at >= start,
            CachedMedia.released_at <= end,
        )
    elif avail == 'streaming':
        streaming_ids = (
            db.session.query(MediaProviderAvailability.cached_media_id)
            .filter(MediaProviderAvailability.offer_type.in_(('flatrate', 'ads', 'free')))
        )
        q = q.filter(CachedMedia.id.in_(streaming_ids))

    # Newest-aired view: hide future-only titles and sort by latest aired/release date.
    # Pure cache read — last-aired/progress are maintained by the 6h media job.
    newest_aired = display_mode == 'newest_aired'
    if newest_aired:
        from sqlalchemy import func as sa_func
        today = date.today()
        if media_type == 'show':
            q = q.filter(
                UserMediaState.last_episode_aired_at.isnot(None),
                sa_func.date(UserMediaState.last_episode_aired_at) <= today,
            )
        else:  # movie
            if not needs_media_join:
                q = q.outerjoin(
                    CachedMedia,
                    and_(
                        CachedMedia.media_type == UserMediaState.media_type,
                        CachedMedia.trakt_id == UserMediaState.trakt_id,
                    ),
                )
            q = q.filter(
                CachedMedia.released_at.isnot(None),
                CachedMedia.released_at <= today,
            )

    total = q.count()
    per_page = _per_page(f'my_{media_type}')
    pages = max((total + per_page - 1) // per_page, 1) if total else 1
    try:
        page = max(int(request.args.get('page', 1)), 1)
    except (TypeError, ValueError):
        page = 1
    if page > pages:
        page = pages

    if newest_aired:
        # Pins as a group on top; within pins (and the rest) newest aired / release first.
        if media_type == 'show':
            states = (
                q.order_by(
                    UserMediaState.pinned.desc(),
                    UserMediaState.last_episode_aired_at.desc(),
                    UserMediaState.id.desc(),
                )
                .offset((page - 1) * per_page)
                .limit(per_page)
                .all()
            )
        else:
            states = (
                q.order_by(
                    UserMediaState.pinned.desc(),
                    CachedMedia.released_at.desc(),
                    UserMediaState.id.desc(),
                )
                .offset((page - 1) * per_page)
                .limit(per_page)
                .all()
            )
    else:
        # Meaningful DB sort (page-only; no full fetch):
        # Pinned first (newest pin first), then:
        # 0 = in progress, 1 = has watch history, 2 = never started.
        # Within those: most recently watched first.
        in_progress = and_(
            UserMediaState.progress_percent.isnot(None),
            UserMediaState.progress_percent > 0,
            UserMediaState.progress_percent < 100,
        )
        sort_bucket = case(
            (in_progress, 0),
            (UserMediaState.last_watched_at.isnot(None), 1),
            else_=2,
        )
        states = (
            q.order_by(
                UserMediaState.pinned.desc(),
                UserMediaState.pinned_at.desc(),
                sort_bucket.asc(),
                UserMediaState.last_watched_at.desc(),
                UserMediaState.id.desc(),
            )
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
    trakt_ids = [s.trakt_id for s in states]
    try:
        ensure_media_cached(media_type, trakt_ids)
    except Exception as exc:
        current_app.logger.warning('Title enrich for my-media failed: %s', exc)

    # Upcoming episode per show from the cached calendar (fed by the 6h job's
    # forward window) — powers the "Next: S#E# · date" card line.
    next_ep_map: dict[int, dict] = {}
    if media_type == 'show' and trakt_ids:
        future_events = (
            UserCalendarEvent.query
            .filter(
                UserCalendarEvent.user_id == current_user.id,
                UserCalendarEvent.media_type == 'show',
                UserCalendarEvent.trakt_id.in_(trakt_ids),
                UserCalendarEvent.event_date > date.today(),
            )
            .order_by(UserCalendarEvent.event_date.asc())
            .all()
        )
        for e in future_events:
            tid = int(e.trakt_id)
            if tid in next_ep_map:
                continue  # ascending order → first seen is soonest
            label = None
            if e.season_number is not None and e.episode_number is not None:
                label = f'S{int(e.season_number):02d}E{int(e.episode_number):02d}'
            next_ep_map[tid] = {
                'date': e.event_date,
                'label': label,
                'title': e.episode_title,
            }

    media_rows = {
        m.trakt_id: m
        for m in CachedMedia.query.filter(
            CachedMedia.media_type == media_type,
            CachedMedia.trakt_id.in_(trakt_ids or [-1]),
        ).all()
    }
    # Same metadata as Latest: overview, genres, locally cached poster + providers.
    from services.streaming_matcher import split_providers_for_user
    from services.sync_jobs import sync_providers_for_media
    from services.tmdb_client import is_configured as tmdb_is_configured

    tmdb_ok = tmdb_is_configured()
    try:
        to_enrich = [media_rows[tid] for tid in trakt_ids if tid in media_rows]
        enrich_media_list_for_display(to_enrich, max_fetches=len(to_enrich))
        provider_fetches = 0
        for media in to_enrich:
            if (
                tmdb_ok
                and media.tmdb_id
                and not media.providers
                and provider_fetches < per_page
            ):
                sync_providers_for_media(media)
                provider_fetches += 1
        media_rows = {
            m.trakt_id: m
            for m in CachedMedia.query.filter(
                CachedMedia.media_type == media_type,
                CachedMedia.trakt_id.in_(trakt_ids or [-1]),
            ).all()
        }
    except Exception as exc:
        current_app.logger.warning('Detail enrich for my-media failed: %s', exc)

    found_map: dict[int, list[str]] = {}
    membership_names: dict[int, list[str]] = {}
    list_name_by_id = {lst['id']: lst['name'] for lst in filter_lists}
    if trakt_ids:
        for fo in MediaFoundOn.query.filter(
            MediaFoundOn.user_id == current_user.id,
            MediaFoundOn.media_type == media_type,
            MediaFoundOn.trakt_id.in_(trakt_ids),
        ).all():
            found_map.setdefault(fo.trakt_id, []).append(fo.service_label)
        for mem in UserListMembership.query.filter(
            UserListMembership.user_id == current_user.id,
            UserListMembership.media_type == media_type,
            UserListMembership.trakt_id.in_(trakt_ids),
        ).all():
            name = list_name_by_id.get(mem.list_id)
            if name:
                membership_names.setdefault(mem.trakt_id, []).append(name)

    from services.availability import attach_availability

    rows = []
    for st in states:
        media = media_rows.get(st.trakt_id)
        genres = []
        providers = []
        my_providers = []
        other_providers = []
        if media:
            try:
                genres = json.loads(media.genres_json or '[]')
            except json.JSONDecodeError:
                genres = []
            if not isinstance(genres, list):
                genres = []
            providers = [
                p.provider_name for p in (media.providers or [])
                if p.offer_type in ('flatrate', 'ads', 'free')
            ]
            my_providers, other_providers = split_providers_for_user(
                providers, current_user,
            )
        row = {
            'state': st,
            'media': media,
            'genres': genres,
            'providers': providers,
            'my_providers': my_providers,
            'other_providers': other_providers,
            'found_on': found_map.get(st.trakt_id, []),
            'list_names': membership_names.get(st.trakt_id, []),
            'next_ep': next_ep_map.get(st.trakt_id),
        }
        attach_availability(row)
        rows.append(row)

    selected_set = set(selected_lists)
    filter_lists_payload = [
        {
            'id': lst['id'],
            'name': lst['name'],
            'kind': lst.get('kind') or 'list',
            'selected': lst['id'] in selected_set,
        }
        for lst in filter_lists
    ]
    selected_names = [lst['name'] for lst in filter_lists if lst['id'] in selected_set]

    return {
        'media_type': media_type,
        'rows': rows,
        'filt': filt,
        'filter_lists': filter_lists,
        'filter_lists_payload': filter_lists_payload,
        'selected_lists': selected_lists,
        'selected_names': selected_names,
        'page': page,
        'pages': pages,
        'per_page': per_page,
        'total': total,
        'page_links': _pagination_pages(page, pages),
        'search_q': search_q,
        'avail': avail,
        **advanced_context(year, filter_genres),
        'display_mode': display_mode,
        'calendar': calendar_ctx,
        'tmdb_configured': tmdb_ok,
        'streaming_region': current_app.config.get('STREAMING_REGION', 'US'),
        'title': 'My Movies' if media_type == 'movie' else 'My Shows',
    }


def _progress_keys_from_trakt(progress, history, watched_entry) -> tuple[set, set]:
    """Watched + aired episode keys from live Trakt payloads."""
    watched_keys = trakt_client.episode_watched_keys_from_trakt(
        history=history,
        watched_entry=watched_entry,
        progress=progress,
    )
    aired_keys: set[tuple[int, int]] = set()
    for season in (progress or {}).get('seasons') or []:
        s_no = season.get('number')
        if s_no is None:
            continue
        for ep in season.get('episodes') or []:
            e_no = ep.get('number')
            if e_no is not None:
                aired_keys.add((int(s_no), int(e_no)))
    return watched_keys, aired_keys


def _build_progress_context(media, trakt_id, seasons_meta, watched_keys, aired_keys) -> dict:
    """Build the Progress template context from cached or live Trakt objects."""
    season_views = []
    next_regular = None
    next_special = None
    total_aired = 0
    total_completed = 0
    for season in seasons_meta or []:
        number = season.get('number')
        if number is None:
            continue
        number = int(number)
        raw_eps = season.get('episodes') or []
        if number == 0 and not raw_eps:
            continue
        episodes = []
        completed = 0
        aired_count = 0
        is_specials = number == 0
        for ep in raw_eps:
            ep_no = ep.get('number')
            if ep_no is None:
                continue
            ep_no = int(ep_no)
            key = (number, ep_no)
            watched = key in watched_keys
            progress_flag = (key in aired_keys) if aired_keys else None
            air = _episode_air_info(ep, progress_says_aired=progress_flag)
            is_aired = air['aired']
            if is_aired:
                aired_count += 1
                if watched:
                    completed += 1
                else:
                    candidate = {
                        'season': number,
                        'number': ep_no,
                        'title': ep.get('title'),
                        'ids': trakt_client.sanitize_episode_ids(ep.get('ids') or {}),
                    }
                    if is_specials:
                        if next_special is None:
                            next_special = candidate
                    elif next_regular is None:
                        next_regular = candidate
            ep_ids = trakt_client.sanitize_episode_ids(ep.get('ids') or {})
            ep_trakt = ep_ids.get('trakt')
            try:
                ep_trakt_id = int(ep_trakt) if ep_trakt is not None else None
            except (TypeError, ValueError):
                ep_trakt_id = None
            episodes.append({
                'number': ep_no,
                'title': ep.get('title'),
                'ids': ep_ids,
                'trakt_id': ep_trakt_id,
                'watched': watched,
                'aired': is_aired,
                'air_label': air['air_label'],
            })
        if not episodes:
            continue
        if not is_specials:
            total_aired += aired_count
            total_completed += completed
        season_views.append({
            'number': number,
            'label': 'Specials' if is_specials else f'Season {number}',
            'is_specials': is_specials,
            'episodes': episodes,
            'all_watched': aired_count > 0 and completed == aired_count,
            'aired': aired_count,
            'completed': completed,
            'default_open': False,
        })

    season_views.sort(key=lambda s: (s['is_specials'], s['number']))
    for season in season_views:
        if season['is_specials']:
            continue
        if not season['all_watched'] and season['aired'] > 0:
            season['default_open'] = True
            break
    else:
        for season in season_views:
            if season['is_specials'] and not season['all_watched'] and season['aired'] > 0:
                season['default_open'] = True
                break

    next_episode = next_regular or next_special
    return {
        'media': media,
        'trakt_id': trakt_id,
        'seasons': season_views,
        'next_episode': next_episode,
        'progress_aired': total_aired,
        'progress_completed': total_completed,
        'title': media.title if media else f'Show {trakt_id}',
    }


def _load_progress_data(trakt_id: int) -> dict:
    """
    Load series progress for the current user.

    Returns ``{'ok': True, ...ctx}`` or ``{'ok': False, 'message', 'status'}``.
    """
    from services.trakt_cache import (
        cache_http_span,
        load_progress_payload,
        log_cache_event,
        progress_cache_is_fresh,
        save_progress_payload,
        _keys_to_tuples,
    )

    media = CachedMedia.query.filter_by(media_type='show', trakt_id=trakt_id).first()
    force = request.args.get('refresh') == '1'
    seasons_meta = None
    watched_keys: set[tuple[int, int]] = set()
    aired_keys: set[tuple[int, int]] = set()

    if not force and progress_cache_is_fresh(current_user.id, trakt_id):
        payload = load_progress_payload(current_user.id, trakt_id)
        if payload and payload.get('seasons_meta'):
            seasons_meta = payload.get('seasons_meta') or []
            watched_keys = _keys_to_tuples(payload.get('watched_keys'))
            aired_keys = _keys_to_tuples(payload.get('aired_keys'))
            log_cache_event(
                'progress', 'hit', user=current_user, item=str(trakt_id), calls=0,
            )

    if seasons_meta is None:
        span = cache_http_span()
        try:
            progress = trakt_client.get_show_progress(current_user, trakt_id)
            seasons_meta = trakt_client.get_show_seasons(trakt_id)
            history = trakt_client.get_show_watch_history(current_user, trakt_id)
            watched_entry = trakt_client.get_show_watched_entry(current_user, trakt_id)
        except Exception as exc:
            rate_limited = trakt_client.is_rate_limited(exc)
            log_cache_event(
                'progress', 'error', user=current_user, item=str(trakt_id),
                reason='429' if rate_limited else 'fetch', calls=span(),
            )
            if rate_limited:
                current_app.logger.warning('Progress load rate-limited: %s', exc)
                msg = 'Trakt is rate-limiting right now. Wait a few seconds and retry.'
                status = 429
            else:
                current_app.logger.exception('Progress load failed: %s', exc)
                msg = 'Could not load show progress from Trakt right now.'
                status = 502
            return {'ok': False, 'message': msg, 'status': status}
        watched_keys, aired_keys = _progress_keys_from_trakt(
            progress, history, watched_entry,
        )
        try:
            save_progress_payload(
                current_user.id,
                trakt_id,
                watched_keys=watched_keys,
                aired_keys=aired_keys,
                seasons_meta=seasons_meta or [],
            )
            db.session.commit()
        except Exception as exc:
            current_app.logger.warning('Could not cache show progress %%: %s', exc)
            db.session.rollback()
        log_cache_event(
            'progress', 'fetch', user=current_user, item=str(trakt_id),
            reason='force' if force else 'stale', calls=span(),
        )

    ctx = _build_progress_context(
        media, trakt_id, seasons_meta, watched_keys, aired_keys,
    )
    return {'ok': True, **ctx}


@user_bp.route('/shows/<int:trakt_id>/progress')
@login_required
def series_progress(trakt_id):
    """Series progress screen with dimmed watched seasons/episodes."""
    result = _load_progress_data(trakt_id)
    if not result.get('ok'):
        msg = result.get('message') or 'Could not load show progress.'
        status = int(result.get('status') or 502)
        if request.args.get('partial') == '1':
            return (f'<p class="muted">{msg}</p>', status)
        flash(msg, 'warning' if status == 429 else 'danger')
        return redirect(url_for('user.my_shows'))
    ctx = {k: v for k, v in result.items() if k != 'ok'}
    if request.args.get('partial') == '1':
        return render_template('_series_progress_body.html', **ctx)
    return render_template('series_progress.html', **ctx)


@user_bp.route('/api/pin/<media_type>/<int:trakt_id>', methods=['POST'])
@login_required
def api_pin_media(media_type, trakt_id):
    """Pin or unpin a title at the top of My movies / My shows (local only)."""
    if media_type not in ('movie', 'show'):
        return jsonify({'success': False, 'message': 'Invalid media type'}), 400
    action = (request.json or {}).get('action') or 'pin'
    st = UserMediaState.query.filter_by(
        user_id=current_user.id, media_type=media_type, trakt_id=trakt_id,
    ).first()
    if not st:
        st = UserMediaState(
            user_id=current_user.id, media_type=media_type, trakt_id=trakt_id,
        )
        db.session.add(st)
    if action == 'unpin':
        st.pinned = False
        st.pinned_at = None
    else:
        st.pinned = True
        st.pinned_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True, 'pinned': bool(st.pinned)})


@user_bp.route('/api/alerts/pin/<media_type>/<int:trakt_id>', methods=['POST'])
@login_required
def api_alerts_pin(media_type, trakt_id):
    """Pin or unpin a title at the top of Alerts (all of that show/movie)."""
    if media_type not in ('movie', 'show'):
        return jsonify({'success': False, 'message': 'Invalid media type'}), 400
    action = (request.json or {}).get('action') or 'pin'
    st = UserMediaState.query.filter_by(
        user_id=current_user.id, media_type=media_type, trakt_id=trakt_id,
    ).first()
    if not st:
        st = UserMediaState(
            user_id=current_user.id, media_type=media_type, trakt_id=trakt_id,
        )
        db.session.add(st)
    if action == 'unpin':
        st.alerts_pinned = False
        st.alerts_pinned_at = None
    else:
        st.alerts_pinned = True
        st.alerts_pinned_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True, 'alerts_pinned': bool(st.alerts_pinned)})


def _strip_list_id_from_prefs(user, list_id: str) -> None:
    """Drop a deleted Trakt list id from hide / default / alert prefs."""
    import json
    prefs = getattr(user, 'preferences', None)
    if prefs is None:
        return
    lid = str(list_id)
    for field in (
        'hidden_list_ids_json',
        'default_selected_list_ids_json',
        'alert_enabled_list_ids_json',
    ):
        raw = getattr(prefs, field, None) or '[]'
        try:
            ids = [str(x) for x in json.loads(raw) if str(x) != lid]
        except (TypeError, json.JSONDecodeError):
            continue
        setattr(prefs, field, json.dumps(ids))


def _refresh_personal_lists_cache(user) -> list[dict]:
    from services.trakt_cache import replace_cached_personal_lists
    lists = trakt_client.get_personal_lists(user)
    replace_cached_personal_lists(user.id, lists)
    return lists


@user_bp.route('/api/lists/create', methods=['POST'])
@login_required
def api_create_trakt_list():
    """Create a private personal list on Trakt and refresh the local cache."""
    name = ((request.json or {}).get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': 'Enter a list name'}), 400
    try:
        created = trakt_client.create_personal_list(current_user, name)
    except Exception as exc:
        current_app.logger.warning('Create Trakt list failed: %s', exc)
        return jsonify({
            'success': False,
            'message': 'Could not create the list on Trakt. Try again.',
        }), 400
    try:
        _refresh_personal_lists_cache(current_user)
    except Exception as exc:
        current_app.logger.warning('Could not refresh lists after create: %s', exc)
    db.session.commit()
    return jsonify({'success': True, 'list': created})


@user_bp.route('/api/lists/<list_id>/delete', methods=['POST'])
@login_required
def api_delete_trakt_list(list_id):
    """Delete a personal list on Trakt and drop local membership / prefs."""
    lid = str(list_id or '').strip()
    if not lid or lid == 'watchlist':
        return jsonify({'success': False, 'message': 'Wishlist cannot be deleted'}), 400
    try:
        trakt_client.delete_personal_list(current_user, lid)
    except Exception as exc:
        current_app.logger.warning('Delete Trakt list %s failed: %s', lid, exc)
        return jsonify({
            'success': False,
            'message': 'Could not delete the list on Trakt. Try again.',
        }), 400
    UserListMembership.query.filter_by(
        user_id=current_user.id, list_id=lid,
    ).delete(synchronize_session=False)
    _strip_list_id_from_prefs(current_user, lid)
    try:
        _refresh_personal_lists_cache(current_user)
    except Exception as exc:
        current_app.logger.warning('Could not refresh lists after delete: %s', exc)
        from models import UserTraktList
        UserTraktList.query.filter_by(
            user_id=current_user.id, list_id=lid,
        ).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({'success': True})


@user_bp.route('/api/episode/watched', methods=['POST'])
@login_required
def api_episode_watched():
    """Mark an episode watched or unwatched on Trakt."""
    payload = request.json or {}
    ids = trakt_client.sanitize_episode_ids(payload.get('ids') or {})
    action = payload.get('action') or 'add'
    if not ids:
        try:
            show_id = int(payload.get('show_trakt_id') or 0)
            season = payload.get('season')
            episode = payload.get('episode')
            if show_id and season is not None and episode is not None:
                from services.trakt_cache import episode_ids_from_progress
                ids = episode_ids_from_progress(
                    current_user.id, show_id, int(season), int(episode),
                )
        except (TypeError, ValueError):
            ids = {}
    if not ids:
        return jsonify({'success': False, 'message': 'ids required'}), 400
    try:
        if action == 'remove':
            trakt_client.mark_episode_unwatched(current_user, ids)
            watched = False
        else:
            trakt_client.mark_episode_watched(current_user, ids)
            watched = True
            try:
                show_id = int(payload.get('show_trakt_id') or 0)
                season = payload.get('season')
                episode = payload.get('episode')
                if show_id and season is not None and episode is not None:
                    from services.alerts import mark_episode_alerts_read
                    mark_episode_alerts_read(
                        current_user, show_id, int(season), int(episode),
                    )
            except Exception as exc:
                current_app.logger.warning(
                    'Could not mark episode alerts read after watch: %s', exc,
                )
        try:
            show_id = int(payload.get('show_trakt_id') or 0)
            season = payload.get('season')
            episode = payload.get('episode')
            if show_id and season is not None and episode is not None:
                from services.trakt_cache import patch_episode_watched
                patch_episode_watched(
                    current_user.id, show_id, int(season), int(episode),
                    watched=watched,
                )
                db.session.commit()
        except Exception as exc:
            current_app.logger.warning(
                'Could not patch progress cache after episode watch: %s', exc,
            )
        return jsonify({'success': True, 'watched': watched})
    except Exception as exc:
        current_app.logger.exception('Episode watched action failed: %s', exc)
        return jsonify({
            'success': False,
            'message': 'Could not update episode. Please try again.',
        }), 400


@user_bp.route('/api/show/<int:trakt_id>/season/<int:season_number>/watched', methods=['POST'])
@login_required
def api_season_watched(trakt_id, season_number):
    """Mark all aired episodes in a season as watched on Trakt."""
    try:
        result = trakt_client.mark_season_watched(current_user, trakt_id, season_number)
        added = int(((result.get('added') or {}).get('episodes')) or 0)
        try:
            from services.alerts import mark_season_alerts_read
            mark_season_alerts_read(current_user, trakt_id, season_number)
        except Exception as exc:
            current_app.logger.warning(
                'Could not mark season alerts read after watch: %s', exc,
            )
        try:
            from services.trakt_cache import patch_season_watched
            patch_season_watched(
                current_user.id, trakt_id, season_number, watched=True,
            )
            db.session.commit()
        except Exception as exc:
            current_app.logger.warning(
                'Could not patch progress cache after season watch: %s', exc,
            )
        return jsonify({'success': True, 'added': added, 'season': season_number})
    except Exception as exc:
        current_app.logger.exception('Season watched failed: %s', exc)
        return jsonify({
            'success': False,
            'message': 'Could not mark season watched. Please try again.',
        }), 400


@user_bp.route('/api/show/<int:trakt_id>/season/<int:season_number>/unwatched', methods=['POST'])
@login_required
def api_season_unwatched(trakt_id, season_number):
    """Remove all watch history for one season on Trakt."""
    try:
        result = trakt_client.mark_season_unwatched(current_user, trakt_id, season_number)
        deleted = int(((result.get('deleted') or {}).get('episodes')) or 0)
        try:
            from services.trakt_cache import patch_season_watched
            patch_season_watched(
                current_user.id, trakt_id, season_number, watched=False,
            )
            db.session.commit()
        except Exception as exc:
            current_app.logger.warning(
                'Could not patch progress cache after season unwatch: %s', exc,
            )
        return jsonify({'success': True, 'deleted': deleted, 'season': season_number})
    except Exception as exc:
        current_app.logger.exception('Season unwatched failed: %s', exc)
        return jsonify({
            'success': False,
            'message': 'Could not unwatch season. Please try again.',
        }), 400


ALERT_TYPE_LABELS = {
    'release_day': 'Released',
    'new_streaming': 'Now streaming',
    'episode_aired': 'New episode',
    'season_aired': 'Season out',
    'list_add': 'Added to list',
    'new_user_login': 'New login',
}

_EP_CODE_RE = re.compile(r'\bS(\d{1,2})E(\d{1,3})\b', re.IGNORECASE)
_SEASON_CODE_RE = re.compile(r'(?:Full season|Season)\s+(\d+)', re.IGNORECASE)
_TITLE_SEASON_RE = re.compile(r'^Season\s+(\d+)\s+out\b', re.IGNORECASE)


def _strip_available_on_blurb(text: str) -> str:
    """Drop legacy 'Available on: …' / 'is available on …' suffixes from alert copy."""
    raw = (text or '').strip()
    lower = raw.lower()
    cut = -1
    for marker in (' available on:', '. available on:', ' is available on '):
        idx = lower.find(marker)
        if idx != -1 and (cut == -1 or idx < cut):
            cut = idx
    if cut == -1:
        return raw
    return raw[:cut].rstrip(' .')


def _parse_season_episode(n) -> tuple[int | None, int | None]:
    """Season/episode from payload_key, then message, then title."""
    key = (getattr(n, 'payload_key', None) or '').strip()
    if key.startswith('ep:'):
        parts = key.split(':')
        if len(parts) >= 3:
            try:
                return int(parts[1]), int(parts[2])
            except (TypeError, ValueError):
                pass
    if key.startswith('season:'):
        try:
            return int(key.split(':', 1)[1]), None
        except (TypeError, ValueError):
            pass
    for text in (getattr(n, 'message', None) or '', getattr(n, 'title', None) or ''):
        m = _EP_CODE_RE.search(text)
        if m:
            return int(m.group(1)), int(m.group(2))
        m = _SEASON_CODE_RE.search(text)
        if m:
            return int(m.group(1)), None
        m = _TITLE_SEASON_RE.search(text)
        if m:
            return int(m.group(1)), None
    return None, None


def _episode_code(n) -> str:
    """Compact S3E5 / S3 for the title line (unpadded, as requested)."""
    season, episode = _parse_season_episode(n)
    if season is None:
        return ''
    if episode is None:
        return f'S{season}'
    return f'S{season}E{episode}'


def _alert_kind_label(media_type: str | None, alert_type: str | None) -> str:
    """Poster badge: Episode / Season / Streaming / Movie / List / Admin."""
    if alert_type == 'new_user_login':
        return 'Admin'
    if alert_type == 'list_add':
        return 'List'
    if alert_type == 'season_aired':
        return 'Season'
    if alert_type == 'episode_aired':
        return 'Episode'
    if alert_type == 'new_streaming':
        return 'Streaming'
    if media_type == 'movie':
        return 'Movie'
    if media_type == 'show':
        return 'Show'
    return 'Alert'


def _group_kind_label(cards: list[dict]) -> str:
    types = {(c['n'].alert_type or '') for c in cards}
    if 'episode_aired' in types:
        return 'Episode'
    if 'season_aired' in types:
        return 'Season'
    if types == {'new_streaming'}:
        return 'Streaming'
    return 'Show'


def _alert_headline(n, media, episode_code: str = '') -> str:
    """Subtitle: episode name + date, or a movie date — not S#E# (that's in the title)."""
    kind = n.alert_type or ''
    if kind in ('episode_aired', 'season_aired', 'list_add', 'new_user_login'):
        text = _strip_available_on_blurb(n.message or '')
        if episode_code:
            text = re.sub(
                rf'^{re.escape(episode_code)}\s*[—\-·.]*\s*',
                '', text, count=1, flags=re.IGNORECASE,
            )
            text = re.sub(
                r'^S\d{1,2}E\d{1,3}\s*[—\-·.]*\s*',
                '', text, count=1, flags=re.IGNORECASE,
            )
            text = re.sub(
                r'^Full season\s+\d+\s*[—\-·.]*\s*',
                '', text, count=1, flags=re.IGNORECASE,
            )
        return text.strip()
    if media is not None and media.released_at:
        return media.released_at.isoformat()
    if n.created_at:
        return n.created_at.strftime('%Y-%m-%d')
    return ''


def _alert_display_title(media, n, episode_code: str) -> str:
    name = media.title if media else (n.title or '')
    if episode_code and name:
        return f'{name} {episode_code}'
    return name or (n.title or '')


def _media_name_from_alert_title(title: str) -> str | None:
    """Best-effort show/movie name from older alert titles that lack trakt_id."""
    raw = (title or '').strip()
    for prefix in ('New episode: ', 'Released: '):
        if raw.startswith(prefix):
            return raw[len(prefix):].strip() or None
    if raw.startswith('Season ') and ' out: ' in raw:
        return raw.split(' out: ', 1)[1].strip() or None
    if raw.startswith('Now on ') and ': ' in raw[7:]:
        return raw.split(': ', 1)[1].strip() or None
    return None


def _alert_media_pair(n, title_to_pair: dict) -> tuple | None:
    if n.media_type and n.trakt_id:
        return n.media_type, int(n.trakt_id)
    name = _media_name_from_alert_title(n.title or '')
    if name:
        return title_to_pair.get(name.casefold())
    return None


def _title_pairs_for_user(user, names: list[str]) -> dict[str, tuple]:
    """Map show/movie name → (media_type, trakt_id), preferring the user's title."""
    if not names:
        return {}
    found = CachedMedia.query.filter(CachedMedia.title.in_(names)).all()
    if not found:
        return {}
    states = {
        (st.media_type, int(st.trakt_id)): st
        for st in UserMediaState.query.filter_by(user_id=user.id).all()
    }

    def _score(m) -> tuple:
        pair = (m.media_type, int(m.trakt_id))
        st = states.get(pair)
        completed = int(st.episodes_completed or 0) if st else -1
        tracked = 1 if st else 0
        is_show = 1 if m.media_type == 'show' else 0
        return (tracked, is_show, completed)

    best: dict[str, object] = {}
    for m in found:
        key = m.title.casefold()
        prev = best.get(key)
        if prev is None or _score(m) > _score(prev):
            best[key] = m
    return {k: (m.media_type, int(m.trakt_id)) for k, m in best.items()}


def _alert_sort_key(card: dict, sort: str):
    n = card['n']
    ts = n.created_at or datetime.min
    pinned_rank = 0 if card.get('alerts_pinned') else 1
    if sort == 'asc':
        return (pinned_rank, ts)
    return (pinned_rank, datetime.max - ts)


def _unread_episode_codes(cards: list[dict]) -> list[str]:
    """Unread S#E# codes, oldest first; fall back to all codes if none unread."""
    unread = []
    all_codes = []
    for card in sorted(cards, key=lambda c: c['n'].created_at or datetime.min):
        code = card.get('episode_code') or ''
        if not code:
            continue
        all_codes.append(code)
        if not card['n'].is_read:
            unread.append(code)
    return unread or all_codes


def _group_alert_cards(cards: list[dict], *, group_shows: bool, sort: str) -> list[dict]:
    """Collapse 2+ show alerts into one expandable entry; movies/admin stay single."""
    if not group_shows:
        return [{'kind': 'single', 'card': c} for c in cards]

    buckets: dict[tuple, list[dict]] = {}
    order: list[tuple] = []
    for card in cards:
        pair = card.get('media_pair')
        note_type = getattr(card.get('n'), 'alert_type', None)
        if pair and pair[0] == 'show' and note_type != 'list_add':
            key = ('show', int(pair[1]))
        else:
            key = ('single', card['n'].id)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(card)

    entries = []
    for key in order:
        items = buckets[key]
        if key[0] == 'show' and len(items) > 1:
            first = items[0]
            media = first.get('media')
            title = media.title if media else (first['n'].title or 'Show')
            entries.append({
                'kind': 'group',
                'media_type': 'show',
                'trakt_id': key[1],
                'media': media,
                'title': title,
                'kind_label': _group_kind_label(items),
                'alerts_pinned': bool(first.get('alerts_pinned')),
                'episode_codes': _unread_episode_codes(items),
                'unread_count': sum(1 for c in items if not c['n'].is_read),
                'cards': items,
            })
        else:
            for card in items:
                entries.append({'kind': 'single', 'card': card})

    def _entry_sort_key(entry: dict):
        if entry['kind'] == 'group':
            times = [c['n'].created_at or datetime.min for c in entry['cards']]
            lead = max(times) if sort == 'desc' else min(times)
            pinned_rank = 0 if entry.get('alerts_pinned') else 1
            if sort == 'asc':
                return (pinned_rank, lead)
            return (pinned_rank, datetime.max - lead)
        return _alert_sort_key(entry['card'], sort)

    entries.sort(key=_entry_sort_key)
    return entries


def _collect_alert_cards() -> dict:
    """Build Alerts page/API payload for the current user."""
    from services import view_prefs

    hide_read = view_prefs.resolve_bool(
        current_user, 'alerts', 'hide_read', 'hide_read', default=True,
    )
    sort = view_prefs.resolve_choice(
        current_user, 'alerts', 'sort', 'sort',
        allowed=('asc', 'desc'), default='desc',
    )
    group_shows = view_prefs.resolve_bool(
        current_user, 'alerts', 'group_shows', 'group_shows', default=True,
    )
    q = Notification.query.filter_by(user_id=current_user.id)
    unread_count = q.filter_by(is_read=False).count()
    if hide_read:
        q = q.filter_by(is_read=False)
    time_order = (
        Notification.created_at.asc() if sort == 'asc'
        else Notification.created_at.desc()
    )
    rows = q.order_by(time_order).limit(200).all()

    need_names = []
    for n in rows:
        if not (n.media_type and n.trakt_id):
            name = _media_name_from_alert_title(n.title or '')
            if name:
                need_names.append(name)
    title_to_pair = _title_pairs_for_user(current_user, need_names)

    pairs = set()
    pair_by_notif: dict[int, tuple] = {}
    for n in rows:
        pair = _alert_media_pair(n, title_to_pair)
        if pair:
            pairs.add(pair)
            pair_by_notif[n.id] = pair

    from services.alerts import mark_cached_watched_alerts_read
    if mark_cached_watched_alerts_read(current_user, rows, pair_by_notif):
        unread_count = Notification.query.filter_by(
            user_id=current_user.id, is_read=False,
        ).count()
        if hide_read:
            rows = [n for n in rows if not n.is_read]
            pair_by_notif = {n.id: pair_by_notif[n.id] for n in rows if n.id in pair_by_notif}
            pairs = set(pair_by_notif.values())
    media_map = {}
    if pairs:
        show_ids = [tid for mt, tid in pairs if mt == 'show']
        movie_ids = [tid for mt, tid in pairs if mt == 'movie']
        found = []
        if show_ids:
            found.extend(CachedMedia.query.filter(
                CachedMedia.media_type == 'show',
                CachedMedia.trakt_id.in_(show_ids),
            ).all())
        if movie_ids:
            found.extend(CachedMedia.query.filter(
                CachedMedia.media_type == 'movie',
                CachedMedia.trakt_id.in_(movie_ids),
            ).all())
        media_map = {(m.media_type, int(m.trakt_id)): m for m in found}
    show_ids = [int(mt_id[1]) for mt_id in pairs if mt_id[0] == 'show']
    movie_ids = [int(mt_id[1]) for mt_id in pairs if mt_id[0] == 'movie']
    state_map: dict[tuple, object] = {}
    state_filters = []
    if show_ids:
        state_filters.append(
            and_(
                UserMediaState.media_type == 'show',
                UserMediaState.trakt_id.in_(show_ids),
            )
        )
    if movie_ids:
        state_filters.append(
            and_(
                UserMediaState.media_type == 'movie',
                UserMediaState.trakt_id.in_(movie_ids),
            )
        )
    if state_filters:
        for st in UserMediaState.query.filter(
            UserMediaState.user_id == current_user.id,
            or_(*state_filters),
        ).all():
            state_map[(st.media_type, int(st.trakt_id))] = st

    from services.streaming_matcher import split_providers_for_user
    found_map: dict[tuple, list[str]] = {}
    if pairs:
        for mt, ids in (
            ('show', [tid for mt, tid in pairs if mt == 'show']),
            ('movie', [tid for mt, tid in pairs if mt == 'movie']),
        ):
            if not ids:
                continue
            for fo in MediaFoundOn.query.filter(
                MediaFoundOn.user_id == current_user.id,
                MediaFoundOn.media_type == mt,
                MediaFoundOn.trakt_id.in_(ids),
            ).all():
                found_map.setdefault((fo.media_type, int(fo.trakt_id)), []).append(
                    fo.service_label,
                )
    cards = []
    for n in rows:
        pair = pair_by_notif.get(n.id)
        media = media_map.get(pair) if pair else None
        my_providers: list[str] = []
        other_providers: list[str] = []
        if media is not None:
            names = [
                r.provider_name for r in media.providers
                if r.provider_name and r.offer_type in STREAMING_OFFER_TYPES
            ]
            my_providers, other_providers = split_providers_for_user(
                sorted(set(names)), current_user,
            )
        found_on = found_map.get(pair, []) if pair else []
        st = state_map.get(pair) if pair else None
        episode_code = _episode_code(n)
        media_type = pair[0] if pair else n.media_type
        cards.append({
            'n': n,
            'media': media,
            'state': st,
            'media_pair': pair,
            'my_providers': my_providers,
            'other_providers': other_providers,
            'found_on': found_on,
            'type_label': ALERT_TYPE_LABELS.get(
                n.alert_type, (n.alert_type or '').replace('_', ' '),
            ),
            'kind_label': _alert_kind_label(media_type, n.alert_type),
            'episode_code': episode_code,
            'display_title': _alert_display_title(media, n, episode_code),
            'headline': _alert_headline(n, media, episode_code),
            'alerts_pinned': bool(st and getattr(st, 'alerts_pinned', False)),
        })
    cards.sort(key=lambda c: _alert_sort_key(c, sort))
    entries = _group_alert_cards(cards, group_shows=group_shows, sort=sort)
    return {
        'cards': cards,
        'entries': entries,
        'unread_count': unread_count,
        'hide_read': hide_read,
        'sort': sort,
        'group_shows': group_shows,
    }


@user_bp.route('/notifications')
@login_required
def notifications():
    """List in-app notifications for the current user."""
    return render_template('notifications.html', **_collect_alert_cards())


@user_bp.route('/notifications/read-all', methods=['POST'])
@login_required
def notifications_read_all():
    """Mark all notifications as read."""
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    flash('All notifications marked read.', 'success')
    return redirect(url_for('user.notifications'))


@user_bp.route('/notifications/<int:notif_id>/read', methods=['POST'])
@login_required
def notification_read(notif_id):
    """Mark one notification as read; optionally open its link."""
    row = Notification.query.filter_by(id=notif_id, user_id=current_user.id).first_or_404()
    row.is_read = True
    db.session.commit()
    if request.form.get('open') == '1' and row.link:
        return redirect(row.link)
    return redirect(url_for('user.notifications'))


@user_bp.route('/notifications/<int:notif_id>/unread', methods=['POST'])
@login_required
def notification_unread(notif_id):
    """Mark one notification as unread."""
    row = Notification.query.filter_by(id=notif_id, user_id=current_user.id).first_or_404()
    row.is_read = False
    db.session.commit()
    return redirect(url_for('user.notifications'))


@user_bp.route('/help/')
@user_bp.route('/help/<topic>')
@login_required
def help_page(topic='overview'):
    """Render user help topic."""
    html = render_help_markdown('user', topic)
    if html is None:
        flash('Help topic not found.', 'warning')
        return redirect(url_for('user.help_page', topic='overview'))
    return render_template('help.html', role='user', topic=topic, content_html=html, toc=get_help_toc('user'))
