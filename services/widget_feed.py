"""Home-screen widget payload. Does not persist My / Alerts view prefs."""

from __future__ import annotations

from datetime import date

from sqlalchemy import and_, func as sa_func, or_

WIDGET_LIMIT = 80


def build_widget_feed(user, mode: str) -> dict:
    """Return {success, mode, items} for shows, movies, or alerts."""
    key = (mode or 'shows').strip().lower()
    if key not in ('shows', 'movies', 'alerts'):
        key = 'shows'
    if key == 'alerts':
        items = _alert_items(user)
    elif key == 'movies':
        items = _media_items(user, 'movie')
    else:
        items = _media_items(user, 'show')
    return {'success': True, 'mode': key, 'items': items}


def _media_items(user, media_type: str) -> list[dict]:
    from models import CachedMedia, UserMediaState
    from routes.user_routes import (
        _my_filter_lists,
        _resolve_selected_lists,
        _trakt_ids_for_lists,
    )

    view = f'my_{media_type}s'
    filter_lists = _my_filter_lists(user)
    selected = _resolve_selected_lists(user, filter_lists, view)
    list_ids = _trakt_ids_for_lists(user.id, media_type, selected)
    if not list_ids:
        return []

    today = date.today()
    q = UserMediaState.query.filter(
        UserMediaState.user_id == user.id,
        UserMediaState.media_type == media_type,
        UserMediaState.trakt_id.in_(list_ids),
    ).outerjoin(
        CachedMedia,
        and_(
            CachedMedia.media_type == UserMediaState.media_type,
            CachedMedia.trakt_id == UserMediaState.trakt_id,
        ),
    )
    if media_type == 'show':
        from services.shows_cache import (
            newest_aired_show_clause, newest_aired_show_sort_day,
        )
        q = q.filter(
            newest_aired_show_clause(today),
            UserMediaState.next_episode_season.isnot(None),
            UserMediaState.next_episode_number.isnot(None),
            or_(
                UserMediaState.episodes_aired.is_(None),
                UserMediaState.episodes_completed.is_(None),
                sa_func.coalesce(UserMediaState.episodes_aired, 0)
                > sa_func.coalesce(UserMediaState.episodes_completed, 0),
            ),
        )
        states = (
            q.order_by(
                UserMediaState.pinned.desc(),
                newest_aired_show_sort_day().desc(),
                UserMediaState.id.desc(),
            )
            .limit(WIDGET_LIMIT)
            .all()
        )
    else:
        q = q.filter(
            CachedMedia.released_at.isnot(None),
            CachedMedia.released_at <= today,
        )
        states = (
            q.order_by(
                UserMediaState.pinned.desc(),
                CachedMedia.released_at.desc(),
                UserMediaState.id.desc(),
            )
            .limit(WIDGET_LIMIT)
            .all()
        )

    media_by_id = _cached_by_id(media_type, [st.trakt_id for st in states])
    items = []
    for st in states:
        media = media_by_id.get(int(st.trakt_id))
        title = (media.title if media else None) or f'{media_type.title()} {st.trakt_id}'
        if media_type == 'show':
            row = _show_item(user.id, st, title)
            if row['can_watch']:
                items.append(row)
        else:
            items.append(_movie_item(st, title, media))
    return items


def _show_item(user_id: int, st, title: str) -> dict:
    from services.trakt_cache import episode_ids_from_progress

    aired = int(st.episodes_aired or 0)
    done = int(st.episodes_completed or 0)
    remaining = max(aired - done, 0)
    season = st.next_episode_season
    episode = st.next_episode_number
    ep_title = (st.next_episode_title or '').strip()
    subtitle = None
    if season is not None and episode is not None:
        subtitle = f'S{int(season)}E{int(episode)}'
        if ep_title:
            subtitle = f'{subtitle} — {ep_title}'
    remaining_label = None
    if remaining > 0:
        remaining_label = f'{remaining} more to watch'
    elif aired and done:
        remaining_label = f'{done}/{aired} watched'
    ids = {}
    if season is not None and episode is not None:
        ids = episode_ids_from_progress(user_id, st.trakt_id, season, episode)
    can_watch = remaining > 0 and season is not None and episode is not None
    return {
        'id': f'show-{st.trakt_id}',
        'kind': 'show',
        'media_type': 'show',
        'trakt_id': int(st.trakt_id),
        'title': title,
        'poster_url': f'/cache/posters/show/{int(st.trakt_id)}',
        'subtitle': subtitle,
        'remaining_label': remaining_label,
        'can_watch': can_watch,
        'season': int(season) if season is not None else None,
        'episode': int(episode) if episode is not None else None,
        'episode_ids': ids or None,
        'expandable': False,
        'child_count': 0,
        'items': [],
    }


def _movie_item(st, title: str, media) -> dict:
    year = media.year if media else None
    released = None
    if media is not None and media.released_at is not None:
        released = media.released_at.date().isoformat() if hasattr(media.released_at, 'date') else str(media.released_at)[:10]
    subtitle = ' · '.join(str(p) for p in (year, released) if p)
    watched = bool(st.watched)
    return {
        'id': f'movie-{st.trakt_id}',
        'kind': 'movie',
        'media_type': 'movie',
        'trakt_id': int(st.trakt_id),
        'title': title,
        'poster_url': f'/cache/posters/movie/{int(st.trakt_id)}',
        'subtitle': subtitle or None,
        'remaining_label': None if watched else 'Unwatched',
        'can_watch': not watched,
        'season': None,
        'episode': None,
        'episode_ids': None,
        'expandable': False,
        'child_count': 0,
        'items': [],
    }


