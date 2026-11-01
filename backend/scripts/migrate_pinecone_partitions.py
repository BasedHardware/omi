#!/usr/bin/env python3
"""Bounded operator inventory, pilot, migration and fresh-copy rollback."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import pinecone_partition_state as state
from database._client import get_data_plane_firestore_client
from database.pinecone_partition_migration import MigrationNotReady, OwnerMigration, PartitionTransport

CORE_WRITERS = {'backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration', 'backend-listen', 'pusher'}
DEV_INDEX = 'memories-backend-dev'


class OperatorGateError(ValueError):
    pass


class BudgetExceeded(RuntimeError):
    pass


def positive(value: str) -> int:
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError('must be positive')
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', default=os.getenv('PINECONE_INDEX_NAME'))
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--uid', action='append', help='Repeat for explicit owners; never accepts a wildcard.')
    selection.add_argument('--uids-file', type=Path, help='Private UTF-8 file with one UID per line.')
    selection.add_argument('--sweep', action='store_true', help='Discover bounded registered legacy routes.')
    parser.add_argument('--family', action='append', choices=sorted(state.FAMILIES))
    parser.add_argument('--apply', action='store_true', help='Actually copy and switch qualified routes.')
    parser.add_argument(
        '--rollback', action='store_true', help='Reconcile current primary into the old namespace first.'
    )
    parser.add_argument('--resume', action='store_true', help='Resume only migrations owned by this output journal.')
    parser.add_argument('--pilot', action='store_true', help='Production test users explicitly listed in the proof.')
    parser.add_argument('--output-dir', type=Path, required=True, help='Private durable journal and receipt directory.')
    parser.add_argument('--fleet-receipt', type=Path)
    parser.add_argument('--test-user-proof', type=Path)
    parser.add_argument('--max-owners', type=positive, default=10)
    parser.add_argument('--max-route-docs', type=positive, default=10000)
    parser.add_argument('--max-attempts', type=positive, default=2)
    parser.add_argument('--max-provider-requests', type=positive, default=1000)
    parser.add_argument('--max-read-units', type=positive, default=10000)
    parser.add_argument('--max-write-units', type=positive, default=10000)
    parser.add_argument('--max-upload-bytes', type=positive, default=100_000_000)
    parser.add_argument('--emulator-project', help='Only demo-* projects with FIRESTORE_EMULATOR_HOST set.')
    args = parser.parse_args(argv)
    if not args.index or args.max_owners > 10000 or args.max_route_docs > 100000 or args.max_attempts > 3:
        parser.error('index required; bounds: owners<=10000, route-docs<=100000, attempts<=3')
    if args.sweep and (args.rollback or args.pilot):
        parser.error('rollback/pilot require explicit owners')
    if args.emulator_project and (
        not os.getenv('FIRESTORE_EMULATOR_HOST') or not args.emulator_project.startswith('demo-')
    ):
        parser.error('--emulator-project requires a demo-* project and FIRESTORE_EMULATOR_HOST')
    if args.index != DEV_INDEX and (args.emulator_project or os.getenv('FIRESTORE_EMULATOR_HOST')):
        parser.error('production index must use the real serving route authority, never an emulator')
    return args


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, sort_keys=True, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path: Path) -> dict:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise OperatorGateError('receipt must be an object')
    return data


def artifact(entry: dict, base: Path) -> dict:
    path = (base / entry['path']).resolve()
    data = path.read_bytes()
    if sha256(data).hexdigest() != entry.get('sha256'):
        raise OperatorGateError('evidence artifact hash does not match')
    return json.loads(data)


def production_gate(args: argparse.Namespace, owners: list[str]) -> dict:
    if not args.apply or args.index == DEV_INDEX:
        return {}
    if not args.fleet_receipt or not args.test_user_proof:
        raise OperatorGateError('production apply requires reviewed fleet and test-user evidence')
    fleet, proof = read_json(args.fleet_receipt), read_json(args.test_user_proof)
    commit = fleet.get('implementation_commit', '')
    if (
        fleet.get('schema_version') != 1
        or fleet.get('index_name') != args.index
        or not re.fullmatch('[0-9a-f]{40}', commit)
        or not fleet.get('reviewed_by')
        or fleet.get('writer_inventory_complete') is not True
    ):
        raise OperatorGateError('fleet review, index or implementation identity is missing')
    try:
        reviewed = datetime.fromisoformat(fleet['reviewed_at'].replace('Z', '+00:00'))
        age = (datetime.now(timezone.utc) - reviewed).total_seconds()
    except (KeyError, TypeError, ValueError) as error:
        raise OperatorGateError('fleet review timestamp is invalid') from error
    if not 0 <= age <= 86400:
        raise OperatorGateError('fleet evidence must be reviewed within 24 hours of this run')
    inventory = artifact(fleet['writer_inventory_artifact'], args.fleet_receipt.parent)
    writers = fleet.get('writers', [])
    names = {writer.get('name') for writer in writers}
    if names != set(inventory.get('writer_names', [])) or not CORE_WRITERS <= names or len(names) != len(writers):
        raise OperatorGateError('complete reviewed writer inventory must include every core surface')
    for writer in writers:
        if (
            not re.fullmatch('[0-9a-f]{40}', writer.get('source_sha', ''))
            or not re.search(r'@sha256:[0-9a-f]{64}$', writer.get('image', ''))
            or writer.get('implementation_present') is not True
            or writer.get('runtime_verified') is not True
        ):
            raise OperatorGateError('every writer needs immutable image, source and verified implementation')
        artifact(writer['evidence'], args.fleet_receipt.parent)
    if (
        proof.get('schema_version') != 1
        or proof.get('status') != 'GO'
        or proof.get('implementation_commit') != commit
        or set(proof.get('families_verified', [])) != state.FAMILIES
        or proof.get('real_user_path_verified') is not True
        or proof.get('cleanup_verified') is not True
        or type(proof.get('repeats')) is not int
        or proof['repeats'] < 3
        or not proof.get('artifacts')
    ):
        raise OperatorGateError('GO proof must verify all families, repeated real user paths and cleanup')
    for entry in proof['artifacts']:
        artifact(entry, args.test_user_proof.parent)
    if args.pilot:
        allowed = set(proof.get('allowed_production_test_uids', []))
        if not owners or not set(owners) <= allowed:
            raise OperatorGateError('pilot owners must be explicitly identified test accounts in the reviewed proof')
    elif proof.get('stage') != 'production_pilot' or proof.get('index_name') != args.index:
        raise OperatorGateError('general rollout requires a successful production test-user pilot')
    return {
        'implementation_commit': commit,
        'fleet_receipt_sha256': sha256(args.fleet_receipt.read_bytes()).hexdigest(),
        'test_user_proof_sha256': sha256(args.test_user_proof.read_bytes()).hexdigest(),
    }


def select_keys(args: argparse.Namespace, db: Any) -> tuple[list[state.PartitionKey], dict]:
    families = set(args.family or state.FAMILIES)
    if not args.sweep:
        raw = args.uid or args.uids_file.read_text().splitlines()
        owners = list(dict.fromkeys(uid.strip() for uid in raw if uid.strip()))
        if not owners or len(owners) > args.max_owners:
            raise OperatorGateError('explicit owner list must be nonempty and within --max-owners')
        return [state.PartitionKey(args.index, family, uid) for uid in owners for family in sorted(families)], {
            'owners': len(owners),
            'route_documents_scanned': 0,
            'scan_complete': True,
        }
    from google.cloud.firestore_v1.base_query import FieldFilter

    owners: set[str] = set()
    keys: dict[str, state.PartitionKey] = {}
    scanned = 0
    deferred_owners: set[str] = set()
    # One indexed field per query; spend a shared document budget across modes.
    # Resume copying first so failed attempts cannot starve behind fresh owners.
    modes = ['copying', 'legacy'] if args.resume else ['legacy']
    scan_complete = True
    for mode in modes:
        remaining = args.max_route_docs - scanned
        if not remaining:
            scan_complete = False
            break
        query = db.collection(state.COLLECTION).where(filter=FieldFilter('mode', '==', mode)).limit(remaining)
        mode_scanned = 0
        for snapshot in query.stream():
            scanned += 1
            mode_scanned += 1
            row = snapshot.to_dict()
            if row.get('index_name') != args.index or row.get('family') not in families:
                continue
            uid = row.get('uid')
            if not isinstance(uid, str) or not uid:
                raise OperatorGateError('route owner identity is invalid')
            if uid not in owners and len(owners) >= args.max_owners:
                deferred_owners.add(uid)
                continue
            key = state.PartitionKey(args.index, row['family'], uid)
            if snapshot.id != key.document_id:
                raise OperatorGateError('route document identity does not match its contents')
            owners.add(uid)
            keys[key.document_id] = key
        if mode_scanned == remaining:
            scan_complete = False
    return list(keys.values()), {
        'owners': len(owners),
        'route_documents_scanned': scanned,
        'queried_modes': modes,
        'scan_complete': scan_complete and not deferred_owners,
        'deferred_owners_in_scan': len(deferred_owners),
    }


class BudgetTransport(PartitionTransport):
    def __init__(self, host: str, api_key: str, args: argparse.Namespace):
        super().__init__(host, api_key)
        self.args = args
        self.requests = 0
        self.upload_bytes = 0

    def check_budget(self, path: str, payload: dict) -> None:
        upload = len(json.dumps(payload).encode()) if path in {'vectors/upsert', 'vectors/update'} else 0
        if (
            self.requests >= self.args.max_provider_requests
            or self.read_units >= self.args.max_read_units
            or self.write_units >= self.args.max_write_units
            or self.upload_bytes + upload > self.args.max_upload_bytes
        ):
            raise BudgetExceeded('provider budget exhausted; rerun from the owned journal after review')

    def call(self, path: str, payload: dict) -> tuple[dict, dict]:
        self.check_budget(path, payload)
        self.requests += 1
        if path in {'vectors/upsert', 'vectors/update'}:
            self.upload_bytes += len(json.dumps(payload).encode())
        body, headers = super().call(path, payload)
        usage = body.get('usage') or {}
        # Provider endpoints use both spellings. Parent transport counts camelCase.
        if 'readUnits' not in usage:
            self.read_units += usage.get('read_units', 0)
        if 'writeUnits' not in usage:
            self.write_units += usage.get('write_units', 0)
        return body, headers


class BoundedMigration(OwnerMigration):
    def _write(self, token: str, path: str, namespace: str, scoped_ids: list[str], **payload: Any) -> int:
        # Refuse before durable write admission: a budget stop is not an
        # uncertain provider request and must not poison the route.
        self.transport.check_budget(path, {'namespace': namespace, **payload})
        return super()._write(token, path, namespace, scoped_ids, **payload)


def process_key(args: argparse.Namespace, key: state.PartitionKey, db: Any, transport: BudgetTransport) -> dict:
    journal_path = args.output_dir / 'owners' / f'{key.document_id}.json'
    if not args.apply:
        snapshot = db.collection(state.COLLECTION).document(key.document_id).get()
        # Serving get_route registers missing rows. Operator inventory must not.
        route = state._route(state._snapshot_row(snapshot, key))
        return {
            'key_id': key.document_id,
            'family': key.family,
            'before': asdict(route),
            'registered': snapshot.exists,
            'status': 'inventory',
        }
    route = state.get_route(key, firestore_client=db)
    result = {'key_id': key.document_id, 'family': key.family, 'before': asdict(route)}
    desired = 'legacy' if args.rollback else 'partitioned'
    if route.mode == desired:
        return {**result, 'status': 'already_complete'}
    if route.pending_count or route.uncertain_count:
        return {**result, 'status': 'blocked_unsettled_operations'}
    journal = read_json(journal_path) if journal_path.exists() else None
    if route.mode == 'copying':
        if (
            not args.resume
            or not journal
            or (
                journal.get('key') != asdict(key)
                or journal.get('rollback') is not args.rollback
                or journal.get('migration_token') != route.migration_token
            )
        ):
            return {**result, 'status': 'blocked_foreign_or_unowned_migration'}
        token = journal['migration_token']
    else:
        token = uuid4().hex
        journal = {'schema_version': 1, 'key': asdict(key), 'rollback': args.rollback, 'migration_token': token}
    atomic_json(journal_path, {**journal, 'status': 'reserved_locally'})
    migration = BoundedMigration(key, transport, firestore_client=db)
    for attempt in range(1, args.max_attempts + 1):
        try:
            route = state.get_route(key, firestore_client=db)
            if route.pending_count or route.uncertain_count:
                return {**result, 'status': 'blocked_unsettled_operations'}
            receipt = migration.qualify(token, dimension=args.dimension, rollback=args.rollback)
            atomic_json(journal_path, {**journal, 'status': 'qualified', 'attempt': attempt, 'receipt': receipt})
            after = state.cutover(key, token, receipt['revision'], receipt, firestore_client=db)
            atomic_json(journal_path, {**journal, 'status': 'complete', 'receipt': receipt, 'after': asdict(after)})
            return {**result, 'status': 'complete', 'records': receipt['records'], 'after': asdict(after)}
        except (MigrationNotReady, state.PartitionConflict) as error:
            route = state.get_route(key, firestore_client=db)
            if route.pending_count or route.uncertain_count:
                status = 'blocked_unsettled_operations'
            elif attempt < args.max_attempts:
                continue
            else:
                status = 'qualification_failed'
            atomic_json(
                journal_path, {**journal, 'status': status, 'error_type': type(error).__name__, 'attempt': attempt}
            )
            return {**result, 'status': status, 'error_type': type(error).__name__}
        except Exception as error:
            atomic_json(
                journal_path, {**journal, 'status': 'stopped', 'error_type': type(error).__name__, 'attempt': attempt}
            )
            if isinstance(error, BudgetExceeded):
                raise
            return {**result, 'status': 'stopped', 'error_type': type(error).__name__}
    raise AssertionError('bounded attempt loop did not terminate')


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(args.output_dir, 0o700)
    run_path = args.output_dir / f'run-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid4().hex[:8]}.json'
    report: dict = {
        'schema_version': 1,
        'index_name': args.index,
        'apply': args.apply,
        'rollback': args.rollback,
        'results': [],
    }
    transport = None
    try:
        if args.emulator_project:
            from google.auth.credentials import AnonymousCredentials
            from google.cloud import firestore

            db = firestore.Client(project=args.emulator_project, credentials=AnonymousCredentials())
        else:
            db = get_data_plane_firestore_client()
        keys, inventory = select_keys(args, db)
        report['inventory'] = inventory
        report['gates'] = production_gate(args, list({key.uid for key in keys}))
        if args.apply:
            from pinecone import Pinecone

            api_key = os.environ.get('PINECONE_API_KEY')
            if not api_key:
                raise OperatorGateError('PINECONE_API_KEY must be provided through the existing secret environment')
            control = Pinecone(api_key=api_key)
            info = control.describe_index(args.index)
            if info.name != args.index or not info.status.ready:
                raise OperatorGateError('configured Pinecone index is not ready')
            args.dimension = info.dimension
            transport = BudgetTransport(info.host, api_key, args)
        for key in keys:
            report['results'].append(process_key(args, key, db, transport))
            atomic_json(run_path, report)
        report['status'] = (
            'GO'
            if all(row['status'] in {'inventory', 'complete', 'already_complete'} for row in report['results'])
            else 'PARTIAL'
        )
        if inventory['scan_complete'] is False:
            report['status'] = 'PARTIAL'
    except Exception as error:
        report['status'] = 'STOPPED'
        report['error_type'] = type(error).__name__
        if isinstance(error, (OperatorGateError, BudgetExceeded)):
            report['reason'] = str(error)
    finally:
        if transport:
            report['provider_usage'] = {
                'requests': transport.requests,
                'read_units': transport.read_units,
                'write_units': transport.write_units,
                'upload_bytes': transport.upload_bytes,
            }
            transport.client.close()
        report['completed_at'] = datetime.now(timezone.utc).isoformat()
        atomic_json(run_path, report)
    print(json.dumps({'status': report['status'], 'processed': len(report['results']), 'receipt': str(run_path)}))
    return 0 if report['status'] == 'GO' else 2


if __name__ == '__main__':
    raise SystemExit(main())
