"""Thread-behind-a-task APIs; workstream creation is intentionally intent-only."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query

import database.workstreams as workstreams_db
from models.workstream import (
    ArtifactDescriptor,
    ArtifactDescriptorCreate,
    ArtifactStatusTransitionRequest,
    ContinuationCheckpoint,
    ContinuationCheckpointUpsert,
    TaskGoalLinkImportReport,
    TaskGoalLinkImportRequest,
    WorkIntentReceipt,
    WorkIntentRequest,
    Workstream,
    WorkstreamDetailProjection,
    WorkstreamEvent,
    WorkstreamEventCreate,
    WorkstreamUpdate,
)
from utils.other import endpoints as auth

router = APIRouter()
IdempotencyHeader = Annotated[str, Header(alias='Idempotency-Key', min_length=1, max_length=256)]
AccountGenerationHeader = Annotated[int, Header(alias='X-Account-Generation', ge=0)]


def _raise_store_error(exc: Exception) -> None:
    if isinstance(exc, workstreams_db.WorkstreamNotFoundError):
        raise HTTPException(status_code=404, detail='Workflow resource not found') from exc
    if isinstance(
        exc,
        (workstreams_db.WorkstreamConflictError, workstreams_db.WorkstreamGenerationMismatchError),
    ):
        raise HTTPException(status_code=409, detail='Workflow operation conflicts with current state') from exc
    raise exc


@router.post('/v1/work-intents', tags=['tasks'], response_model=WorkIntentReceipt)
def resolve_work_intent(
    request: WorkIntentRequest,
    idempotency_key: IdempotencyHeader,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(auth.get_current_user_uid),
) -> WorkIntentReceipt:
    """Idempotent backend operation behind the “Work on this with Omi” affordance."""

    try:
        return workstreams_db.resolve_work_intent(
            uid,
            request,
            idempotency_key=idempotency_key,
            account_generation=account_generation,
        )
    except workstreams_db.WorkstreamStoreError as exc:
        _raise_store_error(exc)
        raise AssertionError('unreachable')


@router.get('/v1/workstreams/{workstream_id}', tags=['tasks'], response_model=WorkstreamDetailProjection)
def get_workstream_detail(
    workstream_id: str,
    uid: str = Depends(auth.get_current_user_uid),
) -> WorkstreamDetailProjection:
    try:
        return workstreams_db.get_workstream_detail(uid, workstream_id)
    except workstreams_db.WorkstreamStoreError as exc:
        _raise_store_error(exc)
        raise AssertionError('unreachable')


@router.patch('/v1/workstreams/{workstream_id}', tags=['tasks'], response_model=Workstream)
def update_workstream(
    workstream_id: str,
    request: WorkstreamUpdate,
    idempotency_key: IdempotencyHeader,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(auth.get_current_user_uid),
) -> Workstream:
    try:
        return workstreams_db.update_workstream(
            uid,
            workstream_id,
            request,
            idempotency_key=idempotency_key,
            account_generation=account_generation,
        )
    except workstreams_db.WorkstreamStoreError as exc:
        _raise_store_error(exc)
        raise AssertionError('unreachable')


@router.post('/v1/workstreams/{workstream_id}/events', tags=['tasks'], response_model=WorkstreamEvent)
def append_workstream_event(
    workstream_id: str,
    request: WorkstreamEventCreate,
    idempotency_key: IdempotencyHeader,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(auth.get_current_user_uid),
) -> WorkstreamEvent:
    try:
        return workstreams_db.append_workstream_event(
            uid,
            workstream_id,
            request,
            idempotency_key=idempotency_key,
            account_generation=account_generation,
        )
    except workstreams_db.WorkstreamStoreError as exc:
        _raise_store_error(exc)
        raise AssertionError('unreachable')


@router.get('/v1/workstreams/{workstream_id}/events', tags=['tasks'], response_model=list[WorkstreamEvent])
def list_workstream_events(
    workstream_id: str,
    after_sequence: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    uid: str = Depends(auth.get_current_user_uid),
) -> list[WorkstreamEvent]:
    return workstreams_db.list_workstream_events(
        uid,
        workstream_id,
        after_sequence=after_sequence,
        limit=limit,
    )


@router.post('/v1/workstreams/{workstream_id}/artifacts', tags=['tasks'], response_model=ArtifactDescriptor)
def create_artifact_descriptor(
    workstream_id: str,
    request: ArtifactDescriptorCreate,
    idempotency_key: IdempotencyHeader,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(auth.get_current_user_uid),
) -> ArtifactDescriptor:
    try:
        return workstreams_db.create_artifact_descriptor(
            uid,
            workstream_id,
            request,
            idempotency_key=idempotency_key,
            account_generation=account_generation,
        )
    except workstreams_db.WorkstreamStoreError as exc:
        _raise_store_error(exc)
        raise AssertionError('unreachable')


@router.patch(
    '/v1/workstreams/{workstream_id}/artifacts/{artifact_id}/status',
    tags=['tasks'],
    response_model=ArtifactDescriptor,
)
def transition_artifact_status(
    workstream_id: str,
    artifact_id: str,
    request: ArtifactStatusTransitionRequest,
    idempotency_key: IdempotencyHeader,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(auth.get_current_user_uid),
) -> ArtifactDescriptor:
    try:
        return workstreams_db.transition_artifact_status(
            uid,
            workstream_id,
            artifact_id,
            request,
            idempotency_key=idempotency_key,
            account_generation=account_generation,
        )
    except workstreams_db.WorkstreamStoreError as exc:
        _raise_store_error(exc)
        raise AssertionError('unreachable')


@router.get('/v1/workstreams/{workstream_id}/artifacts', tags=['tasks'], response_model=list[ArtifactDescriptor])
def list_artifact_descriptors(
    workstream_id: str,
    limit: int = Query(100, ge=1, le=500),
    uid: str = Depends(auth.get_current_user_uid),
) -> list[ArtifactDescriptor]:
    return workstreams_db.list_artifact_descriptors(uid, workstream_id, limit=limit)


@router.put(
    '/v1/workstreams/{workstream_id}/checkpoints/{runtime_id}',
    tags=['tasks'],
    response_model=ContinuationCheckpoint,
)
def upsert_continuation_checkpoint(
    workstream_id: str,
    runtime_id: str,
    request: ContinuationCheckpointUpsert,
    idempotency_key: IdempotencyHeader,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(auth.get_current_user_uid),
) -> ContinuationCheckpoint:
    if request.runtime_id != runtime_id:
        raise HTTPException(status_code=422, detail='runtime_id path and body must match')
    try:
        return workstreams_db.upsert_continuation_checkpoint(
            uid,
            workstream_id,
            request,
            idempotency_key=idempotency_key,
            account_generation=account_generation,
        )
    except workstreams_db.WorkstreamStoreError as exc:
        _raise_store_error(exc)
        raise AssertionError('unreachable')


@router.get(
    '/v1/workstreams/{workstream_id}/checkpoints',
    tags=['tasks'],
    response_model=list[ContinuationCheckpoint],
)
def list_continuation_checkpoints(
    workstream_id: str,
    uid: str = Depends(auth.get_current_user_uid),
) -> list[ContinuationCheckpoint]:
    return workstreams_db.list_continuation_checkpoints(uid, workstream_id)


@router.post('/v1/workflow-migrations/task-goal-links', tags=['tasks'], response_model=TaskGoalLinkImportReport)
def import_task_goal_links(
    request: TaskGoalLinkImportRequest,
    idempotency_key: IdempotencyHeader,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(auth.get_current_user_uid),
) -> TaskGoalLinkImportReport:
    try:
        return workstreams_db.import_task_goal_links(
            uid,
            request,
            idempotency_key=idempotency_key,
            account_generation=account_generation,
        )
    except workstreams_db.WorkstreamStoreError as exc:
        _raise_store_error(exc)
        raise AssertionError('unreachable')


__all__ = ['router']
