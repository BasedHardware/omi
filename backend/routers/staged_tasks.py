"""Staged tasks — AI-generated tasks awaiting user promotion to action items."""

import hashlib
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List
from datetime import datetime
from pydantic import BaseModel, Field

import database.staged_tasks as staged_tasks_db
import database.action_items as action_items_db
import database.candidates as candidates_db
import database.task_intelligence_control as task_control_db
from models.candidate import CandidateRecord, CandidateStatus
from models.task_intelligence import TaskWorkflowMode
from models.staged_task import (
    StagedTask,
    StagedTaskListResponse,
    PromoteStagedTaskResponse,
    MigrateConversationItemsResponse,
)
from models.shared import StatusResponse
from utils.other import endpoints as auth
from utils.observability.fallback import record_fallback
from utils.task_intelligence import candidate_service
from utils.task_intelligence.staged_migration import migrate_staged_tasks, proposal_from_legacy_staged

router = APIRouter()
logger = logging.getLogger(__name__)


def _candidate_as_staged(candidate: CandidateRecord) -> dict:
    task_change = candidate.task_change
    return {
        'id': candidate.candidate_id,
        'description': getattr(task_change, 'description', None) or 'Suggested task',
        'completed': candidate.status != CandidateStatus.pending,
        'created_at': candidate.created_at,
        'updated_at': candidate.resolved_at or candidate.created_at,
        'due_at': getattr(task_change, 'due_at', None),
        'source': candidate.source_surface,
        'priority': getattr(task_change, 'priority', None),
    }


def _create_candidate_from_staged_row(uid: str, row: dict, *, account_generation: int) -> CandidateRecord:
    return candidate_service.create_candidate(
        uid,
        proposal_from_legacy_staged(row),
        idempotency_key=f'legacy-staged:{row["id"]}',
        account_generation=account_generation,
    )


def _is_staged_compatibility_candidate(candidate: CandidateRecord) -> bool:
    return (
        candidate.subject_kind.value == 'task'
        and candidate.proposed_action.value == 'create'
        and candidate.source_surface == 'legacy_staged'
    )


def _pending_staged_candidates(uid: str, *, account_generation: int) -> list[CandidateRecord]:
    records: list[CandidateRecord] = []
    offset = 0
    while True:
        page = candidates_db.list_candidates(
            uid,
            status=CandidateStatus.pending,
            account_generation=account_generation,
            limit=500,
            offset=offset,
        )
        records.extend(candidate for candidate in page if _is_staged_compatibility_candidate(candidate))
        if len(page) < 500:
            break
        offset += len(page)
    return records


def _staged_row(uid: str, staged_id: str) -> dict | None:
    return next(
        (row for row in staged_tasks_db.get_all_staged_tasks_for_migration(uid) if row.get('id') == staged_id),
        None,
    )


