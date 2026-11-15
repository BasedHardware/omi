"""Private OIDC backfill worker RPC; intake is dark until explicit cohort rollout."""

import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from utils.executors import db_executor, run_blocking
from utils.sync import stage, worker_control


def verify_worker(request: Request) -> int:
    from utils.cloud_tasks import verify_configured_cloud_tasks_oidc

    return verify_configured_cloud_tasks_oidc(
        request,
        audience=os.getenv('SYNC_BACKFILL_WORKER_AUDIENCE', '').strip(),
        invoker_sa=os.getenv('SYNC_BACKFILL_WORKER_SERVICE_ACCOUNT', '').strip(),
        log_failure=False,
    )


router = APIRouter(prefix='/v2/sync-jobs', dependencies=[Depends(verify_worker), Depends(stage.require_http_stage)])


class WorkerRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    stage: Literal['prod']

    def check_stage(self) -> None:
        if self.stage != stage.current_stage():
            raise HTTPException(status_code=409, detail='Worker stage mismatch')


class LeaseRequest(WorkerRequest):
    uid: str = Field(min_length=1, max_length=256, pattern=r'^[^/]+$')
    job_id: str = Field(min_length=1, max_length=128, pattern=r'^[^/]+$')
    epoch: int = Field(gt=0, strict=True)
    token: str = Field(min_length=32, max_length=128)

    def identity(self) -> tuple[str, str, int, str]:
        self.check_stage()
        return self.uid, self.job_id, self.epoch, self.token


@router.post('/claim', include_in_schema=False)
async def claim(body: WorkerRequest):
    body.check_stage()
    return {'lease': await run_blocking(db_executor, worker_control.claim)}


@router.post('/heartbeat', include_in_schema=False)
async def heartbeat(body: LeaseRequest):
    return {'accepted': await run_blocking(db_executor, worker_control.heartbeat, *body.identity())}


@router.post('/complete', include_in_schema=False)
async def complete(body: LeaseRequest):
    return {'accepted': await run_blocking(db_executor, worker_control.complete, *body.identity())}


@router.post('/fail', include_in_schema=False)
async def fail(body: LeaseRequest):
    return {'accepted': await run_blocking(db_executor, worker_control.fail, *body.identity())}
