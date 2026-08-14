"""Released staged-task compatibility routes over universal Candidates.

``users/{uid}/staged_tasks`` is historical storage. Reads project its active
rows beside pending Candidates without mutating either store. New creates and
all task decisions use Candidate authority; an explicit mutation of a
historical row materializes only that row and retires it after the canonical
decision succeeds.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import database.action_items as action_items_db
import database.candidates as candidates_db
import database.staged_tasks as staged_tasks_db
import database.task_intelligence_control as task_control_db
from models.candidate import CandidateRecord, CandidateStatus
from models.shared import StatusResponse
from models.staged_task import (
    MigrateConversationItemsResponse,
    PromoteStagedTaskResponse,
    RestoreLegacyConversationItemsResponse,
    StagedTask,
    StagedTaskListResponse,
)
from utils.other import endpoints as auth
from utils.task_intelligence import candidate_service
from utils.task_intelligence.staged_migration import proposal_from_legacy_staged

router = APIRouter()

_LEGACY_EVIDENCE_PREFIX = 'legacy-staged-'
_MISSING_TIMESTAMP = datetime(1970, 1, 1, tzinfo=timezone.utc)
_CANDIDATE_PAGE_SIZE = 500


def _control(uid: str):
    """Read the account-generation fence; workflow mode is no longer entitlement."""

    return task_control_db.get_task_workflow_control(uid)


def _candidate_as_staged(candidate: CandidateRecord) -> dict:
    task_change = candidate.task_change
    compatibility = candidate.compatibility
    return {
        'id': candidate.candidate_id,
        'description': getattr(task_change, 'description', None) or 'Suggested task',
        'completed': candidate.status != CandidateStatus.pending,
        'created_at': candidate.created_at,
        'updated_at': candidate.resolved_at or candidate.created_at,
        'due_at': getattr(task_change, 'due_at', None),
        'source': candidate.source_surface,
        'priority': getattr(task_change, 'priority', None),
        'metadata': compatibility.metadata if compatibility is not None else None,
        'category': compatibility.category if compatibility is not None else None,
        'relevance_score': compatibility.relevance_score if compatibility is not None else None,
    }


def _legacy_as_staged(row: dict) -> dict:
    created_at = row.get('created_at') or row.get('updated_at') or _MISSING_TIMESTAMP
    updated_at = row.get('updated_at') or created_at
    return {
        'id': str(row['id']),
        'description': row.get('description') or 'Suggested task',
        'completed': False,
        'created_at': created_at,
        'updated_at': updated_at,
        'due_at': row.get('due_at'),
        'source': row.get('source'),
        'priority': row.get('priority'),
        'metadata': row.get('metadata'),
        'category': row.get('category'),
        'relevance_score': row.get('relevance_score'),
    }


def _candidate_legacy_row_ids(candidate: CandidateRecord) -> set[str]:
    row_ids: set[str] = set()
    for evidence in candidate.evidence_refs:
        evidence_id = getattr(evidence, 'id', None)
        kind = getattr(getattr(evidence, 'kind', None), 'value', getattr(evidence, 'kind', None))
        if kind == 'external' and isinstance(evidence_id, str) and evidence_id.startswith(_LEGACY_EVIDENCE_PREFIX):
            row_ids.add(evidence_id[len(_LEGACY_EVIDENCE_PREFIX) :])
    return row_ids


def _is_staged_compatibility_candidate(candidate: CandidateRecord) -> bool:
    return (
        candidate.subject_kind.value == 'task'
        and candidate.proposed_action.value == 'create'
        and (candidate.source_surface == 'legacy_staged' or bool(_candidate_legacy_row_ids(candidate)))
    )


def _all_staged_compatibility_candidates(uid: str, *, account_generation: int) -> list[CandidateRecord]:
    records: list[CandidateRecord] = []
    cursor = None
    while True:
        page, raw_page_size, cursor = candidates_db.list_candidates_compatibility_page(
            uid,
            account_generation=account_generation,
            limit=_CANDIDATE_PAGE_SIZE,
            cursor=cursor,
        )
        records.extend(candidate for candidate in page if _is_staged_compatibility_candidate(candidate))
        if raw_page_size < _CANDIDATE_PAGE_SIZE:
            return records


def _active_historical_rows(uid: str) -> list[dict]:
    return [
        row
        for row in staged_tasks_db.get_active_staged_tasks_for_compatibility(uid)
        if row.get('id') and not row.get('completed')
    ]


def _staged_row(uid: str, staged_id: str) -> dict | None:
    return staged_tasks_db.get_staged_task_for_compatibility(uid, staged_id)


def _projected_timestamp(item: dict) -> float:
    value = item.get('created_at') or item.get('updated_at')
    if not isinstance(value, datetime):
        return _MISSING_TIMESTAMP.timestamp()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def _staged_sort_key(item: dict) -> tuple:
    score = item.get('relevance_score')
    has_score = isinstance(score, int) and not isinstance(score, bool)
    return (
        0 if has_score else 1,
        score if has_score else 0,
        -_projected_timestamp(item),
        str(item.get('id', '')),
    )


def _merged_staged_projection(uid: str, *, account_generation: int) -> list[dict]:
    """Pure read projection with canonical precedence and deterministic order."""

    candidates = _all_staged_compatibility_candidates(uid, account_generation=account_generation)
    represented_legacy_ids: set[str] = set()
    candidate_items: list[dict] = []
    for candidate in candidates:
        represented_legacy_ids.update(_candidate_legacy_row_ids(candidate))
        if candidate.status == CandidateStatus.pending:
            candidate_items.append(_candidate_as_staged(candidate))

    legacy_items = [
        _legacy_as_staged(row) for row in _active_historical_rows(uid) if str(row['id']) not in represented_legacy_ids
    ]
    by_id: dict[str, dict] = {}
    for item in [*legacy_items, *candidate_items]:
        # Candidate items are appended last and are authoritative on the
        # vanishingly unlikely public-ID collision.
        by_id[str(item['id'])] = item
    return sorted(by_id.values(), key=_staged_sort_key)


def _create_candidate_from_staged_row(uid: str, row: dict, *, account_generation: int) -> CandidateRecord:
    return candidate_service.create_candidate(
        uid,
        proposal_from_legacy_staged(row),
        idempotency_key=f'legacy-staged:{row["id"]}',
        account_generation=account_generation,
    )


def _materialize_historical_candidate(uid: str, row: dict, *, account_generation: int) -> CandidateRecord:
    try:
        return _create_candidate_from_staged_row(uid, row, account_generation=account_generation)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail='Staged task cannot be represented canonically') from exc
    except candidates_db.CandidateGenerationMismatchError as exc:
        raise HTTPException(status_code=409, detail='Task account generation changed') from exc
    except candidates_db.CandidateStoreError as exc:
        raise HTTPException(status_code=409, detail='Staged task Candidate cannot be materialized') from exc


def _candidate_for_public_id(uid: str, task_id: str, *, account_generation: int) -> CandidateRecord | None:
    candidate = candidates_db.get_candidate(uid, task_id)
    if (
        candidate is None
        or candidate.account_generation != account_generation
        or not _is_staged_compatibility_candidate(candidate)
    ):
        return None
    return candidate


def _reject_pending_candidate(uid: str, candidate: CandidateRecord, *, account_generation: int, reason: str) -> None:
    if candidate.status != CandidateStatus.pending:
        return
    try:
        candidate_service.reject_candidate(
            uid,
            candidate.candidate_id,
            reason=reason,
            account_generation=account_generation,
        )
    except candidates_db.CandidateNotFoundError:
        return
    except candidates_db.CandidateGenerationMismatchError as exc:
        raise HTTPException(status_code=409, detail='Task account generation changed') from exc
    except candidates_db.CandidateStoreError as exc:
        raise HTTPException(status_code=409, detail='Staged task Candidate cannot be rejected') from exc


def _retire_historical_row(uid: str, row_id: str) -> None:
    # Cleanup is deliberately after the canonical terminal decision. If this
    # delete fails, the Candidate evidence suppresses the row on reads and a
    # retry can finish cleanup without recreating or re-resolving the task.
    staged_tasks_db.delete_staged_task(uid, row_id)


def _retire_candidate_historical_rows(uid: str, candidate: CandidateRecord) -> None:
    for row_id in sorted(_candidate_legacy_row_ids(candidate)):
        _retire_historical_row(uid, row_id)


def _accept_candidate(uid: str, candidate: CandidateRecord, *, account_generation: int) -> dict:
    if candidate.status in {CandidateStatus.rejected, CandidateStatus.expired}:
        raise HTTPException(status_code=404, detail='Staged task not found or already closed')
    if candidate.status == CandidateStatus.accepted:
        task_id = candidate.result_task_id
    else:
        try:
            receipt = candidate_service.accept_candidate(
                uid,
                candidate.candidate_id,
                account_generation=account_generation,
            )
        except candidates_db.CandidateNotFoundError as exc:
            raise HTTPException(status_code=404, detail='Staged task not found or already promoted') from exc
        except candidates_db.CandidateGenerationMismatchError as exc:
            raise HTTPException(status_code=409, detail='Task account generation changed') from exc
        except candidates_db.CandidateStoreError as exc:
            raise HTTPException(status_code=409, detail='Staged task Candidate cannot be promoted') from exc
        task_id = receipt.task_id
    if not task_id:
        raise HTTPException(status_code=409, detail='Accepted staged Candidate has no task')
    return action_items_db.get_action_item(uid, task_id) or {
        'id': task_id,
        'candidate_id': candidate.candidate_id,
    }


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


@router.post('/v1/staged-tasks', tags=['staged-tasks'], response_model=StagedTask)
def create_staged_task(request: CreateStagedTaskRequest, uid: str = Depends(auth.get_current_user_uid)):
    control = _control(uid)
    identity_payload = {
        'description': request.description.strip(),
        'due_at': request.due_at.isoformat() if request.due_at else None,
        'priority': request.priority,
        'source': request.source,
        'metadata': request.metadata,
        'category': request.category,
        'relevance_score': request.relevance_score,
    }
    digest = hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    ).hexdigest()[:24]
    synthetic_row = {
        'id': f'compat-{digest}',
        'description': request.description,
        'due_at': request.due_at,
        'source': request.source,
        'priority': request.priority,
        'metadata': request.metadata,
        'category': request.category,
        'relevance_score': request.relevance_score,
    }
    candidate = _materialize_historical_candidate(
        uid,
        synthetic_row,
        account_generation=control.account_generation,
    )
    return _candidate_as_staged(candidate)


@router.get('/v1/staged-tasks', tags=['staged-tasks'], response_model=StagedTaskListResponse)
def get_staged_tasks(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    uid: str = Depends(auth.get_current_user_uid),
):
    control = _control(uid)
    items = _merged_staged_projection(uid, account_generation=control.account_generation)
    return {'items': items[offset : offset + limit], 'has_more': len(items) > offset + limit}


@router.delete('/v1/staged-tasks', tags=['staged-tasks'])
def clear_staged_tasks(uid: str = Depends(auth.get_current_user_uid)):
    control = _control(uid)
    candidates = _all_staged_compatibility_candidates(uid, account_generation=control.account_generation)
    candidate_by_legacy_id: dict[str, CandidateRecord] = {}
    for candidate in candidates:
        for row_id in _candidate_legacy_row_ids(candidate):
            candidate_by_legacy_id[row_id] = candidate

    deleted_count = 0
    counted_candidate_ids: set[str] = set()
    for candidate in candidates:
        if candidate.status != CandidateStatus.pending:
            continue
        _reject_pending_candidate(
            uid,
            candidate,
            account_generation=control.account_generation,
            reason='legacy_clear',
        )
        counted_candidate_ids.add(candidate.candidate_id)
        deleted_count += 1

    for row in _active_historical_rows(uid):
        row_id = str(row['id'])
        candidate = candidate_by_legacy_id.get(row_id)
        if candidate is None:
            candidate = _materialize_historical_candidate(
                uid,
                row,
                account_generation=control.account_generation,
            )
            _reject_pending_candidate(
                uid,
                candidate,
                account_generation=control.account_generation,
                reason='legacy_clear',
            )
        _retire_historical_row(uid, row_id)
        if candidate.candidate_id not in counted_candidate_ids:
            counted_candidate_ids.add(candidate.candidate_id)
            deleted_count += 1
    return {'status': 'ok', 'deleted_count': deleted_count}


@router.delete('/v1/staged-tasks/{task_id}', tags=['staged-tasks'], response_model=StatusResponse)
def delete_staged_task(task_id: str, uid: str = Depends(auth.get_current_user_uid)):
    control = _control(uid)
    candidate = _candidate_for_public_id(uid, task_id, account_generation=control.account_generation)
    if candidate is not None:
        _reject_pending_candidate(
            uid,
            candidate,
            account_generation=control.account_generation,
            reason='legacy_delete',
        )
        _retire_candidate_historical_rows(uid, candidate)
        return {'status': 'ok'}

    row = _staged_row(uid, task_id)
    if row is None:
        return {'status': 'ok'}
    candidate = _materialize_historical_candidate(uid, row, account_generation=control.account_generation)
    _reject_pending_candidate(
        uid,
        candidate,
        account_generation=control.account_generation,
        reason='legacy_delete',
    )
    _retire_historical_row(uid, task_id)
    return {'status': 'ok'}


@router.patch('/v1/staged-tasks/batch-scores', tags=['staged-tasks'], response_model=StatusResponse)
def batch_update_staged_scores(
    request: BatchUpdateScoresRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    control = _control(uid)
    for score in request.scores:
        candidate = _candidate_for_public_id(uid, score.id, account_generation=control.account_generation)
        if candidate is None:
            row = _staged_row(uid, score.id)
            if row is None:
                continue
            candidate = _materialize_historical_candidate(uid, row, account_generation=control.account_generation)
        try:
            candidates_db.update_candidate_compatibility_score(
                uid,
                candidate.candidate_id,
                relevance_score=score.relevance_score,
                account_generation=control.account_generation,
            )
        except candidates_db.CandidateNotFoundError:
            # A concurrent resolution may close and clean up the Candidate;
            # the endpoint remains idempotent for the released client.
            continue
        except candidates_db.CandidateConflictError:
            # Accepted, rejected, expired, or non-staged Candidates are
            # immutable through the released staged-score compatibility API.
            continue
        except candidates_db.CandidateGenerationMismatchError as exc:
            raise HTTPException(status_code=409, detail='Task account generation changed') from exc
    return {'status': 'ok'}


@router.post('/v1/staged-tasks/promote', tags=['staged-tasks'], response_model=PromoteStagedTaskResponse)
def promote_staged_task(uid: str = Depends(auth.get_current_user_uid)):
    control = _control(uid)
    items = _merged_staged_projection(uid, account_generation=control.account_generation)
    if not items:
        return {'promoted': False, 'reason': 'No staged tasks available', 'promoted_task': None}
    return promote_staged_task_by_id(items[0]['id'], uid=uid)


@router.post('/v1/staged-tasks/{task_id}/promote', tags=['staged-tasks'])
def promote_staged_task_by_id(task_id: str, uid: str = Depends(auth.get_current_user_uid)):
    control = _control(uid)
    candidate = _candidate_for_public_id(uid, task_id, account_generation=control.account_generation)
    historical_row: dict | None = None
    if candidate is None:
        historical_row = _staged_row(uid, task_id)
        if historical_row is None:
            raise HTTPException(status_code=404, detail='Staged task not found or already promoted')
        candidate = _materialize_historical_candidate(
            uid,
            historical_row,
            account_generation=control.account_generation,
        )

    action_item = _accept_candidate(uid, candidate, account_generation=control.account_generation)
    if historical_row is not None:
        _retire_historical_row(uid, str(historical_row['id']))
    else:
        _retire_candidate_historical_rows(uid, candidate)
    return {'promoted': True, 'reason': None, 'promoted_task': action_item}


@router.post('/v1/staged-tasks/migrate', tags=['staged-tasks'], response_model=StatusResponse)
def migrate_ai_tasks(uid: str = Depends(auth.get_current_user_uid)):
    del uid
    return {'status': 'legacy task migration retired; no action taken'}


@router.post(
    '/v1/staged-tasks/migrate-conversation-items',
    tags=['staged-tasks'],
    response_model=MigrateConversationItemsResponse,
)
def migrate_conversation_items(
    limit: int = Query(default=50, ge=1, le=100, deprecated=True),
    cursor: str | None = Query(default=None, min_length=1, max_length=256, deprecated=True),
    uid: str = Depends(auth.get_current_user_uid),
):
    # Released callers retain an acknowledged wire shape, but convergence never
    # turns this endpoint into an implicit account-wide migration.
    del limit, cursor, uid
    return {
        'status': 'ok',
        'migrated': 0,
        'deleted': 0,
        'restored': 0,
        'skipped_existing': 0,
        'has_more': False,
        'next_cursor': None,
    }


@router.post(
    '/v1/action-items/restore-legacy-conversation-items',
    tags=['action-items'],
    response_model=RestoreLegacyConversationItemsResponse,
)
def restore_legacy_conversation_items(
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, min_length=1, max_length=256),
    uid: str = Depends(auth.get_current_user_uid),
):
    # The old recovery moved rows directly into action_items and bypassed
    # Candidate authority. Keep the endpoint decodable, permanently inert.
    del limit, cursor, uid
    return {'status': 'ok', 'restored': 0, 'skipped_existing': 0, 'has_more': False, 'next_cursor': None}
