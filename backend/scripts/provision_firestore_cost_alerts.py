#!/usr/bin/env python3
"""Release-only, three-UID Firestore alert provisioning; never write dashboards."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.parse
from pathlib import Path

import provision_monitoring_alerts as shared

TARGETS = frozenset(
    ('omi-firestore-batch-reads-audio-hour', 'omi-firestore-batch-reads-no-output', 'omi-firestore-billed-reads-step')
)


def select_uids(value: str) -> frozenset[str]:
    items = value.split(',')
    if not items or any(not uid or uid.strip() != uid for uid in items) or len(items) != len(set(items)):
        raise ValueError('target UIDs must be nonempty, unique, comma-separated exact UIDs')
    selected = frozenset(items)
    if not selected <= TARGETS:
        raise ValueError('only the three SCA-2189 Firestore UIDs are permitted')
    return selected


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class ScopedGrafana:
    """All mutations pass through this boundary, including shared reconciliation."""

    def __init__(self, api, targets: frozenset[str]):
        if not targets or not targets <= TARGETS:
            raise ValueError('invalid Firestore scope')
        self.api, self.targets = api, targets

    def rules(self):
        return {uid: rule for uid, rule in self.api.rules().items() if uid in self.targets}

    def request(self, path, body=None, method='GET', *, editable=False):
        if method != 'GET':
            uid = body.get('uid') if isinstance(body, dict) else None
            allowed = method == 'POST' and path == shared.API and uid in self.targets
            allowed |= method == 'PUT' and uid in self.targets and path == shared.API + '/' + uid
            allowed |= (
                method == 'DELETE' and body is None and path in {shared.API + '/' + target for target in self.targets}
            )
            if not allowed:
                raise ValueError('refusing mutation outside selected Firestore alert UIDs')
        return self.api.request(path, body, method, editable=editable)


def snapshot(api, targets):
    """Hash every readable Ops dashboard and non-target alert without exposing content."""
    rules = api.rules()
    dashboards = {}
    page = 1
    while True:
        entries = api.request(f'/api/search?type=dash-db&limit=1000&page={page}')
        if not isinstance(entries, list):
            raise ValueError('invalid dashboard inventory')
        for item in entries:
            uid = item['uid']
            if uid in dashboards:
                raise ValueError('dashboard pagination repeated a UID')
            dashboard = api.request('/api/dashboards/uid/' + urllib.parse.quote(uid, safe=''))
            dashboards[uid] = fingerprint(dashboard['dashboard'])
        if len(entries) < 1000:
            break
        page += 1
    return {
        'other_alerts': {
            uid: fingerprint(shared.comparable(rule)) for uid, rule in rules.items() if uid not in targets
        },
        'dashboards': dashboards,
    }


def write_json(path: Path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())


def restore_plan(path: Path, targets):
    backup = json.loads(path.read_text())
    if not isinstance(backup, dict) or set(backup) != {'rules', 'created_uids'}:
        raise ValueError('invalid selected-rule backup')
    if not isinstance(backup['rules'], list):
        raise ValueError('invalid selected-rule backup list')
    rules = shared.index_rules(backup['rules']) if backup['rules'] else {}
    created = backup['created_uids']
    if (
        not isinstance(created, list)
        or any(not isinstance(uid, str) for uid in created)
        or len(set(created)) != len(created)
        or set(rules) & set(created)
        or set(rules) | set(created) != targets
    ):
        raise ValueError('backup must cover exactly the selected UIDs')
    return rules, created


def verify_canaries(api, live, desired):
    if not any(rule.get('execErrState') == 'KeepLast' for rule in desired.values()):
        return
    committed = shared.load_rules(shared.RULES)
    canaries = {uid: committed[uid] for uid in shared.CANARY_UIDS}
    for uid, rule in canaries.items():
        if (
            rule.get('isPaused') is not False
            or rule.get('execErrState') != 'Alerting'
            or rule.get('noDataState') != 'Alerting'
            or uid not in live
            or shared.comparable(live[uid]) != shared.comparable(rule)
        ):
            raise ValueError(
                'KeepLast requires existing active committed datasource canaries; no canary writes allowed'
            )
    if shared.probe_datasources(api, canaries):
        raise ValueError('existing datasource canary probes failed')


def execute(api, desired, targets, *, backup=None, restore=None, evidence=None):
    if not targets or not targets <= TARGETS or set(desired) != targets:
        raise ValueError('desired rules must cover exactly the selected Firestore UIDs')
    saved, created = restore_plan(restore, targets) if restore else ({}, [])
    before = snapshot(api, targets)
    receipt = evidence if evidence is not None else {}
    receipt.update(
        status='incomplete',
        targets=sorted(targets),
        unchanged_before=before,
        selected_expected=saved if restore else desired,
    )
    live = api.rules()
    # Shared reconciliation sees only selected rules. Check their full live
    # groups first so filtering cannot hide a provenance boundary.
    for uid, rule in (saved if restore else desired).items():
        group = (rule['folderUID'], rule['ruleGroup'])
        members = [r for r in live.values() if (r.get('folderUID'), r.get('ruleGroup')) == group]
        provenances = {r.get('provenance', '') for r in members}
        if len(provenances) > 1 or provenances - {'', 'api'}:
            raise ValueError('selected rule group has mixed or file-owned provenance')
        if uid in live and live[uid].get('provenance', '') not in ('', 'api'):
            raise ValueError('selected rule belongs to another provisioner')
        if restore and uid in live and live[uid].get('provenance', '') != rule.get('provenance', ''):
            raise ValueError('restore cannot cross provenance boundaries')
    scoped = ScopedGrafana(api, targets)
    if restore:
        receipt['restore_delete_uids'] = sorted(created)
        if any(live[uid].get('provenance', '') not in ('', 'api') for uid in created if uid in live):
            raise ValueError('restore cannot delete rules owned by another provisioner')
        # Restore can delete only UIDs that the original selected apply created.
        differences = shared.drift(saved, scoped.rules())
        if backup:
            verify_canaries(api, live, saved)
            write_json(backup, {'rules': list(scoped.rules().values()), 'created_uids': sorted(targets - live.keys())})
            for uid, rule in saved.items():
                scoped.request(
                    shared.API + '/' + uid if uid in live else shared.API,
                    shared.definition(rule),
                    'PUT' if uid in live else 'POST',
                    editable=rule.get('provenance', '') == '',
                )
            for uid in created:
                if uid in live:
                    scoped.request(shared.API + '/' + uid, method='DELETE')
            current = scoped.rules()
            differences = shared.drift(saved, current)
    else:
        differences = shared.drift(desired, scoped.rules())
        if backup:
            # Unlike bundle reconciliation, this path must never install or
            # repair canaries. Existing committed canaries must already pass.
            verify_canaries(api, live, desired)
            contacts = api.request('/api/v1/provisioning/contact-points')
            if not isinstance(contacts, list) or not any(
                isinstance(point, dict)
                and point.get('name') == shared.RECEIVER
                and point.get('type') == 'telegram'
                and point.get('disableResolveMessage') is not True
                for point in contacts
            ):
                raise ValueError('Telegram receiver is missing or resolve notifications disabled')
            for folder in sorted({rule['folderUID'] for rule in desired.values()}):
                api.request('/api/folders/' + urllib.parse.quote(folder, safe=''))
            write_json(backup, {'rules': list(scoped.rules().values()), 'created_uids': sorted(targets - live.keys())})
            for uid, rule in sorted(desired.items()):
                if uid in live and shared.comparable(rule) == shared.comparable(live[uid]):
                    continue
                members = [
                    r
                    for r in live.values()
                    if (r.get('folderUID'), r.get('ruleGroup')) == (rule['folderUID'], rule['ruleGroup'])
                ]
                provenance = members[0].get('provenance', '') if members else 'api'
                if uid in live and live[uid].get('provenance', '') != provenance:
                    raise ValueError('selected rule cannot cross provenance boundaries')
                scoped.request(
                    shared.API + '/' + uid if uid in live else shared.API,
                    shared.definition(rule),
                    'PUT' if uid in live else 'POST',
                    editable=provenance == '',
                )
            differences = shared.drift(desired, scoped.rules())
    after = snapshot(api, targets)
    receipt['unchanged_after'] = after
    if before != after:
        raise ValueError('non-target alerts or dashboards changed; retain backup and investigate concurrent changes')
    receipt.update(
        {
            'status': 'failed-readback' if backup and differences else 'complete',
            'mode': ('restore' if restore else 'apply') if backup else 'dry-run',
            'targets': sorted(targets),
            'differences': differences,
            'unchanged_before': before,
            'unchanged_after': after,
            'selected_readback': scoped.rules(),
        }
    )
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-uids', required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--backup-file', type=Path)
    parser.add_argument('--restore-file', type=Path)
    parser.add_argument('--receipt-file', type=Path, required=True)
    args = parser.parse_args()
    try:
        targets = select_uids(args.target_uids)
        if len(args.source_sha) != 40 or any(c not in '0123456789abcdef' for c in args.source_sha):
            raise ValueError('source SHA must be an exact lowercase commit SHA')
        if args.apply != (args.backup_file is not None):
            raise ValueError('--apply requires a fresh --backup-file; dry-run forbids it')
        if args.receipt_file.exists():
            raise ValueError('receipt file already exists')
        rules = shared.load_rules(shared.RULES)
        desired = {uid: rules[uid] for uid in targets}
        if args.restore_file:
            restore_plan(args.restore_file, targets)  # Refuse invalid scope before any network call.
        token = os.environ.get('MONITOR_GRAFANA_TOKEN', '').strip()
        if not token:
            raise ValueError('MONITOR_GRAFANA_TOKEN is empty')
        api = shared.Grafana('https://monitor.omi.me', token)
        receipt = {'source_sha': args.source_sha, 'status': 'incomplete'}
        fd = os.open(args.receipt_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as handle:
            try:
                execute(api, desired, targets, backup=args.backup_file, restore=args.restore_file, evidence=receipt)
            finally:
                if args.backup_file and args.backup_file.exists():
                    receipt['backup_sha256'] = hashlib.sha256(args.backup_file.read_bytes()).hexdigest()
                json.dump(receipt, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
        print(f'{receipt["mode"]}: {len(targets)} selected alerts; non-target resources unchanged')
        return int(bool(args.apply and receipt['differences']))
    except (ValueError, OSError, KeyError, TypeError):
        # No rule bodies, dashboard contents or credentials in logs.
        print('FAIL: scoped provisioning refused or readback failed; retain backup artifacts', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
