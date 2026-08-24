"""My Shows cache job: calendar-derived last-aired, seeds, 429 abort, views."""

from datetime import date, datetime, timedelta
from unittest.mock import patch

from models import (
    UserCalendarEvent, UserListMembership, UserMediaState, UserPreference, db,
)
from services.shows_cache import (
    queue_user_media_cycle,
    refresh_shows_cache_for_user,
    seed_new_shows_inline,
)
from services.trakt_client import TraktError
from tests.conftest import login_client


def _show(user_id, tid, **kw):
    defaults = {'on_watchlist': True, 'media_type': 'show', 'trakt_id': tid}
    defaults.update(kw)
    db.session.add(UserMediaState(user_id=user_id, **defaults))


def _cal_event(user_id, tid, day, season=None, episode=None, title=None):
    db.session.add(UserCalendarEvent(
        user_id=user_id, media_type='show', trakt_id=tid,
        event_date=day, season_number=season, episode_number=episode,
        episode_title=title,
    ))


def _list_show(user_id, tid, **kw):
    """Show on a personal list (not watchlist) — no my-calendar coverage."""
    _show(user_id, tid, on_watchlist=False, **kw)
    db.session.add(UserListMembership(
        user_id=user_id, list_id='lst1', media_type='show', trakt_id=tid,
    ))


def test_refresh_derives_last_aired_from_calendar_rows(app, user):
    """Watchlisted show with calendar rows: date comes from cache, no API call."""
    with app.app_context():
        _show(user, 1)
        _cal_event(user, 1, date.today() - timedelta(days=2), 3, 4, 'The Old One')
        _cal_event(user, 1, date.today() - timedelta(days=9), 3, 3, 'Earlier')
        _cal_event(user, 1, date.today() + timedelta(days=5), 3, 5, 'Future Ep')
        db.session.commit()
        with patch(
            'services.shows_cache.trakt_client.get_show_seasons',
            side_effect=AssertionError('must not hit Trakt'),
        ), patch(
            'services.shows_cache.refresh_show_progress_for_ids', return_value=0,
        ):
            stats = refresh_shows_cache_for_user(_reload_user(user))
        st = UserMediaState.query.filter_by(
            user_id=user, media_type='show', trakt_id=1,
        ).one()
        assert stats['calendar'] == 1
        assert st.last_episode_aired_at.date() == date.today() - timedelta(days=2)
        assert st.last_episode_label == 'S03E04 · The Old One'


def test_refresh_does_not_use_todays_calendar_as_last_aired(app, user):
    """Date-only today would count a 9pm ET episode all afternoon."""
    from services.local_time import local_today

    with app.app_context():
        today = local_today()
        _show(user, 1, last_episode_aired_at=datetime(2026, 8, 17, 1, 0, 0))
        _cal_event(user, 1, today, 1, 2, 'Tonight')
        db.session.commit()
        with patch(
            'services.shows_cache.trakt_client.get_show_seasons',
            return_value=[{
                'number': 1,
                'episodes': [
                    {'number': 1, 'first_aired': '2026-08-17T01:00:00.000Z', 'title': 'Pilot'},
                    {'number': 2, 'first_aired': '2030-01-01T01:00:00.000Z', 'title': 'Tonight'},
                ],
            }],
        ), patch(
            'services.shows_cache.refresh_show_progress_for_ids', return_value=0,
        ):
            refresh_shows_cache_for_user(_reload_user(user))
        st = UserMediaState.query.filter_by(
            user_id=user, media_type='show', trakt_id=1,
        ).one()
        assert st.last_episode_aired_at == datetime(2026, 8, 17, 1, 0, 0)



def test_refresh_seeds_list_only_shows_and_marks_never_aired(app, user):
    """List-only shows get a seasons fetch; never-aired shows stamp checked_at."""
    with app.app_context():
        _list_show(user, 1)
        db.session.commit()
        seasons = [{
            'number': 1, 'aired_episodes': 1,
            'episodes': [{'season': 1, 'number': 1,
                          'first_aired': f'{date.today()}T00:00:00.000Z'}],
        }]
        with patch(
            'services.shows_cache.trakt_client.get_show_seasons', return_value=seasons,
        ) as get_seasons, patch(
            'services.shows_cache.refresh_show_progress_for_ids', return_value=0,
        ):
            stats = refresh_shows_cache_for_user(_reload_user(user))
        assert stats['seeded'] == 1
        st = UserMediaState.query.filter_by(
            user_id=user, media_type='show', trakt_id=1,
        ).one()
        assert st.last_episode_aired_at.date() == date.today()

        # Second run: nothing to re-seed (checked_at fresh, no new calendar rows).
        with patch(
            'services.shows_cache.trakt_client.get_show_seasons',
            side_effect=AssertionError('must not re-seed'),
        ) as get_seasons2, patch(
            'services.shows_cache.refresh_show_progress_for_ids', return_value=0,
        ):
            stats2 = refresh_shows_cache_for_user(_reload_user(user))
        assert stats2['seeded'] == 0


