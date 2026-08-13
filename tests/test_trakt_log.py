"""Unit tests for the admin Trakt cache-scale log reader."""

from services.trakt_log import clamp_trakt_log_limit, parse_trakt_log_line, read_trakt_log


def test_parse_cache_line_extracts_source_with_spaces():
    raw = (
        '2026-08-13 12:00:02,002 - app - INFO - '
        'Cache user_media hit user=friend calls=0 source=http GET /my/shows?refresh=1'
    )
    parsed = parse_trakt_log_line(raw)
    assert parsed['result'] == 'hit'
    assert parsed['object'] == 'user_media'
    assert parsed['calls'] == 0
    assert parsed['user'] == 'friend'
    assert parsed['source'] == 'http GET /my/shows?refresh=1'
    assert parsed['ts'] == '2026-08-13 12:00:02'


def test_parse_cache_fetch_with_id_and_reason():
    raw = (
        '2026-08-13 12:00:03,003 - app - INFO - '
        'Cache progress fetch user=friend id=205569 reason=stale calls=4 '
        'source=http GET /shows/205569/progress'
    )
    parsed = parse_trakt_log_line(raw)
    assert parsed['result'] == 'fetch'
    assert parsed['object'] == 'progress'
    assert parsed['item'] == '205569'
    assert parsed['reason'] == 'stale'
    assert parsed['calls'] == 4


def test_parse_ignores_successful_http_call_lines():
    raw = (
        '2026-08-13 12:00:02,002 - app - INFO - '
        'Trakt GET /sync/last_activities status=200 user=friend source=http GET /my/shows'
    )
    assert parse_trakt_log_line(raw) is None


def test_read_trakt_log_keeps_cache_events_and_429s(tmp_path):
    current = tmp_path / 'app.log'
    current.write_text(
        '\n'.join([
            '2026-08-13 12:00:01,001 - app - INFO - Seeded 11 default streaming services',
            '2026-08-13 12:00:02,002 - app - INFO - Cache user_media hit user=friend calls=0 source=http GET /my/shows',
            '2026-08-13 12:00:03,003 - app - INFO - Trakt GET /sync/last_activities status=200 user=friend source=http GET /my/shows',
            '2026-08-13 12:00:04,004 - app - WARNING - Trakt GET /movies/updates/2026-08-01 status=429 user=- source=scheduler catalog_sync',
            '2026-08-13 12:00:05,005 - app - INFO - Cache latest fetch user=- id=movie reason=ttl calls=3 source=scheduler catalog_sync',
        ]) + '\n',
        encoding='utf-8',
    )
    payload = read_trakt_log(str(current), limit=20)
    assert [row['result'] for row in payload['lines']] == ['hit', 'error', 'fetch']
    assert payload['stats']['hits'] == 1
    assert payload['stats']['fetches'] == 1
    assert payload['stats']['calls'] == 4
    filtered = read_trakt_log(str(current), limit=20, query='scheduler')
    assert filtered['shown'] == 2


def test_clamp_trakt_log_limit():
    assert clamp_trakt_log_limit('nope') == 200
    assert clamp_trakt_log_limit(5) == 20
    assert clamp_trakt_log_limit(5000) == 1000
