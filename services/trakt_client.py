"""
Trakt.tv API client (OAuth + catalog + sync write-backs).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import requests
from flask import current_app

from models import User, db
from services.crypto_tokens import decrypt_token, encrypt_token

logger = logging.getLogger('app')


class TraktError(Exception):
    """Raised when a Trakt API call fails."""

    def __init__(self, message, status_code=None, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


def _headers(access_token: str | None = None) -> dict:
    """Build standard Trakt request headers."""
    headers = {
        'Content-Type': 'application/json',
        'trakt-api-version': current_app.config['TRAKT_API_VERSION'],
        'trakt-api-key': current_app.config['TRAKT_CLIENT_ID'],
    }
    if access_token:
        headers['Authorization'] = f'Bearer {access_token}'
    return headers


def oauth_authorize_url(state: str) -> str:
    """Return the Trakt OAuth authorize URL."""
    params = {
        'response_type': 'code',
        'client_id': current_app.config['TRAKT_CLIENT_ID'],
        'redirect_uri': current_app.config['TRAKT_REDIRECT_URI'],
        'state': state,
    }
    return f'https://trakt.tv/oauth/authorize?{urlencode(params)}'


def exchange_code_for_tokens(code: str) -> dict:
    """Exchange an OAuth authorization code for access/refresh tokens."""
    url = f"{current_app.config['TRAKT_API_BASE']}/oauth/token"
    payload = {
        'code': code,
        'client_id': current_app.config['TRAKT_CLIENT_ID'],
        'client_secret': current_app.config['TRAKT_CLIENT_SECRET'],
        'redirect_uri': current_app.config['TRAKT_REDIRECT_URI'],
        'grant_type': 'authorization_code',
    }
    resp = requests.post(url, json=payload, timeout=30)
    if resp.status_code >= 400:
        raise TraktError('Token exchange failed', resp.status_code, resp.text)
    return resp.json()


def refresh_tokens(refresh_token: str) -> dict:
    """Refresh an expired access token."""
    url = f"{current_app.config['TRAKT_API_BASE']}/oauth/token"
    payload = {
        'refresh_token': refresh_token,
        'client_id': current_app.config['TRAKT_CLIENT_ID'],
        'client_secret': current_app.config['TRAKT_CLIENT_SECRET'],
        'redirect_uri': current_app.config['TRAKT_REDIRECT_URI'],
        'grant_type': 'refresh_token',
    }
    resp = requests.post(url, json=payload, timeout=30)
    if resp.status_code >= 400:
        raise TraktError('Token refresh failed', resp.status_code, resp.text)
    return resp.json()


def save_user_tokens(user: User, token_payload: dict) -> None:
    """Persist encrypted tokens and expiry on the user row."""
    user.access_token_enc = encrypt_token(token_payload.get('access_token'))
    user.refresh_token_enc = encrypt_token(token_payload.get('refresh_token'))
    expires_in = int(token_payload.get('expires_in') or 0)
    user.token_expires_at = datetime.utcnow() + timedelta(seconds=max(expires_in - 60, 0))
    db.session.commit()


def ensure_access_token(user: User) -> str:
    """Return a valid access token, refreshing if needed."""
    access = decrypt_token(user.access_token_enc)
    refresh = decrypt_token(user.refresh_token_enc)
    if access and user.token_expires_at and user.token_expires_at > datetime.utcnow():
        return access
    if not refresh:
        raise TraktError('User has no refresh token; re-login required', 401)
    payload = refresh_tokens(refresh)
    save_user_tokens(user, payload)
    return payload['access_token']


def api_request(
    method: str,
    path: str,
    user: User | None = None,
    params: dict | None = None,
    json_body: Any = None,
    paginate_max_pages: int = 1,
) -> Any:
    """
    Perform a Trakt API request. When paginate_max_pages > 1, follow page headers
    and return a combined list.
    """
    base = current_app.config['TRAKT_API_BASE'].rstrip('/')
    access = ensure_access_token(user) if user else None
    headers = _headers(access)
    collected: list = []
    page = 1
    params = dict(params or {})

    while page <= paginate_max_pages:
        params['page'] = page
        resp = requests.request(
            method.upper(),
            f'{base}{path}',
            headers=headers,
            params=params,
            json=json_body,
            timeout=45,
        )
        if resp.status_code == 401 and user:
            # Force refresh once
            refresh = decrypt_token(user.refresh_token_enc)
            if not refresh:
                raise TraktError('Unauthorized', 401, resp.text)
            payload = refresh_tokens(refresh)
            save_user_tokens(user, payload)
            headers = _headers(payload['access_token'])
            resp = requests.request(
                method.upper(),
                f'{base}{path}',
                headers=headers,
                params=params,
                json=json_body,
                timeout=45,
            )
        if resp.status_code >= 400:
            raise TraktError(
                f'Trakt API error on {path} ({resp.status_code})',
                resp.status_code,
                resp.text,
            )
        if resp.status_code == 204 or not resp.content:
            data = None
        else:
            data = resp.json()

        if paginate_max_pages == 1:
            return data

        if isinstance(data, list):
            collected.extend(data)
        else:
            return data

        page_count = int(resp.headers.get('X-Pagination-Page-Count') or 1)
        if page >= page_count:
            break
        page += 1

    return collected


def get_user_settings(access_token: str) -> dict:
    """Fetch the authenticated Trakt user profile/settings."""
    url = f"{current_app.config['TRAKT_API_BASE']}/users/settings"
    resp = requests.get(url, headers=_headers(access_token), timeout=30)
    if resp.status_code >= 400:
        raise TraktError('Failed to load user settings', resp.status_code, resp.text)
    return resp.json()


def _updates_path(media_type: str, start_date: str) -> str:
    """Build Trakt /updates path for movies or shows."""
    if media_type not in ('movie', 'show'):
        raise ValueError(f'Unsupported media_type: {media_type}')
    return f'/{media_type}s/updates/{start_date}'


def probe_updates_pagination(
    media_type: str,
    start_date: str,
    *,
    extended: str | None = None,
) -> dict:
    """
    Probe Trakt /updates pagination for a start_date window.

    Returns dict: page_count, item_count, limit. Page 1 is oldest; page_count is newest.
    start_date must be within ~29 days or Trakt returns [].

    Keep ``extended`` off here — we only need headers. Fetching page 1 with
    extended=full pulls 100 *oldest* full titles and was a major Refresh stall.
    """
    path = _updates_path(media_type, start_date)
    base = current_app.config['TRAKT_API_BASE'].rstrip('/')
    headers = _headers()
    # Tiny page-1 request just to read X-Pagination-Page-Count.
    params: dict = {'limit': 1, 'page': 1}
    if extended:
        params['extended'] = extended
    resp = requests.get(
        f'{base}{path}',
        headers=headers,
        params=params,
        timeout=45,
    )
    if resp.status_code >= 400:
        raise TraktError(
            f'Trakt API error on {path} ({resp.status_code})',
            resp.status_code,
            resp.text,
        )
    return {
        'page_count': max(1, int(resp.headers.get('X-Pagination-Page-Count') or 1)),
        'item_count': int(resp.headers.get('X-Pagination-Item-Count') or 0),
        'limit': int(resp.headers.get('X-Pagination-Limit') or 100),
        # Do not reuse as a full page cache — probe used limit=1.
        'page1': None,
    }


def fetch_updates_pages(
    media_type: str,
    start_date: str,
    from_page: int,
    to_page: int,
    *,
    page1_cache: list | None = None,
    extended: str | None = 'full',
) -> list:
    """
    Fetch inclusive Trakt /updates page range (1 = oldest … page_count = newest).

    Results are sorted newest-first by updated_at.
    Default extended=full so genres/overview arrive without per-title summary calls
    (needed for Matches-only filtering). Callers should request only the newest
    page(s) for Refresh — never walk older pages here.
    """
    path = _updates_path(media_type, start_date)
    base = current_app.config['TRAKT_API_BASE'].rstrip('/')
    headers = _headers()
    from_page = max(1, int(from_page))
    to_page = max(from_page, int(to_page))
    collected: list = []
    for page in range(from_page, to_page + 1):
        if page == 1 and page1_cache is not None:
            data = page1_cache
        else:
            params: dict = {'limit': 100, 'page': page}
            if extended:
                params['extended'] = extended
            r = requests.get(
                f'{base}{path}',
                headers=headers,
                params=params,
                timeout=45,
            )
            if r.status_code >= 400:
                raise TraktError(
                    f'Trakt API error on {path} ({r.status_code})',
                    r.status_code,
                    r.text,
                )
            data = r.json() if r.content else []
        if isinstance(data, list):
            collected.extend(data)
    collected.sort(key=lambda item: item.get('updated_at') or '', reverse=True)
    return collected


def fetch_all_updates(media_type: str, start_date: str) -> list:
    """Fetch every /updates page in the start_date window (bootstrap)."""
    meta = probe_updates_pagination(media_type, start_date)
    return fetch_updates_pages(
        media_type,
        start_date,
        1,
        meta['page_count'],
        page1_cache=None,
    )


def fetch_recent_updates(media_type: str, start_date: str, pages: int | None = None) -> list:
    """
    Titles recently touched in Trakt's database (/movies|/shows/updates).

    If pages is None, fetch the full window. If pages is set, fetch only the
    newest N pages (legacy helper for callers that want a small slice).
    """
    meta = probe_updates_pagination(media_type, start_date)
    page_count = meta['page_count']
    if pages is None:
        start_page = 1
    else:
        pages = max(1, int(pages))
        start_page = max(1, page_count - pages + 1)
    return fetch_updates_pages(
        media_type,
        start_date,
        start_page,
        page_count,
        page1_cache=None,
    )

def fetch_media_summary(media_type: str, trakt_id: int) -> dict:
    """
    Fetch canonical metadata for a movie or show.

    Trakt docs: summary endpoints with extended=full are the source of truth
    for overview/genres/images (prefer full; images is legacy-equivalent).
    """
    if media_type not in ('movie', 'show'):
        raise ValueError(f'Unsupported media_type: {media_type}')
    # Pass extended via params so it isn't dropped when api_request adds page=.
    return api_request(
        'GET',
        f'/{media_type}s/{trakt_id}',
        params={'extended': 'full'},
    ) or {}


def get_watchlist(
    user: User,
    media_type: str,
    *,
    sort_by: str = 'added',
    sort_how: str = 'desc',
    max_pages: int = 50,
) -> list:
    """
    Return the user's Trakt watchlist for movies or shows.

    Uses ``/users/me/watchlist/{type}/{sort_by}/{sort_how}`` (same items as
    ``/sync/watchlist/...``, but with server-side sort + pagination). Default
    ``max_pages=50`` is a full sync; pass ``max_pages=1`` for first page only.
    """
    kind = f'{media_type}s'
    by = (sort_by or 'added').strip() or 'added'
    how = (sort_how or 'desc').strip().lower()
    if how not in ('asc', 'desc'):
        how = 'desc'
    return api_request(
        'GET',
        f'/users/me/watchlist/{kind}/{by}/{how}',
        user=user,
        params={'limit': 100},
        paginate_max_pages=max(1, int(max_pages)),
    ) or []


def get_watched(user: User, media_type: str, *, extended: str | None = None) -> list:
    """
    Return the user's full watched list for movies or shows (all pages).

    Do not pass extended=progress for bulk sync — it is heavy and paginated at
    100/page. Series progress uses get_show_watched_entry() instead.
    """
    params: dict = {'limit': 100}
    if extended:
        params['extended'] = extended
    return api_request(
        'GET',
        f'/sync/watched/{media_type}s',
        user=user,
        params=params,
        paginate_max_pages=50,
    ) or []


def get_show_watched_entry(user: User, trakt_id: int) -> dict | None:
    """
    Find one show in /sync/watched/shows?extended=progress.

    Pages until the show is found (or the list ends). This is the endpoint
    Showly/Kodi use for per-episode watched plays. Returns None when the show
    has no watched plays on Trakt.
    """
    tid = int(trakt_id)
    base = current_app.config['TRAKT_API_BASE'].rstrip('/')
    access = ensure_access_token(user)
    headers = _headers(access)
    page = 1
    page_count = 1
    while page <= page_count and page <= 50:
        resp = requests.get(
            f'{base}/sync/watched/shows',
            headers=headers,
            params={'extended': 'progress', 'limit': 100, 'page': page},
            timeout=45,
        )
        if resp.status_code == 401:
            refresh = decrypt_token(user.refresh_token_enc)
            if not refresh:
                raise TraktError('Unauthorized', 401, resp.text)
            payload = refresh_tokens(refresh)
            save_user_tokens(user, payload)
            headers = _headers(payload['access_token'])
            resp = requests.get(
                f'{base}/sync/watched/shows',
                headers=headers,
                params={'extended': 'progress', 'limit': 100, 'page': page},
                timeout=45,
            )
        if resp.status_code >= 400:
            raise TraktError(
                f'Trakt API error on /sync/watched/shows ({resp.status_code})',
                resp.status_code,
                resp.text,
            )
        data = resp.json() if resp.content else []
        page_count = int(resp.headers.get('X-Pagination-Page-Count') or page)
        for item in data or []:
            ids = ((item.get('show') or {}).get('ids') or {})
            try:
                item_tid = int(ids.get('trakt'))
            except (TypeError, ValueError):
                continue
            if item_tid == tid:
                return item
        if page >= page_count:
            break
        page += 1
    return None


def episode_watched_keys_from_trakt(
    *,
    history: list | None,
    watched_entry: dict | None,
    progress: dict | None,
) -> set[tuple[int, int]]:
    """
    Build (season, episode) watched keys from Trakt sync sources.

    Union of:
    - /sync/history/shows/{id} (Showly fetchSyncShowHistory)
    - /sync/watched/shows?extended=progress seasons[].episodes[].plays
    - /shows/{id}/progress/watched completed / last_watched_at / play_count
    """
    keys: set[tuple[int, int]] = set()
    for item in history or []:
        ep = item.get('episode') or {}
        s_no, e_no = ep.get('season'), ep.get('number')
        if s_no is None or e_no is None:
            continue
        keys.add((int(s_no), int(e_no)))

    for season in (watched_entry or {}).get('seasons') or []:
        s_no = season.get('number')
        if s_no is None:
            continue
        for ep in season.get('episodes') or []:
            e_no = ep.get('number')
            if e_no is None:
                continue
            plays = int(ep.get('plays') or 0)
            if plays > 0 or ep.get('last_watched_at'):
                keys.add((int(s_no), int(e_no)))

    for season in (progress or {}).get('seasons') or []:
        s_no = season.get('number')
        if s_no is None:
            continue
        for ep in season.get('episodes') or []:
            e_no = ep.get('number')
            if e_no is None:
                continue
            stats = ep.get('stats') or {}
            plays = int(stats.get('play_count') or 0)
            if ep.get('completed') or ep.get('last_watched_at') or plays > 0:
                keys.add((int(s_no), int(e_no)))
    return keys


def search_titles(
    user: User,
    media_type: str,
    query: str,
    *,
    limit: int = 20,
) -> list[dict]:
    """
    Search Trakt for movies or shows by text query.

    Calls exact search first, then broader search, and de-duplicates by Trakt id
    (exact hits keep their earlier position). Each item is a Trakt search row
    ``{type, score, movie|show: {...}}`` suitable for ``upsert_cached_media``.
    """
    if media_type not in ('movie', 'show'):
        raise ValueError(f'Unsupported media_type: {media_type}')
    q = (query or '').strip()
    if len(q) < 2:
        return []
    lim = max(1, min(int(limit), 50))
    params = {'query': q, 'extended': 'full', 'limit': lim}
    exact = api_request(
        'GET',
        f'/search/{media_type}/exact',
        user=user,
        params=params,
    ) or []
    broad = api_request(
        'GET',
        f'/search/{media_type}',
        user=user,
        params=params,
    ) or []
    out: list[dict] = []
    seen: set[int] = set()
    for row in list(exact) + list(broad):
        if not isinstance(row, dict):
            continue
        entity = row.get(media_type) or {}
        ids = entity.get('ids') or {}
        try:
            tid = int(ids.get('trakt'))
        except (TypeError, ValueError):
            continue
        if tid in seen:
            continue
        seen.add(tid)
        out.append(row)
        if len(out) >= lim:
            break
    return out


def get_recommendations(
    user: User,
    media_type: str,
    *,
    limit: int = 100,
    genres: str | None = None,
    ignore_watched: bool = True,
    ignore_collected: bool = True,
    ignore_watchlisted: bool = False,
    extended: str = 'full',
) -> list:
    """
    Personalized Trakt recommendations for movies or shows.

    ``genres`` is a Trakt genre slug (or comma-separated slugs), e.g. ``action``
    or ``science-fiction``.
    """
    if media_type not in ('movie', 'show'):
        raise ValueError(f'Unsupported media_type: {media_type}')
    params: dict = {
        'limit': max(1, min(int(limit), 100)),
        'ignore_watched': 'true' if ignore_watched else 'false',
        'ignore_collected': 'true' if ignore_collected else 'false',
        'ignore_watchlisted': 'true' if ignore_watchlisted else 'false',
    }
    if extended:
        params['extended'] = extended
    if genres:
        params['genres'] = genres
    return api_request(
        'GET',
        f'/recommendations/{media_type}s',
        user=user,
        params=params,
    ) or []


def hide_recommendation(user: User, media_type: str, trakt_id: int) -> None:
    """Hide a title from future Trakt recommendations for this user."""
    if media_type not in ('movie', 'show'):
        raise ValueError(f'Unsupported media_type: {media_type}')
    api_request(
        'DELETE',
        f'/recommendations/{media_type}s/{int(trakt_id)}',
        user=user,
    )


def add_to_watchlist(user: User, media_type: str, trakt_id: int) -> dict:
    """Add a movie/show to the user's Trakt watchlist."""
    body = {f'{media_type}s': [{'ids': {'trakt': trakt_id}}]}
    return api_request('POST', '/sync/watchlist', user=user, json_body=body) or {}


