"""Focus sessions — focus/distraction tracking and statistics."""

from datetime import datetime
import logging
import re
from typing import Any, Dict, List, Mapping, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from models.focus_session import FocusSession, FocusStats
from models.screen_activity import ScreenActivityCoverage
from models.shared import StatusResponse
import database.focus_sessions as focus_sessions_db
import database.screen_activity as screen_activity_db
from utils.log_sanitizer import sanitize
from utils.other import endpoints as auth
from utils.request_validation import validate_calendar_date

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# HELPERS
# ============================================================================

#: Firestore caps document ids at 1500 bytes; anything longer would surface as
#: an opaque data-layer error instead of a clean caller bug.
_MAX_SESSION_ID_BYTES = 1500

#: Firestore reserves ``__`` and ``__.*__`` document ids for internal use.
_RESERVED_SESSION_ID_RE = re.compile(r'__(?:.*__)?')


def _require_session_id(session_id: str) -> str:
    """Validate the ``{session_id}`` path coordinate before it reaches the data layer.

    Firestore accepts almost any string as a document id, so a blank, whitespace-only,
    traversal-shaped (``.``, ``..`` or embedded ``/``), reserved (``__`` / ``__.*__``) or
    oversized (``>1500`` bytes) id would either silently miss (and read back as a
    false 200) or blow up inside the data layer. Classified here as a caller bug
    with HTTP 400, mirroring ``_require_advice_id`` in ``routers/advice.py``.
    """
    stripped = session_id.strip()
    if (
        not stripped
        or stripped in ('.', '..')
        or '/' in stripped
        or _RESERVED_SESSION_ID_RE.fullmatch(stripped)
        or len(stripped.encode('utf-8')) > _MAX_SESSION_ID_BYTES
    ):
        raise HTTPException(status_code=400, detail='Valid session_id is required')
    return stripped


def _log_database_failure(action: str, uid: str, error: Exception) -> None:
    """Log a data-layer failure server-side, masking anything token- or PII-shaped.

    The client only ever receives a fixed message: raw exception text names Firestore
    and provider internals and can echo stored document contents, so it stays in the log.
    """
    logger.error(f'focus-sessions {action} failed uid={uid}: {sanitize(str(error))}', exc_info=True)


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
    # ``min_length=1`` passes whitespace-only strings ("   ") straight through
    # Pydantic, so trim here and reject the all-blank payload explicitly.
    app_or_site = request.app_or_site.strip()
    description = request.description.strip()
    message = request.message.strip() if isinstance(request.message, str) else request.message
    if not app_or_site:
        raise HTTPException(status_code=400, detail='Valid app_or_site is required')
    if not description:
        raise HTTPException(status_code=400, detail='Valid description is required')
    try:
        return focus_sessions_db.create_focus_session(
            uid,
            status=request.status,
            app_or_site=app_or_site,
            description=description,
            message=message,
            duration_seconds=request.duration_seconds,
        )
    except HTTPException:
        raise
    except Exception as e:
        _log_database_failure('create', uid, e)
        raise HTTPException(status_code=500, detail='Failed to create focus session')


@router.get('/v1/focus-sessions', tags=['focus-sessions'], response_model=list[FocusSession])
def get_focus_sessions(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    date: str | None = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    uid: str = Depends(auth.get_current_user_uid),
):
    date = validate_calendar_date(date)
    try:
        raw_sessions = focus_sessions_db.get_focus_sessions(uid, limit=limit, offset=offset, date=date)
    except HTTPException:
        raise
    except Exception as e:
        _log_database_failure('list', uid, e)
        raise HTTPException(status_code=500, detail='Failed to load focus sessions')

    def _log_skipped_session(record: Any, exc: Exception) -> None:
        doc_id = 'unknown'
        try:
            if isinstance(record, (dict, Mapping)):
                raw_id = record.get('id')
                if raw_id is not None:
                    doc_id = str(raw_id)
        except Exception:
            doc_id = 'unknown'
        try:
            logger.warning("Skipping malformed focus session %s: %s", doc_id, type(exc).__name__)
        except Exception:
            pass

    return FocusSession.deserialize_many_safe(raw_sessions, on_error=_log_skipped_session)


