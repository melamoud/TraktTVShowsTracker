"""Availability chips / filters (upcoming, theater window, streaming)."""

from datetime import date, timedelta
from unittest.mock import patch

from models import CachedMedia, MediaProviderAvailability, UserMediaState, UserPreference, db
from services.availability import (
    availability_chips,
    availability_flags,
    filter_rows_by_avail,
    normalize_avail,
)
from tests.conftest import login_client


def test_availability_flags_buckets():
    today = date(2026, 8, 6)

    class M:
        def __init__(self, released):
            self.released_at = released
            self.providers = []

    far = availability_flags(M(today + timedelta(days=45)), today=today)
    assert far['upcoming'] is True
    assert far['theater'] is False

    soon = availability_flags(M(today + timedelta(days=10)), today=today)
    assert soon['upcoming'] is False
    assert soon['theater'] is True

    recent = availability_flags(M(today - timedelta(days=10)), today=today)
    assert recent['theater'] is True
    assert recent['upcoming'] is False

    old = availability_flags(M(today - timedelta(days=60)), today=today)
    assert old['theater'] is False
    assert old['upcoming'] is False

    edge_up = availability_flags(M(today + timedelta(days=31)), today=today)
    assert edge_up['upcoming'] is True
    edge_th = availability_flags(M(today + timedelta(days=30)), today=today)
    assert edge_th['theater'] is True


def test_availability_chips_streaming_label():
    flags = {
        'upcoming': False,
        'theater': False,
        'streaming': True,
        'on_my_services': True,
        'released_at': None,
    }
    chips = availability_chips(flags)
    assert chips == [{'kind': 'streaming', 'label': 'On your services'}]


def test_filter_rows_by_avail():
    today = date(2026, 8, 6)

    class M:
        def __init__(self, released, providers=None):
            self.released_at = released
            self.providers = providers or []

    rows = [
        {'media': M(today + timedelta(days=60)), 'providers': [], 'my_providers': []},
        {'media': M(today + timedelta(days=5)), 'providers': ['Netflix'], 'my_providers': []},
        {'media': M(today - timedelta(days=100)), 'providers': ['Hulu'], 'my_providers': ['Hulu']},
    ]
    assert normalize_avail('THEATER') == 'theater'
    upcoming = filter_rows_by_avail(rows, 'upcoming')
    assert len(upcoming) == 1
    theater = filter_rows_by_avail(rows, 'theater')
    assert len(theater) == 1
    streaming = filter_rows_by_avail(rows, 'streaming')
    assert len(streaming) == 2


def test_my_movies_avail_theater_filter(app, client, user):
    today = date.today()
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        for tid, released in (
            (1, today + timedelta(days=5)),
            (2, today + timedelta(days=60)),
            (3, today - timedelta(days=90)),
        ):
            db.session.add(UserMediaState(
                user_id=user, media_type='movie', trakt_id=tid, on_watchlist=True,
            ))
            db.session.add(CachedMedia(
                media_type='movie', trakt_id=tid, title=f'Movie {tid}',
                year=2026, released_at=released,
            ))
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get(
            '/my/movies?lists_set=1&lists=watchlist&filter=lists&avail=theater'
        )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'data-trakt-id="1"' in html
    assert 'data-trakt-id="2"' not in html
    assert 'data-trakt-id="3"' not in html
    assert 'avail-theater' in html or 'Theater' in html


def test_my_movies_avail_streaming_filter(app, client, user):
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        m1 = CachedMedia(media_type='movie', trakt_id=10, title='Stream Me', year=2024)
        m2 = CachedMedia(media_type='movie', trakt_id=11, title='No Stream', year=2024)
        db.session.add_all([m1, m2])
        db.session.flush()
        db.session.add(MediaProviderAvailability(
            cached_media_id=m1.id, provider_name='Netflix', offer_type='flatrate',
        ))
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=10, on_watchlist=True,
        ))
        db.session.add(UserMediaState(
            user_id=user, media_type='movie', trakt_id=11, on_watchlist=True,
        ))
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get(
            '/my/movies?lists_set=1&lists=watchlist&filter=lists&avail=streaming'
        )
    html = resp.get_data(as_text=True)
    assert 'data-trakt-id="10"' in html
    assert 'data-trakt-id="11"' not in html
