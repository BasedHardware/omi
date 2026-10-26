#!/usr/bin/env python3
# LIFECYCLE: permanent
"""Private, read-only-by-default readiness and bounded operator sync redrive.

Run from backend with PYTHONPATH=. No user API, audio downloads, conversation
reads or transcript reads. Apply is for the rollout lead under prod-operator.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time
from typing import Any
import uuid

import google.auth
from google.api_core.exceptions import NotFound, PermissionDenied
from google.auth.transport.requests import AuthorizedSession
from google.cloud import firestore, storage, tasks_v2
from google.cloud.firestore_v1.base_query import FieldFilter

from database.redis_connection import create_bounded_redis_client
from utils.cloud_tasks import enqueue_sync_job_redrive, sync_job_payload_keys_valid
from utils.sync.incident_redrive import (
    Evidence,
    FIX_COMMIT,
    LEDGER_FIELDS,
    OPTIONAL_FIELDS,
    PAYLOAD_FIELDS,
    POPULATIONS,
    REASONS,
    SERVICES,
    classify,
    digest,
    evidence_digest,
    operation_key,
    resolve_payload,
    select_population,
    serving_commits_valid,
)

PROJECT = 'based-hardware'
REGION = 'us-central1'
REPOSITORY = Path(__file__).resolve().parents[2]
PAYLOAD_MASK = [f'payload.{k}' for k in PAYLOAD_FIELDS + OPTIONAL_FIELDS]
OWNER_MASK = ['active_job_id'] + [f'active_payload.{k}' for k in PAYLOAD_FIELDS + OPTIONAL_FIELDS]
LOCK_RELEASE = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end return 0"
RESET_JOB = """
if redis.call('get', KEYS[1]) ~= ARGV[1] then return 0 end
if redis.call('get', KEYS[2]) ~= ARGV[2] then return 0 end
redis.call('set', KEYS[2], ARGV[3], 'EX', 86400)
return 1
"""


class Blocked(Exception):
    """Only closed reason tokens may cross the CLI exception boundary."""


def private_path(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
        raise Blocked('invalid_input')


def atomic_private_write(path: Path, data: dict) -> None:
    if path.exists() or path.is_symlink():
        private_path(path)
    fd, temporary = tempfile.mkstemp(prefix='.redrive-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as target:
            json.dump(data, target, default=str)
            target.write('\n')
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class ReadInventory:
    """Read capability: projected Firestore reads, GetTask, GCS metadata, Redis GET.

    Deliberately does not expose enqueue, transactions, Redis EVAL/SET, download,
    conversation references, provider calls, or writes of any kind.
    """

    def __init__(self, *, runtime_redis: bool = False):
        credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
        self.firestore = firestore.Client(project=PROJECT, credentials=credentials)
        self.tasks = tasks_v2.CloudTasksClient(credentials=credentials)
        self.storage = storage.Client(project=PROJECT, credentials=credentials)
        self.http = AuthorizedSession(credentials)
        self.redis = create_bounded_redis_client(3) if runtime_redis else None
        self.documents: dict[str, dict] = {}
        self.owners: dict[str, dict] = {}
        self.queues: list[str] = []
        self.denied_queues: set[str] = set()
        self.task_cache: dict[tuple[str, str], dict | None] = {}
        self.services: dict[str, dict] = {}
        self.revisions: dict[str, list[dict]] = {}

    def run_metadata(self) -> dict[str, list[str]]:
        commits = {}
        for name in SERVICES:
            base = f'https://{REGION}-run.googleapis.com/apis/serving.knative.dev/v1/namespaces/{PROJECT}'
            reply = self.http.get(f'{base}/services/{name}', timeout=20)
            reply.raise_for_status()
            service = reply.json()
            self.services[name] = service
            traffic = service.get('status', {}).get('traffic', [])
            names = {t.get('revisionName') for t in traffic if t.get('percent', 0) > 0}
            if not names or None in names or sum(t.get('percent', 0) for t in traffic) != 100:
                raise Blocked('serving_commit_unverified')
            revisions = []
            for revision in sorted(names):
                reply = self.http.get(f'{base}/revisions/{revision}', timeout=20)
                reply.raise_for_status()
                revisions.append(reply.json())
            self.revisions[name] = revisions
            commits[name] = [self.literal_env(r).get('OMI_BACKEND_RELEASE_SHA', '') for r in revisions]
        # Source discovery must inspect each actual traffic revision's queues.
        self.queues = sorted(
            {
                self.tasks.queue_path(PROJECT, self.literal_env(r).get('SYNC_TASKS_LOCATION', REGION), value)
                for revisions in self.revisions.values()
                for r in revisions
                for key, value in self.literal_env(r).items()
                if key in ('SYNC_TASKS_QUEUE', 'SYNC_BACKFILL_TASKS_QUEUE') and value
            }
        )
        return commits

    @staticmethod
    def literal_env(revision: dict) -> dict[str, str]:
        return {e['name']: e['value'] for e in revision['spec']['containers'][0].get('env', []) if 'value' in e}

    def preload(self, rows: list[dict]) -> None:
        for collection, fields in (
            ('sync_redrive_required', ['uid', 'job_id', 'status'] + PAYLOAD_MASK),
            ('sync_backfill_pending', ['uid', 'job_id', 'status'] + PAYLOAD_MASK),
            ('sync_dead_letters', ['uid', 'job_id', 'status', 'lane', 'failure_code']),
        ):
            refs = [self.firestore.collection(collection).document(r['job_id']) for r in rows]
            for start in range(0, len(refs), 100):
                for snapshot in self.firestore.get_all(refs[start : start + 100], field_paths=fields, timeout=20):
                    self.documents[snapshot.reference.path] = snapshot.to_dict() or {}
        uids = {
            row.get('redrive_key', {}).get('uid')
            or next(
                (
                    self.documents.get(f'{c}/{row["job_id"]}', {}).get('uid')
                    for c in ('sync_redrive_required', 'sync_backfill_pending', 'sync_dead_letters')
                    if self.documents.get(f'{c}/{row["job_id"]}', {}).get('uid')
                ),
                None,
            )
            for row in rows
        } - {None, ''}
        refs = [self.firestore.collection('sync_backfill_sequencer').document(uid) for uid in sorted(uids)]
        for start in range(0, len(refs), 100):
            for snapshot in self.firestore.get_all(refs[start : start + 100], field_paths=OWNER_MASK, timeout=20):
                self.owners[snapshot.id] = snapshot.to_dict() or {}

        # Probe access once per queue before parallel work. Access denial is a
        # source-discovery blocker, never thousands of identical failed reads.
        if rows:
            for queue in self.queues:
                self.task_payload(queue, rows[0]['job_id'])

    def task_payload(self, queue: str, job_id: str) -> dict | None:
        if queue in self.denied_queues:
            return None
        cache_key = (queue, job_id)
        if cache_key in self.task_cache:
            return self.task_cache[cache_key]
        try:
            task = self.tasks.get_task(
                request={'name': f'{queue}/tasks/{job_id}', 'response_view': tasks_v2.Task.View.FULL},
                retry=None,
                timeout=10,
            )
            payload = json.loads(task.http_request.body)
            if not isinstance(payload, dict) or not sync_job_payload_keys_valid(payload):
                raise Blocked('payload_invalid')
        except NotFound:
            payload = None
        except PermissionDenied:
            self.denied_queues.add(queue)
            return None
        self.task_cache[cache_key] = payload
        return payload

    def ledger_ref(self, uid: str, content_id: str) -> Any:
        return self.firestore.collection('users').document(uid).collection('sync_content_ledger').document(content_id)

    def inspect(self, row: dict) -> Evidence:
        evidence = Evidence()
        try:
            job_id = row['job_id']
            uid = row.get('redrive_key', {}).get('uid')
            for collection in ('sync_redrive_required', 'sync_backfill_pending', 'sync_dead_letters'):
                doc = self.documents.get(f'{collection}/{job_id}', {})
                evidence.source_checks[collection] = 'present' if doc else 'absent'
                uid = uid or doc.get('uid')
                if isinstance(doc.get('payload'), dict):
                    evidence.payloads[collection] = doc['payload']
            owner = self.owners.get(uid, {})
            if owner.get('active_job_id') == job_id and isinstance(owner.get('active_payload'), dict):
                evidence.payloads['sync_backfill_sequencer.active_payload'] = owner['active_payload']
            evidence.source_checks['sync_backfill_sequencer'] = 'present' if owner else 'absent'
            evidence.active_owner = bool(owner.get('active_job_id'))
            for queue in self.queues:
                task_payload = self.task_payload(queue, job_id)
                source = 'cloud_tasks.' + queue.rsplit('/', 1)[-1]
                evidence.source_checks[source] = (
                    'access_denied' if queue in self.denied_queues else 'present' if task_payload else 'absent'
                )
                if task_payload:
                    evidence.payloads[source] = task_payload
            evidence.task_read_denied = bool(self.denied_queues)
            payload, _ = resolve_payload(evidence)
            content_id = payload.get('content_id') if payload else row.get('redrive_key', {}).get('content_id')
            uid = uid or (payload or {}).get('uid')
            if content_id and uid:
                evidence.content_id = content_id
                evidence.ledger = (
                    self.ledger_ref(uid, content_id).get(field_paths=list(LEDGER_FIELDS), timeout=15).to_dict()
                )
            elif uid:
                # Only this job's ledger metadata. No collection group scan or
                # customer conversation/profile/transcript reads.
                query = self.firestore.collection('users').document(uid).collection('sync_content_ledger')
                docs = list(
                    query.where(filter=FieldFilter('job_id', '==', job_id))
                    .select(list(LEDGER_FIELDS))
                    .limit(2)
                    .stream(timeout=15)
                )
                if len(docs) == 1:
                    evidence.content_id, evidence.ledger = docs[0].id, docs[0].to_dict()
                    evidence.field_sources['content_id'] = 'sync_content_ledger_document_key'
                elif len(docs) > 1:
                    raise Blocked('identity_conflict')
            if evidence.ledger:
                evidence.field_sources.update(
                    {
                        k: 'sync_content_ledger'
                        for k in ('partial_result', 'processed_segment_ids')
                        if k in evidence.ledger
                    }
                )
            # Never contact Redis or GCS when original semantic payload is missing.
            if payload and classify(row, evidence) == 'runtime_probe_required' and self.redis is not None:
                evidence.runtime_checked = True
                raw = self.redis.get(f'sync_job:{job_id}')
                evidence.job = json.loads(raw) if raw else None
                evidence.active_owner = evidence.active_owner or bool(self.redis.get(f'sync_job_lock:{job_id}'))
                sources = {o['name']: o for o in row.get('staging_objects', []) if o.get('bucket') == 'syncing-local'}
                evidence.sources_present = True
                for path in payload['raw_blob_paths']:
                    expected = sources.get(path)
                    blob = self.storage.bucket('syncing-local').get_blob(path)
                    if not blob or not expected or str(blob.generation) != str(expected.get('generation')):
                        evidence.sources_present = False
                        break
        except Blocked:
            evidence.read_failed = True
        except Exception:
            evidence.read_failed = True
        return evidence


def contains_fix(sha: str) -> bool:
    if not re.fullmatch('[0-9a-f]{40}', sha):
        return False
    return (
        subprocess.run(
            ['git', 'merge-base', '--is-ancestor', FIX_COMMIT, sha],
            cwd=REPOSITORY,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )


def project_ledger(current: dict) -> dict:
    """Apply the reader's field mask, including concurrently ADDED fields."""
    projected = {}
    for path in LEDGER_FIELDS:
        parts = path.split('.')
        value = current
        for part in parts:
            if not isinstance(value, dict) or part not in value:
                break
            value = value[part]
        else:
            target = projected
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = value
    return projected


