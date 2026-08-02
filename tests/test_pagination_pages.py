"""Compact pagination window helper."""

from routes.catalog_routes import _pagination_pages


def test_pagination_pages_small_list_is_complete():
    assert _pagination_pages(1, 5) == [1, 2, 3, 4, 5]


def test_pagination_pages_large_list_uses_ellipsis():
    links = _pagination_pages(5, 20)
    assert links[0] == 1
    assert links[-1] == 20
    assert None in links
    assert 5 in links
    assert 4 in links
    assert 6 in links
