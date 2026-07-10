"""Canonical Candidate lifecycle API."""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

import database.candidates as candidates_db
import database.task_intelligence_control as task_control_db
from models.candidate import (
    CandidateCreate,
    CandidateListResponse,
    CandidateMigrationReport,
    CandidateMigrationRequest,
    CandidateRecord,
    CandidateResolutionReceipt,
    CandidateResolutionRequest,
    CandidateStatus,
)
from models.task_intelligence import TaskWorkflowMode
from utils.other import endpoints as auth
from utils.task_intelligence import candidate_service
from utils.task_intelligence.task_links import TaskLinkValidationError
from utils.task_intelligence.staged_migration import migrate_staged_tasks

router = APIRouter()

IdempotencyHeader = Annotated[str, Header(alias='Idempotency-Key', min_length=1, max_length=512)]
AccountGenerationHeader = Annotated[int, Header(alias='X-Account-Generation', ge=0)]


def _require_candidate_write_control(uid: str, account_generation: int) -> None:
    control = task_control_db.get_task_workflow_control(uid)
    if control.account_generation != account_generation:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Account generation mismatch')
    if control.workflow_mode not in {TaskWorkflowMode.write, TaskWorkflowMode.read}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Candidate writes are not enabled')


def _raise_store_error(exc: candidates_db.CandidateStoreError) -> None:
    if isinstance(exc, candidates_db.CandidateNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Candidate or task not found') from exc
    if isinstance(exc, candidates_db.CandidateGenerationMismatchError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Account generation mismatch') from exc
    if isinstance(exc, candidates_db.WorkstreamCandidateResolverUnavailableError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post('/v1/candidates', response_model=CandidateRecord, tags=['candidates'])
def create_candidate(
    request: CandidateCreate,
    idempotency_key: IdempotencyHeader,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(auth.get_current_user_uid),
):
    _require_candidate_write_control(uid, account_generation)
    try:
        return candidate_service.create_candidate(
            uid,
            request,
            idempotency_key=idempotency_key,
            account_generation=account_generation,
        )
    except candidates_db.CandidateStoreError as exc:
        _raise_store_error(exc)


@router.get('/v1/candidates', response_model=CandidateListResponse, tags=['candidates'])
def list_candidates(
    candidate_status: Optional[CandidateStatus] = Query(default=None, alias='status'),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    uid: str = Depends(auth.get_current_user_uid),
):
    control = task_control_db.get_task_workflow_control(uid)
    records = candidates_db.list_candidates(
        uid,
        status=candidate_status,
        account_generation=control.account_generation,
        limit=limit + 1,
        offset=offset,
    )
    return CandidateListResponse(candidates=records[:limit], has_more=len(records) > limit)


@router.post('/v1/candidates/migrate-staged', response_model=CandidateMigrationReport, tags=['candidates'])
def migrate_staged_candidates(
    request: CandidateMigrationRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    control = task_control_db.get_task_workflow_control(uid)
    return migrate_staged_tasks(uid, control, after_id=request.after_id, limit=request.limit)


@router.post('/v1/candidates/integrations/drain', tags=['candidates'])
def drain_candidate_integrations(
    account_generation: AccountGenerationHeader,
    limit: int = Query(default=100, ge=1, le=500),
    uid: str = Depends(auth.get_current_user_uid),
):
    _require_candidate_write_control(uid, account_generation)
    return {
        'scheduled': candidate_service.drain_candidate_integrations(
            uid,
            account_generation=account_generation,
            limit=limit,
        )
    }


@router.get('/v1/candidates/{candidate_id}', response_model=CandidateRecord, tags=['candidates'])
def get_candidate(candidate_id: str, uid: str = Depends(auth.get_current_user_uid)):
    candidate = candidates_db.get_candidate(uid, candidate_id)
    control = task_control_db.get_task_workflow_control(uid)
    if candidate is None or candidate.account_generation != control.account_generation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Candidate not found')
    return candidate


@router.post('/v1/candidates/{candidate_id}/accept', response_model=CandidateResolutionReceipt, tags=['candidates'])
def accept_candidate(
    candidate_id: str,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(auth.get_current_user_uid),
):
    _require_candidate_write_control(uid, account_generation)
    try:
        return candidate_service.accept_candidate(uid, candidate_id, account_generation=account_generation)
    except TaskLinkValidationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except candidates_db.CandidateStoreError as exc:
        _raise_store_error(exc)


@router.post('/v1/candidates/{candidate_id}/reject', response_model=CandidateResolutionReceipt, tags=['candidates'])
def reject_candidate(
    candidate_id: str,
    request: CandidateResolutionRequest,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(auth.get_current_user_uid),
):
    _require_candidate_write_control(uid, account_generation)
    try:
        return candidate_service.reject_candidate(
            uid,
            candidate_id,
            reason=request.reason,
            account_generation=account_generation,
        )
    except candidates_db.CandidateStoreError as exc:
        _raise_store_error(exc)


@router.post('/v1/candidates/{candidate_id}/expire', response_model=CandidateResolutionReceipt, tags=['candidates'])
def expire_candidate(
    candidate_id: str,
    request: CandidateResolutionRequest,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(auth.get_current_user_uid),
):
    _require_candidate_write_control(uid, account_generation)
    try:
        return candidate_service.expire_candidate(
            uid,
            candidate_id,
            reason=request.reason,
            account_generation=account_generation,
        )
    except candidates_db.CandidateStoreError as exc:
        _raise_store_error(exc)


__all__ = ['router']
