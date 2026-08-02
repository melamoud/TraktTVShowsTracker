"""
Local poster cache.

Trakt forbids hotlinking CDN images in the browser — they must be downloaded
and served from our own app/server.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import requests
from flask import current_app

logger = logging.getLogger('app')

_SAFE_TYPE = re.compile(r'^(movie|show)$')


def poster_cache_dir() -> Path:
    """Directory for downloaded poster files."""
    root = Path(current_app.root_path)
    path = root / 'instance' / 'poster_cache'
    path.mkdir(parents=True, exist_ok=True)
    return path


def local_poster_path(media_type: str, trakt_id: int) -> Path | None:
    """Return existing cached poster path if present."""
    if not _SAFE_TYPE.match(media_type or ''):
        return None
    base = poster_cache_dir() / f'{media_type}_{int(trakt_id)}'
    for ext in ('.webp', '.jpg', '.jpeg', '.png'):
        candidate = Path(str(base) + ext)
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    return None


def local_poster_url(media_type: str, trakt_id: int) -> str:
    """App URL that serves a cached poster."""
    return f'/cache/posters/{media_type}/{int(trakt_id)}'


def is_local_poster_url(url: str | None) -> bool:
    """True when poster_url already points at our cache route."""
    return bool(url and str(url).startswith('/cache/posters/'))


def cache_remote_poster(media_type: str, trakt_id: int, remote_url: str) -> str | None:
    """
    Download a remote Trakt (or other) poster into local cache.

    Returns the local app URL on success, or None on failure.
    """
    if not remote_url or not _SAFE_TYPE.match(media_type or ''):
        return None
    existing = local_poster_path(media_type, trakt_id)
    if existing:
        return local_poster_url(media_type, trakt_id)

    url = str(remote_url).strip()
    if url.startswith('//'):
        url = 'https:' + url
    elif not url.startswith('http'):
        url = 'https://' + url.lstrip('/')

    ext = '.webp' if '.webp' in url.lower() else '.jpg'
    dest = poster_cache_dir() / f'{media_type}_{int(trakt_id)}{ext}'
    try:
        resp = requests.get(
            url,
            timeout=45,
            headers={
                'User-Agent': 'TraktTVShowsTracker/1.0 (local poster cache)',
                'Accept': 'image/webp,image/*,*/*',
            },
        )
        if resp.status_code >= 400 or not resp.content:
            logger.warning(
                'Poster download failed %s %s: HTTP %s',
                media_type, trakt_id, resp.status_code,
            )
            return None
        dest.write_bytes(resp.content)
        return local_poster_url(media_type, trakt_id)
    except OSError as exc:
        logger.warning('Poster cache write failed %s %s: %s', media_type, trakt_id, exc)
        return None
    except requests.RequestException as exc:
        logger.warning('Poster download error %s %s: %s', media_type, trakt_id, exc)
        return None
