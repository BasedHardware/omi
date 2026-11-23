"""Authenticated internal builder/sweep routes; no public or client control plane."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from omi_logging import bind_request_log_trace
from utils.cloud_tasks import verify_cloud_tasks_oidc
from utils.conversations.v3 import backfill, service
from config.conversations_v3 import backfill_enabled

router = APIRouter()


class ReconcileRequest(BaseModel):
    uid: str = Field(min_length=1, max_length=128, pattern=r'^[^/]+$')


@router.post('/v1/conversations-v3/reconcile', include_in_schema=False)
async def reconcile(body: ReconcileRequest, request: Request, _retry: int = Depends(verify_cloud_tasks_oidc)):
    with bind_request_log_trace(dict(request.headers.raw)):
        return {'outcome': await service.reconcile(body.uid)}


@router.post('/v1/conversations-v3/sweep', include_in_schema=False)
async def sweep(_retry: int = Depends(verify_cloud_tasks_oidc)):
    enqueued = await service.sweep()
    return {'enqueued': enqueued, 'backfill_started': await backfill.start_planned()}


class BackfillRequest(BaseModel):
    uid: str = Field(min_length=1, max_length=128, pattern=r'^[^/]+$')
    run_id: str = Field(min_length=1, max_length=64, pattern=r'^[A-Za-z0-9-]+$')
    partition: int = Field(ge=0, le=10000)
    phase: Literal['derive', 'drain'] = 'derive'


@router.post('/v1/conversations-v3/backfill', include_in_schema=False)
async def run_backfill(body: BackfillRequest, _retry: int = Depends(verify_cloud_tasks_oidc)):
    """One step of an operator-planned per-owner run; nothing reaches this without a ledger entry."""
    if not backfill_enabled():
        raise HTTPException(404, 'Backfill is disabled')
    try:
        return await backfill.run_step(body.uid, body.run_id, body.partition, body.phase)
    except backfill.BackfillRetry:
        raise HTTPException(503, 'Owner busy; retry')


@router.post('/v1/conversations-v3/legacy-users', include_in_schema=False)
async def legacy_users(_retry: int = Depends(verify_cloud_tasks_oidc)):
    return await service.measure_legacy_users()
