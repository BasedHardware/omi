#!/usr/bin/env python3
"""Plan or apply one bounded, resumable page of the v3 Home index migration.

From backend/ with PYTHONPATH=., run with --project PROJECT --uid OWNER and
capture the dry-run JSON to a file. Publish the counts and approve the scope
before passing that file to --apply. Resume planning with --after set to the
plan's next_after. After all pages, scan from the beginning with no --apply and
require zero missing/mismatched values before adding the uid to
OMI_HOME_VISIBILITY_INDEX_OWNERS. Deploy the index and all writers first.
"""

import argparse
import json
from pathlib import Path

from google.cloud import firestore

from database import home_visibility_index as visibility

FIELDS = (*visibility.FLAGS, visibility.FIELD)
MAX_ROWS = 1000
TX_ATTEMPTS = 3
RPC_TIMEOUT = 30


def _scan(collection, after, limit, *, through=None):
    query = collection.order_by('__name__').select(FIELDS).limit(limit)
    if after:
        query = query.start_after({'__name__': collection.document(after)})
    if through:
        query = query.end_at({'__name__': collection.document(through)})
    return list(query.stream(retry=None, timeout=RPC_TIMEOUT))


def _classify(snapshots):
    missing, mismatched = [], []
    for snapshot in snapshots:
        row = snapshot.to_dict() or {}
        if visibility.FIELD not in row:
            missing.append(snapshot.reference)
        elif row[visibility.FIELD] is not visibility.visible(row):
            mismatched.append(snapshot.reference)
    return missing, mismatched


def plan(collection, *, project, uid, after, limit):
    snapshots = _scan(collection, after, limit)
    missing, mismatched = _classify(snapshots)
    scanned, changes = len(snapshots), len(missing) + len(mismatched)
    return {
        'project': project,
        'uid': uid,
        'after': after,
        'through': snapshots[-1].id if snapshots else None,
        'next_after': snapshots[-1].id if scanned == limit else None,
        'rows_scanned': scanned,
        'missing': len(missing),
        'mismatched': len(mismatched),
        'dry_run_reads': max(1, scanned),
        'expected_apply_reads': max(1, scanned) + changes if scanned else 0,
        'max_apply_reads': scanned + 1 + TX_ATTEMPTS * changes if scanned else 0,
        'expected_apply_writes': changes,
        'max_transaction_attempts': TX_ATTEMPTS,
    }


@firestore.transactional
def _reconcile(transaction, reference):
    snapshot = reference.get(field_paths=FIELDS, transaction=transaction, retry=None, timeout=RPC_TIMEOUT)
    if not snapshot.exists:
        return False
    row = snapshot.to_dict() or {}
    expected = visibility.visible(row)
    if row.get(visibility.FIELD) is expected:
        return False
    transaction.update(reference, {visibility.FIELD: expected})
    return True


def apply(client, collection, approved, *, project, uid):
    if approved['project'] != project or approved['uid'] != uid:
        raise ValueError('approve a plan for the requested project and owner')
    scanned, changes = approved['rows_scanned'], approved['expected_apply_writes']
    if not 0 <= changes <= scanned <= MAX_ROWS or bool(approved['through']) != bool(scanned):
        raise ValueError('invalid plan scope or budget')
    if not scanned:
        return {'rows_scanned': 0, 'rows_written': 0, 'next_after': None}

    # A single extra scan read detects growth. Refuse changed scope or cost
    # before starting any transaction, then redo the projection inside each one.
    snapshots = _scan(collection, approved['after'], scanned + 1, through=approved['through'])
    missing, mismatched = _classify(snapshots)
    if len(snapshots) > scanned or len(missing) + len(mismatched) > changes:
        raise ValueError('candidate count grew within the approved range, so plan the page again')
    written = sum(
        _reconcile(client.transaction(max_attempts=TX_ATTEMPTS), reference) for reference in (*missing, *mismatched)
    )
    return {'rows_scanned': len(snapshots), 'rows_written': written, 'next_after': approved['next_after']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--uid', required=True)
    parser.add_argument('--after')
    parser.add_argument('--limit', type=int, default=MAX_ROWS)
    parser.add_argument('--apply', type=Path, metavar='APPROVED_PLAN_JSON')
    args = parser.parse_args()
    if not 1 <= args.limit <= MAX_ROWS:
        parser.error(f'--limit must be between 1 and {MAX_ROWS}')
    if args.apply and args.after is not None:
        parser.error('--apply takes its range from the approved plan')

    client = firestore.Client(project=args.project)
    collection = client.collection('users').document(args.uid).collection('conversations')
    if args.apply:
        result = apply(client, collection, json.loads(args.apply.read_text()), project=args.project, uid=args.uid)
    else:
        result = plan(collection, project=args.project, uid=args.uid, after=args.after, limit=args.limit)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
