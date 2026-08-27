"""
Local preference / streaming match helpers (not Trakt-owned logic).
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
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


def get_user_excluded_genres(user: User) -> list[str]:
    """Return genres the user never wants on Latest, Recs, or alerts."""
    prefs = getattr(user, 'preferences', None)
    if not prefs:
        return []
    return _parse_json_list(getattr(prefs, 'excluded_genres_json', None))


def media_has_excluded_genre(media: CachedMedia | None, user: User) -> bool:
    """True when cached genres include a hide-genre. Unknown/empty genres do not hide."""
    excluded = {g.casefold() for g in get_user_excluded_genres(user)}
    if not excluded or media is None:
        return False
    return any(g.casefold() in excluded for g in media_genres(media))


def get_hidden_list_ids(user: User) -> list[str]:
    """Return Trakt personal list ids the user hid from the Set lists menu."""
    prefs = user.preferences
    if not prefs:
        return []
    return _parse_json_list(getattr(prefs, 'hidden_list_ids_json', None))


WATCHLIST_LIST_ID = 'watchlist'


def get_default_selected_list_ids(user: User) -> list[str]:
    """
    Return list ids for Apply my defaults / My list filters.

    Includes ``watchlist`` and/or personal list ids. Missing/unset prefs default
    to Wishlist only; an explicit empty JSON list means nothing is pre-checked.
    """
    prefs = user.preferences
    if not prefs:
        return [WATCHLIST_LIST_ID]
    raw = getattr(prefs, 'default_selected_list_ids_json', None)
    if raw is None or str(raw).strip() == '':
        return [WATCHLIST_LIST_ID]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return [WATCHLIST_LIST_ID]
    if not isinstance(data, list):
        return [WATCHLIST_LIST_ID]
    out: list[str] = []
    seen: set[str] = set()
    for item in data:
        lid = str(item or '').strip()
        if not lid or lid in seen:
            continue
        seen.add(lid)
        out.append(lid)
    return out


def get_alert_enabled_list_ids(user: User) -> list[str]:
    """
    Return list ids that should generate in-app media alerts.

    Missing/unset prefs default to Wishlist only so park/archive lists stay
    quiet. An explicit empty JSON list means no list-based alerts.
    """
    prefs = user.preferences
    if not prefs:
        return [WATCHLIST_LIST_ID]
    raw = getattr(prefs, 'alert_enabled_list_ids_json', None)
    if raw is None or str(raw).strip() == '':
        return [WATCHLIST_LIST_ID]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return [WATCHLIST_LIST_ID]
    if not isinstance(data, list):
        return [WATCHLIST_LIST_ID]
    out: list[str] = []
    seen: set[str] = set()
    for item in data:
        lid = str(item or '').strip()
        if not lid or lid in seen:
            continue
        seen.add(lid)
        out.append(lid)
    return out


def filter_visible_list_ids(user: User, list_ids: Iterable[str]) -> list[str]:
    """Keep Wishlist + personal ids that are not hidden in Preferences."""
    hidden = set(get_hidden_list_ids(user))
    out: list[str] = []
    seen: set[str] = set()
    for raw in list_ids:
        lid = str(raw or '').strip()
        if not lid or lid in seen:
            continue
        if lid != WATCHLIST_LIST_ID and lid in hidden:
            continue
        seen.add(lid)
        out.append(lid)
    return out


def user_has_match_prefs(user: User) -> bool:
    """True when the user has at least one genre or keyword for purple matching."""
    genres, keywords = get_user_genres_keywords(user)
    return bool(genres or keywords)


def user_needs_prefs_reminder(user: User) -> bool:
    """
    True when Latest match filtering will be empty/useless and we should nudge.

    Skipped when the user permanently disabled reminders or is within a snooze window.
    """
    if user_has_match_prefs(user):
        return False
    prefs = user.preferences
    if not prefs:
        return True
    if prefs.prefs_reminder_disabled:
        return False
    snooze = prefs.prefs_reminder_snooze_until
    if snooze and snooze > datetime.utcnow():
        return False
    return True


def discovery_year_cutoff(today: date | None = None) -> int:
    """
    Minimum production year kept by Latest's default “recent years” filter.

    Trakt /updates cannot tell first inserts from metadata edits on old titles.
    Year is the best cheap noise filter:
    - Jan–Jun: include last year + this year (awards / late DB adds)
    - Jul–Dec: this year only
    """
    today = today or date.today()
    if today.month <= 6:
        return today.year - 1
    return today.year


def media_year_for_discovery(media: CachedMedia) -> int | None:
    """Best available year for discovery filtering (Trakt year, else release year)."""
    if media.year:
        try:
            return int(media.year)
        except (TypeError, ValueError):
            pass
    if media.released_at:
        return int(media.released_at.year)
    return None


def media_passes_discovery_year(media: CachedMedia, min_year: int | None) -> bool:
    """
    True when media should appear under the recent-years filter.

    Missing year is kept (unknown / not yet filled) so we do not hide stubs.
    """
    if min_year is None:
        return True
    year = media_year_for_discovery(media)
    if year is None:
        return True
    return year >= int(min_year)


def user_service_names(user: User) -> set[str]:
    """Lowercased display names of streaming services the user uses."""
    names: set[str] = set()
    for row in user.streaming_services:
        names.add(row.display_name.lower())
    return names


def user_service_display_names(user: User) -> list[str]:
    """Ordered display names of streaming services the user marked as owned."""
    names: list[str] = []
    seen: set[str] = set()
    for row in user.streaming_services:
        name = (row.display_name or '').strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def normalize_service_name(name: str | None) -> str:
    """
    Normalize streaming names for matching.

    TMDB often spells brands with words (``Disney Plus``) while our catalog uses
    ``Disney+`` / ``Apple TV+`` / ``Paramount+``.
    """
    x = (name or '').strip().lower()
    if not x:
        return ''
    x = x.replace('+', ' plus ')
    x = re.sub(r'[^a-z0-9]+', ' ', x)
    return ' '.join(x.split())


def names_match(a: str | None, b: str | None) -> bool:
    """Loose name equality (same heuristic as static/js/app.js namesMatch)."""
    x = normalize_service_name(a)
    y = normalize_service_name(b)
    if not x or not y:
        return False
    return x == y or x in y or y in x


def genre_to_trakt_slug(genre: str) -> str:
    """Convert a preference genre label to a Trakt genre filter slug."""
    raw = (genre or '').strip().lower()
    if not raw:
        return ''
    # Trakt uses hyphens: science-fiction, not "science fiction".
    return re.sub(r'[\s_]+', '-', raw)


def split_providers_for_user(
    providers: list[str],
    user: User,
) -> tuple[list[str], list[str]]:
    """
    Split TMDB provider names into (on_my_services, other).

    Matching is fuzzy (substring either way) so “Prime Video” ↔ “Amazon Prime Video”.
    """
    mine_names = user_service_display_names(user)
    if not providers:
        return [], []
    if not mine_names:
        return [], list(providers)

    on_mine: list[str] = []
    other: list[str] = []
    seen_mine: set[str] = set()
    for provider in providers:
        matched = next((s for s in mine_names if names_match(provider, s)), None)
        if matched:
            key = matched.lower()
            if key not in seen_mine:
                # Prefer the user's Preference label for clarity.
                on_mine.append(matched)
                seen_mine.add(key)
        else:
            other.append(provider)
    return on_mine, other


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