def remove_from_watchlist(user: User, media_type: str, trakt_id: int) -> dict:
    """Remove a movie/show from the user's Trakt watchlist."""
    body = {f'{media_type}s': [{'ids': {'trakt': trakt_id}}]}
    return api_request('POST', '/sync/watchlist/remove', user=user, json_body=body) or {}


def get_ratings(user: User, media_type: str) -> list:
    """Return the user's Trakt ratings for movies or shows."""
    if media_type not in ('movie', 'show'):
        raise ValueError(f'Unsupported media_type: {media_type}')
    return api_request(
        'GET',
        f'/sync/ratings/{media_type}s',
        user=user,
        params={'limit': 100},
        paginate_max_pages=50,
    ) or []


def add_rating(user: User, media_type: str, trakt_id: int, rating: int) -> dict:
    """Set a 1–10 Trakt rating for a movie/show."""
    if media_type not in ('movie', 'show'):
        raise ValueError(f'Unsupported media_type: {media_type}')
    score = int(rating)
    if score < 1 or score > 10:
        raise ValueError('rating must be 1–10')
    body = {f'{media_type}s': [{'ids': {'trakt': int(trakt_id)}, 'rating': score}]}
    return api_request('POST', '/sync/ratings', user=user, json_body=body) or {}


def remove_rating(user: User, media_type: str, trakt_id: int) -> dict:
    """Clear the user's Trakt rating for a movie/show."""
    if media_type not in ('movie', 'show'):
        raise ValueError(f'Unsupported media_type: {media_type}')
    body = {f'{media_type}s': [{'ids': {'trakt': int(trakt_id)}}]}
    return api_request('POST', '/sync/ratings/remove', user=user, json_body=body) or {}


