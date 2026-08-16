"""Unit tests for year / genre advanced filters."""

from services.list_filters import (
    media_matches_genres,
    media_matches_year,
    normalize_genre_label,
    parse_genre_filters,
    parse_year_filter,
    row_passes_advanced,
)
from models import CachedMedia


def test_parse_year_single():
    assert parse_year_filter('2018') == (2018, 2018)
    assert parse_year_filter(' 1999 ') == (1999, 1999)


def test_parse_year_range():
    assert parse_year_filter('2015-2020') == (2015, 2020)
    assert parse_year_filter('2020–2015') == (2015, 2020)
    assert parse_year_filter('2010 - 2012') == (2010, 2012)


def test_parse_year_invalid():
    assert parse_year_filter('') is None
    assert parse_year_filter('abc') is None
    assert parse_year_filter('99') is None
    assert parse_year_filter('1200') is None


def test_parse_genre_filters_or_labels():
    assert parse_genre_filters({'genre': ['Drama', 'thriller']}) == ['drama', 'thriller']
    assert parse_genre_filters({'genres': 'science-fiction,action'}) == [
        'science fiction', 'action',
    ]


def test_normalize_genre_label():
    assert normalize_genre_label('Science Fiction') == 'science fiction'
    assert normalize_genre_label('unknown-genre') is None


def test_media_matches_year_and_unknown_kept():
    known = CachedMedia(media_type='movie', trakt_id=1, title='A', year=2018)
    unknown = CachedMedia(media_type='movie', trakt_id=2, title='B')
    assert media_matches_year(known, (2015, 2020)) is True
    assert media_matches_year(known, (2020, 2022)) is False
    assert media_matches_year(unknown, (2015, 2020)) is True


def test_media_matches_genres_or():
    media = CachedMedia(
        media_type='show', trakt_id=3, title='C',
        genres_json='["drama","thriller"]',
    )
    assert media_matches_genres(media, ['comedy']) is False
    assert media_matches_genres(media, ['comedy', 'drama']) is True
    assert media_matches_genres(media, []) is True


def test_row_passes_advanced():
    row = {
        'media': CachedMedia(
            media_type='movie', trakt_id=4, title='D', year=2016,
            genres_json='["action"]',
        ),
    }
    assert row_passes_advanced(row, (2015, 2018), ['action']) is True
    assert row_passes_advanced(row, (2010, 2012), ['action']) is False
    assert row_passes_advanced(row, (2015, 2018), ['horror']) is False
