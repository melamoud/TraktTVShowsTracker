"""
User routes: preferences, my movies/shows, series progress, notifications, help.
"""

from datetime import date, datetime, timedelta

from flask import (
    Blueprint, current_app, flash, jsonify, redirect, render_template,
    request, session, url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import String, and_, case, cast, or_


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
    """
    air_dt = _parse_air_datetime(ep.get('first_aired')) or _parse_air_datetime(ep.get('released'))
    now = datetime.utcnow()
    if air_dt is not None:
        is_aired = air_dt <= now
        label = air_dt.strftime('%Y-%m-%d')
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
    UserListMembership, UserMediaState, UserPreference, UserStreamingService, db,
)
from services import trakt_client
from services.seed import COMMON_GENRES
from services.streaming_matcher import (
    WATCHLIST_LIST_ID,
    filter_visible_list_ids,
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
    refresh_show_progress_for_ids,
)
from services.user_media_sync import ensure_user_media_fresh

user_bp = Blueprint('user', __name__)


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
        custom_note = (request.form.get('custom_note') or '').strip() or None
        if custom_name:
            existing = UserStreamingService.query.filter_by(
                user_id=current_user.id, is_custom=True, custom_name=custom_name
            ).first()
            if existing:
                existing.custom_url = custom_url
                existing.custom_note = custom_note
            else:
                db.session.add(UserStreamingService(
                    user_id=current_user.id,
                    is_custom=True,
                    custom_name=custom_name,
                    custom_url=custom_url,
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

        old_genres, old_keywords = get_user_genres_keywords(current_user)
        genres = split_csv_terms(request.form.get('genres', ''))
        genres.extend(request.form.getlist('genre_checks'))
        keywords = split_csv_terms(request.form.get('keywords', ''))
        g_json, k_json = serialize_prefs(genres, keywords)
        prefs.genres_json = g_json
        prefs.keywords_json = k_json

        # Two list prefs: show in menu (personal only) + default-checked (incl. Wishlist).
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
            if known_list_ids:
                hidden_ids = sorted(known_list_ids - shown_list_ids)
                prefs.hidden_list_ids_json = json.dumps(hidden_ids)
                # Auto-select only applies to Wishlist + lists still shown in the menu.
                allowed_defaults = {WATCHLIST_LIST_ID} | shown_list_ids
            else:
                allowed_defaults = {WATCHLIST_LIST_ID} | set(
                    lid for lid in default_raw if lid != WATCHLIST_LIST_ID
                )
            default_ids = sorted(
                lid for lid in default_raw
                if lid in allowed_defaults
            )
            prefs.default_selected_list_ids_json = json.dumps(default_ids)

        if request.form.get('alerts_prefs_present') == '1':
            prefs.alert_release_day = request.form.get('alert_release_day') == '1'
            prefs.alert_new_streaming = request.form.get('alert_new_streaming') == '1'
            prefs.alert_episode_aired = request.form.get('alert_episode_aired') == '1'
            if current_user.is_admin:
                prefs.alert_new_user_login = request.form.get('alert_new_user_login') == '1'

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
    trakt_lists = []
    trakt_lists_error = None
    try:
        trakt_lists = trakt_client.get_personal_lists(current_user)
    except Exception as exc:
        current_app.logger.warning('Could not load Trakt lists for preferences: %s', exc)
        trakt_lists_error = str(exc)
    if request.args.get('marker_prompt') == '1' or session.pop('marker_prompt_after_prefs', None):
        marker_prompt = True
    markers = {
        'movie': ReviewMarker.query.filter_by(user_id=current_user.id, media_type='movie').first(),
        'show': ReviewMarker.query.filter_by(user_id=current_user.id, media_type='show').first(),
    }
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
        watchlist_list_id=WATCHLIST_LIST_ID,
        trakt_lists_error=trakt_lists_error,
        alert_release_day=bool(getattr(prefs, 'alert_release_day', True)),
        alert_new_streaming=bool(getattr(prefs, 'alert_new_streaming', True)),
        alert_episode_aired=bool(getattr(prefs, 'alert_episode_aired', True)),
        alert_new_user_login=bool(getattr(prefs, 'alert_new_user_login', True)),
    )


@user_bp.route('/my/movies')
@login_required
def my_movies():
    """Movies on the user's Trakt watchlist and/or watched history."""
    return _my_media('movie')


@user_bp.route('/my/shows')
@login_required
def my_shows():
    """Shows on the user's Trakt watchlist and/or watched history."""
    return _my_media('show')


def _my_filter_lists(user) -> list[dict]:
    """Wishlist + personal lists shown in Preferences (for My page filter buttons)."""
    hidden = set(get_hidden_list_ids(user))
    out = [{'id': WATCHLIST_LIST_ID, 'name': 'Wishlist', 'kind': 'watchlist'}]
    try:
        for lst in trakt_client.get_personal_lists(user):
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
    # (wishlist / watched / lists). Manual Refresh forces a full pull.
    try:
        synced = ensure_user_media_fresh(
            current_user,
            media_types=(media_type,),
            force=request.args.get('refresh') == '1',
        )
        if synced and request.args.get('refresh') == '1':
            flash('Updated from Trakt.', 'success')
    except Exception as exc:
        current_app.logger.warning('Sync before my-media failed: %s', exc)
        flash('Could not refresh from Trakt right now. Showing cached titles.', 'warning')

    filter_lists = _my_filter_lists(current_user)
    selected_lists = _resolve_selected_lists(current_user, filter_lists, view)
    list_trakt_ids = _trakt_ids_for_lists(current_user.id, media_type, selected_lists)
    search_q = (request.args.get('q') or '').strip()
    if len(search_q) < 2:
        search_q = ''
    from services.availability import (
        normalize_avail, theater_window_bounds, upcoming_after,
    )
    avail = normalize_avail(request.args.get('avail'))

    q = UserMediaState.query.filter_by(user_id=current_user.id, media_type=media_type)
    if filt == 'lists':
        if list_trakt_ids:
            q = q.filter(UserMediaState.trakt_id.in_(list_trakt_ids))
        else:
            q = q.filter(UserMediaState.trakt_id == -1)
    elif filt == 'watched':
        q = q.filter_by(watched=True)
    elif filt == 'unwatched':
        # Movies (or titles) on selected lists that are not watched yet.
        if list_trakt_ids:
            q = q.filter(
                UserMediaState.trakt_id.in_(list_trakt_ids),
                UserMediaState.watched.is_(False),
            )
        else:
            q = q.filter(UserMediaState.trakt_id == -1)
    elif filt == 'unwatched_episodes':
        # Still has something to watch: unfinished titles on selected lists,
        # or any watched show with known incomplete progress.
        # Only trust progress>=100 when progress_detail_at was set from a real
        # episode summary (otherwise old fake 100%s hide shows like Lioness).
        trusted_complete = and_(
            UserMediaState.progress_percent.isnot(None),
            UserMediaState.progress_percent >= 100,
            UserMediaState.progress_detail_at.isnot(None),
        )
        not_finished = ~trusted_complete
        clauses = []
        if list_trakt_ids:
            clauses.append(
                and_(UserMediaState.trakt_id.in_(list_trakt_ids), not_finished)
            )
        clauses.append(
            and_(
                UserMediaState.watched.is_(True),
                UserMediaState.progress_percent.isnot(None),
                UserMediaState.progress_percent < 100,
            )
        )
        q = q.filter(or_(*clauses))
    else:  # both
        clauses = [UserMediaState.watched.is_(True)]
        if list_trakt_ids:
            clauses.append(UserMediaState.trakt_id.in_(list_trakt_ids))
        q = q.filter(or_(*clauses))

    # Title search and/or availability filters need CachedMedia (before pagination).
    # Backfill missing titles for the filtered candidate set first — otherwise
    # q= cannot match rows that only exist in UserMediaState (Search page used
    # to "unlock" them by upserting CachedMedia as a side effect).
    needs_media_join = bool(search_q) or bool(avail)
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

    total = q.count()
    per_page = _per_page(f'my_{media_type}')
    pages = max((total + per_page - 1) // per_page, 1) if total else 1
    try:
        page = max(int(request.args.get('page', 1)), 1)
    except (TypeError, ValueError):
        page = 1
    if page > pages:
        page = pages

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

    # Shows only: fill x/y + next episode for the visible page (not full Refresh).
    if media_type == 'show' and trakt_ids:
        try:
            refresh_show_progress_for_ids(
                current_user,
                trakt_ids,
                force=request.args.get('refresh') == '1',
            )
            # Re-load states so template sees fresh progress columns.
            state_by_id = {
                s.id: s for s in UserMediaState.query.filter(
                    UserMediaState.id.in_([st.id for st in states])
                ).all()
            }
            states = [state_by_id.get(st.id, st) for st in states]
        except Exception as exc:
            current_app.logger.warning('Show progress enrich failed: %s', exc)

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

    return render_template(
        'my_media.html',
        media_type=media_type,
        rows=rows,
        filt=filt,
        filter_lists=filter_lists,
        filter_lists_payload=filter_lists_payload,
        selected_lists=selected_lists,
        selected_names=selected_names,
        page=page,
        pages=pages,
        per_page=per_page,
        total=total,
        page_links=_pagination_pages(page, pages),
        search_q=search_q,
        avail=avail,
        tmdb_configured=tmdb_ok,
        streaming_region=current_app.config.get('STREAMING_REGION', 'US'),
        title='My Movies' if media_type == 'movie' else 'My Shows',
    )


@user_bp.route('/shows/<int:trakt_id>/progress')
@login_required
def series_progress(trakt_id):
    """Series progress screen with dimmed watched seasons/episodes."""
    media = CachedMedia.query.filter_by(media_type='show', trakt_id=trakt_id).first()
    try:
        progress = trakt_client.get_show_progress(current_user, trakt_id)
        seasons_meta = trakt_client.get_show_seasons(trakt_id)
        history = trakt_client.get_show_watch_history(current_user, trakt_id)
        # Same source Showly/Kodi use for per-episode plays (extended=progress).
        watched_entry = trakt_client.get_show_watched_entry(current_user, trakt_id)
    except Exception as exc:
        current_app.logger.exception('Progress load failed: %s', exc)
        if request.args.get('partial') == '1':
            return (
                '<p class="muted">Could not load show progress from Trakt right now.</p>',
                502,
            )
        flash('Could not load show progress from Trakt.', 'danger')
        return redirect(url_for('user.my_shows'))

    watched_keys = trakt_client.episode_watched_keys_from_trakt(
        history=history,
        watched_entry=watched_entry,
        progress=progress,
    )

    # Which episodes Trakt considers aired (for counts / next-up only).
    aired_keys: set[tuple[int, int]] = set()
    for season in progress.get('seasons') or []:
        s_no = season.get('number')
        if s_no is None:
            continue
        for ep in season.get('episodes') or []:
            e_no = ep.get('number')
            if e_no is not None:
                aired_keys.add((int(s_no), int(e_no)))

    # Full season lists from metadata so unaired/future eps still appear.
    # Season 0 (specials) is kept, but must not steal next-up / default-open /
    # header counts — that made shows like True Blood look like "0 watched".
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
            episodes.append({
                'number': ep_no,
                'title': ep.get('title'),
                'ids': trakt_client.sanitize_episode_ids(ep.get('ids') or {}),
                'watched': watched,
                'aired': is_aired,
                'air_label': air['air_label'],
            })
        if not episodes:
            continue
        # Header totals = regular seasons only (matches Trakt season progress).
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

    # Regular seasons first, specials last.
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

    # Persist episode summary for My Shows cards / Unwatched filter.
    try:
        from services.sync_jobs import apply_show_episode_progress
        apply_show_episode_progress(
            current_user.id,
            trakt_id,
            aired=total_aired,
            completed=total_completed,
            next_episode=next_episode,
        )
        db.session.commit()
    except Exception as exc:
        current_app.logger.warning('Could not cache show progress %%: %s', exc)
        db.session.rollback()

    ctx = {
        'media': media,
        'trakt_id': trakt_id,
        'seasons': season_views,
        'next_episode': next_episode,
        'progress_aired': total_aired,
        'progress_completed': total_completed,
        'title': media.title if media else f'Show {trakt_id}',
    }
    # Drawer / AJAX: return body-only fragment (no full page chrome).
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


@user_bp.route('/api/episode/watched', methods=['POST'])
@login_required
def api_episode_watched():
    """Mark an episode watched or unwatched on Trakt."""
    payload = request.json or {}
    ids = trakt_client.sanitize_episode_ids(payload.get('ids') or {})
    action = payload.get('action') or 'add'
    if not ids:
        return jsonify({'success': False, 'message': 'ids required'}), 400
    try:
        if action == 'remove':
            trakt_client.mark_episode_unwatched(current_user, ids)
            watched = False
        else:
            trakt_client.mark_episode_watched(current_user, ids)
            watched = True
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
        return jsonify({'success': True, 'deleted': deleted, 'season': season_number})
    except Exception as exc:
        current_app.logger.exception('Season unwatched failed: %s', exc)
        return jsonify({
            'success': False,
            'message': 'Could not unwatch season. Please try again.',
        }), 400


@user_bp.route('/notifications')
@login_required
def notifications():
    """List in-app notifications for the current user."""
    rows = (
        Notification.query
        .filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(200)
        .all()
    )
    unread_count = sum(1 for n in rows if not n.is_read)
    return render_template(
        'notifications.html',
        notifications=rows,
        unread_count=unread_count,
    )


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
