"""My movies/shows calendar view tests (weekly default, daily, monthly)."""

from datetime import date, datetime
from unittest.mock import patch

from models import CachedMedia, UserCalendarEvent, UserMediaState, UserPreference, db
from tests.conftest import login_client


def _seed_media(media_type, trakt_id, title, year=2024):
    if not CachedMedia.query.filter_by(media_type=media_type, trakt_id=trakt_id).first():
        db.session.add(CachedMedia(
            media_type=media_type, trakt_id=trakt_id, title=title, year=year,
        ))


def _seed_event(user, media_type, trakt_id, event_date, season=None, episode=None, ep_title=None):
    db.session.add(UserCalendarEvent(
        user_id=user, media_type=media_type, trakt_id=trakt_id,
        event_date=event_date, season_number=season, episode_number=episode,
        episode_title=ep_title,
    ))


def test_my_shows_weekly_calendar_renders_events(app, client, user):
    """Weekly calendar groups episodes by air date and links to detail."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        db.session.add(UserMediaState(
            user_id=user, media_type='show', trakt_id=195475, on_watchlist=True,
        ))
        _seed_media('show', 195475, 'The Ark', 2023)
        _seed_media('show', 999999, 'Other Show', 2024)
        _seed_event(user, 'show', 195475, date(2026, 8, 10), 3, 2, "It Won't Hurt Too Much")
        # Not on watchlist — must not appear.
        _seed_event(user, 'show', 999999, date(2026, 8, 10), 1, 1, 'Pilot')
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'), \
         patch('services.calendar_view.ensure_user_calendar_fresh', return_value=False):
        resp = client.get(
            '/my/shows?lists_set=1&lists=watchlist&filter=lists'
            '&display=weekly&cal_date=2026-08-10'
        )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'cal-grid' in html
    assert 'The Ark' in html
    assert 'S03E02' in html
    assert 'Hurt Too Much' in html
    assert '/catalog/show/195475' in html
    assert 'Other Show' not in html
    assert 'media-list' not in html


def test_my_movies_daily_calendar_uses_released(app, client, user):
    """Daily calendar shows movie release with detail link."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=700, on_watchlist=True,
        ))
        _seed_media('movie', 700, 'Future Film', 2026)
        _seed_event(user, 'movie', 700, date(2026, 8, 12))
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'), \
         patch('services.calendar_view.ensure_user_calendar_fresh', return_value=False):
        resp = client.get(
            '/my/movies?lists_set=1&lists=watchlist&filter=lists'
            '&display=daily&cal_date=2026-08-12'
        )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Future Film' in html
    assert '/catalog/movie/700' in html
    assert 'August 12, 2026' in html


def test_my_shows_monthly_calendar_marks_today(app, client, user):
    """Monthly grid renders weekday headers and marks today."""
    today = date.today()
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        db.session.add(UserMediaState(
            user_id=user, media_type='show', trakt_id=42, on_watchlist=True,
        ))
        _seed_media('show', 42, 'Monthly Show', 2024)
        _seed_event(user, 'show', 42, today, 1, 3, 'Mid')
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'), \
         patch('services.calendar_view.ensure_user_calendar_fresh', return_value=False):
        resp = client.get(
            f'/my/shows?lists_set=1&lists=watchlist&filter=lists'
            f'&display=monthly&cal_date={today.isoformat()}'
        )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Mon' in html and 'Sun' in html
    assert 'cal-today' in html
    assert 'Monthly Show' in html
    assert '/catalog/show/42' in html


def test_calendar_mode_is_remembered(app, client, user):
    """display choice persists via view prefs; List restores rows."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        db.session.add(UserMediaState(
            user_id=user, media_type='show', trakt_id=7, on_watchlist=True,
        ))
        _seed_media('show', 7, 'Remembered Show', 2024)
        db.session.commit()

    login_client(client, app, user)
    patches = (
        patch('routes.user_routes.ensure_user_media_fresh', return_value=False),
        patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]),
        patch('routes.user_routes.ensure_media_cached'),
        patch('routes.user_routes.enrich_media_list_for_display'),
        patch('services.calendar_view.ensure_user_calendar_fresh', return_value=False),
    )
    for p in patches:
        p.start()
    try:
        resp = client.get('/my/shows?lists_set=1&lists=watchlist&filter=lists&display=weekly')
        assert 'cal-grid' in resp.get_data(as_text=True)
        # Bare nav keeps the saved calendar mode.
        resp = client.get('/my/shows')
        assert 'cal-grid' in resp.get_data(as_text=True)
        # Back to list.
        resp = client.get('/my/shows?display=list')
        assert 'media-list' in resp.get_data(as_text=True)
        resp = client.get('/my/shows')
        assert 'media-list' in resp.get_data(as_text=True)
    finally:
        for p in patches:
            p.stop()


def test_ensure_user_calendar_fresh_parses_entries(app, user):
    """Sync maps show episodes + movie releases into UserCalendarEvent."""
    from models import User
    from services import calendar_view

    with app.app_context():
        user_obj = db.session.get(User, user)
        shows_payload = [
            {
                'first_aired': '2026-08-10T02:00:00.000Z',
                'episode': {'season': 3, 'number': 2, 'title': 'Ep'},
                'show': {'title': 'The Ark', 'year': 2023, 'ids': {'trakt': 195475}},
            },
        ]
        movies_payload = [
            {
                'released': '2026-08-12',
                'movie': {'title': 'Future Film', 'year': 2026, 'ids': {'trakt': 700}},
            },
        ]

        def fake_get(_user, media_type, start_date, days):
            assert start_date == '2026-08-10'
            return shows_payload if media_type == 'show' else movies_payload

        with patch.object(
            calendar_view.trakt_client, 'get_calendar_entries', side_effect=fake_get,
        ):
            ran = calendar_view.ensure_user_calendar_fresh(
                user_obj, date(2026, 8, 10), 7,
            )
        assert ran is True
        show_ev = UserCalendarEvent.query.filter_by(
            user_id=user, media_type='show', trakt_id=195475,
        ).one()
        assert show_ev.event_date == date(2026, 8, 10)
        assert (show_ev.season_number, show_ev.episode_number) == (3, 2)
        movie_ev = UserCalendarEvent.query.filter_by(
            user_id=user, media_type='movie', trakt_id=700,
        ).one()
        assert movie_ev.event_date == date(2026, 8, 12)
        # Titles cached for display.
        assert CachedMedia.query.filter_by(media_type='show', trakt_id=195475).count() == 1
        assert CachedMedia.query.filter_by(media_type='movie', trakt_id=700).count() == 1


def test_ensure_user_calendar_fresh_keeps_cache_on_error(app, user):
    """A failed Trakt fetch must not blank existing calendar rows."""
    from models import User
    from services import calendar_view

    with app.app_context():
        user_obj = db.session.get(User, user)
        _seed_event(user, 'show', 1, date(2026, 8, 11), 1, 1)
        db.session.commit()

        with patch.object(
            calendar_view.trakt_client, 'get_calendar_entries',
            side_effect=RuntimeError('trakt down'),
        ):
            ran = calendar_view.ensure_user_calendar_fresh(
                user_obj, date(2026, 8, 10), 7,
            )
        assert ran is False
        assert UserCalendarEvent.query.filter_by(
            user_id=user, media_type='show', trakt_id=1,
        ).count() == 1