def get_favorites(user: User, media_type: str) -> list:
    """Return the user's Trakt favorites for movies or shows."""
    if media_type not in ('movie', 'show'):
        raise ValueError(f'Unsupported media_type: {media_type}')
    return api_request(
        'GET',
        f'/sync/favorites/{media_type}s',
        user=user,
        params={'limit': 100},
        paginate_max_pages=50,
    ) or []


def add_to_favorites(user: User, media_type: str, trakt_id: int) -> dict:
    """Add a movie/show to Trakt favorites."""
    if media_type not in ('movie', 'show'):
        raise ValueError(f'Unsupported media_type: {media_type}')
    body = {f'{media_type}s': [{'ids': {'trakt': int(trakt_id)}}]}
    return api_request('POST', '/sync/favorites', user=user, json_body=body) or {}


def remove_from_favorites(user: User, media_type: str, trakt_id: int) -> dict:
    """Remove a movie/show from Trakt favorites."""
    if media_type not in ('movie', 'show'):
        raise ValueError(f'Unsupported media_type: {media_type}')
    body = {f'{media_type}s': [{'ids': {'trakt': int(trakt_id)}}]}
    return api_request('POST', '/sync/favorites/remove', user=user, json_body=body) or {}


def get_personal_lists(user: User) -> list[dict]:
    """
    Return the user's Trakt personal/custom lists (not watchlist).

    Each item is normalized to ``{id, slug, name, item_count}`` where ``id`` is
    the Trakt list id as a string (stable for prefs + membership APIs).
    """
    raw = api_request(
        'GET',
        '/users/me/lists',
        user=user,
        params={'limit': 100},
        paginate_max_pages=10,
    ) or []
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        ids = item.get('ids') or {}
        list_id = ids.get('trakt')
        if list_id is None:
            continue
        out.append({
            'id': str(int(list_id)),
            'slug': (ids.get('slug') or '') or '',
            'name': (item.get('name') or f'List {list_id}').strip() or f'List {list_id}',
            'item_count': int(item.get('item_count') or 0),
        })
    out.sort(key=lambda x: x['name'].lower())
    return out


