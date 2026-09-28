"""Protected Cloud Tasks worker for durable listen conversation finalization."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from database import conversation_finalization_jobs as jobs_db
from database.sync_jobs import release_job_run_lock, try_acquire_job_run_lock
from services.conversation_finalization import (
    final_attempt_failed,
    get_listen_finalization_tasks_max_attempts_for_worker,
)
from utils.cloud_tasks import verify_listen_finalization_cloud_tasks_oidc
from utils.account_cutover.access import should_skip_background_account_mutation
from utils.conversations import lifecycle as lifecycle_service
from utils.conversations.processing_trigger import trigger_for_finalization_job
from utils.conversations.finalizer import (
    ConversationFinalizationDisposition,
    ConversationFinalizationError,
    finalize_persisted_conversation,
)
from utils.executors import db_executor, run_blocking
from utils.metrics import LISTEN_FINALIZATION_RETRIES_TOTAL
from utils.observability.journeys import (
    record_capture_finalization_terminal,
    record_conversation_finalization_client_terminal,
)
from utils.observability.finalization import finalization_diagnostic_id

logger = logging.getLogger(__name__)

router = APIRouter()


def _durable_attempt_cap_enabled() -> bool:
    return os.getenv('LISTEN_FINALIZATION_DURABLE_ATTEMPT_CAP_ENABLED', 'true').strip().lower() in {
        '1',
        'true',
        'yes',
        'on',
    }


def _parse_task_payload(payload: Any) -> tuple[str, int] | None:
    """Accept exactly the opaque durable task schema, never credential fields."""
    if not isinstance(payload, dict) or set(payload) != {'job_id', 'dispatch_generation'}:
        return None
    job_id = payload.get('job_id')
    generation = payload.get('dispatch_generation')
    if not isinstance(job_id, str) or not job_id or len(job_id) > 128:
        return None
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
        return None
    return job_id, generation


async def _retry_or_dead_letter(
    job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    task_retry_count: int,
    failed_attempts: int,
    reason: str,
) -> bool:
    """Record a task failure; return whether this was the terminal delivery."""
    max_attempts = get_listen_finalization_tasks_max_attempts_for_worker()
    # Cloud Tasks resets its retry header when reconciliation issues a new
    # dispatch generation. The job's failed-processing count survives that
    # handoff and is the authoritative budget (as on the pusher path).
    this_attempt = max(task_retry_count, failed_attempts) + 1
    if this_attempt >= max_attempts:
        marked_dead_letter = await run_blocking(
            db_executor,
            final_attempt_failed,
            job_id,
            dispatch_generation,
            lease_epoch,
            this_attempt,
        )
        if not marked_dead_letter:
            return False
        return True

    await run_blocking(
        db_executor,
        jobs_db.mark_finalization_retryable,
        job_id,
        dispatch_generation,
        lease_epoch,
        reason,
    )
    LISTEN_FINALIZATION_RETRIES_TOTAL.inc()
    return False


@router.post('/v1/conversation-finalization-jobs/run', include_in_schema=False)
async def run_listen_finalization_job(
    request: Request,
    task_retry_count: int = Depends(verify_listen_finalization_cloud_tasks_oidc),
):
    try:
        parsed = _parse_task_payload(await request.json())
    except Exception:
        parsed = None
    if parsed is None:
        logger.warning('listen finalization handler dropped invalid opaque task payload')
        return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'invalid_payload'})

    job_id, dispatch_generation = parsed
    lock_key = f'listen-finalization:{job_id}'
    lock_token = await run_blocking(db_executor, try_acquire_job_run_lock, lock_key)
    if not lock_token:
        return JSONResponse(status_code=409, content={'status': 'locked'})

    release_lock = True
    claimed_lease_epoch: int | None = None
    failed_attempts = 0
    job: dict[str, Any] | None = None
    try:
        claim = await run_blocking(
            db_executor,
            jobs_db.claim_finalization_job,
            job_id,
            dispatch_generation,
            count_worker_claim=True,
        )
        claim_status = claim['status']
        if claim_status == 'completed':
            return JSONResponse(status_code=200, content={'status': 'acked', 'job_status': 'completed'})
        if claim_status == 'leased':
            return JSONResponse(status_code=409, content={'status': claim_status})
        if claim_status == 'stale_generation':
            # The reconciler has already enqueued the newer generation. An old
            # named task is no longer actionable and must be acknowledged so
            # Cloud Tasks does not retry this permanently fenced payload.
            logger.info(
                'listen finalization stale generation task acknowledged job=%s dispatch_generation=%s',
                job_id,
                dispatch_generation,
            )
            return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': claim_status})
        if claim_status != 'claimed':
            return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': claim_status})
        claimed_lease_epoch = claim['lease_epoch']
        failed_attempts = int(claim.get('attempt_count') or 0) if _durable_attempt_cap_enabled() else 0
        if claimed_lease_epoch is None:
            logger.error('listen finalization claim returned no lease epoch job=%s', job_id)
            return JSONResponse(status_code=500, content={'status': 'retry'})

        job = await run_blocking(db_executor, jobs_db.get_finalization_job, job_id)
        if not job or not isinstance(job.get('uid'), str) or not isinstance(job.get('conversation_id'), str):
            terminal = await _retry_or_dead_letter(
                job_id, dispatch_generation, claimed_lease_epoch, task_retry_count, failed_attempts, 'invalid_job'
            )
            if terminal:
                logger.error(
                    'listen finalization final attempt failed job_hash=%s error=invalid_job',
                    finalization_diagnostic_id(job_id),
                )
                return JSONResponse(status_code=200, content={'status': 'dead_letter'})
            return JSONResponse(status_code=500, content={'status': 'retry'})

        if await run_blocking(db_executor, should_skip_background_account_mutation, job['uid']):
            # Prequeued finalization must not mutate migrating/new accounts.
            completed = await run_blocking(
                db_executor,
                lifecycle_service.complete_fenced_finalization,
                job_id,
                dispatch_generation,
                claimed_lease_epoch,
            )
            if not completed:
                return JSONResponse(status_code=409, content={'status': 'completion_conflict'})
            record_capture_finalization_terminal('stale', job.get('created_at'))
            record_conversation_finalization_client_terminal('cancelled', job)
            return JSONResponse(status_code=200, content={'status': 'skipped', 'reason': 'account_cutover'})

        # A killed worker cannot record its failure. Its fenced claim still
        # consumed a durable slot, so close an already exhausted generation
        # before paying for another processing attempt.
        if (
            _durable_attempt_cap_enabled()
            and failed_attempts >= get_listen_finalization_tasks_max_attempts_for_worker()
        ):
            if job.get('fanout_status') == 'completed':
                completed = await run_blocking(
                    db_executor, jobs_db.mark_finalization_completed, job_id, dispatch_generation, claimed_lease_epoch
                )
                if not completed:
                    return JSONResponse(status_code=409, content={'status': 'completion_conflict'})
                record_capture_finalization_terminal('success', job.get('created_at'))
                record_conversation_finalization_client_terminal('success', job)
                logger.info(
                    'listen finalization completed committed fanout job_hash=%s', finalization_diagnostic_id(job_id)
                )
                return JSONResponse(status_code=200, content={'status': 'done'})
            terminal = await run_blocking(
                db_executor, final_attempt_failed, job_id, dispatch_generation, claimed_lease_epoch, failed_attempts
            )
            if terminal:
                logger.error(
                    'listen finalization attempt budget exhausted job_hash=%s failed_attempts=%s',
                    finalization_diagnostic_id(job_id),
                    failed_attempts,
                )
                return JSONResponse(status_code=200, content={'status': 'dead_letter'})
            return JSONResponse(status_code=409, content={'status': 'completion_conflict'})

        try:
            disposition = await finalize_persisted_conversation(
                job['uid'],
                job['conversation_id'],
                finalization_job_id=job_id,
                dispatch_generation=dispatch_generation,
                lease_epoch=claimed_lease_epoch,
                trigger=trigger_for_finalization_job(job),
                final_attempt=max(task_retry_count, failed_attempts)
                >= get_listen_finalization_tasks_max_attempts_for_worker() - 1,
            )
        except ConversationFinalizationError:
            terminal = await _retry_or_dead_letter(
                job_id, dispatch_generation, claimed_lease_epoch, task_retry_count, failed_attempts, 'processing_failed'
            )
            if terminal:
                logger.error(
                    'listen finalization final attempt failed job_hash=%s failure=processing_failed',
                    finalization_diagnostic_id(job_id),
                )
                return JSONResponse(status_code=200, content={'status': 'dead_letter'})
            return JSONResponse(status_code=500, content={'status': 'retry'})

        if disposition == ConversationFinalizationDisposition.fenced:
            completed = await run_blocking(
                db_executor,
                lifecycle_service.complete_fenced_finalization,
                job_id,
                dispatch_generation,
                claimed_lease_epoch,
            )
        else:
            completed = await run_blocking(
                db_executor,
                jobs_db.mark_finalization_completed,
                job_id,
                dispatch_generation,
                claimed_lease_epoch,
            )
        if not completed:
            return JSONResponse(status_code=409, content={'status': 'completion_conflict'})
        accepted_at = job.get('created_at') if job else None
        if disposition == ConversationFinalizationDisposition.fenced:
            record_capture_finalization_terminal('stale', accepted_at)
            record_conversation_finalization_client_terminal('cancelled', job)
        else:
            record_capture_finalization_terminal('success', accepted_at)
            record_conversation_finalization_client_terminal('success', job)
            logger.info('listen finalization completed job_hash=%s', finalization_diagnostic_id(job_id))
        return JSONResponse(status_code=200, content={'status': 'done'})
    except asyncio.CancelledError:
        release_lock = False
        logger.warning('listen finalization handler cancelled job=%s; preserving run lock until TTL', job_id)
        raise
    except Exception as error:
        logger.warning(
            'listen finalization worker failed stage=handler exception_type=%s job_hash=%s dispatch_generation=%s',
            type(error).__name__,
            finalization_diagnostic_id(job_id),
            dispatch_generation,
        )
        if claimed_lease_epoch is not None:
            try:
                terminal = await _retry_or_dead_letter(
                    job_id,
                    dispatch_generation,
                    claimed_lease_epoch,
                    task_retry_count,
                    failed_attempts,
                    'worker_failed',
                )
            except Exception:
                logger.error('listen finalization recovery update failed job=%s failure=worker_failed', job_id)
            else:
                if terminal:
                    logger.error(
                        'listen finalization final attempt failed job_hash=%s failure=worker_failed',
                        finalization_diagnostic_id(job_id),
                    )
                    return JSONResponse(status_code=200, content={'status': 'dead_letter'})
                return JSONResponse(status_code=500, content={'status': 'retry'})
        logger.error('listen finalization handler failed job=%s failure=worker_failed', job_id)
        return JSONResponse(status_code=500, content={'status': 'retry'})
    finally:
        if release_lock:
            await run_blocking(db_executor, release_job_run_lock, lock_key, lock_token)
