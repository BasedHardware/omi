#!/usr/bin/env python3
# LIFECYCLE: permanent
"""Manual held-input redrive. Dry-run defaults to aggregate counts and a plan digest.

Dry-run has no GCS access. Apply requires generation-pinned object metadata before
the existing privacy/content-fenced GPU requeue or target-restorable assignment
release. No audio reads, provider calls or scheduled execution.
"""

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.batch_pipeline.input_retention import (
    held_input_leg,
    input_expiring,
    staged_enqueue,
    STAGING_BUCKET,
    WARNING_SECONDS,
)

OPERATION = 'held-staging-redrive-v1'
NAMESPACE = 'batch_pipeline_prod'


class Refused(RuntimeError):
    pass


def require(condition, reason):
    if not condition:
        raise Refused(reason)


class CountsOnlyParser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused('invalid_arguments')


def private_path(path):
    path = Path(path)
    require(path.parent.stat().st_mode & 0o077 == 0, 'private_cursor_directory_required')
    return path


def write_cursor(path, cursor):
    path = private_path(path)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            json.dump(cursor, handle)
            handle.flush()
            os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


_ALLOWANCE_STREAMS = (
    ('held', (('state', '==', 'allowance_held'),)),
    (
        'retry',
        (
            ('state', '==', 'retry'),
            ('compute_decision.outcome', '==', 'held'),
            ('compute_decision.reason', '==', 'allowance_exhausted'),
        ),
    ),
    (
        'dead',
        (
            ('state', '==', 'dead'),
            ('dead_letter_reason', '==', 'input_expiring'),
            ('input_expiring_leg', '==', 'allowance'),
        ),
    ),
)


def _validate_cursor_entry(entry):
    require(isinstance(entry, dict) and set(entry) == {'enqueued_at', 'id'}, 'invalid_cursor')
    require(
        type(entry['enqueued_at']) in (int, float)
        and math.isfinite(entry['enqueued_at'])
        and entry['enqueued_at'] > 0
        and isinstance(entry['id'], str)
        and 0 < len(entry['id']) <= 128
        and '/' not in entry['id'],
        'invalid_cursor',
    )


def _collect_unit(client, job, doc_id, cutoff):
    # Retained input-expiring terminals use the same operator exits.
    candidate = job
    if input_expiring(job):
        original_state = (
            'quarantined'
            if job.get('input_expiring_leg') == 'gpu'
            else (
                'committed'
                if job.get('input_expiring_leg') == 'assignment'
                else 'allowance_held' if job.get('input_expiring_leg') == 'allowance' else None
            )
        )
        candidate = {**job, 'state': original_state}
    stamp, leg = staged_enqueue(job), held_input_leg(candidate)
    if stamp is None or stamp > cutoff or not leg:
        return None
    require(job.get('segment_id') == doc_id, 'invalid_job_identity')
    entry = client.collection(f'{NAMESPACE}_results').document(doc_id).get(timeout=10, retry=None).to_dict() or {}
    return {'id': doc_id, 'leg': leg, 'job': job, 'entry': entry}


def _discover_allowance(client, cutoff, limit, cursor):
    streams_cursor = {}
    if cursor is not None:
        require(
            isinstance(cursor, dict)
            and set(cursor) == {'scope', 'streams'}
            and cursor['scope'] == 'allowance'
            and isinstance(cursor['streams'], dict)
            and set(cursor['streams']).issubset({'held', 'retry', 'dead'}),
            'invalid_cursor',
        )
        for value in cursor['streams'].values():
            if value != 'done':
                _validate_cursor_entry(value)
        streams_cursor = dict(cursor['streams'])
    collection = client.collection(f'{NAMESPACE}_jobs')
    units, examined, seen = [], 0, set()
    next_streams = dict(streams_cursor)
    for key, filters in _ALLOWANCE_STREAMS:
        if examined >= limit:
            break
        entry_cursor = streams_cursor.get(key)
        if entry_cursor == 'done':
            next_streams[key] = 'done'
            continue
        stream_limit = limit - examined
        query = collection
        for field, op, value in filters:
            query = query.where(field, op, value)
        query = query.where('enqueued_at', '<=', cutoff).order_by('enqueued_at').order_by('__name__')
        if isinstance(entry_cursor, dict):
            query = query.start_after(
                {'enqueued_at': entry_cursor['enqueued_at'], '__name__': collection.document(entry_cursor['id'])}
            )
        docs = list(query.limit(stream_limit).stream(timeout=30, retry=None))
        examined += len(docs)
        for doc in docs:
            if doc.id in seen:
                continue
            seen.add(doc.id)
            unit = _collect_unit(client, doc.to_dict() or {}, doc.id, cutoff)
            if unit is not None:
                units.append(unit)
        if len(docs) == stream_limit:
            next_streams[key] = {'enqueued_at': docs[-1].to_dict()['enqueued_at'], 'id': docs[-1].id}
        else:
            next_streams[key] = 'done'
    all_done = all(next_streams.get(key) == 'done' for key, _ in _ALLOWANCE_STREAMS)
    next_cursor = None if all_done else {'scope': 'allowance', 'streams': next_streams}
    return units, examined, next_cursor


