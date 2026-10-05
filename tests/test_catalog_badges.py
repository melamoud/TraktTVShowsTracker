"""Nav badges for Latest / Recs: matches (purple) over remaining pile."""

import json
from datetime import datetime, timedelta
from unittest.mock import patch

from models import (
    CachedMedia, ReviewMarker, User, UserListMembership, UserMediaState,
    UserPreference, db,
)
from services.catalog_badges import catalog_badge_labels, catalog_nav_badges, invalidate_catalog_badges
from services.streaming_matcher import discovery_year_cutoff
from services.trakt_cache import save_recommendations_cache
from tests.conftest import login_client


def _user(user_id):
    return db.session.get(User, user_id)


def _set_genres(user_id, genres, excluded=None):
    prefs = UserPreference.query.filter_by(user_id=user_id).one()
    prefs.genres_json = json.dumps(genres)
    if excluded is not None:
        prefs.excluded_genres_json = json.dumps(excluded)
    db.session.commit()


def _movie(trakt_id, *, title=None, genres=None, year=None, listed=None, overview=''):
    if year is None:
        year = discovery_year_cutoff()
    return CachedMedia(
        media_type='movie',
        trakt_id=trakt_id,
        title=title or f'Movie {trakt_id}',
        year=year,
        overview=overview,
        genres_json=json.dumps(genres or []),
        trakt_listed_at=listed or datetime(2026, 10, 4, 12, 0, 0),
        feed_source='trakt_db_updates',
    )


def _show(trakt_id, *, title=None, genres=None, year=None, listed=None):
    if year is None:
        year = discovery_year_cutoff()
    return CachedMedia(
        media_type='show',
        trakt_id=trakt_id,
        title=title or f'Show {trakt_id}',
        year=year,
        genres_json=json.dumps(genres or []),
        trakt_listed_at=listed or datetime(2026, 10, 4, 12, 0, 0),
        feed_source='trakt_db_updates',
    )


def _rec_entry(media_type, trakt_id, title='Rec'):
    return {media_type: {'title': title, 'year': discovery_year_cutoff(), 'ids': {'trakt': trakt_id}}}


def test_latest_badge_is_purple_over_all_remaining(app, user):
    """x is matches; y is the whole unreviewed pile, not matches-only."""
    with app.app_context():
        invalidate_catalog_badges()
        _set_genres(user, ['Drama'])
        now = datetime(2026, 10, 4, 18, 0, 0)
        db.session.add(_movie(1, title='Drama Hit', genres=['Drama'], listed=now))
        db.session.add(_movie(2, title='Comedy Skip', genres=['Comedy'], listed=now - timedelta(hours=1)))
        db.session.commit()
        badges = catalog_nav_badges(_user(user))
        row = badges['latest_movies']
        assert row['matches'] == 1
        assert row['remaining'] == 2
        assert row['label'] == '1/2'


def test_latest_marker_excludes_reviewed_from_y(app, user):
    with app.app_context():
        invalidate_catalog_badges()
        _set_genres(user, ['Drama'])
        now = datetime(2026, 10, 4, 18, 0, 0)
        db.session.add(_movie(10, title='Newest', genres=['Drama'], listed=now))
        db.session.add(_movie(11, title='Marker', genres=['Drama'], listed=now - timedelta(hours=1)))
        db.session.add(_movie(12, title='Older', genres=['Comedy'], listed=now - timedelta(hours=2)))
        db.session.add(ReviewMarker(
            user_id=user, media_type='movie', trakt_id=11,
            trakt_listed_at=now - timedelta(hours=1), title='Marker',
        ))
        db.session.commit()
        row = catalog_nav_badges(_user(user))['latest_movies']
        assert row['remaining'] == 1
        assert row['matches'] == 1
        assert row['label'] == '1/1'


