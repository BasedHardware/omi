#!/usr/bin/env python3
"""Restore or remove only the Soniox daily-hours alert from its apply snapshot."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.provision_monitoring_alerts import (  # noqa: E402
    APP_ALERT_RULES_API,
    SONIOX_DAILY_HOURS_UID,
    Grafana,
    _app_rule_semantics,
)

MAX_BACKUP_BYTES = 16_000_000


def load_snapshot(path: Path, expected_source_sha: str, expected_source_run_id: str) -> dict:
    if not re.fullmatch(r'[0-9a-f]{40}', expected_source_sha):
        raise ValueError('expected source SHA must be a full lowercase Git SHA')
    if not re.fullmatch(r'[1-9][0-9]*', expected_source_run_id):
        raise ValueError('expected source run ID must be a positive integer')
    if path.stat().st_size > MAX_BACKUP_BYTES:
        raise ValueError('backup exceeds size limit')
    backup = json.loads(path.read_text())
    if not isinstance(backup, dict) or backup.get('schema_version') != 2:
        raise ValueError('unsupported alert backup schema')
    if backup.get('source_sha') != expected_source_sha or str(backup.get('source_run_id')) != expected_source_run_id:
        raise ValueError('backup does not match the selected source run')

    rollback = backup.get('soniox_alert_rollback')
    if not isinstance(rollback, dict) or rollback.get('uid') != SONIOX_DAILY_HOURS_UID:
        raise ValueError('backup does not contain the Soniox alert inverse')
    desired = rollback.get('desired')
    desired_resource = rollback.get('desired_resource')
    if not isinstance(desired, dict) or desired.get('uid') != SONIOX_DAILY_HOURS_UID:
        raise ValueError('backup contains an invalid Soniox desired definition')
    desired_metadata = desired_resource.get('metadata') if isinstance(desired_resource, dict) else None
    if (
        not isinstance(desired_resource, dict)
        or desired_resource.get('kind') != 'AlertRule'
        or not isinstance(desired_metadata, dict)
        or desired_metadata.get('name') != SONIOX_DAILY_HOURS_UID
    ):
        raise ValueError('backup contains an invalid versioned Soniox definition')
    previous = rollback.get('previous_resource')
    previous_metadata = previous.get('metadata') if isinstance(previous, dict) else None
    if previous is not None and (
        not isinstance(previous, dict)
        or previous.get('kind') != 'AlertRule'
        or not isinstance(previous_metadata, dict)
        or previous_metadata.get('name') != SONIOX_DAILY_HOURS_UID
        or not previous_metadata.get('resourceVersion')
    ):
        raise ValueError('backup contains an invalid versioned Soniox preimage')
    created_uids = backup.get('created_uids')
    if (
        not isinstance(created_uids, list)
        or any(not isinstance(uid, str) for uid in created_uids)
        or len(created_uids) != len(set(created_uids))
    ):
        raise ValueError('backup contains an invalid created UID list')
    was_created = SONIOX_DAILY_HOURS_UID in created_uids
    if was_created != (previous is None):
        raise ValueError('backup must show either the prior Soniox rule or that this run created it')
    return {
        'desired': desired,
        'desired_resource': desired_resource,
        'previous_resource': previous,
        'was_created': was_created,
    }


def inverse_plan(api: Grafana, snapshot: dict) -> tuple[str, dict | None, dict | None]:
    uid = SONIOX_DAILY_HOURS_UID
    previous, desired = snapshot['previous_resource'], snapshot['desired_resource']
    live = api.app_alert_rule(uid)
    if previous is not None and live is not None and _app_rule_semantics(live) == _app_rule_semantics(previous):
        return 'already-restored', live, previous
    if previous is None and live is None:
        return 'already-restored', live, previous
    if live is None or _app_rule_semantics(live) != _app_rule_semantics(desired):
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

    path = APP_ALERT_RULES_API + '/' + quote(SONIOX_DAILY_HOURS_UID, safe='')
    if action == 'restore':
        restored = copy.deepcopy(previous)
        metadata = restored['metadata']
        live_metadata = live['metadata']
        restored_metadata = {'name': SONIOX_DAILY_HOURS_UID, 'resourceVersion': live_metadata['resourceVersion']}
        annotations = copy.deepcopy(metadata.get('annotations', {}))
        for key in ('grafana.app/createdBy', 'grafana.app/updatedBy', 'grafana.app/updatedTimestamp'):
            annotations.pop(key, None)
        if annotations:
            restored_metadata['annotations'] = annotations
        labels = metadata.get('labels')
        if isinstance(labels, dict) and labels:
            restored_metadata['labels'] = copy.deepcopy(labels)
        restored['metadata'] = restored_metadata
        restored.pop('status', None)
        api.request(path, restored, 'PUT')
    else:
        api.request(
            path,
            {'preconditions': {'resourceVersion': live['metadata']['resourceVersion']}},
            'DELETE',
        )

    verified = api.app_alert_rule(SONIOX_DAILY_HOURS_UID)
    if previous is None:
        if verified is not None:
            raise ValueError('Soniox rule remains after rollback delete')
    elif verified is None or _app_rule_semantics(verified) != _app_rule_semantics(previous):
        raise ValueError('Soniox rule read-back differs from the captured versioned preimage')
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
        if args.apply:
            print(
                'WARNING: Grafana resourceVersion preconditions are advisory on legacy alert-rule '
                'storage; the pre-write drift check and post-write read-back do not close the '
                'concurrent-edit window.'
            )
        print(restore_soniox_alert(api, snapshot, apply=args.apply))
        return 0
    except (OSError, ValueError, json.JSONDecodeError):
        exc = sys.exc_info()[1]
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
