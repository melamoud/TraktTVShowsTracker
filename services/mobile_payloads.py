"""JSON serializers for the Android /api/v1 client."""

from __future__ import annotations

from datetime import date, datetime


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

    return {
        'media_type': mt,
        'trakt_id': trakt_id,
        'title': media.title if media else f'{mt} {trakt_id}',
        'year': media.year if media else None,
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
        'next_ep': next_payload,
        'my_providers': row.get('my_providers') or [],
        'other_providers': row.get('other_providers') or [],
        'found_on': row.get('found_on') or [],
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
    trakt_id = n.trakt_id if n else None
    media_type = n.media_type if n else None
    poster_url = None
    if media_type in ('movie', 'show') and trakt_id:
        poster_url = f'/cache/posters/{media_type}/{int(trakt_id)}'
    return {
        'id': n.id if n else None,
        'alert_type': n.alert_type if n else None,
        'type_label': card.get('type_label') or '',
        'title': n.title if n else '',
        'message': n.message if n else '',
        'link': n.link if n else None,
        'media_type': media_type,
        'trakt_id': trakt_id,
        'payload_key': n.payload_key if n else None,
        'is_read': bool(n.is_read) if n else False,
        'created_at': _iso(n.created_at) if n else None,
        'poster_url': poster_url,
        'media_title': media.title if media else None,
        'my_providers': card.get('my_providers') or [],
        'other_providers': card.get('other_providers') or [],
    }