def _list_item_trakt_id(item: dict, media_type: str) -> int | None:
    """Extract the movie/show Trakt id from a list-items row."""
    entity = item.get(media_type) or {}
    ids = entity.get('ids') or {}
    try:
        return int(ids.get('trakt'))
    except (TypeError, ValueError):
        return None


def get_list_items(user: User, list_id: str, media_type: str) -> list:
    """
    Return all movie/show rows on a personal Trakt list (paginated).

    Each row is the raw Trakt list-items object (includes nested movie/show).
    """
    if media_type not in ('movie', 'show'):
        raise ValueError(f'Unsupported media_type: {media_type}')
    lid = str(list_id).strip()
    if not lid:
        return []
    # Manual pagination: api_request(paginate_max_pages=1) always hits page 1.
    base = current_app.config['TRAKT_API_BASE'].rstrip('/')
    access = ensure_access_token(user)
    headers = _headers(access)
    path = f'/users/me/lists/{lid}/items/{media_type}s'
    collected: list = []
    page = 1
    page_count = 1
    while page <= page_count and page <= 50:
        resp = requests.get(
            f'{base}{path}',
            headers=headers,
            params={'limit': 100, 'page': page},
            timeout=45,
        )
        if resp.status_code == 401:
            refresh = decrypt_token(user.refresh_token_enc)
            if not refresh:
                raise TraktError('Unauthorized', 401, resp.text)
            payload = refresh_tokens(refresh)
            save_user_tokens(user, payload)
            headers = _headers(payload['access_token'])
            resp = requests.get(
                f'{base}{path}',
                headers=headers,
                params={'limit': 100, 'page': page},
                timeout=45,
            )
        if resp.status_code >= 400:
            raise TraktError(
                f'Trakt API error on {path} ({resp.status_code})',
                resp.status_code,
                resp.text,
            )
        data = resp.json() if resp.content else []
        page_count = int(resp.headers.get('X-Pagination-Page-Count') or page)
        if isinstance(data, list):
            collected.extend(data)
        if page >= page_count:
            break
        page += 1
    return collected


