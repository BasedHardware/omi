"""Read-only audit of tombstone cohorts. Run from backend with read-only ADC."""

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys

from google.api_core.exceptions import FailedPrecondition, Forbidden
from google.cloud import firestore, storage
from google.cloud.firestore_v1 import FieldFilter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.record_wal_storage import private_archive_bucket
from database import conversation_batch_purge_jobs as jobs
from database.batch_pipeline_conversation_purge import DEPENDENT_TABLES, DISCOVER_TABLES
from database.batch_pipeline_privacy import privacy_owner_key
from database.batch_pipeline_purge import NAMESPACES, _belongs, _references, result_document
from database.conversation_tombstones import COLLECTION
from utils.batch_pipeline.record_wal_erasure import _prefix
from utils.batch_pipeline.retention import batch_object_address

PAGE = 100
RPC = {'timeout': 10, 'retry': None}
LOCATIONS = ('wal_objects', 'referenced_objects', 'segment_journals') + tuple(
    f'{namespace}_{table}' for namespace in NAMESPACES for table in DISCOVER_TABLES + DEPENDENT_TABLES
)


class Incomplete(Exception):
    pass


def read(location, operation):
    try:
        return operation()
    except Forbidden:
        raise Incomplete(f'access_denied:{location}') from None
    except FailedPrecondition as exc:
        reason = 'missing_index' if 'index' in str(exc).lower() else 'failed_precondition'
        raise Incomplete(f'{reason}:{location}') from None
    except Exception:
        raise Incomplete(f'read_failed:{location}') from None


class Budget:
    def __init__(self, requests):
        self.remaining = requests

    def read(self, location, operation):
        if self.remaining <= 0:
            raise Incomplete('request_budget_exhausted')
        self.remaining -= 1
        return read(location, operation)

    def pages(self, location, query):
        cursor = None
        while True:
            page_query = query.start_after(cursor) if cursor is not None else query
            rows = self.read(location, lambda: page_query.limit(PAGE).get(**RPC))
            yield from rows
            if len(rows) < PAGE:
                return
            cursor = rows[-1]


def obligation_pending(db, budget, uid, cid):
    return any(
        budget.read(jobs.COLLECTION, lambda: ref.get(field_paths=[], **RPC)).exists
        for ref in (jobs.job_ref(db, uid, cid), jobs.erasure_job_ref(db, uid, cid))
    )


def remainders(db, gcs, budget, uid, cid):
    found = set()
    bucket = private_archive_bucket()
    wal_prefix = _prefix(uid, cid)
    if budget.read(
        bucket, lambda: next(iter(gcs.list_blobs(bucket, prefix=wal_prefix, versions=True, max_results=1, **RPC)), None)
    ):
        found.add('wal_objects')

    owner = privacy_owner_key(uid)
    for namespace in NAMESPACES:
        segments = set()
        journal = jobs.job_ref(db, uid, cid).collection(jobs.SEGMENTS)
        journal = journal.where(filter=FieldFilter('namespace', '==', namespace))
        for row in budget.pages('segment_journals', journal):
            found.add('segment_journals')
            segments.add(row.get('segment_id'))

        def inspect(table, data):
            found.add(f'{namespace}_{table}')
            for uri in _references(data):
                try:
                    name, path, generation = batch_object_address(uid, uri)
                except (TypeError, ValueError):
                    raise Incomplete('invalid_batch_object_reference') from None
                blob = gcs.bucket(name).blob(path, generation=generation)
                if budget.read(name, lambda: blob.exists(**RPC)):
                    found.add('referenced_objects')

        for table in DISCOVER_TABLES + DEPENDENT_TABLES:
            location = f'{namespace}_{table}'
            collection = db.collection(location)
            query = collection.where(filter=FieldFilter('owner_key', '==', owner))
            if table == 'artifacts':
                parked = collection.where(filter=FieldFilter('owner_id', '==', uid))
                owner_rows = budget.pages(location, query)
                rows = _with_parked(owner_rows, budget.pages(location, parked), owner)
            else:
                rows = budget.pages(location, query)
            for row in rows:
                data = row.to_dict() or {}
                if table == 'jobs':
                    ref = result_document(db, namespace, row.id)
                    result = budget.read(f'{namespace}_results', lambda: ref.get(**RPC)).to_dict() or {}
                    if row.id in segments or _belongs(
                        {**data, 'projection': result.get('projection') or data.get('projection')}, cid
                    ):
                        segments.add(row.id)
                        inspect(table, data)
                        if result and result.get('projection_state') != 'erased':
                            inspect('results', result)
                elif table == 'results':
                    if row.id in segments or _belongs(data, cid):
                        segments.add(row.id)
                        inspect(table, data)
                elif (
                    _belongs(data, cid)
                    or (table in {'artifacts', 'projections'} and data.get('segment_id') in segments)
                    or (table == 'intakes' and segments.intersection(data.get('segment_ids') or []))
                ):
                    inspect(table, data)
    return found


