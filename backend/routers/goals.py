"""
Goal tracking API endpoints.
Handles user goals with AI-powered suggestions and advice.
"""

import uuid
from typing import Annotated, Optional, List

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from database import goals as goals_db
from utils.other import endpoints as auth
from utils.request_validation import HistoryDays
from utils.goals_response import normalize_goal_history_entry, normalize_goal_response
from utils.llm.goals import (
    suggest_goal as suggest_goal_llm,
    get_goal_advice as get_goal_advice_llm,
    extract_and_update_goal_progress,
)
from models.goal import (
    AdviceResponse,
    GoalCreate,
    GoalDeleteResponse,
    GoalFocusRequest,
    GoalHistoryEntryResponse,
    GoalLifecycleRequest,
    GoalProgressEvent,
    GoalProgressEventCreate,
    GoalResponse,
    GoalSuggestionResponse,
    GoalUpdate,
)
from models.workstream import GoalDetailProjection
import database.workstreams as workstreams_db

router = APIRouter()
IdempotencyHeader = Annotated[str, Header(alias='Idempotency-Key', min_length=1, max_length=256)]
AccountGenerationHeader = Annotated[int, Header(alias='X-Account-Generation', ge=0)]


@router.get('/v1/goals', tags=['goals'], response_model=Optional[GoalResponse])
def get_current_goal(uid: str = Depends(auth.get_current_user_uid)) -> Optional[dict]:
    """Get the current active goal for the user (backward compatibility)."""
    goal = goals_db.get_user_goal(uid)
    return normalize_goal_response(goal) if goal else None


@router.get('/v1/goals/all', tags=['goals'], response_model=List[GoalResponse])
def get_all_goals(
    include_ended: bool = Query(False),
    uid: str = Depends(auth.get_current_user_uid),
) -> List[dict]:
    """Get all active goals; canonical clients opt into ended history."""
    goals = goals_db.get_all_goals(uid, include_inactive=include_ended)

    return [normalize_goal_response(goal) for goal in goals]


@router.post('/v1/goals', tags=['goals'], response_model=GoalResponse)
def create_goal(goal: GoalCreate, uid: str = Depends(auth.get_current_user_uid)) -> dict:
    """Create a durable goal without changing any other goal's focus or lifecycle."""
    goal_data = goal.model_dump(mode='python', exclude_none=True)
    goal_data['id'] = f"goal_{uuid.uuid4().hex[:12]}"

    try:
        created_goal = goals_db.create_goal(uid, goal_data)
    except goals_db.GoalConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return normalize_goal_response(created_goal)


@router.post('/v1/goals/canonical', tags=['goals'], response_model=GoalResponse)
def create_canonical_goal(
    goal: GoalCreate,
    idempotency_key: IdempotencyHeader,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(auth.get_current_user_uid),
) -> dict:
    """Create a generation-scoped canonical goal with safe retry semantics."""

    try:
        created_goal = goals_db.create_goal_idempotent(
            uid,
            goal.model_dump(mode='python', exclude_none=True),
            idempotency_key=idempotency_key,
            account_generation=account_generation,
        )
    except goals_db.GoalStoreError as exc:
        _raise_goal_store_error(exc)
        raise AssertionError('unreachable')
    return normalize_goal_response(created_goal)


