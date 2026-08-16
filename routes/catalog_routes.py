"""
Catalog routes: home, latest movies/shows, detail, review markers, Trakt actions.
"""

from datetime import datetime

from flask import (
    Blueprint, abort, current_app, flash, jsonify, redirect, render_template,
    request, send_file, session, url_for,
)
from flask_login import current_user, login_required

from models import (
    CachedMedia, MediaFoundOn, ReviewMarker, UserListMembership, UserMediaState, db,
)
from services import trakt_client
from services.streaming_matcher import (
    WATCHLIST_LIST_ID,
    get_default_selected_list_ids,
    get_hidden_list_ids,
    match_preferences,
)
from services.sync_jobs import (
    catalog_has_more_older,
    ensure_catalog_for_offset,
    ensure_catalog_through_marker,
    feed_count,
    refresh_catalog_newest,
    set_list_membership,
    sync_catalog,
    sync_providers_for_media,
)

catalog_bp = Blueprint('catalog', __name__)


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


def _api_fail(log_msg: str, exc: Exception, *, user_message: str = 'Something went wrong. Please try again.', status: int = 400):
    """Log full exception server-side; return a short safe message to the client."""
    current_app.logger.exception('%s: %s', log_msg, exc)
    return jsonify({'success': False, 'message': user_message}), status


@catalog_bp.route('/cache/posters/<media_type>/<int:trakt_id>')
def cached_poster(media_type, trakt_id):
    """
    Serve a locally cached poster.

    Trakt forbids hotlinking their CDN in the browser; we download during
    enrich and serve from here.
    """
    from services.poster_cache import local_poster_path

    if media_type not in ('movie', 'show'):
        abort(404)
    path = local_poster_path(media_type, trakt_id)
    if not path:
        abort(404)
    mime = 'image/webp' if path.suffix.lower() == '.webp' else None
    return send_file(path, mimetype=mime, max_age=60 * 60 * 24 * 7, conditional=True)


@catalog_bp.route('/cache/actors/<int:trakt_person_id>')
def cached_actor(trakt_person_id):
    """Serve a locally cached favorite-actor headshot."""
    from services.actor_cache import local_actor_path

    path = local_actor_path(trakt_person_id)
    if not path:
        abort(404)
    mime = 'image/webp' if path.suffix.lower() == '.webp' else None
    return send_file(path, mimetype=mime, max_age=60 * 60 * 24 * 7, conditional=True)


def _per_page(view_type: str) -> int:
    """Resolve allowed page size for a catalog view (persisted per user)."""
    from services import view_prefs

    allowed = tuple(current_app.config.get('ALLOWED_PER_PAGE', (10, 50, 100)))
    default = current_app.config.get('DEFAULT_PER_PAGE', 50)
    user = view_prefs.current_user_or_none()
    if user is not None:
        value = view_prefs.resolve_per_page(
            user, view_type, allowed=allowed, default=default,
        )
        # Keep session mirror for the current browser tab.
        session.setdefault('per_page_settings', {})[view_type] = value
        return value
    try:
        requested = int(request.args.get('per_page', 0))
    except (TypeError, ValueError):
        requested = 0
    if requested in allowed:
        session.setdefault('per_page_settings', {})[view_type] = requested
        return requested
    stored = (session.get('per_page_settings') or {}).get(view_type)
    if stored in allowed:
        return stored
    return default


def _pagination_pages(page: int, pages: int, radius: int = 2) -> list[int | None]:
    """
    Page numbers for a compact pager: 1 … 4 5 6 … 10.

    ``None`` entries are ellipsis placeholders for the template.
    """
    if pages <= 0:
        return []
    if pages <= 9:
        return list(range(1, pages + 1))
    selected = {1, pages, page}
    for i in range(page - radius, page + radius + 1):
        if 1 <= i <= pages:
            selected.add(i)
    ordered = sorted(selected)
    out: list[int | None] = []
    prev = None
    for n in ordered:
        if prev is not None and n > prev + 1:
            out.append(None)
        out.append(n)
        prev = n
    return out


def _state_map(media_type: str, trakt_ids: list[int]) -> dict[int, UserMediaState]:
    """Load UserMediaState rows keyed by trakt_id."""
    if not trakt_ids:
        return {}
    rows = UserMediaState.query.filter(
        UserMediaState.user_id == current_user.id,
        UserMediaState.media_type == media_type,
        UserMediaState.trakt_id.in_(trakt_ids),
    ).all()
    return {r.trakt_id: r for r in rows}


def _found_map(media_type: str, trakt_ids: list[int]) -> dict[int, list[str]]:
    """Load found-on labels keyed by trakt_id."""
    if not trakt_ids:
        return {}
    rows = MediaFoundOn.query.filter(
        MediaFoundOn.user_id == current_user.id,
        MediaFoundOn.media_type == media_type,
        MediaFoundOn.trakt_id.in_(trakt_ids),
    ).all()
    out: dict[int, list[str]] = {}
    for r in rows:
        out.setdefault(r.trakt_id, []).append(r.service_label)
    return out


def _list_names_map(media_type: str, trakt_ids: list[int]) -> dict[int, list[str]]:
    """Load personal-list names for each title (not watchlist)."""
    if not trakt_ids:
        return {}
    from services.streaming_matcher import WATCHLIST_LIST_ID

    rows = UserListMembership.query.filter(
        UserListMembership.user_id == current_user.id,
        UserListMembership.media_type == media_type,
        UserListMembership.trakt_id.in_(trakt_ids),
    ).all()
    list_ids = {r.list_id for r in rows}
    list_names = {}
    if list_ids:
        try:
            for lst in _personal_lists(current_user):
                if str(lst.get('id')) in list_ids:
                    list_names[str(lst.get('id'))] = lst.get('name') or 'List'
        except Exception as exc:
            current_app.logger.warning('Could not load list names for tags: %s', exc)
    out: dict[int, list[str]] = {}
    for r in rows:
        name = list_names.get(r.list_id) or 'List'
        out.setdefault(r.trakt_id, []).append(name)
    return out


def _marker(media_type: str) -> ReviewMarker | None:
    """Return the user's review marker for a catalog page."""
    return ReviewMarker.query.filter_by(user_id=current_user.id, media_type=media_type).first()


def _decorate(media_type: str, items: list[CachedMedia]) -> list[dict]:
    """Attach preference match, list/watched, found-on flags (marker applied later)."""
    import json

    from services.availability import attach_availability
    from services.streaming_matcher import split_providers_for_user

    ids = [m.trakt_id for m in items]
    states = _state_map(media_type, ids)
    found = _found_map(media_type, ids)
    list_names = _list_names_map(media_type, ids)
    marker = _marker(media_type)
    decorated = []
    for m in items:
        st = states.get(m.trakt_id)
        match = match_preferences(m, current_user)
        try:
            genres = json.loads(m.genres_json or '[]')
        except json.JSONDecodeError:
            genres = []
        if not isinstance(genres, list):
            genres = []
        providers = [
            p.provider_name for p in (m.providers or [])
            if p.offer_type in ('flatrate', 'ads', 'free')
        ]
        my_providers, other_providers = split_providers_for_user(providers, current_user)
        row = {
            'media': m,
            'match': match,
            'on_watchlist': bool(st and st.on_watchlist),
            'watched': bool(st and st.watched),
            'partial': bool(st and st.progress_percent and 0 < st.progress_percent < 100),
            'rating': int(st.rating) if st and st.rating else None,
            'favorited': bool(st and st.favorited),
            'found_on': found.get(m.trakt_id, []),
            'list_names': list_names.get(m.trakt_id, []),
            'genres': genres,
            'providers': providers,
            'my_providers': my_providers,
            'other_providers': other_providers,
            'older_than_marker': False,
            'is_marker': bool(marker and int(marker.trakt_id) == int(m.trakt_id)),
        }
        attach_availability(row)
        decorated.append(row)
    return decorated


