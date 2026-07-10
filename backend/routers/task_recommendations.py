"""Canonical task feedback and What Matters Now APIs."""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

import database.task_recommendations as recommendation_db
import database.task_intelligence_control as task_control_db
from models.task_recommendation import (
    DecisionDebugProjection,
    EvaluationRequest,
    FeedbackCreate,
    FeedbackRecord,
    InterventionCreate,
    InterventionRecord,
    NormalizedContextSnapshot,
    OpenLoopSnapshot,
    OutcomeCreate,
    OutcomeRecord,
    SnapshotReceipt,
    WhatMattersNowProjection,
)
from utils.other import endpoints as auth
from utils.client_device import resolve_client_device_from_request
from utils.llm.clients import get_llm
from utils.task_intelligence import recommendations
from utils.task_intelligence.live_recommendation_judgment import LiveRecommendationJudgment
from utils.task_intelligence.rollout import resolve_task_intelligence_for_user

router = APIRouter()

IdempotencyHeader = Annotated[str, Header(alias='Idempotency-Key', min_length=1, max_length=512)]
AccountGenerationHeader = Annotated[int, Header(alias='X-Account-Generation', ge=0)]


def _live_judgment() -> LiveRecommendationJudgment:
    return LiveRecommendationJudgment(lambda: get_llm('what_matters_now'))


def _raise_store_error(exc: Exception) -> None:
    if isinstance(exc, recommendation_db.InterventionNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Intervention not found') from exc
    if isinstance(exc, recommendation_db.AttributionChainNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Attribution chain not found') from exc
    if isinstance(exc, recommendation_db.IdempotencyConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, recommendation_db.StaleSnapshotError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, recommendation_db.RecommendationGenerationMismatchError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, recommendations.SnapshotValidationError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    raise exc


def _rollout(uid: str):
    control = task_control_db.get_task_workflow_control(uid)
    return resolve_task_intelligence_for_user(
        uid=uid,
        workflow_mode=control.workflow_mode,
        account_generation=control.account_generation,
    )


def _require_product(uid: str):
    rollout = _rollout(uid)
    if not rollout.intelligence_product_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Not found')
    return rollout


def _require_mutation_generation(uid: str, account_generation: int) -> None:
    rollout = _rollout(uid)
    if not rollout.intelligence_product_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Not found')
    if rollout.account_generation != account_generation:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='account generation mismatch')


def _require_evaluation_ingress(uid: str):
    rollout = _rollout(uid)
    if not rollout.intelligence_evaluation_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Not found')
    return rollout


def _require_evaluation_generation(uid: str, account_generation: int):
    rollout = _require_evaluation_ingress(uid)
    if rollout.account_generation != account_generation:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='account generation mismatch')
    return rollout


def _bound_device_id(request: Request, requested_device_id: Optional[str], *, required: bool) -> Optional[str]:
    resolved_device_id = resolve_client_device_from_request(request).client_device_id
    if resolved_device_id is None:
        if required or requested_device_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail='X-App-Platform and X-Device-Id-Hash are required for device-scoped state',
            )
        return None
    if requested_device_id is not None and requested_device_id != resolved_device_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Device scope mismatch')
    return resolved_device_id


@router.get('/v1/what-matters-now', response_model=WhatMattersNowProjection, tags=['task-intelligence'])
def get_what_matters_now(
    request_context: Request,
    device_id: Optional[str] = Query(default=None, min_length=1, max_length=128),
    uid: str = Depends(auth.get_current_user_uid),
):
    rollout = _require_product(uid)
    bound_device_id = _bound_device_id(request_context, device_id, required=False)
    try:
        return recommendations.evaluate(
            uid,
            EvaluationRequest(device_id=bound_device_id),
            judgment=_live_judgment(),
            account_generation=rollout.account_generation,
        )
    except recommendation_db.TaskRecommendationStoreError as exc:
        _raise_store_error(exc)


@router.post('/v1/what-matters-now/evaluate', response_model=WhatMattersNowProjection, tags=['task-intelligence'])
def evaluate_what_matters_now(
    request: EvaluationRequest,
    request_context: Request,
    uid: str = Depends(auth.get_current_user_uid),
):
    rollout = _require_product(uid)
    device_id = _bound_device_id(request_context, request.device_id, required=False)
    try:
        return recommendations.evaluate(
            uid,
            request.model_copy(update={'device_id': device_id}),
            judgment=_live_judgment(),
            account_generation=rollout.account_generation,
        )
    except recommendation_db.TaskRecommendationStoreError as exc:
        _raise_store_error(exc)