def _raise_goal_store_error(exc: Exception) -> None:
    if isinstance(exc, goals_db.GoalNotFoundError):
        raise HTTPException(status_code=404, detail='Goal not found') from exc
    if isinstance(exc, goals_db.GoalConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise exc


@router.post('/v1/goals/{goal_id}/focus', tags=['goals'], response_model=GoalResponse)
def focus_goal(
    goal_id: str,
    request: GoalFocusRequest,
    idempotency_key: IdempotencyHeader,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(auth.get_current_user_uid),
) -> dict:
    try:
        goal = goals_db.focus_goal(
            uid,
            goal_id,
            idempotency_key=idempotency_key,
            account_generation=account_generation,
            replacement_goal_id=request.replacement_goal_id,
            focus_rank=request.focus_rank,
        )
    except goals_db.GoalStoreError as exc:
        _raise_goal_store_error(exc)
        raise AssertionError('unreachable')
    return normalize_goal_response(goal)


@router.delete('/v1/goals/{goal_id}/focus', tags=['goals'], response_model=GoalResponse)
def unfocus_goal(
    goal_id: str,
    idempotency_key: IdempotencyHeader,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(auth.get_current_user_uid),
) -> dict:
    try:
        return normalize_goal_response(
            goals_db.unfocus_goal(
                uid,
                goal_id,
                idempotency_key=idempotency_key,
                account_generation=account_generation,
            )
        )
    except goals_db.GoalStoreError as exc:
        _raise_goal_store_error(exc)
        raise AssertionError('unreachable')


@router.post('/v1/goals/{goal_id}/lifecycle', tags=['goals'], response_model=GoalResponse)
def transition_goal_lifecycle(
    goal_id: str,
    request: GoalLifecycleRequest,
    idempotency_key: IdempotencyHeader,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(auth.get_current_user_uid),
) -> dict:
    try:
        goal = goals_db.transition_goal_lifecycle(
            uid,
            goal_id,
            status=request.status,
            relationship_disposition=request.relationship_disposition,
            idempotency_key=idempotency_key,
            account_generation=account_generation,
        )
    except goals_db.GoalStoreError as exc:
        _raise_goal_store_error(exc)
        raise AssertionError('unreachable')
    return normalize_goal_response(goal)


@router.get('/v1/goals/{goal_id}/detail', tags=['goals'], response_model=GoalDetailProjection)
def get_goal_detail(goal_id: str, uid: str = Depends(auth.get_current_user_uid)) -> GoalDetailProjection:
    try:
        return workstreams_db.get_goal_detail(uid, goal_id)
    except workstreams_db.WorkstreamNotFoundError as exc:
        raise HTTPException(status_code=404, detail='Goal not found') from exc


@router.post('/v1/goals/{goal_id}/progress-events', tags=['goals'], response_model=GoalProgressEvent)
def append_goal_progress_event(
    goal_id: str,
    request: GoalProgressEventCreate,
    idempotency_key: IdempotencyHeader,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(auth.get_current_user_uid),
) -> GoalProgressEvent:
    try:
        return goals_db.append_goal_progress_event(
            uid,
            goal_id,
            request,
            idempotency_key=idempotency_key,
            account_generation=account_generation,
        )
    except goals_db.GoalStoreError as exc:
        _raise_goal_store_error(exc)
        raise AssertionError('unreachable')


@router.get('/v1/goals/{goal_id}/progress-events', tags=['goals'], response_model=list[GoalProgressEvent])
def list_goal_progress_events(
    goal_id: str,
    limit: int = Query(100, ge=1, le=500),
    uid: str = Depends(auth.get_current_user_uid),
) -> list[GoalProgressEvent]:
    return goals_db.list_goal_progress_events(uid, goal_id, limit=limit)


@router.patch('/v1/goals/{goal_id}', tags=['goals'], response_model=GoalResponse)
def update_goal(goal_id: str, updates: GoalUpdate, uid: str = Depends(auth.get_current_user_uid)) -> dict:
    """Update an existing goal."""
    update_data = updates.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(status_code=400, detail="No updates provided")

    updated_goal = goals_db.update_goal(uid, goal_id, update_data)

    if not updated_goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    return normalize_goal_response(updated_goal)


@router.patch('/v1/goals/{goal_id}/progress', tags=['goals'], response_model=GoalResponse)
def update_goal_progress(
    goal_id: str,
    current_value: float = Query(..., description="New progress value"),
    uid: str = Depends(auth.get_current_user_uid),
) -> dict:
    """Update the progress value of a goal."""
    updated_goal = goals_db.update_goal_progress(uid, goal_id, current_value)

    if not updated_goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    return normalize_goal_response(updated_goal)


@router.get('/v1/goals/{goal_id}/history', tags=['goals'], response_model=List[GoalHistoryEntryResponse])
def get_goal_history(goal_id: str, days: HistoryDays = 30, uid: str = Depends(auth.get_current_user_uid)) -> List[dict]:
    """Get progress history for a goal."""
    history = goals_db.get_goal_history(uid, goal_id, days)

    return [normalize_goal_history_entry(entry) for entry in history]


@router.delete('/v1/goals/{goal_id}', tags=['goals'], response_model=GoalDeleteResponse, deprecated=True)
def delete_goal(goal_id: str, uid: str = Depends(auth.get_current_user_uid)) -> dict:
    """Released compatibility route: soft-abandon and retain links. Use the lifecycle route for explicit disposition."""
    success = goals_db.delete_goal(uid, goal_id)

    if not success:
        raise HTTPException(status_code=404, detail="Goal not found")

    return {"success": True, "deleted_id": goal_id}


@router.get('/v1/goals/suggest', tags=['goals'], response_model=GoalSuggestionResponse)
def suggest_goal(uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "goals:suggest"))) -> dict:
    """Generate an AI-suggested goal based on user's memories and conversations."""
    return suggest_goal_llm(uid)