def test_refresh_reseeds_when_episodes_aired_but_no_last_aired_date(app, user):
    """A pre-premiere seed must not hide a show after progress sees aired episodes."""
    with app.app_context():
        _list_show(
            user, 157599,
            last_aired_checked_at=datetime.utcnow() - timedelta(days=10),
            episodes_aired=2, episodes_completed=0,
        )
        db.session.commit()
        seasons = [{
            'number': 1, 'aired_episodes': 2,
            'episodes': [
                {'season': 1, 'number': 1,
                 'first_aired': f'{date.today() - timedelta(days=6)}T00:00:00.000Z',
                 'title': 'Pilot'},
                {'season': 1, 'number': 2,
                 'first_aired': f'{date.today() - timedelta(days=1)}T00:00:00.000Z',
                 'title': 'Episode 2'},
            ],
        }]
        with patch(
            'services.shows_cache.trakt_client.get_show_seasons', return_value=seasons,
        ) as get_seasons, patch(
            'services.shows_cache.refresh_show_progress_for_ids', return_value=0,
        ):
            stats = refresh_shows_cache_for_user(_reload_user(user))
        assert stats['seeded'] == 1
        get_seasons.assert_called_once()
        st = UserMediaState.query.filter_by(
            user_id=user, media_type='show', trakt_id=157599,
        ).one()
        assert st.last_episode_aired_at.date() == date.today() - timedelta(days=1)


def test_refresh_aborts_seed_loop_on_429(app, user):
    """First 429 stops the seed loop; remaining shows keep NULL checked_at."""
    with app.app_context():
        for tid in (1, 2, 3):
            _list_show(user, tid)
        db.session.commit()
        err = TraktError('Trakt API error on /shows (429)', 429)
        with patch(
            'services.shows_cache.trakt_client.get_show_seasons', side_effect=err,
        ) as get_seasons, patch(
            'services.shows_cache.refresh_show_progress_for_ids', return_value=0,
        ) as prog:
            stats = refresh_shows_cache_for_user(_reload_user(user))
        assert stats['aborted'] is True
        assert get_seasons.call_count == 1
        assert prog.call_count == 0
        unchecked = UserMediaState.query.filter(
            UserMediaState.user_id == user,
            UserMediaState.media_type == 'show',
            UserMediaState.last_aired_checked_at.is_(None),
        ).count()
        assert unchecked == 3


def test_refresh_progress_only_for_open_shows(app, user):
    """Finished shows (100%) are excluded from the progress refresh."""
    with app.app_context():
        _show(user, 1, progress_percent=100.0,
              last_episode_aired_at=datetime.utcnow(),
              last_aired_checked_at=datetime.utcnow())
        _show(user, 2, progress_percent=40.0,
              last_episode_aired_at=datetime.utcnow(),
              last_aired_checked_at=datetime.utcnow())
        db.session.commit()
        with patch(
            'services.shows_cache.refresh_show_progress_for_ids', return_value=1,
        ) as prog:
            refresh_shows_cache_for_user(_reload_user(user))
        args, kwargs = prog.call_args
        assert args[1] == [2]
        assert kwargs.get('max_workers') == 2


def test_seed_new_shows_inline_is_bounded(app, user):
    """At most ``limit`` seeds per page load; the job picks up the rest."""
    with app.app_context():
        for tid in range(1, 6):
            _show(user, tid)
        db.session.commit()
        with patch(
            'services.shows_cache.trakt_client.get_show_seasons', return_value=[],
        ) as get_seasons:
            n = seed_new_shows_inline(_reload_user(user), limit=3)
        assert n == 3
        assert get_seasons.call_count == 3


