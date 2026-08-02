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
    MediaProviderAvailability,
    Notification,
    ReleaseWatch,
    User,
    UserMediaState,
    db,
)
from services import trakt_client
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


def enrich_media_details_for_display(media: CachedMedia) -> CachedMedia:
    """Ensure overview/genres/poster exist (Trakt summary + local poster cache)."""
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
    return media


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
        enrich_media_details_for_display(media)
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


def sync_catalog(
    media_type: str = 'movie',
    days_back: int = 7,
    days_forward: int = 0,  # unused; kept for call-site compatibility
    pages: int = 2,
) -> int:
    """
    Sync Latest feed from Trakt DB updates (/movies|/shows/updates).

    Ordered by Trakt's updated_at — the only official timestamp for
    “recently added/changed in Trakt’s database”. There is no public
    created_at; first inserts and later metadata edits both appear here.
    """
    days_back = max(1, min(int(days_back), 29))
    start = (date.today() - timedelta(days=days_back)).isoformat()
    items = trakt_client.fetch_recent_updates(media_type, start, pages=pages)
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
    db.session.commit()
    logger.info(
        'Catalog sync %s (Trakt DB updates): upserted %s since %s (raw=%s)',
        media_type, count, start, len(items) if isinstance(items, list) else 0,
    )
    # Updates payload has no overview/images — pull full details for newest stubs.
    try:
        enriched = enrich_media_details(media_type, limit=min(40, max(count, 10)))
        if enriched:
            logger.info('Catalog enrich %s: filled details for %s titles', media_type, enriched)
    except Exception as exc:
        logger.warning('Catalog enrich after sync failed: %s', exc)
    return count


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


def sync_user_media_state(user: User) -> None:
    """Refresh local watchlist/watched cache from Trakt for one user."""
    for media_type in ('movie', 'show'):
        try:
            watchlist = trakt_client.get_watchlist(user, media_type)
            watched = trakt_client.get_watched(user, media_type)
        except Exception as exc:
            logger.warning('State sync failed for user %s %s: %s', user.id, media_type, exc)
            continue

        wl_ids = set()
        for entry in watchlist:
            entity = entry.get(media_type) or {}
            tid = (entity.get('ids') or {}).get('trakt')
            if tid:
                wl_ids.add(tid)
                _upsert_state(user.id, media_type, tid, on_watchlist=True)
                # Watchlist payloads include title/year/ids — cache for My Movies/Shows UI.
                upsert_cached_media(media_type, entry)

        for entry in watched:
            entity = entry.get(media_type) or {}
            tid = (entity.get('ids') or {}).get('trakt')
            if not tid:
                continue
            plays = entry.get('plays') or 0
            last_watched = _parse_trakt_dt(entry.get('last_watched_at'))
            progress = None
            if media_type == 'show':
                # Approximate from aired/completed if present in progress endpoints later
                progress = 100.0 if plays else 0.0
            _upsert_state(
                user.id,
                media_type,
                tid,
                on_watchlist=tid in wl_ids,
                watched=plays > 0,
                plays=plays,
                last_watched_at=last_watched,
                progress_percent=progress,
            )
            upsert_cached_media(media_type, entry)
    user.last_sync_at = datetime.utcnow()
    db.session.commit()


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
    on_watchlist: bool = False,
    watched: bool = False,
    plays: int = 0,
    last_watched_at: datetime | None = None,
    progress_percent: float | None = None,
) -> None:
    """Upsert a UserMediaState row."""
    row = UserMediaState.query.filter_by(
        user_id=user_id, media_type=media_type, trakt_id=trakt_id
    ).first()
    if not row:
        row = UserMediaState(user_id=user_id, media_type=media_type, trakt_id=trakt_id)
        db.session.add(row)
    row.on_watchlist = on_watchlist or bool(row.on_watchlist and on_watchlist)
    # Preserve watchlist flag if already set and this call is from watched loop
    if on_watchlist:
        row.on_watchlist = True
    row.watched = watched or row.watched
    if plays:
        row.plays = plays
    if last_watched_at:
        row.last_watched_at = last_watched_at
    if progress_percent is not None:
        row.progress_percent = progress_percent
    row.updated_at = datetime.utcnow()


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
    """Notify users when a watched upcoming title appears on any streaming service."""
    notified = 0
    with app.app_context():
        watches = ReleaseWatch.query.filter_by(active=True, notified_at=None).all()
        for watch in watches:
            media = CachedMedia.query.filter_by(
                media_type=watch.media_type, trakt_id=watch.trakt_id
            ).first()
            if not media:
                continue
            names = sync_providers_for_media(media)
            # Consider flatrate/ads/free as "available to stream"
            streaming = (
                MediaProviderAvailability.query
                .filter(
                    MediaProviderAvailability.cached_media_id == media.id,
                    MediaProviderAvailability.offer_type.in_(('flatrate', 'ads', 'free')),
                )
                .all()
            )
            if not streaming:
                continue
            provider_list = ', '.join(sorted({s.provider_name for s in streaming}))
            db.session.add(Notification(
                user_id=watch.user_id,
                title=f'Now streaming: {watch.title or media.title}',
                message=f'Available on: {provider_list}',
                link=f'/catalog/{watch.media_type}/{watch.trakt_id}',
            ))
            watch.notified_at = datetime.utcnow()
            watch.active = False
            notified += 1
        db.session.commit()
    logger.info('Release watch check notified %s items', notified)
    return notified


def run_catalog_sync_job(app: Flask) -> None:
    """Scheduled job: sync movie/show catalogs and enrich details."""
    with app.app_context():
        try:
            sync_catalog('movie')
            sync_catalog('show')
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
        check_release_watches, 'interval', hours=hours, args=[app], id='release_watches',
        replace_existing=True,
    )
    scheduler.start()
    app.logger.info('Scheduler started (catalog every %sm, providers every %sh)', minutes, hours)
    return scheduler
