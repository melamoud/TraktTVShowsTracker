"""
Titles Latest keeps hidden after Trakt re-lists them.

Latest is Trakt's "recently updated" feed: any metadata edit gives a title a new
timestamp and lifts it above the review marker. Two per-user memories survive
that bump:

- ``not_interested``: the user's Trakt hidden recommendations
- ``reviewed``: every feed title at/below the marker when the marker was set
"""

from __future__ import annotations

from datetime import datetime

from flask import current_app
from sqlalchemy import and_, insert, literal, or_, select

from models import CachedMedia, User, UserDismissedTitle, db

NOT_INTERESTED = 'not_interested'
REVIEWED = 'reviewed'

_FEED_SOURCE = 'trakt_db_updates'


def dismissed_ids(user_id: int, media_type: str, reason: str) -> set[int]:
    """Trakt ids this user dismissed for one reason."""
    rows = (
        UserDismissedTitle.query
        .filter_by(user_id=user_id, media_type=media_type, reason=reason)
        .with_entities(UserDismissedTitle.trakt_id)
        .all()
    )
    return {int(r[0]) for r in rows}


def record_not_interested(user_id: int, media_type: str, trakt_id: int) -> None:
    """Remember a hide done from this app (no wait for the next Trakt pull)."""
    exists = UserDismissedTitle.query.filter_by(
        user_id=user_id, media_type=media_type,
        trakt_id=int(trakt_id), reason=NOT_INTERESTED,
    ).first()
    if exists is None:
        db.session.add(UserDismissedTitle(
            user_id=user_id, media_type=media_type,
            trakt_id=int(trakt_id), reason=NOT_INTERESTED,
        ))


def ensure_not_interested_fresh(user: User, *, force: bool = False) -> None:
    """
    Mirror Trakt hidden recommendations (movies + shows) into the local table.

    Pulled at most once per admin Trakt read-cache TTL. A failed pull keeps the
    last copy, so Latest never flashes hidden titles back on a Trakt hiccup.
    """
    from services import trakt_client
    from services.trakt_cache import cache_is_fresh

    if not force and cache_is_fresh(getattr(user, 'hidden_recs_synced_at', None)):
        return
    fetched: dict[str, set[int]] = {}
    try:
        for media_type in ('movie', 'show'):
            ids: set[int] = set()
            for item in trakt_client.get_hidden_recommendations(user, media_type):
                entity = (item or {}).get(media_type) or {}
                try:
                    ids.add(int((entity.get('ids') or {}).get('trakt')))
                except (TypeError, ValueError):
                    continue
            fetched[media_type] = ids
    except Exception as exc:
        current_app.logger.warning('Hidden recommendations pull failed: %s', exc)
        return

    for media_type, remote in fetched.items():
        local = dismissed_ids(user.id, media_type, NOT_INTERESTED)
        gone = local - remote
        if gone:
            UserDismissedTitle.query.filter(
                UserDismissedTitle.user_id == user.id,
                UserDismissedTitle.media_type == media_type,
                UserDismissedTitle.reason == NOT_INTERESTED,
                UserDismissedTitle.trakt_id.in_(gone),
            ).delete(synchronize_session=False)
        for tid in remote - local:
            db.session.add(UserDismissedTitle(
                user_id=user.id, media_type=media_type,
                trakt_id=tid, reason=NOT_INTERESTED,
            ))
    user.hidden_recs_synced_at = datetime.utcnow()
    db.session.commit()


def record_reviewed_through(
    user_id: int,
    media_type: str,
    marker_media: CachedMedia,
    listed_at: datetime | None = None,
) -> int:
    """
    Remember every Latest feed title at or below ``marker_media`` as reviewed.

    Feed order is ``trakt_listed_at`` desc, then ``id`` desc, so ties at the
    marker timestamp count as reviewed only when they sort at/below it.
    ``listed_at`` overrides the title's current timestamp (a stored marker time).
    Returns the number of newly remembered titles.
    """
    listed_at = listed_at or marker_media.trakt_listed_at
    if listed_at is None:
        return 0
    already = select(UserDismissedTitle.trakt_id).where(
        UserDismissedTitle.user_id == user_id,
        UserDismissedTitle.media_type == media_type,
        UserDismissedTitle.reason == REVIEWED,
    )
    source = (
        select(
            literal(user_id),
            CachedMedia.media_type,
            CachedMedia.trakt_id,
            literal(REVIEWED),
            literal(datetime.utcnow()),
        )
        .where(
            CachedMedia.media_type == media_type,
            CachedMedia.feed_source == _FEED_SOURCE,
            or_(
                CachedMedia.trakt_listed_at < listed_at,
                and_(
                    CachedMedia.trakt_listed_at == listed_at,
                    CachedMedia.id <= marker_media.id,
                ),
            ),
            CachedMedia.trakt_id.not_in(already),
        )
    )
    stmt = insert(UserDismissedTitle).from_select(
        ['user_id', 'media_type', 'trakt_id', 'reason', 'created_at'], source,
    )
    result = db.session.execute(stmt)
    return int(result.rowcount or 0)


def forget_reviewed(user_id: int, media_type: str) -> None:
    """Clear marker → start over: reviewed titles may show again."""
    UserDismissedTitle.query.filter_by(
        user_id=user_id, media_type=media_type, reason=REVIEWED,
    ).delete(synchronize_session=False)
