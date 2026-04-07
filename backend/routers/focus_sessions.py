"""Focus sessions — focus/distraction tracking and statistics."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

import database.focus_sessions as focus_sessions_db
from utils.other import endpoints as auth

router = APIRouter()


# ============================================================================
# MODELS
# ============================================================================


class CreateFocusSessionRequest(BaseModel):
    status: str = Field(..., pattern=r'^(focused|distracted)$')
    app_or_site: str = Field(..., min_length=1, max_length=500)
    description: str = Field(..., min_length=1, max_length=5000)
    message: str | None = Field(None, max_length=5000)
    duration_seconds: int | None = Field(None, ge=0, le=86400)


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.post('/v1/focus-sessions', tags=['focus-sessions'])
def create_focus_session(
    request: CreateFocusSessionRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    return focus_sessions_db.create_focus_session(
        uid,
        status=request.status,
        app_or_site=request.app_or_site,
        description=request.description,
        message=request.message,
        duration_seconds=request.duration_seconds,
    )


@router.get('/v1/focus-sessions', tags=['focus-sessions'])
def get_focus_sessions(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    date: str | None = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    uid: str = Depends(auth.get_current_user_uid),
):
    return focus_sessions_db.get_focus_sessions(uid, limit=limit, offset=offset, date=date)


@router.delete('/v1/focus-sessions/{session_id}', tags=['focus-sessions'])
def delete_focus_session(
    session_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    focus_sessions_db.delete_focus_session(uid, session_id)
    return {'status': 'ok'}


@router.get('/v1/focus-stats', tags=['focus-sessions'])
def get_focus_stats(
    date: str | None = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    uid: str = Depends(auth.get_current_user_uid),
):
    return focus_sessions_db.get_focus_stats(uid, date=date)
