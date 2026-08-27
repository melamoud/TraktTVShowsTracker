"""Latest matches-only filter, marker clear/caught-up, prefs wizard/reminder."""

from datetime import datetime, timedelta
from unittest.mock import patch

from models import CachedMedia, ReviewMarker, UserPreference, db
from tests.conftest import login_client


def _add_movie(title, trakt_id, listed, genres=None, overview='', year=2026):
    import json
    return CachedMedia(
        media_type='movie',
        trakt_id=trakt_id,
        title=title,
        year=year,
        overview=overview,
        genres_json=json.dumps(genres or []),
        trakt_listed_at=listed,
        feed_source='trakt_db_updates',
    )


def test_latest_defaults_to_matches_when_prefs_set(app, client, user):
    """With genres set, Latest defaults to matches-only and hides non-matches."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).first()
        prefs.genres_json = '["drama"]'
        db.session.add(_add_movie('Drama Hit', 1, datetime(2026, 8, 3), genres=['Drama']))
        db.session.add(_add_movie('Comedy Skip', 2, datetime(2026, 8, 2), genres=['Comedy']))
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.catalog_routes.feed_count', return_value=2), patch(
        'routes.catalog_routes.ensure_catalog_through_marker'
    ), patch('routes.catalog_routes.catalog_has_more_older', return_value=False), patch(
        'services.sync_jobs.enrich_media_list_for_display'
    ):
        resp = client.get('/latest/movies')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert 'Matches only' in html
    assert 'Drama Hit' in html
    assert 'Comedy Skip' not in html


def test_latest_show_all_includes_non_matches(app, client, user):
    """match_only=0 shows the full feed."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).first()
        prefs.genres_json = '["drama"]'
        db.session.add(_add_movie('Drama Hit', 1, datetime(2026, 8, 3), genres=['Drama']))
        db.session.add(_add_movie('Comedy Skip', 2, datetime(2026, 8, 2), genres=['Comedy']))
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.catalog_routes.feed_count', return_value=2), patch(
        'routes.catalog_routes.ensure_catalog_through_marker'
    ), patch('routes.catalog_routes.catalog_has_more_older', return_value=False), patch(
        'services.sync_jobs.enrich_media_list_for_display'
    ):
        resp = client.get('/latest/movies?match_only=0')
    html = resp.data.decode('utf-8')
    assert 'Drama Hit' in html
    assert 'Comedy Skip' in html
    assert 'All titles' in html


def test_latest_show_all_hides_excluded_genre(app, client, user):
    """Hide-genre blocklist applies even when Matches only is off."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).first()
        prefs.genres_json = '["drama"]'
        prefs.excluded_genres_json = '["animation"]'
        db.session.add(_add_movie(
            'Drawn Drama', 1, datetime(2026, 8, 3), genres=['Drama', 'Animation'],
        ))
        db.session.add(_add_movie('Live Drama', 2, datetime(2026, 8, 2), genres=['Drama']))
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.catalog_routes.feed_count', return_value=2), patch(
        'routes.catalog_routes.ensure_catalog_through_marker'
    ), patch('routes.catalog_routes.catalog_has_more_older', return_value=False), patch(
        'services.sync_jobs.enrich_media_list_for_display'
    ):
        resp = client.get('/latest/movies?match_only=0')
    html = resp.data.decode('utf-8')
    assert 'Live Drama' in html
    assert 'Drawn Drama' not in html


def test_prefs_save_excluded_genre_wins_overlap(app, client, user):
    """A genre in both lists is kept only on the hide list."""
    login_client(client, app, user)
    resp = client.post(
        '/preferences',
        data={
            'genre_checks': ['drama', 'animation'],
            'exclude_genre_checks': 'animation',
            'keywords': 'heist',
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        import json
        liked = [x.lower() for x in json.loads(prefs.genres_json or '[]')]
        hidden = [x.lower() for x in json.loads(prefs.excluded_genres_json or '[]')]
        assert 'drama' in liked
        assert 'animation' not in liked
        assert 'animation' in hidden


def test_latest_recent_years_hides_old_production_year(app, client, user):
    """Default recent-years filter drops old titles even when they match genres."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).first()
        prefs.genres_json = '["drama"]'
        db.session.add(_add_movie('New Drama', 1, datetime(2026, 8, 3), genres=['Drama'], year=2026))
        db.session.add(_add_movie('Old Drama', 2, datetime(2026, 8, 3), genres=['Drama'], year=1999))
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.catalog_routes.feed_count', return_value=2), patch(
        'routes.catalog_routes.ensure_catalog_through_marker'
    ), patch('routes.catalog_routes.catalog_has_more_older', return_value=False), patch(
        'services.sync_jobs.enrich_media_list_for_display'
    ):
        resp = client.get('/latest/movies')
    html = resp.data.decode('utf-8')
    assert 'New Drama' in html
    assert 'Old Drama' not in html

    with patch('routes.catalog_routes.feed_count', return_value=2), patch(
        'routes.catalog_routes.ensure_catalog_through_marker'
    ), patch('routes.catalog_routes.catalog_has_more_older', return_value=False), patch(
        'services.sync_jobs.enrich_media_list_for_display'
    ):
        resp = client.get('/latest/movies?recent_years=0')
    html = resp.data.decode('utf-8')
    assert 'Old Drama' in html


