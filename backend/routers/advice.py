"""Advice — proactive coaching items."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import database.advice as advice_db
from utils.other import endpoints as auth

router = APIRouter()


# ============================================================================
# MODELS
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
# ENDPOINTS
# ============================================================================


@router.post('/v1/advice', tags=['advice'])
def create_advice(
    request: CreateAdviceRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    return advice_db.create_advice(
        uid,
        content=request.content,
        category=request.category or 'other',
        reasoning=request.reasoning,
        source_app=request.source_app,
        confidence=request.confidence,
        context_summary=request.context_summary,
        current_activity=request.current_activity,
    )


@router.get('/v1/advice', tags=['advice'])
def get_advice(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    category: str | None = Query(None),
    include_dismissed: bool = Query(False),
    uid: str = Depends(auth.get_current_user_uid),
):
    return advice_db.get_advice(uid, limit=limit, offset=offset, category=category, include_dismissed=include_dismissed)


@router.patch('/v1/advice/{advice_id}', tags=['advice'])
def update_advice(
    advice_id: str,
    request: UpdateAdviceRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    result = advice_db.update_advice(uid, advice_id, is_read=request.is_read, is_dismissed=request.is_dismissed)
    if result is None:
        raise HTTPException(status_code=404, detail='Advice not found')
    return result


@router.delete('/v1/advice/{advice_id}', tags=['advice'])
def delete_advice(
    advice_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    advice_db.delete_advice(uid, advice_id)
    return {'status': 'ok'}


@router.post('/v1/advice/mark-all-read', tags=['advice'])
def mark_all_advice_read(uid: str = Depends(auth.get_current_user_uid)):
    count = advice_db.mark_all_advice_read(uid)
    return {'status': f'marked {count} as read'}
