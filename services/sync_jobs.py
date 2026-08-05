"""
Background sync jobs: catalog refresh, user state, streaming availability alerts.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta

from flask import Flask
from sqlalchemy.exc import IntegrityError

from models import (
    CachedMedia,
    CatalogFeedSync,
    MediaProviderAvailability,
    ReviewMarker,
    User,
    UserListMembership,
    UserMediaState,
    db,
)
from services import trakt_client
from services.streaming_matcher import get_hidden_list_ids
from services.tmdb_client import get_watch_providers, is_configured as tmdb_configured

logger = logging.getLogger('app')


def _parse_trakt_dt(value: str | None) -> datetime | None:
    """Parse a Trakt ISO timestamp."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).replace(tzinfo=None)
    except ValueError:
        return None


def _normalize_media_url(url: str | None) -> str | None:
    """Ensure Trakt media CDN paths become absolute https URLs."""
    if not url:
        return None
    url = str(url).strip()
    if url.startswith('http://') or url.startswith('https://'):
        return url
    if url.startswith('//'):
        return 'https:' + url
    return 'https://' + url.lstrip('/')


def _extract_poster_url(entity: dict | None) -> str | None:
    """Pull a poster URL from Trakt images payload shapes."""
    if not entity:
        return None
    images = entity.get('images') or {}
    posters = images.get('poster') or images.get('posters') or images.get('thumb') or []
    if isinstance(posters, list) and posters:
        first = posters[0]
        if isinstance(first, dict):
            return _normalize_media_url(
                first.get('url') or first.get('thumb') or first.get('full')
            )
        if isinstance(first, str):
            return _normalize_media_url(first)
    return _normalize_media_url(entity.get('poster_url'))


def _ensure_local_poster(media: CachedMedia, remote_url: str | None = None) -> None:
    """
    Store poster as a locally cached URL.

    Trakt blocks browser hotlinking of media.trakt.tv — we must download.
    """
    from services.poster_cache import (
        cache_remote_poster,
        is_local_poster_url,
        local_poster_path,
        local_poster_url,
    )

    if is_local_poster_url(media.poster_url) and local_poster_path(media.media_type, media.trakt_id):
        return

    remote = remote_url or media.poster_url
    if is_local_poster_url(remote):
        remote = None
    if remote:
        remote = _normalize_media_url(remote)

    if remote:
        local = cache_remote_poster(media.media_type, media.trakt_id, remote)
        if local:
            media.poster_url = local
            db.session.commit()
            return

    # Already downloaded earlier but DB still has CDN URL.
    if local_poster_path(media.media_type, media.trakt_id):
        media.poster_url = local_poster_url(media.media_type, media.trakt_id)
        db.session.commit()


def enrich_media_details_for_display(media: CachedMedia) -> bool:
    """
    Ensure overview/genres/poster exist (Trakt summary + local poster cache).

    Returns False when Trakt rate-limits (429) so callers can stop early.
    """
    from services.poster_cache import is_local_poster_url

    needs_summary = (
        not media.overview
        or media.genres_json in (None, '', '[]')
        or not media.poster_url
        or not is_local_poster_url(media.poster_url)
        or not media.runtime
    )
    if needs_summary:
        try:
            summary = trakt_client.fetch_media_summary(media.media_type, media.trakt_id)
            if summary:
                upsert_cached_media(
                    media.media_type,
                    summary,
                    listed_at=media.trakt_listed_at,
                    feed_source=media.feed_source,
                )
                db.session.commit()
                db.session.refresh(media)
                remote_poster = _extract_poster_url(summary)
                _ensure_local_poster(media, remote_poster)
        except Exception as exc:
            logger.warning('Detail enrich Trakt failed for %s: %s', media.trakt_id, exc)
            if getattr(exc, 'status_code', None) == 429 or '429' in str(exc):
                return False

    if media.poster_url and not is_local_poster_url(media.poster_url):
        _ensure_local_poster(media, media.poster_url)

    if not media.poster_url and media.tmdb_id:
        try:
            from services.tmdb_client import get_poster_for_tmdb_id, is_configured
            if is_configured():
                url = get_poster_for_tmdb_id(media.media_type, media.tmdb_id)
                if url:
                    _ensure_local_poster(media, url)
        except Exception as exc:
            logger.warning('Detail enrich TMDB poster failed for %s: %s', media.trakt_id, exc)
    return True


