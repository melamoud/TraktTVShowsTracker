"""
Local preference / streaming match helpers (not Trakt-owned logic).
"""

from __future__ import annotations

import json
import re
from typing import Iterable

from models import CachedMedia, User, UserPreference, UserStreamingService


def _parse_json_list(raw: str | None) -> list[str]:
    """Parse a JSON list of strings safely."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    except json.JSONDecodeError:
        pass
    return []


def get_user_genres_keywords(user: User) -> tuple[list[str], list[str]]:
    """Return (genres, keywords) for a user."""
    prefs = user.preferences
    if not prefs:
        return [], []
    return _parse_json_list(prefs.genres_json), _parse_json_list(prefs.keywords_json)


def user_service_names(user: User) -> set[str]:
    """Lowercased display names of streaming services the user uses."""
    names: set[str] = set()
    for row in user.streaming_services:
        names.add(row.display_name.lower())
    return names


def media_genres(media: CachedMedia) -> list[str]:
    """Return genre list for cached media."""
    return _parse_json_list(media.genres_json)


def match_preferences(media: CachedMedia, user: User) -> dict:
    """
    Compute preference match highlights for a media item.

    Purple highlight is genres + keywords only (not streaming services —
    those flood the feed with false positives).

    Returns dict with keys: matched (bool), genres, keywords, streaming, reasons.
    ``streaming`` is always empty (kept for template/API compatibility).
    """
    genres, keywords = get_user_genres_keywords(user)
    media_genre_list = media_genres(media)
    text_blob = ' '.join([
        media.title or '',
        media.overview or '',
        media.network or '',
        ' '.join(media_genre_list),
    ]).lower()

    matched_genres = [
        g for g in genres
        if g.lower() in {mg.lower() for mg in media_genre_list}
    ]
    matched_keywords = [
        k for k in keywords
        if k.lower() in text_blob
    ]

    reasons = []
    if matched_genres:
        reasons.append('genres: ' + ', '.join(matched_genres))
    if matched_keywords:
        reasons.append('keywords: ' + ', '.join(matched_keywords))

    return {
        'matched': bool(reasons),
        'genres': matched_genres,
        'keywords': matched_keywords,
        'streaming': [],
        'reasons': reasons,
    }


def serialize_prefs(genres: Iterable[str], keywords: Iterable[str]) -> tuple[str, str]:
    """Serialize genre/keyword lists to JSON strings."""
    g = sorted({x.strip() for x in genres if x and x.strip()}, key=str.lower)
    k = sorted({x.strip() for x in keywords if x and x.strip()}, key=str.lower)
    return json.dumps(g), json.dumps(k)


def split_csv_terms(raw: str) -> list[str]:
    """Split a comma/newline separated preference string."""
    parts = re.split(r'[\n,;]+', raw or '')
    return [p.strip() for p in parts if p.strip()]
