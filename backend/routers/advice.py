"""Advice — proactive coaching items."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import database.advice as advice_db
from models.advice import Advice
from models.shared import StatusResponse
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
# ENDPOINTS
# ============================================================================


@router.post("/v1/advice", tags=["advice"], response_model=Advice)
def create_advice(
    request: CreateAdviceRequest,
    uid: str = Depends(auth.get_current_user_uid),
) -> Any:
    clean_content = request.content.strip()
    if not clean_content:
        raise HTTPException(status_code=400, detail="content cannot be empty or whitespace only")

    try:
        return advice_db.create_advice(
            uid,
            content=clean_content,
            category=request.category or "other",
            reasoning=request.reasoning,
            source_app=request.source_app,
            confidence=request.confidence,
            context_summary=request.context_summary,
            current_activity=request.current_activity,
        )
    except HTTPException:
        raise
    except (ValueError, TypeError) as error:
        logger.warning("Invalid advice creation parameters for user %s: %s", uid, sanitize(str(error)))
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.error("Failed to create advice for user %s: %s", uid, sanitize(str(error)), exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to create advice") from error


@router.get("/v1/advice", tags=["advice"], response_model=list[Advice])
def get_advice(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    category: str | None = Query(None),
    include_dismissed: bool = Query(False),
    uid: str = Depends(auth.get_current_user_uid),
) -> Any:
    try:
        return advice_db.get_advice(
            uid,
            limit=limit,
            offset=offset,
            category=category,
            include_dismissed=include_dismissed,
        )
    except HTTPException:
        raise
    except (ValueError, TypeError) as error:
        logger.warning("Invalid advice query parameters for user %s: %s", uid, sanitize(str(error)))
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.error("Failed to fetch advice list for user %s: %s", uid, sanitize(str(error)), exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to fetch advice") from error


@router.patch("/v1/advice/{advice_id}", tags=["advice"], response_model=Advice)
def update_advice(
    advice_id: str,
    request: UpdateAdviceRequest,
    uid: str = Depends(auth.get_current_user_uid),
) -> Any:
    clean_advice_id = (advice_id or "").strip()
    if not clean_advice_id:
        raise HTTPException(status_code=400, detail="Valid advice_id is required")

    if request.is_read is None and request.is_dismissed is None:
        raise HTTPException(status_code=400, detail="At least one field (is_read or is_dismissed) must be provided")

    try:
        result = advice_db.update_advice(
            uid,
            clean_advice_id,
            is_read=request.is_read,
            is_dismissed=request.is_dismissed,
        )
    except HTTPException:
        raise
    except (ValueError, TypeError) as error:
        logger.warning("Invalid advice update for user %s: %s", uid, sanitize(str(error)))
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.error("Failed to update advice for user %s: %s", uid, sanitize(str(error)), exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to update advice") from error

    if result is None:
        raise HTTPException(status_code=404, detail="Advice not found")
    return result


@router.delete("/v1/advice/{advice_id}", tags=["advice"], response_model=StatusResponse)
def delete_advice(
    advice_id: str,
    uid: str = Depends(auth.get_current_user_uid),
) -> Any:
    clean_advice_id = (advice_id or "").strip()
    if not clean_advice_id:
        raise HTTPException(status_code=400, detail="Valid advice_id is required")

    try:
        deleted = advice_db.delete_advice(uid, clean_advice_id)
    except HTTPException:
        raise
    except (ValueError, TypeError) as error:
        logger.warning("Invalid advice deletion for user %s: %s", uid, sanitize(str(error)))
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.error("Failed to delete advice for user %s: %s", uid, sanitize(str(error)), exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to delete advice") from error

    if not deleted:
        raise HTTPException(status_code=404, detail="Advice not found")
    return {"status": "ok"}


@router.post("/v1/advice/mark-all-read", tags=["advice"], response_model=StatusResponse)
def mark_all_advice_read(uid: str = Depends(auth.get_current_user_uid)) -> Any:
    try:
        count = advice_db.mark_all_advice_read(uid)
        return {"status": f"marked {count} as read"}
    except HTTPException:
        raise
    except Exception as error:
        logger.error("Failed to mark all advice as read for user %s: %s", uid, sanitize(str(error)), exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to mark all advice as read") from error
