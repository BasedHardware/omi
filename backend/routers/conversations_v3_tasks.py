"""Authenticated internal builder/sweep routes; no public or client control plane."""

import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from utils.cloud_tasks import verify_cloud_tasks_oidc
from utils.conversations.v3 import (
    Conflict,
    ProcessingPersistenceFenced,
    backfill,
    bind_request_log_trace,
    metrics,
    service,
)
from utils.observability.reasons import RetryReason
from utils.workers.retry import exhausted_transaction_retry_class, retry_response
from utils.llm.gateway_error_contract import retryable_provider_failure_http_exception
from config.conversations_v3 import backfill_enabled

router = APIRouter()


class ReconcileRequest(BaseModel):
    uid: str = Field(min_length=1, max_length=128, pattern=r'^[^/]+$')


@router.post('/v1/conversations-v3/reconcile', include_in_schema=False)
async def reconcile(body: ReconcileRequest, request: Request, _retry: int = Depends(verify_cloud_tasks_oidc)):
    try:
        with bind_request_log_trace(dict(request.headers.raw)):
            return {'outcome': await service.reconcile(body.uid)}
    except Exception as error:
        # The composition boundary may already have answered a provider fault
        # with the typed retryable contract (and recorded its metric). Re-raise
        # that answer unchanged instead of remapping its chained cause.
        if isinstance(error, HTTPException):
            raise
        if os.getenv('CONVERSATIONS_V3_RECONCILE_RETRY_RESPONSE', 'on').strip().lower() != 'off':
            retry_class = exhausted_transaction_retry_class(error)
            reason = RetryReason.DEPENDENCY_WARMING
            if isinstance(error, ProcessingPersistenceFenced):
                retry_class = 'v3_processing_not_completed'
                reason = RetryReason.PERSISTENCE_FENCED
            elif isinstance(error, Conflict) and str(error) == 'processing_source_changed':
                retry_class = 'processing_source_changed'
                reason = RetryReason.PERSISTENCE_FENCED
            if retry_class is not None:
                metrics.RACES.labels(retry_class).inc()
                return retry_response(reason)
        # A gateway-first call (the v3 outline) can raise a provider 5xx. Answer
        # the existing retryable contract so Cloud Tasks retries the task instead
        # of the failure surfacing as an unhandled 500; anything else keeps its
        # loud 500.
        retryable = retryable_provider_failure_http_exception(error, route='conversations_v3_reconcile')
        if retryable is None:
            raise
        raise retryable from error


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
    except Exception as error:
        # The derive pass runs the same gateway-first outline call; a provider
        # 5xx answers the retryable contract instead of an unhandled 500. An
        # already-typed answer from the composition boundary is re-raised as is.
        if isinstance(error, HTTPException):
            raise
        retryable = retryable_provider_failure_http_exception(error, route='conversations_v3_backfill')
        if retryable is None:
            raise
        raise retryable from error


@router.post('/v1/conversations-v3/legacy-users', include_in_schema=False)
async def legacy_users(_retry: int = Depends(verify_cloud_tasks_oidc)):
    return await service.measure_legacy_users()
