"""Trakt-wide /search page and in-list title filter tests."""

from unittest.mock import patch

from models import CachedMedia, UserListMembership, UserMediaState, UserPreference, db
from tests.conftest import login_client


def test_search_page_prompts_without_query(app, client, user):
    login_client(client, app, user)
    resp = client.get('/search')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Type a title' in html
    assert 'class="media-list"' not in html
    assert 'data-action="lists-edit"' not in html
    assert 'search-select' not in html
    assert 'class="pill on"' in html
    assert '>Movies</' in html
    assert '>Shows</' in html
    assert 'class="active"' in html
    assert 'aria-current="page"' in html
    assert '>Search</a>' in html
    assert 'id="adv-year"' in html
    assert 'name="genre"' in html
    assert 'More filters' in html
    assert 'name="actor_q"' in html


def test_search_year_and_genre_filter_trakt_hits(app, client, user):
    """Year range + genre OR filter Trakt title hits locally."""
    login_client(client, app, user)

    def fake_search(_user, media_type, query, *, limit=20):
        return [
            {
                'type': 'movie', 'score': 3,
                'movie': {
                    'title': 'Old Drama', 'year': 2010, 'genres': ['drama'],
                    'ids': {'trakt': 21},
                },
            },
            {
                'type': 'movie', 'score': 2,
                'movie': {
                    'title': 'New Action', 'year': 2018, 'genres': ['action'],
                    'ids': {'trakt': 22},
                },
            },
            {
                'type': 'movie', 'score': 1,
                'movie': {
                    'title': 'New Drama', 'year': 2019, 'genres': ['drama'],
                    'ids': {'trakt': 23},
                },
            },
        ]

    with patch('services.user_media_sync.ensure_user_media_fresh', return_value=False), \
         patch('services.trakt_client.search_titles', side_effect=fake_search), \
         patch('services.sync_jobs.enrich_media_list_for_display', return_value=[]), \
         patch('services.sync_jobs.sync_providers_for_media', return_value=[]):
        resp = client.get(
            '/search?q=film&type=movie&hide_watched=0&hide_lists=0'
            '&year=2015-2020&genre=drama'
        )

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'data-trakt-id="23"' in html
    assert 'data-trakt-id="21"' not in html
    assert 'data-trakt-id="22"' not in html


def test_search_remembers_year_and_genres(app, client, user):
    login_client(client, app, user)

    def fake_search(_user, media_type, query, *, limit=20):
        return [{
            'type': 'movie', 'score': 1,
            'movie': {'title': 'Solo', 'year': 2018, 'genres': ['action'], 'ids': {'trakt': 31}},
        }]

    with patch('services.user_media_sync.ensure_user_media_fresh', return_value=False), \
         patch('services.trakt_client.search_titles', side_effect=fake_search), \
         patch('services.sync_jobs.enrich_media_list_for_display', return_value=[]), \
         patch('services.sync_jobs.sync_providers_for_media', return_value=[]):
        client.get('/search?q=solo&type=movie&year=2018&genre=action&genres_set=1')
        resp = client.get('/search?q=solo&type=movie')

    html = resp.get_data(as_text=True)
    assert 'value="2018"' in html
    assert 'value="action"' in html and 'checked' in html


def test_latest_year_genre_filter_without_title_q(app, client, user):
    """In-list Latest can narrow by year/genre with no title search."""
    from datetime import datetime
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='movie', trakt_id=41, title='Keep Me', year=2018,
            genres_json='["drama"]', trakt_listed_at=datetime(2026, 8, 1),
            feed_source='trakt_db_updates',
        ))
        db.session.add(CachedMedia(
            media_type='movie', trakt_id=42, title='Drop Me', year=2010,
            genres_json='["drama"]', trakt_listed_at=datetime(2026, 8, 2),
            feed_source='trakt_db_updates',
        ))
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.catalog_routes.feed_count', return_value=2), \
         patch('routes.catalog_routes.ensure_catalog_through_marker'), \
         patch('routes.catalog_routes.catalog_has_more_older', return_value=False), \
         patch('services.sync_jobs.enrich_media_list_for_display'), \
         patch('services.user_media_sync.ensure_user_media_fresh', return_value=False):
        resp = client.get(
            '/latest/movies?hide_lists=0&hide_watched=0&match_only=0'
            '&recent_years=0&year=2015-2020&genre=drama'
        )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'data-trakt-id="41"' in html
    assert 'data-trakt-id="42"' not in html
    assert 'More filters' in html