def _apply_marker_to_visible_rows(rows: list[dict], media_type: str) -> None:
    """
    Dim the marker row and every row below it in the *visible* list order.

    Uses list position (not timestamp math) so hide-watched / ties cannot
    shift the boundary to the wrong title.
    """
    marker = _marker(media_type)
    if not marker or not rows:
        return
    marker_id = int(marker.trakt_id)
    marker_index = None
    for i, row in enumerate(rows):
        if int(row['media'].trakt_id) == marker_id:
            marker_index = i
            break
    if marker_index is None:
        # Marker title not in this visible feed (e.g. filtered out) — leave undimmed.
        return
    for i, row in enumerate(rows):
        # Include the clicked marker row and every row below it.
        row['is_marker'] = (i == marker_index)
        row['older_than_marker'] = (i >= marker_index)


def _normalize_search_q(raw: str | None) -> str:
    """Strip search query; empty when shorter than 2 chars."""
    q = (raw or '').strip()
    return q if len(q) >= 2 else ''


def _row_title_matches(row: dict, q: str) -> bool:
    """Case-insensitive title/year match for in-list search."""
    if not q:
        return True
    media = row.get('media')
    if not media:
        return False
    needle = q.casefold()
    title = (media.title or '').casefold()
    year = str(media.year or '')
    return needle in title or (bool(year) and needle in year)


@catalog_bp.route('/')
@login_required
def home():
    """Home dashboard with quick links and unread notification count."""
    from models import Notification
    unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return render_template('home.html', unread=unread)


def _search_on_any_list(row: dict) -> bool:
    """True when the title is on Wishlist or any personal list."""
    return bool(row.get('on_watchlist') or row.get('list_names'))


@catalog_bp.route('/search')
@login_required
def search():
    """
    Trakt-wide title and/or actor search (movies and/or shows).

    Results use the same decorated card fields as Latest (lists / watched / streaming).
    Defaults hide watched and already-listed titles (Wishlist + personal lists).
    """
    return render_template('search.html', **_search_catalog())


