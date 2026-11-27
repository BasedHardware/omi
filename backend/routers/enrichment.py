"""Enrichment consumer route ``POST /v2/enrichment/run`` (contracts (a), (d)).

A Cloud Tasks wake for one ``sync_reprocess_outbox`` row. The row is the state: the task carries only
``{"kind", "key", "task_token"}``, the same payload the legacy ``/v2/sync-jobs/run`` binding delivers, so
rows bound to either handler drain (contract (b) invariant 7). Responses follow contract (d) only:
200 for consumed deliveries, 409 ``retry`` for expected retries, 400 for a malformed task, and 500 only for
an unexpected exception.
"""

import asyncio
import logging
import os
import re
import threading
import time

from fastapi import APIRouter, Depends, Request
from prometheus_client import Counter
from config.sync_telemetry import bounded_exception_class
from utils.batch_pipeline.enrichment import run_enrichment
from utils.enrichment.retry_reason import expected_retry_reason
from utils.enrichment import outbox as reprocess
from fastapi.responses import JSONResponse

from config import enrichment as enrichment_config
from database import outbox_firestore
from database.firestore_transaction_retry import transaction_retry_deadline_scope
from database.outbox_firestore import provider_stt_outbox
from utils.enrichment import fresh_demotion
from utils.executors import db_executor, postprocess_executor, run_blocking
from utils.observability.reasons import RetryReason
from utils.workers.consumer import http_response, run_push
from utils.workers.retry import firestore_retry_reason, retry_response

router = APIRouter()
logger = logging.getLogger(__name__)

# Static retry classes; never IDs. 'unexpected' answers 500, the others 409.
ENRICHMENT_RETRIES = Counter(
    'batch_enrichment_sync_reprocess_retries_total',
    'Enrichment task retries by expected or unexpected class',
    ['retry_class'],
)

_KINDS = {'enrichment', 'sync_reprocess', 'batch_final_pass'}
# TimeoutMiddleware cuts an attempt at HTTP_POST_TIMEOUT (600s), so the request log records a bare 504
# while this thread may still be working. Retries and slow deliveries log their real end and timing.
SLOW_DELIVERY_SECONDS = 120.0
# TimeoutMiddleware cuts this path at HTTP_POST_TIMEOUT (600s) with a bare 504 while the worker thread keeps
# its heartbeated lease, so a slow delivery held a queue slot for the full 600s. Answer a 409 retry at the
# budget instead; the worker still settles its own lease, and the queue retry or sweep claims after it.
DELIVERY_BUDGET_SECONDS = 300.0


def _delivery_budget() -> float:
    try:
        return float(os.getenv('ENRICHMENT_DELIVERY_BUDGET_SECONDS', DELIVERY_BUDGET_SECONDS))
    except ValueError:
        return DELIVERY_BUDGET_SECONDS


def _drain(work: asyncio.Future) -> None:
    # The abandoned delivery's own settlement already ran; only retrieve its outcome so it is not lost silently.
    if not work.cancelled() and work.exception() is not None:
        logger.warning(
            'event=enrichment_delivery outcome=error phase=after_budget exception_type=%s',
            type(work.exception()).__name__,
        )


def _audience() -> str:
    handler = os.getenv('ENRICHMENT_TASKS_HANDLER_URL', '').strip()
    return os.getenv('ENRICHMENT_TASKS_OIDC_AUDIENCE', '').strip() or handler


def verify_enrichment_task(request: Request) -> int:
    """OIDC for the enrichment queue's invoker; the audience is the enrichment handler (TaskEdge ``enrichment``)."""
    from utils.cloud_tasks import verify_configured_cloud_tasks_oidc

    invoker = os.getenv('ENRICHMENT_TASKS_INVOKER_SA', '').strip() or os.getenv('SYNC_TASKS_INVOKER_SA', '').strip()
    return verify_configured_cloud_tasks_oidc(request, audience=_audience(), invoker_sa=invoker)