@router.get('/v1/goals/{goal_id}/advice', tags=['goals'], response_model=AdviceResponse)
def get_goal_advice(
    goal_id: str, uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "goals:advice"))
) -> dict:
    """Get AI-generated actionable advice for achieving a goal."""
    try:
        advice = get_goal_advice_llm(uid, goal_id)
        return {'advice': advice}
    except ValueError:
        raise HTTPException(status_code=404, detail="Goal not found")


@router.get('/v1/goals/advice', tags=['goals'], response_model=AdviceResponse)
def get_current_goal_advice(
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "goals:advice"))
) -> dict:
    """Get AI-generated advice for the current active goal."""
    goal = goals_db.get_user_goal(uid)
    if not goal:
        return {'advice': 'Set a goal to get personalized advice!'}

    return get_goal_advice(goal['id'], uid)


class ProgressExtractRequest(BaseModel):
    """Request to extract progress from text."""

    text: str


class ProgressExtractUpdateResponse(BaseModel):
    goal_id: str | None = None
    goal_title: str | None = None
    previous_value: float | int | str | None = None
    new_value: float | int | str | None = None
    reasoning: str = ''


class ProgressExtractResponse(BaseModel):
    updated: bool
    reason: str | None = None
    updates: List[ProgressExtractUpdateResponse] = Field(default_factory=list)


@router.post('/v1/goals/extract-progress', tags=['goals'], response_model=ProgressExtractResponse)
def extract_and_update_progress(
    request: ProgressExtractRequest,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "goals:extract")),
) -> dict:
    """
    Extract goal progress from conversation/chat text and update if found.
    Uses LLM to understand context and extract numeric progress.
    """
    result = extract_and_update_goal_progress(uid, request.text)
    if result is None:
        return {'updated': False, 'reason': 'No active goal'}

    if result.get('status') == 'updated':
        updates = result.get('updates', [])
        return {
            'updated': True,
            'updates': [
                {
                    'goal_id': u.get('goal_id'),
                    'goal_title': u.get('goal_title'),
                    'previous_value': u.get('old_value'),
                    'new_value': u.get('new_value'),
                    'reasoning': u.get('reasoning', ''),
                }
                for u in updates
            ],
        }

    return {'updated': False, 'reason': result.get('message', 'No progress found in text')}


# Declared after the static /v1/goals/* routes (/all, /suggest, /advice, /extract-progress) so
# those match first and are not captured as a goal_id.
@router.get('/v1/goals/{goal_id}', tags=['goals'], response_model=GoalResponse)
def get_goal_by_id(goal_id: str, uid: str = Depends(auth.get_current_user_uid)) -> dict:
    """Fetch a single goal by id.

    The list routes cap how many goals are returned, and update/delete/progress/history/advice
    already address a goal by id, so this exposes the matching read for one goal (404 if it does
    not exist or belongs to another user).
    """
    goal = goals_db.get_goal(uid, goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return normalize_goal_response(goal)