@firestore.transactional
def prepare_operation(transaction: Any, ref: Any, expected: dict, marker: dict) -> bool:
    current = ref.get(transaction=transaction).to_dict() or {}
    # Compare every planning field, including checkpoints, metering and ownership.
    projected = project_ledger(current)
    if projected != expected:
        return False
    existing = current.get('openloop_redrive')
    if existing and existing != marker:
        return False
    transaction.update(
        ref,
        {
            'status': 'processing',
            'job_id': marker['job_id'],
            'openloop_redrive': marker,
            'updated_at': datetime.now(timezone.utc),
        },
    )
    return True


@firestore.transactional
def mark_dispatched(transaction: Any, ref: Any, key: str) -> None:
    current = ref.get(transaction=transaction).to_dict() or {}
    marker = current.get('openloop_redrive') or {}
    if marker.get('key') != key:
        raise Blocked('operation_conflict')
    transaction.update(ref, {'openloop_redrive': {**marker, 'state': 'dispatched'}})


def apply_one(
    row: dict,
    evidence: Evidence,
    approved_digest: str,
    inventory: ReadInventory,
    enqueue: Any = enqueue_sync_job_redrive,
) -> str:
    """Hold original run lock; checkpoint-preserving ledger CAS; named-task outbox.

    Never creates a replacement job, changes content identity, writes a row,
    copies audio, or invokes a provider. A prepared operation can resume only
    with the same approved plan; after dispatch it is permanently a no-op.
    """
    reason = classify(row, evidence)
    if reason != 'ready':
        return reason
    payload, _ = resolve_payload(evidence)
    key = operation_key(row, payload['content_id'])
    existing = evidence.ledger.get('openloop_redrive') or {}
    if evidence_digest(evidence) != approved_digest and existing.get('plan_digest') != approved_digest:
        return 'plan_changed'
    redis = inventory.redis
    job_id = row['job_id']
    lock, job_key = f'sync_job_lock:{job_id}', f'sync_job:{job_id}'
    token = 'operator-' + uuid.uuid4().hex
    if not redis.set(lock, token, nx=True, ex=1800):
        return 'active_owner'
    try:
        raw = redis.get(job_key)
        if raw is None or json.loads(raw) != evidence.job:
            return 'plan_changed'
        ref = inventory.ledger_ref(payload['uid'], payload['content_id'])
        marker = existing or {
            'key': key,
            'job_id': job_id,
            'state': 'prepared',
            'plan_digest': approved_digest,
            'enqueue_until': time.time() + 1800,
        }
        if not prepare_operation(inventory.firestore.transaction(), ref, evidence.ledger, marker):
            return 'plan_changed'
        queued = {
            **evidence.job,
            'status': 'queued',
            'completed_at': None,
            'error': None,
            'reason_code': None,
            'updated_at': time.time(),
            'partial_result': evidence.ledger['partial_result'],
            'openloop_redrive_key': key,
        }
        if redis.eval(RESET_JOB, 2, lock, job_key, token, raw, json.dumps(queued)) != 1:
            return 'plan_changed'
        # A lost create acknowledgement retries this exact deterministic name.
        # A successful acknowledgement sets the durable never-enqueue-again marker.
        enqueue(payload, key)
        mark_dispatched(inventory.firestore.transaction(), ref, key)
        return 'dispatched'
    except Exception:
        return 'dispatch_uncertain'
    finally:
        redis.eval(LOCK_RELEASE, 1, lock, token)