def test_search_type_pills_toggle_movies_and_shows(app, client, user):
    """Movies + Shows pills sit with other filters; both on means type=both."""
    login_client(client, app, user)

    def fake_search(_user, media_type, query, *, limit=20):
        if media_type == 'movie':
            return [{
                'type': 'movie', 'score': 1,
                'movie': {'title': 'Solo Movie', 'year': 2024, 'ids': {'trakt': 11}},
            }]
        return [{
            'type': 'show', 'score': 1,
            'show': {'title': 'Solo Show', 'year': 2024, 'ids': {'trakt': 12}},
        }]

    with patch('services.user_media_sync.ensure_user_media_fresh', return_value=False), \
         patch('services.trakt_client.search_titles', side_effect=fake_search), \
         patch('services.sync_jobs.enrich_media_list_for_display', return_value=[]), \
         patch('services.sync_jobs.sync_providers_for_media', return_value=[]):
        both = client.get('/search?q=solo&type=both&hide_watched=0&hide_lists=0')
        movies = client.get('/search?q=solo&type=movie&hide_watched=0&hide_lists=0')
        shows = client.get('/search?q=solo&type=show&hide_watched=0&hide_lists=0')

    both_html = both.get_data(as_text=True)
    assert 'data-trakt-id="11"' in both_html
    assert 'data-trakt-id="12"' in both_html
    assert 'type=show' in both_html  # Movies pill turns off → shows only
    assert 'type=movie' in both_html  # Shows pill turns off → movies only

    movies_html = movies.get_data(as_text=True)
    assert 'data-trakt-id="11"' in movies_html
    assert 'data-trakt-id="12"' not in movies_html
    assert 'type=both' in movies_html  # Shows pill adds shows back

    shows_html = shows.get_data(as_text=True)
    assert 'data-trakt-id="12"' in shows_html
    assert 'data-trakt-id="11"' not in shows_html
    assert 'type=both' in shows_html  # Movies pill adds movies back


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
    assert 'Set lists' in html
    assert 'Not watched' in html
    assert 'Not in lists' in html
    assert 'trakt.tv/shows/' in html
    assert '>Trakt</a>' in html


def test_search_hides_watched_and_list_titles_by_default(app, client, user):
    """Default Search filters drop watched, wishlist, and personal-list hits."""
    with app.app_context():
        db.session.add(UserMediaState(
            user_id=user, media_type='show', trakt_id=1, watched=True,
        ))
        db.session.add(UserMediaState(
            user_id=user, media_type='show', trakt_id=2, on_watchlist=True,
        ))
        db.session.add(UserMediaState(
            user_id=user, media_type='show', trakt_id=3, on_watchlist=False,
        ))
        db.session.add(UserListMembership(
            user_id=user, list_id='10', media_type='show', trakt_id=3,
        ))
        db.session.commit()

    def fake_search(_user, media_type, query, *, limit=20):
        assert media_type == 'show'
        return [
            {
                'type': 'show', 'score': 100,
                'show': {'title': 'Watched Show', 'year': 2020, 'ids': {'trakt': 1}},
            },
            {
                'type': 'show', 'score': 90,
                'show': {'title': 'Wishlist Show', 'year': 2021, 'ids': {'trakt': 2}},
            },
            {
                'type': 'show', 'score': 80,
                'show': {'title': 'Personal List Show', 'year': 2022, 'ids': {'trakt': 3}},
            },
            {
                'type': 'show', 'score': 70,
                'show': {'title': 'Fresh Show', 'year': 2023, 'ids': {'trakt': 4}},
            },
        ]

    login_client(client, app, user)
    with patch('services.user_media_sync.ensure_user_media_fresh', return_value=False), \
         patch('services.trakt_client.search_titles', side_effect=fake_search), \
         patch('services.sync_jobs.enrich_media_list_for_display', return_value=[]), \
         patch('services.sync_jobs.sync_providers_for_media', return_value=[]), \
         patch('routes.catalog_routes.trakt_client.get_personal_lists', return_value=[
             {'id': '10', 'name': 'Favs', 'slug': 'favs'},
         ]):
        hidden = client.get('/search?q=show&type=show')
        shown = client.get('/search?q=show&type=show&hide_watched=0&hide_lists=0')

    assert hidden.status_code == 200
    hidden_html = hidden.get_data(as_text=True)
    assert 'data-trakt-id="4"' in hidden_html
    assert 'Fresh Show' in hidden_html
    assert 'data-trakt-id="1"' not in hidden_html
    assert 'data-trakt-id="2"' not in hidden_html
    assert 'data-trakt-id="3"' not in hidden_html

    assert shown.status_code == 200
    shown_html = shown.get_data(as_text=True)
    assert 'data-trakt-id="1"' in shown_html
    assert 'data-trakt-id="2"' in shown_html
    assert 'data-trakt-id="3"' in shown_html
    assert 'data-trakt-id="4"' in shown_html


