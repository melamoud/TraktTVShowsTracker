"""Read recent Trakt cache-scale lines from the rotating app log."""

from __future__ import annotations

import os
import re
from collections import Counter
from typing import Callable

_CACHE_MSG_RE = re.compile(
    r'Cache (?P<object>\S+) (?P<result>\S+)'
    r' user=(?P<user>\S+)'
    r'(?: id=(?P<item>\S+))?'
    r'(?: reason=(?P<reason>\S+))?'
    r'(?: calls=(?P<calls>\d+))?'
    r' source=(?P<source>.+?)\s*$'
)
_TRAKT_ERR_RE = re.compile(
    r'Trakt (?P<method>GET|POST|PUT|PATCH|DELETE) (?P<path>\S+)'
    r'(?: page=(?P<page>\d+))?'
    r' status=(?P<status>\S+)'
    r' user=(?P<user>\S+)'
    r' source=(?P<source>.+?)\s*$'
)
_TS_RE = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})')
_MAX_BYTES_PER_FILE = 2 * 1024 * 1024
_MIN_LIMIT = 20
_MAX_LIMIT = 1000
_DEFAULT_LIMIT = 200


def clamp_trakt_log_limit(raw) -> int:
    """Keep the viewer window in a sane range."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_LIMIT
    return max(_MIN_LIMIT, min(_MAX_LIMIT, value))


def parse_trakt_log_line(raw: str) -> dict | None:
    """Parse a cache-scale line (or a Trakt HTTP error) into viewer fields."""
    text = (raw or '').rstrip('\n')
    ts_match = _TS_RE.match(text)
    ts = ts_match.group(1) if ts_match else ''
    cache = _CACHE_MSG_RE.search(text)
    if cache:
        calls = cache.group('calls')
        return {
            'raw': text,
            'ts': ts,
            'result': cache.group('result'),
            'object': cache.group('object'),
            'item': cache.group('item') or '',
            'reason': cache.group('reason') or '',
            'calls': int(calls) if calls is not None else 0,
            'user': cache.group('user'),
            'source': cache.group('source').strip(),
        }
    err = _TRAKT_ERR_RE.search(text)
    if err:
        status = err.group('status') or ''
        try:
            code = int(status)
        except (TypeError, ValueError):
            code = 0
        if code < 400:
            return None
        return {
            'raw': text,
            'ts': ts,
            'result': 'error',
            'object': 'http',
            'item': f'{err.group("method")} {err.group("path")}',
            'reason': status,
            'calls': 1,
            'user': err.group('user'),
            'source': err.group('source').strip(),
        }
    return None


def _is_scale_line(line: str) -> bool:
    if ' - Cache ' in line:
        return True
    if ' - Trakt ' not in line:
        return False
    return 'status=4' in line or 'status=5' in line


def _log_paths_newest_first(log_file: str) -> list[str]:
    paths = [log_file]
    for index in range(1, 6):
        backup = f'{log_file}.{index}'
        if os.path.isfile(backup):
            paths.append(backup)
    return paths


def _matching_lines_from_file(
    path: str,
    predicate: Callable[[str], bool],
    max_bytes: int = _MAX_BYTES_PER_FILE,
) -> list[str]:
    try:
        size = os.path.getsize(path)
    except OSError:
        return []
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
                fh.readline()
            return [line.rstrip('\n') for line in fh if predicate(line)]
    except OSError:
        return []


def read_trakt_log(log_file: str, *, limit: int = _DEFAULT_LIMIT, query: str = '') -> dict:
    """
    Return the newest cache-scale lines from the rotating log.

    `query` is a case-insensitive substring filter on the raw line.
    """
    limit = clamp_trakt_log_limit(limit)
    needle = (query or '').strip().lower()

    def predicate(line: str) -> bool:
        if not _is_scale_line(line):
            return False
        if needle and needle not in line.lower():
            return False
        return True

    newest_chunks: list[list[str]] = []
    remaining = limit
    for path in _log_paths_newest_first(log_file):
        if remaining <= 0:
            break
        matches = _matching_lines_from_file(path, predicate)
        take = matches[-remaining:]
        if take:
            newest_chunks.append(take)
            remaining -= len(take)

    raw_lines: list[str] = []
    for chunk in reversed(newest_chunks):
        raw_lines.extend(chunk)

    entries = []
    for raw in raw_lines:
        parsed = parse_trakt_log_line(raw)
        if parsed:
            entries.append(parsed)

    results = Counter(entry['result'] or '(unknown)' for entry in entries)
    objects = Counter(entry['object'] or '(unknown)' for entry in entries)
    users = Counter(entry['user'] or '-' for entry in entries)
    hits = results.get('hit', 0)
    probes = results.get('probe', 0)
    fetches = results.get('fetch', 0)
    decided = hits + probes + fetches
    call_total = sum(int(entry.get('calls') or 0) for entry in entries)
    return {
        'lines': entries,
        'shown': len(entries),
        'limit': limit,
        'query': query or '',
        'log_file': os.path.basename(log_file) if log_file else '',
        'exists': bool(log_file) and os.path.isfile(log_file),
        'stats': {
            'hits': hits,
            'probes': probes,
            'fetches': fetches,
            'calls': call_total,
            'hit_pct': round(100.0 * hits / decided) if decided else 0,
            'by_result': results.most_common(8),
            'by_object': objects.most_common(8),
            'by_user': users.most_common(8),
            'errors': results.get('error', 0),
        },
    }
