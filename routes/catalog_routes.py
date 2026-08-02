"""
Catalog routes: home, latest movies/shows, detail, review markers, Trakt actions.
"""

from datetime import datetime

from flask import (
    Blueprint, abort, current_app, flash, jsonify, redirect, render_template,
    request, send_file, session, url_for,
)
from flask_login import current_user, login_required

from models import CachedMedia, MediaFoundOn, ReviewMarker, ReleaseWatch, UserMediaState, db
from services import trakt_client
from services.streaming_matcher import match_preferences
from services.sync_jobs import (
    catalog_has_more_older,
    ensure_catalog_for_offset,
    ensure_catalog_through_marker,
    feed_count,
    refresh_catalog_newest,
    sync_catalog,
    sync_providers_for_media,
    sync_user_media_state,
)

catalog_bp = Blueprint('catalog', __name__)


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


def _per_page(view_type: str) -> int:
    """Resolve allowed page size for a catalog view."""
    allowed = current_app.config.get('ALLOWED_PER_PAGE', (10, 50, 100))
    default = current_app.config.get('DEFAULT_PER_PAGE', 50)
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


def _marker(media_type: str) -> ReviewMarker | None:
    """Return the user's review marker for a catalog page."""
    return ReviewMarker.query.filter_by(user_id=current_user.id, media_type=media_type).first()


def _decorate(media_type: str, items: list[CachedMedia]) -> list[dict]:
    """Attach preference match, list/watched, found-on flags (marker applied later)."""
    import json

    ids = [m.trakt_id for m in items]
    states = _state_map(media_type, ids)
    found = _found_map(media_type, ids)
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
        decorated.append({
            'media': m,
            'match': match,
            'on_watchlist': bool(st and st.on_watchlist),
            'watched': bool(st and st.watched),
            'partial': bool(st and st.progress_percent and 0 < st.progress_percent < 100),
            'found_on': found.get(m.trakt_id, []),
            'genres': genres,
            'providers': [p.provider_name for p in (m.providers or []) if p.offer_type in ('flatrate', 'ads', 'free')],
            'older_than_marker': False,
            'is_marker': bool(marker and int(marker.trakt_id) == int(m.trakt_id)),
        })
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


@catalog_bp.route('/')
@login_required
def home():
    """Home dashboard with quick links and unread notification count."""
    from models import Notification
    unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return render_template('home.html', unread=unread)


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


def _latest_visible_rows(media_type: str, hide_watched: bool) -> list[dict]:
    """Decorate feed rows and apply hide-watched + review-marker dimming."""
    items_all = _latest_feed_query(media_type).all()
    rows_all = _decorate(media_type, items_all)
    if hide_watched:
        rows_all = [r for r in rows_all if not r['watched']]
    _apply_marker_to_visible_rows(rows_all, media_type)
    return rows_all