def discover(client, as_of, limit=128, cursor=None, *, scope='held'):
    """At most 128 examined rows, globally oldest first using held-age indexes."""
    require(1 <= limit <= 128, 'invalid_page_size')
    require(scope in {'held', 'allowance'}, 'invalid_scope')
    cutoff = as_of - WARNING_SECONDS
    if scope == 'allowance':
        return _discover_allowance(client, cutoff, limit, cursor)
    collection = client.collection(f'{NAMESPACE}_jobs')
    query = (
        collection.where('state', 'in', ['quarantined', 'committed', 'dead'])
        .where('recovery_state', 'in', ['held', 'failed_held'])
        .where('enqueued_at', '<=', cutoff)
        .order_by('enqueued_at')
        .order_by('__name__')
    )
    if cursor:
        _validate_cursor_entry(cursor)
        query = query.start_after(
            {
                'enqueued_at': cursor['enqueued_at'],
                '__name__': collection.document(cursor['id']),
            }
        )
    docs = list(query.limit(limit).stream(timeout=30, retry=None))
    units = []
    for doc in docs:
        unit = _collect_unit(client, doc.to_dict() or {}, doc.id, cutoff)
        if unit is not None:
            units.append(unit)
    next_cursor = {'enqueued_at': docs[-1].to_dict()['enqueued_at'], 'id': docs[-1].id} if len(docs) == limit else None
    return units, len(docs), next_cursor


def plan_digest(units, as_of, limit, cursor, *, scope=None):
    payload = {
        'operation': OPERATION,
        'namespace': NAMESPACE,
        'bucket': STAGING_BUCKET,
        'as_of': as_of,
        'limit': limit,
        'cursor': cursor,
        'units': units,
    }
    if scope is not None:
        payload['scope'] = scope
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(',', ':'),
            default=str,
        ).encode()
    ).hexdigest()


def pinned_audio_exists(job, storage_client=None):
    """Metadata GET only; absent, unpinned and unknown generations never authorize redrive."""
    try:
        uri = job.get('audio_uri')
        if not isinstance(uri, str):
            return False
        parsed = urlsplit(uri)
        if (
            parsed.scheme != 'gs'
            or parsed.netloc != STAGING_BUCKET
            or parsed.query
            or not parsed.path.startswith('/')
            or not parsed.path[1:]
            or not re.fullmatch(r'[1-9][0-9]{0,19}', parsed.fragment)
        ):
            return False
        generation = int(parsed.fragment)
        if storage_client is None:
            from google.cloud import storage

            storage_client = storage.Client(project='based-hardware')
        blob = storage_client.bucket(STAGING_BUCKET).blob(parsed.path[1:], generation=generation)
        blob.reload(if_generation_match=generation, timeout=10, retry=None)
        return str(blob.generation) == parsed.fragment
    except Exception:
        # Includes NotFound, precondition failure, permissions and transport errors.
        # Neither provider exception bodies nor private references enter output.
        return False


