"""Authenticated internal builder/sweep routes; no public or client control plane."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from utils.cloud_tasks import verify_cloud_tasks_oidc
from utils.conversations.v3 import service
from config.conversations_v3 import backfill_enabled

router = APIRouter()


class ReconcileRequest(BaseModel):
    uid: str = Field(min_length=1, max_length=128, pattern=r'^[^/]+$')


@router.post('/v1/conversations-v3/reconcile', include_in_schema=False)
async def reconcile(body: ReconcileRequest, _retry: int = Depends(verify_cloud_tasks_oidc)):
    return {'outcome': await service.reconcile(body.uid)}


@router.post('/v1/conversations-v3/sweep', include_in_schema=False)
async def sweep(_retry: int = Depends(verify_cloud_tasks_oidc)):
    return {'enqueued': await service.sweep()}


@router.post('/v1/conversations-v3/backfill', include_in_schema=False)
async def backfill(body: ReconcileRequest, _retry: int = Depends(verify_cloud_tasks_oidc)):
    if not backfill_enabled():
        raise HTTPException(404, 'Backfill is disabled')
    return {'outcome': await service.backfill(body.uid)}


@router.post('/v1/conversations-v3/legacy-users', include_in_schema=False)
async def legacy_users(_retry: int = Depends(verify_cloud_tasks_oidc)):
    return await service.measure_legacy_users()
