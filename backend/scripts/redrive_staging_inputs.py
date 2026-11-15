#!/usr/bin/env python3
# LIFECYCLE: permanent
"""Manual held-input redrive. Dry-run defaults to aggregate counts and a plan digest.

No GCS access, audio, provider calls or scheduled execution. Apply uses only the
existing privacy/content-fenced GPU requeue or target-restorable assignment release.
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
import sys
import tempfile
import time

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


def discover(client, as_of, limit=128, cursor=None):
    """At most 128 examined rows, globally oldest first using an existing held-age index."""
    require(1 <= limit <= 128, 'invalid_page_size')
    collection = client.collection(f'{NAMESPACE}_jobs')
    query = (
        collection.where('state', 'in', ['quarantined', 'committed', 'dead'])
        .where('recovery_state', 'in', ['held', 'failed_held'])
        .where('enqueued_at', '<=', as_of - WARNING_SECONDS)
        .order_by('enqueued_at')
        .order_by('__name__')
    )
    if cursor:
        require(set(cursor) == {'enqueued_at', 'id'}, 'invalid_cursor')
        require(
            type(cursor['enqueued_at']) in (int, float)
            and math.isfinite(cursor['enqueued_at'])
            and cursor['enqueued_at'] > 0
            and isinstance(cursor['id'], str)
            and 0 < len(cursor['id']) <= 128
            and '/' not in cursor['id'],
            'invalid_cursor',
        )
        query = query.start_after(
            {
                'enqueued_at': cursor['enqueued_at'],
                '__name__': collection.document(cursor['id']),
            }
        )
    docs = list(query.limit(limit).stream(timeout=30, retry=None))
    units = []
    for doc in docs:
        job = doc.to_dict() or {}
        # Retained input-expiring terminals use the same operator exits.
        candidate = job
        if input_expiring(job):
            original_state = (
                'quarantined'
                if job.get('input_expiring_leg') == 'gpu'
                else 'committed' if job.get('input_expiring_leg') == 'assignment' else None
            )
            candidate = {**job, 'state': original_state}
        stamp, leg = staged_enqueue(job), held_input_leg(candidate)
        if stamp is None or stamp > as_of - WARNING_SECONDS or not leg:
            continue
        require(job.get('segment_id') == doc.id, 'invalid_job_identity')
        entry = client.collection(f'{NAMESPACE}_results').document(doc.id).get(timeout=10, retry=None).to_dict() or {}
        units.append({'id': doc.id, 'leg': leg, 'job': job, 'entry': entry})
    next_cursor = {'enqueued_at': docs[-1].to_dict()['enqueued_at'], 'id': docs[-1].id} if len(docs) == limit else None
    return units, len(docs), next_cursor


def plan_digest(units, as_of, limit, cursor):
    return hashlib.sha256(
        json.dumps(
            {
                'operation': OPERATION,
                'namespace': NAMESPACE,
                'bucket': STAGING_BUCKET,
                'as_of': as_of,
                'limit': limit,
                'cursor': cursor,
                'units': units,
            },
            sort_keys=True,
            separators=(',', ':'),
            default=str,
        ).encode()
    ).hexdigest()


def apply_plan(store, units, digest, approved, now):
    # Approval is checked before constructing a writer or entering any transaction.
    require(approved == digest, 'approval_digest_changed')
    from database.batch_pipeline_quarantine_recovery import RecoveryStore
    from database.batch_pipeline_projection import ProjectionStore
    from database.batch_pipeline_projection_release import ProjectionReleaseStore
    from database.batch_pipeline_privacy import BatchPrivacyBlocked
    from database.batch_pipeline_projection_protocol import ProjectionBlocked

    counts = Counter()
    for unit in units:
        try:
            if unit['leg'] == 'gpu':
                changed = RecoveryStore(store).requeue_quarantined(unit['id'], now, expected_job=unit['job'])
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
    units, examined, next_cursor = discover(client, as_of, args.page_size, cursor)
    digest = plan_digest(units, as_of, args.page_size, cursor)
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
