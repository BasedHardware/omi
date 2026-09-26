"""Thread-behind-a-task APIs; workstream creation is intentionally intent-only."""

import logging
from typing import Annotated, NoReturn

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
from routers.canonical_task_access import require_canonical_task_user
from utils.log_sanitizer import sanitize
from utils.task_intelligence.workstream_index import refresh_workstream_association_index

logger = logging.getLogger(__name__)

router = APIRouter()
IdempotencyHeader = Annotated[str, Header(alias='Idempotency-Key', min_length=1, max_length=256)]
AccountGenerationHeader = Annotated[int, Header(alias='X-Account-Generation', ge=0)]


def _clean_id(id_val: str | None, field_name: str = 'id') -> str:
    cleaned = (id_val or '').strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail=f'{field_name} must not be empty or whitespace')
    return cleaned


def _raise_store_error(exc: Exception) -> NoReturn:
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, workstreams_db.WorkstreamNotFoundError):
        raise HTTPException(status_code=404, detail='Workflow resource not found') from exc
    if isinstance(
        exc,
        (workstreams_db.WorkstreamConflictError, workstreams_db.WorkstreamGenerationMismatchError),
    ):
        raise HTTPException(status_code=409, detail='Workflow operation conflicts with current state') from exc
    if isinstance(exc, (ValueError, TypeError)):
        logger.warning('workstreams router validation error: %s', sanitize(str(exc)))
        raise HTTPException(status_code=400, detail='Invalid workstream request') from exc
    logger.error('Unhandled workstreams error: %s', sanitize(str(exc)), exc_info=True)
    raise HTTPException(status_code=500, detail='An internal server error occurred') from exc


@router.post('/v1/work-intents', tags=['tasks'], response_model=WorkIntentReceipt)
def resolve_work_intent(
    request: WorkIntentRequest,
    idempotency_key: IdempotencyHeader,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(require_canonical_task_user),
) -> WorkIntentReceipt:
    """Idempotent backend operation behind the “Work on this with Omi” affordance."""

    try:
        receipt = workstreams_db.resolve_work_intent(
            uid,
            request,
            idempotency_key=idempotency_key,
            account_generation=account_generation,
        )
        refresh_workstream_association_index(uid, receipt.workstream_id)
        return receipt
    except HTTPException:
        raise
    except Exception as exc:
        _raise_store_error(exc)


@router.get('/v1/workstreams/{workstream_id}', tags=['tasks'], response_model=WorkstreamDetailProjection)
def get_workstream_detail(
    workstream_id: str,
    uid: str = Depends(require_canonical_task_user),
) -> WorkstreamDetailProjection:
    clean_workstream_id = _clean_id(workstream_id, 'workstream_id')
    try:
        return workstreams_db.get_workstream_detail(uid, clean_workstream_id)
    except HTTPException:
        raise
    except Exception as exc:
        _raise_store_error(exc)


@router.patch('/v1/workstreams/{workstream_id}', tags=['tasks'], response_model=Workstream)
def update_workstream(
    workstream_id: str,
    request: WorkstreamUpdate,
    idempotency_key: IdempotencyHeader,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(require_canonical_task_user),
) -> Workstream:
    clean_workstream_id = _clean_id(workstream_id, 'workstream_id')
    try:
        workstream = workstreams_db.update_workstream(
            uid,
            clean_workstream_id,
            request,
            idempotency_key=idempotency_key,
            account_generation=account_generation,
        )
        refresh_workstream_association_index(uid, workstream.workstream_id)
        return workstream
    except HTTPException:
        raise
    except Exception as exc:
        _raise_store_error(exc)


@router.post('/v1/workstreams/{workstream_id}/events', tags=['tasks'], response_model=WorkstreamEvent)
def append_workstream_event(
    workstream_id: str,
    request: WorkstreamEventCreate,
    idempotency_key: IdempotencyHeader,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(require_canonical_task_user),
) -> WorkstreamEvent:
    clean_workstream_id = _clean_id(workstream_id, 'workstream_id')
    try:
        return workstreams_db.append_workstream_event(
            uid,
            clean_workstream_id,
            request,
            idempotency_key=idempotency_key,
            account_generation=account_generation,
        )
    except HTTPException:
        raise
    except Exception as exc:
        _raise_store_error(exc)