def enrich_media_list_for_display(
    items: list[CachedMedia],
    max_fetches: int = 25,
) -> list[CachedMedia]:
    """
    Fill overview/genres/poster for a visible catalog page.

    Trakt /updates only returns stubs; without this the Latest list has
    titles and dates but no description or artwork.
    """
    from services.poster_cache import is_local_poster_url

    fetches = 0
    for media in items:
        needs = (
            not media.overview
            or media.genres_json in (None, '', '[]')
            or not media.poster_url
            or not is_local_poster_url(media.poster_url)
        )
        if needs and fetches >= max_fetches:
            # Best-effort: migrate CDN URL already on the row into local cache.
            if media.poster_url and not is_local_poster_url(media.poster_url):
                try:
                    _ensure_local_poster(media, media.poster_url)
                except Exception:
                    pass
            continue
        if needs:
            fetches += 1
        ok = enrich_media_details_for_display(media)
        if not ok:
            logger.warning('Stopping list enrich early (Trakt rate limit)')
            break
    return items


def upsert_cached_media(
    media_type: str,
    item: dict,
    listed_at: datetime | None = None,
    feed_source: str | None = None,
    release_date: date | None = None,
) -> CachedMedia | None:
    """Insert or update a CachedMedia row from a Trakt calendar/summary payload."""
    entity = item.get(media_type) or item
    ids = entity.get('ids') or {}
    trakt_id = ids.get('trakt')
    if not trakt_id:
        return None

    row = CachedMedia.query.filter_by(media_type=media_type, trakt_id=trakt_id).first()
    if not row:
        row = CachedMedia(media_type=media_type, trakt_id=trakt_id, title=entity.get('title') or 'Untitled')
        db.session.add(row)

    row.slug = ids.get('slug') or row.slug
    row.title = entity.get('title') or row.title
    row.year = entity.get('year') or row.year
    row.overview = entity.get('overview') or row.overview
    row.runtime = entity.get('runtime') or row.runtime
    row.network = entity.get('network') or row.network
    if entity.get('genres') is not None:
        row.genres_json = json.dumps(entity.get('genres') or [])
    row.imdb_id = ids.get('imdb') or row.imdb_id
    row.tmdb_id = ids.get('tmdb') or row.tmdb_id
    row.tvdb_id = ids.get('tvdb') or row.tvdb_id
    row.trailer_url = entity.get('trailer') or row.trailer_url
    row.homepage = entity.get('homepage') or row.homepage

    poster = _extract_poster_url(entity) or _extract_poster_url(item)
    if poster:
        # Keep CDN URL temporarily; enrich step downloads into local cache.
        # Do not overwrite an already-local cached poster with a CDN link.
        from services.poster_cache import is_local_poster_url
        if not is_local_poster_url(row.poster_url):
            row.poster_url = poster

    released = release_date
    if not released:
        raw_released = (
            item.get('released')
            or entity.get('released')
            or item.get('first_aired')
            or entity.get('first_aired')
        )
        if raw_released:
            try:
                released = date.fromisoformat(str(raw_released)[:10])
            except ValueError:
                released = None
    if released:
        row.released_at = released

    candidate_listed = listed_at
    if not candidate_listed and released:
        candidate_listed = datetime.combine(released, datetime.min.time())
    if not candidate_listed:
        candidate_listed = _parse_trakt_dt(item.get('updated_at')) or _parse_trakt_dt(
            entity.get('updated_at')
        )
    if candidate_listed and (
        not row.trakt_listed_at or candidate_listed > row.trakt_listed_at
    ):
        row.trakt_listed_at = candidate_listed

    if not row.trakt_listed_at:
        row.trakt_listed_at = datetime.utcnow()

    if feed_source:
        row.feed_source = feed_source

    row.raw_json = json.dumps(item)[:20000]
    row.updated_at = datetime.utcnow()
    return row


# Trakt /updates rejects dates older than ~30 days; stay inside with margin.
UPDATES_WINDOW_DAYS = 28
# One newest page only — older pages load when the user pages back.
INITIAL_BOOTSTRAP_PAGES = 1
NEWEST_REFRESH_MIN_INTERVAL = timedelta(minutes=15)


