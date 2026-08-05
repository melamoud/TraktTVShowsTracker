"""My movies/shows multi-list filter tests."""

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
):
    db.session.add(UserMediaState(
        user_id=user_id,
        media_type=media_type,
        trakt_id=trakt_id,
        on_watchlist=on_watchlist,
        watched=watched,
        last_watched_at=last_watched_at,
        progress_percent=progress_percent,
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
    with patch('routes.user_routes.sync_user_media_state') as sync, \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=personal), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get('/my/movies')
    assert resp.status_code == 200
    sync.assert_not_called()
    html = resp.get_data(as_text=True)
    assert 'List 1' in html
    assert 'Hidden' not in html
    # Default filter includes watchlist (1) and list 10 (2), not hidden list title 3.
    assert 'data-trakt-id="1"' in html
    assert 'data-trakt-id="2"' in html
    assert 'data-trakt-id="3"' not in html


def test_my_movies_refresh_triggers_sync(app, client, user):
    """?refresh=1 is the only path that full-syncs Trakt on My pages."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        _seed_state(user, trakt_id=1, on_watchlist=True)
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.sync_user_media_state') as sync, \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get('/my/movies?refresh=1')
    assert resp.status_code == 200
    sync.assert_called_once()
    assert sync.call_args.kwargs.get('media_types') == ('movie',)


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
    with patch('routes.user_routes.sync_user_media_state'), \
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
    with patch('routes.user_routes.sync_user_media_state'), \
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
    with patch('routes.user_routes.sync_user_media_state'), \
         patch('routes.user_routes.refresh_show_progress_for_ids', return_value=0), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get('/my/shows?lists_set=1&lists=watchlist&filter=lists')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    pos = {tid: html.index(f'data-trakt-id="{tid}"') for tid in (1, 2, 3, 4)}
    assert pos[2] < pos[3] < pos[1] < pos[4]


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
    with patch('routes.user_routes.sync_user_media_state'), \
         patch('routes.user_routes.refresh_show_progress_for_ids', return_value=0), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get('/my/shows?lists_set=1&lists=watchlist&filter=lists')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert '5</strong> / 10 episodes watched' in html
    assert 'Next: S2E1 — Blood Trial' in html


def test_refresh_show_progress_skips_fresh_cache(app, user):
    """Page enrich does not re-hit Trakt when progress_detail_at is fresh."""
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
            progress_detail_at=datetime.utcnow(),
        ))
        db.session.commit()
        with patch('services.sync_jobs.trakt_client.get_show_progress') as prog:
            n = refresh_show_progress_for_ids(user_obj, [77], force=False)
        assert n == 0
        prog.assert_not_called()


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
    with patch('routes.user_routes.sync_user_media_state'), \
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
            last_watched_at=datetime(2026, 8, 1),
        )
        _seed_state(
            user, media_type='show', trakt_id=101, on_watchlist=True,
            watched=True, progress_percent=40.0,
            last_watched_at=datetime(2026, 8, 2),
        )
        _seed_state(user, media_type='show', trakt_id=102, on_watchlist=True)
        _seed_state(
            user, media_type='show', trakt_id=103, on_watchlist=False,
            watched=True, progress_percent=100.0,
        )
        db.session.add(UserListMembership(
            user_id=user, list_id='10', media_type='show', trakt_id=100,
        ))
        db.session.commit()

    login_client(client, app, user)
    personal = [{'id': '10', 'slug': 'a', 'name': 'List 1', 'item_count': 1}]
    with patch('routes.user_routes.sync_user_media_state'), \
         patch('routes.user_routes.refresh_show_progress_for_ids', return_value=0), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=personal), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get(
            '/my/shows?lists_set=1&lists=watchlist&lists=10&filter=unwatched_episodes'
        )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'data-trakt-id="100"' not in html  # finished, on list
    assert 'data-trakt-id="101"' in html      # partial
    assert 'data-trakt-id="102"' in html      # never started, on list
    assert 'data-trakt-id="103"' not in html  # finished, not on list
    assert '>2</strong> of <strong>2</strong>' in html
