"""
Primary country for a movie or show, from Trakt's ``country`` field.

Trakt stores one ISO 3166-1 alpha-2 code (plus a few legacy codes such as
``su``). That is the title's main country, not every co-producer.
"""

from __future__ import annotations

import json
import re

# code, English name. Checkbox order is by name.
COUNTRY_CHOICES: list[tuple[str, str]] = [
    ('ar', 'Argentina'),
    ('au', 'Australia'),
    ('be', 'Belgium'),
    ('br', 'Brazil'),
    ('ca', 'Canada'),
    ('cn', 'China'),
    ('dk', 'Denmark'),
    ('eg', 'Egypt'),
    ('fi', 'Finland'),
    ('fr', 'France'),
    ('de', 'Germany'),
    ('gr', 'Greece'),
    ('hk', 'Hong Kong'),
    ('in', 'India'),
    ('id', 'Indonesia'),
    ('ie', 'Ireland'),
    ('il', 'Israel'),
    ('it', 'Italy'),
    ('jp', 'Japan'),
    ('mx', 'Mexico'),
    ('nl', 'Netherlands'),
    ('nz', 'New Zealand'),
    ('ng', 'Nigeria'),
    ('no', 'Norway'),
    ('pk', 'Pakistan'),
    ('ph', 'Philippines'),
    ('pl', 'Poland'),
    ('pt', 'Portugal'),
    ('ru', 'Russia'),
    ('za', 'South Africa'),
    ('kr', 'South Korea'),
    ('su', 'Soviet Union'),
    ('es', 'Spain'),
    ('se', 'Sweden'),
    ('tw', 'Taiwan'),
    ('th', 'Thailand'),
    ('tr', 'Turkey'),
    ('gb', 'United Kingdom'),
    ('us', 'United States'),
]

_NAMES = {code: name for code, name in COUNTRY_CHOICES}
_CODE_RE = re.compile(r'^[a-z]{2}$')


def normalize_country_code(raw: str | None) -> str | None:
    """Return a lowercase 2-letter code, or None."""
    code = (raw or '').strip().lower()
    if not _CODE_RE.match(code):
        return None
    return code


def country_label(code: str | None) -> str:
    """English name for a code. Unknown codes stay as uppercase letters."""
    norm = normalize_country_code(code)
    if not norm:
        return ''
    return _NAMES.get(norm) or norm.upper()


def country_choices_payload() -> list[dict[str, str]]:
    """``[{code, name}, ...]`` for templates and the Android API."""
    return [{'code': code, 'name': name} for code, name in COUNTRY_CHOICES]


def country_from_payload(item: dict | None, media_type: str | None = None) -> str | None:
    """Read ``country`` from a Trakt summary or a wrapped calendar/search row."""
    if not isinstance(item, dict):
        return None
    entity = item
    if media_type and isinstance(item.get(media_type), dict):
        entity = item[media_type]
    code = normalize_country_code(entity.get('country') if isinstance(entity, dict) else None)
    if code:
        return code
    if entity is not item:
        return normalize_country_code(item.get('country'))
    return None


def country_from_raw_json(raw_json: str | None, media_type: str | None = None) -> str | None:
    """Read a stored Trakt payload without calling Trakt again."""
    if not raw_json:
        return None
    try:
        raw = json.loads(raw_json)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    return country_from_payload(raw, media_type)