def _from_fresh_queue(request: Request) -> bool:
    """Cloud Tasks names the delivering queue; only fresh-queue deliveries pay the demotion read."""
    fresh = enrichment_config.fresh_queue()
    return bool(fresh) and request.headers.get('X-CloudTasks-QueueName', '').strip() == fresh


def _task(payload: object) -> tuple[str, str] | None:
    if not isinstance(payload, dict) or set(payload) != {'kind', 'key', 'task_token'}:
        return None
    key, token = payload.get('key'), payload.get('task_token')
    if payload.get('kind') not in _KINDS or not isinstance(key, str) or not isinstance(token, str):
        return None
    if not re.fullmatch('[0-9a-f]{64}', key) or not re.fullmatch('[0-9a-f]{32}', token):
        return None
    return key, token


def consume(key: str, token: str, accepted: float | None = None, abandoned: threading.Event | None = None):
    """One push delivery through the enrichment consumer; shared with the legacy sync-jobs handler.

    ``accepted`` is the handler's ``time.monotonic()`` before the executor hop. Only a retry or a slow
    delivery logs its executor wait and run time (no ids). ``abandoned`` is set once the route answered its
    budget 409. That retry met this delivery's lease and was consumed as BUSY, so a RETRY here re-arms the
    row under a fresh wake instead of stranding it.
    """
    from database.outbox import Outcome
    from utils.enrichment.consumer import EnrichmentConsumer

    started = time.monotonic()
    accepted = started if accepted is None else accepted
    outcome, reason = 'error', 'unexpected'
    try:
        outbox = outbox_firestore.ENRICHMENT_OUTBOX
        result = run_push(EnrichmentConsumer(outbox), outbox, key, token, now=time.time())
        outcome, reason = result.outcome.value, result.reason.value
        if abandoned is not None and abandoned.is_set() and result.outcome is Outcome.RETRY:
            outbox.rearm_released(key, token, now=time.time())
        return result
    finally:
        finished = time.monotonic()
        if outcome == Outcome.RETRY.value or finished - accepted >= SLOW_DELIVERY_SECONDS:
            logger.info(
                'event=enrichment_delivery outcome=%s reason=%s wait_s=%.1f run_s=%.1f',
                outcome,
                reason,
                started - accepted,
                finished - started,
            )


@router.post('/v2/enrichment/run', include_in_schema=False)
async def run_enrichment_task(request: Request, _retry_count: int = Depends(verify_enrichment_task)):
    try:
        payload = await request.json()
    except ValueError:
        payload = None
    task = _task(payload)
    if payload is None or task is None:
        return JSONResponse(status_code=400, content={'status': 'invalid_enrichment_task'})
    budget = _delivery_budget()
    try:
        if budget > 0:
            with transaction_retry_deadline_scope(time.monotonic() + budget):
                return await _deliver_task(request, payload['kind'], task, budget)
        return await _deliver_task(request, payload['kind'], task, budget)
    except Exception as error:
        reason = firestore_retry_reason(error)
        if reason is None:
            raise
        return retry_response(reason)