def _reconcile_write_sidecar(
    uid: str,
    row: dict,
    *,
    account_generation: int,
    status: CandidateStatus,
    result_task_id: str | None = None,
    reason: str,
    claim_token: str | None = None,
) -> bool:
    try:
        candidate = _create_candidate_from_staged_row(uid, row, account_generation=account_generation)
        if candidate.status == CandidateStatus.pending:
            candidate = candidates_db.reconcile_migrated_candidate(
                uid,
                candidate.candidate_id,
                status=status,
                account_generation=account_generation,
                result_task_id=result_task_id,
                reason=reason,
                claim_token=claim_token,
            )
        if candidate.status != status:
            return False
        if status == CandidateStatus.accepted and candidate.result_task_id != result_task_id:
            return False
        return True
    except (ValueError, candidates_db.CandidateStoreError):
        record_fallback(
            component='other',
            from_mode='staged_write',
            to_mode='legacy_only',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        return False


def _require_write_promotion_reconciled(
    uid: str,
    row: dict,
    *,
    account_generation: int,
) -> dict:
    promoted_to = row.get('promoted_to')
    if not isinstance(promoted_to, str) or not promoted_to:
        raise HTTPException(status_code=404, detail='Staged task not found or already promoted')
    candidate, claim_token = _claim_write_promotion(
        uid,
        row,
        account_generation=account_generation,
        resume_active_claim=True,
    )
    if candidate.status == CandidateStatus.accepted:
        if candidate.result_task_id != promoted_to:
            raise HTTPException(status_code=409, detail='Staged task Candidate resolved to another task')
        return action_items_db.get_action_item(uid, promoted_to) or {'id': promoted_to}
    if not claim_token:
        raise HTTPException(status_code=503, detail='Could not recover staged task promotion claim')
    try:
        reserved_task_id = candidates_db.begin_candidate_legacy_promotion(
            uid,
            candidate.candidate_id,
            account_generation=account_generation,
            claim_token=claim_token,
            result_task_id=promoted_to,
            legacy_mutation_already_committed=True,
        )
    except (ValueError, candidates_db.CandidateStoreError) as exc:
        raise HTTPException(status_code=503, detail='Could not recover staged task promotion claim') from exc
    if reserved_task_id.task_id != promoted_to:
        raise HTTPException(status_code=409, detail='Staged task promotion does not match its Candidate claim')
    if not _reconcile_write_sidecar(
        uid,
        row,
        account_generation=account_generation,
        status=CandidateStatus.accepted,
        result_task_id=promoted_to,
        reason=row.get('promotion_skipped') or 'legacy_promoted',
        claim_token=claim_token,
    ):
        raise HTTPException(status_code=503, detail='Could not reconcile staged task promotion')
    return action_items_db.get_action_item(uid, promoted_to) or {'id': promoted_to}


def _claim_write_promotion(
    uid: str,
    row: dict,
    *,
    account_generation: int,
    resume_active_claim: bool = False,
) -> tuple[CandidateRecord, str | None]:
    try:
        candidate = _create_candidate_from_staged_row(uid, row, account_generation=account_generation)
        if candidate.status == CandidateStatus.accepted:
            return candidate, None
        if candidate.status in {CandidateStatus.rejected, CandidateStatus.expired}:
            staged_tasks_db.suppress_staged_task_for_terminal_candidate(
                uid,
                row['id'],
                reason=candidate.status.value,
            )
            return candidate, None
        if candidate.status != CandidateStatus.pending:
            raise HTTPException(status_code=409, detail=f'Staged task Candidate is {candidate.status.value}')
        claim_token = candidates_db.claim_candidate_for_legacy_promotion(
            uid,
            candidate.candidate_id,
            account_generation=account_generation,
            resume_active_claim=resume_active_claim,
        )
        return candidate, claim_token
    except HTTPException:
        raise
    except (ValueError, candidates_db.CandidateStoreError) as exc:
        raise HTTPException(status_code=409, detail='Staged task Candidate cannot be promoted') from exc


def _begin_write_promotion(
    uid: str,
    row: dict,
    candidate: CandidateRecord,
    claim_token: str | None,
    *,
    account_generation: int,
) -> candidates_db.LegacyPromotionReservation:
    if not claim_token:
        raise HTTPException(status_code=409, detail='Staged task Candidate has no promotion claim')
    existing = action_items_db.get_active_action_item_by_description(uid, row['description'])
    preferred_existing_task_id = (
        existing['id'] if existing is not None and isinstance(existing.get('id'), str) and existing['id'] else None
    )
    result_task_id = candidates_db.task_id_for_candidate(uid, account_generation, candidate.candidate_id)
    try:
        return candidates_db.begin_candidate_legacy_promotion(
            uid,
            candidate.candidate_id,
            account_generation=account_generation,
            claim_token=claim_token,
            result_task_id=result_task_id,
            preferred_existing_task_id=preferred_existing_task_id,
        )
    except (ValueError, candidates_db.CandidateStoreError) as exc:
        raise HTTPException(status_code=409, detail='Staged task Candidate promotion could not begin') from exc


# ============================================================================
# MODELS
# ============================================================================


class CreateStagedTaskRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=5000)
    due_at: datetime | None = None
    source: str | None = None
    priority: str | None = None
    metadata: str | None = None
    category: str | None = None
    relevance_score: int | None = Field(None, ge=0, le=1000)


class BatchScoreEntry(BaseModel):
    id: str = Field(..., min_length=1)
    relevance_score: int = Field(..., ge=0, le=1000)


