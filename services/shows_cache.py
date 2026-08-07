"""
My Shows cache maintenance — the only place per-show Trakt fetches happen.

Pages render from cache only. This module runs inside the periodic media job
(admin-configurable interval, default 6h):

1. last-aired dates derived from the already-synced My-calendar rows (free;
   covers watchlisted / in-progress shows).
2. per-show seasons fetch for shows with no calendar coverage (list-only) or
   never seeded — sequential, spaced, aborted on the first HTTP 429.
3. progress refresh for shows not known finished (feeds x/y + the
   newest-aired "hide caught-up" filter).

A manual page Refresh queues a one-off background cycle for that user instead
of blocking the request.
"""

import logging
import time
from datetime import date, datetime, timedelta

from flask import Flask

from models import User, UserCalendarEvent, UserMediaState, db
from services import trakt_client
from services.sync_jobs import (
    _update_latest_aired_for_show,
    collection_trakt_ids,
    refresh_show_progress_for_ids,
)

logger = logging.getLogger('app')

# Never-aired shows get re-seeded at most this often (their premiere arrives
# via the forward calendar window in the meantime).
SEED_RECHECK_DAYS = 30
_SEED_SPACING_SECONDS = 0.25


def _calendar_last_aired(user_id: int, show_ids: list[int], today: date) -> dict[int, tuple]:
    """Latest aired calendar row per show: {trakt_id: (event_date, label)}."""
    rows = (
        UserCalendarEvent.query
        .filter(
            UserCalendarEvent.user_id == user_id,
            UserCalendarEvent.media_type == 'show',
            UserCalendarEvent.trakt_id.in_(show_ids),
            UserCalendarEvent.event_date <= today,
        )
        .order_by(UserCalendarEvent.event_date.asc())
        .all()
    )
    latest: dict[int, tuple] = {}
    for e in rows:
        label = None
        if e.season_number is not None and e.episode_number is not None:
            parts = [f'S{int(e.season_number):02d}E{int(e.episode_number):02d}']
            if e.episode_title:
                parts.append(str(e.episode_title))
            label = ' · '.join(parts)
        latest[int(e.trakt_id)] = (e.event_date, label)
    return latest


def refresh_shows_cache_for_user(user: User, *, skip_per_show: bool = False) -> dict:
    """Refresh last-aired + progress cache for one user. Returns stats.

    ``skip_per_show`` skips steps 2-3 entirely (caller hit a Trakt 429 this
    run — calendar-derived updates are cache reads and still run).
    """
    today = date.today()
    show_ids = sorted(collection_trakt_ids(user.id, 'show'))
    stats = {'calendar': 0, 'seeded': 0, 'progress': 0, 'aborted': skip_per_show}
    if not show_ids:
        return stats

    states = {
        int(r.trakt_id): r
        for r in UserMediaState.query.filter(
            UserMediaState.user_id == user.id,
            UserMediaState.media_type == 'show',
            UserMediaState.trakt_id.in_(show_ids),
        ).all()
    }

    def _state(tid: int) -> UserMediaState:
        row = states.get(tid)
        if row is None:
            row = UserMediaState(user_id=user.id, media_type='show', trakt_id=tid)
            db.session.add(row)
            states[tid] = row
        return row

    # 1. Free: derive last-aired from the freshly synced calendar rows.
    for tid, (air_day, label) in _calendar_last_aired(user.id, show_ids, today).items():
        row = _state(tid)
        aired_dt = datetime.combine(air_day, datetime.min.time())
        if row.last_episode_aired_at is None or aired_dt > row.last_episode_aired_at:
            row.last_episode_aired_at = aired_dt
            if label:
                row.last_episode_label = label
            row.last_aired_checked_at = datetime.utcnow()
            stats['calendar'] += 1

    # 2. Per-show seed: nothing stored yet and (never checked or stale check).
    if skip_per_show:
        db.session.commit()
        logger.info('My Shows cache refresh for user %s: %s', user.id, stats)
        return stats
    recheck_before = datetime.utcnow() - timedelta(days=SEED_RECHECK_DAYS)
    need_seed = [
        tid for tid in show_ids
        if (states.get(tid) is None or states[tid].last_episode_aired_at is None)
        and (
            states.get(tid) is None
            or states[tid].last_aired_checked_at is None
            or states[tid].last_aired_checked_at < recheck_before
        )
    ]
    for tid in need_seed:
        time.sleep(_SEED_SPACING_SECONDS)
        try:
            if _update_latest_aired_for_show(user.id, tid):
                stats['seeded'] += 1
        except Exception as exc:
            if getattr(exc, 'status_code', None) != 429:
                raise
            stats['aborted'] = True
            logger.warning(
                'Trakt is throttling; remaining %s show seeds deferred to next run',
                len(need_seed) - need_seed.index(tid),
            )
            break
    db.session.commit()

    # 3. Progress for anything not known finished (NULL = unknown, fetch once).
    if not stats['aborted']:
        open_ids = [
            tid for tid in show_ids
            if (states.get(tid) is None)
            or (states[tid].progress_percent is None or states[tid].progress_percent < 100)
        ]
        if open_ids:
            try:
                stats['progress'] = refresh_show_progress_for_ids(
                    user, open_ids, max_workers=2,
                )
            except Exception as exc:
                logger.warning('Progress refresh failed for user %s: %s', user.id, exc)
    logger.info('My Shows cache refresh for user %s: %s', user.id, stats)
    return stats


def seed_new_shows_inline(user: User, *, limit: int = 3) -> int:
    """Seed last-aired for newly discovered shows during a page load.

    Bounded to ``limit`` shows so a big list import cannot slow the request;
    the periodic job picks up the rest.
    """
    rows = (
        UserMediaState.query
        .filter(
            UserMediaState.user_id == user.id,
            UserMediaState.media_type == 'show',
            UserMediaState.last_aired_checked_at.is_(None),
        )
        .limit(limit)
        .all()
    )
    done = 0
    for row in rows:
        try:
            if _update_latest_aired_for_show(user.id, int(row.trakt_id)):
                done += 1
        except Exception as exc:
            if getattr(exc, 'status_code', None) == 429:
                break
            raise
    if done:
        db.session.commit()
    return done


def _user_media_cycle_job(app: Flask, user_id: int) -> None:
    """One-off queued cycle for a single user (manual page Refresh)."""
    from services.alerts import _run_alerts_for_user

    with app.app_context():
        user = db.session.get(User, user_id)
        if user is None or not user.is_active_account:
            return
        try:
            _created, rate_limited = _run_alerts_for_user(user)
            refresh_shows_cache_for_user(user, skip_per_show=rate_limited)
            db.session.commit()
        except Exception as exc:
            logger.warning('Queued media cycle failed for user %s: %s', user_id, exc)
            db.session.rollback()


def queue_user_media_cycle(app: Flask, user_id: int) -> bool:
    """Queue a background alerts+cache cycle for one user.

    Returns True when queued on the scheduler; runs inline when no scheduler
    is available (tests, one-off scripts).
    """
    scheduler = (app.extensions or {}).get('shows_scheduler')
    if scheduler is None:
        _user_media_cycle_job(app, user_id)
        return False
    scheduler.add_job(
        _user_media_cycle_job, 'date', args=[app, user_id],
        id=f'user_media_cycle_{user_id}', replace_existing=True,
    )
    return True
