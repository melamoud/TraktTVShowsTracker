"""Series progress uses Trakt history for watched marks, not progress.completed."""

from unittest.mock import patch

from models import CachedMedia, db
from tests.conftest import login_client


def test_series_progress_prefers_history_over_progress_flags(app, client, user):
    """Episodes in history show as watched even when progress.completed is false."""
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show',
            trakt_id=10494,
            title='True Blood',
            year=2008,
        ))
        db.session.commit()

    # Progress only lists 2 aired eps; metadata has the full season.
    progress = {
        'aired': 2,
        'completed': 0,
        'seasons': [{
            'number': 1,
            'aired': 2,
            'completed': 0,
            'episodes': [
                {'number': 1, 'completed': False},
                {'number': 2, 'completed': False},
            ],
        }],
    }
    seasons_meta = [{
        'number': 1,
        'episodes': [
            {'number': 1, 'title': 'E1', 'ids': {'trakt': 101}, 'first_aired': '2026-01-01T00:00:00.000Z'},
            {'number': 2, 'title': 'E2', 'ids': {'trakt': 102}, 'first_aired': '2026-01-08T00:00:00.000Z'},
            {'number': 3, 'title': 'E3', 'ids': {'trakt': 103}, 'first_aired': '2030-01-01T00:00:00.000Z'},
            {'number': 4, 'title': 'E4', 'ids': {'trakt': 104}, 'first_aired': '2030-01-08T00:00:00.000Z'},
        ],
    }]
    history = [
        {'episode': {'season': 1, 'number': 1, 'ids': {'trakt': 101}}},
        {'episode': {'season': 1, 'number': 2, 'ids': {'trakt': 102}}},
    ]

    login_client(client, app, user)
    with patch('routes.user_routes.trakt_client.get_show_progress', return_value=progress), patch(
        'routes.user_routes.trakt_client.get_show_seasons', return_value=seasons_meta
    ), patch(
        'routes.user_routes.trakt_client.get_show_watch_history', return_value=history
    ), patch(
        'routes.user_routes.trakt_client.get_show_watched_entry', return_value=None
    ):
        resp = client.get('/shows/10494/progress')

    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert '2</strong> / 2 aired' in html
    assert 'Next up:' not in html  # all aired eps watched; E3/E4 future
    assert 'E3' in html and 'E4' in html
    assert 'Airs 2030-01-01 · Not aired yet' in html
    assert 'episode-line' in html
    assert 'btn-watched' in html and '>Watched<' in html
    assert 'btn-watch' in html and '>Watch<' in html


def test_sanitize_episode_ids_strips_nested_plex():
    """Nested plex.guid must not be sent to Trakt history sync."""
    from services.trakt_client import sanitize_episode_ids

    clean = sanitize_episode_ids({
        'trakt': 12949723,
        'tvdb': 1,
        'tmdb': 2,
        'imdb': 'tt1',
        'plex': {'guid': 'plex://episode/1'},
    })
    assert clean == {'trakt': 12949723, 'tvdb': 1, 'tmdb': 2, 'imdb': 'tt1'}


def test_episode_watched_keys_union_history_and_watched_progress():
    """Watched keys come from history + sync/watched plays + progress flags."""
    from services.trakt_client import episode_watched_keys_from_trakt

    keys = episode_watched_keys_from_trakt(
        history=[{'episode': {'season': 1, 'number': 1}}],
        watched_entry={
            'seasons': [{
                'number': 1,
                'episodes': [
                    {'number': 2, 'plays': 1, 'last_watched_at': '2026-01-01T00:00:00.000Z'},
                    {'number': 3, 'plays': 0},
                ],
            }],
        },
        progress={
            'seasons': [{
                'number': 1,
                'episodes': [
                    {'number': 4, 'completed': True, 'stats': {'play_count': 0}},
                ],
            }],
        },
    )
    assert keys == {(1, 1), (1, 2), (1, 4)}


