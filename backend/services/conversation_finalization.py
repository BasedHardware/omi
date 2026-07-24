"""Durable dispatch and recovery for listen conversation finalization.

The Firestore job is the source of truth.  Cloud Tasks wakes a worker for
platform-key conversations; it is never allowed to carry content or BYOK
credentials.  BYOK jobs remain explicitly blocked until a live request again
presents its request-scoped keys.
"""

from __future__ import annotations

import logging
from typing import Any

from database import conversation_finalization_jobs as jobs_db
from utils.conversations import lifecycle as lifecycle_service
from utils.cloud_tasks import (
    enqueue_listen_finalization_job,
    get_listen_finalization_tasks_max_attempts,
    is_listen_finalization_dispatch_enabled,
)
from utils.metrics import (
    LISTEN_FINALIZATION_DEAD_LETTER_TOTAL,
    LISTEN_FINALIZATION_JOB_STATUS,
    LISTEN_FINALIZATION_OLDEST_NONTERMINAL_AGE_SECONDS,
    LISTEN_FINALIZATION_RETRIES_TOTAL,
    LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL,
)
from utils.observability.fallback import record_fallback
from utils.observability.journeys import (
    record_capture_finalization_reconciliation,
    record_capture_finalization_terminal,
)

logger = logging.getLogger(__name__)


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
    (``lifecycle.complete``): a row already completed, discarded, or superseded by
    a newer generation is fenced out, so the orphan reaches exactly one terminal
    and its recording stays retrievable. Re-enrichment is a separate follow-up;
    this safety net only ends the stuck lifecycle. It needs no durable dispatch,
    so it runs in every deployment mode.

    Outcomes are recorded on ``LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL``
    (privacy-safe: aggregate counts only, no user identifiers in success logs).
    """
    result: dict[str, int] = {'completed': 0, 'migrated': 0, 'skipped': 0, 'error': 0}
    stale_after = jobs_db.get_stale_processing_orphan_after()
    try:
        candidates = jobs_db.get_stale_processing_orphan_candidates(
            stale_after=stale_after, limit=limit, firestore_client=firestore_client
        )
    except Exception:
        logger.exception('stale processing conversation reconciliation query failed')
        LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL.labels(outcome='error').inc()
        return result | {'error': 1}
    for candidate in candidates:
        uid = candidate.get('uid')
        conversation_id = candidate.get('conversation_id')
        if not isinstance(uid, str) or not isinstance(conversation_id, str):
            result['skipped'] += 1
            continue
        try:
            if candidate.get('legacy'):
                # A stranded pre-fence row: stamp the server-owned admission
                # instant so a later sweep bounds recovery by admission age. Never
                # terminalize on first sight.
                jobs_db.stamp_processing_admission_if_absent(uid, conversation_id, firestore_client=firestore_client)
                result['migrated'] += 1
                LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL.labels(outcome='migrated').inc()
                continue
            completed = lifecycle_service.complete(uid, conversation_id)
        except Exception:
            logger.exception('stale processing conversation reconciliation failed for one row')
            result['skipped'] += 1
            LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL.labels(outcome='skipped').inc()
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
    for status in ('queued', 'leased', 'blocked_byok', 'dead_letter'):
        LISTEN_FINALIZATION_JOB_STATUS.labels(status=status).set(float(summary[status]))
