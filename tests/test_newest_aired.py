"""My Shows / My Movies "Newest aired" view."""

from datetime import datetime, timedelta
from unittest.mock import patch

from models import CachedMedia, UserMediaState, UserPreference, db
from tests.conftest import login_client


def _seed_state(user_id, **kwargs):
    defaults = {
        'media_type': 'show', 'on_watchlist': True, 'watched': False,
    }
    defaults.update(kwargs)
    db.session.add(UserMediaState(user_id=user_id, **defaults))


def test_newest_aired_hides_future_shows_and_sorts(app, client, user):
    """Shows with no aired episode or fully caught up are hidden; newest first."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        for tid, title, aired, aired_count, completed in (
            (1, 'Old Show', datetime(2024, 1, 1), 10, 5),
            (2, 'New Show', datetime(2026, 8, 6), 8, 3),
            (3, 'Future Show', datetime(2026, 12, 1), 0, 0),
            (4, 'Caught Up Show', datetime(2026, 8, 5), 10, 10),
        ):
            _seed_state(user, trakt_id=tid, on_watchlist=True)
            db.session.add(CachedMedia(
                media_type='show', trakt_id=tid, title=title, year=2024,
            ))
            if aired:
                st = UserMediaState.query.filter_by(
                    user_id=user, media_type='show', trakt_id=tid,
                ).first()
                st.last_episode_aired_at = aired
                st.last_episode_label = f'{title} latest'
                st.episodes_aired = aired_count
                st.episodes_completed = completed
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get('/my/shows?lists_set=1&lists=watchlist&filter=lists&display=newest_aired')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'New Show' in html
    assert 'Old Show' in html
    assert 'Future Show' not in html
    assert 'Caught Up Show' not in html
    assert html.index('New Show') < html.index('Old Show')


def test_newest_aired_movies_sort_by_release_date(app, client, user):
    """Movies sort by release date descending, future releases hidden."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        from datetime import date
        for tid, title, released in (
            (10, 'Old Movie', date(2020, 1, 1)),
            (11, 'New Movie', date(2026, 8, 6)),
            (12, 'Future Movie', date(2026, 12, 1)),
        ):
            db.session.add(UserMediaState(
                user_id=user, media_type='movie', trakt_id=tid, on_watchlist=True,
            ))
            db.session.add(CachedMedia(
                media_type='movie', trakt_id=tid, title=title, year=2024,
                released_at=released,
            ))
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get('/my/movies?lists_set=1&lists=watchlist&filter=lists&display=newest_aired')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'New Movie' in html
    assert 'Old Movie' in html
    assert 'Future Movie' not in html
    assert html.index('New Movie') < html.index('Old Movie')


def test_newest_aired_pinned_shows_stay_on_top(app, client, user):
    """Pinned titles sort above everything else, even in newest-aired view."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        for tid, title, aired, aired_count, completed, pinned_at in (
            (1, 'Newest Show', datetime(2026, 8, 6), 8, 3, None),
            (2, 'Pinned Old Show', datetime(2024, 1, 1), 10, 5, datetime(2026, 8, 4)),
        ):
            _seed_state(user, trakt_id=tid, on_watchlist=True)
            db.session.add(CachedMedia(
                media_type='show', trakt_id=tid, title=title, year=2024,
            ))
            st = UserMediaState.query.filter_by(
                user_id=user, media_type='show', trakt_id=tid,
            ).first()
            st.last_episode_aired_at = aired
            st.last_episode_label = f'{title} latest'
            st.episodes_aired = aired_count
            st.episodes_completed = completed
            if pinned_at:
                st.pinned = True
                st.pinned_at = pinned_at
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get('/my/shows?lists_set=1&lists=watchlist&filter=lists&display=newest_aired')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Pinned Old Show' in html
    assert 'Newest Show' in html
    assert html.index('Pinned Old Show') < html.index('Newest Show')


def test_newest_aired_pinned_movies_stay_on_top(app, client, user):
    """Pinned movies sort above newer releases in newest-aired view."""
    from datetime import date
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        for tid, title, released, pinned_at in (
            (10, 'Newest Movie', date(2026, 8, 6), None),
            (11, 'Pinned Old Movie', date(2020, 1, 1), datetime(2026, 8, 4)),
        ):
            db.session.add(UserMediaState(
                user_id=user, media_type='movie', trakt_id=tid, on_watchlist=True,
                pinned=bool(pinned_at), pinned_at=pinned_at,
            ))
            db.session.add(CachedMedia(
                media_type='movie', trakt_id=tid, title=title, year=2024,
                released_at=released,
            ))
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get('/my/movies?lists_set=1&lists=watchlist&filter=lists&display=newest_aired')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Pinned Old Movie' in html
    assert 'Newest Movie' in html
    assert html.index('Pinned Old Movie') < html.index('Newest Movie')
