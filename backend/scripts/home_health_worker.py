"""Bounded Home experience review and optional summary-admission repair."""

from argparse import ArgumentParser, ArgumentTypeError
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import os
import re
import time

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from config.episodes import home_step_projection_enabled
from config.summary_guarantee import deadline_seconds
from services import home_health_repair as repair, home_health_review as review
from utils.enrichment.age_gate import max_age_seconds

MAX_PER_STATUS = 500
MAX_WRITES = 50
MAX_SECONDS = 240
SCAN_TIMEOUT = 15


def _utc(value):
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ArgumentTypeError('an ISO datetime with a UTC offset is required') from None
    if parsed.tzinfo is None:
        raise ArgumentTypeError('an ISO datetime with a UTC offset is required')
    return parsed.astimezone(timezone.utc)


def _scope(snapshot):
    parts = snapshot.reference.path.split('/')
    return parts[1] if len(parts) == 4 and parts[0] == 'users' and parts[2] == 'conversations' else None


def scan(client, *, lane, status, start, end, limit):
    # Registered index record_seal_repair_newest_completed, also usable for
    # other status keys. One explicitly bounded query per status, no offsets.
    return (
        client.collection_group('conversations')
        .where(filter=FieldFilter('record_lane_owner', '==', lane))
        .where(filter=FieldFilter('status', '==', status))
        .where(filter=FieldFilter('finished_at', '>=', start))
        .where(filter=FieldFilter('finished_at', '<', end))
        .order_by('finished_at', direction=firestore.Query.DESCENDING)
        .order_by('__name__', direction=firestore.Query.DESCENDING)
        .select(repair.DISCOVERY_FIELDS)
        .limit(limit + 1)
        .get(retry=None, timeout=SCAN_TIMEOUT)
    )


def run(client, args, *, now, monotonic=time.monotonic, utcnow=lambda: datetime.now(timezone.utc)):
    stop_at = monotonic() + MAX_SECONDS
    report = {
        'schema_version': 1,
        'generated_at': now.isoformat(),
        'cohort': {
            'lane': args.lane,
            'start': args.start.isoformat(),
            'end': args.end.isoformat(),
            'clock': 'finished_at',
        },
        'surface': 'legacy_conversation_list_card_projection',
        'selection': 'newest_in_each_status',
        'home_step_projection_enabled': home_step_projection_enabled(),
        'notes_deadline_seconds': deadline_seconds(),
        'repair_max_age_seconds': max_age_seconds(),
        'per_status_limit': args.per_status,
        'survey_documents': 0,
        'budget_interrupted': False,
        'status_coverage': {},
        'mode': 'apply' if args.apply else 'review',
        'repair': {},
    }
    revision = os.environ.get('OMI_BACKEND_RELEASE_SHA', '')
    if re.fullmatch(r'[0-9a-f]{40}', revision):
        report['release_sha'] = revision
    observations = review.Review()
    proposed = {}
    query_failed = False
    counts_suppressed = False
    for status in review.STATUSES:
        if monotonic() + SCAN_TIMEOUT >= stop_at:
            report['budget_interrupted'] = True
            break
        try:
            snapshots = scan(
                client, lane=args.lane, status=status, start=args.start, end=args.end, limit=args.per_status
            )
        except Exception:
            # Driver errors can embed document references. No exception text
            # or traceback reaches a persistent receipt or operator log.
            report['status_coverage'][status] = 'query_failed'
            query_failed = True
            break
        report['survey_documents'] += len(snapshots)
        status_owners = set()
        for snapshot in snapshots[: args.per_status]:
            owner = _scope(snapshot)
            if owner is None:
                continue
            status_owners.add(owner)
            row = snapshot.to_dict() or {}
            findings = observations.observe(owner, row, now=now)
            if 'notes_not_scheduled' in findings and repair.candidate(row, now=now.timestamp()):
                proposed.setdefault(owner, (snapshot.reference, repair.generation(row)))
        if snapshots and len(status_owners) < review.MIN_REPORT_OWNERS:
            counts_suppressed = True
            report['status_coverage'][status] = 'suppressed'
        else:
            report['status_coverage'][status] = 'capped' if len(snapshots) > args.per_status else 'complete'
    report.update(observations.receipt())
    if counts_suppressed or report['suppressed']:
        report['survey_documents'] = None
    report['repair']['candidate_owners'] = len(proposed) if len(proposed) >= review.MIN_REPORT_OWNERS else None
    if query_failed or report['budget_interrupted'] or not args.apply or len(proposed) < review.MIN_REPORT_OWNERS:
        return report, query_failed or report['budget_interrupted']

    outcomes = Counter()
    for owner, (ref, expected) in list(proposed.items())[: args.max_writes]:
        current = utcnow()
        if monotonic() >= stop_at or current >= args.execute_before:
            report['budget_interrupted'] = True
            break
        try:
            outcome = repair.arm(
                client, ref, owner, expected, deadline=stop_at, execute_before=args.execute_before.timestamp()
            )
        except Exception:
            outcomes['error'] += 1
            break
        outcomes[outcome] += 1
        if outcome == 'deadline_reached':
            report['budget_interrupted'] = True
            break
    report['repair']['outcomes'] = dict(sorted(outcomes.items()))
    return report, bool(outcomes['error'] or report['budget_interrupted'])


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--lane', choices=review.LANES, required=True)
    parser.add_argument('--start', type=_utc, required=True)
    parser.add_argument('--end', type=_utc, required=True)
    parser.add_argument('--per-status', type=int, default=200)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--max-writes', type=int)
    parser.add_argument('--execute-before', type=_utc)
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    if not timedelta(minutes=15) <= args.end - args.start <= timedelta(hours=24) or args.end > now:
        parser.error('the finished-at window must be 15 minutes to 24 hours and end in the past')
    if not 1 <= args.per_status <= MAX_PER_STATUS:
        parser.error(f'--per-status must be 1 to {MAX_PER_STATUS}')
    if args.apply:
        if args.lane != 'batch_live_v1':
            parser.error('summary admission repair is supported for batch live')
        if args.max_writes is None or not 1 <= args.max_writes <= MAX_WRITES:
            parser.error(f'--apply requires --max-writes between 1 and {MAX_WRITES}')
        if args.execute_before is None or not now < args.execute_before <= now + timedelta(minutes=30):
            parser.error('--apply requires --execute-before within the next 30 minutes')
    elif args.max_writes is not None or args.execute_before is not None:
        parser.error('--max-writes and --execute-before require --apply')
    if args.project == 'based-hardware':
        tier = 'prod-operator' if args.apply else 'ro-prod'
        if os.environ.get('GCP_AGENT_TIER') != tier or not os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
            parser.error(f'this production mode requires the {tier} agent environment')
    try:
        report, failed = run(firestore.Client(project=args.project), args, now=now)
    except Exception:
        print(json.dumps({'schema_version': 1, 'error': 'worker_failed'}))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
