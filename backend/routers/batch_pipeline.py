"""Private OIDC batch worker RPC. Rollback closes intake, never accepted leases."""

from dataclasses import asdict
import logging
import os
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from config import reliability_experiments
from config.batch_pipeline import projection_pump_enabled, read_only_metrics_enabled
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_record_dead_letter import requeue_record as requeue_record_job
from utils.batch_pipeline.contracts import PoolCapacity, WorkResult
from utils.batch_pipeline.admission import authorize
from utils.batch_pipeline.serving import serving_for_stage
from utils.batch_pipeline.shadow_projection import run as run_shadow_projection
from utils.executors import db_executor, run_blocking, sync_executor
from utils.workers.retry import retry_response
from utils.observability.reasons import RetryReason
from utils.sync.stage import current_stage, require_http_stage

logger = logging.getLogger(__name__)


def verify_worker(request: Request) -> int:
    # Keep worker-only authentication out of legacy sync import paths.
    from utils.cloud_tasks import verify_configured_cloud_tasks_oidc

    audience = os.getenv('BATCH_PIPELINE_WORKER_AUDIENCE', '').strip()
    invoker = os.getenv('BATCH_PIPELINE_WORKER_SERVICE_ACCOUNT', '').strip()
    if request.url.path == '/v2/batch-pipeline/recover-quarantine':
        audience = os.getenv('BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE', '').strip()
        invoker = os.getenv('SYNC_TASKS_INVOKER_SA', '').strip()
    elif request.url.path in {
        '/v2/batch-pipeline/shadow-recover',
        '/v2/batch-pipeline/shadow-project',
        '/v2/batch-pipeline/commit-wake',
    }:
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


@router.post('/pull', include_in_schema=False)
async def pull(body: PullRequest):
    try:
        leases = await run_blocking(db_executor, body.service().pull, body.limit, body.capacity)
    except BatchPrivacyBlocked:
        return {'leases': []}
    return {'leases': [{**asdict(lease), 'item': lease.item.to_dict(include_nulls=True)} for lease in leases]}


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
    started = time.monotonic()
    try:
        outcome = await service.recovery.recover_async(body.segment_id, job['owner_id'])
    finally:
        logger.info('event=batch_recovery_stage stage=recognition duration_seconds=%.3f', time.monotonic() - started)
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
        started = time.monotonic()
        try:
            await service.reconcile_async(
                owner_id=job['owner_id'],
                recovered=body.segment_id,
                owner_only=True,
                run_held_expiry=False,
            )
        finally:
            logger.info(
                'event=batch_recovery_stage stage=post_recovery duration_seconds=%.3f', time.monotonic() - started
            )
    return {'status': outcome}


@router.post('/redrive-dead', include_in_schema=False)
async def redrive_dead(body: RedriveRequest):
    try:
        accepted = await run_blocking(db_executor, body.service().queue().redrive_dead, body.segment_id, time.time())
    except (BatchPrivacyBlocked, ProjectionBlocked):
        accepted = False
    return {'accepted': accepted}


@router.post('/requeue-quarantined', include_in_schema=False)
async def requeue_quarantined(body: RedriveRequest):
    """Same private worker OIDC boundary; usable even with expiry disabled."""
    from database.batch_pipeline_quarantine_recovery import RecoveryStore
    from database.batch_pipeline_projection_protocol import ProjectionBlocked

    try:
        accepted = await run_blocking(
            db_executor, RecoveryStore(body.service().store).requeue_quarantined, body.segment_id, time.time()
        )
    except (BatchPrivacyBlocked, ProjectionBlocked):
        accepted = False
    return {'accepted': accepted}


@router.post('/requeue-record', include_in_schema=False)
async def requeue_record(body: RedriveRequest):
    """Private worker OIDC; rechecks the record reason and commit privacy fence."""
    try:
        accepted = await run_blocking(
            db_executor, requeue_record_job, body.service().store, body.segment_id, time.time()
        )
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


class ShadowProjectionRequest(WorkerRequest):
    segment_id: str = Field(min_length=1, max_length=128, pattern=r'^[^/]+$')
    payload: dict


@router.post('/shadow-project', include_in_schema=False)
async def shadow_project(body: ShadowProjectionRequest):
    return await run_blocking(sync_executor, run_shadow_projection, body.service().store, body.segment_id, body.payload)


class CommitWakeRequest(WorkerRequest):
    owner_ids: list[str] = Field(min_length=1, max_length=32)


@router.post('/commit-wake', include_in_schema=False)
async def commit_wake(body: CommitWakeRequest):
    # Reliability experiment commit_wake: a hint only. An owner it is off for is not accepted and nothing runs.
    from utils.batch_pipeline import commit_wake as wake

    if body.stage != current_stage():
        raise HTTPException(status_code=409, detail='Worker stage mismatch')
    owners = [owner_id for owner_id in dict.fromkeys(body.owner_ids) if 0 < len(owner_id) <= 128]
    for owner_id in owners:
        await reliability_experiments.warm(owner_id)
    return {'accepted': wake.request(owners) if owners else 0}


@router.post('/reconcile', include_in_schema=False)
async def reconcile(body: WorkerRequest):
    await body.service().reconcile_async(recover_quarantine=True, run_held_expiry=False)
    return {'status': 'reconciled'}


@router.get('/metrics', include_in_schema=False)
async def metrics():
    service = serving_for_stage(current_stage())
    if (projection_pump_enabled() or read_only_metrics_enabled()) and service.metrics is not None:
        await run_blocking(db_executor, service.metrics.refresh, service.store, time.time())
    else:
        # Periodic maintenance uses the leader lease; per-unit policy decides follow-ups.
        await service.reconcile_async(periodic=True, run_held_expiry=False)
    return Response(generate_latest(), headers={'Content-Type': CONTENT_TYPE_LATEST})


@router.post('/authorize-compute', include_in_schema=False)
async def authorize_compute(body: HeartbeatRequest, request: Request):
    # Workers advertise their client budget in a header so either side may roll first.
    return await authorize(
        body.service().store,
        [lease.model_dump() for lease in body.leases],
        budget=request.headers.get('x-omi-admission-seconds'),
    )
