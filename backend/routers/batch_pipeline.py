"""Private OIDC batch worker RPC. Rollback closes intake, never accepted leases."""

from dataclasses import asdict
import logging
import os
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
from starlette.responses import Response, JSONResponse

from config.batch_pipeline import read_only_metrics_enabled
from config.summary_guarantee import enabled as summary_deadline_enabled
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from utils.batch_pipeline.contracts import PoolCapacity, WorkResult
from utils.batch_pipeline.admission import authorize
from utils.batch_pipeline.enrichment import run_enrichment
from utils.batch_pipeline.serving import serving_for_stage
from utils.executors import db_executor, postprocess_executor, run_blocking, sync_executor
from utils.observability.reasons import RetryReason
from utils.workers.retry import retry_response
from utils.sync.stage import current_stage, require_http_stage

logger = logging.getLogger(__name__)

# Static retry classes; never IDs. 'unexpected' answers 500, the others 409.
ENRICHMENT_RETRIES = Counter(
    'batch_enrichment_sync_reprocess_retries_total',
    'Enrichment task retries by expected or unexpected class',
    ['retry_class'],
)
# Deliberate retain-and-retry signals, matched by defining module and name so
# this router does not import the sync pipeline at startup.
EXPECTED_RETRIES = {
    # Keyed by the defining module: utils.sync.reprocess is only an alias of utils.enrichment.outbox (#22431).
    ('utils.enrichment.outbox', 'FirstSummaryCallbackPending'): 'callback_pending',
    ('utils.enrichment.callback', 'SyncConversationPersistenceFenced'): 'persistence_fenced',
    ('utils.sync.pipeline', 'SyncConversationPersistenceFenced'): 'persistence_fenced',
}


def expected_retry_reason(error: BaseException) -> str | None:
    for cls in type(error).__mro__:
        reason = EXPECTED_RETRIES.get((cls.__module__, cls.__qualname__))
        if reason is not None:
            return reason
    if dependency_failure(error):
        return RetryReason.DEPENDENCY_WARMING.value
    return None


def dependency_failure(error: BaseException) -> bool:
    """Conversation processing's HTTP contract for a failed dependency (LLM/provider step or app), not a bug.

    ``process_conversation`` raises 429 (BYOK rate limit or quota), 500 (generic processing failure) or
    502 (selected app failed). Inside a task delivery these are transient dependency outages: answering
    500 would make Cloud Tasks system-throttle the queue (contract (d)). Other 4xx stay unexpected.
    """
    return isinstance(error, HTTPException) and (error.status_code == 429 or error.status_code >= 500)


def verify_worker(request: Request) -> int:
    # Keep worker-only authentication out of legacy sync import paths.
    from utils.cloud_tasks import verify_configured_cloud_tasks_oidc

    audience = os.getenv('BATCH_PIPELINE_WORKER_AUDIENCE', '').strip()
    invoker = os.getenv('BATCH_PIPELINE_WORKER_SERVICE_ACCOUNT', '').strip()
    if request.url.path == '/v2/batch-pipeline/recover-quarantine':
        audience = os.getenv('BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE', '').strip()
        invoker = os.getenv('SYNC_TASKS_INVOKER_SA', '').strip()
    elif request.url.path == '/v2/batch-pipeline/shadow-recover':
        # Same CPU role/policy as paid record recovery, with the GPU worker's
        # existing service principal rather than the Cloud Tasks invoker.
        audience = os.getenv('BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE', '').strip()
    return verify_configured_cloud_tasks_oidc(
        request,
        audience=audience,
        invoker_sa=invoker,
        log_failure=False,
    )


router = APIRouter(prefix='/v2/batch-pipeline', dependencies=[Depends(verify_worker), Depends(require_http_stage)])


class WorkerRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    stage: Literal['prod', 'dev']

    def service(self):
        if self.stage != current_stage():
            raise HTTPException(status_code=409, detail='Worker stage mismatch')
        return serving_for_stage(self.stage)


