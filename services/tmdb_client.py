"""
TMDB API client for watch-provider availability (region US by default).
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from flask import current_app

logger = logging.getLogger('app')


class TmdbError(Exception):
    """Raised when a TMDB API call fails."""

    def __init__(self, message, status_code=None, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


def _api_key() -> str:
    """Return configured TMDB API key."""
    return (current_app.config.get('TMDB_API_KEY') or '').strip()


def is_configured() -> bool:
    """True when TMDB API key is present."""
    return bool(_api_key())


def _get(path: str, params: dict | None = None) -> Any:
    """GET a TMDB API path."""
    key = _api_key()
    if not key:
        raise TmdbError('TMDB_API_KEY is not configured')
    params = dict(params or {})
    params['api_key'] = key
    url = f"{current_app.config['TMDB_API_BASE'].rstrip('/')}{path}"
    resp = requests.get(url, params=params, timeout=30)
    if resp.status_code >= 400:
        raise TmdbError(f'TMDB error on {path}', resp.status_code, resp.text)
    return resp.json()


def get_watch_providers(media_type: str, tmdb_id: int, region: str | None = None) -> list[dict]:
    """
    Return normalized watch providers for a movie/tv id in a region.

    media_type: 'movie' or 'show' (mapped to TMDB 'tv')
    """
    if not tmdb_id:
        return []
    region = region or current_app.config.get('STREAMING_REGION', 'US')
    tmdb_type = 'tv' if media_type == 'show' else 'movie'
    data = _get(f'/{tmdb_type}/{tmdb_id}/watch/providers')
    results = (data or {}).get('results') or {}
    regional = results.get(region) or {}
    providers: list[dict] = []
    for offer_type in ('flatrate', 'ads', 'free', 'rent', 'buy'):
        for item in regional.get(offer_type) or []:
            providers.append({
                'provider_name': item.get('provider_name'),
                'tmdb_provider_id': item.get('provider_id'),
                'offer_type': offer_type,
                'region': region,
                'logo_path': item.get('logo_path'),
            })
    return providers


def poster_url(poster_path: str | None, size: str = 'w342') -> str | None:
    """Build a full TMDB image URL from a poster path."""
    if not poster_path:
        return None
    return f'https://image.tmdb.org/t/p/{size}{poster_path}'


def get_poster_for_tmdb_id(media_type: str, tmdb_id: int, size: str = 'w342') -> str | None:
    """Fetch poster path from TMDB movie/tv details and return a full URL."""
    if not tmdb_id or not is_configured():
        return None
    tmdb_type = 'tv' if media_type == 'show' else 'movie'
    data = _get(f'/{tmdb_type}/{tmdb_id}')
    return poster_url((data or {}).get('poster_path'), size=size)


def get_person_profile_url(tmdb_person_id: int, size: str = 'w185') -> str | None:
    """Fetch a TMDB person profile image URL (fallback when credits map is unavailable)."""
    if not tmdb_person_id or not is_configured():
        return None
    data = _get(f'/person/{int(tmdb_person_id)}')
    return poster_url((data or {}).get('profile_path'), size=size)


def get_cast_profile_urls(media_type: str, tmdb_id: int, size: str = 'w185') -> dict[int, str]:
    """
    One TMDB credits call → map of tmdb person id → profile image URL.

    Used to cache cast headshots once per person without N× /person lookups.
    """
    if not tmdb_id or not is_configured():
        return {}
    tmdb_type = 'tv' if media_type == 'show' else 'movie'
    data = _get(f'/{tmdb_type}/{int(tmdb_id)}/credits')
    out: dict[int, str] = {}
    for entry in (data or {}).get('cast') or []:
        if not isinstance(entry, dict):
            continue
        try:
            pid = int(entry.get('id') or 0)
        except (TypeError, ValueError):
            pid = 0
        if not pid:
            continue
        url = poster_url(entry.get('profile_path'), size=size)
        if url:
            out[pid] = url
    return out
