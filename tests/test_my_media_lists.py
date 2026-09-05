"""My movies/shows multi-list filter tests."""

import json
from datetime import datetime
from unittest.mock import patch

from models import UserListMembership, UserMediaState, UserPreference, db
from tests.conftest import login_client


def _seed_state(
    user_id,
    *,
    media_type='movie',
    trakt_id=1,
    on_watchlist=False,
    watched=False,
    last_watched_at=None,
    progress_percent=None,
    progress_detail_at=None,
):
    db.session.add(UserMediaState(
        user_id=user_id,
        media_type=media_type,
        trakt_id=trakt_id,
        on_watchlist=on_watchlist,
        watched=watched,
        last_watched_at=last_watched_at,
        progress_percent=progress_percent,
        progress_detail_at=progress_detail_at,
    ))


def test_my_movies_defaults_to_auto_selected_lists(app, client, user):
    """Without lists_set, My movies uses Preferences auto-select defaults."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist", "10"]'
        prefs.hidden_list_ids_json = '["99"]'
        _seed_state(user, trakt_id=1, on_watchlist=True)
        _seed_state(user, trakt_id=2, on_watchlist=False)
        db.session.add(UserListMembership(
            user_id=user, list_id='10', media_type='movie', trakt_id=2
        ))
        db.session.add(UserListMembership(
            user_id=user, list_id='99', media_type='movie', trakt_id=3
        ))
        _seed_state(user, trakt_id=3, on_watchlist=False)
        db.session.commit()

    login_client(client, app, user)
    personal = [
        {'id': '10', 'slug': 'a', 'name': 'List 1', 'item_count': 1},
        {'id': '99', 'slug': 'h', 'name': 'Hidden', 'item_count': 1},
    ]
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False) as sync, \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=personal), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get('/my/movies')
    assert resp.status_code == 200
    # Auto cache check always runs; full Trakt pull only when activities changed.
    sync.assert_called_once()
    assert sync.call_args.kwargs.get('force') is False
    html = resp.get_data(as_text=True)
    assert 'List 1' in html
    assert 'Hidden' not in html
    # Default filter includes watchlist (1) and list 10 (2), not hidden list title 3.
    assert 'data-trakt-id="1"' in html
    assert 'data-trakt-id="2"' in html
    assert 'data-trakt-id="3"' not in html


def test_my_movies_refresh_forces_sync(app, client, user):
    """?refresh=1 forces ensure_user_media_fresh(..., force=True)."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        _seed_state(user, trakt_id=1, on_watchlist=True)
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=True) as sync, \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get('/my/movies?refresh=1')
    assert resp.status_code == 200
    sync.assert_called_once()
    assert sync.call_args.kwargs.get('media_types') == ('movie',)
    assert sync.call_args.kwargs.get('force') is True


def test_my_movies_auto_syncs_when_activities_change(app, user):
    """Stale last_activities fingerprint triggers a watchlist/watched sync."""
    from models import User
    from services.user_media_sync import ensure_user_media_fresh

    with app.app_context():
        user_obj = db.session.get(User, user)
        user_obj.last_sync_at = datetime(2026, 8, 1)
        user_obj.trakt_activities_json = json.dumps({
            'watchlist': '2026-08-01T00:00:00.000Z',
            'lists': '2026-08-01T00:00:00.000Z',
            'movies_watched': '2026-08-01T00:00:00.000Z',
            'movies_watchlisted': '2026-08-01T00:00:00.000Z',
        })
        db.session.commit()

        activities = {
            'watchlist': {'updated_at': '2026-08-05T13:02:01.000Z'},
            'lists': {'updated_at': '2026-08-01T00:00:00.000Z'},
            'movies': {
                'watched_at': '2026-08-01T00:00:00.000Z',
                'watchlisted_at': '2026-08-05T13:02:01.000Z',
            },
        }
        with patch('services.user_media_sync.get_last_activities', return_value=activities), \
             patch('services.user_media_sync.sync_user_media_state', return_value=True) as sync:
            ran = ensure_user_media_fresh(user_obj, media_types=('movie',), force=False)
        assert ran is True
        sync.assert_called_once()
        db.session.refresh(user_obj)
        stored = json.loads(user_obj.trakt_activities_json or '{}')
        assert stored.get('watchlist') == '2026-08-05T13:02:01.000Z'