def list_contains_item(user: User, list_id: str, media_type: str, trakt_id: int) -> bool:
    """True when the movie/show is already on the given personal list."""
    tid = int(trakt_id)
    for item in get_list_items(user, list_id, media_type):
        if _list_item_trakt_id(item, media_type) == tid:
            return True
    return False


def add_to_list(user: User, list_id: str, media_type: str, trakt_id: int) -> dict:
    """Add a movie/show to a personal Trakt list."""
    if media_type not in ('movie', 'show'):
        raise ValueError(f'Unsupported media_type: {media_type}')
    lid = str(list_id).strip()
    body = {f'{media_type}s': [{'ids': {'trakt': int(trakt_id)}}]}
    return api_request(
        'POST',
        f'/users/me/lists/{lid}/items',
        user=user,
        json_body=body,
    ) or {}


def remove_from_list(user: User, list_id: str, media_type: str, trakt_id: int) -> dict:
    """Remove a movie/show from a personal Trakt list."""
    if media_type not in ('movie', 'show'):
        raise ValueError(f'Unsupported media_type: {media_type}')
    lid = str(list_id).strip()
    body = {f'{media_type}s': [{'ids': {'trakt': int(trakt_id)}}]}
    return api_request(
        'POST',
        f'/users/me/lists/{lid}/items/remove',
        user=user,
        json_body=body,
    ) or {}