def _updates_start_date(days_back: int = UPDATES_WINDOW_DAYS) -> str:
    """ISO date for Trakt /updates window (clamped to a safe ~28-day max)."""
    days_back = max(1, min(int(days_back), UPDATES_WINDOW_DAYS))
    return (date.today() - timedelta(days=days_back)).isoformat()


def _item_trakt_id(item: dict, media_type: str) -> int | None:
    """Extract trakt id from an /updates list entry."""
    entity = item.get(media_type) or item
    tid = (entity.get('ids') or {}).get('trakt')
    return int(tid) if tid else None


def _upsert_update_items(media_type: str, items: list) -> int:
    """Upsert /updates payload rows into CachedMedia; return count touched."""
    count = 0
    for item in items or []:
        listed_at = _parse_trakt_dt(item.get('updated_at'))
        row = upsert_cached_media(
            media_type,
            item,
            listed_at=listed_at,
            feed_source='trakt_db_updates',
        )
        if row:
            count += 1
    return count


def _get_feed_sync(media_type: str) -> CatalogFeedSync | None:
    """Return catalog feed sync cursor for media type."""
    return db.session.get(CatalogFeedSync, media_type)


def _save_feed_sync(
    media_type: str,
    start_date: str,
    page_count: int,
    oldest_fetched_page: int | None,
    newest_fetched_page: int | None,
    *,
    bootstrapped: bool = False,
) -> CatalogFeedSync:
    """Create or update the lazy-sync cursor."""
    row = _get_feed_sync(media_type)
    if not row:
        row = CatalogFeedSync(media_type=media_type, start_date=start_date)
        db.session.add(row)
    row.start_date = start_date
    row.page_count = page_count
    row.oldest_fetched_page = oldest_fetched_page
    row.newest_fetched_page = newest_fetched_page
    row.updated_at = datetime.utcnow()
    if bootstrapped:
        row.bootstrapped_at = datetime.utcnow()
    return row


def feed_count(media_type: str) -> int:
    """Cached Latest-feed title count."""
    return CachedMedia.query.filter_by(
        media_type=media_type, feed_source='trakt_db_updates'
    ).count()


def catalog_has_more_older(media_type: str) -> bool:
    """True if older Trakt /updates pages remain unfetched in the current window."""
    row = _get_feed_sync(media_type)
    if not row or row.oldest_fetched_page is None:
        return False
    return int(row.oldest_fetched_page) > 1


def _should_refresh_newest(media_type: str) -> bool:
    """Throttle newest-page refreshes so Latest clicks do not hammer Trakt."""
    row = _get_feed_sync(media_type)
    if not row or not row.updated_at:
        return True
    return (datetime.utcnow() - row.updated_at) >= NEWEST_REFRESH_MIN_INTERVAL


def reconcile_feed_cursor(media_type: str, days_back: int = UPDATES_WINDOW_DAYS) -> CatalogFeedSync | None:
    """
    Fix cursors that incorrectly claim the full window was fetched.

    A bad migration set oldest_fetched_page=1 / page_count=1 while local cache
    only held today's newest updates — blocking lazy older loads forever.
    """
    start = _updates_start_date(days_back)
    cursor = _get_feed_sync(media_type)
    # Fast path: cursor already looks like an in-progress / valid lazy window.
    if (
        cursor
        and cursor.bootstrapped_at
        and cursor.start_date == start
        and int(cursor.page_count or 0) > 10
        and int(cursor.oldest_fetched_page or 0) > 1
    ):
        return cursor

    try:
        meta = trakt_client.probe_updates_pagination(media_type, start)
    except Exception as exc:
        logger.warning('Feed cursor probe failed for %s: %s', media_type, exc)
        return cursor

    real_pages = max(1, int(meta['page_count']))
    if not cursor:
        row = _save_feed_sync(
            media_type,
            start,
            real_pages,
            oldest_fetched_page=real_pages,
            newest_fetched_page=real_pages,
            bootstrapped=True,
        )
        db.session.commit()
        return row

    broken = (
        cursor.start_date != start
        or int(cursor.page_count or 0) < max(2, min(real_pages, 50))
        or (
            int(cursor.oldest_fetched_page or 0) <= 1
            and real_pages > 1
        )
    )
    if not broken and int(cursor.page_count or 0) >= real_pages:
        return cursor

    newest = real_pages
    if cursor.newest_fetched_page and cursor.start_date == start:
        newest = max(int(cursor.newest_fetched_page), real_pages)
    if cursor.oldest_fetched_page and cursor.start_date == start and int(cursor.oldest_fetched_page) > 1:
        oldest = min(int(cursor.oldest_fetched_page), real_pages)
    else:
        # Re-open lazy older walk from the newest edge (do not pretend page 1 is done).
        oldest = real_pages

    logger.info(
        'Reconciling %s feed cursor: page_count %s->%s oldest %s->%s',
        media_type, cursor.page_count, real_pages, cursor.oldest_fetched_page, oldest,
    )
    row = _save_feed_sync(
        media_type,
        start,
        real_pages,
        oldest_fetched_page=oldest,
        newest_fetched_page=newest,
        bootstrapped=True,
    )
    db.session.commit()
    return row


