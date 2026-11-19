"""Count or erase SCA-2283 historical receipts with bounded reads."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
import json
import logging
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google.api_core.exceptions import Aborted, Forbidden
from google.cloud import firestore, storage
from google.cloud.firestore_v1.base_query import FieldFilter

from database.batch_pipeline_purge import NAMESPACES
from database.stranded_artifact_receipts import CUTOFF, RPC, erase, proof, signature


def sweep(db, gcs, args, cursor, checkpoint, report):
    for namespace in NAMESPACES:
        collection = db.collection(f'{namespace}_artifacts')
        query = collection.where(filter=FieldFilter('erasure_requested', '==', True)).order_by('__name__')
        counts = report['namespaces'].setdefault(namespace, Counter())
        while True:
            # Reserve enough for one full proof and the transactional recheck.
            size = min(20, args.max_reads - report['reads'] - 7)
            if size < 1:
                return 'read_limit'
            after = cursor.get(namespace)
            page = query.start_after({'__name__': collection.document(after)}) if after else query
            rows = page.limit(size).get(**RPC)
            report['reads'] += max(1, len(rows))
            if not rows:
                break
            started = time.monotonic()
            for index, row in enumerate(rows, 1):
                time.sleep(max(0, started + index / args.rows_per_second - time.monotonic()))
                counts['scanned'] += 1
                reason, identity = signature(row, datetime.now(timezone.utc))
                if identity is None:
                    counts[reason] += 1
                else:
                    reserve = 7 if args.apply else 3
                    if report['reads'] + reserve > args.max_reads:
                        return 'read_limit'
                    report['reads'] += 3
                    matched, version = proof(db, row, identity)
                    if matched:
                        week = row.create_time.strftime('%G-W%V')
                        counts[week] += 1
                        counts['matched'] += 1
                        if args.apply:
                            report['reads'] += 4
                            if not erase(db, row, version, gcs):
                                return 'conflict'
                            report['erasures'] += 1
                    else:
                        counts['tombstone_or_obligation'] += 1
                cursor[namespace] = row.id
                if args.apply:
                    checkpoint()
                    if report['erasures'] >= args.max_erasures:
                        return 'erasure_limit'
            if len(rows) < size:
                break
    return 'complete'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--max-reads', type=int, required=True)
    parser.add_argument('--max-erasures', type=int, required=True)
    parser.add_argument('--rows-per-second', type=int, default=10)
    args = parser.parse_args()
    if args.max_reads < 8 or not 1 <= args.max_erasures <= 2000 or args.rows_per_second < 1:
        parser.error('require at least eight reads, 1–2000 erasures, and a positive row rate')

    logging.disable(logging.CRITICAL)
    os.environ['BUCKET_BATCH_PIPELINE'] = 'based-hardware-batch-pipeline-staging'
    os.environ['BUCKET_TEMPORAL_SYNC_LOCAL'] = 'syncing-local'
    os.umask(0o077)
    state = Path.home() / '.local' / 'state' / 'omi-stranded-artifact-receipts'
    report = {'cutoff': CUTOFF.isoformat(), 'reads': 0, 'erasures': 0, 'namespaces': {}}
    try:
        state.mkdir(mode=0o700, parents=True, exist_ok=True)
        if state.is_symlink() or state.stat().st_mode & 0o077:
            raise PermissionError('state directory must be private')
        with (state / 'driver.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            path = state / 'apply-cursor.json'
            cursor = json.loads(path.read_text()) if args.apply and path.exists() else {}

            def checkpoint():
                temp = path.with_suffix('.tmp')
                temp.write_text(json.dumps(cursor))
                temp.replace(path)

            db = firestore.Client(project='based-hardware')
            gcs = storage.Client(project='based-hardware') if args.apply else None
            report['status'] = sweep(db, gcs, args, cursor, checkpoint, report)
    except Aborted:
        report['status'] = 'conflict'
    except Forbidden as error:
        # Error messages can embed object names. Report only recognized IAM names.
        report['status'] = 'permission_denied'
        report['permissions'] = [
            permission
            for permission in (
                'storage.objects.delete',
                'storage.objects.get',
                'datastore.entities.get',
                'datastore.entities.list',
                'datastore.entities.delete',
            )
            if permission in str(error)
        ]
    except Exception as error:
        report['status'] = type(error).__name__
    print(json.dumps(report, sort_keys=True))
    return 0 if report['status'] in {'complete', 'erasure_limit'} else 2


if __name__ == '__main__':
    sys.exit(main())