def configure_dispatch(inventory: ReadInventory) -> None:
    envs = [inventory.literal_env(r) for r in inventory.revisions['backend-sync']]
    keys = (
        'SYNC_TASKS_PROJECT',
        'SYNC_TASKS_LOCATION',
        'SYNC_TASKS_QUEUE',
        'SYNC_TASKS_INVOKER_SA',
        'SYNC_TASKS_HANDLER_URL',
        'SYNC_TASKS_OIDC_AUDIENCE',
        'SYNC_BACKFILL_TASKS_QUEUE',
        'SYNC_BACKFILL_TASKS_HANDLER_URL',
        'SYNC_BACKFILL_TASKS_OIDC_AUDIENCE',
        'SYNC_BACKFILL_ROUTING_ENABLED',
    )
    config = {k: envs[0].get(k, '') for k in keys}
    if any({k: env.get(k, '') for k in keys} != config for env in envs):
        raise Blocked('operator_runtime_required')
    if config['SYNC_TASKS_PROJECT'] != PROJECT:
        raise Blocked('operator_runtime_required')
    for name, prefix in (('backend-sync', 'SYNC_TASKS'), ('backend-sync-backfill', 'SYNC_BACKFILL_TASKS')):
        url = inventory.services[name]['status']['url'] + '/v2/sync-jobs/run'
        if config[prefix + '_HANDLER_URL'] != url or config[prefix + '_OIDC_AUDIENCE'] not in ('', url):
            raise Blocked('operator_runtime_required')
    # Only literal, non-secret dispatch bindings from the serving revision.
    os.environ.update(config)


