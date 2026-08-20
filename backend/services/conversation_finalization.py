"""Durable dispatch and recovery for listen conversation finalization.

The Firestore job is the source of truth.  Cloud Tasks wakes a worker for
platform-key conversations; it is never allowed to carry content or BYOK
credentials.  BYOK jobs remain explicitly blocked until a live request again
presents its request-scoped keys.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from google.api_core.exceptions import InvalidArgument

from database import conversation_finalization_jobs as jobs_db
from database._client import is_document_size_limit_error
from utils.cloud_tasks import (
    enqueue_listen_finalization_job,
    get_listen_finalization_tasks_max_attempts,
    is_listen_finalization_dispatch_enabled,
)
from utils.metrics import (
    LISTEN_FINALIZATION_DEAD_LETTER_TOTAL,
    LISTEN_FINALIZATION_DURABLE_JOBS,
    LISTEN_FINALIZATION_JOB_STATUS,
    LISTEN_FINALIZATION_OLDEST_NONTERMINAL_AGE_SECONDS,
    LISTEN_FINALIZATION_RETRIES_TOTAL,
    LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL,
)
from utils.observability.fallback import record_fallback
from utils.conversations.meeting_receipt import (
    record_and_persist_finalized_meeting_receipt,
    repair_meeting_receipt_intent,
)
from utils.observability.journeys import (
    record_capture_finalization_reconciliation,
    record_capture_finalization_terminal,
)

logger = logging.getLogger(__name__)


def is_meeting_receipt_reconciler_enabled() -> bool:
    return os.getenv('MEETING_RECEIPT_RECONCILER_ENABLED', 'false').strip().lower() in {'1', 'true', 'yes', 'on'}


def reconcile_meeting_receipts(limit: int = 100, *, firestore_client: Any = None) -> dict[str, int]:
    """Repair missing intent writes and seed receipts for historical completed meetings."""
    result = {'repaired': 0, 'backfilled': 0, 'skipped': 0, 'error': 0}
    if not is_meeting_receipt_reconciler_enabled():
        return result

    try:
        candidates = jobs_db.get_meeting_receipt_reconcile_candidates(limit=limit, firestore_client=firestore_client)
    except Exception:
        logger.exception('meeting receipt reconciliation query failed')
        result['error'] += 1
        candidates = []
    for candidate in candidates:
        try:
            if repair_meeting_receipt_intent(candidate):
                result['repaired'] += 1
            else:
                result['skipped'] += 1
        except Exception:
            logger.exception('meeting receipt intent repair failed')
            result['error'] += 1

    try:
        cursor = jobs_db.get_meeting_receipt_backfill_cursor(firestore_client=firestore_client)
        sweep = jobs_db.get_meeting_receipt_backfill_candidates(
            limit=limit,
            resume_after_path=cursor.get('resume_after_path'),
            firestore_client=firestore_client,
        )
        jobs_db.advance_meeting_receipt_backfill_cursor(
            int(cursor.get('generation') or 0),
            None if sweep['exhausted'] else sweep['resume_after_path'],
            firestore_client=firestore_client,
        )
    except Exception:
        logger.exception('meeting receipt backfill query failed')
        result['error'] += 1
        return result
    for candidate in sweep['candidates']:
        try:
            receipt = record_and_persist_finalized_meeting_receipt(
                candidate['uid'], candidate['conversation'], firestore_client=firestore_client
            )
            if receipt is not None:
                result['backfilled'] += 1
            else:
                result['skipped'] += 1
        except Exception:
            logger.exception('meeting receipt backfill failed')
            result['error'] += 1
    return result


def reconcile_listen_finalization_jobs(limit: int = 100, *, firestore_client: Any = None) -> dict[str, int | float]:
    """Replay stale queued/leased platform-key jobs and publish backlog signals."""
    result: dict[str, int | float] = {'requeued': 0, 'skipped': 0, 'enqueue_failed': 0}
    if not is_listen_finalization_dispatch_enabled():
        _publish_job_metrics(firestore_client=firestore_client)
        return result

    stale_after = jobs_db.get_finalization_reconcile_stale_after()
    try:
        candidates = jobs_db.get_finalization_replay_candidates(limit=limit, firestore_client=firestore_client)
    except Exception:
        logger.exception('listen finalization reconciliation query failed')
        _publish_job_metrics(firestore_client=firestore_client)
        return result | {'error': 1}

    for candidate in candidates:
        job_id = candidate.get('job_id')
        if not isinstance(job_id, str) or not job_id:
            result['skipped'] += 1
            continue
        try:
            claimed = jobs_db.claim_finalization_replay(
                job_id,
                stale_after=stale_after,
                firestore_client=firestore_client,
            )
        except Exception:
            logger.exception('listen finalization reconciliation claim failed job=%s', job_id)
            result['skipped'] += 1
            continue
        if claimed['status'] != 'queued' or claimed['dispatch_generation'] is None:
            result['skipped'] += 1
            continue
        try:
            enqueue_listen_finalization_job(job_id, int(claimed['dispatch_generation']))
        except Exception:
            record_capture_finalization_reconciliation('enqueue_failed')
            record_fallback(
                component='pusher',
                from_mode='cloud_tasks',
                to_mode='durable_queued',
                reason='enqueue_failed',
                outcome='degraded',
                log=logger,
            )
            logger.exception('listen finalization reconciliation enqueue failed job=%s', job_id)
            result['enqueue_failed'] += 1
            continue
        result['requeued'] += 1
        record_capture_finalization_reconciliation('requeued')
        LISTEN_FINALIZATION_RETRIES_TOTAL.inc()

    _publish_job_metrics(firestore_client=firestore_client)
    return result


def reconcile_stale_processing_conversations(limit: int = 100, *, firestore_client: Any = None) -> dict[str, int]:
    """Close bare-`processing` conversations stranded by a synchronous-route crash.

    The durable replay sweep (``reconcile_listen_finalization_jobs``) only covers
    rows with a finalization job. A bare-`processing` row admitted by the
    synchronous legacy route (or a server/merge create) and then lost to a hard
    crash has no job, so it is never replayed and the recording never resolves.

    Eligibility is bounded by the authoritative, server-owned admission fence
    ``processing_admitted_at`` (never caller-controlled ``created_at``), so a live
    synchronous run whose admission is still under the conservative threshold can
    never be terminalized. A legacy row predating the fence is migrated by
    stamping the fence and deferred to a later sweep rather than completed on
    sight. Each aged orphan is driven through the truthful terminal ownership CAS
    (``complete_orphan_conversation``): a row already completed, discarded,
    superseded by a newer generation, or since bound to a durable job is fenced
    out, so the orphan reaches exactly one terminal and its recording stays
    retrievable. Re-enrichment is a separate follow-up; this safety net only ends
    the stuck lifecycle. It needs no durable dispatch, so it runs in every
    deployment mode.

    Eventual discovery is guaranteed by a persisted, rotated sweep cursor: each
    periodic invocation resumes a bounded window from the cursor and wraps to the
    top once the collection is exhausted, so a stable excluded prefix larger than
    the per-invocation bound cannot permanently hide a later orphan.

    Outcomes are recorded on ``LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL``
    (privacy-safe: aggregate counts only, no user identifiers in success logs).
    Unexpected per-row failures are counted as ``error``; an expected CAS fencing
    (the row moved on) is ``skipped``.
    """
    result: dict[str, int] = {'completed': 0, 'migrated': 0, 'skipped': 0, 'error': 0}
    stale_after = jobs_db.get_stale_processing_orphan_after()
    try:
        cursor = jobs_db.get_stale_processing_sweep_cursor(firestore_client=firestore_client)
    except Exception:
        logger.exception('stale processing sweep cursor read failed; sweeping from the top')
        cursor = {'resume_after_path': None, 'generation': 0}
    _path = cursor.get('resume_after_path')
    resume_after_path: str | None = _path if isinstance(_path, str) else None
    expected_generation: int = int(cursor.get('generation') or 0)
    try:
        sweep = jobs_db.get_stale_processing_orphan_candidates(
            stale_after=stale_after, limit=limit, resume_after_path=resume_after_path, firestore_client=firestore_client
        )
    except Exception:
        logger.exception('stale processing conversation reconciliation query failed')
        LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL.labels(outcome='error').inc()
        return result | {'error': 1}
    next_cursor = None if sweep['exhausted'] else sweep['resume_after_path']
    try:
        jobs_db.advance_stale_processing_sweep_cursor(
            expected_generation, next_cursor, firestore_client=firestore_client
        )
    except Exception:
        logger.exception('stale processing sweep cursor advance failed; coverage is still guaranteed')
    for candidate in sweep['candidates']:
        uid = candidate.get('uid')
        conversation_id = candidate.get('conversation_id')
        if not isinstance(uid, str) or not isinstance(conversation_id, str):
            result['skipped'] += 1
            LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL.labels(outcome='skipped').inc()
            continue
        try:
            if candidate.get('legacy'):
                # A stranded pre-fence row: stamp the server-owned admission
                # instant so a later sweep bounds recovery by admission age. Never
                # terminalize on first sight.  Only a successful stamp counts as
                # ``migrated``; a CAS loss (already stamped / status changed /
                # absent) is an expected ``skipped`` fencing, never a migration.
                try:
                    stamped = jobs_db.stamp_processing_admission_if_absent(
                        uid, conversation_id, firestore_client=firestore_client
                    )
                except InvalidArgument as error:
                    if not is_document_size_limit_error(error):
                        raise
                    # The row is at Firestore's 1 MiB document ceiling, so the
                    # fence can never be stamped: migration would fail on every
                    # future sweep and the conversation would stay `processing`
                    # for good. Terminalize it on the server-owned last-write
                    # instant instead — that shrinking write is the one update
                    # the document still accepts.
                    record_fallback(
                        component='pusher',
                        from_mode='admission_stamp',
                        to_mode='unstampable_terminal',
                        reason='other',
                        outcome='degraded',
                        log=logger,
                    )
                    if jobs_db.complete_unstampable_orphan_conversation(
                        uid, conversation_id, stale_after=stale_after, firestore_client=firestore_client
                    ):
                        result['completed'] += 1
                        LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL.labels(outcome='completed').inc()
                    else:
                        result['skipped'] += 1
                        LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL.labels(outcome='skipped').inc()
                    continue
                if stamped:
                    result['migrated'] += 1
                    LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL.labels(outcome='migrated').inc()
                else:
                    result['skipped'] += 1
                    LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL.labels(outcome='skipped').inc()
                continue
            completed = jobs_db.complete_orphan_conversation(
                uid,
                conversation_id,
                expected_admitted_at=candidate.get('processing_admitted_at'),
                firestore_client=firestore_client,
            )
        except Exception:
            # An unexpected per-row failure (e.g. Firestore unavailable) is an
            # error, distinct from an expected CAS fencing skip below.
            logger.exception('stale processing conversation reconciliation failed for one row')
            result['error'] += 1
            LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL.labels(outcome='error').inc()
            continue
        if completed:
            result['completed'] += 1
            LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL.labels(outcome='completed').inc()
        else:
            result['skipped'] += 1
            LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL.labels(outcome='skipped').inc()
    if result['completed'] or result['migrated']:
        logger.info('stale processing conversation reconciliation: %s', result)
    return result


def final_attempt_failed(
    job_id: str, dispatch_generation: int, lease_epoch: int, retry_count: int, *, firestore_client: Any = None
) -> bool:
    marked = jobs_db.mark_finalization_dead_letter(
        job_id,
        dispatch_generation,
        lease_epoch,
        retry_count,
        firestore_client=firestore_client,
    )
    if marked:
        LISTEN_FINALIZATION_DEAD_LETTER_TOTAL.inc()
        try:
            job = jobs_db.get_finalization_job(job_id, firestore_client=firestore_client)
            accepted_at = job.get('created_at') if job else None
            record_capture_finalization_terminal('failure', accepted_at)
        except Exception:
            # Dead-lettering is authoritative; a best-effort metric lookup must
            # never change its terminal outcome.
            logger.exception('listen finalization terminal metric lookup failed job=%s', job_id)
    return marked


def get_listen_finalization_tasks_max_attempts_for_worker() -> int:
    return get_listen_finalization_tasks_max_attempts()


def _publish_job_metrics(*, firestore_client: Any = None) -> None:
    try:
        summary = jobs_db.get_finalization_job_summary(firestore_client=firestore_client)
    except Exception:
        logger.exception('listen finalization metrics query failed')
        return
    LISTEN_FINALIZATION_OLDEST_NONTERMINAL_AGE_SECONDS.set(float(summary['oldest_nonterminal_age_seconds']))
    for state in ('accepted', 'success', 'failure', 'stale', 'nonterminal', 'blocked_byok', 'terminal_unknown'):
        LISTEN_FINALIZATION_DURABLE_JOBS.labels(state=state).set(float(summary[state]))
    for status in ('queued', 'leased', 'blocked_byok', 'dead_letter'):
        LISTEN_FINALIZATION_JOB_STATUS.labels(status=status).set(float(summary[status]))
