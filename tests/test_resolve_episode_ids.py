"""resolve_episode_ids falls back when progress cache was cleared (c437a8b)."""

from unittest.mock import patch

from models import UserMediaState, db


def test_resolve_episode_ids_uses_progress_cache(app, user):
    from services.trakt_cache import resolve_episode_ids, save_progress_payload

    with app.app_context():
        save_progress_payload(
            user,
            1001,
            watched_keys=set(),
            aired_keys={(1, 2)},
            seasons_meta=[
                {
                    'number': 1,
                    'episodes': [
                        {'number': 2, 'ids': {'trakt': 555, 'tvdb': 999}},
                    ],
                },
            ],
        )
        db.session.commit()
        ids = resolve_episode_ids(user, 1001, 1, 2)
    assert ids.get('trakt') == 555


def test_resolve_episode_ids_uses_next_episode_ids_json(app, user):
    from services.trakt_cache import resolve_episode_ids

    with app.app_context():
        row = UserMediaState(
            user_id=user, media_type='show', trakt_id=1003,
        )
        db.session.add(row)
        row.progress_payload_json = None
        row.next_episode_season = 2
        row.next_episode_number = 4
        row.next_episode_ids_json = '{"trakt": 888, "imdb": "tt999"}'
        db.session.commit()
        ids = resolve_episode_ids(user, 1003, 2, 4)
    assert ids.get('trakt') == 888
    assert ids.get('imdb') == 'tt999'


def test_resolve_episode_ids_falls_back_to_trakt_when_cache_empty(app, user):
    from services.trakt_cache import resolve_episode_ids

    seasons = [
        {
            'number': 1,
            'episodes': [
                {'number': 3, 'ids': {'trakt': 777, 'imdb': 'tt123'}},
            ],
        },
    ]
    with app.app_context():
        row = UserMediaState.query.filter_by(
            user_id=user, media_type='show', trakt_id=1002,
        ).first()
        if row is None:
            row = UserMediaState(user_id=user, media_type='show', trakt_id=1002)
            db.session.add(row)
        row.progress_payload_json = None
        row.next_episode_ids_json = None
        db.session.commit()
        with patch(
            'services.trakt_client.get_show_seasons', return_value=seasons,
        ):
            ids = resolve_episode_ids(user, 1002, 1, 3)
    assert ids.get('trakt') == 777
    assert ids.get('imdb') == 'tt123'