class BatchUpdateScoresRequest(BaseModel):
    scores: List[BatchScoreEntry] = Field(..., max_length=500)


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.post('/v1/staged-tasks', tags=['staged-tasks'], response_model=StagedTask)
def create_staged_task(
    request: CreateStagedTaskRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    control = task_control_db.get_task_workflow_control(uid)
    if control.workflow_mode == TaskWorkflowMode.read:
        digest = hashlib.sha256(request.description.strip().lower().encode('utf-8')).hexdigest()[:24]
        synthetic_row = {
            'id': f'read-{digest}',
            'description': request.description,
            'due_at': request.due_at,
            'source': request.source,
            'priority': request.priority,
        }
        try:
            candidate = _create_candidate_from_staged_row(
                uid, synthetic_row, account_generation=control.account_generation
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail='Staged task cannot be represented canonically') from exc
        return _candidate_as_staged(candidate)

    row = staged_tasks_db.create_staged_task(
        uid,
        description=request.description,
        due_at=request.due_at,
        source=request.source,
        priority=request.priority,
        metadata=request.metadata,
        category=request.category,
        relevance_score=request.relevance_score,
    )
    if control.workflow_mode == TaskWorkflowMode.write:
        try:
            _create_candidate_from_staged_row(uid, row, account_generation=control.account_generation)
        except (ValueError, candidates_db.CandidateStoreError):
            record_fallback(
                component='other',
                from_mode='staged_write',
                to_mode='legacy_only',
                reason='other',
                outcome='degraded',
                log=logger,
            )
    return row


@router.get('/v1/staged-tasks', tags=['staged-tasks'], response_model=StagedTaskListResponse)
def get_staged_tasks(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    uid: str = Depends(auth.get_current_user_uid),
):
    control = task_control_db.get_task_workflow_control(uid)
    if control.workflow_mode == TaskWorkflowMode.read:
        candidates = _pending_staged_candidates(uid, account_generation=control.account_generation)
        return {
            'items': [_candidate_as_staged(candidate) for candidate in candidates[offset : offset + limit]],
            'has_more': len(candidates) > offset + limit,
        }
    fetch_limit = limit + 1
    items = staged_tasks_db.get_staged_tasks(uid, limit=fetch_limit, offset=offset)
    has_more = len(items) > limit
    if has_more:
        items = items[:limit]
    return {'items': items, 'has_more': has_more}


@router.delete('/v1/staged-tasks', tags=['staged-tasks'])
def clear_staged_tasks(uid: str = Depends(auth.get_current_user_uid)):
    control = task_control_db.get_task_workflow_control(uid)
    if control.workflow_mode == TaskWorkflowMode.read:
        candidates = _pending_staged_candidates(uid, account_generation=control.account_generation)
        for candidate in candidates:
            candidate_service.reject_candidate(
                uid,
                candidate.candidate_id,
                reason='legacy_clear',
                account_generation=control.account_generation,
            )
        return {'status': 'ok', 'deleted_count': len(candidates)}
    rows = (
        [row for row in staged_tasks_db.get_all_staged_tasks_for_migration(uid) if not row.get('completed')]
        if control.workflow_mode == TaskWorkflowMode.write
        else []
    )
    for row in rows:
        reconciled = _reconcile_write_sidecar(
            uid,
            row,
            account_generation=control.account_generation,
            status=CandidateStatus.rejected,
            reason='legacy_clear',
        )
        if not reconciled:
            raise HTTPException(status_code=503, detail='Could not reconcile staged task deletion')
    count = staged_tasks_db.clear_staged_tasks(uid)
    return {'status': 'ok', 'deleted_count': count}


@router.delete('/v1/staged-tasks/{task_id}', tags=['staged-tasks'], response_model=StatusResponse)
def delete_staged_task(
    task_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    control = task_control_db.get_task_workflow_control(uid)
    if control.workflow_mode == TaskWorkflowMode.read:
        candidate = candidates_db.get_candidate(uid, task_id)
        if (
            candidate is None
            or candidate.account_generation != control.account_generation
            or not _is_staged_compatibility_candidate(candidate)
        ):
            return {'status': 'ok'}
        if candidate.status != CandidateStatus.pending:
            return {'status': 'ok'}
        try:
            candidate_service.reject_candidate(
                uid,
                task_id,
                reason='legacy_delete',
                account_generation=control.account_generation,
            )
        except candidates_db.CandidateNotFoundError:
            pass
        return {'status': 'ok'}
    row = _staged_row(uid, task_id) if control.workflow_mode == TaskWorkflowMode.write else None
    if row is not None and not row.get('completed'):
        reconciled = _reconcile_write_sidecar(
            uid,
            row,
            account_generation=control.account_generation,
            status=CandidateStatus.rejected,
            reason='legacy_delete',
        )
        if not reconciled:
            raise HTTPException(status_code=503, detail='Could not reconcile staged task deletion')
    staged_tasks_db.delete_staged_task(uid, task_id)
    return {'status': 'ok'}


@router.patch('/v1/staged-tasks/batch-scores', tags=['staged-tasks'], response_model=StatusResponse)
def batch_update_staged_scores(
    request: BatchUpdateScoresRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    if task_control_db.get_task_workflow_control(uid).workflow_mode == TaskWorkflowMode.read:
        return {'status': 'ok'}
    staged_tasks_db.batch_update_staged_scores(uid, [s.model_dump() for s in request.scores])
    return {'status': 'ok'}


@router.post('/v1/staged-tasks/promote', tags=['staged-tasks'], response_model=PromoteStagedTaskResponse)
def promote_staged_task(uid: str = Depends(auth.get_current_user_uid)):
    control = task_control_db.get_task_workflow_control(uid)
    if control.workflow_mode == TaskWorkflowMode.read:
        return {'promoted': False, 'reason': 'Score-based promotion is disabled', 'promoted_task': None}
    claim_token: str | None = None
    reservation: candidates_db.LegacyPromotionReservation | None = None
    if control.workflow_mode == TaskWorkflowMode.write:
        for row in staged_tasks_db.get_all_staged_tasks_for_migration(uid):
            if row.get('completed') and row.get('promoted_to'):
                _require_write_promotion_reconciled(
                    uid,
                    row,
                    account_generation=control.account_generation,
                )
        while True:
            selected_row = staged_tasks_db.get_top_staged_task_for_promotion(uid)
            if selected_row is None:
                return {'promoted': False, 'reason': 'No staged tasks available', 'promoted_task': None}
            candidate, claim_token = _claim_write_promotion(
                uid,
                selected_row,
                account_generation=control.account_generation,
            )
            if candidate.status not in {CandidateStatus.rejected, CandidateStatus.expired}:
                break
        if candidate.status == CandidateStatus.accepted:
            task_id = candidate.result_task_id
            if task_id is None:
                raise HTTPException(status_code=409, detail='Accepted staged Candidate has no task')
            staged_tasks_db.complete_staged_task_promotion(uid, selected_row['id'], task_id)
            action_item = action_items_db.get_action_item(uid, task_id) or {'id': task_id}
            return {'promoted': True, 'reason': None, 'promoted_task': action_item}
        reservation = _begin_write_promotion(
            uid,
            selected_row,
            candidate,
            claim_token,
            account_generation=control.account_generation,
        )
        action_item = staged_tasks_db.promote_staged_task(
            uid,
            task_id=selected_row['id'],
            include_staged_id=True,
            action_item_id=reservation.task_id,
            reservation_kind=reservation.kind,
        )
    else:
        action_item = staged_tasks_db.promote_staged_task(uid, include_staged_id=True)
    if action_item is None:
        return {'promoted': False, 'reason': 'No staged tasks available', 'promoted_task': None}
    staged_id = action_item.pop('_staged_task_id', None)
    if control.workflow_mode == TaskWorkflowMode.write and staged_id:
        row = _staged_row(uid, staged_id)
        if row is not None:
            if not _reconcile_write_sidecar(
                uid,
                row,
                account_generation=control.account_generation,
                status=CandidateStatus.accepted,
                result_task_id=action_item.get('id'),
                reason=row.get('promotion_skipped') or 'legacy_promoted',
                claim_token=claim_token,
            ):
                raise HTTPException(status_code=503, detail='Could not reconcile staged task promotion')
    return {'promoted': True, 'reason': None, 'promoted_task': action_item}


@router.post('/v1/staged-tasks/{task_id}/promote', tags=['staged-tasks'])
def promote_staged_task_by_id(task_id: str, uid: str = Depends(auth.get_current_user_uid)):
    control = task_control_db.get_task_workflow_control(uid)
    if control.workflow_mode == TaskWorkflowMode.read:
        candidate = candidates_db.get_candidate(uid, task_id)
        if (
            candidate is None
            or candidate.account_generation != control.account_generation
            or not _is_staged_compatibility_candidate(candidate)
        ):
            raise HTTPException(status_code=404, detail='Staged task not found or already promoted')
        if candidate.status in {CandidateStatus.rejected, CandidateStatus.expired}:
            raise HTTPException(status_code=404, detail='Staged task not found or already promoted')
        receipt = candidate_service.accept_candidate(uid, task_id, account_generation=control.account_generation)
        return {
            'promoted': True,
            'reason': None,
            'promoted_task': {
                'id': receipt.task_id,
                'candidate_id': candidate.candidate_id,
            },
        }
    existing_row = _staged_row(uid, task_id) if control.workflow_mode == TaskWorkflowMode.write else None
    if existing_row is not None and existing_row.get('completed'):
        action_item = _require_write_promotion_reconciled(
            uid,
            existing_row,
            account_generation=control.account_generation,
        )
        return {'promoted': True, 'reason': None, 'promoted_task': action_item}
    claim_token: str | None = None
    reservation: candidates_db.LegacyPromotionReservation | None = None
    if control.workflow_mode == TaskWorkflowMode.write:
        if existing_row is None:
            raise HTTPException(status_code=404, detail='Staged task not found or already promoted')
        candidate, claim_token = _claim_write_promotion(
            uid,
            existing_row,
            account_generation=control.account_generation,
        )
        if candidate.status in {CandidateStatus.rejected, CandidateStatus.expired}:
            raise HTTPException(status_code=404, detail='Staged task not found or already closed')
        if candidate.status == CandidateStatus.accepted:
            accepted_task_id = candidate.result_task_id
            if accepted_task_id is None:
                raise HTTPException(status_code=409, detail='Accepted staged Candidate has no task')
            staged_tasks_db.complete_staged_task_promotion(uid, task_id, accepted_task_id)
            action_item = action_items_db.get_action_item(uid, accepted_task_id) or {'id': accepted_task_id}
            return {'promoted': True, 'reason': None, 'promoted_task': action_item}
        reservation = _begin_write_promotion(
            uid,
            existing_row,
            candidate,
            claim_token,
            account_generation=control.account_generation,
        )
    action_item = staged_tasks_db.promote_staged_task(
        uid,
        task_id=task_id,
        include_staged_id=True,
        action_item_id=reservation.task_id if reservation is not None else None,
        reservation_kind=reservation.kind if reservation is not None else None,
    )
    if action_item is None:
        raise HTTPException(status_code=404, detail='Staged task not found or already promoted')
    action_item.pop('_staged_task_id', None)
    if control.workflow_mode == TaskWorkflowMode.write:
        row = _staged_row(uid, task_id)
        if row is not None:
            if not _reconcile_write_sidecar(
                uid,
                row,
                account_generation=control.account_generation,
                status=CandidateStatus.accepted,
                result_task_id=action_item.get('id'),
                reason=row.get('promotion_skipped') or 'legacy_promoted',
                claim_token=claim_token,
            ):
                raise HTTPException(status_code=503, detail='Could not reconcile staged task promotion')
    return {'promoted': True, 'reason': None, 'promoted_task': action_item}


@router.post('/v1/staged-tasks/migrate', tags=['staged-tasks'], response_model=StatusResponse)
def migrate_ai_tasks(uid: str = Depends(auth.get_current_user_uid)):
    control = task_control_db.get_task_workflow_control(uid)
    if control.workflow_mode == TaskWorkflowMode.read:
        return {'status': 'canonical read mode; no legacy migration performed'}
    result = staged_tasks_db.migrate_ai_tasks(uid)
    if control.workflow_mode == TaskWorkflowMode.write:
        migrate_staged_tasks(uid, control)
    return {'status': f"moved {result['moved']}, kept {result['kept']}"}


@router.post(
    '/v1/staged-tasks/migrate-conversation-items',
    tags=['staged-tasks'],
    response_model=MigrateConversationItemsResponse,
)
def migrate_conversation_items(uid: str = Depends(auth.get_current_user_uid)):
    control = task_control_db.get_task_workflow_control(uid)
    if control.workflow_mode == TaskWorkflowMode.read:
        return {'status': 'ok', 'migrated': 0, 'deleted': 0}
    result = staged_tasks_db.migrate_conversation_items_to_staged(uid)
    if control.workflow_mode == TaskWorkflowMode.write:
        migrate_staged_tasks(uid, control)
    return {'status': 'ok', 'migrated': result['moved'], 'deleted': 0}
