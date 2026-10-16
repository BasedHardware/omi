"""Private OIDC batch worker RPC. Rollback closes intake, never accepted leases."""

from dataclasses import asdict
import os
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response, JSONResponse

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from utils.batch_pipeline.contracts import PoolCapacity, WorkResult
from utils.batch_pipeline.admission import authorize
from utils.batch_pipeline.enrichment import run_enrichment
from utils.batch_pipeline.serving import serving_for_stage
from utils.executors import db_executor, run_blocking, sync_executor
from utils.sync.stage import current_stage, require_http_stage


def verify_worker(request: Request) -> int:
    # Keep worker-only authentication out of legacy sync import paths.
    from utils.cloud_tasks import verify_configured_cloud_tasks_oidc

    return verify_configured_cloud_tasks_oidc(
        request,
        audience=os.getenv('BATCH_PIPELINE_WORKER_AUDIENCE', '').strip(),
        invoker_sa=os.getenv('BATCH_PIPELINE_WORKER_SERVICE_ACCOUNT', '').strip(),
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


@router.post('/redrive-dead', include_in_schema=False)
async def redrive_dead(body: RedriveRequest):
    try:
        accepted = await run_blocking(db_executor, body.service().queue().redrive_dead, body.segment_id, time.time())
    except BatchPrivacyBlocked:
        accepted = False
    return {'accepted': accepted}


@router.post('/gpu-idle', include_in_schema=False)
async def gpu_idle(body: IdleRequest):
    accepted = await run_blocking(db_executor, body.service().queue().acknowledge_gpu_idle, body.gpu_id, body.token)
    return {'accepted': accepted}


@router.post('/reconcile', include_in_schema=False)
async def reconcile(body: WorkerRequest):
    await run_blocking(sync_executor, body.service().reconcile, recover_quarantine=True)
    return {'status': 'reconciled'}


@router.get('/metrics', include_in_schema=False)
async def metrics():
    service = serving_for_stage(current_stage())
    await run_blocking(sync_executor, service.reconcile)
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
        status = await run_blocking(sync_executor, run_enrichment, document_id, token)
        return JSONResponse(status_code=503 if status == 'busy' else 200, content={'status': status})
    except (ValueError, TypeError):
        return JSONResponse(status_code=400, content={'status': 'invalid_enrichment_task'})
    except Exception:
        return JSONResponse(status_code=500, content={'status': 'retry'})