def sync_catalog(
    media_type: str = 'movie',
    days_back: int = UPDATES_WINDOW_DAYS,
    days_forward: int = 0,  # unused; kept for call-site compatibility
    pages: int | None = INITIAL_BOOTSTRAP_PAGES,
    *,
    full_window: bool = False,
    enrich: bool = False,
) -> int:
    """
    Sync Latest feed from Trakt DB updates (/movies|/shows/updates).

    Default: newest INITIAL_BOOTSTRAP_PAGES only (1 page). Older pages load lazily.
    ``enrich`` is off by default — visible-page enrich handles display; bulk enrich
    was the main cause of 30s+ Refresh times.

    Uses a *light* pagination probe (limit=1, no extended), then fetches only the
    newest page(s) with extended=full — never the oldest page.
    """
    import time
    del days_forward  # API compatibility
    t0 = time.perf_counter()
    start = _updates_start_date(days_back)
    meta = trakt_client.probe_updates_pagination(media_type, start)
    page_count = meta['page_count']
    t_probe = time.perf_counter()

    if full_window and pages is None:
        pages = max(INITIAL_BOOTSTRAP_PAGES, min(page_count, 10))

    if pages is None:
        pages = INITIAL_BOOTSTRAP_PAGES

    pages = max(1, int(pages))
    from_page = max(1, page_count - pages + 1)
    # Never pass page1_cache from the light probe (limit=1 / incomplete).
    items = trakt_client.fetch_updates_pages(
        media_type,
        start,
        from_page,
        page_count,
        page1_cache=None,
        extended='full',
    )
    t_fetch = time.perf_counter()
    count = _upsert_update_items(media_type, items)
    existing = _get_feed_sync(media_type)
    oldest = from_page
    newest = page_count
    if existing and existing.start_date == start and existing.oldest_fetched_page:
        oldest = min(int(existing.oldest_fetched_page), from_page)
        newest = max(int(existing.newest_fetched_page or 0), page_count)
    _save_feed_sync(
        media_type,
        start,
        page_count,
        oldest,
        newest,
        bootstrapped=True,
    )

    db.session.commit()
    logger.info(
        'Catalog sync %s: upserted %s pages %s-%s/%s '
        '(probe=%.2fs fetch=%d page(s) %.2fs total=%.2fs)',
        media_type, count, oldest, newest, page_count,
        t_probe - t0, pages, t_fetch - t_probe, time.perf_counter() - t0,
    )
    if enrich:
        try:
            enriched = enrich_media_details(media_type, limit=min(20, max(count, 5)))
            if enriched:
                logger.info('Catalog enrich %s: filled details for %s titles', media_type, enriched)
        except Exception as exc:
            logger.warning('Catalog enrich after sync failed: %s', exc)
    return count


def refresh_catalog_newest(
    media_type: str,
    days_back: int = UPDATES_WINDOW_DAYS,
    pages: int = 1,
) -> int:
    """Re-pull the newest Trakt /updates page(s); keep older cached rows. No bulk enrich."""
    return sync_catalog(media_type, days_back=days_back, pages=pages, enrich=False)