def test_discovery_year_cutoff_rules():
    """Jan–Jun includes prior year; Jul–Dec is current year only."""
    from datetime import date
    from services.streaming_matcher import discovery_year_cutoff

    assert discovery_year_cutoff(date(2026, 3, 1)) == 2025
    assert discovery_year_cutoff(date(2026, 8, 1)) == 2026


def test_review_marker_clear_and_caught_up(app, client, user):
    """Clear removes markers; caught-up sets marker on newest feed title."""
    with app.app_context():
        db.session.add(_add_movie('Newest', 10, datetime(2026, 8, 3)))
        db.session.add(_add_movie('Older', 9, datetime(2026, 8, 1)))
        db.session.add(ReviewMarker(
            user_id=user, media_type='movie', trakt_id=9,
            title='Older', trakt_listed_at=datetime(2026, 8, 1),
        ))
        db.session.commit()

    login_client(client, app, user)
    resp = client.post('/api/review-marker/movie/clear', json={})
    assert resp.status_code == 200
    with app.app_context():
        assert ReviewMarker.query.filter_by(user_id=user, media_type='movie').count() == 0

    resp = client.post('/api/review-marker/movie/caught-up', json={})
    assert resp.status_code == 200
    with app.app_context():
        marker = ReviewMarker.query.filter_by(user_id=user, media_type='movie').one()
        assert marker.trakt_id == 10
        assert marker.title == 'Newest'


def test_preferences_setup_requires_genre_or_keyword(app, client, user):
    """Wizard save without filters is rejected; with a genre succeeds."""
    login_client(client, app, user)
    resp = client.post('/preferences/setup', data={'action': 'save'}, follow_redirects=False)
    assert resp.status_code == 302
    assert '/preferences/setup' in (resp.headers.get('Location') or '')

    resp = client.post(
        '/preferences/setup',
        data={'action': 'save', 'genre_checks': 'drama'},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert '/latest/movies' in (resp.headers.get('Location') or '')
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        assert 'drama' in (prefs.genres_json or '').lower()
        assert prefs.onboarding_completed_at is not None


def test_prefs_reminder_snooze(app, client, user):
    """Snooze hides the reminder for a day."""
    login_client(client, app, user)
    resp = client.post('/api/prefs-reminder', json={'action': 'snooze'})
    assert resp.status_code == 200
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        assert prefs.prefs_reminder_snooze_until is not None
        assert prefs.prefs_reminder_snooze_until > datetime.utcnow() + timedelta(hours=20)


def test_prefs_change_prompts_marker_reset(app, client, user):
    """Changing keywords redirects with marker_prompt."""
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).first()
        prefs.keywords_json = '["old"]'
        db.session.commit()

    login_client(client, app, user)
    resp = client.post(
        '/preferences',
        data={'keywords': 'heist, space'},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert 'marker_prompt=1' in (resp.headers.get('Location') or '')
