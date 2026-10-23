#!/usr/bin/env python3
"""Approved-plan operator for historical stuck rows. Never run apply without GO.

Runtime: PYTHONPATH=backend backend/.venv/bin/python backend/scripts/stuck_backfill.py ...
Private plans/journals contain IDs and revisions, never content. Stdout is counts-only.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import stat
import sys
import time
import uuid
from typing import Any

from google.api_core.datetime_helpers import DatetimeWithNanoseconds
from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client
from database import conversations, conversation_finalization_jobs as jobs, stuck_backfill as db
from utils.conversations import lifecycle
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.backfill_stats import transcript_stats, classify

FIELDS = [
    'status',
    'source',
    'finished_at',
    'transcript_segments',
    'transcript_segments_compressed',
    'audio_files',
    'discarded',
    'deleted',
    'is_locked',
    'deferred',
    'processing_state',
    'terminal_no_derived_effects',
    'structured',
    'user_title',
    'finalization_job_id',
    'finalization_revision',
    'external_data',
    'has_content',
    'has_photos',
    'record_lane_owner',
    'silent_backfill',
]
SUMMARY_USD = 0.0011


def require(condition: Any, reason: str) -> None:
    if not condition:
        raise db.BackfillConflict(reason)


def private_read(path: Path) -> bytes:
    require(not path.is_symlink() and path.is_file(), 'private_file_required')
    require(stat.S_IMODE(path.stat().st_mode) == 0o600, 'private_file_requires_0600')
    require(path.stat().st_size <= 16 * 1024 * 1024, 'private_file_too_large')
    return path.read_bytes()


def private_write(path: Path, data: dict[str, Any]) -> None:
    # Never replace another plan, receipt or symlink.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(data, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())


def parse_time(value: str) -> datetime:
    return DatetimeWithNanoseconds.from_rfc3339(value)


def owner_allowlist(path: Path) -> set[str]:
    owners = set(private_read(path).decode().splitlines()) - {''}
    require(0 < len(owners) <= 1000 and all('/' not in u and u.strip() == u for u in owners), 'unsafe_owner_allowlist')
    return owners


def make_plan(
    client: Any, owners: set[str], cutoff: datetime, limit: int, seconds: float, words: int, budget_usd: float = 100.0
) -> dict[str, Any]:
    require(cutoff.tzinfo and cutoff <= datetime.now(timezone.utc) - timedelta(hours=1), 'unsafe_cutoff')
    rows = []
    for uid in sorted(owners):
        user = client.collection('users').document(uid)
        snapshots = list(
            user.collection('conversations')
            .where(filter=FieldFilter('status', '==', 'in_progress'))
            .select(FIELDS)
            .limit(limit + 1)
            .stream(timeout=60)
        )
        require(len(snapshots) <= limit, 'owner_inventory_exceeds_bound')
        for snap in snapshots:
            require(len(rows) < 10000, 'cohort_inventory_exceeds_bound')
            row = snap.to_dict() or {}
            reason = (
                'record_owner'
                if row.get('record_lane_owner')
                else jobs.recovery_admission_refusal(uid, {**row, 'has_content': True}, cutoff)
            )
            if reason and reason != 'no_content':
                kind, stats = 'skip_' + reason, {}
            else:
                try:
                    segments = conversations.decode_transcript_segments_verified(
                        uid, row.get('transcript_segments') or [], bool(row.get('transcript_segments_compressed'))
                    )
                    stats = transcript_stats(segments)
                    kind = classify(stats, bool(row.get('audio_files')), seconds=seconds, words=words)
                except Exception:
                    kind, stats = 'review_decode_error', {}
            external = row.get('external_data') or {}
            sid = external.get('recording_session_id') if isinstance(external, dict) else None
            if sid is not None and (not isinstance(sid, str) or not sid or '/' in sid):
                kind, sid = 'skip_invalid_session', None
            session = user.collection('recording_sessions').document(sid).get() if sid else None
            session_rev = db.revision(session) if session else None
            session_row = session.to_dict() or {} if session else {}
            lease = session_row.get('lease_expires_at')
            if isinstance(lease, datetime) and lease > datetime.now(timezone.utc):
                kind = 'skip_active_session'
            finished = row.get('finished_at')
            rows.append(
                {
                    'uid': uid,
                    'id': snap.id,
                    'revision': db.revision(snap),
                    'session_revision': session_rev,
                    'finished_at': finished.isoformat() if finished else '',
                    'kind': kind,
                    'stats': stats,
                    'has_audio_ref': bool(row.get('audio_files')),
                    'modeled_usd': SUMMARY_USD * 3 if kind == 'substantive' else 0.0,
                }
            )
    rows.sort(key=lambda r: (r['finished_at'], r['id']), reverse=True)
    return {
        'schema_version': 1,
        'policy': db.POLICY,
        'max_modeled_usd': budget_usd,
        'project': 'based-hardware',
        'run_id': uuid.uuid4().hex,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'cutoff': cutoff.isoformat(),
        'thresholds': {'seconds': seconds, 'words': words},
        'rows': rows,
    }


def summarize(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        'counts': dict(Counter(r['kind'] for r in plan['rows'])),
        'modeled_upper_usd': sum(r['modeled_usd'] for r in plan['rows']),
        'summary_only_usd': sum(r['kind'] == 'substantive' for r in plan['rows']) * SUMMARY_USD,
    }


def check_enabled(client: Any, plan: dict[str, Any], digest: str) -> None:
    control = client.collection('stuck_backfill_runs').document(plan['run_id']).get().to_dict() or {}
    require(
        control.get('enabled') is True and control.get('approved_plan_sha256') == digest, 'run_disabled_or_plan_changed'
    )
    require(0 < float(control.get('max_modeled_usd', 0)) <= plan['max_modeled_usd'], 'run_budget_exceeds_plan')
    require(
        bool(control.get('silent_canary_evidence_ref')) and bool(control.get('queue_consumers_evidence_ref')),
        'serving_silence_evidence_required',
    )
    # Explicit serving-release evidence belongs to the runtime operator. The control
    # is only armed after both forward fixes and this policy ship on all consumers.
    require(
        control.get('verified_delivery_policy') == db.POLICY and bool(control.get('verified_release_sha')),
        'serving_policy_not_verified',
    )


def wait_job(
    client: Any, plan: dict[str, Any], digest: str, item: dict[str, Any], intent: dict[str, Any], timeout: float
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        check_enabled(client, plan, digest)
        job = jobs.get_finalization_job(intent['job_id'], firestore_client=client) or {}
        require(
            job.get('uid') == item['uid']
            and job.get('conversation_id') == item['id']
            and job.get('processing_trigger') == ProcessingTrigger.SILENT_BACKFILL.value
            and job.get('delivery_policy') == db.POLICY
            and job.get('backfill_run_id') == plan['run_id']
            and job.get('dispatch_generation') == intent['dispatch_generation'],
            'job_identity_changed',
        )
        if job.get('status') in jobs.TERMINAL_JOB_STATUSES:
            require(
                job.get('status') == 'completed'
                and job.get('fanout_status') == 'completed'
                and job.get('terminal_outcome') == 'success',
                'canary_job_failed',
            )
            snap = (
                client.collection('users').document(item['uid']).collection('conversations').document(item['id']).get()
            )
            row = snap.to_dict() or {}
            require(
                row.get('status') == 'completed'
                and not row.get('discarded')
                and not row.get('deleted')
                and not row.get('processing_deferred')
                and row.get('processing_state') != 'local_pending'
                and row.get('finalization_job_id') == intent['job_id']
                and row.get('terminal_no_derived_effects') is True,
                'canary_row_failed',
            )
            return {
                'closed_revision': db.revision(snap),
                'job_id': intent['job_id'],
                'dispatch_generation': intent['dispatch_generation'],
                'finalization_revision': job.get('finalization_revision'),
            }
        time.sleep(min(2, max(0, deadline - time.monotonic())))
    raise db.BackfillConflict('job_timeout_preserve_inflight')


def actual_spend(path: Path | None, digest: str, batch: int) -> float | None:
    if path is None or not path.exists():
        return None
    ledger = json.loads(private_read(path))
    receipt = next((r for r in ledger if r.get('plan_sha256') == digest and r.get('batch') == batch), None)
    if receipt is None:
        return None
    cost = receipt.get('actual_usd')
    require(
        isinstance(cost, (int, float))
        and math.isfinite(cost)
        and cost >= 0
        and bool(receipt.get('vendor_evidence_ref')),
        'invalid_spend_receipt',
    )
    return float(cost)


def enforce_actual_budget(client: Any, plan: dict[str, Any], actual_total: float) -> None:
    require(math.isfinite(actual_total) and actual_total >= 0, 'invalid_actual_total')
    if actual_total > plan['max_modeled_usd']:
        client.collection('stuck_backfill_runs').document(plan['run_id']).update({'enabled': False})
        raise db.BackfillConflict('actual_budget_exceeded')


def apply(client: Any, plan: dict[str, Any], digest: str, args: Any) -> None:
    directory = args.receipts_dir
    require(directory is not None, 'receipts_directory_required')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(
        not directory.is_symlink() and stat.S_IMODE(directory.stat().st_mode) == 0o700,
        'receipts_directory_requires_0700',
    )
    actual_total = 0.0
    actionable = [r for r in plan['rows'] if r['kind'] in {'noise', 'substantive'}]
    for offset in range(0, len(actionable), args.batch_size):
        batch = offset // args.batch_size + 1
        items = actionable[offset : offset + args.batch_size]
        item_identity = [{k: item[k] for k in ['uid', 'id', 'revision', 'kind']} for item in items]
        binding = {
            'plan_sha256': digest,
            'batch': batch,
            'batch_size': args.batch_size,
            'items_sha256': hashlib.sha256(json.dumps(item_identity, sort_keys=True).encode()).hexdigest(),
        }
        journal = directory / f'batch-{batch:05d}.private.json'
        if journal.exists():
            previous = json.loads(private_read(journal))
            require(
                all(previous.get(key) == value for key, value in binding.items()) and previous.get('complete') is True,
                'incomplete_batch_requires_review',
            )
            cost = previous.get('actual_spend_usd')
            if cost is None:
                cost = actual_spend(args.spend_receipts, digest, batch)
            if cost is None:
                raise db.BackfillConflict('actual_spend_reconciliation_required')
            actual_total += float(cost)
            enforce_actual_budget(client, plan, actual_total)
            continue
        if batch > 1:
            require(
                json.loads(private_read(directory / f'batch-{batch - 1:05d}.private.json')).get('actual_spend_usd')
                is not None
                or actual_spend(args.spend_receipts, digest, batch - 1) is not None,
                'actual_spend_reconciliation_required',
            )
        entries, counts, modeled = [], Counter(), 0.0
        private_write(journal, {**binding, 'complete': False, 'entries': []})
        try:
            for item in items:
                check_enabled(client, plan, digest)
                require(
                    actual_total + modeled + item['modeled_usd'] <= plan['max_modeled_usd'],
                    'reconciled_budget_exhausted',
                )
                while True:
                    delay = db.reserve_admission(plan['run_id'], digest, item['modeled_usd'], firestore_client=client)
                    if not delay:
                        break
                    time.sleep(min(delay, 2))
                    check_enabled(client, plan, digest)
                modeled += item['modeled_usd']
                counts['reserved'] += 1
                if item['kind'] == 'noise':
                    closed_revision = lifecycle.close_stuck_backfill_noise(
                        item['uid'],
                        item['id'],
                        expected_revision=item['revision'],
                        cutoff=parse_time(plan['cutoff']),
                        expected_session_revision=item['session_revision'],
                        run_id=plan['run_id'],
                        firestore_client=client,
                    )
                    snap = (
                        client.collection('users')
                        .document(item['uid'])
                        .collection('conversations')
                        .document(item['id'])
                        .get()
                    )
                    require(db.revision(snap) == closed_revision, 'noise_changed_after_close')
                    result = {'closed_revision': closed_revision}
                else:
                    intent = lifecycle.request_finalization(
                        item['uid'],
                        item['id'],
                        has_byok_keys=False,
                        trigger=ProcessingTrigger.SILENT_BACKFILL,
                        require_cloud_tasks=True,
                        recovery_cutoff=parse_time(plan['cutoff']),
                        expected_update_time=parse_time(item['revision']),
                        expected_session_revision=item['session_revision'],
                        backfill_run_id=plan['run_id'],
                        firestore_client=client,
                    )
                    require(intent.get('created') and intent.get('route') == 'cloud_tasks', 'admission_not_dispatched')
                    # Sequential completion is stronger than per-owner serialization;
                    # the transactional owner fence also covers other/restarted operators.
                    result = wait_job(client, plan, digest, item, intent, args.job_timeout)
                entries.append({**{k: item[k] for k in ['uid', 'id', 'kind', 'revision']}, **result})
                counts[item['kind']] += 1
                # Persist after each outcome with atomic replacement; an admission with
                # lost ACK leaves incomplete=True and stops unattended resumption.
                tmp = journal.with_suffix('.tmp')
                private_write(tmp, {**binding, 'complete': False, 'entries': entries})
                os.replace(tmp, journal)
        except BaseException:
            # Freeze the shared run, including other operator processes. Do not
            # cancel an already admitted durable job or rewrite its generation.
            client.collection('stuck_backfill_runs').document(plan['run_id']).update({'enabled': False})
            print(
                json.dumps(
                    {
                        'batch': batch,
                        'counts': dict(counts),
                        'modeled_upper_usd': modeled,
                        'actual_spend_usd': None,
                        'status': 'stopped_requires_review',
                    }
                ),
                flush=True,
            )
            raise
        receipt = {
            **binding,
            'complete': True,
            'entries': entries,
            'counts': dict(counts),
            'modeled_upper_usd': modeled,
            'actual_spend_usd': (
                0.0 if not counts['substantive'] else actual_spend(args.spend_receipts, digest, batch)
            ),
        }
        tmp = journal.with_suffix('.tmp')
        private_write(tmp, receipt)
        os.replace(tmp, journal)
        print(
            json.dumps({k: v for k, v in receipt.items() if k not in {'entries', 'plan_sha256', 'items_sha256'}}),
            flush=True,
        )
        # Never report unmeasured cost as zero, or expand past an unreconciled batch.
        if receipt['actual_spend_usd'] is None:
            raise db.BackfillConflict('actual_spend_reconciliation_required')
        actual_total += receipt['actual_spend_usd']
        enforce_actual_budget(client, plan, actual_total)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--plan', type=Path)
    mode.add_argument('--apply-approved-plan', type=Path)
    mode.add_argument('--restore-noise', type=Path, help='private completed batch receipt')
    parser.add_argument('--approved-plan-sha256')
    parser.add_argument('--owner-allowlist', type=Path, required=True)
    parser.add_argument('--cutoff')
    parser.add_argument('--max-rows-per-owner', type=int, default=1000)
    parser.add_argument('--min-speech-seconds', type=float, default=60)
    parser.add_argument('--min-words', type=int, default=100)
    parser.add_argument('--max-modeled-usd', type=float, default=100.0)
    parser.add_argument('--batch-size', type=int, default=10)
    parser.add_argument('--job-timeout', type=float, default=600)
    parser.add_argument('--receipts-dir', type=Path)
    parser.add_argument('--spend-receipts', type=Path)
    parser.add_argument('--run-id', help='required only for restore')
    args = parser.parse_args()
    require(
        1 <= args.max_rows_per_owner <= 10000
        and 1 <= args.batch_size <= 100
        and 0 < args.min_speech_seconds < 86400
        and args.min_words > 0
        and 0 < args.job_timeout <= 3600
        and math.isfinite(args.max_modeled_usd)
        and 0 < args.max_modeled_usd <= 100000,
        'unsafe_bounds',
    )
    require(
        os.getenv('GCP_AGENT_TIER') == 'prod-operator' and not os.getenv('FIRESTORE_EMULATOR_HOST'), 'wrong_runtime'
    )
    owners = owner_allowlist(args.owner_allowlist)
    logging.getLogger('utils.encryption').disabled = True  # tolerant decoder logs UIDs on authentication failure
    client = get_firestore_client()
    require(client.project == 'based-hardware', 'wrong_project')
    if args.restore_noise:
        require(args.run_id, 'restore_run_required')
        receipt = json.loads(private_read(args.restore_noise))
        require(
            receipt.get('complete') is True and receipt.get('plan_sha256') == args.approved_plan_sha256,
            'restore_approval_mismatch',
        )
        count = 0
        for entry in receipt['entries']:
            if entry['kind'] == 'noise':
                require(entry['uid'] in owners, 'owner_not_approved')
                lifecycle.restore_stuck_backfill_noise(
                    entry['uid'],
                    entry['id'],
                    expected_closed_revision=entry['closed_revision'],
                    run_id=args.run_id,
                    firestore_client=client,
                )
                count += 1
        print(json.dumps({'restored_noise': count}))
        return
    if args.apply_approved_plan:
        raw = private_read(args.apply_approved_plan)
        digest = hashlib.sha256(raw).hexdigest()
        require(digest == args.approved_plan_sha256, 'plan_digest_mismatch')
        plan = json.loads(raw)
        require(
            plan.get('schema_version') == 1
            and plan.get('policy') == db.POLICY
            and plan.get('project') == 'based-hardware',
            'invalid_plan',
        )
        require(all(r['uid'] in owners for r in plan['rows']), 'owner_not_approved')
        require(0 < len(plan['rows']) <= 10000, 'unsafe_plan_bound')
        require(
            all(r['modeled_usd'] == (SUMMARY_USD * 3 if r['kind'] == 'substantive' else 0.0) for r in plan['rows']),
            'invalid_modeled_cost',
        )
        require(
            plan['rows'] == sorted(plan['rows'], key=lambda r: (r['finished_at'], r['id']), reverse=True),
            'plan_not_newest_first',
        )
        apply(client, plan, digest, args)
        return
    require(args.cutoff, 'cutoff_required')
    plan = make_plan(
        client,
        owners,
        parse_time(args.cutoff),
        args.max_rows_per_owner,
        args.min_speech_seconds,
        args.min_words,
        args.max_modeled_usd,
    )
    if args.plan:
        private_write(args.plan, plan)
    print(json.dumps({'mode': 'plan' if args.plan else 'dry_run', **summarize(plan)}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        reason = str(error) if isinstance(error, db.BackfillConflict) else type(error).__name__
        print(json.dumps({'stopped': reason}), file=sys.stderr)
        raise SystemExit(1)