@router.delete('/v1/focus-sessions/{session_id}', tags=['focus-sessions'], response_model=StatusResponse)
def delete_focus_session(
    session_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    session_id = _require_session_id(session_id)
    try:
        deleted = focus_sessions_db.delete_focus_session(uid, session_id)
    except HTTPException:
        raise
    except Exception as e:
        _log_database_failure('delete', uid, e)
        raise HTTPException(status_code=500, detail='Failed to delete focus session')
    if not deleted:
        raise HTTPException(status_code=404, detail='Focus session not found')
    return {'status': 'ok'}


@router.get('/v1/focus-stats', tags=['focus-sessions'], response_model=FocusStats)
def get_focus_stats(
    date: str | None = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    uid: str = Depends(auth.get_current_user_uid),
):
    date = validate_calendar_date(date)
    try:
        return focus_sessions_db.get_focus_stats(uid, date=date)
    except HTTPException:
        raise
    except Exception as e:
        _log_database_failure('stats', uid, e)
        raise HTTPException(status_code=500, detail='Failed to load focus stats')


class ScreenActivityRow(BaseModel):
    """One captured screen-activity row. The desktop app owns the write shape and
    adds fields over time, so unknown keys pass through rather than being dropped."""

    model_config = {"extra": "allow"}

    id: str
    timestamp: Optional[str] = None
    appName: Optional[str] = None
    windowTitle: Optional[str] = None


class ScreenActivityAppSummary(BaseModel):
    count: int
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    window_titles: List[str] = Field(default_factory=list)


class ScreenActivitySummaryResponse(BaseModel):
    apps: Dict[str, ScreenActivityAppSummary]
    total_screenshots: int
    coverage: Optional[ScreenActivityCoverage] = None


@router.get('/v1/screen-activity', tags=['screen-activity'], response_model=List[ScreenActivityRow])
def list_screen_activity(
    date: str | None = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    app_filter: str | None = Query(None, max_length=500),
    limit: int = Query(500, ge=1, le=5000),
    uid: str = Depends(auth.get_current_user_uid),
):
    """List the user's captured screen-activity rows, optionally filtered to a single day and/or app.

    The rows are captured by the desktop app and only ever read back internally (MCP); this
    exposes them to the user's own first-party client. A bad date is rejected with 422.
    """
    date = validate_calendar_date(date)
    # A whitespace-only app filter is a caller bug, not a filter: normalize it to
    # None so it cannot silently narrow the query to zero rows.
    if isinstance(app_filter, str):
        app_filter = app_filter.strip() or None
    start = end = None
    if date:
        start = datetime.strptime(date, '%Y-%m-%d')
        # Inclusive same-day upper bound. get_screen_activity applies end_date as
        # timestamp <= 'YYYY-MM-DD HH:MM:SS.999', so a next-day midnight end would leak the
        # following day's first second into this privacy-sensitive single-day result.
        end = start.replace(hour=23, minute=59, second=59)
    try:
        return screen_activity_db.get_screen_activity(
            uid, start_date=start, end_date=end, app_filter=app_filter, limit=limit
        )
    except HTTPException:
        raise
    except Exception as e:
        _log_database_failure('screen-activity list', uid, e)
        raise HTTPException(status_code=500, detail='Failed to load screen activity')


@router.get('/v1/screen-activity/summary', tags=['screen-activity'], response_model=ScreenActivitySummaryResponse)
def screen_activity_summary(
    date: str | None = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    uid: str = Depends(auth.get_current_user_uid),
):
    """Aggregated per-app screen-activity summary (screenshots per app, first/last seen).

    The desktop app captures screen-activity but it was only ever read back internally (MCP);
    this exposes the aggregated view to the user's own first-party client. A bad date is 422.
    """
    date = validate_calendar_date(date)
    start = end = None
    if date:
        start = datetime.strptime(date, '%Y-%m-%d')
        # Inclusive same-day upper bound. get_screen_activity applies end_date as
        # timestamp <= 'YYYY-MM-DD HH:MM:SS.999', so a next-day midnight end would leak the
        # following day's first second into this privacy-sensitive single-day summary.
        end = start.replace(hour=23, minute=59, second=59)
    try:
        return screen_activity_db.get_screen_activity_summary(uid, start_date=start, end_date=end)
    except HTTPException:
        raise
    except Exception as e:
        _log_database_failure('screen-activity summary', uid, e)
        raise HTTPException(status_code=500, detail='Failed to load screen activity summary')
