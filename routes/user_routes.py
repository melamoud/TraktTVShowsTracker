"""
User routes: preferences, my movies/shows, series progress, notifications, help.
"""

from datetime import datetime

from flask import (
    Blueprint, current_app, flash, jsonify, redirect, render_template,
    request, url_for,
)
from flask_login import current_user, login_required

from help_utils import get_help_toc, render_help_markdown
from models import (
    CachedMedia, MediaFoundOn, Notification, StreamingService, StreamingServiceSuggestion,
    UserMediaState, UserPreference, UserStreamingService, db,
)
from services import trakt_client
from services.seed import COMMON_GENRES
from services.streaming_matcher import serialize_prefs, split_csv_terms
from services.sync_jobs import (
    ensure_media_cached,
    enrich_media_list_for_display,
    sync_user_media_state,
)

user_bp = Blueprint('user', __name__)


@user_bp.route('/preferences', methods=['GET', 'POST'])
@login_required
def preferences():
    """Configure streaming services, genres, and keywords."""
    prefs = current_user.preferences
    if not prefs:
        prefs = UserPreference(user_id=current_user.id)
        db.session.add(prefs)
        db.session.commit()

    defaults = StreamingService.query.filter_by(is_default=True).order_by(StreamingService.name).all()

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
                            title='New streaming service suggestion',
                            message=(
                                f'{current_user.username} suggested '
                                f'"{custom_name}" as a default service.'
                            ),
                            link='/admin/streaming-services',
                        ))
            flash(f'Custom service "{custom_name}" saved.', 'success')

        genres = split_csv_terms(request.form.get('genres', ''))
        genres.extend(request.form.getlist('genre_checks'))
        keywords = split_csv_terms(request.form.get('keywords', ''))
        g_json, k_json = serialize_prefs(genres, keywords)
        prefs.genres_json = g_json
        prefs.keywords_json = k_json
        prefs.updated_at = datetime.utcnow()
        db.session.commit()
        db.session.expire(current_user)
        flash('Preferences saved.', 'success')
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
    return render_template(
        'preferences.html',
        defaults=defaults,
        selected=selected,
        customs=customs,
        common_genres=COMMON_GENRES,
        user_genres=user_genres,
        user_keywords=user_keywords,
        keywords_text=', '.join(user_keywords),
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


def _my_media(media_type: str):
    """Shared my-movies / my-shows listing with wishlist/watched filters."""
    import json

    filt = (request.args.get('filter') or 'wishlist').lower()
    if filt not in ('wishlist', 'watched', 'both', 'unwatched_episodes'):
        filt = 'wishlist'

    try:
        sync_user_media_state(current_user)
    except Exception as exc:
        current_app.logger.warning('Sync before my-media failed: %s', exc)

    q = UserMediaState.query.filter_by(user_id=current_user.id, media_type=media_type)
    if filt == 'wishlist':
        q = q.filter_by(on_watchlist=True)
    elif filt == 'watched':
        q = q.filter_by(watched=True)
    elif filt == 'unwatched_episodes':
        # Shows with progress not complete (or on watchlist and not fully watched)
        q = q.filter(
            (UserMediaState.on_watchlist.is_(True)) |
            ((UserMediaState.watched.is_(True)) & (UserMediaState.progress_percent < 100)) |
            ((UserMediaState.on_watchlist.is_(True)) & (UserMediaState.watched.is_(False)))
        )
    else:
        q = q.filter(
            (UserMediaState.on_watchlist.is_(True)) | (UserMediaState.watched.is_(True))
        )

    states = q.order_by(UserMediaState.updated_at.desc()).all()
    trakt_ids = [s.trakt_id for s in states]
    try:
        ensure_media_cached(media_type, trakt_ids)
    except Exception as exc:
        current_app.logger.warning('Title enrich for my-media failed: %s', exc)

    media_rows = {
        m.trakt_id: m
        for m in CachedMedia.query.filter(
            CachedMedia.media_type == media_type,
            CachedMedia.trakt_id.in_(trakt_ids or [-1]),
        ).all()
    }
    # Same metadata as Latest: overview, genres, locally cached poster + providers.
    from services.sync_jobs import sync_providers_for_media
    from services.tmdb_client import is_configured as tmdb_is_configured

    try:
        to_enrich = [media_rows[tid] for tid in trakt_ids if tid in media_rows]
        enrich_media_list_for_display(to_enrich, max_fetches=max(len(to_enrich), 25))
        provider_fetches = 0
        for media in to_enrich:
            if (
                tmdb_is_configured()
                and media.tmdb_id
                and not media.providers
                and provider_fetches < 25
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
    if trakt_ids:
        for fo in MediaFoundOn.query.filter(
            MediaFoundOn.user_id == current_user.id,
            MediaFoundOn.media_type == media_type,
            MediaFoundOn.trakt_id.in_(trakt_ids),
        ).all():
            found_map.setdefault(fo.trakt_id, []).append(fo.service_label)

    rows = []
    for st in states:
        media = media_rows.get(st.trakt_id)
        genres = []
        providers = []
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
        rows.append({
            'state': st,
            'media': media,
            'genres': genres,
            'providers': providers,
            'found_on': found_map.get(st.trakt_id, []),
        })

    return render_template(
        'my_media.html',
        media_type=media_type,
        rows=rows,
        filt=filt,
        title='My Movies' if media_type == 'movie' else 'My Shows',
    )


@user_bp.route('/shows/<int:trakt_id>/progress')
@login_required
def series_progress(trakt_id):
    """Series progress screen with dimmed watched seasons/episodes."""
    media = CachedMedia.query.filter_by(media_type='show', trakt_id=trakt_id).first()
    try:
        progress = trakt_client.get_show_progress(current_user, trakt_id)
        seasons = trakt_client.get_show_seasons(trakt_id)
    except Exception as exc:
        current_app.logger.exception('Progress load failed: %s', exc)
        flash('Could not load show progress from Trakt.', 'danger')
        return redirect(url_for('user.my_shows'))

    watched_episode_ids = set()
    next_episode = progress.get('next_episode')
    for season in progress.get('seasons') or []:
        for ep in season.get('episodes') or []:
            if ep.get('completed'):
                watched_episode_ids.add((season.get('number'), ep.get('number')))

    # Build season/episode view model
    season_views = []
    for season in seasons:
        number = season.get('number')
        if number is None or number == 0:
            # Skip specials by default unless they have unwatched content
            pass
        episodes = []
        all_watched = True
        for ep in season.get('episodes') or []:
            ep_no = ep.get('number')
            watched = (number, ep_no) in watched_episode_ids
            if not watched:
                all_watched = False
            episodes.append({
                'number': ep_no,
                'title': ep.get('title'),
                'ids': ep.get('ids') or {},
                'watched': watched,
            })
        season_views.append({
            'number': number,
            'episodes': episodes,
            'all_watched': all_watched and bool(episodes),
        })

    return render_template(
        'series_progress.html',
        media=media,
        trakt_id=trakt_id,
        seasons=season_views,
        next_episode=next_episode,
        title=media.title if media else f'Show {trakt_id}',
    )


@user_bp.route('/api/episode/watched', methods=['POST'])
@login_required
def api_episode_watched():
    """Mark an episode watched or unwatched on Trakt."""
    payload = request.json or {}
    ids = payload.get('ids') or {}
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
        return jsonify({'success': False, 'message': str(exc)}), 400


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
    return render_template('notifications.html', notifications=rows)


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
    """Mark one notification as read."""
    row = Notification.query.filter_by(id=notif_id, user_id=current_user.id).first_or_404()
    row.is_read = True
    db.session.commit()
    if row.link:
        return redirect(row.link)
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