def bootstrap_catalog_initial(
    media_type: str,
    days_back: int = UPDATES_WINDOW_DAYS,
) -> int:
    """
    First-load sync: newest page only. Older pages load lazily when paging.
    """
    return sync_catalog(
        media_type,
        days_back=days_back,
        pages=INITIAL_BOOTSTRAP_PAGES,
        enrich=False,
    )


def ensure_catalog_through_marker(
    media_type: str,
    user: User,
    days_back: int = UPDATES_WINDOW_DAYS,
) -> int:
    """
    Keep Latest cache ready without walking to the review marker.

    Review markers only dim rows already in cache. Older Trakt pages load when
    the user pages back (ensure_catalog_for_offset) — never eagerly here.
    """
    del user  # kept for call-site compatibility
    count = feed_count(media_type)
    if count == 0:
        return bootstrap_catalog_initial(media_type, days_back=days_back)

    cursor = reconcile_feed_cursor(media_type, days_back=days_back)
    if not cursor or not cursor.bootstrapped_at:
        return bootstrap_catalog_initial(media_type, days_back=days_back)

    start = _updates_start_date(days_back)
    if cursor.start_date != start:
        return refresh_catalog_newest(media_type, days_back=days_back, pages=1)

    if _should_refresh_newest(media_type):
        return refresh_catalog_newest(media_type, days_back=days_back, pages=1)
    return 0


def ensure_catalog_for_offset(
    media_type: str,
    days_back: int = UPDATES_WINDOW_DAYS,
) -> bool:
    """
    Fetch one older Trakt /updates page into cache for lazy pagination.

    Returns True if a page was fetched (caller should re-query). False if
    nothing older remains in the current window.
    """
    start = _updates_start_date(days_back)
    cursor = _get_feed_sync(media_type)
    if not cursor or cursor.oldest_fetched_page is None:
        return False
    if cursor.start_date != start:
        # Window date rolled; do not walk old cursor pages against a new start_date.
        return False

    oldest = int(cursor.oldest_fetched_page)
    if oldest <= 1:
        return False

    page = oldest - 1
    items = trakt_client.fetch_updates_pages(media_type, start, page, page)
    _upsert_update_items(media_type, items)
    _save_feed_sync(
        media_type,
        start,
        int(cursor.page_count or 1),
        page,
        int(cursor.newest_fetched_page or cursor.page_count or 1),
    )
    db.session.commit()
    logger.info('Lazy catalog older page %s for %s (%s items)', page, media_type, len(items))
    return True


def enrich_media_details(media_type: str, limit: int = 40) -> int:
    """Fetch full Trakt summaries for recently cached stubs missing overview."""
    rows = (
        CachedMedia.query
        .filter_by(media_type=media_type, feed_source='trakt_db_updates')
        .order_by(CachedMedia.trakt_listed_at.desc())
        .limit(limit)
        .all()
    )
    updated = 0
    for row in rows:
        if (
            row.overview
            and row.genres_json not in (None, '', '[]')
            and row.poster_url
        ):
            continue
        try:
            before = (row.overview, row.genres_json, row.poster_url)
            enrich_media_details_for_display(row)
            after = (row.overview, row.genres_json, row.poster_url)
            if after != before:
                updated += 1
        except Exception as exc:
            logger.warning('Enrich failed for %s %s: %s', media_type, row.trakt_id, exc)
    db.session.commit()
    return updated