def _latest_page(media_type: str):
    """Shared latest-movies / latest-shows listing (Trakt DB updates feed)."""
    view = f'latest_{media_type}s'
    per_page = _per_page(view)
    page = max(int(request.args.get('page', 1) or 1), 1)
    # Default: hide titles already watched on Trakt (still “in DB”, just less noise).
    hide_watched = request.args.get('hide_watched', '1') != '0'

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

    from services.sync_jobs import enrich_media_list_for_display
    from services.tmdb_client import is_configured as tmdb_is_configured

    rows_all = _latest_visible_rows(media_type, hide_watched)
    # Lazy-load older Trakt pages when the UI page needs more rows, or when the
    # user is on/past the last filled page (so Next reveals older than "today").
    needed = page * per_page
    filled_pages = max((len(rows_all) + per_page - 1) // per_page, 1) if rows_all else 1
    lazy_rounds = 0
    while catalog_has_more_older(media_type) and lazy_rounds < 5:
        need_more_rows = len(rows_all) < needed
        on_tail = page >= filled_pages
        if not need_more_rows and not on_tail:
            break
        # Prefetch only a couple older API pages when merely sitting on the tail.
        if not need_more_rows and on_tail and lazy_rounds >= 2:
            break
        try:
            if not ensure_catalog_for_offset(media_type):
                break
        except Exception as exc:
            current_app.logger.warning('Lazy older catalog fetch failed: %s', exc)
            break
        rows_all = _latest_visible_rows(media_type, hide_watched)
        filled_pages = max((len(rows_all) + per_page - 1) // per_page, 1) if rows_all else 1
        lazy_rounds += 1

    total = len(rows_all)
    filled_pages = max((total + per_page - 1) // per_page, 1) if total else 1
    pages = filled_pages
    # If more older Trakt pages exist, expose one extra page so Next can lazy-load.
    if catalog_has_more_older(media_type):
        pages = max(filled_pages + 1, page)
    else:
        page = min(page, pages)
    rows = rows_all[(page - 1) * per_page: page * per_page]
    # Trakt /updates stubs have no plot/art — fetch for the visible page only.
    # Keep marker flags from the full-list pass above (do not re-apply on the slice).
    try:
        import json
        enrich_media_list_for_display([r['media'] for r in rows])
        # Streaming availability comes from TMDB (same JustWatch source Trakt uses).
        provider_fetches = 0
        for r in rows:
            media = r['media']
            has_providers = bool(media.providers)
            if tmdb_is_configured() and media.tmdb_id and not has_providers and provider_fetches < 20:
                sync_providers_for_media(media)
                provider_fetches += 1
                db.session.refresh(media)
            try:
                genres = json.loads(media.genres_json or '[]')
            except json.JSONDecodeError:
                genres = []
            r['genres'] = genres if isinstance(genres, list) else []
            r['providers'] = [
                p.provider_name for p in (media.providers or [])
                if p.offer_type in ('flatrate', 'ads', 'free')
            ]
    except Exception as exc:
        current_app.logger.warning('Visible-page enrich failed: %s', exc)
    marker = _marker(media_type)

    return render_template(
        'latest_media.html',
        media_type=media_type,
        rows=rows,
        page=page,
        pages=pages,
        page_links=_pagination_pages(page, pages),
        per_page=per_page,
        total=total,
        marker=marker,
        hide_watched=hide_watched,
        has_more_older=catalog_has_more_older(media_type),
        tmdb_configured=tmdb_is_configured(),
        streaming_region=current_app.config.get('STREAMING_REGION', 'US'),
        title='Latest Movies' if media_type == 'movie' else 'Latest Shows',
        feed_blurb=(
            'Ordered by when Trakt last added/changed the title in its database '
            '(official /updates API). Trakt does not publish a separate “first inserted” '
            'timestamp, so first inserts and later metadata edits both appear here. '
            'This is NOT the public release calendar. '
            'Newest pages load first; older activity loads as you page. '
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

    media = enrich_media_details_for_display(media)
    sync_providers_for_media(media)
    db.session.refresh(media)
    rows = _decorate(media_type, [media])
    try:
        genres = json.loads(media.genres_json or '[]')
    except json.JSONDecodeError:
        genres = []
    return render_template(
        'media_detail.html',
        row=rows[0],
        media_type=media_type,
        genres=genres if isinstance(genres, list) else [],
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
        return jsonify({'success': True, 'on_watchlist': on})
    except Exception as exc:
        current_app.logger.exception('Watchlist action failed: %s', exc)
        return jsonify({'success': False, 'message': str(exc)}), 400


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
            st.progress_percent = 100.0
        db.session.commit()
        return jsonify({'success': True, 'watched': watched})
    except Exception as exc:
        current_app.logger.exception('Watched action failed: %s', exc)
        return jsonify({'success': False, 'message': str(exc)}), 400


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


@catalog_bp.route('/api/release-watch/<media_type>/<int:trakt_id>', methods=['POST'])
@login_required
def api_release_watch(media_type, trakt_id):
    """Watch a title for in-app alert when it appears on any streaming service."""
    media = CachedMedia.query.filter_by(media_type=media_type, trakt_id=trakt_id).first()
    title = media.title if media else f'{media_type} {trakt_id}'
    row = ReleaseWatch.query.filter_by(
        user_id=current_user.id, media_type=media_type, trakt_id=trakt_id
    ).first()
    if not row:
        row = ReleaseWatch(
            user_id=current_user.id, media_type=media_type, trakt_id=trakt_id, title=title
        )
        db.session.add(row)
    else:
        row.active = True
        row.notified_at = None
        row.title = title
    db.session.commit()
    return jsonify({'success': True})


@catalog_bp.route('/api/sync-catalog/<media_type>', methods=['POST'])
@login_required
def api_sync_catalog(media_type):
    """Manually refresh newest Latest activity from Trakt (keeps older cache)."""
    if media_type not in ('movie', 'show'):
        return jsonify({'success': False, 'message': 'bad type'}), 400
    try:
        if feed_count(media_type) == 0:
            from services.sync_jobs import bootstrap_catalog_initial
            count = bootstrap_catalog_initial(media_type)
        else:
            count = refresh_catalog_newest(media_type, pages=2)
        sync_user_media_state(current_user)
        return jsonify({'success': True, 'count': count})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400