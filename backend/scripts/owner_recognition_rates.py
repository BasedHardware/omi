"""Print owner-recognition counter rates from a Prometheus HTTP endpoint.

Usage:
    python backend/scripts/owner_recognition_rates.py http://127.0.0.1:9090 --window 1h

The endpoint is the only address. This script sends no credentials.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

_WINDOW = re.compile(r'^[0-9]+[smhdw]$')


def validate_window(window: str) -> str:
    if not _WINDOW.fullmatch(window):
        raise SystemExit(f'window must look like 5m or 1h, not {window!r}')
    return window


def queries(window: str) -> list[tuple[str, str]]:
    validated = validate_window(window)
    return [
        (
            'omi_owner_recognition_conversations_total',
            'sum by (surface, source, outcome) ' f'(rate(omi_owner_recognition_conversations_total[{validated}]))',
        ),
        (
            'omi_owner_recognition_owner_share',
            'histogram_quantile(0.5, sum by (le) ' f'(rate(omi_owner_recognition_owner_share_bucket[{validated}])))',
        ),
        (
            'omi_speaker_id_live_decisions_total',
            f'sum by (target, decision) (rate(omi_speaker_id_live_decisions_total[{validated}]))',
        ),
        (
            'omi_speaker_id_match_exits_total',
            f'sum by (reason) (rate(omi_speaker_id_match_exits_total[{validated}]))',
        ),
        (
            'omi_live_speaker_rollover_total',
            f'sum by (carried, target) (rate(omi_live_speaker_rollover_total[{validated}]))',
        ),
    ]


def query_url(endpoint: str, promql: str) -> str:
    base = endpoint.rstrip('/')
    return base + '/api/v1/query?' + urllib.parse.urlencode({'query': promql})


def format_vector(name: str, body: dict) -> str:
    lines = [name]
    result = ((body.get('data') or {}).get('result')) or []
    if not result:
        lines.append('  (no series)')
        return '\n'.join(lines)
    for series in result:
        metric = series.get('metric') or {}
        labels = ' '.join(f'{key}={value}' for key, value in sorted(metric.items()) if key != '__name__')
        value = (series.get('value') or [None, None])[1]
        lines.append(f'  {labels}  {value}'.rstrip())
    return '\n'.join(lines)


def fetch(endpoint: str, promql: str, *, timeout: float) -> dict:
    request = urllib.request.Request(query_url(endpoint, promql), method='GET')
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode('utf-8'))
    if payload.get('status') != 'success':
        raise RuntimeError(payload.get('error') or payload.get('status') or 'prometheus query failed')
    return payload


def render(endpoint: str, window: str, *, timeout: float, opener=None) -> str:
    """Query each counter. ``opener`` is fetch(endpoint, promql) -> body, for tests."""
    blocks = [f'endpoint={endpoint} window={window}']
    load = opener or (lambda _endpoint, promql: fetch(_endpoint, promql, timeout=timeout))
    for name, promql in queries(window):
        blocks.append(format_vector(name, load(endpoint, promql)))
    return '\n'.join(blocks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('endpoint', help='Prometheus base URL, for example http://127.0.0.1:9090')
    parser.add_argument('--window', default='1h', help='Prometheus range like 5m, 1h, or 7d')
    parser.add_argument('--timeout', type=float, default=30.0)
    args = parser.parse_args(argv)
    try:
        print(render(args.endpoint, args.window, timeout=args.timeout))
    except (urllib.error.URLError, RuntimeError, json.JSONDecodeError, OSError) as error:
        print(f'prometheus query failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
