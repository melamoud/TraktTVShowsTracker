"""
Shared year / genre filters for Search and in-list pages.

Trakt /search is title-only; these filters apply locally after fetch (or on
an already-loaded My / Latest / Rec set). Future filters can live here too.
"""

from __future__ import annotations

import re
from typing import Any

from flask import request

from services.countries import country_choices_payload, normalize_country_code
from services.seed import COMMON_GENRES
from services.streaming_matcher import genre_to_trakt_slug, media_genres, media_year_for_discovery
from services import view_prefs

YEAR_MIN = 1800
YEAR_MAX = 2100
_YEAR_RANGE_RE = re.compile(
    r'^\s*(\d{4})\s*[-–—]\s*(\d{4})\s*$'
)
_YEAR_ONE_RE = re.compile(r'^\s*(\d{4})\s*$')


def parse_year_filter(raw: str | None) -> tuple[int, int] | None:
    """Parse ``2018`` or ``2015-2020`` (en/em dash ok). Invalid → None."""
    text = (raw or '').strip()
    if not text:
        return None
    m = _YEAR_RANGE_RE.match(text)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if not (_valid_year(a) and _valid_year(b)):
            return None
        return (a, b) if a <= b else (b, a)
    m = _YEAR_ONE_RE.match(text)
    if m:
        y = int(m.group(1))
        if not _valid_year(y):
            return None
        return (y, y)
    return None


def _valid_year(year: int) -> bool:
    return YEAR_MIN <= year <= YEAR_MAX


def normalize_genre_label(raw: str | None) -> str | None:
    """Map a slug or label to a COMMON_GENRES label, or None if unknown."""
    slug = genre_to_trakt_slug(raw or '')
    if not slug:
        return None
    for label in COMMON_GENRES:
        if genre_to_trakt_slug(label) == slug:
            return label
    return None


def parse_genre_filters(args=None) -> list[str]:
    """Collect unique COMMON_GENRES from ``genre=`` repeats and ``genres=a,b``."""
    src = args if args is not None else request.args
    raw: list[str] = []
    if hasattr(src, 'getlist'):
        raw.extend(src.getlist('genre') or [])
        extra = src.get('genres')
        if extra:
            raw.extend(str(extra).split(','))
    elif isinstance(src, dict):
        g = src.get('genre')
        if isinstance(g, (list, tuple)):
            raw.extend(g)
        elif g:
            raw.append(str(g))
        extra = src.get('genres')
        if extra:
            raw.extend(str(extra).split(','))
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        label = normalize_genre_label(item)
        if not label or label in seen:
            continue
        seen.add(label)
        out.append(label)
    return out


def media_matches_year(media, year_range: tuple[int, int] | None) -> bool:
    """True when media year is in range. Unknown year is kept (same as Latest)."""
    if not year_range:
        return True
    if media is None:
        return False
    year = media_year_for_discovery(media)
    if year is None:
        return True
    ymin, ymax = year_range
    return ymin <= year <= ymax


def media_matches_genres(media, genres: list[str] | set[str] | None) -> bool:
    """True when media has any selected genre (OR). Empty selection = no filter."""
    if not genres:
        return True
    if media is None:
        return False
    wanted = {genre_to_trakt_slug(g) for g in genres if genre_to_trakt_slug(g)}
    if not wanted:
        return True
    have = {genre_to_trakt_slug(g) for g in media_genres(media)}
    return bool(wanted & have)


def parse_country_filters(args=None) -> list[str]:
    """Collect unique country codes from ``country=`` repeats and ``countries=a,b``."""
    src = args if args is not None else request.args
    raw: list[str] = []
    if hasattr(src, 'getlist'):
        raw.extend(src.getlist('country') or [])
        extra = src.get('countries')
        if extra:
            raw.extend(str(extra).split(','))
    elif isinstance(src, dict):
        g = src.get('country')
        if isinstance(g, (list, tuple)):
            raw.extend(g)
        elif g:
            raw.append(str(g))
        extra = src.get('countries')
        if extra:
            raw.extend(str(extra).split(','))
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        code = normalize_country_code(item)
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


def media_matches_countries(media, countries: list[str] | set[str] | None) -> bool:
    """True when the title's country is one of the selected codes (OR).

    Empty selection = no filter. A title with no country does not match a
    selection, same as a title with none of the selected genres.
    """
    if not countries:
        return True
    if media is None:
        return False
    code = normalize_country_code(getattr(media, 'country', None))
    if not code:
        return False
    wanted = {normalize_country_code(c) for c in countries}
    wanted.discard(None)
    return code in wanted


def row_passes_advanced(
    row: dict,
    year_range: tuple[int, int] | None,
    genres: list[str] | set[str] | None,
    countries: list[str] | set[str] | None = None,
) -> bool:
    media = row.get('media') if isinstance(row, dict) else row
    return (
        media_matches_year(media, year_range)
        and media_matches_genres(media, genres)
        and media_matches_countries(media, countries)
    )


def resolve_advanced(user, view: str) -> tuple[str, list[str], list[str]]:
    """
    Resolve year string, genre labels, and country codes.

    ``year`` present (even empty) updates saved year.
    ``genre`` present or ``genres_set=1`` updates saved genres (empty = clear).
    ``country`` present or ``countries_set=1`` updates saved countries (empty = clear).
    """
    if 'year' in request.args:
        raw = (request.args.get('year') or '').strip()
        year = raw if parse_year_filter(raw) else ''
        view_prefs.update_view(user, view, year=year)
    else:
        stored = view_prefs.get_view(user, view).get('year')
        year = stored if isinstance(stored, str) else ''
        if year and not parse_year_filter(year):
            year = ''

    if 'genre' in request.args or request.args.get('genres_set') == '1':
        genres = parse_genre_filters(request.args)
        view_prefs.update_view(user, view, genres=genres)
    else:
        stored_g = view_prefs.get_view(user, view).get('genres')
        if isinstance(stored_g, list):
            genres = [g for g in (normalize_genre_label(x) for x in stored_g) if g]
        else:
            genres = []

    if 'country' in request.args or request.args.get('countries_set') == '1':
        countries = parse_country_filters(request.args)
        view_prefs.update_view(user, view, countries=countries)
    else:
        stored_c = view_prefs.get_view(user, view).get('countries')
        if isinstance(stored_c, list):
            countries = [
                c for c in (normalize_country_code(x) for x in stored_c) if c
            ]
        else:
            countries = []
    return year, genres, countries


def advanced_context(year: str, genres: list[str], countries: list[str] | None = None) -> dict[str, Any]:
    """Template/JSON extras for year, genre, and country filters."""
    selected = list(countries or [])
    return {
        'year': year or '',
        'filter_genres': list(genres),
        'genre_choices': list(COMMON_GENRES),
        'filter_countries': selected,
        'country_choices': country_choices_payload(),
        'year_range': parse_year_filter(year),
        'has_advanced': bool(parse_year_filter(year) or genres or selected),
    }
