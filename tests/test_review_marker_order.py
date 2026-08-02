"""Review marker dimming follows visible list position (includes clicked row)."""

from datetime import datetime

from flask_login import login_user

from models import ReviewMarker, User, db
from routes.catalog_routes import _apply_marker_to_visible_rows


class _M:
    def __init__(self, trakt_id, title):
        self.trakt_id = trakt_id
        self.title = title


def test_marker_dims_from_clicked_row_down(app, user):
    """Rows at/after the marker index are dimmed; rows above are not."""
    with app.app_context():
        db.session.add(ReviewMarker(
            user_id=user, media_type='movie', trakt_id=20,
            trakt_listed_at=datetime(2026, 8, 2, 12, 0, 0),
            title='Clicked',
        ))
        db.session.commit()
        u = db.session.get(User, user)

        rows = [
            {'media': _M(10, 'Above'), 'older_than_marker': False, 'is_marker': False},
            {'media': _M(20, 'Clicked'), 'older_than_marker': False, 'is_marker': False},
            {'media': _M(30, 'Below'), 'older_than_marker': False, 'is_marker': False},
        ]
        with app.test_request_context('/'):
            login_user(u)
            _apply_marker_to_visible_rows(rows, 'movie')

        assert rows[0]['older_than_marker'] is False
        assert rows[0]['is_marker'] is False
        assert rows[1]['older_than_marker'] is True
        assert rows[1]['is_marker'] is True
        assert rows[2]['older_than_marker'] is True
        assert rows[2]['is_marker'] is False
