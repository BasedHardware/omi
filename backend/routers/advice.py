import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import database.advice as advice_db
from utils.other import endpoints as auth

logger = logging.getLogger(__name__)

router = APIRouter()

VALID_CATEGORIES = ('productivity', 'health', 'communication', 'learning', 'other')


class CreateAdviceRequest(BaseModel):
    content: str = Field(description="Advice content text")
    category: Optional[str] = Field(default=None, description="Category: productivity, health, communication, learning, other")
    reasoning: Optional[str] = Field(default=None, description="Reasoning behind the advice")
    source_app: Optional[str] = Field(default=None, description="App where context was observed")
    confidence: Optional[float] = Field(default=None, description="Confidence score 0.0-1.0")
    context_summary: Optional[str] = Field(default=None, description="Context summary")
    current_activity: Optional[str] = Field(default=None, description="User's current activity")


class UpdateAdviceRequest(BaseModel):
    is_read: Optional[bool] = None
    is_dismissed: Optional[bool] = None


class AdviceResponse(BaseModel):
    id: str
    content: str
    category: str = 'other'
    reasoning: Optional[str] = None
    source_app: Optional[str] = None
    confidence: float = 0.5
    context_summary: Optional[str] = None
    current_activity: Optional[str] = None
    created_at: object = None
    updated_at: object = None
    is_read: bool = False
    is_dismissed: bool = False


class AdviceStatusResponse(BaseModel):
    status: str


def _validate_category(category: Optional[str]):
    if category and category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"category must be one of: {', '.join(VALID_CATEGORIES)}"
        )


def _validate_confidence(confidence: Optional[float]):
    if confidence is not None and not (0.0 <= confidence <= 1.0):
        raise HTTPException(status_code=400, detail="confidence must be between 0.0 and 1.0")


@router.post('/v1/advice', status_code=201, tags=['advice'])
def create_advice(
    request: CreateAdviceRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    _validate_category(request.category)
    _validate_confidence(request.confidence)
    try:
        return advice_db.create_advice(uid, request.model_dump(exclude_none=True))
    except Exception:
        logger.exception('Failed to create advice for uid=%s', uid)
        raise HTTPException(status_code=500, detail="Failed to create advice")


@router.get('/v1/advice', tags=['advice'])
def get_advice(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    category: Optional[str] = Query(default=None),
    include_dismissed: bool = Query(default=False),
    uid: str = Depends(auth.get_current_user_uid),
):
    _validate_category(category)
    try:
        return advice_db.get_advice(
            uid, limit=limit, offset=offset, category=category, include_dismissed=include_dismissed,
        )
    except Exception:
        logger.exception('Failed to get advice for uid=%s', uid)
        return []


@router.patch('/v1/advice/{advice_id}', tags=['advice'])
def update_advice(
    advice_id: str,
    request: UpdateAdviceRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    update_data = request.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        result = advice_db.update_advice(uid, advice_id, update_data)
        if result is None:
            raise HTTPException(status_code=404, detail="Advice not found")
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception('Failed to update advice %s for uid=%s', advice_id, uid)
        raise HTTPException(status_code=500, detail="Failed to update advice")


@router.delete('/v1/advice/{advice_id}', response_model=AdviceStatusResponse, tags=['advice'])
def delete_advice(
    advice_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    try:
        advice_db.delete_advice(uid, advice_id)
        return AdviceStatusResponse(status="ok")
    except Exception:
        logger.exception('Failed to delete advice %s for uid=%s', advice_id, uid)
        raise HTTPException(status_code=500, detail="Failed to delete advice")


@router.post('/v1/advice/mark-all-read', response_model=AdviceStatusResponse, tags=['advice'])
def mark_all_advice_read(
    uid: str = Depends(auth.get_current_user_uid),
):
    try:
        count = advice_db.mark_all_advice_read(uid)
        return AdviceStatusResponse(status=f"marked {count} as read")
    except Exception:
        logger.exception('Failed to mark all advice read for uid=%s', uid)
        raise HTTPException(status_code=500, detail="Failed to mark advice as read")
