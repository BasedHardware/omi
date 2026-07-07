"""Focus sessions — focus/distraction tracking and statistics."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from models.focus_session import FocusSession, FocusStats
from models.shared import StatusResponse
import database.focus_sessions as focus_sessions_db
from utils.other import endpoints as auth
from utils.request_validation import validate_calendar_date

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


@router.post('/v1/focus-sessions', tags=['focus-sessions'], response_model=FocusSession)
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


@router.get('/v1/focus-sessions', tags=['focus-sessions'], response_model=list[FocusSession])
def get_focus_sessions(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    date: str | None = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    uid: str = Depends(auth.get_current_user_uid),
):
    date = validate_calendar_date(date)
    return focus_sessions_db.get_focus_sessions(uid, limit=limit, offset=offset, date=date)


@router.get('/v1/focus-sessions/{session_id}', tags=['focus-sessions'], response_model=FocusSession)
def get_focus_session(
    session_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    session = focus_sessions_db.get_focus_session(uid, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail='Focus session not found')
    return session


@router.delete('/v1/focus-sessions/{session_id}', tags=['focus-sessions'], response_model=StatusResponse)
def delete_focus_session(
    session_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    focus_sessions_db.delete_focus_session(uid, session_id)
    return {'status': 'ok'}


@router.get('/v1/focus-stats', tags=['focus-sessions'], response_model=FocusStats)
def get_focus_stats(
    date: str | None = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    uid: str = Depends(auth.get_current_user_uid),
):
    date = validate_calendar_date(date)
    return focus_sessions_db.get_focus_stats(uid, date=date)
