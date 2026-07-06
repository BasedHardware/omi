#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

EXIT_REFRESH_OBSERVED = 0
EXIT_HARD_ERROR = 1
EXIT_TIMEOUT = 2
EXIT_NOT_READY_AFTER_REFRESH = 3


def main() -> int:
    parser = argparse.ArgumentParser(description='Wait for an ExternalSecret refresh observed after a force-sync.')
    parser.add_argument('--namespace', required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument(
        '--min-refresh-time', required=True, help='Unix epoch seconds or ISO timestamp before annotation.'
    )
    parser.add_argument('--timeout-seconds', type=int, default=120)
    parser.add_argument('--interval-seconds', type=float, default=2.0)
    parser.add_argument('--state-json', type=Path, help='Offline ExternalSecret JSON for tests.')
    args = parser.parse_args()

    min_refresh_time = parse_timestamp(args.min_refresh_time)
    deadline = time.monotonic() + args.timeout_seconds
    last_reason = 'ExternalSecret status unavailable'
    saw_fresh_refresh = False

    while True:
        try:
            state = load_json(args.state_json) if args.state_json else fetch_external_secret(args.namespace, args.name)
        except Exception as exc:
            print(f'ERROR: failed to read ExternalSecret state: {exc}', file=sys.stderr)
            return EXIT_HARD_ERROR
        observed, reason = external_secret_refresh_observed(state, min_refresh_time)
        if observed:
            print(f'ExternalSecret refresh observed: {reason}')
            return EXIT_REFRESH_OBSERVED
        last_reason = reason
        if reason.startswith('status.refreshTime') and 'Ready condition is not true' in reason:
            saw_fresh_refresh = True
        if args.state_json or time.monotonic() >= deadline:
            break
        time.sleep(args.interval_seconds)

    if saw_fresh_refresh:
        print(
            f'ERROR: ExternalSecret refreshed after {min_refresh_time.isoformat()} but Ready condition is not true: '
            f'{last_reason}',
            file=sys.stderr,
        )
        return EXIT_NOT_READY_AFTER_REFRESH

    print(
        f'ERROR: timed out waiting for ExternalSecret refresh after {min_refresh_time.isoformat()}: {last_reason}',
        file=sys.stderr,
    )
    return EXIT_TIMEOUT


def fetch_external_secret(namespace: str, name: str) -> dict[str, Any]:
    result = subprocess.run(
        ['kubectl', '-n', namespace, 'get', f'externalsecret/{name}', '-o', 'json'],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    with path.open('r', encoding='utf-8') as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f'{path} must contain a JSON object')
    return loaded


def external_secret_refresh_observed(state: dict[str, Any], min_refresh_time: datetime) -> tuple[bool, str]:
    status = state.get('status') if isinstance(state, dict) else {}
    if not isinstance(status, dict):
        return False, 'ExternalSecret status missing'

    refresh_time = parse_optional_timestamp(status.get('refreshTime'))
    if refresh_time is None:
        return False, 'status.refreshTime missing'
    min_refresh_time = to_kubernetes_timestamp_precision(min_refresh_time)
    if refresh_time < min_refresh_time:
        return False, f'status.refreshTime {refresh_time.isoformat()} is older than requested refresh'

    if not is_ready(status.get('conditions')):
        return False, f'status.refreshTime {refresh_time.isoformat()} observed but Ready condition is not true'

    return True, f'status.refreshTime={refresh_time.isoformat()}'


def is_ready(conditions: Any) -> bool:
    if not isinstance(conditions, list):
        return False
    return any(
        isinstance(condition, dict)
        and condition.get('type') == 'Ready'
        and str(condition.get('status') or '').lower() == 'true'
        for condition in conditions
    )


def parse_optional_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    return parse_timestamp(value)


def parse_timestamp(value: str) -> datetime:
    if value.isdigit():
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def to_kubernetes_timestamp_precision(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(microsecond=0)


if __name__ == '__main__':
    raise SystemExit(main())