def test_my_movies_skips_sync_when_activities_unchanged(app, user):
    """Matching fingerprint serves cache without a full Trakt pull."""
    from models import User
    from services.user_media_sync import ensure_user_media_fresh

    with app.app_context():
        user_obj = db.session.get(User, user)
        fp = {
            'watchlist': '2026-08-05T13:02:01.000Z',
            'lists': '2026-08-05T13:01:57.000Z',
            'movies_watched': '2026-08-05T03:02:56.000Z',
            'movies_watchlisted': '2026-08-03T19:09:59.000Z',
        }
        user_obj.last_sync_at = datetime(2026, 8, 5, 12, 0, 0)
        user_obj.trakt_activities_json = json.dumps(fp)
        db.session.commit()

        activities = {
            'watchlist': {'updated_at': fp['watchlist']},
            'lists': {'updated_at': fp['lists']},
            'movies': {
                'watched_at': fp['movies_watched'],
                'watchlisted_at': fp['movies_watchlisted'],
            },
        }
        with patch('services.user_media_sync.get_last_activities', return_value=activities), \
             patch('services.user_media_sync.sync_user_media_state') as sync:
            ran = ensure_user_media_fresh(user_obj, media_types=('movie',), force=False)
        assert ran is False
        sync.assert_not_called()
        db.session.refresh(user_obj)
        assert user_obj.last_sync_at > datetime(2026, 8, 5, 12, 0, 0)


def test_failed_sync_does_not_advance_fingerprint(app, user):
    """A failed watchlist pull must not mark activities fresh."""
    from models import User
    from services.user_media_sync import ensure_user_media_fresh

    with app.app_context():
        user_obj = db.session.get(User, user)
        old_fp = {
            'watchlist': '2026-08-01T00:00:00.000Z',
            'lists': '2026-08-01T00:00:00.000Z',
            'movies_watched': '2026-08-01T00:00:00.000Z',
            'movies_watchlisted': '2026-08-01T00:00:00.000Z',
        }
        user_obj.last_sync_at = datetime(2026, 8, 1)
        user_obj.trakt_activities_json = json.dumps(old_fp)
        db.session.commit()

        activities = {
            'watchlist': {'updated_at': '2026-08-05T13:02:01.000Z'},
            'lists': {'updated_at': '2026-08-01T00:00:00.000Z'},
            'movies': {
                'watched_at': '2026-08-01T00:00:00.000Z',
                'watchlisted_at': '2026-08-05T13:02:01.000Z',
            },
        }
        with patch('services.user_media_sync.get_last_activities', return_value=activities), \
             patch('services.user_media_sync.sync_user_media_state', return_value=False) as sync:
            ran = ensure_user_media_fresh(user_obj, media_types=('movie',), force=False)
        assert ran is True
        sync.assert_called_once()
        db.session.refresh(user_obj)
        stored = json.loads(user_obj.trakt_activities_json or '{}')
        assert stored.get('watchlist') == old_fp['watchlist']


def test_note_user_media_write_stores_activities_fingerprint(app, user):
    """Local writes bump last_sync_at and store last_activities so the next load does not full-pull lists."""
    from models import User
    from services.user_media_sync import note_user_media_write

    with app.app_context():
        user_obj = db.session.get(User, user)
        old_fp = {
            'watchlist': '2026-08-01T00:00:00.000Z',
            'lists': '2026-08-01T00:00:00.000Z',
            'ratings': '2026-08-01T00:00:00.000Z',
            'movies_watchlisted': '2026-08-01T00:00:00.000Z',
            'movies_rated': '2026-08-01T00:00:00.000Z',
        }
        user_obj.last_sync_at = datetime(2026, 8, 1)
        user_obj.trakt_activities_json = json.dumps(old_fp)
        db.session.commit()

        activities = {
            'watchlist': {'updated_at': '2026-08-16T22:00:00.000Z'},
            'lists': {'updated_at': '2026-08-16T22:00:00.000Z'},
            'ratings': {'updated_at': '2026-08-16T22:00:00.000Z'},
            'movies': {
                'watchlisted_at': '2026-08-16T22:00:00.000Z',
                'rated_at': '2026-08-16T22:00:00.000Z',
            },
        }
        with patch('services.user_media_sync.get_last_activities', return_value=activities) as probe:
            note_user_media_write(user_obj, media_types=('movie',), aspects=('ratings',))

        probe.assert_called_once()
        db.session.refresh(user_obj)
        stored = json.loads(user_obj.trakt_activities_json or '{}')
        assert stored.get('watchlist') == '2026-08-16T22:00:00.000Z'
        assert stored.get('lists') == '2026-08-16T22:00:00.000Z'
        assert user_obj.last_sync_at > datetime(2026, 8, 1)


