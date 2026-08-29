"""JSON serializers for the Android /api/v1 client."""

from __future__ import annotations

from datetime import date, datetime

from services.local_time import format_local_date


def _link_maps():
    """User service URLs + search templates, cached on the request."""
    from services.found_on_links import service_link_maps
    try:
        from flask import g, has_app_context
        from flask_login import current_user
        if has_app_context():
            cached = getattr(g, '_found_on_link_maps', None)
            if cached is None:
                user = current_user if getattr(current_user, 'is_authenticated', False) else None
                cached = service_link_maps(user)
                g._found_on_link_maps = cached
            return cached
    except Exception:
        pass
    return service_link_maps()


def service_link_entries(labels, title=None, year=None) -> list[dict]:
    """[{label, url}] for Found on / Plays on chips (url is None when not clickable)."""
    from services.found_on_links import found_on_open_url
    base, templates = _link_maps()
    out = []
    for label in labels or []:
        name = str(label).strip()
        if not name:
            continue
        out.append({
            'label': name,
            'url': found_on_open_url(
                name,
                title=title,
                year=year,
                base_urls=base,
                search_templates=templates,
            ),
        })
    return out


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep=' ')
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def serialize_media_item(row: dict, media_type: str | None = None) -> dict:
    """Turn a My / Search card row into a JSON object."""
    media = row.get('media')
    st = row.get('state')
    mt = media_type or row.get('media_type') or (getattr(media, 'media_type', None) if media else None)
    trakt_id = None
    if media is not None:
        trakt_id = media.trakt_id
    elif st is not None:
        trakt_id = st.trakt_id

    next_ep = row.get('next_ep')
    next_payload = None
    if next_ep:
        next_payload = {
            'date': _iso(next_ep.get('date')),
            'label': next_ep.get('label'),
            'title': next_ep.get('title'),
        }

    avail = row.get('avail') or {}
    poster_url = None
    if mt and trakt_id:
        poster_url = f'/cache/posters/{mt}/{int(trakt_id)}'

    title = media.title if media else f'{mt} {trakt_id}'
    year = media.year if media else None
    found_on = row.get('found_on') or []
    my_providers = row.get('my_providers') or []
    other_providers = row.get('other_providers') or []

    return {
        'media_type': mt,
        'trakt_id': trakt_id,
        'title': title,
        'year': year,
        'overview': (media.overview or '') if media else '',
        'poster_url': poster_url,
        'genres': row.get('genres') or [],
        'watched': bool(st.watched) if st is not None else bool(row.get('watched')),
        'on_watchlist': bool(st.on_watchlist) if st is not None else bool(row.get('on_watchlist')),
        'list_names': row.get('list_names') or [],
        'pinned': bool(st.pinned) if st is not None else False,
        'rating': (
            int(st.rating) if st is not None and st.rating else row.get('rating')
        ),
        'favorited': bool(st.favorited) if st is not None else bool(row.get('favorited')),
        'progress_percent': (
            float(st.progress_percent)
            if st is not None and st.progress_percent is not None
            else None
        ),
        'episodes_aired': st.episodes_aired if st is not None else None,
        'episodes_completed': st.episodes_completed if st is not None else None,
        'next_episode_season': st.next_episode_season if st is not None else None,
        'next_episode_number': st.next_episode_number if st is not None else None,
        'next_episode_title': st.next_episode_title if st is not None else None,
        'last_episode_aired_at': (
            (format_local_date(st.last_episode_aired_at) or None)
            if st is not None else None
        ),
        'last_episode_label': st.last_episode_label if st is not None else None,
        'next_ep': next_payload,
        'my_providers': my_providers,
        'other_providers': other_providers,
        'found_on': found_on,
        'found_on_links': service_link_entries(found_on, title, year),
        'found_on_choice_links': found_on_choice_links(title, year),
        'my_provider_links': service_link_entries(my_providers, title, year),
        'other_provider_links': service_link_entries(other_providers, title, year),
        'avail': {
            'upcoming': bool(avail.get('upcoming')),
            'theater': bool(avail.get('theater')),
            'streaming': bool(avail.get('streaming')),
            'on_my_services': bool(avail.get('on_my_services')),
            'released_at': _iso(avail.get('released_at')),
        },
        'avail_chips': row.get('avail_chips') or [],
        'imdb_id': media.imdb_id if media else None,
        'trailer_url': media.trailer_url if media else None,
        'slug': media.slug if media else None,
        'network': media.network if media else None,
        'runtime': media.runtime if media else None,
    }