def sync_user_media_state(user: User, media_types: tuple[str, ...] | None = None) -> None:
    """Refresh local watchlist/watched cache from Trakt for one user."""
    types = media_types or ('movie', 'show')
    for media_type in types:
        try:
            watchlist = trakt_client.get_watchlist(user, media_type)
            # No extended=progress here — bulk show progress is too slow for Refresh.
            watched = trakt_client.get_watched(user, media_type)
        except Exception as exc:
            logger.warning('State sync failed for user %s %s: %s', user.id, media_type, exc)
            continue

        wl_ids: set[int] = set()
        for entry in watchlist:
            entity = entry.get(media_type) or {}
            tid = (entity.get('ids') or {}).get('trakt')
            if tid:
                wl_ids.add(int(tid))
                _upsert_state(user.id, media_type, int(tid), on_watchlist=True)
                # Watchlist payloads include title/year/ids — cache for My Movies/Shows UI.
                upsert_cached_media(media_type, entry)

        watched_ids: set[int] = set()
        for entry in watched:
            entity = entry.get(media_type) or {}
            tid = (entity.get('ids') or {}).get('trakt')
            if not tid:
                continue
            tid = int(tid)
            watched_ids.add(tid)
            plays = entry.get('plays') or 0
            last_watched = _parse_trakt_dt(entry.get('last_watched_at'))
            # Do not invent show progress_percent here. Bulk /sync/watched has
            # plays only (no aired/completed) unless extended=progress, which is
            # too slow for Refresh. Real % is written from the Progress page.
            _upsert_state(
                user.id,
                media_type,
                tid,
                on_watchlist=tid in wl_ids,
                watched=plays > 0,
                plays=plays,
                last_watched_at=last_watched,
            )
            upsert_cached_media(media_type, entry)

        # Drop local flags for titles no longer on Trakt lists (full sync only).
        for row in UserMediaState.query.filter_by(
            user_id=user.id, media_type=media_type
        ).all():
            if row.trakt_id not in wl_ids:
                row.on_watchlist = False
            if row.trakt_id not in watched_ids:
                row.watched = False
            # Old sync invented progress=100 from play count. Without a real
            # Progress-page / page-enrich detail stamp, that % is untrusted and
            # hides unfinished shows from "Unwatched episodes" forever.
            if (
                media_type == 'show'
                and row.progress_detail_at is None
                and row.progress_percent is not None
            ):
                row.progress_percent = None

    try:
        sync_user_list_memberships(user, media_types=types)
    except Exception as exc:
        logger.warning('List membership sync failed for user %s: %s', user.id, exc)

    user.last_sync_at = datetime.utcnow()
    db.session.commit()


def sync_user_list_memberships(
    user: User,
    media_types: tuple[str, ...] | None = None,
) -> None:
    """
    Refresh local cache of personal-list membership for lists shown in Preferences.

    Hidden lists are skipped (and their cached rows cleared). Wishlist is handled
    separately via ``UserMediaState.on_watchlist``.
    """
    types = media_types or ('movie', 'show')
    hidden = set(get_hidden_list_ids(user))
    try:
        personal = trakt_client.get_personal_lists(user)
    except Exception as exc:
        logger.warning('Could not load personal lists for user %s: %s', user.id, exc)
        return

    shown = [lst for lst in personal if lst['id'] not in hidden]
    shown_ids = {lst['id'] for lst in shown}

    # Drop cache for lists no longer shown / deleted on Trakt.
    stale = UserListMembership.query.filter(
        UserListMembership.user_id == user.id,
        UserListMembership.list_id.notin_(shown_ids or ['__none__']),
    ).all()
    for row in stale:
        db.session.delete(row)

    for lst in shown:
        lid = lst['id']
        for media_type in types:
            try:
                items = trakt_client.get_list_items(user, lid, media_type)
            except Exception as exc:
                logger.warning(
                    'List items sync failed user=%s list=%s %s: %s',
                    user.id, lid, media_type, exc,
                )
                continue
            current_ids: set[int] = set()
            for entry in items:
                entity = entry.get(media_type) or {}
                tid = (entity.get('ids') or {}).get('trakt')
                if not tid:
                    continue
                tid = int(tid)
                current_ids.add(tid)
                _upsert_list_membership(user.id, lid, media_type, tid)
                _upsert_state(user.id, media_type, tid)
                upsert_cached_media(media_type, entry)

            existing = UserListMembership.query.filter_by(
                user_id=user.id, list_id=lid, media_type=media_type
            ).all()
            for row in existing:
                if row.trakt_id not in current_ids:
                    db.session.delete(row)


def _upsert_list_membership(
    user_id: int,
    list_id: str,
    media_type: str,
    trakt_id: int,
) -> None:
    """Ensure a personal-list membership row exists."""
    row = UserListMembership.query.filter_by(
        user_id=user_id,
        list_id=str(list_id),
        media_type=media_type,
        trakt_id=int(trakt_id),
    ).first()
    if not row:
        db.session.add(UserListMembership(
            user_id=user_id,
            list_id=str(list_id),
            media_type=media_type,
            trakt_id=int(trakt_id),
        ))
    else:
        row.updated_at = datetime.utcnow()


