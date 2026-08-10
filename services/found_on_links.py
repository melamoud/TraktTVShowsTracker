"""Build open-in-new-tab URLs for streaming / Found-on service chips."""

from __future__ import annotations

from urllib.parse import quote, quote_plus, urlparse

from sqlalchemy.orm import joinedload

from models import StreamingService, User, UserStreamingService

# Title search pages for known catalog services (homepage alone is weak for queueing).
# Keys are normalize_service_name() forms (Disney+ → disney plus).
_SEARCH_TEMPLATES = {
    'netflix': 'https://www.netflix.com/search?q={q}',
    'prime video': 'https://www.primevideo.com/search/ref=atv_nb_sr?phrase={q}',
    'disney plus': 'https://www.disneyplus.com/search?q={q}',
    'hulu': 'https://www.hulu.com/search?q={q}',
    'max': 'https://www.max.com/search?q={q}',
    'apple tv plus': 'https://tv.apple.com/search?term={q}',
    'paramount plus': 'https://www.paramountplus.com/search/?q={q}',
    'peacock': 'https://www.peacocktv.com/search?q={q}',
    'youtube': 'https://www.youtube.com/results?search_query={q}',
}


def _norm(name: str | None) -> str:
    """Lowercased key; treat Disney+ and Disney Plus as the same."""
    from services.streaming_matcher import normalize_service_name
    return normalize_service_name(name)


def _title_query(title: str | None, year: int | None) -> str:
    bits = []
    t = (title or '').strip()
    if t:
        bits.append(t)
        if year:
            bits.append(str(int(year)))
    return ' '.join(bits)


def apply_search_template(template: str, title_text: str) -> str | None:
    """
    Fill a user/catalog search template.

    Placeholders (URL-encoded title text, including optional year):
      <title>  preferred (e.g. https://toflx.com/search?q=<title>)
      {title}  same
      {q}      same (quote_plus style for built-ins)
    """
    tmpl = (template or '').strip()
    text = (title_text or '').strip()
    if not tmpl or not text:
        return None
    enc_pct = quote(text, safe='')  # The%20Devil%27s%20Mouth%202026
    enc_plus = quote_plus(text)     # The+Devil%27s+Mouth+2026
    out = tmpl.replace('<title>', enc_pct).replace('{title}', enc_pct).replace('{q}', enc_plus)
    if out == tmpl:
        # No placeholder — not a usable search URL by itself.
        return None
    return out


def service_link_maps(user: User | None = None) -> tuple[dict[str, str], dict[str, str]]:
    """
    Return (base_urls, search_templates) keyed by lowercased service name.

    User custom services override catalog entries with the same name.
    """
    base: dict[str, str] = {}
    search: dict[str, str] = dict(_SEARCH_TEMPLATES)
    for svc in StreamingService.query.order_by(StreamingService.name).all():
        key = _norm(svc.name)
        url = (svc.url or '').strip()
        if key and url:
            base[key] = url
    if user is not None and getattr(user, 'is_authenticated', False):
        owned = (
            UserStreamingService.query
            .options(joinedload(UserStreamingService.service))
            .filter_by(user_id=user.id)
            .all()
        )
        for row in owned:
            name = _norm(row.display_name)
            if not name:
                continue
            if row.is_custom:
                url = (row.custom_url or '').strip()
                tmpl = (row.custom_search_template or '').strip()
                if tmpl:
                    search[name] = tmpl
            else:
                url = ((row.service.url if row.service else None) or '').strip()
            if url:
                base[name] = url
    return base, search


def service_base_url_map(user: User | None = None) -> dict[str, str]:
    """Case-insensitive service name → homepage URL (compat wrapper)."""
    base, _ = service_link_maps(user)
    return base


def found_on_open_url(
    service_label: str,
    *,
    title: str | None = None,
    year: int | None = None,
    base_urls: dict[str, str] | None = None,
    search_templates: dict[str, str] | None = None,
) -> str | None:
    """
    URL to open for a service chip (Found on / Plays on your services).

    Prefer a search template with the title; else homepage; else generic web search.
    """
    label = (service_label or '').strip()
    if not label:
        return None
    key = _norm(label)
    if key in ('cable dvr', 'other', 'cable', 'dvr'):
        return None

    title_text = _title_query(title, year)
    templates = search_templates if search_templates is not None else dict(_SEARCH_TEMPLATES)
    if base_urls is None and search_templates is None:
        base_urls, templates = service_link_maps()

    tmpl = templates.get(key) if templates else None
    if tmpl and title_text:
        # Built-in templates use {q}; user templates use <title>.
        filled = apply_search_template(tmpl, title_text)
        if filled:
            return filled
        # Built-ins stored as https://...?q={q}
        if '{q}' in tmpl:
            return tmpl.format(q=quote_plus(title_text))

    base = None
    if base_urls is not None:
        base = base_urls.get(key)
    if not base:
        base = service_base_url_map().get(key)

    if base and title_text:
        host = urlparse(base).hostname or ''
        if host:
            return (
                'https://www.google.com/search?q='
                + quote_plus(f'site:{host} {title_text}')
            )
    if base:
        return base

    if title_text:
        return 'https://www.google.com/search?q=' + quote_plus(f'{label} {title_text}')
    return None