def mark_watched(user: User, media_type: str, trakt_id: int) -> dict:
    """Mark a movie/show as watched on Trakt."""
    body = {f'{media_type}s': [{'ids': {'trakt': trakt_id}}]}
    return api_request('POST', '/sync/history', user=user, json_body=body) or {}


def mark_unwatched(user: User, media_type: str, trakt_id: int) -> dict:
    """Remove a movie/show from Trakt watch history."""
    body = {f'{media_type}s': [{'ids': {'trakt': trakt_id}}]}
    return api_request('POST', '/sync/history/remove', user=user, json_body=body) or {}


def _season_history_body(show_trakt_id: int, season_number: int) -> dict:
    return {
        'shows': [{
            'ids': {'trakt': int(show_trakt_id)},
            'seasons': [{'number': int(season_number)}],
        }]
    }


def mark_season_watched(user: User, show_trakt_id: int, season_number: int) -> dict:
    """
    Mark all aired episodes in a season as watched on Trakt.

    Uses Trakt's season history payload (same as marking a season on Trakt.tv).
    """
    body = _season_history_body(show_trakt_id, season_number)
    result = api_request('POST', '/sync/history', user=user, json_body=body) or {}
    not_found_shows = (result.get('not_found') or {}).get('shows') or []
    not_found_seasons = (result.get('not_found') or {}).get('seasons') or []
    added = int(((result.get('added') or {}).get('episodes')) or 0)
    # Trakt may already have every episode watched → added can be 0 with empty not_found.
    if not_found_shows or not_found_seasons:
        raise TraktError(
            'Trakt did not record the season watch (show/season not found)',
            400,
            result,
        )
    if added < 1 and not result.get('added'):
        # Empty / unexpected payload — treat as failure so the UI does not lie.
        raise TraktError(
            'Trakt did not record the season watch',
            400,
            result,
        )
    return result


