"""
Help menu helpers: load markdown topics safely for user/admin roles.
"""

import os

import markdown


def render_help_markdown(role: str = 'user', topic: str = 'overview') -> str | None:
    """
    Load a help markdown file for role/topic and return HTML.
    Returns None if the topic file is missing (except overview fallback).
    """
    role = 'admin' if role == 'admin' else 'user'
    topic = os.path.basename(topic).replace('.md', '')
    base_dir = os.path.join(os.path.dirname(__file__), 'docs', 'help', role)
    target_file = os.path.join(base_dir, f'{topic}.md')

    if not os.path.exists(target_file):
        if topic not in ('overview', 'admin_overview'):
            return None
        return markdown.markdown('# Help Topic Not Found\n\nThis section has not been authored yet.')

    with open(target_file, 'r', encoding='utf-8') as fh:
        return markdown.markdown(fh.read(), extensions=['tables', 'fenced_code'])


def get_help_toc(role: str = 'user') -> list[dict]:
    """Return table-of-contents entries for the help sidebar."""
    if role == 'admin':
        return [
            {'title': 'Admin overview', 'slug': 'admin_overview'},
            {'title': 'Managing users', 'slug': 'managing_users'},
            {'title': 'Streaming services', 'slug': 'streaming_services'},
            {'title': 'System configuration', 'slug': 'system_config'},
            {'title': 'TMDB API key', 'slug': 'tmdb_api_key'},
            {'title': 'Security', 'slug': 'security'},
            {'title': 'SSL certificates', 'slug': 'ssl_certificates'},
            {'title': 'Testing', 'slug': 'testing'},
            {'title': 'Troubleshooting', 'slug': 'troubleshooting'},
        ]
    return [
        {'title': 'Getting started', 'slug': 'overview'},
        {'title': 'Login with Trakt', 'slug': 'login'},
            {'title': 'Latest movies', 'slug': 'latest_movies'},
            {'title': 'Latest shows', 'slug': 'latest_shows'},
            {'title': 'Trakt 30-day limit', 'slug': 'trakt_sync_limit'},
            {'title': 'Review markers', 'slug': 'review_markers'},
            {'title': 'Preferences', 'slug': 'preferences'},
        {'title': 'My movies', 'slug': 'my_movies'},
        {'title': 'My shows', 'slug': 'my_shows'},
        {'title': 'Series progress', 'slug': 'series_progress'},
        {'title': 'Streaming availability', 'slug': 'streaming'},
        {'title': 'Release alerts', 'slug': 'release_alerts'},
        {'title': 'Notifications', 'slug': 'notifications'},
    ]
