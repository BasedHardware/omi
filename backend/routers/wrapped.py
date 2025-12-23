"""
Wrapped 2025 API endpoints.

Provides generation and retrieval of yearly recap data.
"""

import threading
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import database.wrapped as wrapped_db
from database.wrapped import WrappedStatus
from utils.other import endpoints as auth

router = APIRouter()


# Response models
class WrappedStatusResponse(BaseModel):
    status: str
    year: int = 2025
    result: Optional[dict] = None
    error: Optional[str] = None
    progress: Optional[dict] = None


class GenerateWrappedResponse(BaseModel):
    status: str
    message: str


# Background generation function (imported lazily to avoid circular imports)
def _run_wrapped_generation(uid: str, year: int):
    """Run wrapped generation in a background thread."""
    try:
        from utils.wrapped.generate_2025 import generate_wrapped_2025

        generate_wrapped_2025(uid, year)
    except Exception as e:
        print(f"Error in wrapped generation for user {uid}: {e}")
        wrapped_db.update_wrapped_status(uid, year, WrappedStatus.ERROR, error=str(e))


@router.get('/v1/wrapped/{year}', response_model=WrappedStatusResponse, tags=['wrapped'])
def get_wrapped_status(year: int, uid: str = Depends(auth.get_current_user_uid)):
    """
    Get the status and result of wrapped generation for a given year.

    Returns:
        - status: not_generated, processing, done, or error
        - result: The wrapped payload (only when status=done)
        - error: Error message (only when status=error)
        - progress: Progress info (only when status=processing)
    """
    # For now, only support 2025
    if year != 2025:
        raise HTTPException(status_code=400, detail="Only year 2025 is currently supported")

    wrapped = wrapped_db.get_wrapped(uid, year)

    if not wrapped:
        return WrappedStatusResponse(
            status=WrappedStatus.NOT_GENERATED,
            year=year,
        )

    return WrappedStatusResponse(
        status=wrapped.get('status', WrappedStatus.NOT_GENERATED),
        year=year,
        result=wrapped.get('result'),
        error=wrapped.get('error'),
        progress=wrapped.get('progress'),
    )


@router.post('/v1/wrapped/{year}/generate', response_model=GenerateWrappedResponse, tags=['wrapped'])
def generate_wrapped(year: int, uid: str = Depends(auth.get_current_user_uid)):
    """
    Start wrapped generation for a given year.

    This is idempotent:
    - If already done: returns done status (no regeneration in v1)
    - If already processing: returns processing status
    - If error or not generated: starts generation
    - If processing but stuck (no heartbeat for 15 min): restarts generation
    """
    # For now, only support 2025
    if year != 2025:
        raise HTTPException(status_code=400, detail="Only year 2025 is currently supported")

    wrapped = wrapped_db.get_wrapped(uid, year)

    # Already done - no regeneration in v1
    if wrapped and wrapped.get('status') == WrappedStatus.DONE:
        return GenerateWrappedResponse(
            status=WrappedStatus.DONE,
            message="Your Wrapped 2025 is already generated",
        )

    # Already processing - check if stuck
    if wrapped and wrapped.get('status') == WrappedStatus.PROCESSING:
        if wrapped_db.is_wrapped_stuck(wrapped):
            # Restart stuck job
            wrapped_db.reset_wrapped_for_regeneration(uid, year)
            thread = threading.Thread(target=_run_wrapped_generation, args=(uid, year))
            thread.start()
            return GenerateWrappedResponse(
                status=WrappedStatus.PROCESSING,
                message="Restarting stuck generation...",
            )
        else:
            return GenerateWrappedResponse(
                status=WrappedStatus.PROCESSING,
                message="Generation is already in progress",
            )

    # Error or not generated - start fresh
    if wrapped and wrapped.get('status') == WrappedStatus.ERROR:
        wrapped_db.reset_wrapped_for_regeneration(uid, year)
    else:
        wrapped_db.create_wrapped(uid, year)

    # Start generation in background
    thread = threading.Thread(target=_run_wrapped_generation, args=(uid, year))
    thread.start()

    return GenerateWrappedResponse(
        status=WrappedStatus.PROCESSING,
        message="Starting Wrapped 2025 generation...",
    )
