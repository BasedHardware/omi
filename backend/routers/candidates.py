"""Canonical Candidate lifecycle API."""

from datetime import datetime, timezone
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

import database.candidates as candidates_db
import database.task_recommendations as recommendation_db
import database.task_intelligence_control as task_control_db
from models.action_item import TaskCreatePayload
from models.candidate import (
    CandidateAction,
    CandidateCreate,
    CandidateListResponse,
    CandidateMigrationReport,
    CandidateMigrationRequest,
    CandidateRecord,
    CandidateResolutionReceipt,
    CandidateResolutionRequest,
    CandidateStatus,
    CandidateSubjectKind,
)
from models.task_intelligence import TaskWorkflowControl, TaskWorkflowMode
from utils.other import endpoints as auth
from utils.task_intelligence import candidate_service
from utils.task_intelligence.capture_policy import MINIMUM_CAPTURE_CONFIDENCE
from utils.task_intelligence.recommendations import candidate_recommendation_dedupe_key
from utils.task_intelligence.rollout import resolve_chat_first_ui, resolve_task_intelligence_for_user
from utils.task_intelligence.task_links import TaskLinkValidationError
from utils.task_intelligence.staged_migration import migrate_staged_tasks

router = APIRouter()

IdempotencyHeader = Annotated[str, Header(alias='Idempotency-Key', min_length=1, max_length=512)]
AccountGenerationHeader = Annotated[int, Header(alias='X-Account-Generation', ge=0)]
SUGGESTED_CANDIDATE_LIMIT = 5
SUGGESTED_CANDIDATE_RAW_LIMIT = 500
SUGGESTED_CANDIDATE_FRESHNESS = candidates_db.PENDING_CANDIDATE_REUSE_WINDOW


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


def _require_suggested_rollout(uid: str):
    control = task_control_db.get_task_workflow_control(uid)
    rollout = resolve_task_intelligence_for_user(
        uid=uid,
        workflow_mode=control.workflow_mode,
        account_generation=control.account_generation,
    )
    if not rollout.intelligence_product_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Not found')
    return rollout


def _has_suggested_candidate_shape(
    candidate: CandidateRecord,
    *,
    now: datetime,
    enforce_freshness: bool = True,
) -> bool:
    if candidate.proposed_action != CandidateAction.create:
        return False
    if candidate.subject_kind == CandidateSubjectKind.task:
        if not isinstance(candidate.task_change, TaskCreatePayload):
            return False
    elif candidate.subject_kind == CandidateSubjectKind.workstream:
        if candidate.workstream_proposal is None:
            return False
    else:
        return False
    if (
        candidate.capture_confidence < MINIMUM_CAPTURE_CONFIDENCE
        or candidate.ownership_confidence < MINIMUM_CAPTURE_CONFIDENCE
        or not candidate.evidence_refs
    ):
        return False
    created_at = candidate.created_at
    if created_at.tzinfo is None:
        return False
    return not enforce_freshness or created_at >= now - SUGGESTED_CANDIDATE_FRESHNESS


def _is_suggested_candidate(candidate: CandidateRecord, *, now: datetime) -> bool:
    return candidate.status == CandidateStatus.pending and _has_suggested_candidate_shape(candidate, now=now)