def test_latest_marker_same_timestamp_counts_only_rows_above(app, user):
    """Badge uses the marker timestamp cutoff, then drops same-second rows under it."""
    with app.app_context():
        invalidate_catalog_badges()
        _set_genres(user, ['Drama'])
        ts = datetime(2026, 10, 4, 12, 0, 0)
        db.session.add(_movie(1, title='Below Tie', listed=ts))
        db.session.add(_movie(2, title='Marker', listed=ts))
        db.session.add(_movie(3, title='Above Tie', genres=['Drama'], listed=ts))
        db.session.add(_movie(4, title='Older', genres=['Drama'], listed=ts - timedelta(hours=1)))
        db.session.add(_movie(5, title='Newer', genres=['Drama'], listed=ts + timedelta(hours=1)))
        db.session.add(ReviewMarker(
            user_id=user, media_type='movie', trakt_id=2,
            trakt_listed_at=ts, title='Marker',
        ))
        db.session.commit()
        row = catalog_nav_badges(_user(user))['latest_movies']
        assert row['remaining'] == 2
        assert row['matches'] == 2


def test_latest_watched_and_lists_excluded_from_y(app, user):
    with app.app_context():
        invalidate_catalog_badges()
        _set_genres(user, ['Drama'])
        now = datetime(2026, 10, 4, 18, 0, 0)
        db.session.add(_movie(21, title='Keep', genres=['Drama'], listed=now))
        db.session.add(_movie(22, title='Watched', genres=['Drama'], listed=now - timedelta(hours=1)))
        db.session.add(_movie(23, title='Listed', genres=['Comedy'], listed=now - timedelta(hours=2)))
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=22, watched=True,
        ))
        db.session.add(UserListMembership(
            user_id=user, media_type='movie', trakt_id=23, list_id='99',
        ))
        db.session.commit()
        row = catalog_nav_badges(_user(user))['latest_movies']
        assert row['remaining'] == 1
        assert row['matches'] == 1


def test_latest_old_year_excluded_from_y(app, user):
    with app.app_context():
        invalidate_catalog_badges()
        _set_genres(user, ['Drama'])
        db.session.add(_movie(31, title='Recent', genres=['Drama']))
        db.session.add(_movie(32, title='Ancient', genres=['Drama'], year=1999))
        db.session.commit()
        row = catalog_nav_badges(_user(user))['latest_movies']
        assert row['remaining'] == 1
        assert row['matches'] == 1


def test_latest_excluded_genre_dropped_from_pile(app, user):
    with app.app_context():
        invalidate_catalog_badges()
        _set_genres(user, ['Drama'], excluded=['Horror'])
        db.session.add(_movie(41, title='Drama', genres=['Drama']))
        db.session.add(_movie(42, title='Horror', genres=['Horror']))
        db.session.commit()
        row = catalog_nav_badges(_user(user))['latest_movies']
        assert row['remaining'] == 1
        assert row['matches'] == 1


def test_latest_zero_matches_still_shows_zero_over_y(app, user):
    with app.app_context():
        invalidate_catalog_badges()
        _set_genres(user, ['Drama'])
        db.session.add(_movie(51, title='Comedy', genres=['Comedy']))
        db.session.commit()
        labels = catalog_badge_labels(_user(user))
        assert labels['latest_movies_badge'] == '0/1'


def test_latest_empty_pile_hides_badge(app, user):
    with app.app_context():
        invalidate_catalog_badges()
        labels = catalog_badge_labels(_user(user))
        assert labels['latest_movies_badge'] is None
        assert labels['latest_shows_badge'] is None


def test_page_genre_and_avail_filters_do_not_shrink_badge(app, client, user):
    """Nav counts ignore Matches-only, genre, upcoming/streaming, and search."""
    with app.app_context():
        invalidate_catalog_badges()
        _set_genres(user, ['Drama'])
        db.session.add(_movie(61, title='Drama Hit', genres=['Drama']))
        db.session.add(_movie(62, title='Comedy Skip', genres=['Comedy']))
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.catalog_routes.feed_count', return_value=2), patch(
        'routes.catalog_routes.ensure_catalog_through_marker'
    ), patch('routes.catalog_routes.catalog_has_more_older', return_value=False), patch(
        'services.sync_jobs.enrich_media_list_for_display'
    ), patch('services.user_media_sync.ensure_user_media_fresh', return_value=False), patch(
        'services.trakt_client.get_recommendations'
    ) as recs:
        html = client.get(
            '/latest/movies?genre=Comedy&avail=streaming&q=skip&match_only=1',
        ).get_data(as_text=True)
    recs.assert_not_called()
    assert 'title="Matches / unreviewed"' in html
    assert '>1/2</span>' in html