def test_search_remembers_filter_prefs(app, client, user):
    """Toggling Show watched persists for the next Search visit without args."""
    login_client(client, app, user)

    def fake_search(_user, media_type, query, *, limit=20):
        return [{
            'type': 'movie', 'score': 1,
            'movie': {'title': 'Solo', 'year': 2024, 'ids': {'trakt': 9}},
        }]

    with patch('services.user_media_sync.ensure_user_media_fresh', return_value=False), \
         patch('services.trakt_client.search_titles', side_effect=fake_search), \
         patch('services.sync_jobs.enrich_media_list_for_display', return_value=[]), \
         patch('services.sync_jobs.sync_providers_for_media', return_value=[]):
        client.get('/search?q=solo&type=movie&hide_watched=0&hide_lists=1')
        resp = client.get('/search?q=solo&type=movie')

    html = resp.get_data(as_text=True)
    assert 'Showing watched' in html
    assert 'Not in lists' in html


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


def test_my_shows_q_backfills_missing_cached_media(app, client, user):
    """Title search must backfill CachedMedia before filtering (not only after page)."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        db.session.add(UserMediaState(
            user_id=user, media_type='show', trakt_id=195475, on_watchlist=True,
        ))
        # Intentionally no CachedMedia row — mirrors stale sync / state-only rows.
        db.session.commit()

    def fake_ensure(media_type, trakt_ids):
        assert media_type == 'show'
        if 195475 in (trakt_ids or []):
            if not CachedMedia.query.filter_by(media_type='show', trakt_id=195475).first():
                db.session.add(CachedMedia(
                    media_type='show', trakt_id=195475, title='The Ark', year=2023,
                ))
                db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached', side_effect=fake_ensure), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get(
            '/my/shows?lists_set=1&lists=watchlist&filter=lists&q=ark'
        )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'data-trakt-id="195475"' in html
    assert 'The Ark' in html


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


def test_search_by_actor_id_uses_filmography_not_title_search(app, client, user):
    """Actor id loads Trakt cast credits and keeps Search filters."""
    from models import CachedPerson

    with app.app_context():
        db.session.add(CachedPerson(trakt_id=501, name='Ada Actor'))
        db.session.commit()

    def fake_credits(_user, person_id, media_type, *, limit=80):
        assert person_id == 501
        if media_type != 'movie':
            return []
        return [{
            'movie': {
                'title': 'Ada Film', 'year': 2021, 'genres': ['drama'],
                'ids': {'trakt': 77},
            },
        }]

    login_client(client, app, user)
    with patch('services.user_media_sync.ensure_user_media_fresh', return_value=False), \
         patch('services.trakt_client.search_titles') as title_search, \
         patch('services.trakt_client.fetch_person_cast_titles', side_effect=fake_credits), \
         patch('services.sync_jobs.enrich_media_list_for_display', return_value=[]), \
         patch('services.sync_jobs.sync_providers_for_media', return_value=[]):
        resp = client.get('/search?actor=501&type=movie&hide_watched=0&hide_lists=0')

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Ada Film' in html
    assert 'data-trakt-id="77"' in html
    assert 'for actor' in html and 'Ada Actor' in html
    title_search.assert_not_called()


def test_search_actor_q_matches_favorite_then_filters_year(app, client, user):
    """Typed actor name uses a favorite; year filter still applies."""
    from models import CachedPerson, UserFavoriteActor

    with app.app_context():
        person = CachedPerson(trakt_id=501, name='Ada Actor')
        db.session.add(person)
        db.session.flush()
        db.session.add(UserFavoriteActor(user_id=user, person_id=person.id))
        db.session.commit()

    def fake_credits(_user, person_id, media_type, *, limit=80):
        assert person_id == 501
        if media_type != 'movie':
            return []
        return [
            {
                'movie': {
                    'title': 'Old Ada', 'year': 2010, 'genres': ['drama'],
                    'ids': {'trakt': 81},
                },
            },
            {
                'movie': {
                    'title': 'New Ada', 'year': 2019, 'genres': ['drama'],
                    'ids': {'trakt': 82},
                },
            },
        ]

    login_client(client, app, user)
    with patch('services.user_media_sync.ensure_user_media_fresh', return_value=False), \
         patch('services.trakt_client.search_people') as people_search, \
         patch('services.trakt_client.fetch_person_cast_titles', side_effect=fake_credits), \
         patch('services.sync_jobs.enrich_media_list_for_display', return_value=[]), \
         patch('services.sync_jobs.sync_providers_for_media', return_value=[]):
        resp = client.get(
            '/search?actor_q=Ada+Actor&type=movie&hide_watched=0&hide_lists=0&year=2015-2020'
        )

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'data-trakt-id="82"' in html
    assert 'data-trakt-id="81"' not in html
    people_search.assert_not_called()


def test_latest_page_has_actor_search_jump(app, client, user):
    """List pages expose actor fields that post to the main Search page."""
    login_client(client, app, user)
    with patch('routes.catalog_routes.feed_count', return_value=0), \
         patch('routes.catalog_routes.ensure_catalog_through_marker'), \
         patch('routes.catalog_routes.catalog_has_more_older', return_value=False), \
         patch('services.sync_jobs.enrich_media_list_for_display'), \
         patch('services.user_media_sync.ensure_user_media_fresh', return_value=False):
        resp = client.get('/latest/movies?hide_lists=0&hide_watched=0&match_only=0')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'name="actor_q"' in html
    assert 'Search actor' in html
    assert '/search' in html


def test_search_second_load_uses_local_cache(app, client, user):
    """Repeating the same Search URL (browser Back) must not call Trakt again."""
    login_client(client, app, user)

    def fake_search(_user, media_type, query, *, limit=20):
        if media_type != 'movie':
            return []
        return [{
            'type': 'movie', 'score': 1,
            'movie': {'title': 'Cached Hit', 'year': 2024, 'ids': {'trakt': 91}},
        }]

    with patch('services.user_media_sync.ensure_user_media_fresh', return_value=False), \
         patch('services.trakt_client.search_titles', side_effect=fake_search) as title_search, \
         patch('services.sync_jobs.enrich_media_list_for_display', return_value=[]), \
         patch('services.sync_jobs.sync_providers_for_media', return_value=[]):
        first = client.get('/search?q=cached&type=movie&hide_watched=0&hide_lists=0')
        second = client.get('/search?q=cached&type=movie&hide_watched=0&hide_lists=0')

    assert first.status_code == 200
    assert second.status_code == 200
    assert 'data-trakt-id="91"' in second.get_data(as_text=True)
    assert title_search.call_count == 1


def test_search_refresh_bypasses_cache(app, client, user):
    """refresh=1 re-fetches Trakt even when the search cache is fresh."""
    login_client(client, app, user)

    def fake_search(_user, media_type, query, *, limit=20):
        return [{
            'type': 'movie', 'score': 1,
            'movie': {'title': 'Fresh Hit', 'year': 2024, 'ids': {'trakt': 92}},
        }] if media_type == 'movie' else []

    with patch('services.user_media_sync.ensure_user_media_fresh', return_value=False), \
         patch('services.trakt_client.search_titles', side_effect=fake_search) as title_search, \
         patch('services.sync_jobs.enrich_media_list_for_display', return_value=[]), \
         patch('services.sync_jobs.sync_providers_for_media', return_value=[]):
        client.get('/search?q=fresh&type=movie&hide_watched=0&hide_lists=0')
        client.get('/search?q=fresh&type=movie&hide_watched=0&hide_lists=0&refresh=1')

    assert title_search.call_count == 2