def _suggested_candidates(
    candidates: list[CandidateRecord],
    *,
    limit: int,
    suppressed_dedupe_keys: set[str],
    now: Optional[datetime] = None,
) -> list[CandidateRecord]:
    current_time = now or datetime.now(timezone.utc)
    eligible = [candidate for candidate in candidates if _is_suggested_candidate(candidate, now=current_time)]
    eligible.sort(key=lambda candidate: candidate.created_at, reverse=True)
    eligible_with_identity = [
        (candidate, candidates_db.suggested_candidate_semantic_identity(candidate.as_proposal()))
        for candidate in eligible
    ]
    terminal_resolutions: dict[str, list[datetime]] = {}
    for candidate in candidates:
        if (
            candidate.status not in {CandidateStatus.accepted, CandidateStatus.rejected}
            or candidate.resolved_at is None
            or candidate.resolved_at.tzinfo is None
            or not _has_suggested_candidate_shape(candidate, now=current_time, enforce_freshness=False)
        ):
            continue
        semantic_identity = candidates_db.suggested_candidate_semantic_identity(candidate.as_proposal())
        if semantic_identity is not None:
            terminal_resolutions.setdefault(semantic_identity, []).append(candidate.resolved_at)
    suppressed_semantic_identities = {
        semantic_identity
        for candidate in candidates
        if _has_suggested_candidate_shape(candidate, now=current_time, enforce_freshness=False)
        and (semantic_identity := candidates_db.suggested_candidate_semantic_identity(candidate.as_proposal()))
        is not None
        and candidate_recommendation_dedupe_key(candidate.candidate_id) in suppressed_dedupe_keys
    }
    projection: list[CandidateRecord] = []
    seen: set[str] = set()
    for candidate, semantic_identity in eligible_with_identity:
        if candidate_recommendation_dedupe_key(candidate.candidate_id) in suppressed_dedupe_keys:
            continue
        if semantic_identity is not None and semantic_identity in suppressed_semantic_identities:
            continue
        if semantic_identity is not None and any(
            candidate.created_at <= resolved_at for resolved_at in terminal_resolutions.get(semantic_identity, [])
        ):
            continue
        dedupe_key = semantic_identity or candidate.candidate_id
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        projection.append(candidate)
        if len(projection) == min(limit, SUGGESTED_CANDIDATE_LIMIT):
            break
    return projection


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
    surface: Optional[Literal['suggested']] = Query(default=None),
    uid: str = Depends(auth.get_current_user_uid),
):
    if surface == 'suggested':
        rollout = _require_suggested_rollout(uid)
        records = candidates_db.list_candidates(
            uid,
            status=None,
            account_generation=rollout.account_generation,
            limit=SUGGESTED_CANDIDATE_RAW_LIMIT,
            offset=0,
        )
        now = datetime.now(timezone.utc)
        suppressed = recommendation_db.list_active_override_dedupe_keys(
            uid,
            now=now,
            account_generation=rollout.account_generation,
        )
        refreshed_rollout = _require_suggested_rollout(uid)
        if refreshed_rollout.account_generation != rollout.account_generation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Not found')
        return CandidateListResponse(
            candidates=_suggested_candidates(
                records,
                limit=limit,
                suppressed_dedupe_keys=suppressed,
                now=now,
            ),
            has_more=False,
        )
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


@router.get('/v1/candidates/control', response_model=TaskWorkflowControl, tags=['candidates'])
def get_candidate_workflow_control(uid: str = Depends(auth.get_current_user_uid)) -> TaskWorkflowControl:
    try:
        control = task_control_db.get_task_workflow_control(uid)
    except Exception:
        # This endpoint selects a shell. An unavailable control record must not
        # expose a partial new experience or hide the legacy-safe response.
        return TaskWorkflowControl()

    try:
        rollout = resolve_task_intelligence_for_user(
            uid=uid,
            workflow_mode=control.workflow_mode,
            account_generation=control.account_generation,
        )
        chat_first_ui = resolve_chat_first_ui(rollout, control.chat_first_ui_enabled)
    except Exception:
        # Cohort resolution is intentionally fail-closed: a backend outage or
        # stale selector keeps this user in the existing shell.
        chat_first_ui = False

    return control.model_copy(update={'chat_first_ui': chat_first_ui})


@router.post('/v1/candidates/integrations/drain', tags=['candidates'])
def drain_candidate_integrations(
    account_generation: AccountGenerationHeader,
    limit: int = Query(default=100, ge=1, le=500),
    uid: str = Depends(auth.get_current_user_uid),
) -> dict[str, int]:
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
