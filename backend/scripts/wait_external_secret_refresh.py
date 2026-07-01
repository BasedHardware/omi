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

    while True:
        state = load_json(args.state_json) if args.state_json else fetch_external_secret(args.namespace, args.name)
        observed, reason = external_secret_refresh_observed(state, min_refresh_time)
        if observed:
            print(f'ExternalSecret refresh observed: {reason}')
            return 0
        last_reason = reason
        if args.state_json or time.monotonic() >= deadline:
            break
        time.sleep(args.interval_seconds)

    print(
        f'ERROR: timed out waiting for ExternalSecret refresh after {min_refresh_time.isoformat()}: {last_reason}',
        file=sys.stderr,
    )
    return 1


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


if __name__ == '__main__':
    raise SystemExit(main())