def _search_catalog() -> dict:
    """Collect Trakt-wide search results and filter state for HTML or JSON."""
    from services import view_prefs
    from services.cast_service import list_favorite_actors, resolve_actor_for_search
    from services.sync_jobs import enrich_media_list_for_display, upsert_cached_media
    from services.streaming_matcher import split_providers_for_user
    from services.tmdb_client import is_configured as tmdb_is_configured

    q = _normalize_search_q(request.args.get('q'))
    actor_q = (request.args.get('actor_q') or '').strip()
    try:
        actor_id_raw = int(request.args.get('actor') or 0)
    except (TypeError, ValueError):
        actor_id_raw = 0
    actor_id = actor_id_raw if actor_id_raw > 0 else None
    type_raw = (request.args.get('type') or 'both').lower()
    if type_raw not in ('movie', 'show', 'both'):
        type_raw = 'both'
    page = max(int(request.args.get('page', 1) or 1), 1)
    per_page = 20
    hide_watched = view_prefs.resolve_bool(
        current_user, 'search', 'hide_watched', 'hide_watched', default=True,
    )
    hide_lists = view_prefs.resolve_bool(
        current_user, 'search', 'hide_lists', 'hide_lists', default=True,
    )
    from services.list_filters import (
        advanced_context, parse_year_filter, resolve_advanced, row_passes_advanced,
    )
    year, filter_genres = resolve_advanced(current_user, 'search')
    year_range = parse_year_filter(year)
    has_advanced = bool(year_range or filter_genres)

    types: list[str] = ['movie', 'show'] if type_raw == 'both' else [type_raw]
    rows: list[dict] = []
    fetch_error = None
    raw_total = 0
    actor = None
    actor_missing = False
    wanted_actor = bool(actor_id or len(actor_q) >= 2)

    if wanted_actor:
        try:
            actor = resolve_actor_for_search(
                current_user, actor_id=actor_id, actor_q=actor_q,
            )
        except Exception as exc:
            current_app.logger.warning('Actor resolve failed: %s', exc)
            actor = None
        if actor:
            actor_id = actor.trakt_id
            if not actor_q:
                actor_q = actor.name or ''
        else:
            actor_missing = True

    has_query = bool(q) or bool(actor)

    if has_query:
        try:
            from services.user_media_sync import ensure_user_media_fresh
            ensure_user_media_fresh(
                current_user, media_types=tuple(types), force=False,
            )
        except Exception as exc:
            current_app.logger.warning('User-state sync before search failed: %s', exc)

        cached_items: list[tuple[str, CachedMedia]] = []
        try:
            from services.trakt_cache import (
                cache_http_span,
                load_search_cache,
                log_cache_event,
                media_from_search_ids,
                save_search_cache,
                search_cache_key,
            )
            force_search = request.args.get('refresh') == '1'
            skey = search_cache_key(
                q=q, actor_id=actor.trakt_id if actor else None, type_raw=type_raw,
            )
            payload = None if force_search else load_search_cache(current_user.id, skey)
            if payload is not None:
                cached_items = media_from_search_ids(payload, types)
                log_cache_event(
                    'search', 'hit', user=current_user, item=skey[:12], calls=0,
                )
            else:
                span = cache_http_span()
                id_payload: dict[str, list[int]] = {'movie': [], 'show': []}
                if actor:
                    for media_type in types:
                        hits = trakt_client.fetch_person_cast_titles(
                            current_user, actor.trakt_id, media_type, limit=80,
                        )
                        for entry in hits:
                            row = upsert_cached_media(media_type, entry)
                            if row:
                                cached_items.append((media_type, row))
                                id_payload[media_type].append(int(row.trakt_id))
                else:
                    # Stable over-fetch so Back / filter toggles reuse this payload.
                    per_type_limit = 50 if type_raw != 'both' else 25
                    for media_type in types:
                        hits = trakt_client.search_titles(
                            current_user, media_type, q, limit=per_type_limit,
                        )
                        for entry in hits:
                            row = upsert_cached_media(media_type, entry)
                            if row:
                                cached_items.append((media_type, row))
                                id_payload[media_type].append(int(row.trakt_id))
                save_search_cache(current_user.id, skey, id_payload)
                log_cache_event(
                    'search', 'fetch', user=current_user, item=skey[:12],
                    reason='force' if force_search else 'stale', calls=span(),
                )
            db.session.commit()
        except Exception as exc:
            fetch_error = str(exc)
            current_app.logger.warning('Trakt search failed: %s', exc)
            flash('Could not search Trakt right now.', 'warning')

        # Decorate per media type (state maps are type-scoped).
        by_type: dict[str, list] = {'movie': [], 'show': []}
        for media_type, media in cached_items:
            by_type[media_type].append(media)
        for media_type, items in by_type.items():
            if not items:
                continue
            decorated = _decorate(media_type, items)
            for r in decorated:
                r['media_type'] = media_type
            rows.extend(decorated)

        if actor and q:
            rows = [r for r in rows if _row_title_matches(r, q)]

        raw_total = len(rows)
        if hide_watched:
            rows = [r for r in rows if not r.get('watched')]
        if hide_lists:
            rows = [r for r in rows if not _search_on_any_list(r)]
        if has_advanced:
            rows = [r for r in rows if row_passes_advanced(r, year_range, filter_genres)]

        # Enrich + providers for the visible slice only (after simple paging).
        total = len(rows)
        pages = max((total + per_page - 1) // per_page, 1) if total else 1
        page = min(page, pages)
        page_rows = rows[(page - 1) * per_page: page * per_page]
        try:
            import json
            enrich_media_list_for_display(
                [r['media'] for r in page_rows], max_fetches=len(page_rows),
            )
            provider_fetches = 0
            for r in page_rows:
                media = r['media']
                if (
                    tmdb_is_configured()
                    and media.tmdb_id
                    and not media.providers
                    and provider_fetches < per_page
                ):
                    sync_providers_for_media(media)
                    provider_fetches += 1
                try:
                    genres = json.loads(media.genres_json or '[]')
                except json.JSONDecodeError:
                    genres = []
                r['genres'] = genres if isinstance(genres, list) else []
                providers = [
                    p.provider_name for p in (media.providers or [])
                    if p.offer_type in ('flatrate', 'ads', 'free')
                ]
                r['providers'] = providers
                r['my_providers'], r['other_providers'] = split_providers_for_user(
                    providers, current_user,
                )
                r['match'] = match_preferences(media, current_user)
            db.session.commit()
        except Exception as exc:
            current_app.logger.warning('Search enrich failed: %s', exc)
    else:
        page_rows = []
        total = 0
        pages = 1

    return {
        'q': q,
        'actor_q': actor_q,
        'actor_id': actor.trakt_id if actor else (actor_id or ''),
        'actor_name': (actor.name if actor else ''),
        'actor_missing': actor_missing,
        'wanted_actor': wanted_actor,
        'favorite_actors': list_favorite_actors(current_user),
        'search_type': type_raw,
        'rows': page_rows,
        'page': page,
        'pages': pages,
        'page_links': _pagination_pages(page, pages),
        'per_page': per_page,
        'total': total,
        'raw_total': raw_total,
        'hide_watched': hide_watched,
        'hide_lists': hide_lists,
        **advanced_context(year, filter_genres),
        'fetch_error': fetch_error,
        'tmdb_configured': tmdb_is_configured(),
        'streaming_region': current_app.config.get('STREAMING_REGION', 'US'),
        'title': 'Search',
    }


@catalog_bp.route('/latest/movies')
@login_required
def latest_movies():
    """Latest movies ordered by Trakt listing/update date."""
    return _latest_page('movie')


@catalog_bp.route('/latest/shows')
@login_required
def latest_shows():
    """Latest shows ordered by Trakt listing/update date."""
    return _latest_page('show')


@catalog_bp.route('/recommendations/movies')
@login_required
def recommended_movies():
    """Personalized Trakt movie recommendations."""
    return _recommendations_page('movie')


@catalog_bp.route('/recommendations/shows')
@login_required
def recommended_shows():
    """Personalized Trakt show recommendations."""
    return _recommendations_page('show')


def _recommendations_page(media_type: str):
    """Shared recommended-movies / recommended-shows listing."""
    from services.streaming_matcher import (
        genre_to_trakt_slug,
        get_user_genres_keywords,
        split_providers_for_user,
    )
    from services.sync_jobs import enrich_media_list_for_display, upsert_cached_media
    from services.tmdb_client import is_configured as tmdb_is_configured

    from services import view_prefs

    view = f'rec_{media_type}s'
    per_page = _per_page(view)
    page = max(int(request.args.get('page', 1) or 1), 1)

    hide_watched = view_prefs.resolve_bool(
        current_user, view, 'hide_watched', 'hide_watched', default=True,
    )
    hide_wishlist = view_prefs.resolve_bool(
        current_user, view, 'hide_wishlist', 'hide_wishlist', default=True,
    )
    on_my_services = view_prefs.resolve_bool(
        current_user, view, 'on_my_services', 'on_my_services',
        default=False, true_when='one',
    )
    match_only = view_prefs.resolve_bool(
        current_user, view, 'match_only', 'match_only',
        default=False, true_when='one',
    )

    user_genres, _keywords = get_user_genres_keywords(current_user)
    category_slugs = {genre_to_trakt_slug(g): g for g in user_genres if genre_to_trakt_slug(g)}
    category = view_prefs.resolve_choice(
        current_user, view, 'category', 'category',
        allowed=set(category_slugs) | {'all'},
        default='all',
    )
    genre_filter = None if category == 'all' else category

    # Local wishlist/watched tags + client-side filters need a fresh cache too.
    try:
        from services.user_media_sync import ensure_user_media_fresh
        ensure_user_media_fresh(current_user, media_types=(media_type,), force=False)
    except Exception as exc:
        current_app.logger.warning('User-state sync before Recs failed: %s', exc)

    fetch_limit = 100
    items: list[CachedMedia] = []
    fetch_error = None
    force_recs = request.args.get('refresh') == '1'
    try:
        from services.trakt_cache import (
            cache_http_span,
            load_recommendations_cache,
            log_cache_event,
            recs_genre_key,
            save_recommendations_cache,
        )
        payload = None
        if not force_recs:
            payload = load_recommendations_cache(
                current_user.id, media_type, genre_filter,
            )
        recs_item = f'{media_type}:{recs_genre_key(genre_filter)}'
        if payload is None:
            span = cache_http_span()
            payload = trakt_client.get_recommendations(
                current_user,
                media_type,
                limit=fetch_limit,
                genres=genre_filter,
                ignore_watched=hide_watched,
                ignore_collected=True,
                ignore_watchlisted=hide_wishlist,
            )
            save_recommendations_cache(
                current_user.id, media_type, genre_filter, payload or [],
            )
            log_cache_event(
                'recs', 'fetch', user=current_user, item=recs_item,
                reason='force' if force_recs else 'stale', calls=span(),
            )
        else:
            log_cache_event('recs', 'hit', user=current_user, item=recs_item, calls=0)
        for entry in payload or []:
            row = upsert_cached_media(media_type, entry)
            if row:
                items.append(row)
        db.session.commit()
    except Exception as exc:
        fetch_error = str(exc)
        current_app.logger.warning('Recommendations fetch failed: %s', exc)
        flash('Could not load recommendations from Trakt right now.', 'warning')

    # Deduplicate while preserving Trakt order.
    seen_ids: set[int] = set()
    unique_items: list[CachedMedia] = []
    for m in items:
        tid = int(m.trakt_id)
        if tid in seen_ids:
            continue
        seen_ids.add(tid)
        unique_items.append(m)

    rows_all = _decorate(media_type, unique_items)
    if hide_wishlist:
        rows_all = [r for r in rows_all if not r['on_watchlist']]
    if hide_watched:
        rows_all = [r for r in rows_all if not r['watched']]
    if match_only:
        rows_all = [r for r in rows_all if r.get('match') and r['match'].get('matched')]

    total_before_services = len(rows_all)

    # Providers are required for "on my services" — fetch for this page's candidates.
    # Cap lookups so a cold cache does not stall the whole list.
    try:
        enrich_media_list_for_display(unique_items, max_fetches=20)
        provider_fetches = 0
        for r in rows_all:
            media = r['media']
            if not media.providers and provider_fetches < 40 and media.tmdb_id:
                sync_providers_for_media(media)
                provider_fetches += 1
                db.session.refresh(media)
            providers = [
                p.provider_name for p in (media.providers or [])
                if p.offer_type in ('flatrate', 'ads', 'free')
            ]
            r['providers'] = providers
            r['my_providers'], r['other_providers'] = split_providers_for_user(
                providers, current_user,
            )
            r['match'] = match_preferences(media, current_user)
        db.session.commit()
    except Exception as exc:
        current_app.logger.warning('Recommendations enrich/providers failed: %s', exc)

    if on_my_services:
        rows_all = [r for r in rows_all if r.get('my_providers')]

    from services.availability import attach_availability, filter_rows_by_avail, normalize_avail

    search_q = _normalize_search_q(request.args.get('q'))
    if search_q:
        rows_all = [r for r in rows_all if _row_title_matches(r, search_q)]
    from services.list_filters import (
        advanced_context, parse_year_filter, resolve_advanced, row_passes_advanced,
    )
    year, filter_genres = resolve_advanced(current_user, view)
    year_range = parse_year_filter(year)
    if year_range or filter_genres:
        rows_all = [r for r in rows_all if row_passes_advanced(r, year_range, filter_genres)]
    avail = normalize_avail(request.args.get('avail'))
    if avail:
        for r in rows_all:
            attach_availability(r)
        rows_all = filter_rows_by_avail(rows_all, avail)

    total = len(rows_all)
    pages = max((total + per_page - 1) // per_page, 1) if total else 1
    page = min(page, pages)
    rows = rows_all[(page - 1) * per_page: page * per_page]
    for r in rows:
        attach_availability(r)

    categories = [{'slug': 'all', 'label': 'All'}]
    for slug, label in sorted(category_slugs.items(), key=lambda kv: kv[1].lower()):
        categories.append({'slug': slug, 'label': label})

    return render_template(
        'recommendations_media.html',
        media_type=media_type,
        rows=rows,
        page=page,
        pages=pages,
        page_links=_pagination_pages(page, pages),
        per_page=per_page,
        total=total,
        total_before_services=total_before_services,
        hide_watched=hide_watched,
        hide_wishlist=hide_wishlist,
        on_my_services=on_my_services,
        match_only=match_only,
        category=category,
        categories=categories,
        has_match_prefs=bool(user_genres or _keywords),
        user_service_names=list(
            dict.fromkeys(
                (r.display_name for r in current_user.streaming_services if r.display_name)
            )
        ),
        tmdb_configured=tmdb_is_configured(),
        streaming_region=current_app.config.get('STREAMING_REGION', 'US'),
        fetch_error=fetch_error,
        search_q=search_q,
        avail=avail,
        **advanced_context(year, filter_genres),
        title='Recommended Movies' if media_type == 'movie' else 'Recommended Shows',
    )


def _latest_feed_query(media_type: str):
    """Ordered Latest-feed query (Trakt DB updates)."""
    return (
        CachedMedia.query
        .filter_by(media_type=media_type, feed_source='trakt_db_updates')
        .order_by(
            CachedMedia.trakt_listed_at.desc(),
            CachedMedia.id.desc(),
        )
    )


def _latest_visible_rows(
    media_type: str,
    hide_watched: bool,
    match_only: bool,
    hide_lists: bool = False,
    *,
    min_year: int | None = None,
) -> tuple[list[dict], dict]:
    """
    Decorate feed rows and apply filters. Returns (rows, stats).

    Year is applied in SQL first so we do not decorate thousands of old stubs.
    """
    from sqlalchemy import or_

    from services.streaming_matcher import media_passes_discovery_year

    cached_total = feed_count(media_type)
    query = _latest_feed_query(media_type)
    if min_year is not None:
        # Keep unknown year (NULL) for stubs; drop clearly-old years in SQL.
        query = query.filter(or_(
            CachedMedia.year.is_(None),
            CachedMedia.year >= int(min_year),
        ))
    items = query.all()
    # released_at-only years (year NULL) still need the Python check.
    if min_year is not None:
        items = [m for m in items if media_passes_discovery_year(m, min_year)]
    after_year = len(items)

    rows_all = _decorate(media_type, items)
    if hide_watched:
        rows_all = [r for r in rows_all if not r['watched']]
    after_watched = len(rows_all)
    if hide_lists:
        rows_all = [r for r in rows_all if not r.get('list_names')]
    after_lists = len(rows_all)
    if match_only:
        rows_all = [r for r in rows_all if r.get('match') and r['match'].get('matched')]
    _apply_marker_to_visible_rows(rows_all, media_type)
    stats = {
        'cached_total': cached_total,
        'after_year': after_year,
        'after_watched': after_watched,
        'after_lists': after_lists,
        'visible': len(rows_all),
    }
    return rows_all, stats


def _latest_page(media_type: str):
    """Shared latest-movies / latest-shows listing (Trakt DB updates feed)."""
    from services.streaming_matcher import discovery_year_cutoff, user_has_match_prefs

    from services import view_prefs

    view = f'latest_{media_type}s'
    per_page = _per_page(view)
    page = max(int(request.args.get('page', 1) or 1), 1)
    # Default: hide titles already watched on Trakt (still “in DB”, just less noise).
    hide_watched = view_prefs.resolve_bool(
        current_user, view, 'hide_watched', 'hide_watched', default=True,
    )
    # Default: hide titles already saved in personal lists so Latest only surfaces new discoveries.
    hide_lists = view_prefs.resolve_bool(
        current_user, view, 'hide_lists', 'hide_lists', default=True,
    )
    # Default: preference matches only (purple) when the user has match prefs.
    # Persist across visits (replaces session-only toggle).
    if 'match_only' in request.args:
        match_only = view_prefs.resolve_bool(
            current_user, view, 'match_only', 'match_only',
            default=user_has_match_prefs(current_user),
        )
    else:
        stored_match = view_prefs.get_view(current_user, view).get('match_only')
        if isinstance(stored_match, bool):
            match_only = stored_match
        else:
            match_only = user_has_match_prefs(current_user)

    # Default: hide old production years (Trakt /updates is mostly metadata noise).
    recent_years = view_prefs.resolve_bool(
        current_user, view, 'recent_years', 'recent_years', default=True,
    )
    min_year = discovery_year_cutoff() if recent_years else None

    # Explicit older-page load only (never invent empty UI pages).
    if request.args.get('load_older') == '1':
        try:
            ensure_catalog_for_offset(media_type)
        except Exception as exc:
            current_app.logger.warning('Manual older catalog fetch failed: %s', exc)
            flash('Could not load an older Trakt page right now.', 'warning')
        args = request.args.to_dict(flat=True)
        args.pop('load_older', None)
        return redirect(url_for(
            'catalog.latest_movies' if media_type == 'movie' else 'catalog.latest_shows',
            **args,
        ))

    try:
        if feed_count(media_type) == 0:
            from services.sync_jobs import bootstrap_catalog_initial
            bootstrap_catalog_initial(media_type)
        else:
            ensure_catalog_through_marker(media_type, current_user)
    except Exception as exc:
        current_app.logger.warning('On-demand catalog sync failed: %s', exc)
        # Cached list still renders; avoid alarming on transient Trakt 429s.
        if '429' not in str(exc):
            flash('Could not refresh catalog from Trakt right now. Showing cached items.', 'warning')

    # Hide-watched uses local watched cache — keep it aligned with Trakt activity.
    try:
        from services.user_media_sync import ensure_user_media_fresh
        ensure_user_media_fresh(current_user, media_types=(media_type,), force=False)
    except Exception as exc:
        current_app.logger.warning('User-state sync before Latest failed: %s', exc)

    from services.sync_jobs import enrich_media_list_for_display
    from services.tmdb_client import is_configured as tmdb_is_configured

    rows_all, filter_stats = _latest_visible_rows(
        media_type, hide_watched, match_only, hide_lists, min_year=min_year,
    )
    from services.availability import filter_rows_by_avail, normalize_avail

    search_q = _normalize_search_q(request.args.get('q'))
    if search_q:
        rows_all = [r for r in rows_all if _row_title_matches(r, search_q)]
    from services.list_filters import (
        advanced_context, parse_year_filter, resolve_advanced, row_passes_advanced,
    )
    year, filter_genres = resolve_advanced(current_user, view)
    year_range = parse_year_filter(year)
    if year_range or filter_genres:
        rows_all = [r for r in rows_all if row_passes_advanced(r, year_range, filter_genres)]
    avail = normalize_avail(request.args.get('avail'))
    if avail:
        # Streaming filter needs providers — enrich a capped batch when cold.
        if avail == 'streaming':
            try:
                from services.sync_jobs import enrich_media_list_for_display as _enrich
                cold = [r['media'] for r in rows_all if r['media'] and not r.get('providers')]
                _enrich(cold[:40], max_fetches=20)
                for r in rows_all:
                    media = r['media']
                    providers = [
                        p.provider_name for p in (media.providers or [])
                        if p.offer_type in ('flatrate', 'ads', 'free')
                    ]
                    r['providers'] = providers
                    from services.streaming_matcher import split_providers_for_user
                    from services.availability import attach_availability
                    r['my_providers'], r['other_providers'] = split_providers_for_user(
                        providers, current_user,
                    )
                    attach_availability(r)
            except Exception as exc:
                current_app.logger.warning('Latest streaming-filter enrich failed: %s', exc)
        rows_all = filter_rows_by_avail(rows_all, avail)
    filter_stats = dict(filter_stats)
    filter_stats['visible'] = len(rows_all)
    # Do NOT auto-fetch older Trakt pages when the filtered list is short — that
    # made every Matches-only load walk the cache slowly. Use "Load older" instead.

    total = len(rows_all)
    # Only real pages from filtered rows — never a phantom empty "next" page.
    pages = max((total + per_page - 1) // per_page, 1) if total else 1
    page = min(page, pages)
    rows = rows_all[(page - 1) * per_page: page * per_page]
    has_more_older = catalog_has_more_older(media_type)

    # Posters only when missing; skip TMDB streaming lookups on the list (detail page).
    try:
        import json
        from services.availability import attach_availability
        from services.streaming_matcher import split_providers_for_user

        enrich_media_list_for_display([r['media'] for r in rows], max_fetches=8)
        for r in rows:
            media = r['media']
            try:
                genres = json.loads(media.genres_json or '[]')
            except json.JSONDecodeError:
                genres = []
            r['genres'] = genres if isinstance(genres, list) else []
            r['providers'] = [
                p.provider_name for p in (media.providers or [])
                if p.offer_type in ('flatrate', 'ads', 'free')
            ]
            r['my_providers'], r['other_providers'] = split_providers_for_user(
                r['providers'], current_user,
            )
            r['match'] = match_preferences(media, current_user)
            attach_availability(r)
    except Exception as exc:
        current_app.logger.warning('Visible-page enrich failed: %s', exc)
    marker = _marker(media_type)
    has_match_prefs = user_has_match_prefs(current_user)
    current_app.logger.info(
        'Latest %s filters: cached=%s after_year=%s after_watched=%s after_lists=%s visible=%s page=%s/%s',
        media_type,
        filter_stats.get('cached_total'),
        filter_stats.get('after_year'),
        filter_stats.get('after_watched'),
        filter_stats.get('after_lists'),
        filter_stats.get('visible'),
        page,
        pages,
    )

    return render_template(
        'latest_media.html',
        media_type=media_type,
        rows=rows,
        page=page,
        pages=pages,
        page_links=_pagination_pages(page, pages),
        per_page=per_page,
        total=total,
        filter_stats=filter_stats,
        marker=marker,
        hide_watched=hide_watched,
        hide_lists=hide_lists,
        match_only=match_only,
        recent_years=recent_years,
        min_discovery_year=min_year,
        has_match_prefs=has_match_prefs,
        has_more_older=has_more_older,
        search_q=search_q,
        avail=avail,
        **advanced_context(year, filter_genres),
        tmdb_configured=tmdb_is_configured(),
        streaming_region=current_app.config.get('STREAMING_REGION', 'US'),
        title='Latest Movies' if media_type == 'movie' else 'Latest Shows',
        feed_blurb=(
            'Ordered by when Trakt last added/changed the title in its database '
            '(official /updates API). Trakt does not publish a separate “first inserted” '
            'timestamp, so first inserts and later metadata edits both appear here. '
            'This is NOT the public release calendar. '
            'By default we hide older production years (metadata-edit noise). '
            'Older Trakt update pages load only when you click Load older. '
            '“Streaming” uses TMDB/JustWatch availability (Trakt does not expose that in its API).'
        ),
    )

@catalog_bp.route('/catalog/<media_type>/<int:trakt_id>')
@login_required
def media_detail(media_type, trakt_id):
    """Show detail metadata, links, providers, and actions for one title."""
    import json
    from services.sync_jobs import enrich_media_details_for_display, upsert_cached_media

    if media_type not in ('movie', 'show'):
        flash('Unknown media type.', 'danger')
        return redirect(url_for('catalog.home'))
    media = CachedMedia.query.filter_by(media_type=media_type, trakt_id=trakt_id).first()
    if not media:
        try:
            summary = trakt_client.fetch_media_summary(media_type, trakt_id)
            media = upsert_cached_media(media_type, summary)
            db.session.commit()
        except Exception as exc:
            current_app.logger.warning('Detail fetch failed: %s', exc)
            flash('Title not found.', 'warning')
            return redirect(url_for('catalog.home'))

    enrich_media_details_for_display(media)
    sync_providers_for_media(media)
    db.session.refresh(media)
    rows = _decorate(media_type, [media])
    try:
        genres = json.loads(media.genres_json or '[]')
    except json.JSONDecodeError:
        genres = []
    from services.cast_service import MAIN_CAST_LIMIT, cast_for_detail
    cast = cast_for_detail(media, current_user)
    return render_template(
        'media_detail.html',
        row=rows[0],
        media_type=media_type,
        genres=genres if isinstance(genres, list) else [],
        cast=cast,
        main_cast_limit=MAIN_CAST_LIMIT,
    )


@catalog_bp.route('/api/watchlist/<media_type>/<int:trakt_id>', methods=['POST'])
@login_required
def api_watchlist(media_type, trakt_id):
    """Add or remove watchlist entry on Trakt and update local cache."""
    action = (request.json or {}).get('action') or request.form.get('action') or 'add'
    try:
        if action == 'remove':
            trakt_client.remove_from_watchlist(current_user, media_type, trakt_id)
            on = False
        else:
            trakt_client.add_to_watchlist(current_user, media_type, trakt_id)
            on = True
        st = UserMediaState.query.filter_by(
            user_id=current_user.id, media_type=media_type, trakt_id=trakt_id
        ).first()
        if not st:
            st = UserMediaState(user_id=current_user.id, media_type=media_type, trakt_id=trakt_id)
            db.session.add(st)
        st.on_watchlist = on
        db.session.commit()
        try:
            from services.user_media_sync import note_user_media_write
            note_user_media_write(
                current_user, media_types=(media_type,), aspects=('watchlist',),
            )
        except Exception:
            pass
        return jsonify({'success': True, 'on_watchlist': on})
    except Exception as exc:
        db.session.rollback()
        return _api_fail(
            'Watchlist action failed',
            exc,
            user_message='Could not update watchlist. Please try again.',
        )


@catalog_bp.route('/api/rating/<media_type>/<int:trakt_id>', methods=['POST'])
@login_required
def api_rating(media_type, trakt_id):
    """Set or clear a 1–10 Trakt rating and update local cache (movies/shows)."""
    if media_type not in ('movie', 'show', 'episode'):
        return jsonify({'success': False, 'message': 'Invalid media type'}), 400
    payload = request.json or {}
    raw = payload.get('rating', payload.get('action'))
    try:
        if raw in (None, '', 'clear', 'remove'):
            trakt_client.remove_rating(current_user, media_type, trakt_id)
            score = None
        else:
            score = int(raw)
            if score < 1 or score > 10:
                return jsonify({'success': False, 'message': 'Rating must be 1–10'}), 400
            trakt_client.add_rating(current_user, media_type, trakt_id, score)
        # Episode ratings are not cached in UserMediaState (progress loads them live).
        if media_type in ('movie', 'show'):
            st = UserMediaState.query.filter_by(
                user_id=current_user.id, media_type=media_type, trakt_id=trakt_id
            ).first()
            if not st:
                st = UserMediaState(
                    user_id=current_user.id, media_type=media_type, trakt_id=trakt_id,
                )
                db.session.add(st)
            st.rating = score
            db.session.commit()
            try:
                from services.user_media_sync import note_user_media_write
                note_user_media_write(
                    current_user, media_types=(media_type,), aspects=('ratings',),
                )
            except Exception:
                pass
        return jsonify({'success': True, 'rating': score})
    except Exception as exc:
        db.session.rollback()
        return _api_fail(
            'Rating action failed',
            exc,
            user_message='Could not update rating. Please try again.',
        )


@catalog_bp.route('/api/feedback/<media_type>/<int:trakt_id>', methods=['GET'])
@login_required
def api_feedback(media_type, trakt_id):
    """Lazy-load the user's Trakt rating + comment for one title/episode."""
    if media_type not in ('movie', 'show', 'episode'):
        return jsonify({'success': False, 'message': 'Invalid media type'}), 400
    try:
        data = trakt_client.get_media_feedback(current_user, media_type, trakt_id)
        return jsonify({'success': True, **data})
    except Exception as exc:
        return _api_fail(
            'Feedback load failed',
            exc,
            user_message='Could not load your Trakt rating/review. Please try again.',
        )


@catalog_bp.route('/api/comment/<media_type>/<int:trakt_id>', methods=['POST'])
@login_required
def api_comment(media_type, trakt_id):
    """Post or update a Trakt comment/review on a movie, show, or episode."""
    if media_type not in ('movie', 'show', 'episode'):
        return jsonify({'success': False, 'message': 'Invalid media type'}), 400
    payload = request.json or {}
    text = (payload.get('comment') or '').strip()
    spoiler = bool(payload.get('spoiler'))
    comment_id = payload.get('comment_id')
    if not text:
        return jsonify({'success': False, 'message': 'Comment text is required'}), 400
    try:
        if comment_id:
            result = trakt_client.update_comment(
                current_user, int(comment_id), text, spoiler=spoiler,
            )
        else:
            result = trakt_client.add_comment(
                current_user, media_type, trakt_id, text, spoiler=spoiler,
            )
        return jsonify({
            'success': True,
            'comment_id': result.get('id') or comment_id,
            'review': bool(result.get('review')),
        })
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400
    except Exception as exc:
        return _api_fail(
            'Comment post failed',
            exc,
            user_message='Could not post review to Trakt. Please try again.',
        )


@catalog_bp.route('/api/favorite/<media_type>/<int:trakt_id>', methods=['POST'])
@login_required
def api_favorite(media_type, trakt_id):
    """Add or remove a title from Trakt favorites and update local cache."""
    if media_type not in ('movie', 'show'):
        return jsonify({'success': False, 'message': 'Invalid media type'}), 400
    action = (request.json or {}).get('action') or 'add'
    try:
        if action == 'remove':
            trakt_client.remove_from_favorites(current_user, media_type, trakt_id)
            on = False
        else:
            trakt_client.add_to_favorites(current_user, media_type, trakt_id)
            on = True
        st = UserMediaState.query.filter_by(
            user_id=current_user.id, media_type=media_type, trakt_id=trakt_id
        ).first()
        if not st:
            st = UserMediaState(
                user_id=current_user.id, media_type=media_type, trakt_id=trakt_id,
            )
            db.session.add(st)
        st.favorited = on
        db.session.commit()
        try:
            from services.user_media_sync import note_user_media_write
            note_user_media_write(
                current_user, media_types=(media_type,), aspects=('favorites',),
            )
        except Exception:
            pass
        return jsonify({'success': True, 'favorited': on})
    except Exception as exc:
        db.session.rollback()
        return _api_fail(
            'Favorite action failed',
            exc,
            user_message='Could not update favorites. Please try again.',
        )


@catalog_bp.route('/api/favorite-actor/<int:trakt_person_id>', methods=['POST'])
@login_required
def api_favorite_actor(trakt_person_id):
    """Add or remove a local favorite actor (Preferences-managed, not Trakt)."""
    from services.cast_service import set_favorite_actor

    action = (request.json or {}).get('action') or request.form.get('action') or 'add'
    favorited = action != 'remove'
    try:
        person = set_favorite_actor(current_user, trakt_person_id, favorited=favorited)
        return jsonify({
            'success': True,
            'favorited': favorited,
            'trakt_id': person.trakt_id,
            'name': person.name,
            'headshot_url': person.headshot_url if favorited else None,
        })
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return _api_fail(
            'Favorite actor action failed',
            exc,
            user_message='Could not update favorite actor. Please try again.',
        )


@catalog_bp.route('/api/lists/membership/<media_type>/<int:trakt_id>', methods=['GET', 'POST'])
@login_required
def api_lists_membership(media_type, trakt_id):
    """
    Read or update Wishlist + personal-list membership for one title.

    Wishlist is always first. Personal lists respect Preferences → show/hide.
    GET selected always mirrors actual membership (on_list). Preferences
    Auto-select defaults are returned as ``defaults`` for Apply my defaults —
    they are not pre-checked after a clear or on reopen.
    """
    if media_type not in ('movie', 'show'):
        return jsonify({'success': False, 'message': 'Invalid media type'}), 400

    st = UserMediaState.query.filter_by(
        user_id=current_user.id, media_type=media_type, trakt_id=trakt_id
    ).first()
    media = CachedMedia.query.filter_by(media_type=media_type, trakt_id=trakt_id).first()
    title = media.title if media else f'{media_type} {trakt_id}'

    try:
        personal = _personal_lists(current_user)
    except Exception as exc:
        return _api_fail(
            'Failed loading Trakt lists',
            exc,
            user_message='Could not load your lists. Please try again.',
        )

    hidden = set(get_hidden_list_ids(current_user))
    visible = [lst for lst in personal if lst['id'] not in hidden]
    visible_ids = {lst['id'] for lst in visible}
    # Only expose defaults that appear in this dialog (Wishlist + visible personal).
    defaults_out = [
        lid for lid in get_default_selected_list_ids(current_user)
        if lid == WATCHLIST_LIST_ID or lid in visible_ids
    ]

    if request.method == 'GET':
        try:
            # Local cache only — never paginate personal lists here. My pages
            # sync memberships via last_activities; a live scan per list made
            # opening Set lists hang on the 2nd/3rd title.
            on_watchlist = bool(st and st.on_watchlist)
            lists_out = [{
                'id': WATCHLIST_LIST_ID,
                'name': 'Wishlist',
                'kind': 'watchlist',
                'selected': on_watchlist,
                'on_list': on_watchlist,
            }]
            for lst in visible:
                on_list = UserListMembership.query.filter_by(
                    user_id=current_user.id,
                    list_id=lst['id'],
                    media_type=media_type,
                    trakt_id=trakt_id,
                ).first() is not None
                lists_out.append({
                    'id': lst['id'],
                    'name': lst['name'],
                    'kind': 'list',
                    'slug': lst.get('slug') or '',
                    'selected': on_list,
                    'on_list': on_list,
                })
            return jsonify({
                'success': True,
                'title': title,
                'lists': lists_out,
                'defaults': defaults_out,
            })
        except Exception as exc:
            return _api_fail(
                'List membership read failed',
                exc,
                user_message='Could not load your lists. Please try again.',
            )

    payload = request.json or {}
    selected_raw = payload.get('selected')
    if not isinstance(selected_raw, list):
        return jsonify({'success': False, 'message': 'selected must be a list'}), 400

    selected = {str(x).strip() for x in selected_raw if str(x).strip()}
    visible_ids = {lst['id'] for lst in visible}
    # Ignore ids for hidden lists or unknown values (except watchlist).
    wanted_lists = {lid for lid in selected if lid in visible_ids}
    want_watchlist = WATCHLIST_LIST_ID in selected
    clear_all = not want_watchlist and not wanted_lists

    try:
        # Diff against local membership cache only (no list_contains_item).
        if want_watchlist:
            if not (st and st.on_watchlist):
                trakt_client.add_to_watchlist(current_user, media_type, trakt_id)
            on_watchlist = True
        else:
            # Remove when local says on, or clear-all (empty selection).
            if (st and st.on_watchlist) or clear_all:
                trakt_client.remove_from_watchlist(current_user, media_type, trakt_id)
            on_watchlist = False

        if clear_all:
            # Drop every cached personal-list row for this title (not only
            # currently visible lists), so a 2nd clear cannot leave orphans.
            mems = UserListMembership.query.filter_by(
                user_id=current_user.id,
                media_type=media_type,
                trakt_id=trakt_id,
            ).all()
            for mem in mems:
                trakt_client.remove_from_list(
                    current_user, mem.list_id, media_type, trakt_id,
                )
                set_list_membership(
                    current_user.id, mem.list_id, media_type, trakt_id, on_list=False
                )
        else:
            for lst in visible:
                lid = lst['id']
                currently = UserListMembership.query.filter_by(
                    user_id=current_user.id,
                    list_id=lid,
                    media_type=media_type,
                    trakt_id=trakt_id,
                ).first() is not None
                want = lid in wanted_lists
                if want and not currently:
                    trakt_client.add_to_list(current_user, lid, media_type, trakt_id)
                    set_list_membership(
                        current_user.id, lid, media_type, trakt_id, on_list=True
                    )
                elif not want and currently:
                    trakt_client.remove_from_list(current_user, lid, media_type, trakt_id)
                    set_list_membership(
                        current_user.id, lid, media_type, trakt_id, on_list=False
                    )

        # Re-load after set_list_membership / _upsert_state may have created the row
        # in this same session (stale ``st is None`` caused duplicate INSERT).
        st = UserMediaState.query.filter_by(
            user_id=current_user.id, media_type=media_type, trakt_id=trakt_id,
        ).first()
        if not st:
            st = UserMediaState(
                user_id=current_user.id, media_type=media_type, trakt_id=trakt_id
            )
            db.session.add(st)
        st.on_watchlist = on_watchlist
        db.session.commit()
        try:
            from services.user_media_sync import note_user_media_write
            note_user_media_write(
                current_user,
                media_types=(media_type,),
                aspects=('watchlist', 'lists'),
            )
        except Exception:
            pass
        return jsonify({
            'success': True,
            'on_watchlist': on_watchlist,
            'selected': (
                ([WATCHLIST_LIST_ID] if on_watchlist else [])
                + sorted(wanted_lists)
            ),
        })
    except Exception as exc:
        db.session.rollback()
        return _api_fail(
            'List membership update failed',
            exc,
            user_message='Could not update lists. Please try again.',
        )


@catalog_bp.route('/api/watched/<media_type>/<int:trakt_id>', methods=['POST'])
@login_required
def api_watched(media_type, trakt_id):
    """Mark watched / unwatched on Trakt and update local cache."""
    action = (request.json or {}).get('action') or request.form.get('action') or 'add'
    try:
        if action == 'remove':
            trakt_client.mark_unwatched(current_user, media_type, trakt_id)
            watched = False
        else:
            trakt_client.mark_watched(current_user, media_type, trakt_id)
            watched = True
        st = UserMediaState.query.filter_by(
            user_id=current_user.id, media_type=media_type, trakt_id=trakt_id
        ).first()
        if not st:
            st = UserMediaState(user_id=current_user.id, media_type=media_type, trakt_id=trakt_id)
            db.session.add(st)
        st.watched = watched
        if watched:
            st.plays = max(st.plays or 0, 1)
            st.last_watched_at = datetime.utcnow()
            # Movies are binary; shows get % from Progress (aired/completed).
            # Never invent show progress_percent=100 here — that stalled alerts
            # when a new season aired before Progress refreshed.
            if media_type == 'movie':
                st.progress_percent = 100.0
            else:
                from services.trakt_cache import patch_show_watched
                patch_show_watched(current_user.id, trakt_id, watched=True)
        else:
            if media_type == 'show':
                from services.trakt_cache import patch_show_watched
                patch_show_watched(current_user.id, trakt_id, watched=False)
        db.session.commit()
        if watched:
            try:
                from services import alerts as alerts_svc
                if media_type == 'movie':
                    alerts_svc.mark_movie_alerts_read(current_user, trakt_id)
                elif media_type == 'show':
                    alerts_svc.mark_show_alerts_read(current_user, trakt_id)
            except Exception as exc:
                current_app.logger.warning(
                    'Could not mark alerts read after watched: %s', exc,
                )
        try:
            from services.user_media_sync import note_user_media_write
            note_user_media_write(
                current_user, media_types=(media_type,), aspects=('watched',),
            )
        except Exception:
            pass
        return jsonify({'success': True, 'watched': watched})
    except Exception as exc:
        db.session.rollback()
        return _api_fail(
            'Watched action failed',
            exc,
            user_message='Could not update watched status. Please try again.',
        )


@catalog_bp.route('/api/review-marker/<media_type>/<int:trakt_id>', methods=['POST'])
@login_required
def api_review_marker(media_type, trakt_id):
    """Set 'I reviewed all items older than this' marker for movies or shows page."""
    media = CachedMedia.query.filter_by(media_type=media_type, trakt_id=trakt_id).first_or_404()
    if not media.trakt_listed_at:
        return jsonify({'success': False, 'message': 'Missing Trakt listed date'}), 400
    marker = ReviewMarker.query.filter_by(user_id=current_user.id, media_type=media_type).first()
    if not marker:
        marker = ReviewMarker(user_id=current_user.id, media_type=media_type, trakt_id=trakt_id,
                              trakt_listed_at=media.trakt_listed_at, title=media.title)
        db.session.add(marker)
    else:
        marker.trakt_id = trakt_id
        marker.trakt_listed_at = media.trakt_listed_at
        marker.title = media.title
        marker.created_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True, 'title': media.title, 'listed_at': media.trakt_listed_at.isoformat()})


@catalog_bp.route('/api/review-marker/<media_type>/clear', methods=['POST'])
@login_required
def api_review_marker_clear(media_type):
    """Remove the review marker for movies or shows (or both when media_type=all)."""
    types = ('movie', 'show') if media_type == 'all' else (media_type,)
    if media_type != 'all' and media_type not in ('movie', 'show'):
        return jsonify({'success': False, 'message': 'Invalid media type'}), 400
    deleted = 0
    for mt in types:
        rows = ReviewMarker.query.filter_by(user_id=current_user.id, media_type=mt).all()
        for row in rows:
            db.session.delete(row)
            deleted += 1
    db.session.commit()
    return jsonify({'success': True, 'deleted': deleted})


@catalog_bp.route('/api/review-marker/<media_type>/caught-up', methods=['POST'])
@login_required
def api_review_marker_caught_up(media_type):
    """
    Set the marker on the newest feed title (= “caught up as of now”).

    Everything currently in the feed becomes dimmed; only newer Trakt updates
    stay undimmed. Useful after changing genres/keywords.
    """
    types = ('movie', 'show') if media_type == 'all' else (media_type,)
    if media_type != 'all' and media_type not in ('movie', 'show'):
        return jsonify({'success': False, 'message': 'Invalid media type'}), 400
    results = {}
    for mt in types:
        newest = _latest_feed_query(mt).first()
        if not newest or not newest.trakt_listed_at:
            results[mt] = None
            continue
        marker = ReviewMarker.query.filter_by(user_id=current_user.id, media_type=mt).first()
        if not marker:
            marker = ReviewMarker(
                user_id=current_user.id,
                media_type=mt,
                trakt_id=newest.trakt_id,
                trakt_listed_at=newest.trakt_listed_at,
                title=newest.title,
            )
            db.session.add(marker)
        else:
            marker.trakt_id = newest.trakt_id
            marker.trakt_listed_at = newest.trakt_listed_at
            marker.title = newest.title
            marker.created_at = datetime.utcnow()
        results[mt] = {'title': newest.title, 'trakt_id': newest.trakt_id}
    db.session.commit()
    return jsonify({'success': True, 'markers': results})


@catalog_bp.route('/api/found-on/<media_type>/<int:trakt_id>', methods=['POST'])
@login_required
def api_found_on(media_type, trakt_id):
    """Replace local 'found on' service labels for a title (multi-select)."""
    if media_type not in ('movie', 'show'):
        return jsonify({'success': False, 'message': 'Invalid media type'}), 400
    payload = request.json or request.form or {}
    labels = payload.get('service_labels')
    if labels is None:
        single = (payload.get('service_label') or '').strip()
        labels = [single] if single else []
    if not isinstance(labels, list):
        return jsonify({'success': False, 'message': 'service_labels must be a list'}), 400
    cleaned = []
    seen = set()
    for raw in labels:
        label = str(raw or '').strip()
        if not label:
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(label[:120])

    MediaFoundOn.query.filter_by(
        user_id=current_user.id, media_type=media_type, trakt_id=trakt_id
    ).delete()
    for label in cleaned:
        db.session.add(MediaFoundOn(
            user_id=current_user.id,
            media_type=media_type,
            trakt_id=trakt_id,
            service_label=label,
        ))
    db.session.commit()
    return jsonify({'success': True, 'found_on': cleaned})


@catalog_bp.route('/api/recommendations/<media_type>/<int:trakt_id>/hide', methods=['POST'])
@login_required
def api_hide_recommendation(media_type, trakt_id):
    """Hide a title from Trakt recommendations (same as Trakt.tv Not interested)."""
    if media_type not in ('movie', 'show'):
        return jsonify({'success': False, 'message': 'Invalid media type'}), 400
    try:
        trakt_client.hide_recommendation(current_user, media_type, trakt_id)
        try:
            from services.trakt_cache import drop_recommendation_from_cache
            drop_recommendation_from_cache(current_user.id, media_type, trakt_id)
            db.session.commit()
        except Exception:
            db.session.rollback()
        return jsonify({'success': True, 'hidden': True, 'trakt_id': int(trakt_id)})
    except Exception as exc:
        return _api_fail(
            'Hide recommendation failed',
            exc,
            user_message='Could not hide recommendation. Please try again.',
        )


@catalog_bp.route('/api/sync-catalog/<media_type>', methods=['POST'])
@login_required
def api_sync_catalog(media_type):
    """Manually refresh newest Latest page from Trakt (keeps older cache; no bulk enrich)."""
    if media_type not in ('movie', 'show'):
        return jsonify({'success': False, 'message': 'bad type'}), 400
    try:
        if feed_count(media_type) == 0:
            from services.sync_jobs import bootstrap_catalog_initial
            count = bootstrap_catalog_initial(media_type)
        else:
            count = refresh_catalog_newest(media_type, pages=1)
        # Skip watchlist/watched sync — full library pagination often dominates Refresh time.
        return jsonify({'success': True, 'count': count})
    except Exception as exc:
        return _api_fail(
            'Catalog sync failed',
            exc,
            user_message='Could not refresh from Trakt. Please try again.',
        )