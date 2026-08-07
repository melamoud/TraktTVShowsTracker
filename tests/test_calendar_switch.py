"""Calendar / List view switching persists correctly."""

from datetime import date
from unittest.mock import patch

from models import CachedMedia, UserCalendarEvent, UserMediaState, UserPreference, db
from tests.conftest import login_client


def test_list_link_from_calendar_switches_back(app, client, user):
    """Clicking List from a calendar view must emit display=list and switch back."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        prefs.ui_view_settings_json = '{"my_shows": {"display": "weekly"}}'
        db.session.add(UserMediaState(
            user_id=user, media_type='show', trakt_id=1, on_watchlist=True,
        ))
        db.session.add(CachedMedia(media_type='show', trakt_id=1, title='Show A', year=2024))
        db.session.add(UserCalendarEvent(
            user_id=user, media_type='show', trakt_id=1, event_date=date(2026, 8, 10),
        ))
        db.session.commit()

    login_client(client, app, user)
    patches = (
        patch('routes.user_routes.ensure_user_media_fresh', return_value=False),
        patch('routes.user_routes.refresh_show_progress_for_ids', return_value=0),
        patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]),
        patch('routes.user_routes.ensure_media_cached'),
        patch('routes.user_routes.enrich_media_list_for_display'),
        patch('services.calendar_view.ensure_user_calendar_fresh', return_value=False),
    )
    for p in patches:
        p.start()
    try:
        # Calendar page should render
        resp = client.get('/my/shows?lists_set=1&lists=watchlist&filter=lists&display=weekly&cal_date=2026-08-10')
        html = resp.get_data(as_text=True)
        assert 'cal-grid' in html
        # The List pill link must contain display=list
        assert 'display=list' in html
        # Clicking the list URL explicitly should switch back
        resp = client.get('/my/shows?lists_set=1&lists=watchlist&filter=lists&display=list')
        html = resp.get_data(as_text=True)
        assert 'media-list' in html
        assert 'cal-grid' not in html
    finally:
        for p in patches:
            p.stop()
