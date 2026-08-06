"""
Release / streaming availability signals for media cards and list filters.

- Theater window: public release within ±30 days of today
- Upcoming: public release more than 30 days after today
- Streaming: TMDB lists at least one flatrate/ads/free provider
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

THEATER_DAYS = 30
AVAIL_CHOICES = ('upcoming', 'theater', 'streaming')


def normalize_avail(raw: str | None) -> str:
    """Return a valid avail filter key or empty string."""
    val = (raw or '').strip().lower()
    return val if val in AVAIL_CHOICES else ''


def _release_date(media) -> date | None:
    if not media:
        return None
    released = getattr(media, 'released_at', None)
    return released if isinstance(released, date) else None


def availability_flags(
    media,
    providers: list | None = None,
    *,
    my_providers: list | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """
    Compute availability flags for one title.

    ``providers`` should be subscription/free names already filtered
    (flatrate/ads/free). When omitted, reads ``media.providers``.
    """
    today = today or date.today()
    released = _release_date(media)
    upcoming = False
    theater = False
    if released is not None:
        delta = (released - today).days
        if delta > THEATER_DAYS:
            upcoming = True
        elif -THEATER_DAYS <= delta <= THEATER_DAYS:
            theater = True

    if providers is None and media is not None:
        providers = [
            p.provider_name for p in (media.providers or [])
            if getattr(p, 'offer_type', None) in ('flatrate', 'ads', 'free')
        ]
    providers = providers or []
    my_providers = my_providers or []
    streaming = bool(providers)
    on_my_services = bool(my_providers)

    return {
        'upcoming': upcoming,
        'theater': theater,
        'streaming': streaming,
        'on_my_services': on_my_services,
        'released_at': released,
    }


def _fmt_release(d: date | None) -> str:
    if not d:
        return ''
    return d.strftime('%b %d').replace(' 0', ' ')


def availability_chips(flags: dict[str, Any]) -> list[dict[str, str]]:
    """UI chips to render under the poster (0–3 items)."""
    chips: list[dict[str, str]] = []
    released = flags.get('released_at')
    date_label = _fmt_release(released)
    if flags.get('upcoming'):
        label = f'Upcoming · {date_label}' if date_label else 'Upcoming'
        chips.append({'kind': 'upcoming', 'label': label})
    if flags.get('theater'):
        label = f'Theater · {date_label}' if date_label else 'Theater window'
        chips.append({'kind': 'theater', 'label': label})
    if flags.get('streaming'):
        label = 'On your services' if flags.get('on_my_services') else 'Streaming'
        chips.append({'kind': 'streaming', 'label': label})
    return chips


def attach_availability(row: dict) -> dict:
    """Add ``avail`` flags and ``avail_chips`` onto a decorated/media row."""
    media = row.get('media')
    flags = availability_flags(
        media,
        providers=row.get('providers'),
        my_providers=row.get('my_providers'),
    )
    row['avail'] = flags
    row['avail_chips'] = availability_chips(flags)
    return row


def row_matches_avail(row: dict, avail: str) -> bool:
    """True when row matches the selected avail filter (or filter is off)."""
    avail = normalize_avail(avail)
    if not avail:
        return True
    flags = row.get('avail')
    if not flags:
        attach_availability(row)
        flags = row['avail']
    return bool(flags.get(avail))


def filter_rows_by_avail(rows: list[dict], avail: str) -> list[dict]:
    """Filter decorated rows by avail= upcoming|theater|streaming."""
    avail = normalize_avail(avail)
    if not avail:
        return rows
    out = []
    for row in rows:
        attach_availability(row)
        if row_matches_avail(row, avail):
            out.append(row)
    return out


def theater_window_bounds(today: date | None = None) -> tuple[date, date]:
    """Inclusive start/end dates for the theater window."""
    today = today or date.today()
    return today - timedelta(days=THEATER_DAYS), today + timedelta(days=THEATER_DAYS)


def upcoming_after(today: date | None = None) -> date:
    """First date that counts as Upcoming (exclusive theater upper bound + 1)."""
    today = today or date.today()
    return today + timedelta(days=THEATER_DAYS + 1)