def test_my_movies_lists_set_overrides_defaults(app, client, user):
    """lists_set=1 uses explicit multi-select, not Preferences defaults."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        _seed_state(user, trakt_id=1, on_watchlist=True)
        _seed_state(user, trakt_id=2, on_watchlist=False)
        db.session.add(UserListMembership(
            user_id=user, list_id='10', media_type='movie', trakt_id=2
        ))
        db.session.commit()

    login_client(client, app, user)
    personal = [{'id': '10', 'slug': 'a', 'name': 'List 1', 'item_count': 1}]
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=personal), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get('/my/movies?lists_set=1&lists=10&filter=lists')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'data-trakt-id="2"' in html
    assert 'data-trakt-id="1"' not in html


def test_my_movies_pages_current_slice_only(app, client, user):
    """My movies loads only the requested page of results."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        for tid in range(1, 26):
            _seed_state(user, trakt_id=tid, on_watchlist=True)
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached') as ensure, \
         patch('routes.user_routes.enrich_media_list_for_display') as enrich:
        resp = client.get('/my/movies?lists_set=1&lists=watchlist&filter=lists&per_page=10&page=2')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'page 2/3' in html
    assert html.count('class="media-row"') == 10
    # Enrichment only asked for the current page ids.
    ensured_ids = ensure.call_args.args[1]
    assert len(ensured_ids) == 10
    enrich.assert_called_once()
    assert len(enrich.call_args.args[0]) <= 10


def test_my_shows_orders_by_progress_then_last_watched(app, client, user):
    """In-progress first, then recently watched; never-started last."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        _seed_state(
            user, media_type='show', trakt_id=1, on_watchlist=True,
            last_watched_at=datetime(2024, 1, 1), progress_percent=100.0, watched=True,
        )
        _seed_state(
            user, media_type='show', trakt_id=2, on_watchlist=True,
            last_watched_at=datetime(2026, 8, 1), progress_percent=40.0, watched=True,
        )
        _seed_state(
            user, media_type='show', trakt_id=3, on_watchlist=True,
            last_watched_at=datetime(2026, 7, 1), progress_percent=100.0, watched=True,
        )
        _seed_state(user, media_type='show', trakt_id=4, on_watchlist=True)
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get('/my/shows?lists_set=1&lists=watchlist&filter=lists')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    pos = {tid: html.index(f'data-trakt-id="{tid}"') for tid in (1, 2, 3, 4)}
    assert pos[2] < pos[3] < pos[1] < pos[4]


def test_my_shows_pinned_sort_above_others(app, client, user):
    """Pinned titles stay above in-progress / recently watched."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        _seed_state(
            user, media_type='show', trakt_id=1, on_watchlist=True,
            watched=True, progress_percent=40.0,
            last_watched_at=datetime(2026, 8, 5),
        )
        db.session.add(UserMediaState(
            user_id=user, media_type='show', trakt_id=2, on_watchlist=True,
            watched=False, pinned=True, pinned_at=datetime(2026, 8, 4),
        ))
        db.session.add(UserMediaState(
            user_id=user, media_type='show', trakt_id=3, on_watchlist=True,
            watched=False, pinned=True, pinned_at=datetime(2026, 8, 5),
        ))
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get('/my/shows?lists_set=1&lists=watchlist&filter=lists')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    pos = {tid: html.index(f'data-trakt-id="{tid}"') for tid in (1, 2, 3)}
    assert pos[3] < pos[2] < pos[1]
    assert 'Pinned' in html
    assert 'data-action="pin-remove"' in html


def test_api_pin_toggles_local_flag(app, client, user):
    """Pin API sets/clears local pinned state without Trakt writes."""
    with app.app_context():
        _seed_state(user, media_type='movie', trakt_id=9, on_watchlist=True)
        db.session.commit()

    login_client(client, app, user)
    resp = client.post('/api/pin/movie/9', json={'action': 'pin'})
    assert resp.status_code == 200
    assert resp.get_json()['pinned'] is True
    with app.app_context():
        st = UserMediaState.query.filter_by(
            user_id=user, media_type='movie', trakt_id=9,
        ).one()
        assert st.pinned is True
        assert st.pinned_at is not None

    resp = client.post('/api/pin/movie/9', json={'action': 'unpin'})
    assert resp.status_code == 200
    assert resp.get_json()['pinned'] is False
    with app.app_context():
        st = UserMediaState.query.filter_by(
            user_id=user, media_type='movie', trakt_id=9,
        ).one()
        assert st.pinned is False
        assert st.pinned_at is None


