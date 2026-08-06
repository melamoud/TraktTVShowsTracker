"""Trakt-wide /search page and in-list title filter tests."""

from unittest.mock import patch

from models import CachedMedia, UserMediaState, UserPreference, db
from tests.conftest import login_client


def test_search_page_prompts_without_query(app, client, user):
    login_client(client, app, user)
    resp = client.get('/search')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Type at least 2 characters' in html
    assert 'class="media-list"' not in html
    assert 'data-action="lists-edit"' not in html


def test_search_page_renders_multiple_results(app, client, user):
    """Exact + broad hits are decorated into media-row cards with list actions."""
    login_client(client, app, user)

    def fake_search(_user, media_type, query, *, limit=20):
        assert query == 'boys'
        if media_type != 'show':
            return []
        return [
            {
                'type': 'show',
                'score': 100,
                'show': {
                    'title': 'The Boys',
                    'year': 2019,
                    'overview': 'Superheroes go bad.',
                    'genres': ['action', 'drama'],
                    'ids': {'trakt': 1390, 'tmdb': 76479, 'slug': 'the-boys'},
                },
            },
            {
                'type': 'show',
                'score': 80,
                'show': {
                    'title': 'Boys Over Flowers',
                    'year': 2009,
                    'overview': 'Romance.',
                    'genres': ['drama'],
                    'ids': {'trakt': 1400, 'tmdb': 1, 'slug': 'boys-over-flowers'},
                },
            },
        ]

    with patch('routes.catalog_routes.ensure_user_media_fresh', create=True), \
         patch('services.user_media_sync.ensure_user_media_fresh', return_value=False), \
         patch('services.trakt_client.search_titles', side_effect=fake_search), \
         patch('services.sync_jobs.enrich_media_list_for_display', return_value=[]), \
         patch('services.sync_jobs.sync_providers_for_media', return_value=[]):
        resp = client.get('/search?q=boys&type=show')

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'The Boys' in html
    assert 'Boys Over Flowers' in html
    assert 'data-trakt-id="1390"' in html
    assert 'data-trakt-id="1400"' in html
    assert 'data-action="lists-edit"' in html
    assert 'Add to lists' in html


def test_search_titles_dedupes_exact_before_broad(app, user):
    from services import trakt_client

    exact = [{
        'type': 'movie',
        'score': 1,
        'movie': {'title': 'Exact Hit', 'year': 2024, 'ids': {'trakt': 1}},
    }]
    broad = [
        {
            'type': 'movie',
            'score': 2,
            'movie': {'title': 'Exact Hit', 'year': 2024, 'ids': {'trakt': 1}},
        },
        {
            'type': 'movie',
            'score': 3,
            'movie': {'title': 'Other', 'year': 2020, 'ids': {'trakt': 2}},
        },
    ]
    with app.app_context():
        with patch('services.trakt_client.api_request') as api:
            api.side_effect = [exact, broad]
            from models import User
            u = db.session.get(User, user)
            out = trakt_client.search_titles(u, 'movie', 'exact', limit=20)
    assert [r['movie']['ids']['trakt'] for r in out] == [1, 2]
    assert api.call_count == 2
    assert '/search/movie/exact' in api.call_args_list[0].args[1]
    assert api.call_args_list[1].args[1] == '/search/movie'


def test_my_movies_q_filters_by_title(app, client, user):
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        for tid, title in ((1, 'Alpha Mission'), (2, 'Beta Force'), (3, 'Alpha Squad')):
            db.session.add(UserMediaState(
                user_id=user, media_type='movie', trakt_id=tid, on_watchlist=True,
            ))
            db.session.add(CachedMedia(
                media_type='movie', trakt_id=tid, title=title, year=2024,
            ))
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get('/my/movies?lists_set=1&lists=watchlist&filter=lists&q=alpha')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'data-trakt-id="1"' in html
    assert 'data-trakt-id="3"' in html
    assert 'data-trakt-id="2"' not in html
    assert 'matching “alpha”' in html or 'matching &ldquo;alpha&rdquo;' in html or 'alpha' in html


def test_recommendations_q_filters_by_title(app, client, user):
    login_client(client, app, user)
    fake = [
        {
            'title': 'Night Runner',
            'year': 2024,
            'overview': 'A',
            'genres': ['action'],
            'ids': {'trakt': 1, 'tmdb': 1, 'slug': 'night-runner'},
        },
        {
            'title': 'Day Walker',
            'year': 2023,
            'overview': 'B',
            'genres': ['action'],
            'ids': {'trakt': 2, 'tmdb': 2, 'slug': 'day-walker'},
        },
    ]
    with patch('services.trakt_client.get_recommendations', return_value=fake), \
         patch('services.user_media_sync.ensure_user_media_fresh', return_value=False), \
         patch('services.sync_jobs.enrich_media_list_for_display', return_value=[]), \
         patch('services.sync_jobs.sync_providers_for_media', return_value=[]):
        resp = client.get('/recommendations/movies?hide_wishlist=0&hide_watched=0&q=night')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Night Runner' in html
    assert 'Day Walker' not in html