@router.post('/v1/task-intelligence/interventions', response_model=InterventionRecord, tags=['task-intelligence'])
def register_intervention(
    request: InterventionCreate,
    idempotency_key: IdempotencyHeader,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(auth.get_current_user_uid),
):
    _require_mutation_generation(uid, account_generation)
    try:
        return recommendations.register_intervention(
            uid, request, idempotency_key=idempotency_key, account_generation=account_generation
        )
    except (recommendation_db.TaskRecommendationStoreError, recommendations.SnapshotValidationError) as exc:
        _raise_store_error(exc)


@router.post('/v1/task-intelligence/feedback', response_model=FeedbackRecord, tags=['task-intelligence'])
def create_feedback(
    request: FeedbackCreate,
    idempotency_key: IdempotencyHeader,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(auth.get_current_user_uid),
):
    _require_mutation_generation(uid, account_generation)
    try:
        return recommendations.record_feedback(
            uid, request, idempotency_key=idempotency_key, account_generation=account_generation
        )
    except (recommendation_db.TaskRecommendationStoreError, recommendations.SnapshotValidationError) as exc:
        _raise_store_error(exc)


@router.post('/v1/task-intelligence/outcomes', response_model=OutcomeRecord, tags=['task-intelligence'])
def create_outcome(
    request: OutcomeCreate,
    idempotency_key: IdempotencyHeader,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(auth.get_current_user_uid),
):
    _require_mutation_generation(uid, account_generation)
    try:
        return recommendations.record_outcome(
            uid, request, idempotency_key=idempotency_key, account_generation=account_generation
        )
    except recommendation_db.TaskRecommendationStoreError as exc:
        _raise_store_error(exc)


@router.put('/v1/task-intelligence/context-snapshot', response_model=SnapshotReceipt, tags=['task-intelligence'])
def replace_context_snapshot(
    request: NormalizedContextSnapshot,
    request_context: Request,
    idempotency_key: IdempotencyHeader,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(auth.get_current_user_uid),
):
    _require_evaluation_generation(uid, account_generation)
    _bound_device_id(request_context, request.device_id, required=True)
    try:
        return recommendations.ingest_context_snapshot(
            uid,
            request,
            account_generation=account_generation,
            idempotency_key=idempotency_key,
        )
    except (recommendation_db.TaskRecommendationStoreError, recommendations.SnapshotValidationError) as exc:
        _raise_store_error(exc)


@router.put('/v1/task-intelligence/open-loop-snapshot', response_model=SnapshotReceipt, tags=['task-intelligence'])
def replace_open_loop_snapshot(
    request: OpenLoopSnapshot,
    request_context: Request,
    idempotency_key: IdempotencyHeader,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(auth.get_current_user_uid),
):
    _require_evaluation_generation(uid, account_generation)
    _bound_device_id(request_context, request.device_id, required=True)
    try:
        return recommendations.ingest_open_loop_snapshot(
            uid,
            request,
            account_generation=account_generation,
            idempotency_key=idempotency_key,
        )
    except (recommendation_db.TaskRecommendationStoreError, recommendations.SnapshotValidationError) as exc:
        _raise_store_error(exc)


@router.get(
    '/v1/task-intelligence/debug/evaluations/{evaluation_id}',
    response_model=DecisionDebugProjection,
    tags=['task-intelligence'],
)
def get_evaluation_debug_projection(
    request_context: Request,
    evaluation_id: str,
    x_omi_debug: Annotated[bool, Header(alias='X-Omi-Debug')] = False,
    device_id: Optional[str] = Query(default=None, min_length=1, max_length=128),
    uid: str = Depends(auth.get_current_user_uid),
):
    rollout = _require_product(uid)
    if not x_omi_debug:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Not found')
    bound_device_id = _bound_device_id(request_context, device_id, required=False)
    try:
        projection = recommendations.get_debug_projection(
            uid, evaluation_id, device_id=bound_device_id, account_generation=rollout.account_generation
        )
    except recommendation_db.TaskRecommendationStoreError as exc:
        _raise_store_error(exc)
    if projection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Evaluation not found')
    return projection


__all__ = ['router']