def result_record(row: dict, evidence: Evidence, reason: str) -> dict:
    assert reason in REASONS
    return {
        'job_id': row['job_id'],
        'job_ref': row.get('job_ref'),
        'population': row['population'],
        'status': (
            'ready'
            if reason == 'ready'
            else (
                'applied'
                if reason == 'dispatched'
                else 'noop' if reason in ('already_dispatched', 'ledger_completed') else 'blocked'
            )
        ),
        'reason': reason,
        'field_sources': evidence.field_sources,
        'source_checks': evidence.source_checks,
        'evidence_digest': evidence_digest(evidence),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--population', choices=POPULATIONS)
    parser.add_argument('--limit', type=int)
    parser.add_argument(
        '--runtime-redis', action='store_true', help='read runtime Redis metadata; requires its env/network'
    )
    args = parser.parse_args(argv)
    logging.disable(logging.CRITICAL)  # Product/SDK loggers must never print identifiers.
    try:
        if os.getenv('GCP_AGENT_TIER') != ('prod-operator' if args.apply else 'ro-prod'):
            raise Blocked('operator_runtime_required')
        if os.getenv('OMI_ENV_STAGE') != 'prod':
            raise Blocked('operator_runtime_required')
        private_path(args.input)
        source = args.input.resolve()
        if source.is_relative_to(REPOSITORY):
            raise Blocked('invalid_input')
        output = args.output or source.with_suffix('.redrive-results.json')
        if output.parent.resolve() != source.parent or output.resolve() == source or output.is_symlink():
            raise Blocked('invalid_input')
        if args.apply and (args.population is None or args.limit is None or args.limit <= 0 or not args.runtime_redis):
            raise Blocked('invalid_input')
        raw_input = source.read_bytes()
        document = json.loads(raw_input)
        rows = document['jobs']
        if (
            len(rows) != document['count_header']['jobs']
            or len({r['job_id'] for r in rows}) != len(rows)
            or any(not re.fullmatch('[A-Za-z0-9_-]+', r['job_id']) for r in rows)
        ):
            raise Blocked('invalid_input')
        fingerprint = hashlib.sha256(raw_input).hexdigest()
        history = {'input_sha256': fingerprint, 'runs': []}
        if output.exists():
            private_path(output)
            history = json.loads(output.read_text())
            if history['input_sha256'] != fingerprint:
                raise Blocked('plan_changed')
        # Serialize local output histories for concurrent invocations. Cloud
        # ownership still belongs to the Redis lock and the durable ledger CAS.
        lock_path = output.with_suffix(output.suffix + '.lock')
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(lock_fd, 'w') as local_lock:
            fcntl.flock(local_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return run(args, rows, output, history)
    except Exception as error:
        reason = str(error) if isinstance(error, Blocked) and str(error) in REASONS else 'metadata_read_failed'
        print(json.dumps({'counts': {reason: 1}}))
        return 2


def run(args: Any, rows: list[dict], output: Path, history: dict) -> int:
    approved = {}
    if args.apply:
        dry_runs = [r for r in history['runs'] if r['mode'] == 'dry_run']
        if not dry_runs:
            raise Blocked('dry_run_required')
        approved = {r['job_id']: r for r in dry_runs[-1]['results'] if r['reason'] == 'ready'}
        rows = select_population([r for r in rows if r['job_id'] in approved], args.population, args.limit)
        if not rows:
            raise Blocked('no_ready_jobs')
    elif args.population:
        rows = select_population(rows, args.population, args.limit or len(rows))
    elif args.limit is not None:
        raise Blocked('invalid_input')
    run_result = {
        'mode': 'apply' if args.apply else 'dry_run',
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'serving_fix_verified': False,
        'results': [],
    }
    try:
        inventory = ReadInventory(runtime_redis=args.runtime_redis)
        commits = inventory.run_metadata()
        run_result['serving_fix_verified'] = serving_commits_valid(commits, contains_fix)
        if args.apply:
            if not run_result['serving_fix_verified']:
                raise Blocked('serving_commit_unverified')
            configure_dispatch(inventory)
        inventory.preload(rows)
    except Exception as error:
        reason = str(error) if isinstance(error, Blocked) and str(error) in REASONS else 'metadata_read_failed'
        run_result['results'] = [result_record(row, Evidence(read_failed=True), reason) for row in rows]
        run_result['counts'] = {reason: len(rows)}
        history['runs'].append(run_result)
        atomic_private_write(output, history)
        print(json.dumps({'counts': run_result['counts']}))
        return 2
    history['runs'].append(run_result)
    if args.apply:
        for row in rows:
            # Fresh metadata before each mutation; never reuse a dry-run owner.
            inventory.preload([row])
            evidence = inventory.inspect(row)
            try:
                if not serving_commits_valid(inventory.run_metadata(), contains_fix):
                    raise Blocked('serving_commit_unverified')
                reason = apply_one(row, evidence, approved[row['job_id']]['evidence_digest'], inventory)
            except Blocked as error:
                reason = str(error)
            except Exception:
                reason = 'dispatch_uncertain'
            run_result['results'].append(result_record(row, evidence, reason))
            atomic_private_write(output, history)
            if reason not in ('dispatched', 'already_dispatched', 'ledger_completed'):
                break  # Stop the entire canary on the first refusal/uncertainty.
    else:
        with ThreadPoolExecutor(max_workers=4) as pool:
            for row, evidence in zip(rows, pool.map(inventory.inspect, rows)):
                run_result['results'].append(result_record(row, evidence, classify(row, evidence)))
    run_result['counts'] = dict(Counter(r['reason'] for r in run_result['results']))
    atomic_private_write(output, history)
    print(json.dumps({'counts': run_result['counts']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
