#!/usr/bin/env python3
"""Restore or remove only the Soniox daily-hours alert from its apply snapshot."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.provision_monitoring_alerts import (  # noqa: E402
    API,
    SONIOX_DAILY_HOURS_UID,
    Grafana,
    comparable,
    definition,
)

MAX_BACKUP_BYTES = 16_000_000


def _rule_map(value: object, field: str) -> dict[str, dict]:
    if not isinstance(value, list):
        raise ValueError(f'{field} must be a list')
    result = {}
    for rule in value:
        if not isinstance(rule, dict):
            raise ValueError(f'{field} contains a non-object rule')
        uid = rule.get('uid')
        if not isinstance(uid, str) or not uid or uid in result:
            raise ValueError(f'{field} contains a missing or duplicate UID')
        result[uid] = rule
    return result


def load_snapshot(path: Path, expected_source_sha: str, expected_source_run_id: str) -> dict:
    if not re.fullmatch(r'[0-9a-f]{40}', expected_source_sha):
        raise ValueError('expected source SHA must be a full lowercase Git SHA')
    if not re.fullmatch(r'[1-9][0-9]*', expected_source_run_id):
        raise ValueError('expected source run ID must be a positive integer')
    if path.stat().st_size > MAX_BACKUP_BYTES:
        raise ValueError('backup exceeds size limit')
    backup = json.loads(path.read_text())
    if not isinstance(backup, dict) or backup.get('schema_version') != 1:
        raise ValueError('unsupported alert backup schema')
    if backup.get('source_sha') != expected_source_sha or str(backup.get('source_run_id')) != expected_source_run_id:
        raise ValueError('backup does not match the selected source run')

    rollback = backup.get('soniox_alert_rollback')
    if not isinstance(rollback, dict) or rollback.get('uid') != SONIOX_DAILY_HOURS_UID:
        raise ValueError('backup does not contain the Soniox alert inverse')
    desired = rollback.get('desired')
    if not isinstance(desired, dict) or desired.get('uid') != SONIOX_DAILY_HOURS_UID:
        raise ValueError('backup contains an invalid Soniox desired definition')

    previous = _rule_map(backup.get('rules'), 'rules').get(SONIOX_DAILY_HOURS_UID)
    created_uids = backup.get('created_uids')
    if (
        not isinstance(created_uids, list)
        or any(not isinstance(uid, str) for uid in created_uids)
        or len(created_uids) != len(set(created_uids))
    ):
        raise ValueError('backup contains an invalid created UID list')
    was_created = SONIOX_DAILY_HOURS_UID in created_uids
    if (previous is None) == (not was_created):
        raise ValueError('backup must show either the prior Soniox rule or that this run created it')
    return {'desired': desired, 'previous': previous, 'was_created': was_created}


def inverse_plan(api: Grafana, snapshot: dict) -> tuple[str, dict | None, dict | None]:
    uid = SONIOX_DAILY_HOURS_UID
    previous, desired = snapshot['previous'], snapshot['desired']
    live = api.rules().get(uid)
    if previous is not None and live is not None and comparable(live) == comparable(previous):
        return 'already-restored', live, previous
    if previous is None and live is None:
        return 'already-restored', live, previous
    if live is None or comparable(live) != comparable(desired):
        raise ValueError(
            'live Soniox rule differs from both the applied and captured definitions; refusing to overwrite'
        )
    return ('restore' if previous is not None else 'delete'), live, previous


def restore_soniox_alert(api: Grafana, snapshot: dict, *, apply: bool) -> str:
    action, live, previous = inverse_plan(api, snapshot)
    if action == 'already-restored':
        return 'Soniox alert already matches the captured pre-apply state'
    if not apply:
        return f'Would {action} only {SONIOX_DAILY_HOURS_UID}'

    path = API + '/' + quote(SONIOX_DAILY_HOURS_UID, safe='')
    if action == 'restore':
        api.request(path, definition(previous), 'PUT', editable=live.get('provenance', '') == '')
    else:
        api.request(path, method='DELETE', editable=live.get('provenance', '') == '')

    verified = api.rules().get(SONIOX_DAILY_HOURS_UID)
    if previous is None:
        if verified is not None:
            raise ValueError('Soniox rule remains after rollback delete')
    elif verified is None or comparable(verified) != comparable(previous):
        raise ValueError('Soniox rule read-back differs from the captured pre-apply definition')
    return f'Rolled back only {SONIOX_DAILY_HOURS_UID} and verified read-back'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup-file', type=Path, required=True)
    parser.add_argument('--expected-source-sha', required=True)
    parser.add_argument('--expected-source-run-id', required=True)
    parser.add_argument('--grafana-url', default='https://monitor.omi.me')
    parser.add_argument('--token-env', default='MONITOR_GRAFANA_TOKEN')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-soniox-alert-restore', action='store_true')
    args = parser.parse_args()
    try:
        if args.apply != args.confirm_soniox_alert_restore:
            raise ValueError('--apply and --confirm-soniox-alert-restore must be supplied together')
        snapshot = load_snapshot(args.backup_file, args.expected_source_sha, args.expected_source_run_id)
        token = os.environ.get(args.token_env, '').strip()
        if not token:
            raise ValueError(f'{args.token_env} is empty')
        api = Grafana(args.grafana_url, token)
        print(restore_soniox_alert(api, snapshot, apply=args.apply))
        return 0
    except (OSError, ValueError, json.JSONDecodeError):
        exc = sys.exc_info()[1]
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