def _with_parked(owner_rows, parked_rows, owner):
    yield from owner_rows
    for row in parked_rows:
        if (row.to_dict() or {}).get('owner_key') != owner:
            yield row


def audit(db, gcs, start, end, budget):
    report = {
        'start': start.isoformat(),
        'end': end.isoformat(),
        'tombstones': 0,
        'terminal': 0,
        'pending': 0,
        'terminal_checked': 0,
        'remainders': dict.fromkeys(LOCATIONS, 0),
    }
    query = (
        db.collection_group(COLLECTION)
        .where(filter=FieldFilter('deleted_at', '>=', start))
        .where(filter=FieldFilter('deleted_at', '<', end))
        .order_by('deleted_at')
        .order_by('__name__')
        .select(['deleted_at'])
    )
    try:
        for tombstone in budget.pages(COLLECTION, query):
            parts = tombstone.reference.path.split('/')
            if len(parts) != 4 or parts[0] != 'users':
                continue
            report['tombstones'] += 1
            uid, cid = parts[1], parts[3]
            if obligation_pending(db, budget, uid, cid):
                report['pending'] += 1
                continue
            report['terminal'] += 1
            found = remainders(db, gcs, budget, uid, cid)
            if obligation_pending(db, budget, uid, cid):
                report['terminal'] -= 1
                report['pending'] += 1
                continue
            report['terminal_checked'] += 1
            for location in found:
                report['remainders'][location] += 1
    except Incomplete as exc:
        report.update(verdict='incomplete_scan', reason=str(exc))
        if not report['tombstones']:
            for key in ('tombstones', 'terminal', 'pending', 'terminal_checked'):
                report[key] = None
            report['remainders'] = dict.fromkeys(LOCATIONS)
    except Exception:
        report.update(verdict='incomplete_scan', reason='unexpected_audit_failure')
    else:
        if any(report['remainders'].values()):
            report.update(verdict='remainders_found', reason='current_attributable_remainders')
        elif report['terminal_checked']:
            report.update(verdict='incomplete_scan', reason='shadow_and_discarded_associations_unverified')
        else:
            report.update(verdict='clean', reason='no_terminal_obligations_in_cohort')
    return report


def timestamp(value):
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is not None:
            return result.astimezone(timezone.utc)
    except ValueError:
        pass
    raise argparse.ArgumentTypeError('use an ISO-8601 timestamp with a timezone')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', required=True, type=timestamp)
    parser.add_argument('--end', required=True, type=timestamp)
    parser.add_argument('--project', required=True)
    parser.add_argument('--max-requests', type=int, default=10000)
    args = parser.parse_args()
    if args.start >= args.end or args.max_requests < 1:
        parser.error('require start < end and a positive request budget')
    logging.disable(logging.CRITICAL)
    try:
        db = firestore.Client(project=args.project)
        gcs = storage.Client(project=args.project)
    except Exception:
        print(json.dumps({'verdict': 'incomplete_scan', 'reason': 'client_initialization_failed'}))
        return 2
    main_window = audit(db, gcs, args.start, args.end, Budget(args.max_requests))
    control_start = args.start - (args.end - args.start)
    if main_window['reason'].startswith('access_denied:'):
        control = {'verdict': 'incomplete_scan', 'reason': 'stopped_after_access_denied'}
    else:
        control = audit(db, gcs, control_start, args.start, Budget(args.max_requests))
    print(json.dumps({'main': main_window, 'control': control}, indent=2))
    return 2 if any(window['verdict'] == 'incomplete_scan' for window in (main_window, control)) else 0


if __name__ == '__main__':
    sys.exit(main())