def mark_season_unwatched(user: User, show_trakt_id: int, season_number: int) -> dict:
    """
    Remove all watch history for one season on Trakt.

    Same season payload as mark_season_watched, posted to /sync/history/remove.
    """
    body = _season_history_body(show_trakt_id, season_number)
    result = api_request('POST', '/sync/history/remove', user=user, json_body=body) or {}
    not_found_shows = (result.get('not_found') or {}).get('shows') or []
    not_found_seasons = (result.get('not_found') or {}).get('seasons') or []
    deleted = int(((result.get('deleted') or {}).get('episodes')) or 0)
    if not_found_shows or not_found_seasons:
        raise TraktError(
            'Trakt did not clear the season (show/season not found)',
            400,
            result,
        )
    if deleted < 1 and not result.get('deleted'):
        raise TraktError(
            'Trakt did not clear the season watch history',
            400,
            result,
        )
    return result


def get_show_progress(user: User, trakt_id: int) -> dict:
    """Return watched progress for a show (aired window; completed flags can be stale)."""
    return api_request('GET', f'/shows/{trakt_id}/progress/watched', user=user) or {}


def get_show_watch_history(user: User, trakt_id: int) -> list:
    """
    Episode watch history for one show (all pages).

    Prefer this over progress.completed — Trakt's progress totals/flags are often
    wrong while history + episode checkmarks stay correct.
    """
    return api_request(
        'GET',
        f'/sync/history/shows/{trakt_id}',
        user=user,
        params={'limit': 100},
        paginate_max_pages=50,
    ) or []


