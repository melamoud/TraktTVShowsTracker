"""Latest keeps Not-interested and already-reviewed titles hidden after Trakt re-lists them."""

from datetime import datetime, timedelta
from unittest.mock import patch

from flask_login import login_user

from models import CachedMedia, User, UserDismissedTitle, db
from routes.catalog_routes import _latest_visible_rows
from services.dismissed_titles import (
    NOT_INTERESTED,
    REVIEWED,
    dismissed_ids,
    ensure_not_interested_fresh,
)
from tests.conftest import login_client

BASE = datetime(2026, 11, 10, 12, 0, 0)


def _seed(media_type, trakt_id, minutes):
    row = CachedMedia(
        media_type=media_type,
        trakt_id=trakt_id,
        title=f'Title {trakt_id}',
        year=2026,
        trakt_listed_at=BASE + timedelta(minutes=minutes),
        feed_source='trakt_db_updates',
    )
    db.session.add(row)
    db.session.commit()
    return row


def _visible_ids(rows):
    return {int(r['media'].trakt_id) for r in rows if not r.get('older_than_marker')}


def test_reviewed_title_stays_hidden_after_trakt_edit(app, client, user):
    """A title under the marker stays reviewed when a later edit lifts it above."""
    login_client(client, app, user)
    with app.app_context():
        _seed('movie', 3001, 1)   # old, reviewed
        _seed('movie', 3002, 2)   # marker
        _seed('movie', 3003, 3)   # newer, not reviewed
    resp = client.post('/api/review-marker/movie/3002')
    assert resp.get_json()['success'] is True
    with app.app_context():
        assert dismissed_ids(user, 'movie', REVIEWED) == {3001, 3002}
        bumped = CachedMedia.query.filter_by(media_type='movie', trakt_id=3001).one()
        bumped.trakt_listed_at = BASE + timedelta(minutes=10)
        db.session.commit()
    with app.test_request_context('/latest/movies'):
        login_user(db.session.get(User, user))
        rows, _stats = _latest_visible_rows('movie', False, False, False)
        assert _visible_ids(rows) == {3003}


def test_clear_marker_forgets_reviewed_titles(app, client, user):
    login_client(client, app, user)
    with app.app_context():
        _seed('movie', 3101, 1)
        _seed('movie', 3102, 2)
    client.post('/api/review-marker/movie/3102')
    client.post('/api/review-marker/movie/clear')
    with app.app_context():
        assert dismissed_ids(user, 'movie', REVIEWED) == set()


def test_caught_up_remembers_whole_feed(app, client, user):
    login_client(client, app, user)
    with app.app_context():
        _seed('show', 3201, 1)
        _seed('show', 3202, 2)
    client.post('/api/review-marker/show/caught-up')
    with app.app_context():
        assert dismissed_ids(user, 'show', REVIEWED) == {3201, 3202}


def test_hide_not_interested_filter(app, client, user):
    login_client(client, app, user)
    with app.test_request_context('/latest/movies'):
        login_user(db.session.get(User, user))
        _seed('movie', 3301, 1)
        _seed('movie', 3302, 2)
        db.session.add(UserDismissedTitle(
            user_id=user, media_type='movie', trakt_id=3302, reason=NOT_INTERESTED,
        ))
        db.session.commit()
        hidden, stats = _latest_visible_rows(
            'movie', False, False, False, hide_not_interested=True,
        )
        assert _visible_ids(hidden) == {3301}
        assert stats['after_not_interested'] == 1
        shown, _ = _latest_visible_rows('movie', False, False, False)
        assert _visible_ids(shown) == {3301, 3302}


def test_hide_recommendation_records_not_interested(app, client, user):
    login_client(client, app, user)
    with patch('services.trakt_client.hide_recommendation'):
        resp = client.post('/api/recommendations/movie/3401/hide')
    assert resp.get_json()['success'] is True
    with app.app_context():
        assert dismissed_ids(user, 'movie', NOT_INTERESTED) == {3401}


def test_app_hide_recommendation_drops_title_from_app_latest(app, client, user):
    """Android hide (/api/v1) is remembered and the app's Latest list skips it."""
    login_client(client, app, user)
    with app.app_context():
        _seed('movie', 3501, 1)
        _seed('movie', 3502, 2)
    with patch('services.trakt_client.hide_recommendation'):
        resp = client.post('/api/v1/recommendations/movie/3502/hide')
    assert resp.get_json()['success'] is True
    with patch('routes.catalog_routes._ensure_latest_catalog'), \
            patch('services.dismissed_titles.ensure_not_interested_fresh'):
        data = client.get(
            '/api/v1/latest/movies?hide_watched=0&match_only=0&recent_years=0&hide_lists=0',
        ).get_json()
    ids = {int(item['trakt_id']) for item in data['items']}
    assert 3502 not in ids
    assert 3501 in ids
    assert data['hide_not_interested'] is True


def test_not_interested_pull_mirrors_trakt(app, user):
    """Pull adds new hides and drops titles un-hidden on Trakt.tv."""
    with app.app_context():
        db.session.add(UserDismissedTitle(
            user_id=user, media_type='movie', trakt_id=9, reason=NOT_INTERESTED,
        ))
        db.session.commit()

        def fake(_user, media_type):
            if media_type == 'movie':
                return [{'movie': {'ids': {'trakt': 1}}}, {'movie': {'ids': {'trakt': 2}}}]
            return [{'show': {'ids': {'trakt': 5}}}]

        u = db.session.get(User, user)
        with patch('services.trakt_client.get_hidden_recommendations', side_effect=fake):
            ensure_not_interested_fresh(u, force=True)
        assert dismissed_ids(user, 'movie', NOT_INTERESTED) == {1, 2}
        assert dismissed_ids(user, 'show', NOT_INTERESTED) == {5}
        assert u.hidden_recs_synced_at is not None

        with patch(
            'services.trakt_client.get_hidden_recommendations',
            side_effect=RuntimeError('trakt down'),
        ):
            ensure_not_interested_fresh(u, force=True)
        assert dismissed_ids(user, 'movie', NOT_INTERESTED) == {1, 2}
