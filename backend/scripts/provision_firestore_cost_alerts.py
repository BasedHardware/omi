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
WORKFLOW_PATH = '.github/workflows/firestore_cost_alert_provisioning.yml'


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


def validate_restore_evidence(receipt, backup_bytes, run_metadata, expected_run_id, targets):
    """Bind rollback inputs to the original successful-or-partial scoped apply run."""
    expected_id = str(expected_run_id)
    if not expected_id.isdecimal():
        raise ValueError('restore run ID must be numeric')
    if not isinstance(run_metadata, dict):
        raise ValueError('restore run metadata is invalid')
    if str(run_metadata.get('id', '')) != expected_id:
        raise ValueError('restore metadata run ID mismatch')
    if (
        run_metadata.get('path') != WORKFLOW_PATH
        or run_metadata.get('head_branch') != 'main'
        or run_metadata.get('event') != 'workflow_dispatch'
        or run_metadata.get('status') != 'completed'
        or run_metadata.get('conclusion') not in {'success', 'failure', 'cancelled', 'timed_out'}
    ):
        raise ValueError('restore must reference a completed main dispatch of the scoped workflow')
    head_sha = run_metadata.get('head_sha')
    if not isinstance(head_sha, str) or len(head_sha) != 40 or any(c not in '0123456789abcdef' for c in head_sha):
        raise ValueError('restore run metadata has an invalid source SHA')
    if not isinstance(receipt, dict):
        raise ValueError('restore receipt is invalid')
    if str(receipt.get('run_id', '')) != expected_id:
        raise ValueError('restore receipt run ID mismatch')
    if receipt.get('operation') != 'apply' or receipt.get('mode') != 'apply':
        raise ValueError('restore artifact must come from an apply operation')
    if receipt.get('source_sha') != head_sha:
        raise ValueError('restore receipt source SHA does not match its workflow run')
    expected_targets = sorted(targets)
    if expected_targets != sorted(TARGETS) or receipt.get('targets') != expected_targets:
        raise ValueError('restore receipt must cover exactly the approved Firestore UIDs')
    selected_expected = receipt.get('selected_expected')
    if not isinstance(selected_expected, dict) or set(selected_expected) != targets:
        raise ValueError('restore receipt has no complete original selected definition')
    if any(not isinstance(rule, dict) or rule.get('uid') != uid for uid, rule in selected_expected.items()):
        raise ValueError('restore receipt selected definitions are invalid')
    backup_sha256 = receipt.get('backup_sha256')
    if (
        not isinstance(backup_sha256, str)
        or len(backup_sha256) != 64
        or any(c not in '0123456789abcdef' for c in backup_sha256)
    ):
        raise ValueError('restore receipt is missing a valid backup checksum')
    if hashlib.sha256(backup_bytes).hexdigest() != backup_sha256:
        raise ValueError('restore backup checksum mismatch')
    return receipt


def load_restore_evidence(receipt_path, backup_path, metadata_path, expected_run_id, targets):
    try:
        receipt = json.loads(receipt_path.read_text())
        metadata = json.loads(metadata_path.read_text())
        backup_bytes = backup_path.read_bytes()
    except (OSError, ValueError, UnicodeError):
        raise ValueError('restore evidence files are missing or invalid') from None
    return validate_restore_evidence(receipt, backup_bytes, metadata, expected_run_id, targets)


def safe_error_diagnostic(error):
    """Return a short diagnostic without response bodies, credentials, or filesystem paths."""
    if isinstance(error, OSError):
        message = f'errno={error.errno}; {error.strerror or "filesystem operation failed"}'
    else:
        message = str(error)
    return {'type': type(error).__name__, 'message': message[:240]}


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


def execute(
    api,
    desired,
    targets,
    *,
    backup=None,
    restore=None,
    evidence=None,
    restore_evidence=None,
    run_id='unit-test',
):
    if not targets or not targets <= TARGETS or set(desired) != targets:
        raise ValueError('desired rules must cover exactly the selected Firestore UIDs')
    if backup is not None and targets != TARGETS:
        raise ValueError('apply and restore require exactly the three approved Firestore UIDs')
    if restore is not None and restore_evidence is None:
        raise ValueError('restore requires the originating apply receipt')
    if restore_evidence is not None:
        validate_restore_evidence_shape(restore_evidence, targets)
    saved, created = restore_plan(restore, targets) if restore else ({}, [])
    receipt = evidence if evidence is not None else {}
    operation = 'restore' if restore else 'apply' if backup else 'dry-run'
    mode = operation if backup else 'dry-run'
    receipt.update(
        status='incomplete',
        operation=operation,
        mode=mode,
        run_id=str(run_id),
        targets=sorted(targets),
        selected_expected=saved if restore else desired,
    )
    organization = api.request('/api/org')
    if not isinstance(organization, dict) or type(organization.get('id')) is not int or organization['id'] != 1:
        raise ValueError('refusing Grafana organization other than Ops (id 1)')
    receipt['grafana_org_id'] = 1
    before = snapshot(api, targets)
    receipt['unchanged_before'] = before
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
        receipt['restore_deleted'] = {}
        if any(live[uid].get('provenance', '') not in ('', 'api') for uid in created if uid in live):
            raise ValueError('restore cannot delete rules owned by another provisioner')
        # Restore can delete only UIDs that the original selected apply created.
        differences = shared.drift(saved, scoped.rules())
        verify_canaries(api, live, saved)
        if backup:
            write_json(
                backup,
                {
                    'rules': list(scoped.rules().values()),
                    'created_uids': sorted(targets - live.keys()),
                },
            )
            for uid, rule in saved.items():
                scoped.request(
                    shared.API + '/' + uid if uid in live else shared.API,
                    shared.definition(rule),
                    'PUT' if uid in live else 'POST',
                    editable=rule.get('provenance', '') == '',
                )
            for uid in created:
                current = scoped.rules()
                if uid in current:
                    expected = restore_evidence['selected_expected'][uid]
                    if current[uid].get('provenance', '') not in ('', 'api'):
                        raise ValueError(f'restore cannot delete rule {uid} owned by another provisioner')
                    if shared.comparable(current[uid]) != shared.comparable(expected):
                        raise ValueError(f'restore refuses to delete changed rule {uid}')
                    deleted_definition = shared.comparable(current[uid])
                    scoped.request(shared.API + '/' + uid, method='DELETE')
                    receipt['restore_deleted'][uid] = {
                        'definition': deleted_definition,
                        'sha256': fingerprint(deleted_definition),
                    }
            current = scoped.rules()
            differences = shared.drift(saved, current)
    else:
        differences = shared.drift(desired, scoped.rules())
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
        if backup:
            # Unlike bundle reconciliation, this path must never install or
            # repair canaries. Existing committed canaries must already pass.
            write_json(
                backup,
                {
                    'rules': list(scoped.rules().values()),
                    'created_uids': sorted(targets - live.keys()),
                },
            )
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


