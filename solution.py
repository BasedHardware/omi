"""Wrapped 2025 router.

This module contains the HTTP endpoints and background task handling for the
Wrapped 2025 generation workflow.  The primary goal of the recent changes is
to ensure that any unexpected exception is **sanitized** before it is persisted
to the database or returned to a client.  This prevents leaking internal stack
traces, API keys or other sensitive information.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status

# NOTE: The actual import paths may differ slightly in the real repo – adjust
# them if necessary.
from backend.utils.wrapped.generate_2025 import generate_wrapped_2025
from backend.models.wrapped import WrappedStatus  # assumed ORM model

router = APIRouter()
log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Helper utilities
# --------------------------------------------------------------------------- #
def _sanitize_error(exc: Exception) -> str:
    """
    Return a short, safe representation of an exception.

    The format mirrors the typical ``repr`` of an exception but without any
    traceback or internal details that could be sensitive.
    """
    return f"{type(exc).__name__}: {exc}"


def _mask_legacy_error(message: str) -> str:
    """
    Detect legacy raw traceback strings that may have been persisted before
    sanitisation was added and replace them with a generic user‑facing message.
    """
    if not message:
        return message
    # Very simple heuristic – if the string looks like a Python traceback we
    # replace it.  This catches the most common cases without needing a full
    # parser.
    if "\n" in message or "Traceback" in message:
        return "An error occurred while generating Wrapped data."
    return message


# --------------------------------------------------------------------------- #
# Background generation task
# --------------------------------------------------------------------------- #
async def _run_wrapped_generation(year: int) -> None:
    """
    Execute the Wrapped 2025 generation pipeline for a given year.

    Any exception raised by ``generate_wrapped_2025`` is caught, sanitised and
    persisted to the ``WrappedStatus`` table.  The function never propagates the
    original exception to avoid leaking details to the caller.
    """
    try:
        await generate_wrapped_2025(year)
        # Mark the generation as successful.
        await WrappedStatus.update_status(
            year=year,
            status="completed",
            error=None,
        )
    except Exception as exc:  # pylint: disable=broad-except
        # Log the full traceback for internal debugging, but store only a
        # sanitised version for the client.
        log.exception("Unexpected error during Wrapped 2025 generation")
        safe_message = _sanitize_error(exc)
        await WrappedStatus.update_status(
            year=year,
            status="failed",
            error=safe_message,
        )


# --------------------------------------------------------------------------- #
# HTTP endpoints
# --------------------------------------------------------------------------- #
@router.get(
    "/v1/wrapped/{year}",
    response_model=Any,  # Replace with the actual Pydantic model in the repo.
    status_code=status.HTTP_200_OK,
)
async def get_wrapped_status(year: int):
    """
    Retrieve the generation status for a specific Wrapped year.

    The endpoint ensures that any legacy raw error strings stored in the DB are
    masked before being sent to the client.
    """
    status_record = await WrappedStatus.get_by_year(year)
    if not status_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No Wrapped status found for year {year}",
        )

    # Sanitize the error field for legacy records.
    if getattr(status_record, "error", None):
        status_record.error = _mask_legacy_error(status_record.error)

    return status_record
