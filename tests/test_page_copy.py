"""Page headings use Help ?, not long intros; list filter vs nav Search."""

from unittest.mock import patch

from tests.conftest import login_client


def test_search_page_help_without_long_intro(app, client, user):
    login_client(client, app, user)
    html = client.get('/search').get_data(as_text=True)
    assert 'Type a title' in html
    assert 'href="/help/search"' in html
    assert 'class="page-help"' in html
    assert 'Search Trakt’s movie' not in html
    assert 'placeholder="Title (min. 2 characters)"' in html
    assert 'Search Trakt for new titles (not your lists).' in html
    assert 'Filter this page…' not in html


def test_home_and_prefs_and_alerts_have_help(app, client, user):
    login_client(client, app, user)
    home = client.get('/').get_data(as_text=True)
    assert 'href="/help/overview"' in home
    assert 'Review newly listed titles on Trakt' not in home

    prefs = client.get('/preferences').get_data(as_text=True)
    assert 'href="/help/preferences"' in prefs
    assert 'Streaming services you use, plus genres' not in prefs
    assert 'Show in menu' in prefs

    alerts = client.get('/notifications').get_data(as_text=True)
    assert 'href="/help/release_alerts"' in alerts
    assert 'Unread alerts are brighter.' not in alerts
    assert 'Hiding read' in alerts or 'Showing all' in alerts


def test_latest_and_my_use_filter_this_page(app, client, user):
    login_client(client, app, user)
    with patch('routes.catalog_routes.feed_count', return_value=0), \
         patch('routes.catalog_routes.ensure_catalog_through_marker'), \
         patch('routes.catalog_routes.catalog_has_more_older', return_value=False), \
         patch('services.sync_jobs.enrich_media_list_for_display'), \
         patch('services.user_media_sync.ensure_user_media_fresh', return_value=False):
        latest = client.get(
            '/latest/movies?hide_lists=0&hide_watched=0&match_only=0'
        ).get_data(as_text=True)
    assert latest.count('href="/help/latest_movies"') >= 1
    assert 'Filter this page…' in latest
    assert 'Search titles in this list' not in latest
    assert 'By default: <strong>recent years</strong>' not in latest
    assert 'official /updates API' not in latest

    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        mine = client.get('/my/movies?lists_set=1&lists=watchlist&filter=lists').get_data(
            as_text=True
        )
    assert 'href="/help/my_movies"' in mine
    assert 'Filter this page…' in mine
    assert 'Search titles in this list' not in mine
    assert 'watch history alone never adds' not in mine


def test_page_help_topics_render(app, client, user):
    login_client(client, app, user)
    for topic in (
        'search', 'latest_movies', 'latest_shows',
        'recommended_movies', 'recommended_shows',
        'my_movies', 'my_shows', 'release_alerts',
        'preferences', 'series_progress', 'overview', 'wishlist',
    ):
        resp = client.get(f'/help/{topic}')
        assert resp.status_code == 200, topic


def test_recs_use_filter_this_page(app, client, user):
    login_client(client, app, user)
    with patch('services.user_media_sync.ensure_user_media_fresh', return_value=False), \
         patch('services.trakt_cache.load_recommendations_cache', return_value=[]), \
         patch('services.sync_jobs.enrich_media_list_for_display'):
        html = client.get('/recommendations/movies').get_data(as_text=True)
    assert 'href="/help/recommended_movies"' in html
    assert 'Filter this page…' in html
    assert 'Personalized picks from Trakt' not in html