def test_nav_and_me_show_latest_and_recs_badges(app, client, user):
    with app.app_context():
        invalidate_catalog_badges()
        _set_genres(user, ['Drama'])
        db.session.add(_movie(71, title='Drama Hit', genres=['Drama']))
        db.session.add(_movie(72, title='Comedy Skip', genres=['Comedy']))
        db.session.add(CachedMedia(
            media_type='movie', trakt_id=81, title='Rec Drama',
            year=discovery_year_cutoff(), genres_json='["Drama"]',
        ))
        db.session.add(CachedMedia(
            media_type='movie', trakt_id=82, title='Rec Comedy',
            year=discovery_year_cutoff(), genres_json='["Comedy"]',
        ))
        save_recommendations_cache(user, 'movie', None, [
            _rec_entry('movie', 81, 'Rec Drama'),
            _rec_entry('movie', 82, 'Rec Comedy'),
        ])
        db.session.commit()

    login_client(client, app, user)
    with patch('services.trakt_client.get_recommendations') as recs:
        html = client.get('/').get_data(as_text=True)
        recs.assert_not_called()
    assert 'title="Matches / unreviewed"' in html
    assert 'title="Matches / remaining"' in html
    assert '>1/2</span>' in html

    with patch('services.trakt_client.get_recommendations') as recs:
        me = client.get('/api/v1/me').get_json()
        recs.assert_not_called()
    assert me['user']['latest_movies_matches'] == 1
    assert me['user']['latest_movies_remaining'] == 2
    assert me['user']['recommended_movies_matches'] == 1
    assert me['user']['recommended_movies_remaining'] == 2
    assert 'recommended_shows_remaining' not in me['user']


def test_recs_cache_miss_omits_badge(app, user):
    with app.app_context():
        invalidate_catalog_badges()
        with patch('services.trakt_client.get_recommendations') as recs:
            badges = catalog_nav_badges(_user(user))
            recs.assert_not_called()
        assert badges['recommended_movies'] is None
        assert badges['recommended_shows'] is None


def test_recs_hides_watched_lists_and_wishlist(app, user):
    with app.app_context():
        invalidate_catalog_badges()
        _set_genres(user, ['Drama'])
        year = discovery_year_cutoff()
        for tid, genres in ((91, ['Drama']), (92, ['Drama']), (93, ['Comedy']), (94, ['Drama'])):
            db.session.add(CachedMedia(
                media_type='movie', trakt_id=tid, title=f'Rec {tid}',
                year=year, genres_json=json.dumps(genres),
            ))
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=92, watched=True,
        ))
        db.session.add(UserListMembership(
            user_id=user, media_type='movie', trakt_id=93, list_id='55',
        ))
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=94, on_watchlist=True,
        ))
        save_recommendations_cache(user, 'movie', None, [
            _rec_entry('movie', 91),
            _rec_entry('movie', 92),
            _rec_entry('movie', 93),
            _rec_entry('movie', 94),
        ])
        db.session.commit()
        with patch('services.trakt_client.get_recommendations') as recs:
            row = catalog_nav_badges(_user(user))['recommended_movies']
            recs.assert_not_called()
        assert row['remaining'] == 1
        assert row['matches'] == 1
        assert row['label'] == '1/1'


def test_recs_empty_cache_omits_badge(app, user):
    with app.app_context():
        invalidate_catalog_badges()
        save_recommendations_cache(user, 'movie', None, [])
        db.session.commit()
        assert catalog_nav_badges(_user(user))['recommended_movies'] is None


def test_shows_badge_is_independent_of_movies(app, user):
    with app.app_context():
        invalidate_catalog_badges()
        _set_genres(user, ['Drama'])
        db.session.add(_show(101, title='Show Drama', genres=['Drama']))
        db.session.add(_show(102, title='Show Comedy', genres=['Comedy']))
        db.session.commit()
        badges = catalog_nav_badges(_user(user))
        assert badges['latest_movies'] is None
        assert badges['latest_shows']['label'] == '1/2'