def get_show_seasons(trakt_id: int) -> list:
    """Return seasons/episodes metadata (includes first_aired when using episodes,full)."""
    return api_request(
        'GET',
        f'/shows/{trakt_id}/seasons',
        params={'extended': 'episodes,full'},
    ) or []


def sanitize_episode_ids(episode_ids: dict | None) -> dict:
    """
    Keep only scalar Trakt episode id fields.

    Season metadata often includes nested objects (e.g. plex.guid). Sending those
    in /sync/history can return HTTP 200 with added.episodes=0 (silent no-op).
    """
    if not episode_ids:
        return {}
    clean: dict = {}
    for key in ('trakt', 'tvdb', 'tmdb', 'imdb'):
        val = episode_ids.get(key)
        if val is None or isinstance(val, (dict, list)):
            continue
        clean[key] = val
    return clean


def mark_episode_watched(user: User, episode_ids: dict) -> dict:
    """Mark one episode watched via Trakt history sync."""
    ids = sanitize_episode_ids(episode_ids)
    if not ids:
        raise TraktError('Episode ids required', 400)
    body = {'episodes': [{'ids': ids}]}
    result = api_request('POST', '/sync/history', user=user, json_body=body) or {}
    not_found = (result.get('not_found') or {}).get('episodes') or []
    added = int(((result.get('added') or {}).get('episodes')) or 0)
    # Trakt can return HTTP 200 with added.episodes=0 (silent no-op) when ids
    # are rejected — same class of failure as nested plex.guid payloads.
    if not_found or added < 1:
        raise TraktError(
            'Trakt did not record the watch (episode not added to history)',
            400,
            result,
        )
    return result


def mark_episode_unwatched(user: User, episode_ids: dict) -> dict:
    """Remove one episode from Trakt history."""
    ids = sanitize_episode_ids(episode_ids)
    if not ids:
        raise TraktError('Episode ids required', 400)
    body = {'episodes': [{'ids': ids}]}
    result = api_request('POST', '/sync/history/remove', user=user, json_body=body) or {}
    not_found = (result.get('not_found') or {}).get('episodes') or []
    deleted = int(((result.get('deleted') or {}).get('episodes')) or 0)
    if not_found or deleted < 1:
        raise TraktError(
            'Trakt did not remove the watch (episode not found in history)',
            400,
            result,
        )
    return result
