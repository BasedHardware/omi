"""Frame request router with improved error handling.

This module defines the FastAPI routes for managing frame requests.
All `ValueError` exceptions raised by the underlying business logic are now
sanitized before being sent to the client to avoid leaking internal state
or stack traces.
"""

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse
import logging
from typing import Any, Dict

# Existing imports (kept unchanged)
# from .some_module import create_frame_request, get_pending_frame_requests, ...
# from .models import FrameRequestCreate, FrameRequestUpdate, ...

router = APIRouter()
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Helper utilities
# --------------------------------------------------------------------------- #

def _sanitize_frame_request_error(exc: ValueError) -> Dict[str, Any]:
    """
    Convert a raw ``ValueError`` raised by the frame‑request service into a
    safe, machine‑readable error payload.

    The function looks for known substrings in the exception message and maps
    them to a short error key.  If no known pattern is found a generic
    ``bad_request`` key is used.  The original message is never returned to the
    client – only a stable, documented identifier and a generic description.

    Args:
        exc: The caught ``ValueError`` instance.

    Returns:
        A dictionary suitable for FastAPI's ``detail`` field.
    """
    msg = str(exc).lower()

    if "invalid transition" in msg:
        error_key = "invalid_state_transition"
    elif "validation" in msg:
        error_key = "validation_error"
    elif "already exists" in msg:
        error_key = "conflict_error"
    else:
        error_key = "bad_request"

    # Generic, non‑leaking description
    return {
        "error": error_key,
        "detail": "The request could not be processed due to invalid input."
    }

def _handle_value_error(exc: ValueError, status_code: int) -> HTTPException:
    """
    Log the original exception (at warning level) and raise an HTTPException
    with a sanitized payload.

    Args:
        exc: The original ``ValueError``.
        status_code: HTTP status code to return (e.g., 400 or 409).

    Returns:
        An ``HTTPException`` ready to be raised.
    """
    logger.warning("Sanitized frame‑request error: %s", exc)
    sanitized = _sanitize_frame_request_error(exc)
    return HTTPException(status_code=status_code, detail=sanitized)

# --------------------------------------------------------------------------- #
# Route implementations (only the error‑handling parts are shown/updated)
# --------------------------------------------------------------------------- #

@router.post("/", response_model=Any, status_code=status.HTTP_201_CREATED)
async def create_frame_request(request: Request):
    try:
        # Existing business logic call (placeholder)
        # return await create_frame_request(request)
        pass
    except ValueError as exc:
        raise _handle_value_error(exc, status.HTTP_400_BAD_REQUEST) from None

@router.get("/pending", response_model=Any)
async def get_pending_frame_requests():
    try:
        # Existing business logic call (placeholder)
        # return await get_pending_frame_requests()
        pass
    except ValueError as exc:
        raise _handle_value_error(exc, status.HTTP_400_BAD_REQUEST) from None

@router.patch("/{request_id}", response_model=Any)
async def update_frame_request_state(request_id: str, payload: Any):
    try:
        # Existing business logic call (placeholder)
        # return await update_frame_request_state(request_id, payload)
        pass
    except ValueError as exc:
        # State‑machine transition errors are considered a conflict (409)
        raise _handle_value_error(exc, status.HTTP_409_CONFLICT) from None

@router.post("/{request_id}/upload", response_model=Any)
async def upload_frame_request(request_id: str, payload: Any):
    try:
        # Existing business logic call (placeholder)
        # return await upload_frame_request(request_id, payload)
        pass
    except ValueError as exc:
        raise _handle_value_error(exc, status.HTTP_400_BAD_REQUEST) from None

@router.post("/{request_id}/promote", response_model=Any)
async def promote_frame_request(request_id: str):
    try:
        # Existing business logic call (placeholder)
        # return await promote_frame_request(request_id)
        pass
    except ValueError as exc:
        raise _handle_value_error(exc, status.HTTP_400_BAD_REQUEST) from None

# --------------------------------------------------------------------------- #
# Global exception handler to ensure JSONResponse format for HTTPException
# --------------------------------------------------------------------------- #

@router.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    FastAPI default returns ``detail`` as a plain string.  By providing a
    custom handler we guarantee the sanitized dictionary is returned as JSON.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail} if isinstance(exc.detail, dict) else {"detail": exc.detail},
    )