async def _deliver_task(request: Request, kind: str, task: tuple[str, str], budget: float) -> JSONResponse:
    if kind == 'batch_final_pass':
        from utils.conversations.final_pass_retry import consume as consume_speaker_pass

        return JSONResponse(
            status_code=200, content=await run_blocking(postprocess_executor, consume_speaker_pass, *task)
        )
    from utils.enrichment import outbox

    if not outbox.owns_runtime():
        return JSONResponse(status_code=200, content={'status': 'foreign_runtime'})
    from utils.enrichment.age_gate import max_age_seconds, park_if_expired

    # Historical work must not wait behind the long-running callback pool.
    if max_age_seconds() > 0:
        try:
            if await run_blocking(db_executor, park_if_expired, *task):
                return JSONResponse(status_code=200, content={'status': 'deferred', 'reason': 'age_gate_72h'})
        except Exception as error:
            from utils.enrichment.consumer import transient_dependency

            if not transient_dependency(error):
                raise
            return retry_response(RetryReason.DEPENDENCY_WARMING)
    if _from_fresh_queue(request):
        # The reserved fresh lane is for fresh work: move an aged first summary to the primary
        # queue instead of running it on a fresh slot (prod 2026-11-16 fresh backlog).
        try:
            if await run_blocking(db_executor, fresh_demotion.demote_if_stale, *task):
                return JSONResponse(status_code=200, content={'status': 'deferred', 'reason': 'fresh_demoted'})
        except Exception as error:
            from utils.enrichment.consumer import transient_dependency

            if not transient_dependency(error):
                raise
            return retry_response(RetryReason.DEPENDENCY_WARMING)
    if budget <= 0:  # Kill switch: 0 restores the middleware-only cut.
        return http_response(await run_blocking(postprocess_executor, consume, *task, time.monotonic()))
    abandoned = threading.Event()
    work = asyncio.ensure_future(run_blocking(postprocess_executor, consume, *task, time.monotonic(), abandoned))
    try:
        result = await asyncio.wait_for(asyncio.shield(work), timeout=budget)
    except asyncio.TimeoutError:
        abandoned.set()
        work.add_done_callback(_drain)
        logger.warning('event=enrichment_delivery outcome=retry reason=delivery_budget budget_s=%.0f', budget)
        return retry_response(RetryReason.DEPENDENCY_WARMING)
    return http_response(result)


def maintain(now: float) -> dict[str, int]:
    """One maintenance pass: re-wake lost obligations, then admit overdue first-summary debt (C4).

    Both halves are safe beside the legacy sequencer sweep: the outbox sweep is per-row CAS and the
    summary-debt tick holds its own cursor lease, so a second owner never double-admits.
    """
    from services import summary_debt_repair

    from utils.conversations import final_pass_retry

    # Same scheduled maintenance, separate rows and speaker-only wakes.
    try:
        final_pass_retry.sweep(now=now)
    except Exception as error:
        logger.error('event=batch_final_pass_retry outcome=sweep_failed exception_type=%s', type(error).__name__)
    from database.owner_identity_availability import refresh

    try:
        refresh(now)
    except Exception as error:
        logger.warning(
            'event=owner_identity_availability outcome=refresh_unavailable exception_type=%s', type(error).__name__
        )
    swept = outbox_firestore.ENRICHMENT_OUTBOX.sweep(now=now)
    counts = {
        'rewoken': swept.rewoken,
        'discarded': swept.discarded,
        'sweep_errors': swept.errors,
        'provider_stt_rewoken': 0,
        'provider_stt_discarded': 0,
        'provider_stt_sweep_errors': 0,
        'provider_stt_running_rewoken': 0,
        'provider_stt_running_errors': 0,
        'summary_debt_scanned': 0,
        'summary_debt_admitted': 0,
        'summary_debt_near_expiry_admitted': 0,
        'summary_debt_errors': 0,
        'summary_debt_expired_seen': 0,
    }
    # C8 provider-STT units rely on this sweep when a post-commit wake is lost (contract (b),
    # invariant 4); it shares the enrichment maintenance schedule (M3 review). Its own failure
    # never blocks the enrichment half.
    try:
        provider = provider_stt_outbox().sweep(now=now)
        counts.update(
            provider_stt_rewoken=provider.rewoken,
            provider_stt_discarded=provider.discarded,
            provider_stt_sweep_errors=provider.errors,
        )
    except Exception as error:
        logger.error('event=provider_stt_sweep outcome=error exception_type=%s', type(error).__name__)
        counts['provider_stt_sweep_errors'] = 1
    try:
        rewoken, errors = provider_stt_outbox().sweep_running(now=now)
        counts.update(provider_stt_running_rewoken=rewoken, provider_stt_running_errors=errors)
    except Exception as error:
        logger.error('event=provider_stt_running_sweep outcome=error exception_type=%s', type(error).__name__)
        counts['provider_stt_running_errors'] = 1
    try:
        summary = summary_debt_repair.tick(now=now)
    except Exception as error:
        logger.error('event=summary_debt_repair outcome=error exception_type=%s', type(error).__name__)
        summary = {'scanned': 0, 'admitted': 0, 'near_expiry_admitted': 0, 'errors': 1, 'expired_seen': 0}
    counts.update(
        summary_debt_scanned=summary['scanned'],
        summary_debt_admitted=summary['admitted'],
        summary_debt_near_expiry_admitted=summary.get('near_expiry_admitted', 0),
        summary_debt_errors=summary['errors'],
        summary_debt_expired_seen=summary['expired_seen'],
    )
    return counts


