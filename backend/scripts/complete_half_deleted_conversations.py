#!/usr/bin/env python3
"""Find, and optionally finish, conversations the user deleted that still exist.

From 2026-10-27 cascade deletes recorded the deletion tombstone
(``users/{uid}/deleted_conversations/{id}``) and then failed under the account
gate, leaving the conversation document behind.

Default is a read-only dry run that prints counts. Without ``--project`` it
scans through the backend runtime's own Firestore client and prints that
runtime's data-plane bindings plus a ``runtime_digest``. ``--execute`` must run
in the same runtime and repeat that digest with ``--confirm-runtime``; any
mismatch exits before a single mutation. Each live leftover is then completed
through the public delete route (``cascade=True``, under the account gate)
after its tombstone is re-read in that same runtime. Batch-purge obligations
are only counted: the backend reconciler owns dispatching them.

    python scripts/complete_half_deleted_conversations.py --project based-hardware   # standalone count
    python scripts/complete_half_deleted_conversations.py                            # runtime count + digest
    python scripts/complete_half_deleted_conversations.py --execute --confirm-runtime <digest> --limit 50
"""

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google.cloud import firestore

TOMBSTONES = 'deleted_conversations'
OBLIGATIONS = 'conversation_batch_purge_jobs'
DEFAULT_SINCE = '2026-10-27'
_GET_ALL_CHUNK = 300


def _aware(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return None


def scan(client, since, uid_filter=None):
    """Yield (uid, conversation_id, state) for every tombstone at or after ``since``.

    ``state`` is ``live`` (document still visible), ``soft_deleted`` (document
    kept with ``deleted: true``), or ``gone``. Reads only; one unfiltered
    collection-group stream plus batched point reads of the conversations.
    """
    pending = []

    def flush():
        refs = [
            client.collection('users').document(uid).collection('conversations').document(cid) for uid, cid in pending
        ]
        found = {snap.reference.path: snap for snap in client.get_all(refs, field_paths=['deleted'])}
        for (uid, cid), ref in zip(pending, refs):
            snapshot = found.get(ref.path)
            if snapshot is None or not snapshot.exists:
                state = 'gone'
            elif (snapshot.to_dict() or {}).get('deleted'):
                state = 'soft_deleted'
            else:
                state = 'live'
            yield uid, cid, state
        pending.clear()

    for tombstone in client.collection_group(TOMBSTONES).select(['deleted_at']).stream():
        owner = tombstone.reference.parent.parent
        if owner is None:
            continue
        uid = owner.id
        if uid_filter and uid != uid_filter:
            continue
        deleted_at = _aware((tombstone.to_dict() or {}).get('deleted_at'))
        if deleted_at is None or deleted_at < since:
            continue
        pending.append((uid, tombstone.id))
        if len(pending) >= _GET_ALL_CHUNK:
            yield from flush()
    if pending:
        yield from flush()


def runtime_bindings(client):
    """Every data plane the route touches in this process, as the digest's input."""
    return {
        'firestore_project': getattr(client, 'project', None),
        'firestore_database': getattr(client, '_database', None) or '(default)',
        'data_plane_project': os.getenv('OMI_FIRESTORE_DATA_PLANE_PROJECT') or None,
        'google_cloud_project': os.getenv('GOOGLE_CLOUD_PROJECT') or None,
        'env_stage': os.getenv('OMI_ENV_STAGE') or None,
        'pinecone_index': os.getenv('PINECONE_INDEX_NAME') or None,
        'buckets': {name: value for name, value in sorted(os.environ.items()) if name.startswith('BUCKET_')},
    }


def runtime_digest(bindings):
    return hashlib.sha256(json.dumps(bindings, sort_keys=True, default=str).encode()).hexdigest()[:16]


def runtime_client():
    from database._client import get_firestore_client

    return get_firestore_client()


def route_client_project():
    from routers import conversations as conversation_routes

    return getattr(conversation_routes.db_client_module.db, 'project', None)


def tombstone_exists(client, uid, conversation_id):
    return client.collection('users').document(uid).collection(TOMBSTONES).document(conversation_id).get().exists


def complete_with_route(uid, conversation_id):
    """The public route's own code path: account gate, cascade, then its background audio purge."""
    from fastapi import BackgroundTasks
    from routers import conversations as conversation_routes

    background_tasks = BackgroundTasks()
    conversation_routes.delete_conversation(conversation_id, background_tasks, cascade=True, http_request=None, uid=uid)
    asyncio.run(background_tasks())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--project', help='standalone read-only scan of this project (dry-run only)')
    parser.add_argument('--since', default=DEFAULT_SINCE, help='tombstones deleted_at >= this UTC date')
    parser.add_argument('--uid', help='limit to one account')
    parser.add_argument('--limit', type=int, default=0, help='max conversations to complete with --execute')
    parser.add_argument('--max-per-minute', type=int, default=60, help='execution rate ceiling')
    parser.add_argument('--confirm-runtime', help='runtime_digest printed by a dry run in this same runtime')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', default=True, help='count only (default)')
    mode.add_argument('--execute', action='store_true', help='complete each live leftover through the route')
    args = parser.parse_args(argv)

    if args.execute and args.project:
        print('refusing --execute with --project: execution must use the runtime it scans', file=sys.stderr)
        return 2
    since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
    if args.project:
        client, bindings, digest = firestore.Client(project=args.project), {'firestore_project': args.project}, None
    else:
        client = runtime_client()
        bindings = runtime_bindings(client)
        digest = runtime_digest(bindings)
    if args.execute:
        if args.confirm_runtime != digest:
            print(f'refusing --execute: runtime_digest={digest} does not match --confirm-runtime', file=sys.stderr)
            return 2
        if route_client_project() != bindings['firestore_project']:
            print('refusing --execute: the delete route resolves a different Firestore project', file=sys.stderr)
            return 2

    counts = Counter()
    owners = set()
    work = []
    for uid, cid, state in scan(client, since, args.uid):
        counts['tombstones'] += 1
        counts[f'conversation_{state}'] += 1
        if state == 'live':
            owners.add(uid)
            work.append((uid, cid))
    counts['accounts_with_live_leftovers'] = len(owners)
    counts['batch_purge_obligations_pending'] = sum(1 for _ in client.collection(OBLIGATIONS).select([]).stream())
    print(f'since={since.date().isoformat()} mode={"execute" if args.execute else "dry-run"}')
    print(f'bindings={json.dumps(bindings, sort_keys=True, default=str)}')
    print(f'runtime_digest={digest or "n/a (standalone scan cannot authorize --execute)"}')
    for key in sorted(counts):
        print(f'  {key}={counts[key]}')
    if not args.execute:
        return 0

    outcomes = Counter()
    interval = 60.0 / max(1, args.max_per_minute)
    for uid, cid in work[: args.limit] if args.limit else work:
        started = time.monotonic()
        try:
            # Re-read the evidence in the executing plane immediately before mutating.
            if not tombstone_exists(client, uid, cid):
                outcomes['skipped_tombstone_missing'] += 1
                continue
            complete_with_route(uid, cid)
            outcomes['completed_via_route'] += 1
        except Exception as error:  # noqa: BLE001 - keep going; the tombstone keeps intent durable
            outcomes[f'failed_{getattr(error, "status_code", None) or type(error).__name__}'] += 1
        time.sleep(max(0.0, interval - (time.monotonic() - started)))
    for key in sorted(outcomes):
        print(f'  {key}={outcomes[key]}')
    return 1 if any(key.startswith('failed_') for key in outcomes) else 0


if __name__ == '__main__':
    raise SystemExit(main())
