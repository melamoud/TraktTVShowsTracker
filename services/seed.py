"""
Seed default streaming services and genres for a fresh database.
"""

from models import StreamingService, db

DEFAULT_STREAMING_SERVICES = [
    {'name': 'Netflix', 'url': 'https://www.netflix.com', 'tmdb_provider_id': 8},
    {'name': 'Prime Video', 'url': 'https://www.amazon.com/primevideo', 'tmdb_provider_id': 9},
    {'name': 'Disney+', 'url': 'https://www.disneyplus.com', 'tmdb_provider_id': 337},
    {'name': 'Hulu', 'url': 'https://www.hulu.com', 'tmdb_provider_id': 15},
    {'name': 'Max', 'url': 'https://www.max.com', 'tmdb_provider_id': 1899},
    {'name': 'Apple TV+', 'url': 'https://tv.apple.com', 'tmdb_provider_id': 350},
    {'name': 'Paramount+', 'url': 'https://www.paramountplus.com', 'tmdb_provider_id': 531},
    {'name': 'Peacock', 'url': 'https://www.peacocktv.com', 'tmdb_provider_id': 386},
    {'name': 'YouTube', 'url': 'https://www.youtube.com', 'tmdb_provider_id': 192},
    {'name': 'Cable / DVR', 'url': '', 'note': 'Traditional cable or DVR recording'},
    {'name': 'Other', 'url': '', 'note': 'Catch-all for uncommon sources'},
]

COMMON_GENRES = [
    'action', 'adventure', 'animation', 'comedy', 'crime', 'documentary',
    'drama', 'family', 'fantasy', 'history', 'horror', 'music', 'mystery',
    'romance', 'science fiction', 'thriller', 'war', 'western', 'reality',
]


def seed_default_streaming_services() -> int:
    """Insert default streaming services if missing. Returns inserted count."""
    inserted = 0
    for item in DEFAULT_STREAMING_SERVICES:
        if StreamingService.query.filter_by(name=item['name']).first():
            continue
        db.session.add(StreamingService(
            name=item['name'],
            url=item.get('url'),
            note=item.get('note'),
            tmdb_provider_id=item.get('tmdb_provider_id'),
            is_default=True,
        ))
        inserted += 1
    if inserted:
        db.session.commit()
    return inserted
