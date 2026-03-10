"""Desktop staged tasks endpoints.

Staged tasks are AI-extracted action items ranked by relevance_score.
The top-ranked task can be promoted to action_items (max 5 active AI tasks).
Deduplication prevents promoting tasks whose description already exists in active action_items.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime, timedelta

import database.staged_tasks as staged_tasks_db
from utils.other import endpoints as auth

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Models ---


class CreateStagedTaskRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=2000)
    due_at: Optional[datetime] = None
    source: Optional[str] = None
    priority: Optional[str] = None
    metadata: Optional[str] = None
    category: Optional[str] = None
    relevance_score: Optional[int] = None

    @field_validator('description')
    @classmethod
    def description_not_blank(cls, v):
        if not v.strip():
            raise ValueError('description must not be blank')
        return v


class StagedTaskResponse(BaseModel):
    id: str
    description: str
    completed: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    source: Optional[str] = None
    priority: Optional[str] = None
    metadata: Optional[str] = None
    category: Optional[str] = None
    relevance_score: Optional[int] = None


class StagedTasksListResponse(BaseModel):
    items: List[StagedTaskResponse]
    has_more: bool


class StatusResponse(BaseModel):
    status: str


class ScoreUpdate(BaseModel):
    id: str
    relevance_score: int


class BatchUpdateScoresRequest(BaseModel):
    scores: List[ScoreUpdate] = Field(..., min_length=1, max_length=500)


class PromoteResponse(BaseModel):
    promoted: bool
    reason: Optional[str] = None
    promoted_task: Optional[StagedTaskResponse] = None


# --- Endpoints ---


# --- Desktop staged tasks ---


@router.post('/v1/staged-tasks', response_model=StagedTaskResponse, tags=['staged-tasks'])
def create_staged_task(request: CreateStagedTaskRequest, uid: str = Depends(auth.get_current_user_uid)):
    """Create a new staged task."""
    data = {
        'description': request.description.strip(),
        'source': request.source,
        'priority': request.priority,
        'metadata': request.metadata,
        'category': request.category,
        'relevance_score': request.relevance_score,
    }
    if request.due_at:
        data['due_at'] = request.due_at

    result = staged_tasks_db.create_staged_task(uid, data)
    return StagedTaskResponse(**result)


@router.get('/v1/staged-tasks', response_model=StagedTasksListResponse, tags=['staged-tasks'])
def get_staged_tasks(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    uid: str = Depends(auth.get_current_user_uid),
):
    """List staged tasks ordered by relevance_score ASC (best ranked first)."""
    items, has_more = staged_tasks_db.get_staged_tasks(uid, limit=limit, offset=offset)
    return StagedTasksListResponse(
        items=[StagedTaskResponse(**item) for item in items],
        has_more=has_more,
    )


@router.delete('/v1/staged-tasks/{task_id}', response_model=StatusResponse, tags=['staged-tasks'])
def delete_staged_task(task_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Hard-delete a staged task. Idempotent — returns ok even if not found (matches Rust)."""
    staged_tasks_db.delete_staged_task(uid, task_id)
    return StatusResponse(status='ok')


@router.patch('/v1/staged-tasks/batch-scores', response_model=StatusResponse, tags=['staged-tasks'])
def batch_update_scores(request: BatchUpdateScoresRequest, uid: str = Depends(auth.get_current_user_uid)):
    """Batch update relevance scores for staged tasks."""
    scores = [{'id': s.id, 'relevance_score': s.relevance_score} for s in request.scores]
    staged_tasks_db.batch_update_scores(uid, scores)
    return StatusResponse(status='ok')


@router.post('/v1/staged-tasks/promote', response_model=PromoteResponse, tags=['staged-tasks'])
def promote_staged_task(uid: str = Depends(auth.get_current_user_uid)):
    """Promote the top-ranked staged task to action_items.

    Rules:
    - Max 5 active AI tasks (from_staged=true, not completed, not deleted)
    - Skips duplicates (case-insensitive description match, strips [screen] prefix/suffix)
    - Deletes duplicate staged tasks found during scan
    - Hard-deletes the promoted task from staged_tasks
    """
    # Step 1: Check active AI task count
    active_items = staged_tasks_db.get_active_ai_action_items(uid)
    if len(active_items) >= 5:
        return PromoteResponse(
            promoted=False,
            reason=f'Already have {len(active_items)} active AI tasks (max 5)',
        )

    # Build dedup set from existing descriptions
    existing_descriptions = set()
    for item in active_items:
        desc = item.get('description', '')
        normalized = desc.strip().removeprefix('[screen] ').removesuffix(' [screen]').lower()
        existing_descriptions.add(normalized)

    # Step 2: Get top-ranked staged tasks (batch of 20 for dedup scanning)
    staged_items, _ = staged_tasks_db.get_staged_tasks(uid, limit=20, offset=0)
    if not staged_items:
        return PromoteResponse(promoted=False, reason='No staged tasks available')

    # Step 3: Find first non-duplicate, collecting duplicates to delete
    selected_task = None
    seen_descriptions = set()
    duplicate_ids = []

    for task in staged_items:
        normalized = task.get('description', '').strip().removeprefix('[screen] ').removesuffix(' [screen]').lower()
        if normalized in existing_descriptions or normalized in seen_descriptions:
            duplicate_ids.append(task['id'])
            continue
        seen_descriptions.add(normalized)
        if selected_task is None:
            selected_task = task

    # Clean up duplicates
    if duplicate_ids:
        staged_tasks_db.delete_staged_tasks_batch(uid, duplicate_ids)
        logger.info(f'Cleaned up {len(duplicate_ids)} duplicate staged tasks for user {uid}')

    if selected_task is None:
        return PromoteResponse(promoted=False, reason='All candidate staged tasks are duplicates')

    # Step 4: Promote to action_items
    promoted_item = staged_tasks_db.promote_staged_task(uid, selected_task)

    # Step 5: Hard-delete from staged_tasks
    staged_tasks_db.delete_staged_task(uid, selected_task['id'])

    logger.info(f'Promoted staged task {selected_task["id"]} -> action item {promoted_item["id"]} for user {uid}')

    return PromoteResponse(promoted=True, promoted_task=StagedTaskResponse(**promoted_item))