def set_list_membership(
    user_id: int,
    list_id: str,
    media_type: str,
    trakt_id: int,
    *,
    on_list: bool,
) -> None:
    """Add or remove one cached personal-list membership row."""
    lid = str(list_id).strip()
    if not lid:
        return
    row = UserListMembership.query.filter_by(
        user_id=user_id,
        list_id=lid,
        media_type=media_type,
        trakt_id=int(trakt_id),
    ).first()
    if on_list and not row:
        db.session.add(UserListMembership(
            user_id=user_id,
            list_id=lid,
            media_type=media_type,
            trakt_id=int(trakt_id),
        ))
        _upsert_state(user_id, media_type, int(trakt_id))
    elif not on_list and row:
        db.session.delete(row)


def ensure_media_cached(media_type: str, trakt_ids: list[int]) -> None:
    """Fetch Trakt summaries for any missing CachedMedia rows (titles for My lists)."""
    if not trakt_ids:
        return
    existing = {
        m.trakt_id
        for m in CachedMedia.query.filter(
            CachedMedia.media_type == media_type,
            CachedMedia.trakt_id.in_(trakt_ids),
        ).all()
    }
    missing = [tid for tid in trakt_ids if tid not in existing]
    for tid in missing:
        try:
            summary = trakt_client.fetch_media_summary(media_type, tid)
            if summary:
                upsert_cached_media(media_type, summary)
        except Exception as exc:
            logger.warning('ensure_media_cached failed for %s %s: %s', media_type, tid, exc)
    if missing:
        db.session.commit()


def _upsert_state(
    user_id: int,
    media_type: str,
    trakt_id: int,
    on_watchlist: bool | None = None,
    watched: bool | None = None,
    plays: int = 0,
    last_watched_at: datetime | None = None,
    progress_percent: float | None = None,
) -> None:
    """Upsert a UserMediaState row. Booleans are set only when explicitly passed."""
    row = UserMediaState.query.filter_by(
        user_id=user_id, media_type=media_type, trakt_id=trakt_id
    ).first()
    if not row:
        row = UserMediaState(user_id=user_id, media_type=media_type, trakt_id=trakt_id)
        db.session.add(row)
    if on_watchlist is not None:
        row.on_watchlist = on_watchlist
    if watched is not None:
        row.watched = watched
    if plays:
        row.plays = plays
    if last_watched_at:
        row.last_watched_at = last_watched_at
    if progress_percent is not None:
        row.progress_percent = progress_percent
    row.updated_at = datetime.utcnow()


def apply_show_episode_progress(
    user_id: int,
    trakt_id: int,
    *,
    aired: int | None,
    completed: int | None,
    next_episode: dict | None = None,
) -> UserMediaState:
    """
    Cache show episode summary on UserMediaState for My Shows cards.

    ``aired`` / ``completed`` are regular-season counts when available.
    ``next_episode`` is a Trakt episode object or {season, number, title}.
    """
    row = UserMediaState.query.filter_by(
        user_id=user_id, media_type='show', trakt_id=int(trakt_id),
    ).first()
    if not row:
        row = UserMediaState(
            user_id=user_id, media_type='show', trakt_id=int(trakt_id),
        )
        db.session.add(row)

    if aired is not None:
        row.episodes_aired = int(aired)
    if completed is not None:
        row.episodes_completed = int(completed)
    if aired is not None and completed is not None and int(aired) > 0:
        row.progress_percent = round(100.0 * int(completed) / int(aired), 1)
        if int(completed) > 0:
            row.watched = True

    if next_episode:
        row.next_episode_season = next_episode.get('season')
        row.next_episode_number = next_episode.get('number')
        title = next_episode.get('title')
        row.next_episode_title = (str(title)[:400] if title else None)
    else:
        row.next_episode_season = None
        row.next_episode_number = None
        row.next_episode_title = None

    row.progress_detail_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    return row


