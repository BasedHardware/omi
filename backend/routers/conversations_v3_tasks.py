"""Authenticated internal builder/sweep routes; no public or client control plane."""

import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from database.conversations_v3_fence import ProcessingPersistenceFenced
from utils.cloud_tasks import verify_cloud_tasks_oidc
from utils.conversations.v3 import (
    Conflict,
    backfill,
    bind_request_log_trace,
    metrics,
    service,
)
from utils.observability.reasons import RetryReason
from utils.workers.retry import exhausted_transaction_retry_class, retry_response
from utils.llm.gateway_error_contract import (
    RETRYABLE_CONVERSATION_PROCESSING_ERROR_CODE,
    retryable_provider_failure_http_exception,
)
from config.conversations_v3 import backfill_enabled

router = APIRouter()


def _is_retryable_provider_http_answer(error: HTTPException) -> bool:
    return (
        error.status_code == 503
        and isinstance(error.detail, dict)
        and error.detail.get('code') == RETRYABLE_CONVERSATION_PROCESSING_ERROR_CODE
    )


class ReconcileRequest(BaseModel):
    uid: str = Field(min_length=1, max_length=128, pattern=r'^[^/]+$')
    trigger: Literal['native_manual_ready'] | None = None


@router.post('/v1/conversations-v3/reconcile', include_in_schema=False)
async def reconcile(body: ReconcileRequest, request: Request, _retry: int = Depends(verify_cloud_tasks_oidc)):
    try:
        with bind_request_log_trace(dict(request.headers.raw)):
            if body.trigger != 'native_manual_ready':
                return {'outcome': await service.reconcile(body.uid, background=True)}
            outcome = await service.reconcile(body.uid)
            if outcome == 'busy':
                return retry_response(RetryReason.LOCKED)
            return {'outcome': outcome}
    except Exception as error:
        # Keep the shared boundary's metric, but adapt its mobile 503 contract
        # to the task-target 409 contract; Cloud Tasks ignores Retry-After.
        if isinstance(error, HTTPException):
            if _is_retryable_provider_http_answer(error):
                return retry_response(RetryReason.DEPENDENCY_WARMING)
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
        # Classify and record provider faults with the shared adapter, then use
        # the contract-(d) response shape for this Cloud Tasks target.
        retryable = retryable_provider_failure_http_exception(error, route='conversations_v3_reconcile')
        if retryable is None:
            raise
        return retry_response(RetryReason.DEPENDENCY_WARMING)


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
        return retry_response(RetryReason.LOCKED)
    except Exception as error:
        # An already-typed provider 503 has been counted at the composition
        # boundary; translate it without recording the same failure twice.
        if isinstance(error, HTTPException):
            if _is_retryable_provider_http_answer(error):
                return retry_response(RetryReason.DEPENDENCY_WARMING)
            raise
        retryable = retryable_provider_failure_http_exception(error, route='conversations_v3_backfill')
        if retryable is None:
            raise
        return retry_response(RetryReason.DEPENDENCY_WARMING)


@router.post('/v1/conversations-v3/legacy-users', include_in_schema=False)
async def legacy_users(_retry: int = Depends(verify_cloud_tasks_oidc)):
    return await service.measure_legacy_users()
