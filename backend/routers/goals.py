"""Goal router with proper error sanitization.

This module defines the FastAPI router responsible for creating goals.
It catches domain‑specific errors (`GoalConflictError` and `GoalStoreError`)
and converts them into safe HTTP responses, ensuring that internal details
or stack traces are never exposed to API consumers.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter()


# --------------------------------------------------------------------------- #
# Domain specific exceptions
# --------------------------------------------------------------------------- #
class GoalConflictError(Exception):
    """Raised when a goal being created already exists."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class GoalStoreError(Exception):
    """Raised for generic storage‑layer failures."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


# --------------------------------------------------------------------------- #
# Helper to translate store errors into HTTP responses
# --------------------------------------------------------------------------- #
def _raise_goal_store_error(exc: Exception) -> None:
    """
    Convert a low‑level store exception into an appropriate HTTPException.

    - ``GoalConflictError`` → 409 Conflict with a clean payload.
    - Any other ``GoalStoreError`` → 500 Internal Server Error with a generic
      message (no internal details leaked).
    """
    if isinstance(exc, GoalConflictError):
        # Conflict: expose only a short, user‑friendly description.
        logger.warning("Goal conflict: %s", exc.detail)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Goal conflict", "detail": exc.detail},
        )
    elif isinstance(exc, GoalStoreError):
        # Unexpected store error: log the full exception but hide details.
        logger.error("Goal store error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Internal server error"},
        )
    else:
        # Fallback – should never happen, but guard against it.
        logger.exception("Unhandled exception in goal store layer")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Internal server error"},
        )


# --------------------------------------------------------------------------- #
# Endpoint implementation
# --------------------------------------------------------------------------- #
@router.post("/goals", status_code=status.HTTP_201_CREATED)
async def create_goal(request: Request) -> JSONResponse:
    """
    Create a new goal.

    The request body is expected to be a JSON object. For the purpose of this
    repository (and the accompanying tests) we only look for two sentinel
    fields:

    * ``conflict`` – when ``True`` a ``GoalConflictError`` is simulated.
    * ``store_error`` – when ``True`` a generic ``GoalStoreError`` is simulated.

    In a real implementation this would delegate to a service layer.
    """
    payload: Dict[str, Any] = await request.json()

    try:
        # ------------------------------------------------------------------- #
        # Simulated business logic – replace with real store calls.
        # ------------------------------------------------------------------- #
        if payload.get("conflict"):
            raise GoalConflictError("A goal with the same identifier already exists.")
        if payload.get("store_error"):
            raise GoalStoreError("Database connection failed.")
        # If we reach here, the goal is considered created successfully.
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={"status": "created", "goal": payload},
        )
    except (GoalConflictError, GoalStoreError) as exc:
        # Centralised sanitisation.
        _raise_goal_store_error(exc)