def refresh_show_progress_for_ids(
    user: User,
    trakt_ids: list[int],
    *,
    force: bool = False,
    max_age_hours: int = 12,
    max_workers: int = 6,
) -> int:
    """
    Fetch Trakt progress for the given show ids (typically one My Shows page).

    Skips rows with fresh ``progress_detail_at`` unless ``force``. Does not run
    on full Refresh — only for the visible page — so Refresh stays fast.
    Returns how many shows were updated.
    """
    ids = [int(t) for t in trakt_ids if t]
    if not ids:
        return 0

    cutoff = datetime.utcnow() - timedelta(hours=max(1, int(max_age_hours)))
    rows = {
        r.trakt_id: r
        for r in UserMediaState.query.filter(
            UserMediaState.user_id == user.id,
            UserMediaState.media_type == 'show',
            UserMediaState.trakt_id.in_(ids),
        ).all()
    }
    need: list[int] = []
    for tid in ids:
        row = rows.get(tid)
        if force or row is None or not row.progress_detail_at or row.progress_detail_at < cutoff:
            need.append(tid)
    if not need:
        return 0

    from concurrent.futures import ThreadPoolExecutor, as_completed
    from flask import current_app

    app = current_app._get_current_object()
    user_id = user.id

    def _one(tid: int):
        with app.app_context():
            from models import User as UserModel
            u = UserModel.query.get(user_id)
            if not u:
                return tid, None
            try:
                return tid, trakt_client.get_show_progress(u, tid)
            except Exception as exc:
                logger.warning('Show progress fetch failed for %s: %s', tid, exc)
                return tid, None

    updated = 0
    workers = max(1, min(int(max_workers), len(need)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one, tid) for tid in need]
        for fut in as_completed(futures):
            tid, progress = fut.result()
            if not progress:
                continue
            aired = progress.get('aired')
            completed = progress.get('completed')
            if aired is None and completed is None:
                continue
            apply_show_episode_progress(
                user_id,
                tid,
                aired=int(aired or 0),
                completed=int(completed or 0),
                next_episode=progress.get('next_episode'),
            )
            updated += 1
    if updated:
        db.session.commit()
    return updated


def sync_providers_for_media(media: CachedMedia) -> list[str]:
    """Refresh TMDB providers for one media row; return provider names found."""
    if not tmdb_configured() or not media.tmdb_id:
        return []
    try:
        providers = get_watch_providers(media.media_type, media.tmdb_id)
    except Exception as exc:
        logger.warning('Provider sync failed for %s: %s', media.trakt_id, exc)
        return []

    MediaProviderAvailability.query.filter_by(cached_media_id=media.id).delete()
    names = []
    for p in providers:
        name = p.get('provider_name')
        if not name:
            continue
        db.session.add(MediaProviderAvailability(
            cached_media_id=media.id,
            provider_name=name,
            tmdb_provider_id=p.get('tmdb_provider_id'),
            offer_type=p.get('offer_type') or 'flatrate',
            region=p.get('region') or 'US',
            checked_at=datetime.utcnow(),
        ))
        names.append(name)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    return names


def check_release_watches(app: Flask) -> int:
    """Backward-compatible entry point — runs auto media alerts."""
    from services.alerts import run_media_alerts
    return run_media_alerts(app)


def run_catalog_sync_job(app: Flask) -> None:
    """Scheduled job: refresh newest catalog activity and enrich details."""
    with app.app_context():
        try:
            for media_type in ('movie', 'show'):
                if feed_count(media_type) == 0:
                    sync_catalog(media_type)
                else:
                    refresh_catalog_newest(media_type, pages=2)
            enrich_media_details('movie')
            enrich_media_details('show')
        except Exception as exc:
            logger.exception('Catalog sync job failed: %s', exc)


def start_scheduler(app: Flask):
    """Start APScheduler background jobs; return scheduler instance."""
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler(daemon=True)
    minutes = app.config.get('CATALOG_SYNC_INTERVAL_MINUTES', 60)
    hours = app.config.get('PROVIDER_SYNC_INTERVAL_HOURS', 12)
    scheduler.add_job(
        run_catalog_sync_job, 'interval', minutes=minutes, args=[app], id='catalog_sync',
        replace_existing=True,
    )
    scheduler.add_job(
        check_release_watches, 'interval', hours=hours, args=[app], id='media_alerts',
        replace_existing=True,
    )
    # Keep old job id replaced if a previous process registered it.
    try:
        scheduler.remove_job('release_watches')
    except Exception:
        pass
    scheduler.start()
    app.logger.info('Scheduler started (catalog every %sm, alerts every %sh)', minutes, hours)
    return scheduler