def serialize_cast_member(actor: dict) -> dict:
    """JSON for one Cast row on a title page."""
    return {
        'trakt_id': actor.get('trakt_id'),
        'name': actor.get('name') or '',
        'characters': actor.get('characters') or [],
        'episode_count': actor.get('episode_count'),
        'favorited': bool(actor.get('favorited')),
        'headshot_url': actor.get('headshot_url'),
    }


def found_on_service_choices(user) -> list[str]:
    """User services first, then remaining catalog names (same as the website picker)."""
    from sqlalchemy.orm import joinedload

    from models import StreamingService, UserStreamingService

    if user is None:
        return []

    owned = (
        UserStreamingService.query
        .options(joinedload(UserStreamingService.service))
        .filter_by(user_id=user.id)
        .order_by(UserStreamingService.id)
        .all()
    )
    names = [row.display_name for row in owned if row.display_name]
    seen = {n.lower() for n in names}
    out = list(names)
    for svc in StreamingService.query.order_by(StreamingService.name).all():
        if svc.name and svc.name.lower() not in seen:
            out.append(svc.name)
            seen.add(svc.name.lower())
    return out


def _request_found_on_choices() -> list[str]:
    """Service names for the Found on picker, cached on the request."""
    try:
        from flask import g, has_app_context
        from flask_login import current_user
        if has_app_context():
            cached = getattr(g, '_found_on_choices', None)
            if cached is None:
                user = current_user if getattr(current_user, 'is_authenticated', False) else None
                cached = found_on_service_choices(user)
                g._found_on_choices = cached
            return cached
    except Exception:
        pass
    return []


def found_on_choice_links(title=None, year=None, choices=None) -> list[dict]:
    """[{label, url}] Search/open links for every Found on picker row."""
    labels = choices if choices is not None else _request_found_on_choices()
    return service_link_entries(labels, title, year)


def serialize_media_detail(row: dict, media_type: str, cast: list, choices: list[str]) -> dict:
    """Full title-page JSON (list-card fields plus cast, match, and links)."""
    from services.cast_service import MAIN_CAST_LIMIT

    item = serialize_media_item(row, media_type)
    media = row.get('media')
    match = row.get('match') or {}
    mt = item.get('media_type') or media_type
    trakt_id = item.get('trakt_id')
    slug = item.get('slug') or trakt_id
    imdb = item.get('imdb_id')
    return {
        'item': item,
        'homepage': (media.homepage or None) if media else None,
        'trakt_listed_at': _iso(getattr(media, 'trakt_listed_at', None)) if media else None,
        'released_at': _iso(getattr(media, 'released_at', None)) if media else None,
        'match': {
            'matched': bool(match.get('matched')),
            'genres': match.get('genres') or [],
            'keywords': match.get('keywords') or [],
        },
        'providers': row.get('providers') or [],
        'found_on_choices': list(choices or []),
        'cast': [serialize_cast_member(actor) for actor in (cast or [])],
        'main_cast_limit': MAIN_CAST_LIMIT,
        'trakt_url': f'https://trakt.tv/{mt}s/{slug}' if mt and trakt_id else None,
        'imdb_url': f'https://www.imdb.com/title/{imdb}/' if imdb else None,
    }


