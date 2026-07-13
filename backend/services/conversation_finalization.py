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
)
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


def prepare_listen_finalization(
    uid: str,
    conversation_id: str,
    *,
    has_byok_keys: bool,
    firestore_client: Any = None,
) -> dict[str, Any]:
    """Create finalization intent and select the bounded worker handoff.

    Returns ``route``:
    - ``pusher``: legacy/live pusher executes while claiming the same job;
    - ``cloud_tasks``: durable worker task was enqueued;
    - ``queued``: intent persisted but enqueue failed; reconciler owns recovery;
    - ``blocked_byok``: no durable credential custody is permitted;
    - ``noop``: no actionable persisted conversation exists.
    """
    intent = jobs_db.create_or_get_finalization_intent(
        uid,
        conversation_id,
        requires_byok=has_byok_keys,
        firestore_client=firestore_client,
    )
    status = intent['status']
    if intent['job_id'] is None or status in {'missing', 'no_content', 'deferred', 'completed', 'dead_letter'}:
        return dict(intent) | {'route': 'noop'}

    if intent['requires_byok']:
        # A task worker cannot safely acquire request-scoped keys.  In inline
        # An existing BYOK job can only resume when this request actually
        # presents keys again; it must never silently fall back to Omi keys.
        # Cloud Tasks remains reserved for platform-key work, but a live BYOK
        # pusher request can safely claim this same durable job in either mode.
        if not has_byok_keys:
            record_fallback(
                component='pusher',
                from_mode='cloud_tasks',
                to_mode='blocked_byok',
                reason='byok',
                outcome='degraded',
                log=logger,
            )
            return dict(intent) | {'route': 'blocked_byok'}
        resumed = jobs_db.resume_blocked_byok_job_for_live_session(intent['job_id'], firestore_client=firestore_client)
        return dict(resumed) | {'route': 'pusher'}

    if not is_listen_finalization_dispatch_enabled():
        return dict(intent) | {'route': 'pusher'}

    try:
        enqueue_listen_finalization_job(intent['job_id'], int(intent['dispatch_generation'] or 1))
    except Exception:
        # The transaction has committed, so do not fall back to a second owner.
        # Reconciliation will issue a new dispatch generation after the stale
        # window; emitting shared telemetry keeps this degraded state visible.
        record_fallback(
            component='pusher',
            from_mode='cloud_tasks',
            to_mode='durable_queued',
            reason='enqueue_failed',
            outcome='degraded',
            log=logger,
        )
        logger.exception('listen finalization enqueue failed job=%s', intent['job_id'])
        return dict(intent) | {'route': 'queued'}
    return dict(intent) | {'route': 'cloud_tasks'}


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
        LISTEN_FINALIZATION_RETRIES_TOTAL.inc()

    _publish_job_metrics(firestore_client=firestore_client)
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
