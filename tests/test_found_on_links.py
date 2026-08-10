"""Found-on / Plays-on service chip link builders."""

from services.found_on_links import apply_search_template, found_on_open_url


def test_found_on_netflix_uses_search():
    """Known services open a title search, not just the homepage."""
    url = found_on_open_url(
        'Netflix', title='Andor', year=2022, base_urls={}, search_templates=None,
    )
    assert 'netflix.com/search' in url
    assert 'Andor' in url
    assert '2022' in url


def test_custom_search_template_title_placeholder():
    """User search templates replace <title> with an encoded title+year."""
    url = found_on_open_url(
        'toFlx',
        title="The Devil's Mouth",
        year=2026,
        base_urls={'toflx': 'https://toflx.com'},
        search_templates={'toflx': 'https://toflx.com/search?q=<title>'},
    )
    assert url == "https://toflx.com/search?q=The%20Devil%27s%20Mouth%202026"


def test_apply_search_template_requires_placeholder():
    """Templates without a placeholder are ignored."""
    assert apply_search_template('https://toflx.com/', 'Dune 2021') is None


def test_found_on_cable_has_no_link():
    """Cable / DVR and Other stay non-links."""
    assert found_on_open_url('Cable / DVR', title='Anything', base_urls={}) is None
    assert found_on_open_url('Other', title='Anything', base_urls={}) is None


def test_found_on_homepage_without_title():
    """Without a title, fall back to the service homepage."""
    url = found_on_open_url(
        'Netflix',
        title='',
        base_urls={'netflix': 'https://www.netflix.com'},
        search_templates={},
    )
    assert url == 'https://www.netflix.com'