def test_my_shows_card_shows_episode_progress_and_next(app, client, user):
    """Show cards render cached x/y watched and next episode."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        st = UserMediaState(
            user_id=user,
            media_type='show',
            trakt_id=55,
            on_watchlist=True,
            watched=True,
            progress_percent=50.0,
            episodes_aired=10,
            episodes_completed=5,
            next_episode_season=2,
            next_episode_number=1,
            next_episode_title='Blood Trial',
            progress_detail_at=datetime.utcnow(),
        )
        db.session.add(st)
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get('/my/shows?lists_set=1&lists=watchlist&filter=lists')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert '5</strong> / 10 episodes watched' in html
    assert 'Next: S2E1 — Blood Trial' in html


def test_refresh_show_progress_skips_fresh_cache(app, user):
    """Page enrich does not re-hit Trakt when progress payload is fresh."""
    from models import User
    from services.sync_jobs import refresh_show_progress_for_ids

    with app.app_context():
        user_obj = db.session.get(User, user)
        db.session.add(UserMediaState(
            user_id=user,
            media_type='show',
            trakt_id=77,
            watched=True,
            episodes_aired=8,
            episodes_completed=3,
            progress_payload_json='{}',
            progress_detail_at=datetime.utcnow(),
        ))
        db.session.commit()
        with patch('services.sync_jobs.trakt_client.get_show_progress') as prog:
            n = refresh_show_progress_for_ids(user_obj, [77], force=False)
        assert n == 0
        prog.assert_not_called()


def test_my_shows_both_excludes_watch_history_only(app, client, user):
    """Both / Watched never include titles that are off every selected list."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        _seed_state(user, media_type='show', trakt_id=232779, on_watchlist=True, watched=True)
        _seed_state(
            user, media_type='show', trakt_id=999001, on_watchlist=False, watched=True,
            progress_percent=16.7,
        )
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        both = client.get('/my/shows?lists_set=1&lists=watchlist&filter=both')
        watched = client.get('/my/shows?lists_set=1&lists=watchlist&filter=watched')
    assert both.status_code == 200
    both_html = both.get_data(as_text=True)
    assert 'data-trakt-id="232779"' in both_html
    assert 'data-trakt-id="999001"' not in both_html
    watched_html = watched.get_data(as_text=True)
    assert 'data-trakt-id="232779"' in watched_html
    assert 'data-trakt-id="999001"' not in watched_html


def test_my_movies_unwatched_filter(app, client, user):
    """My movies Unwatched shows list titles that are not watched."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        _seed_state(user, trakt_id=1, on_watchlist=True, watched=False)
        _seed_state(user, trakt_id=2, on_watchlist=True, watched=True)
        _seed_state(user, trakt_id=3, on_watchlist=False, watched=True)
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get('/my/movies?lists_set=1&lists=watchlist&filter=unwatched')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Unwatched' in html
    assert 'data-trakt-id="1"' in html
    assert 'data-trakt-id="2"' not in html
    assert 'data-trakt-id="3"' not in html


def test_my_shows_unwatched_excludes_finished_list_titles(app, client, user):
    """Unwatched episodes drops 100% shows even when they remain on a list."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist", "10"]'
        _seed_state(
            user, media_type='show', trakt_id=100, on_watchlist=True,
            watched=True, progress_percent=100.0,
            progress_detail_at=datetime(2026, 8, 1),
            last_watched_at=datetime(2026, 8, 1),
        )
        _seed_state(
            user, media_type='show', trakt_id=101, on_watchlist=True,
            watched=True, progress_percent=40.0,
            progress_detail_at=datetime(2026, 8, 2),
            last_watched_at=datetime(2026, 8, 2),
        )
        _seed_state(user, media_type='show', trakt_id=102, on_watchlist=True)
        _seed_state(
            user, media_type='show', trakt_id=103, on_watchlist=False,
            watched=True, progress_percent=100.0,
            progress_detail_at=datetime(2026, 8, 1),
        )
        # Fake 100% without detail stamp must still appear (untrusted).
        _seed_state(
            user, media_type='show', trakt_id=104, on_watchlist=True,
            watched=True, progress_percent=100.0,
        )
        db.session.add(UserListMembership(
            user_id=user, list_id='10', media_type='show', trakt_id=100,
        ))
        db.session.commit()

    login_client(client, app, user)
    personal = [{'id': '10', 'slug': 'a', 'name': 'List 1', 'item_count': 1}]
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=personal), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get(
            '/my/shows?lists_set=1&lists=watchlist&lists=10&filter=unwatched_episodes'
        )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'data-trakt-id="100"' not in html  # trusted finished, on list
    assert 'data-trakt-id="101"' in html      # partial
    assert 'data-trakt-id="102"' in html      # never started, on list
    assert 'data-trakt-id="103"' not in html  # trusted finished, not on list
    assert 'data-trakt-id="104"' in html      # fake 100% without detail
    assert '>3</strong> of <strong>3</strong>' in html