def validate_restore_evidence_shape(receipt, targets):
    if (
        not isinstance(receipt, dict)
        or receipt.get('operation') != 'apply'
        or receipt.get('mode') != 'apply'
        or receipt.get('targets') != sorted(targets)
        or not isinstance(receipt.get('selected_expected'), dict)
        or set(receipt['selected_expected']) != targets
    ):
        raise ValueError('restore requires a complete receipt from the original selected apply')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-uids', required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--backup-file', type=Path)
    parser.add_argument('--restore-file', type=Path)
    parser.add_argument('--restore-receipt-file', type=Path)
    parser.add_argument('--restore-run-metadata-file', type=Path)
    parser.add_argument('--restore-run-id')
    parser.add_argument('--receipt-file', type=Path, required=True)
    args = parser.parse_args()
    try:
        targets = select_uids(args.target_uids)
        if len(args.source_sha) != 40 or any(c not in '0123456789abcdef' for c in args.source_sha):
            raise ValueError('source SHA must be an exact lowercase commit SHA')
        if args.apply != (args.backup_file is not None):
            raise ValueError('--apply requires a fresh --backup-file; dry-run forbids it')
        if args.apply and targets != TARGETS:
            raise ValueError('apply and restore require exactly the three approved Firestore UIDs')
        if args.receipt_file.exists():
            raise ValueError('receipt file already exists')
        rules = shared.load_rules(shared.RULES)
        desired = {uid: rules[uid] for uid in targets}
        if args.restore_file:
            restore_plan(args.restore_file, targets)  # Refuse invalid scope before any network call.
            if (
                not args.apply
                or not args.restore_receipt_file
                or not args.restore_run_metadata_file
                or not args.restore_run_id
            ):
                raise ValueError('restore requires apply mode, original receipt, run metadata, and run ID')
            prior_receipt = load_restore_evidence(
                args.restore_receipt_file,
                args.restore_file,
                args.restore_run_metadata_file,
                args.restore_run_id,
                targets,
            )
        elif any(
            (
                args.restore_receipt_file,
                args.restore_run_metadata_file,
                args.restore_run_id,
            )
        ):
            raise ValueError('restore evidence arguments require --restore-file')
        else:
            prior_receipt = None
        if not args.run_id.isdecimal():
            raise ValueError('run ID must be numeric')
        token = os.environ.get('MONITOR_GRAFANA_TOKEN', '').strip()
        if not token:
            raise ValueError('MONITOR_GRAFANA_TOKEN is empty')
        api = shared.Grafana('https://monitor.omi.me', token)
        operation = 'restore' if args.restore_file else 'apply' if args.apply else 'dry-run'
        receipt = {
            'source_sha': args.source_sha,
            'run_id': args.run_id,
            'operation': operation,
            'mode': operation,
            'status': 'incomplete',
        }
        fd = os.open(args.receipt_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as handle:
            try:
                execute(
                    api,
                    desired,
                    targets,
                    backup=args.backup_file,
                    restore=args.restore_file,
                    evidence=receipt,
                    restore_evidence=prior_receipt,
                    run_id=args.run_id,
                )
            except (ValueError, OSError, KeyError, TypeError) as exc:
                receipt['error'] = safe_error_diagnostic(exc)
                raise
            finally:
                if args.backup_file and args.backup_file.exists():
                    receipt['backup_sha256'] = hashlib.sha256(args.backup_file.read_bytes()).hexdigest()
                json.dump(receipt, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
        print(f'{receipt["mode"]}: {len(targets)} selected alerts; non-target resources unchanged')
        return int(bool(args.apply and receipt['differences']))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        # Diagnostics contain only a bounded reason; no response body or credential is logged.
        diagnostic = safe_error_diagnostic(exc)
        print(f'FAIL: {diagnostic["type"]}: {diagnostic["message"]}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
