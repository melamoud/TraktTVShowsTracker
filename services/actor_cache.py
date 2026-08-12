"""
Local actor headshot cache.

Headshots are keyed by Trakt person id under instance/actor_cache and downloaded
at most once per person (TMDB credits batch on title detail, or a single-person
fallback when favoriting).
"""

from __future__ import annotations

import logging
from pathlib import Path

import requests
from flask import current_app

logger = logging.getLogger('app')


def actor_cache_dir() -> Path:
    """Directory for downloaded actor headshots."""
    root = Path(current_app.root_path)
    path = root / 'instance' / 'actor_cache'
    path.mkdir(parents=True, exist_ok=True)
    return path


def local_actor_path(trakt_person_id: int) -> Path | None:
    """Return existing cached headshot path if present."""
    base = actor_cache_dir() / f'person_{int(trakt_person_id)}'
    for ext in ('.webp', '.jpg', '.jpeg', '.png'):
        candidate = Path(str(base) + ext)
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    return None


def local_actor_url(trakt_person_id: int) -> str:
    """App URL that serves a cached actor headshot."""
    return f'/cache/actors/{int(trakt_person_id)}'


def is_local_actor_url(url: str | None) -> bool:
    """True when headshot_url already points at our cache route."""
    return bool(url and str(url).startswith('/cache/actors/'))


def cache_remote_headshot(trakt_person_id: int, remote_url: str) -> str | None:
    """
    Download a remote headshot into local cache.

    Returns the local app URL on success, or None on failure.
    Skips the network when the file already exists.
    """
    if not remote_url or not trakt_person_id:
        return None
    existing = local_actor_path(trakt_person_id)
    if existing:
        return local_actor_url(trakt_person_id)

    url = str(remote_url).strip()
    if url.startswith('//'):
        url = 'https:' + url
    elif not url.startswith('http'):
        url = 'https://' + url.lstrip('/')

    ext = '.webp' if '.webp' in url.lower() else '.jpg'
    dest = actor_cache_dir() / f'person_{int(trakt_person_id)}{ext}'
    try:
        resp = requests.get(
            url,
            timeout=45,
            headers={
                'User-Agent': 'TraktTVShowsTracker/1.0 (local actor cache)',
                'Accept': 'image/webp,image/*,*/*',
            },
        )
        if resp.status_code >= 400 or not resp.content:
            logger.warning(
                'Actor headshot download failed person %s: HTTP %s',
                trakt_person_id, resp.status_code,
            )
            return None
        dest.write_bytes(resp.content)
        return local_actor_url(trakt_person_id)
    except OSError as exc:
        logger.warning('Actor cache write failed person %s: %s', trakt_person_id, exc)
        return None
    except requests.RequestException as exc:
        logger.warning('Actor headshot download error person %s: %s', trakt_person_id, exc)
        return None
