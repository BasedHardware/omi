import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import database.focus_sessions as focus_sessions_db
from utils.other import endpoints as auth

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateFocusSessionRequest(BaseModel):
    status: str = Field(description="'focused' or 'distracted'")
    app_or_site: str = Field(description="App or website name")
    description: str = Field(description="Brief description of the session")
    message: Optional[str] = Field(default=None, description="Optional coaching message")
    duration_seconds: Optional[int] = Field(default=None, description="Optional session duration in seconds")


class FocusSessionResponse(BaseModel):
    id: str
    status: str
    app_or_site: str
    description: str
    message: Optional[str] = None
    created_at: datetime
    duration_seconds: Optional[int] = None


class FocusSessionStatusResponse(BaseModel):
    status: str


class DistractionEntry(BaseModel):
    app_or_site: str
    total_seconds: int
    count: int


class FocusStatsResponse(BaseModel):
    date: str
    focused_minutes: int
    distracted_minutes: int
    session_count: int
    focused_count: int
    distracted_count: int
    top_distractions: List[DistractionEntry]


def _validate_focus_status(status: str):
    if status not in ('focused', 'distracted'):
        raise HTTPException(status_code=400, detail="status must be 'focused' or 'distracted'")


@router.post('/v1/focus-sessions', response_model=FocusSessionResponse, tags=['focus-sessions'])
def create_focus_session(
    request: CreateFocusSessionRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    _validate_focus_status(request.status)
    try:
        session = focus_sessions_db.create_focus_session(uid, request.model_dump())
        return session
    except Exception:
        logger.exception('Failed to create focus session for uid=%s', uid)
        raise HTTPException(status_code=500, detail="Failed to create focus session")


@router.get('/v1/focus-sessions', response_model=List[FocusSessionResponse], tags=['focus-sessions'])
def get_focus_sessions(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    date: Optional[str] = Query(default=None, description="Filter by date (YYYY-MM-DD)"),
    uid: str = Depends(auth.get_current_user_uid),
):
    if date:
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            date = None  # Skip invalid date filter (match Rust behavior)
    try:
        return focus_sessions_db.get_focus_sessions(uid, limit=limit, offset=offset, date=date)
    except Exception:
        logger.exception('Failed to get focus sessions for uid=%s', uid)
        return []


@router.delete('/v1/focus-sessions/{session_id}', response_model=FocusSessionStatusResponse, tags=['focus-sessions'])
def delete_focus_session(
    session_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    try:
        focus_sessions_db.delete_focus_session(uid, session_id)
        return FocusSessionStatusResponse(status="ok")
    except Exception:
        logger.exception('Failed to delete focus session %s for uid=%s', session_id, uid)
        raise HTTPException(status_code=500, detail="Failed to delete focus session")


@router.get('/v1/focus-stats', response_model=FocusStatsResponse, tags=['focus-sessions'])
def get_focus_stats(
    date: Optional[str] = Query(default=None, description="Date for stats (YYYY-MM-DD), defaults to today"),
    uid: str = Depends(auth.get_current_user_uid),
):
    if date:
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            date = None  # Skip invalid date filter (match Rust behavior)
    if not date:
        date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    try:
        sessions = focus_sessions_db.get_focus_sessions_for_stats(uid, date)
    except Exception:
        logger.exception('Failed to get focus stats for uid=%s', uid)
        raise HTTPException(status_code=500, detail="Failed to get focus stats")

    focused_count = 0
    distracted_count = 0
    distraction_map = defaultdict(lambda: {'total_seconds': 0, 'count': 0})

    for s in sessions:
        status = s.get('status', '')
        if status == 'focused':
            focused_count += 1
        elif status == 'distracted':
            distracted_count += 1
            app = s.get('app_or_site', 'Unknown')
            raw_duration = s.get('duration_seconds')
            duration = raw_duration if raw_duration is not None else 60
            distraction_map[app]['total_seconds'] += duration
            distraction_map[app]['count'] += 1

    top_distractions = sorted(
        [DistractionEntry(app_or_site=app, **vals) for app, vals in distraction_map.items()],
        key=lambda d: d.total_seconds,
        reverse=True,
    )[:5]

    return FocusStatsResponse(
        date=date,
        focused_minutes=focused_count,
        distracted_minutes=distracted_count,
        session_count=focused_count + distracted_count,
        focused_count=focused_count,
        distracted_count=distracted_count,
        top_distractions=top_distractions,
    )