class PullRequest(WorkerRequest):
    limit: int = Field(default=8, ge=1, le=32, strict=True)
    pool: Literal['batch', 'live'] = 'batch'
    capacity: PoolCapacity


class LeaseToken(BaseModel):
    model_config = ConfigDict(extra='forbid')
    segment_id: str = Field(min_length=1, max_length=128, pattern=r'^[^/]+$')
    token: str = Field(min_length=1, max_length=128)


class HeartbeatRequest(WorkerRequest):
    leases: list[LeaseToken] = Field(min_length=1, max_length=32)


class CompleteRequest(WorkerRequest):
    result: WorkResult
    token: str = Field(min_length=1, max_length=128)


class FailRequest(WorkerRequest):
    segment_id: str = Field(min_length=1, max_length=128, pattern=r'^[^/]+$')
    token: str = Field(min_length=1, max_length=128)


class RedriveRequest(WorkerRequest):
    segment_id: str = Field(min_length=1, max_length=128, pattern=r'^[^/]+$')


class IdleRequest(WorkerRequest):
    gpu_id: str = Field(min_length=1, max_length=128)
    token: str = Field(min_length=1, max_length=128)


@router.post('/pull', include_in_schema=False)
async def pull(body: PullRequest):
    try:
        leases = await run_blocking(db_executor, body.service().pull, body.limit, body.capacity, pool=body.pool)
    except BatchPrivacyBlocked:
        return {'leases': []}
    return {'leases': [asdict(lease) for lease in leases]}


@router.post('/heartbeat', include_in_schema=False)
async def heartbeat(body: HeartbeatRequest):
    queue = body.service().queue()
    accepted = []
    for lease in body.leases:
        try:
            valid = await run_blocking(db_executor, queue.heartbeat, lease.segment_id, lease.token, time.time())
        except BatchPrivacyBlocked:
            valid = False
        if valid:
            accepted.append(lease.segment_id)
    return {'accepted': accepted}


@router.post('/complete', include_in_schema=False)
async def complete(body: CompleteRequest):
    try:
        accepted = await run_blocking(db_executor, body.service().complete, body.result, body.token)
    except BatchPrivacyBlocked:
        accepted = False
    return {'accepted': accepted}


@router.post('/fail', include_in_schema=False)
async def fail(body: FailRequest):
    try:
        accepted = await run_blocking(
            db_executor, body.service().queue().fail, body.segment_id, body.token, time.time()
        )
    except BatchPrivacyBlocked:
        accepted = False
    return {'accepted': accepted}


@router.post('/recover-quarantine', include_in_schema=False)
async def recover_quarantine(body: RedriveRequest, request: Request):
    """Keep paid STT inside an active request across ordinary revision draining.

    Retried/duplicate tasks can reconcile the original intent; start() never
    authorizes a second provider invocation. The payload carries no owner ID.
    """
    service = body.service()
    if not service.recovery:
        # Contract (d): a switched-off target answers 409, never 503 (fast 5xx throttles the queue).
        return retry_response(RetryReason.KILL_SWITCH_OFF)
    job = await run_blocking(db_executor, service.store.run, lambda tx: tx.get('jobs', body.segment_id))
    if not job:
        return {'status': 'held'}
    outcome = await service.recovery.recover_async(body.segment_id, job['owner_id'])
    if outcome == 'held':
        try:
            await run_blocking(
                db_executor,
                service.recovery.delivered,
                body.segment_id,
                outcome,
                request.headers.get('X-CloudTasks-TaskName'),
            )
        except Exception:
            pass  # The lease still expires; the sweep repairs the wake then.
    if outcome == 'disabled':
        return retry_response(RetryReason.KILL_SWITCH_OFF)
    if outcome in {'recovered', 'reconciled'}:
        await service.reconcile_async(owner_id=job['owner_id'], recovered=body.segment_id)
    return {'status': outcome}


