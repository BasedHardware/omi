#!/usr/bin/env python3
"""Fail deployment if a same-name sequencer alert has drifted from its contract.

The lifecycle action owns creation but intentionally does not overwrite an
existing operator-managed policy. A stale policy must not silently satisfy the
alert gate before Cloud Run traffic promotion.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def check_policy(
    policy: dict[str, Any], *, condition: str, filter_text: str, duration_seconds: int, channels: list[str]
) -> list[str]:
    errors: list[str] = []
    conditions = policy.get('conditions')
    if not isinstance(conditions, list) or len(conditions) != 1:
        return ['expected exactly one alert condition']
    field = 'conditionAbsent' if condition == 'absent' else 'conditionThreshold'
    actual = conditions[0].get(field) if isinstance(conditions[0], dict) else None
    if not isinstance(actual, dict):
        return [f'expected {field} condition']
    if actual.get('filter') != filter_text:
        errors.append('condition filter differs')
    duration = actual.get('duration', '0s')
    if duration != f'{duration_seconds}s':
        errors.append('condition duration differs')
    actual_channels = policy.get('notificationChannels')
    if not isinstance(actual_channels, list) or sorted(actual_channels) != sorted(channels):
        errors.append('notification channels differ')
    if policy.get('enabled') is False:
        errors.append('policy is disabled')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--condition', choices=('threshold', 'absent'), required=True)
    parser.add_argument('--filter', required=True)
    parser.add_argument('--duration-seconds', type=int, required=True)
    parser.add_argument('--channels', required=True, help='comma-separated notification-channel resource names')
    args = parser.parse_args()
    channels = [channel.strip() for channel in args.channels.split(',') if channel.strip()]
    if not channels or len(channels) != len(set(channels)):
        parser.error('expected distinct nonempty notification channels')
    policy = json.load(sys.stdin)
    errors = check_policy(
        policy,
        condition=args.condition,
        filter_text=args.filter,
        duration_seconds=args.duration_seconds,
        channels=channels,
    )
    if errors:
        print('Sync backfill alert policy drift: ' + '; '.join(errors), file=sys.stderr)
        return 1
    print('Sync backfill alert policy matches its routed condition and channels')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