@router.post('/v2/enrichment/sweep', include_in_schema=False)
async def sweep_enrichment(_retry_count: int = Depends(verify_enrichment_task)):
    """Cloud Scheduler ``enrichment-maintenance`` (*/2): 200 with counts; partial errors are counted, not 5xx."""
    from utils.enrichment import outbox

    if not outbox.owns_runtime():
        return JSONResponse(status_code=200, content={'status': 'foreign_runtime'})
    counts = await run_blocking(postprocess_executor, maintain, time.time())
    return JSONResponse(status_code=200, content={'status': 'swept', 'counts': counts})


async def enrichment_response(payload: dict):
    document_id, token = payload.get('key'), payload.get('task_token')
    if set(payload) != {'kind', 'key', 'task_token'} or not all(
        isinstance(value, str) and value for value in (document_id, token)
    ):
        return JSONResponse(status_code=400, content={'status': 'invalid_enrichment_task'})
    assert isinstance(document_id, str) and isinstance(token, str)
    if not reprocess.owns_runtime():
        return JSONResponse(status_code=200, content={'status': 'foreign_runtime'})
    try:
        if enrichment_config.route() == 'enrichment_queue':
            # C3: one state machine. Rows still bound to /v2/sync-jobs/run drain through the same
            # consumer as /v2/enrichment/run; the route lever flips both together.
            return http_response(
                await run_blocking(postprocess_executor, consume, document_id, token, time.monotonic())
            )
        # Summaries must not queue behind long transcription jobs. Reuse the
        # conversation-processing bulkhead for every first-summary obligation.
        executor = postprocess_executor
        status = await run_blocking(executor, run_enrichment, document_id, token)
        if status == 'busy':
            logger.info('event=batch_enrichment_sync_reprocess outcome=busy')
            # The leased outbox and task watchdog retain custody after this ACK.
            return JSONResponse(status_code=200, content={'status': status})
        return JSONResponse(status_code=200, content={'status': status})
    except Exception as error:
        reason = firestore_retry_reason(error) or expected_retry_reason(error)
        if reason is None and isinstance(error, (ValueError, TypeError)):
            return JSONResponse(status_code=400, content={'status': 'invalid_enrichment_task'})
        if reason is None:
            ENRICHMENT_RETRIES.labels('unexpected').inc()
            logger.error(
                'event=batch_enrichment_sync_reprocess outcome=retry retry_class=unexpected site=run_enrichment exception_type=%s',
                bounded_exception_class(error),
            )
            return JSONResponse(status_code=500, content={'status': 'retry'})
        ENRICHMENT_RETRIES.labels(reason).inc()
        logger.warning(
            'event=batch_enrichment_sync_reprocess outcome=retry retry_class=%s site=run_enrichment exception_type=%s',
            reason,
            bounded_exception_class(error),
        )
        # 409 keeps Cloud Tasks retrying (any non-2xx) without the 429/503
        # queue throttling that caused the 2026-10-18 backlog, and keeps these
        # by-design waits out of 5xx error gates.
        return JSONResponse(status_code=409, content={'status': 'retry', 'reason': reason})
