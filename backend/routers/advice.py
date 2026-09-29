"""Advice — proactive coaching items."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError

from models.advice import Advice
from models.shared import StatusResponse
import database.advice as advice_db
from utils.log_sanitizer import sanitize
from utils.other import endpoints as auth

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# REQUEST MODELS
# ============================================================================


class CreateAdviceRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)
    category: str | None = Field(None, max_length=100)
    reasoning: str | None = Field(None, max_length=5000)
    source_app: str | None = Field(None, max_length=200)
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    context_summary: str | None = Field(None, max_length=5000)
    current_activity: str | None = Field(None, max_length=500)


class UpdateAdviceRequest(BaseModel):
    is_read: bool | None = None
    is_dismissed: bool | None = None


# ============================================================================
# HELPERS
# ============================================================================


def _require_advice_id(advice_id: str) -> str:
    """Classify a blank path coordinate as a bad request before it reaches the data layer.

    ``/v1/advice/{advice_id}`` carrying only whitespace is a caller bug, not a lookup:
    Firestore accepts the string as a document id and the read simply misses, so the route
    answered 404 (PATCH) or 200 (DELETE) for what the caller meant as "no id at all".
    """
    stripped = advice_id.strip()
    if not stripped:
        raise HTTPException(status_code=400, detail='Valid advice_id is required')
    return stripped


def _log_database_failure(action: str, uid: str, error: Exception) -> None:
    """Log a data-layer failure server-side, masking anything token- or PII-shaped.

    The client only ever receives a fixed message: raw exception text names Firestore and
    provider internals and can echo stored document contents, so it stays in the log.
    """
    logger.error(f'advice {action} failed uid={uid}: {sanitize(str(error))}', exc_info=True)


def _safe_advice_responses(items: list[dict], uid: str) -> list[Advice]:
    """Build validated Advice objects from raw records, dropping any malformed or legacy
    rows so a single bad document cannot 500 the whole list endpoint (mirrors the defensive
    deserialization pattern in calendar_meetings and action_items)."""
    valid: list[Advice] = []
    for item in items:
        try:
            valid.append(Advice.model_validate(item))
        except ValidationError as exc:
            advice_id = item.get('id')
            logger.warning(
                'Skipping malformed advice item for uid=%s id=%s: %s',
                uid,
                advice_id,
                type(exc).__name__,
            )
    return valid


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.post('/v1/advice', tags=['advice'], response_model=Advice)
def create_advice(
    request: CreateAdviceRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    content = request.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail='content cannot be empty or whitespace only')
    try:
        return advice_db.create_advice(
            uid,
            content=content,
            category=request.category or 'other',
            reasoning=request.reasoning,
            source_app=request.source_app,
            confidence=request.confidence,
            context_summary=request.context_summary,
            current_activity=request.current_activity,
        )
    except HTTPException:
        raise
    except Exception as e:
        _log_database_failure('create', uid, e)
        raise HTTPException(status_code=500, detail='Failed to create advice')


@router.get('/v1/advice', tags=['advice'], response_model=list[Advice])
def get_advice(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    category: str | None = Query(None),
    include_dismissed: bool = Query(False),
    uid: str = Depends(auth.get_current_user_uid),
):
    try:
        raw_items = advice_db.get_advice(
            uid, limit=limit, offset=offset, category=category, include_dismissed=include_dismissed
        )
    except HTTPException:
        raise
    except Exception as e:
        _log_database_failure('list', uid, e)
        raise HTTPException(status_code=500, detail='Failed to load advice')
    return _safe_advice_responses(raw_items, uid)


@router.patch('/v1/advice/{advice_id}', tags=['advice'], response_model=Advice)
def update_advice(
    advice_id: str,
    request: UpdateAdviceRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    advice_id = _require_advice_id(advice_id)
    if request.is_read is None and request.is_dismissed is None:
        raise HTTPException(status_code=400, detail='At least one of is_read or is_dismissed is required')
    try:
        result = advice_db.update_advice(uid, advice_id, is_read=request.is_read, is_dismissed=request.is_dismissed)
    except HTTPException:
        raise
    except Exception as e:
        _log_database_failure('update', uid, e)
        raise HTTPException(status_code=500, detail='Failed to update advice')
    if result is None:
        raise HTTPException(status_code=404, detail='Advice not found')
    try:
        return Advice.model_validate(result)
    except ValidationError as exc:
        logger.warning(
            'Malformed advice item after update for uid=%s id=%s: %s',
            uid,
            advice_id,
            type(exc).__name__,
        )
        raise HTTPException(status_code=404, detail='Advice not found')


@router.delete('/v1/advice/{advice_id}', tags=['advice'], response_model=StatusResponse)
def delete_advice(
    advice_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    advice_id = _require_advice_id(advice_id)
    try:
        deleted = advice_db.delete_advice(uid, advice_id)
    except HTTPException:
        raise
    except Exception as e:
        _log_database_failure('delete', uid, e)
        raise HTTPException(status_code=500, detail='Failed to delete advice')
    if not deleted:
        raise HTTPException(status_code=404, detail='Advice not found')
    return {'status': 'ok'}


@router.post('/v1/advice/mark-all-read', tags=['advice'], response_model=StatusResponse)
def mark_all_advice_read(uid: str = Depends(auth.get_current_user_uid)):
    try:
        count = advice_db.mark_all_advice_read(uid)
    except HTTPException:
        raise
    except Exception as e:
        _log_database_failure('mark_all_read', uid, e)
        raise HTTPException(status_code=500, detail='Failed to mark advice as read')
    return {'status': f'marked {count} as read'}
