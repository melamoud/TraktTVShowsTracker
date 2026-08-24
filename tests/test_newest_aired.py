"""My Shows / My Movies "Newest aired" view."""

from datetime import date, datetime, timedelta
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
    """Shows with no aired episode or a future last air date are hidden; newest first.

    Caught-up shows still appear — sort is by last episode air date, not watch progress.
    """
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
    assert 'Caught Up Show' in html
    assert 'Future Show' not in html
    assert html.index('New Show') < html.index('Caught Up Show') < html.index('Old Show')


def test_newest_aired_includes_show_with_aired_count_but_no_date(app, client, user):
    """Progress can know episodes aired before last_episode_aired_at is seeded."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        _seed_state(
            user, trakt_id=157599, on_watchlist=True,
            episodes_aired=2, episodes_completed=0, progress_percent=0.0,
        )
        db.session.add(CachedMedia(
            media_type='show', trakt_id=157599, title='Lanterns', year=2026,
            released_at=date(2026, 8, 17),
        ))
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get('/my/shows?lists_set=1&lists=watchlist&filter=lists&display=newest_aired')
    assert resp.status_code == 200
    assert 'Lanterns' in resp.get_data(as_text=True)


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


def test_newest_aired_sorts_by_air_date_among_pins(app, client, user):
    """Among pinned shows, newest last-aired wins — not who was pinned last."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        for tid, title, aired, pinned_at in (
            (1, 'Person of Interest', datetime(2016, 6, 22), datetime(2026, 8, 15)),
            (2, 'Stuart Fails', datetime(2026, 8, 14), datetime(2026, 8, 1)),
        ):
            _seed_state(user, trakt_id=tid, on_watchlist=True)
            db.session.add(CachedMedia(
                media_type='show', trakt_id=tid, title=title, year=2016,
            ))
            st = UserMediaState.query.filter_by(
                user_id=user, media_type='show', trakt_id=tid,
            ).first()
            st.last_episode_aired_at = aired
            st.last_episode_label = title
            st.episodes_aired = 5
            st.episodes_completed = 1
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
    assert html.index('Stuart Fails') < html.index('Person of Interest')


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


def test_newest_aired_api_same_order_as_web(app, client, user):
    """Android /api/v1/my/shows uses the same newest-aired sort as the website."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        for tid, title, aired in (
            (1, 'Old Show', datetime(2024, 1, 1)),
            (2, 'New Show', datetime(2026, 8, 6)),
        ):
            _seed_state(user, trakt_id=tid, on_watchlist=True)
            db.session.add(CachedMedia(
                media_type='show', trakt_id=tid, title=title, year=2024,
            ))
            st = UserMediaState.query.filter_by(
                user_id=user, media_type='show', trakt_id=tid,
            ).first()
            st.last_episode_aired_at = aired
            st.episodes_aired = 5
            st.episodes_completed = 1
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get(
            '/api/v1/my/shows?lists_set=1&lists=watchlist&filter=lists&display=newest_aired'
        )
    assert resp.status_code == 200
    titles = [row['title'] for row in resp.get_json()['items']]
    assert titles.index('New Show') < titles.index('Old Show')
    assert resp.get_json()['display'] == 'newest_aired'