def apply_plan(store, units, digest, approved, now, *, storage_client=None, entitlement_check=None):
    # Approval is checked before constructing a writer or entering any transaction.
    require(approved == digest, 'approval_digest_changed')
    from database.batch_pipeline_quarantine_recovery import RecoveryStore
    from database.batch_pipeline_projection import ProjectionStore
    from database.batch_pipeline_projection_release import ProjectionReleaseStore
    from database.batch_pipeline_privacy import BatchPrivacyBlocked
    from database.batch_pipeline_projection_protocol import ProjectionBlocked

    counts = Counter()
    for unit in units:
        if not pinned_audio_exists(unit['job'], storage_client):
            counts['skipped_input_unproven'] += 1
            continue
        try:
            if unit['leg'] == 'gpu':
                changed = RecoveryStore(store).requeue_quarantined(unit['id'], now, expected_job=unit['job'])
            elif unit['leg'] == 'allowance':
                changed = RecoveryStore(store).release_allowance_input(
                    unit['id'], now, expected_job=unit['job'], entitled=entitlement_check
                )
            else:
                changed = ProjectionReleaseStore(ProjectionStore(store)).release(
                    unit['id'],
                    now,
                    operator=True,
                    expected_job=unit['job'],
                    expected_entry=unit['entry'],
                )
            counts['requeued' if changed else 'refused'] += 1
        except (BatchPrivacyBlocked, ProjectionBlocked):
            counts['refused'] += 1
    return dict(counts)


def main(argv=None):
    parser = CountsOnlyParser(description=__doc__)
    parser.add_argument('--as-of', required=True, help='Frozen UTC ISO timestamp; reuse unchanged for apply')
    parser.add_argument('--page-size', type=int, default=128)
    parser.add_argument('--scope', choices=('held', 'allowance'), default='held')
    parser.add_argument('--cursor-file')
    parser.add_argument('--next-cursor-file')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--approve-plan-sha256')
    args = parser.parse_args(argv)
    logging.disable(logging.CRITICAL)
    require(not os.getenv('FIRESTORE_EMULATOR_HOST'), 'cloud_only')
    require(
        os.getenv('GCP_AGENT_TIER') in (('prod-operator',) if args.apply else ('ro-prod', 'prod-operator')),
        'wrong_identity',
    )
    require(1 <= args.page_size <= 128, 'invalid_page_size')
    stamp = datetime.fromisoformat(args.as_of.replace('Z', '+00:00'))
    offset = stamp.utcoffset()
    require(offset is not None and offset.total_seconds() == 0, 'utc_as_of_required')
    as_of = stamp.timestamp()
    require(0 < as_of <= time.time(), 'invalid_as_of')
    require(not args.apply or bool(args.approve_plan_sha256), 'approval_required')
    cursor = None
    if args.cursor_file:
        path = private_path(args.cursor_file)
        require(not path.is_symlink() and path.stat().st_mode & 0o077 == 0, 'private_cursor_file_required')
        cursor = json.loads(path.read_text())
    if args.next_cursor_file:
        private_path(args.next_cursor_file)
        require(
            not args.cursor_file or Path(args.cursor_file).resolve() != Path(args.next_cursor_file).resolve(),
            'separate_cursor_files_required',
        )
    from google.cloud import firestore
    from database.batch_pipeline_store import FirestoreStore

    client = firestore.Client(project='based-hardware')
    scope = None if args.scope == 'held' else args.scope
    units, examined, next_cursor = (
        discover(client, as_of, args.page_size, cursor)
        if args.scope == 'held'
        else discover(client, as_of, args.page_size, cursor, scope=args.scope)
    )
    digest = plan_digest(units, as_of, args.page_size, cursor, scope=scope)
    output = {
        'operation': OPERATION,
        'mode': 'apply' if args.apply else 'dry_run',
        'examined': examined,
        'selected': len(units),
        'by_leg': dict(Counter(unit['leg'] for unit in units)),
        'plan_sha256': digest,
        'more': next_cursor is not None,
    }
    if args.apply:
        output.update(
            apply_plan(
                FirestoreStore(NAMESPACE, firestore_client=client), units, digest, args.approve_plan_sha256, time.time()
            )
        )
    else:
        output['firestore_writes'] = 0
    if args.next_cursor_file:
        write_cursor(args.next_cursor_file, next_cursor)
    print(json.dumps(output, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Refused as error:
        print(json.dumps({'operation': OPERATION, 'outcome': 'refused', 'reason': str(error)}))
        sys.exit(2)
    except Exception:
        print(json.dumps({'operation': OPERATION, 'outcome': 'error', 'reason': 'operation_failed_closed'}))
        sys.exit(1)
