#!/usr/bin/env python3
"""Backfill public conversation owners from Redis, without deleting source keys.

Run BEFORE deleting old no-TTL memories-visibility keys (preferably before TTL
cache rollout). No migration flag is required: serving discovers owners by the
stored id independently. The conversations.id collection-group index is already
registered in firestore_index_registry.py. Leave public-memories intact.

Dry-run is default. Use one durable checkpoint across all apply runs; it stores
SCAN cursor + pending page + a UTC daily write reservation (maximum 10,000).
Reservations persist BEFORE writes, so crashes may under-use but never exceed
that budget. Each write uses the read snapshot's CAS precondition; concurrent
unshares cannot restore owner_uid. Completed scans can be repeated with --rescan
while preserving the daily ledger. Do not edit/remove the apply checkpoint.
Quarantine is an append-only local JSONL report; no conflicting doc is modified.

Example (not executed by this PR):
  python scripts/backfill_conversation_owner_uid.py --checkpoint /secure/owners.json
  python scripts/backfill_conversation_owner_uid.py --checkpoint /secure/owners.json --apply
"""

import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import sys

from google.api_core.exceptions import FailedPrecondition
from google.cloud.firestore_v1 import FieldFilter

PREFIX = 'memories-visibility:'
MAX_DAILY_WRITES = 10_000


def _save(path, state):
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w') as output:
        os.chmod(temp, 0o600)
        json.dump(state, output)
        output.flush()
        os.fsync(output.fileno())
    temp.replace(path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def run_backfill(
    redis_client,
    firestore_client,
    *,
    checkpoint,
    apply=False,
    daily_limit=10_000,
    page_size=100,
    max_keys=10_000,
    rescan=False,
    today=None,
):
    """Process bounded SCAN pages; a failed operation leaves its key pending."""
    checkpoint = Path(checkpoint)

    def current_day():
        return today or datetime.now(timezone.utc).date().isoformat()

    run_day = current_day()
    daily_limit = min(max(0, daily_limit), MAX_DAILY_WRITES)
    page_size = min(max(1, page_size), 500)
    state = (
        json.loads(checkpoint.read_text())
        if checkpoint.exists()
        else {
            'cursor': 0,
            'pending': [],
            'complete': False,
            'day': run_day,
            'reserved': 0,
        }
    )
    if state['day'] != run_day:
        state.update(day=run_day, reserved=0)
    if rescan and state['complete']:
        state.update(cursor=0, pending=[], complete=False)
    summary = {'scanned': 0, 'written': 0, 'eligible': 0, 'quarantined': 0}

    def persist():
        if apply:
            _save(checkpoint, state)

    def quarantine(key, uid, reason, paths):
        summary['quarantined'] += 1
        if apply:
            report = checkpoint.with_suffix(checkpoint.suffix + '.quarantine.jsonl')
            with report.open('a') as output:
                os.chmod(report, 0o600)
                output.write(json.dumps({'key': key, 'redis_uid': uid, 'reason': reason, 'paths': paths}) + '\n')
                output.flush()
                os.fsync(output.fileno())

    while summary['scanned'] < max_keys and not state['complete']:
        if not state['pending']:
            cursor, keys = redis_client.scan(cursor=state['cursor'], match=PREFIX + '*', count=page_size)
            state['cursor'] = int(cursor)
            state['pending'] = [key.decode() if isinstance(key, bytes) else key for key in keys]
            if not keys and not cursor:
                state['complete'] = True
            persist()
            if not keys:
                continue
        key = state['pending'][0]
        conversation_id = key[len(PREFIX) :]
        uid = redis_client.get(key)
        uid = uid.decode() if isinstance(uid, bytes) else uid
        if uid:
            docs = list(
                firestore_client.collection_group('conversations')
                .where(filter=FieldFilter('id', '==', conversation_id))
                .select(['id', 'owner_uid', 'visibility', 'deleted'])
                .limit(2)
                .stream()
            )
            paths = [doc.reference.path for doc in docs]
            expected = f'users/{uid}/conversations/{conversation_id}'
            if len(docs) != 1 or paths != [expected] or len(paths[0].split('/')) != 4:
                quarantine(key, uid, 'missing_ambiguous_or_parent_mismatch', paths)
            else:
                doc = docs[0]
                data = doc.to_dict() or {}
                if data.get('id') != conversation_id or ('owner_uid' in data and data['owner_uid'] != uid):
                    quarantine(key, uid, 'owner_or_id_mismatch', paths)
                elif (
                    data.get('visibility') in ('shared', 'public')
                    and not data.get('deleted')
                    and 'owner_uid' not in data
                ):
                    summary['eligible'] += 1
                    if apply:
                        write_day = current_day()
                        if state['day'] != write_day:
                            state.update(day=write_day, reserved=0)
                        if state['reserved'] >= daily_limit:
                            persist()
                            return {**summary, 'complete': False, 'budget_exhausted': True}
                        state['reserved'] += 1
                        persist()
                        try:
                            doc.reference.update(
                                {'owner_uid': uid},
                                option=firestore_client.write_option(last_update_time=doc.update_time),
                            )
                        except FailedPrecondition:
                            # Retry this key against the new visibility/owner on resume.
                            return {**summary, 'complete': False, 'contended': True}
                        summary['written'] += 1
        summary['scanned'] += 1
        state['pending'].pop(0)
        if not state['pending'] and state['cursor'] == 0:
            state['complete'] = True
        persist()
    return {**summary, 'complete': state['complete']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--rescan', action='store_true')
    parser.add_argument('--daily-limit', type=int, default=MAX_DAILY_WRITES)
    parser.add_argument('--page-size', type=int, default=100)
    parser.add_argument('--max-keys', type=int, default=10_000)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from database._client import get_firestore_client
    from database.redis_db import r

    # One process per durable ledger; never allow concurrent budget consumers.
    with args.checkpoint.with_suffix(args.checkpoint.suffix + '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print(
            json.dumps(
                run_backfill(
                    r,
                    get_firestore_client(),
                    checkpoint=args.checkpoint,
                    apply=args.apply,
                    daily_limit=args.daily_limit,
                    page_size=args.page_size,
                    max_keys=args.max_keys,
                    rescan=args.rescan,
                )
            )
        )


if __name__ == '__main__':
    main()