def serialize_progress(ctx: dict) -> dict:
    """JSON for the series progress panel."""
    media = ctx.get('media')
    seasons = []
    for season in ctx.get('seasons') or []:
        episodes = []
        for ep in season.get('episodes') or []:
            episodes.append({
                'number': ep.get('number'),
                'title': ep.get('title'),
                'ids': ep.get('ids') or {},
                'trakt_id': ep.get('trakt_id'),
                'watched': bool(ep.get('watched')),
                'aired': bool(ep.get('aired')),
                'air_label': ep.get('air_label') or '',
            })
        seasons.append({
            'number': season.get('number'),
            'label': season.get('label'),
            'is_specials': bool(season.get('is_specials')),
            'episodes': episodes,
            'all_watched': bool(season.get('all_watched')),
            'aired': season.get('aired') or 0,
            'completed': season.get('completed') or 0,
            'default_open': bool(season.get('default_open')),
        })
    next_ep = ctx.get('next_episode')
    return {
        'trakt_id': ctx.get('trakt_id'),
        'title': ctx.get('title') or (media.title if media else ''),
        'poster_url': (
            f"/cache/posters/show/{int(ctx['trakt_id'])}"
            if ctx.get('trakt_id') else None
        ),
        'progress_aired': ctx.get('progress_aired') or 0,
        'progress_completed': ctx.get('progress_completed') or 0,
        'next_episode': next_ep,
        'seasons': seasons,
    }


def serialize_alert_card(card: dict) -> dict:
    """JSON for one Alerts card."""
    n = card.get('n')
    media = card.get('media')
    st = card.get('state')
    pair = card.get('media_pair')
    if pair:
        media_type, trakt_id = pair
    else:
        trakt_id = n.trakt_id if n else None
        media_type = n.media_type if n else None
    poster_url = None
    if media_type in ('movie', 'show') and trakt_id:
        poster_url = f'/cache/posters/{media_type}/{int(trakt_id)}'
    title = media.title if media else (n.title if n else '')
    year = media.year if media else None
    found_on = card.get('found_on') or []
    my_providers = card.get('my_providers') or []
    other_providers = card.get('other_providers') or []
    match = card.get('match') or {}
    return {
        'id': n.id if n else None,
        'alert_type': n.alert_type if n else None,
        'type_label': card.get('type_label') or '',
        'title': n.title if n else '',
        'message': n.message if n else '',
        'headline': card.get('headline') or '',
        'link': n.link if n else None,
        'media_type': media_type,
        'trakt_id': trakt_id,
        'payload_key': n.payload_key if n else None,
        'is_read': bool(n.is_read) if n else False,
        'created_at': _iso(n.created_at) if n else None,
        'poster_url': poster_url,
        'media_title': media.title if media else None,
        'year': year,
        'my_providers': my_providers,
        'other_providers': other_providers,
        'found_on': found_on,
        'found_on_links': service_link_entries(found_on, title, year),
        'my_provider_links': service_link_entries(my_providers, title, year),
        'other_provider_links': service_link_entries(other_providers, title, year),
        'last_episode_aired_at': (
            format_local_date(st.last_episode_aired_at) or None
        ) if st else None,
        'last_episode_label': st.last_episode_label if st else None,
        'kind_label': card.get('kind_label') or '',
        'episode_code': card.get('episode_code') or '',
        'display_title': card.get('display_title') or title,
        'alerts_pinned': bool(card.get('alerts_pinned')),
        'match': {
            'matched': bool(match.get('matched')),
            'genres': list(match.get('genres') or []),
            'keywords': list(match.get('keywords') or []),
        },
    }


def serialize_alert_entry(entry: dict) -> dict:
    """JSON for a single alert or a collapsible show group."""
    if entry.get('kind') == 'group':
        trakt_id = entry.get('trakt_id')
        poster_url = None
        if trakt_id:
            poster_url = f'/cache/posters/show/{int(trakt_id)}'
        return {
            'kind': 'group',
            'media_type': 'show',
            'trakt_id': trakt_id,
            'title': entry.get('title') or '',
            'poster_url': poster_url,
            'kind_label': entry.get('kind_label') or 'Show',
            'alerts_pinned': bool(entry.get('alerts_pinned')),
            'episode_codes': list(entry.get('episode_codes') or []),
            'unread_count': int(entry.get('unread_count') or 0),
            'items': [serialize_alert_card(c) for c in (entry.get('cards') or [])],
        }
    return {
        'kind': 'single',
        'item': serialize_alert_card(entry['card']),
    }
