#!/usr/bin/env python3
"""Find, and optionally finish, conversations the user deleted that still exist.

From 2026-10-27 cascade deletes recorded the deletion tombstone
(``users/{uid}/deleted_conversations/{id}``) and then failed under the account
gate, leaving the conversation document behind. The default ``--dry-run`` only
reads and prints counts. ``--execute`` re-runs the public delete route
(``routers.conversations.delete_conversation`` with ``cascade=True``, under the
same account gate) for each live leftover, and runs any batch purge still
marked pending on a tombstone. ``--execute`` needs the backend runtime env.

    python scripts/complete_half_deleted_conversations.py                 # counts only
    python scripts/complete_half_deleted_conversations.py --execute --limit 50
"""

import argparse
import asyncio
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google.cloud import firestore

TOMBSTONES = 'deleted_conversations'
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
            client.collection('users').document(uid).collection('conversations').document(cid)
            for uid, cid, _ in pending
        ]
        found = {snap.reference.path: snap for snap in client.get_all(refs, field_paths=['deleted'])}
        for (uid, cid, purge_pending), ref in zip(pending, refs):
            snapshot = found.get(ref.path)
            if snapshot is None or not snapshot.exists:
                state = 'gone'
            elif (snapshot.to_dict() or {}).get('deleted'):
                state = 'soft_deleted'
            else:
                state = 'live'
            yield uid, cid, state, purge_pending
        pending.clear()

    query = client.collection_group(TOMBSTONES).select(['deleted_at', 'batch_purge_pending'])
    for tombstone in query.stream():
        owner = tombstone.reference.parent.parent
        if owner is None:
            continue
        uid = owner.id
        if uid_filter and uid != uid_filter:
            continue
        row = tombstone.to_dict() or {}
        deleted_at = _aware(row.get('deleted_at'))
        if deleted_at is None or deleted_at < since:
            continue
        pending.append((uid, tombstone.id, bool(row.get('batch_purge_pending'))))
        if len(pending) >= _GET_ALL_CHUNK:
            yield from flush()
    if pending:
        yield from flush()


def complete_with_route(uid, conversation_id):
    """The public route's own code path: account gate, cascade, then its background audio purge."""
    from fastapi import BackgroundTasks
    from routers import conversations as conversation_routes

    background_tasks = BackgroundTasks()
    conversation_routes.delete_conversation(conversation_id, background_tasks, cascade=True, http_request=None, uid=uid)
    asyncio.run(background_tasks())


def run_pending_batch_purge(uid, conversation_id):
    from database import conversation_tombstones

    return conversation_tombstones.run_batch_purge(uid, conversation_id)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--project', default='based-hardware')
    parser.add_argument('--since', default=DEFAULT_SINCE, help='tombstones deleted_at >= this UTC date')
    parser.add_argument('--uid', help='limit to one account')
    parser.add_argument('--limit', type=int, default=0, help='max conversations to complete with --execute')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', default=True, help='count only (default)')
    mode.add_argument('--execute', action='store_true', help='complete each live leftover through the route')
    args = parser.parse_args(argv)

    since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
    client = firestore.Client(project=args.project)
    counts = Counter()
    owners = set()
    work = []
    for uid, cid, state, purge_pending in scan(client, since, args.uid):
        counts['tombstones'] += 1
        counts[f'conversation_{state}'] += 1
        if purge_pending:
            counts['batch_purge_pending'] += 1
        if state == 'live':
            owners.add(uid)
        if args.execute and (state == 'live' or purge_pending):
            work.append((uid, cid, state, purge_pending))
    counts['accounts_with_live_leftovers'] = len(owners)
    print(f'since={since.date().isoformat()} project={args.project} mode={"execute" if args.execute else "dry-run"}')
    for key in sorted(counts):
        print(f'  {key}={counts[key]}')
    if not args.execute:
        return 0

    outcomes = Counter()
    if args.limit:
        work = work[: args.limit]
    for uid, cid, state, purge_pending in work:
        try:
            if state == 'live':
                complete_with_route(uid, cid)
                outcomes['completed_via_route'] += 1
            else:
                outcomes[f'batch_purge_{run_pending_batch_purge(uid, cid)}'] += 1
        except Exception as error:  # noqa: BLE001 - keep going; the tombstone keeps intent durable
            status = getattr(error, 'status_code', None)
            outcomes[f'failed_{status or type(error).__name__}'] += 1
    for key in sorted(outcomes):
        print(f'  {key}={outcomes[key]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