def test_series_progress_specials_do_not_hide_regular_watched(app, client, user):
    """Season 0 specials must not steal next-up or make header counts look empty."""
    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show',
            trakt_id=10494,
            title='True Blood',
            year=2008,
        ))
        db.session.commit()

    progress = {'aired': 14, 'completed': 12, 'seasons': []}
    seasons_meta = [
        {
            'number': 0,
            'episodes': [
                {
                    'number': 1,
                    'title': 'Unaired Pilot',
                    'ids': {'trakt': 1, 'plex': {'guid': 'x'}},
                    'first_aired': '2008-01-01T00:00:00.000Z',
                },
                {
                    'number': 2,
                    'title': 'Special 2',
                    'ids': {'trakt': 2},
                    'first_aired': '2008-01-02T00:00:00.000Z',
                },
            ],
        },
        {
            'number': 1,
            'episodes': [
                {
                    'number': 1,
                    'title': 'Strange Love',
                    'ids': {'trakt': 101},
                    'first_aired': '2008-09-07T00:00:00.000Z',
                },
                {
                    'number': 2,
                    'title': 'The First Taste',
                    'ids': {'trakt': 102},
                    'first_aired': '2008-09-14T00:00:00.000Z',
                },
            ],
        },
        {
            'number': 2,
            'episodes': [
                {
                    'number': 1,
                    'title': 'Nothing But the Blood',
                    'ids': {'trakt': 201},
                    'first_aired': '2009-06-14T00:00:00.000Z',
                },
            ],
        },
    ]
    history = [
        {'episode': {'season': 1, 'number': 1}},
        {'episode': {'season': 1, 'number': 2}},
    ]

    login_client(client, app, user)
    with patch('routes.user_routes.trakt_client.get_show_progress', return_value=progress), patch(
        'routes.user_routes.trakt_client.get_show_seasons', return_value=seasons_meta
    ), patch(
        'routes.user_routes.trakt_client.get_show_watch_history', return_value=history
    ), patch(
        'routes.user_routes.trakt_client.get_show_watched_entry', return_value=None
    ):
        resp = client.get('/shows/10494/progress')

    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    # Regular seasons only in header (2 watched / 3 aired), not specials.
    assert '2</strong> / 3 aired' in html
    assert 'Next up' in html
    assert 'S2E1' in html
    assert 'Specials' in html
    # Specials section exists but is not the open/default focus when S2 needs watching.
    assert html.index('Season 2') < html.index('Specials')
    assert 'open' in html


def test_mark_episode_watched_rejects_silent_noop():
    """HTTP 200 with added.episodes=0 must not look like success."""
    from services.trakt_client import TraktError, mark_episode_watched
    from unittest.mock import MagicMock

    user = MagicMock()
    with patch(
        'services.trakt_client.api_request',
        return_value={'added': {'episodes': 0}, 'not_found': {'episodes': []}},
    ):
        try:
            mark_episode_watched(user, {'trakt': 12949723})
            assert False, 'expected TraktError'
        except TraktError as exc:
            assert 'did not record the watch' in str(exc)


def test_mark_season_watched_posts_season_payload():
    """Season watch uses Trakt show+season history body."""
    from services.trakt_client import mark_season_watched
    from unittest.mock import MagicMock, patch

    user = MagicMock()
    with patch('services.trakt_client.api_request') as api:
        api.return_value = {'added': {'episodes': 8}}
        result = mark_season_watched(user, 1390, 2)
        assert result['added']['episodes'] == 8
        args, kwargs = api.call_args
        assert args[0] == 'POST'
        assert args[1] == '/sync/history'
        body = kwargs['json_body']
        assert body['shows'][0]['ids']['trakt'] == 1390
        assert body['shows'][0]['seasons'][0]['number'] == 2


def test_series_progress_shows_bulk_watch_actions(app, client, user):
    """Incomplete seasons expose Mark season watched; series button when incomplete."""
    from datetime import datetime

    with app.app_context():
        db.session.add(CachedMedia(
            media_type='show', trakt_id=4242, title='Bulk Show',
            trakt_listed_at=datetime.utcnow(),
        ))
        db.session.commit()

    seasons = [{
        'number': 1,
        'episodes': [
            {'number': 1, 'title': 'One', 'first_aired': '2020-01-01T00:00:00.000Z',
             'ids': {'trakt': 1}},
            {'number': 2, 'title': 'Two', 'first_aired': '2020-01-08T00:00:00.000Z',
             'ids': {'trakt': 2}},
        ],
    }]
    progress = {'seasons': [{'number': 1, 'episodes': [
        {'number': 1}, {'number': 2},
    ]}]}

    with patch('routes.user_routes.trakt_client.get_show_progress', return_value=progress), \
         patch('routes.user_routes.trakt_client.get_show_seasons', return_value=seasons), \
         patch('routes.user_routes.trakt_client.get_show_watch_history', return_value=[]), \
         patch('routes.user_routes.trakt_client.get_show_watched_entry', return_value=None), \
         patch('routes.user_routes.trakt_client.episode_watched_keys_from_trakt', return_value=set()):
        login_client(client, app, user)
        resp = client.get('/shows/4242/progress')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert 'Mark season watched' in html
    assert 'Mark series watched' in html
    assert 'next-up' in html
    assert 'S1E1' in html
    assert 'One' in html