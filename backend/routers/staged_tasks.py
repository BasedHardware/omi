"""Staged tasks — AI-generated tasks awaiting user promotion to action items."""

from fastapi import APIRouter, Depends, Query
from typing import List
from datetime import datetime
from pydantic import BaseModel, Field

import database.staged_tasks as staged_tasks_db
from utils.other import endpoints as auth

router = APIRouter()


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


@router.post('/v1/staged-tasks', tags=['staged-tasks'])
def create_staged_task(
    request: CreateStagedTaskRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    return staged_tasks_db.create_staged_task(
        uid,
        description=request.description,
        due_at=request.due_at,
        source=request.source,
        priority=request.priority,
        metadata=request.metadata,
        category=request.category,
        relevance_score=request.relevance_score,
    )


@router.get('/v1/staged-tasks', tags=['staged-tasks'])
def get_staged_tasks(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    uid: str = Depends(auth.get_current_user_uid),
):
    fetch_limit = limit + 1
    items = staged_tasks_db.get_staged_tasks(uid, limit=fetch_limit, offset=offset)
    has_more = len(items) > limit
    if has_more:
        items = items[:limit]
    return {'items': items, 'has_more': has_more}


@router.delete('/v1/staged-tasks/{task_id}', tags=['staged-tasks'])
def delete_staged_task(
    task_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    staged_tasks_db.delete_staged_task(uid, task_id)
    return {'status': 'ok'}


@router.patch('/v1/staged-tasks/batch-scores', tags=['staged-tasks'])
def batch_update_staged_scores(
    request: BatchUpdateScoresRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    staged_tasks_db.batch_update_staged_scores(uid, [s.model_dump() for s in request.scores])
    return {'status': 'ok'}


@router.post('/v1/staged-tasks/promote', tags=['staged-tasks'])
def promote_staged_task(uid: str = Depends(auth.get_current_user_uid)):
    action_item = staged_tasks_db.promote_staged_task(uid)
    if action_item is None:
        return {'promoted': False, 'reason': 'No staged tasks available', 'promoted_task': None}
    return {'promoted': True, 'reason': None, 'promoted_task': action_item}


@router.post('/v1/staged-tasks/migrate', tags=['staged-tasks'])
def migrate_ai_tasks(uid: str = Depends(auth.get_current_user_uid)):
    result = staged_tasks_db.migrate_ai_tasks(uid)
    return {'status': f"moved {result['moved']}, kept {result['kept']}"}


@router.post('/v1/staged-tasks/migrate-conversation-items', tags=['staged-tasks'])
def migrate_conversation_items(uid: str = Depends(auth.get_current_user_uid)):
    result = staged_tasks_db.migrate_conversation_items_to_staged(uid)
    return {'status': 'ok', 'migrated': result['moved'], 'deleted': 0}