@router.get('/v1/workstreams/{workstream_id}/events', tags=['tasks'], response_model=list[WorkstreamEvent])
def list_workstream_events(
    workstream_id: str,
    after_sequence: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    uid: str = Depends(require_canonical_task_user),
) -> list[WorkstreamEvent]:
    clean_workstream_id = _clean_id(workstream_id, 'workstream_id')
    try:
        return workstreams_db.list_workstream_events(
            uid,
            clean_workstream_id,
            after_sequence=after_sequence,
            limit=limit,
        )
    except HTTPException:
        raise
    except Exception as exc:
        _raise_store_error(exc)


@router.post('/v1/workstreams/{workstream_id}/artifacts', tags=['tasks'], response_model=ArtifactDescriptor)
def create_artifact_descriptor(
    workstream_id: str,
    request: ArtifactDescriptorCreate,
    idempotency_key: IdempotencyHeader,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(require_canonical_task_user),
) -> ArtifactDescriptor:
    clean_workstream_id = _clean_id(workstream_id, 'workstream_id')
    try:
        return workstreams_db.create_artifact_descriptor(
            uid,
            clean_workstream_id,
            request,
            idempotency_key=idempotency_key,
            account_generation=account_generation,
        )
    except HTTPException:
        raise
    except Exception as exc:
        _raise_store_error(exc)


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
    uid: str = Depends(require_canonical_task_user),
) -> ArtifactDescriptor:
    clean_workstream_id = _clean_id(workstream_id, 'workstream_id')
    clean_artifact_id = _clean_id(artifact_id, 'artifact_id')
    try:
        return workstreams_db.transition_artifact_status(
            uid,
            clean_workstream_id,
            clean_artifact_id,
            request,
            idempotency_key=idempotency_key,
            account_generation=account_generation,
        )
    except HTTPException:
        raise
    except Exception as exc:
        _raise_store_error(exc)


@router.get('/v1/workstreams/{workstream_id}/artifacts', tags=['tasks'], response_model=list[ArtifactDescriptor])
def list_artifact_descriptors(
    workstream_id: str,
    limit: int = Query(100, ge=1, le=500),
    uid: str = Depends(require_canonical_task_user),
) -> list[ArtifactDescriptor]:
    clean_workstream_id = _clean_id(workstream_id, 'workstream_id')
    try:
        return workstreams_db.list_artifact_descriptors(uid, clean_workstream_id, limit=limit)
    except HTTPException:
        raise
    except Exception as exc:
        _raise_store_error(exc)


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
    uid: str = Depends(require_canonical_task_user),
) -> ContinuationCheckpoint:
    clean_workstream_id = _clean_id(workstream_id, 'workstream_id')
    clean_runtime_id = _clean_id(runtime_id, 'runtime_id')
    if request.runtime_id != clean_runtime_id:
        raise HTTPException(status_code=422, detail='runtime_id path and body must match')
    try:
        return workstreams_db.upsert_continuation_checkpoint(
            uid,
            clean_workstream_id,
            request,
            idempotency_key=idempotency_key,
            account_generation=account_generation,
        )
    except HTTPException:
        raise
    except Exception as exc:
        _raise_store_error(exc)


@router.get(
    '/v1/workstreams/{workstream_id}/checkpoints',
    tags=['tasks'],
    response_model=list[ContinuationCheckpoint],
)
def list_continuation_checkpoints(
    workstream_id: str,
    uid: str = Depends(require_canonical_task_user),
) -> list[ContinuationCheckpoint]:
    clean_workstream_id = _clean_id(workstream_id, 'workstream_id')
    try:
        return workstreams_db.list_continuation_checkpoints(uid, clean_workstream_id)
    except HTTPException:
        raise
    except Exception as exc:
        _raise_store_error(exc)


@router.post('/v1/workflow-migrations/task-goal-links', tags=['tasks'], response_model=TaskGoalLinkImportReport)
def import_task_goal_links(
    request: TaskGoalLinkImportRequest,
    idempotency_key: IdempotencyHeader,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(require_canonical_task_user),
) -> TaskGoalLinkImportReport:
    try:
        return workstreams_db.import_task_goal_links(
            uid,
            request,
            idempotency_key=idempotency_key,
            account_generation=account_generation,
        )
    except HTTPException:
        raise
    except Exception as exc:
        _raise_store_error(exc)


__all__ = ['router']