@router.post('/redrive-dead', include_in_schema=False)
async def redrive_dead(body: RedriveRequest):
    try:
        accepted = await run_blocking(db_executor, body.service().queue().redrive_dead, body.segment_id, time.time())
    except BatchPrivacyBlocked:
        accepted = False
    return {'accepted': accepted}


@router.post('/shadow-recover', include_in_schema=False)
async def shadow_recover(body: RedriveRequest):
    from database.batch_pipeline_shadow import ShadowStore
    from utils.batch_pipeline.artifact_policy import artifacts_for
    from utils.batch_pipeline.shadow_recovery import recover_async

    store = body.service().store
    repository = await run_blocking(db_executor, ShadowStore, store)
    artifacts = await run_blocking(sync_executor, artifacts_for, store)
    outcome = await recover_async(repository, artifacts, body.segment_id)
    return {'status': outcome}


@router.post('/gpu-idle', include_in_schema=False)
async def gpu_idle(body: IdleRequest):
    accepted = await run_blocking(db_executor, body.service().queue().acknowledge_gpu_idle, body.gpu_id, body.token)
    return {'accepted': accepted}


@router.post('/reconcile', include_in_schema=False)
async def reconcile(body: WorkerRequest):
    await body.service().reconcile_async(recover_quarantine=True)
    return {'status': 'reconciled'}


@router.get('/metrics', include_in_schema=False)
async def metrics():
    service = serving_for_stage(current_stage())
    if read_only_metrics_enabled() and service.metrics is not None:
        await run_blocking(db_executor, service.metrics.refresh, service.store, time.time())
    else:
        # Periodic maintenance uses the leader lease; per-unit policy decides follow-ups.
        await service.reconcile_async(periodic=True)
    return Response(generate_latest(), headers={'Content-Type': CONTENT_TYPE_LATEST})


@router.post('/authorize-compute', include_in_schema=False)
async def authorize_compute(body: HeartbeatRequest):
    return await run_blocking(
        db_executor, authorize, body.service().store, [lease.model_dump() for lease in body.leases]
    )


async def enrichment_response(payload: dict):
    document_id, token = payload.get('key'), payload.get('task_token')
    if set(payload) != {'kind', 'key', 'task_token'} or not all(
        isinstance(value, str) and value for value in (document_id, token)
    ):
        return JSONResponse(status_code=400, content={'status': 'invalid_enrichment_task'})
    assert isinstance(document_id, str) and isinstance(token, str)
    from utils.sync import reprocess

    if not reprocess.owns_runtime():
        return JSONResponse(status_code=200, content={'status': 'foreign_runtime'})
    try:
        from config.enrichment import route

        if route() == 'enrichment_queue':
            # C3: one state machine. Rows still bound to /v2/sync-jobs/run drain through the same
            # consumer as /v2/enrichment/run; the route lever flips both together.
            from routers.enrichment import consume
            from utils.workers.consumer import http_response

            return http_response(await run_blocking(postprocess_executor, consume, document_id, token))
        # Summaries must not queue behind long transcription jobs. Reuse the
        # conversation-processing bulkhead; the master flag restores the old pool.
        executor = postprocess_executor if summary_deadline_enabled() else sync_executor
        status = await run_blocking(executor, run_enrichment, document_id, token)
        if status == 'busy':
            logger.info('event=batch_enrichment_sync_reprocess outcome=busy')
            # The leased outbox and task watchdog retain custody after this ACK.
            return JSONResponse(status_code=200, content={'status': status})
        return JSONResponse(status_code=200, content={'status': status})
    except (ValueError, TypeError):
        return JSONResponse(status_code=400, content={'status': 'invalid_enrichment_task'})
    except Exception as error:
        from config.sync_telemetry import bounded_exception_class

        reason = expected_retry_reason(error)
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