def test_seed_inline_fills_aired_show_with_stale_check(app, user):
    """List-only shows with episodes_aired but no last-aired date seed on page load."""
    with app.app_context():
        _list_show(
            user, 157599,
            last_aired_checked_at=datetime.utcnow() - timedelta(days=10),
            episodes_aired=2, episodes_completed=1,
        )
        db.session.commit()
        seasons = [{
            'number': 1,
            'episodes': [
                {'number': 1, 'first_aired': '2026-08-17T01:00:00.000Z', 'title': 'Pilot'},
                {'number': 2, 'first_aired': '2026-08-24T01:00:00.000Z', 'title': 'Episode 2'},
            ],
        }]
        with patch(
            'services.sync_jobs.trakt_client.get_show_seasons', return_value=seasons,
        ):
            n = seed_new_shows_inline(_reload_user(user), limit=3)
        assert n == 1
        st = UserMediaState.query.filter_by(
            user_id=user, media_type='show', trakt_id=157599,
        ).one()
        assert st.last_episode_aired_at is not None


def test_queue_user_media_cycle_inline_without_scheduler(app, user):
    """No scheduler in tests → runs the cycle inline."""
    with app.app_context():
        with patch(
            'services.shows_cache._user_media_cycle_job',
        ) as job:
            queued = queue_user_media_cycle(app, user)
        assert queued is False
        job.assert_called_once_with(app, user)


def test_newest_aired_view_makes_no_trakt_calls(app, client, user):
    """Newest-aired renders from cache: no seasons/progress API calls."""
    from models import CachedMedia

    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        _show(user, 7)
        db.session.add(CachedMedia(
            media_type='show', trakt_id=7, title='Cached Show', year=2024,
        ))
        st = UserMediaState.query.filter_by(
            user_id=user, media_type='show', trakt_id=7,
        ).one()
        st.last_episode_aired_at = datetime.utcnow() - timedelta(days=1)
        st.last_episode_label = 'S01E02'
        st.episodes_aired = 5
        st.episodes_completed = 2
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'), \
         patch(
             'services.trakt_client.get_show_seasons',
             side_effect=AssertionError('page must not call Trakt'),
         ), patch(
             'services.trakt_client.get_show_progress',
             side_effect=AssertionError('page must not call Trakt'),
         ):
        resp = client.get(
            '/my/shows?lists_set=1&lists=watchlist&filter=lists&display=newest_aired'
        )
    assert resp.status_code == 200
    assert 'Cached Show' in resp.get_data(as_text=True)


def test_my_shows_card_shows_next_episode_date(app, client, user):
    """Next-episode line includes the upcoming air date from the calendar."""
    from models import CachedMedia

    future = date.today() + timedelta(days=6)
    with app.app_context():
        prefs = UserPreference.query.filter_by(user_id=user).one()
        prefs.default_selected_list_ids_json = '["watchlist"]'
        _show(
            user, 7, episodes_aired=5, episodes_completed=2,
            next_episode_season=1, next_episode_number=3,
            next_episode_title='Soon',
        )
        db.session.add(CachedMedia(
            media_type='show', trakt_id=7, title='Dated Show', year=2024,
        ))
        _cal_event(user, 7, future, 1, 3, 'Soon')
        db.session.commit()

    login_client(client, app, user)
    with patch('routes.user_routes.ensure_user_media_fresh', return_value=False), \
         patch('routes.user_routes.trakt_client.get_personal_lists', return_value=[]), \
         patch('routes.user_routes.ensure_media_cached'), \
         patch('routes.user_routes.enrich_media_list_for_display'):
        resp = client.get(
            '/my/shows?lists_set=1&lists=watchlist&filter=lists'
        )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Dated Show' in html
    assert 'Next:' in html
    assert future.strftime('%Y-%m-%d') in html


def test_apply_progress_clamps_aired_until_local_air_time(app, user):
    """Trakt aired=2 before 9pm ET must not become 2/2 on the card."""
    from services.sync_jobs import apply_show_episode_progress
    from zoneinfo import ZoneInfo

    with app.app_context():
        _show(
            user, 157599,
            last_episode_aired_at=datetime(2026, 8, 24, 1, 0, 0),
            episodes_aired=1, episodes_completed=1,
            next_episode_season=1, next_episode_number=2,
        )
        db.session.commit()
        before = datetime(2026, 8, 23, 20, 0, 0, tzinfo=ZoneInfo('America/New_York'))
        with patch('services.local_time.local_now', return_value=before):
            apply_show_episode_progress(
                user, 157599, aired=2, completed=1,
                next_episode={'season': 1, 'number': 3, 'title': 'Too far'},
            )
        st = UserMediaState.query.filter_by(
            user_id=user, media_type='show', trakt_id=157599,
        ).one()
        assert st.episodes_aired == 1
        assert st.next_episode_number == 2


def _reload_user(user_id):
    from models import User
    return db.session.get(User, user_id)
