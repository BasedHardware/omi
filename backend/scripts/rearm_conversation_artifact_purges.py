"""Find terminal conversation purges with artifact receipts. Dry-run by default."""

import argparse
import json
import logging
import sys

from pathlib import Path

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_conversation_purge_remainders import Budget, Incomplete, obligation_pending, remainders, timestamp
from database import conversation_batch_purge_jobs as jobs
from database.conversation_tombstones import COLLECTION

ARTIFACT_CLASSES = {'batch_pipeline_prod_artifacts', 'batch_pipeline_dev_artifacts'}


def candidates(db, start, end, budget, counts):
    query = (
        db.collection_group(COLLECTION)
        .where(filter=FieldFilter('deleted_at', '>=', start))
        .where(filter=FieldFilter('deleted_at', '<', end))
        .order_by('deleted_at')
        .order_by('__name__')
        .select(['deleted_at'])
    )
    for tombstone in budget.pages(COLLECTION, query):
        path = tombstone.reference.path.split('/')
        if len(path) != 4 or path[0] != 'users':
            continue
        uid, cid = path[1], path[3]
        if obligation_pending(db, budget, uid, cid):
            continue
        found = remainders(db, None, budget, uid, cid, artifacts_only=True)
        if obligation_pending(db, budget, uid, cid):
            continue
        counts['terminal_checked'] += 1
        if found.intersection(ARTIFACT_CLASSES):
            counts['candidates'] += 1
            yield uid, cid, tombstone.update_time


def rearm(db, uid, cid, tombstone_version):
    batch_ref = jobs.job_ref(db, uid, cid)
    erase_ref = jobs.erasure_job_ref(db, uid, cid)
    tombstone_ref = db.collection('users').document(uid).collection(COLLECTION).document(cid)

    @firestore.transactional
    def arm(tx):
        current = tombstone_ref.get(transaction=tx, timeout=10)
        if not current.exists or current.update_time != tombstone_version:
            return False
        if batch_ref.get(transaction=tx, timeout=10).exists or erase_ref.get(transaction=tx, timeout=10).exists:
            return False
        tx.create(batch_ref, jobs.arm_fields(uid, cid))
        return True

    return arm(db.transaction())


def run(db, start, end, budget, apply, max_repairs, counts):
    # Finish the read pass before writing anything. An incomplete audit never
    # arms a subset, and the bound also caps the candidate list in memory.
    selected = []
    for candidate in candidates(db, start, end, budget, counts):
        if apply:
            if len(selected) >= max_repairs:
                raise Incomplete('repair_cap_exceeded')
            selected.append(candidate)
    for uid, cid, version in selected:
        if rearm(db, uid, cid, version):
            counts['rearmed'] += 1
        else:
            counts['changed_since_scan'] += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--start', required=True, type=timestamp)
    parser.add_argument('--end', required=True, type=timestamp)
    parser.add_argument('--max-requests', type=int, default=10000)
    parser.add_argument('--max-repairs', type=int, default=25)
    parser.add_argument('--apply', action='store_true', help='Write purge obligations for the existing reconciler')
    args = parser.parse_args()
    if args.start >= args.end or min(args.max_requests, args.max_repairs) < 1:
        parser.error('require start < end and positive bounds')
    logging.disable(logging.CRITICAL)
    counts = dict(terminal_checked=0, candidates=0, rearmed=0, changed_since_scan=0)
    status = 'complete'
    try:
        run(
            firestore.Client(project=args.project),
            args.start,
            args.end,
            Budget(args.max_requests),
            args.apply,
            args.max_repairs,
            counts,
        )
    except Incomplete as exc:
        status = str(exc)
    except Exception:
        # SDK errors may include document paths or object names.
        status = 'repair_operation_failed'
    print(json.dumps({'mode': 'apply' if args.apply else 'dry_run', 'status': status, **counts}))
    return 0 if status == 'complete' else 2


if __name__ == '__main__':
    sys.exit(main())