def _alert_items(user) -> list[dict]:
    from routes.user_routes import _collect_alert_cards, _group_alert_cards, _parse_season_episode

    ctx = _collect_alert_cards()
    cards = ctx.get('cards') or []
    sort = ctx.get('sort') or 'desc'
    entries = _group_alert_cards(cards, group_shows=True, sort=sort)
    remaining_by_show = _remaining_by_show(
        user.id,
        [
            int(e['trakt_id'])
            for e in entries
            if e.get('kind') == 'group' and e.get('trakt_id')
        ] + [
            int((e.get('card') or {}).get('media_pair')[1])
            for e in entries
            if e.get('kind') == 'single'
            and (e.get('card') or {}).get('media_pair')
            and (e.get('card') or {})['media_pair'][0] == 'show'
        ],
    )
    items = []
    for entry in entries:
        if entry.get('kind') == 'group':
            items.append(_alert_group(entry, remaining_by_show, _parse_season_episode))
        else:
            card = entry.get('card') or {}
            items.append(_alert_single(card, remaining_by_show, _parse_season_episode))
    return items[:WIDGET_LIMIT]


def _alert_group(entry: dict, remaining_by_show: dict, parse_se) -> dict:
    trakt_id = int(entry['trakt_id'])
    codes = [c for c in (entry.get('episode_codes') or []) if c]
    unread = int(entry.get('unread_count') or 0)
    count = len(entry.get('cards') or [])
    bits = []
    if codes:
        bits.append(' · '.join(codes[:6]))
    bits.append(f'{count} alerts')
    remaining = remaining_by_show.get(trakt_id)
    children = [
        _alert_child(card, trakt_id, remaining, parse_se)
        for card in (entry.get('cards') or [])
    ]
    return {
        'id': f'group-{trakt_id}',
        'kind': 'group',
        'media_type': 'show',
        'trakt_id': trakt_id,
        'title': entry.get('title') or 'Show',
        'poster_url': f'/cache/posters/show/{trakt_id}',
        'subtitle': ' · '.join(bits),
        'remaining_label': f'{remaining} more to watch' if remaining else None,
        'can_watch': False,
        'season': None,
        'episode': None,
        'episode_ids': None,
        'expandable': True,
        'child_count': count,
        'unread_count': unread,
        'group_key': f'show-{trakt_id}',
        'items': children,
    }


def _alert_single(card: dict, remaining_by_show: dict, parse_se) -> dict:
    n = card.get('n')
    pair = card.get('media_pair')
    media = card.get('media')
    if pair:
        media_type, trakt_id = pair
        trakt_id = int(trakt_id) if trakt_id else None
    else:
        media_type = getattr(n, 'media_type', None)
        trakt_id = int(n.trakt_id) if n and n.trakt_id else None
    title = card.get('display_title') or (media.title if media else None) or (n.title if n else 'Alert')
    season, episode = parse_se(n) if n else (None, None)
    remaining = remaining_by_show.get(trakt_id) if media_type == 'show' and trakt_id else None
    can_watch = False
    if media_type == 'movie' and trakt_id:
        can_watch = True
    elif media_type == 'show' and trakt_id and season is not None and episode is not None:
        can_watch = True
    poster = None
    if media_type in ('movie', 'show') and trakt_id:
        poster = f'/cache/posters/{media_type}/{trakt_id}'
    return {
        'id': f'alert-{getattr(n, "id", 0)}',
        'kind': 'alert',
        'media_type': media_type,
        'trakt_id': trakt_id,
        'title': title,
        'poster_url': poster,
        'subtitle': card.get('headline') or card.get('type_label') or None,
        'remaining_label': f'{remaining} more to watch' if remaining else None,
        'can_watch': can_watch,
        'season': season,
        'episode': episode,
        'episode_ids': None,
        'alert_id': getattr(n, 'id', None),
        'expandable': False,
        'child_count': 0,
        'items': [],
    }


def _alert_child(card: dict, show_id: int, remaining: int | None, parse_se) -> dict:
    row = _alert_single(card, {show_id: remaining} if remaining else {}, parse_se)
    row['kind'] = 'child'
    row['id'] = f'child-{row.get("alert_id") or row["id"]}'
    row['group_key'] = f'show-{show_id}'
    return row


def _remaining_by_show(user_id: int, trakt_ids: list[int]) -> dict[int, int]:
    from models import UserMediaState

    ids = sorted({int(t) for t in trakt_ids if t})
    if not ids:
        return {}
    out = {}
    for st in UserMediaState.query.filter(
        UserMediaState.user_id == user_id,
        UserMediaState.media_type == 'show',
        UserMediaState.trakt_id.in_(ids),
    ).all():
        aired = int(st.episodes_aired or 0)
        done = int(st.episodes_completed or 0)
        left = max(aired - done, 0)
        if left:
            out[int(st.trakt_id)] = left
    return out


def _cached_by_id(media_type: str, trakt_ids: list[int]) -> dict:
    from models import CachedMedia

    ids = [int(t) for t in trakt_ids if t]
    if not ids:
        return {}
    rows = CachedMedia.query.filter(
        CachedMedia.media_type == media_type,
        CachedMedia.trakt_id.in_(ids),
    ).all()
    return {int(m.trakt_id): m for m in rows}
