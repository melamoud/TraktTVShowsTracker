from flask_login import login_user

from models import CachedMedia, User, UserListMembership, UserMediaState, db
from routes.catalog_routes import _latest_visible_rows
from tests.conftest import login_client


def _seed_feed(media_type, trakt_ids):
    for tid in trakt_ids:
        db.session.add(CachedMedia(
            media_type=media_type,
            trakt_id=tid,
            title=f'Title {tid}',
            year=2026,
            trakt_listed_at=db.func.now(),
            feed_source='trakt_db_updates',
        ))
    db.session.commit()


def _list_membership(media_type, trakt_id, list_id='21576412'):
    db.session.add(UserListMembership(
        user_id=1,
        media_type=media_type,
        trakt_id=trakt_id,
        list_id=list_id,
    ))
    db.session.commit()


def _watch_state(media_type, trakt_id, watched=True):
    db.session.add(UserMediaState(
        user_id=1,
        media_type=media_type,
        trakt_id=trakt_id,
        watched=watched,
    ))
    db.session.commit()


def _user_obj(user_id):
    return db.session.get(User, user_id)


def test_latest_hide_lists_excludes_personal_list_titles(app, client, user):
    login_client(client, app, user)
    with app.test_request_context('/latest/shows'):
        login_user(_user_obj(user))
        _seed_feed('show', [1001, 1002, 1003])
        _list_membership('show', 1002)

        rows, stats = _latest_visible_rows('show', hide_watched=False, match_only=False, hide_lists=True)
        ids = {int(r['media'].trakt_id) for r in rows}
        assert 1001 in ids
        assert 1002 not in ids
        assert 1003 in ids
        assert stats['after_lists'] == 2


def test_latest_show_lists_includes_titles_when_disabled(app, client, user):
    login_client(client, app, user)
    with app.test_request_context('/latest/shows'):
        login_user(_user_obj(user))
        _seed_feed('show', [1001, 1002])
        _list_membership('show', 1002)

        rows, _stats = _latest_visible_rows('show', hide_watched=False, match_only=False, hide_lists=False)
        ids = {int(r['media'].trakt_id) for r in rows}
        assert ids == {1001, 1002}


def test_latest_hide_lists_combined_with_hide_watched(app, client, user):
    login_client(client, app, user)
    with app.test_request_context('/latest/movies'):
        login_user(_user_obj(user))
        _seed_feed('movie', [2001, 2002, 2003, 2004])
        _list_membership('movie', 2002)
        _watch_state('movie', 2003)

        rows, stats = _latest_visible_rows('movie', hide_watched=True, match_only=False, hide_lists=True)
        ids = {int(r['media'].trakt_id) for r in rows}
        assert ids == {2001, 2004}
        assert stats['after_watched'] == 3
        assert stats['after_lists'] == 2
