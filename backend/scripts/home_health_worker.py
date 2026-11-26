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

from config import episode_composition, episodes, transcription_pending
from config.summary_guarantee import deadline_seconds
from database import rpc_deadline
from services import home_health_repair as repair, home_health_review as review
from scripts import home_health_runtime as runtime
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


def _read_card_fields(client, entries, field_paths, transaction):
    if not entries:
        return
    remaining = {ref.path: row for ref, row in entries}
    refs = [ref for ref, _ in entries]
    for snapshot in client.get_all(refs, field_paths=field_paths, transaction=transaction):
        if not snapshot.exists:
            raise ValueError('missing card snapshot')
        remaining.pop(snapshot.reference.path).update(snapshot.to_dict() or {})
    if remaining:
        raise ValueError('incomplete card read')


def scan(client, *, lane, status, start, end, limit, deadline):
    @firestore.transactional
    def read_page(transaction):
        # All reads share a snapshot. The lookahead reads metadata only.
        snapshots = (
            client.collection_group('conversations')
            .where(filter=FieldFilter('record_lane_owner', '==', lane))
            .where(filter=FieldFilter('status', '==', status))
            .where(filter=FieldFilter('finished_at', '>=', start))
            .where(filter=FieldFilter('finished_at', '<', end))
            .order_by('finished_at', direction=firestore.Query.DESCENDING)
            .order_by('__name__', direction=firestore.Query.DESCENDING)
            .select(repair.DISCOVERY_FIELDS)
            .limit(limit + 1)
            .get(transaction=transaction)
        )
        rows = []
        owners = set()
        allowed = []
        title_checks = []
        for snapshot in snapshots[:limit]:
            owner = _scope(snapshot)
            if owner is None:
                continue
            row = snapshot.to_dict() or {}
            ref = snapshot.reference
            rows.append((owner, ref, row))
            owners.add(owner)
            if review.protected_for_review(row) or review.hidden_by_metadata(row):
                continue
            allowed.append((ref, row))
            if review.needs_title_for_visibility(row):
                title_checks.append((ref, row))
        if len(owners) < review.MIN_REPORT_OWNERS:
            return len(snapshots), rows
        _read_card_fields(client, title_checks, ('user_title',), transaction)
        if status == 'completed':
            cards = []
            for ref, row in allowed:
                if not review.needs_title_for_visibility(row):
                    cards.append((ref, row))
                elif not review.hidden_for_review(row, show_held=True):
                    # A settling row's transcription exception may depend on
                    # note content. Leave visibility unknown without reading it.
                    row['home_health_visibility_unknown'] = True
            _read_card_fields(client, cards, review.CARD_FIELDS, transaction)
        return len(snapshots), rows

    rpc_deadline.bind_firestore_client(client)
    with rpc_deadline.rpc_deadline(min(deadline, rpc_deadline.now() + SCAN_TIMEOUT)):
        return read_page(client.transaction(read_only=True, max_attempts=1))


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
        'home_step_projection_enabled': episodes.home_step_projection_enabled(),
        'home_visibility_policy': {
            'source': 'operator_environment',
            'transcription_presentation_gate_enabled': episodes.home_transcription_presentation_gate_enabled(),
            'transcription_queue_hold_enabled': episodes.home_transcription_queue_hold_enabled(),
            'transcription_seal_wait_enabled': transcription_pending.seal_wait_enabled(),
            'hide_below_floor_rows_enabled': episodes.home_hide_below_floor_rows_enabled(),
            'empty_output_noise_enabled': episodes.home_empty_output_noise_enabled(),
            'stale_empty_noise_enabled': transcription_pending.stale_empty_noise_enabled(),
            'legacy_empty_wire_enabled': episode_composition.legacy_empty_wire_enabled(),
            'processing_max_age_seconds': (
                episodes.home_processing_max_age_seconds() or episodes.DEFAULT_HOME_PROCESSING_MAX_AGE_SECONDS
            ),
            'transcription_max_age_seconds': episodes.home_transcription_max_age_seconds(),
            'transcription_deadline_seconds': episodes.home_transcription_deadline_seconds(),
        },
        'notes_deadline_seconds': deadline_seconds(),
        'repair_max_age_seconds': max_age_seconds(),
        'per_status_limit': args.per_status,
        'survey_documents': 0,
        'budget_interrupted': False,
        'status_coverage': dict.fromkeys(review.STATUSES, 'not_scanned'),
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
            scanned, rows = scan(
                client,
                lane=args.lane,
                status=status,
                start=args.start,
                end=args.end,
                limit=args.per_status,
                deadline=stop_at,
            )
        except Exception:
            # Driver errors can embed document references. No exception text
            # or traceback reaches a persistent receipt or operator log.
            report['status_coverage'][status] = 'query_failed'
            query_failed = True
            break
        status_owners = {owner for owner, _, _ in rows}
        if scanned and len(status_owners) < review.MIN_REPORT_OWNERS:
            counts_suppressed = True
            report['status_coverage'][status] = 'suppressed'
            continue
        report['survey_documents'] += scanned
        report['status_coverage'][status] = 'capped' if scanned > args.per_status else 'complete'
        for owner, ref, row in rows:
            findings = observations.observe(owner, row, now=now)
            if 'notes_not_scheduled' in findings and repair.candidate(row, now=now.timestamp()):
                proposed.setdefault(owner, (ref, repair.generation(row)))
    report.update(observations.receipt())
    if counts_suppressed or 'rows' not in report['metrics']:
        report['survey_documents'] = None
    enough_owners = len(proposed) >= review.MIN_REPORT_OWNERS
    report['repair']['candidate_owners'] = len(proposed) if enough_owners else None
    if not enough_owners:
        report['repair']['candidate_owners_state'] = 'below_reporting_minimum'
    if query_failed or report['budget_interrupted'] or not args.apply or not enough_owners:
        return report, query_failed or report['budget_interrupted']

    if getattr(client, 'project', None) == runtime.PRODUCTION_PROJECT:
        deadline = min(stop_at, monotonic() + (args.execute_before - utcnow()).total_seconds())
        if not runtime.serving_allows_repair(deadline=deadline):
            report['repair']['serving_policy'] = 'unavailable_or_disabled'
            return report, True
        report['repair']['serving_policy'] = 'enabled'

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
    # Each attempt has a distinct owner. A published bucket could reveal a
    # suppressed bucket by subtraction, so publish the breakdown as a whole.
    if outcomes and min(outcomes.values()) >= review.MIN_REPORT_OWNERS:
        report['repair']['outcomes'] = dict(sorted(outcomes.items()))
        return report, bool(outcomes['error'] or report['budget_interrupted'])
    report['repair']['outcomes'] = None
    report['repair']['outcomes_state'] = 'below_reporting_minimum'
    report['budget_interrupted'] = None
    # An inconclusive apply must stop automation regardless of the private
    # outcomes. Subsequent read-only review can verify durable admissions.
    return report, True


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
    if args.project == runtime.PRODUCTION_PROJECT:
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
