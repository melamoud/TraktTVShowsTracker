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
            raise TraktError(f'Trakt API error on {path}', resp.status_code, resp.text)
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


def fetch_recent_updates(media_type: str, start_date: str, pages: int = 2) -> list:
    """
    Titles recently touched in Trakt's database (/movies|/shows/updates).

    This is the official API closest to “added/changed in Trakt DB”.
    Trakt does not expose a separate created_at / first-inserted timestamp.
    Results are oldest-first, so we read the last pages (newest activity).
    start_date must be within ~29 days or Trakt returns [].
    """
    path = f'/{media_type}s/updates/{start_date}'
    base = current_app.config['TRAKT_API_BASE'].rstrip('/')
    headers = _headers()
    params = {'limit': 100, 'page': 1}
    resp = requests.get(f'{base}{path}', headers=headers, params=params, timeout=45)
    if resp.status_code >= 400:
        raise TraktError(f'Trakt API error on {path}', resp.status_code, resp.text)
    page_count = int(resp.headers.get('X-Pagination-Page-Count') or 1)
    pages = max(1, int(pages))
    start_page = max(1, page_count - pages + 1)

    collected: list = []
    for page in range(start_page, page_count + 1):
        if page == 1 and start_page == 1:
            data = resp.json() if resp.content else []
        else:
            r = requests.get(
                f'{base}{path}',
                headers=headers,
                params={'limit': 100, 'page': page},
                timeout=45,
            )
            if r.status_code >= 400:
                raise TraktError(f'Trakt API error on {path}', r.status_code, r.text)
            data = r.json() if r.content else []
        if isinstance(data, list):
            collected.extend(data)

    collected.sort(key=lambda item: item.get('updated_at') or '', reverse=True)
    return collected


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


def get_watchlist(user: User, media_type: str) -> list:
    """Return the user's Trakt watchlist for movies or shows."""
    return api_request('GET', f'/sync/watchlist/{media_type}s', user=user) or []


def get_watched(user: User, media_type: str) -> list:
    """Return the user's watched movies or shows."""
    return api_request('GET', f'/sync/watched/{media_type}s', user=user) or []


def add_to_watchlist(user: User, media_type: str, trakt_id: int) -> dict:
    """Add a movie/show to the user's Trakt watchlist."""
    body = {f'{media_type}s': [{'ids': {'trakt': trakt_id}}]}
    return api_request('POST', '/sync/watchlist', user=user, json_body=body) or {}


def remove_from_watchlist(user: User, media_type: str, trakt_id: int) -> dict:
    """Remove a movie/show from the user's Trakt watchlist."""
    body = {f'{media_type}s': [{'ids': {'trakt': trakt_id}}]}
    return api_request('POST', '/sync/watchlist/remove', user=user, json_body=body) or {}


def mark_watched(user: User, media_type: str, trakt_id: int) -> dict:
    """Mark a movie/show as watched on Trakt."""
    body = {f'{media_type}s': [{'ids': {'trakt': trakt_id}}]}
    return api_request('POST', '/sync/history', user=user, json_body=body) or {}


def mark_unwatched(user: User, media_type: str, trakt_id: int) -> dict:
    """Remove a movie/show from Trakt watch history."""
    body = {f'{media_type}s': [{'ids': {'trakt': trakt_id}}]}
    return api_request('POST', '/sync/history/remove', user=user, json_body=body) or {}


def get_show_progress(user: User, trakt_id: int) -> dict:
    """Return watched progress for a show."""
    return api_request('GET', f'/shows/{trakt_id}/progress/watched', user=user) or {}


def get_show_seasons(trakt_id: int) -> list:
    """Return seasons/episodes metadata for a show."""
    return api_request('GET', f'/shows/{trakt_id}/seasons', params={'extended': 'episodes'}) or []


def mark_episode_watched(user: User, episode_ids: dict) -> dict:
    """Mark one episode watched via Trakt history sync."""
    body = {'episodes': [{'ids': episode_ids}]}
    return api_request('POST', '/sync/history', user=user, json_body=body) or {}


def mark_episode_unwatched(user: User, episode_ids: dict) -> dict:
    """Remove one episode from Trakt history."""
    body = {'episodes': [{'ids': episode_ids}]}
    return api_request('POST', '/sync/history/remove', user=user, json_body=body) or {}