# --- Desktop daily scores ---


class DailyScoreResponse(BaseModel):
    score: float
    completed_tasks: int
    total_tasks: int
    date: str


class ScoreData(BaseModel):
    score: float
    completed_tasks: int
    total_tasks: int


class ScoresResponse(BaseModel):
    daily: ScoreData
    weekly: ScoreData
    overall: ScoreData
    default_tab: str
    date: str


@router.get('/v1/daily-score', response_model=DailyScoreResponse, tags=['scores'])
def get_daily_score(
    date: Optional[str] = Query(default=None, description='Date in YYYY-MM-DD format'),
    uid: str = Depends(auth.get_current_user_uid),
):
    """Calculate daily score from action items due today (legacy endpoint)."""
    if date:
        try:
            parsed = datetime.strptime(date, '%Y-%m-%d').date()
        except ValueError:
            raise HTTPException(status_code=400, detail='Invalid date format, use YYYY-MM-DD')
    else:
        parsed = datetime.now().date()

    date_str = parsed.strftime('%Y-%m-%d')
    due_start = f'{date_str}T00:00:00Z'
    due_end = f'{date_str}T23:59:59.999Z'

    completed, total = staged_tasks_db.get_action_items_for_daily_score(uid, due_start, due_end)
    score = (completed / total * 100.0) if total > 0 else 0.0

    return DailyScoreResponse(score=score, completed_tasks=completed, total_tasks=total, date=date_str)


@router.get('/v1/scores', response_model=ScoresResponse, tags=['scores'])
def get_scores(
    date: Optional[str] = Query(default=None, description='Date in YYYY-MM-DD format'),
    uid: str = Depends(auth.get_current_user_uid),
):
    """Get daily, weekly, and overall scores with default tab selection."""
    if date:
        try:
            parsed = datetime.strptime(date, '%Y-%m-%d').date()
        except ValueError:
            raise HTTPException(status_code=400, detail='Invalid date format, use YYYY-MM-DD')
    else:
        parsed = datetime.now().date()

    date_str = parsed.strftime('%Y-%m-%d')

    # Daily: tasks due today
    today_start = f'{date_str}T00:00:00Z'
    today_end = f'{date_str}T23:59:59.999Z'
    daily_completed, daily_total = staged_tasks_db.get_action_items_for_daily_score(uid, today_start, today_end)

    # Weekly: last 7 days
    week_ago = parsed - timedelta(days=7)
    week_start = f'{week_ago.strftime("%Y-%m-%d")}T00:00:00Z'
    weekly_completed, weekly_total = staged_tasks_db.get_action_items_for_weekly_score(uid, week_start, today_end)

    # Overall: all time
    overall_completed, overall_total = staged_tasks_db.get_action_items_for_overall_score(uid)

    def calc_score(completed, total):
        return (completed / total * 100.0) if total > 0 else 0.0

    daily = ScoreData(
        score=calc_score(daily_completed, daily_total), completed_tasks=daily_completed, total_tasks=daily_total
    )
    weekly = ScoreData(
        score=calc_score(weekly_completed, weekly_total), completed_tasks=weekly_completed, total_tasks=weekly_total
    )
    overall = ScoreData(
        score=calc_score(overall_completed, overall_total), completed_tasks=overall_completed, total_tasks=overall_total
    )

    # Default tab: highest score, prefer daily if tied
    if daily.total_tasks > 0 and daily.score >= weekly.score and daily.score >= overall.score:
        default_tab = 'daily'
    elif weekly.score >= overall.score:
        default_tab = 'weekly'
    else:
        default_tab = 'overall'

    return ScoresResponse(daily=daily, weekly=weekly, overall=overall, default_tab=default_tab, date=date_str)
