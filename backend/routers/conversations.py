"""Conversations router – handles conversation‑related endpoints."""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException
from typing import Any

# Local imports – adjust if the actual import paths differ
from backend.services.email import (
    AmbiguousDeliveryError,
    get_email_service,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Helper constants for sanitized error messages
# --------------------------------------------------------------------------- #
_SANITIZED_MESSAGES = {
    AmbiguousDeliveryError: ("Email delivery timed out.", 504),
    ValueError: ("Email service unavailable.", 503),
    RuntimeError: ("Email delivery failed.", 502),
}


@router.post("/share-email")
async def send_conversation_share_email(
    conversation_id: str,
    email: str,
    email_service: Any = Depends(get_email_service),
) -> dict[str, str]:
    """
    Send a share‑email for a conversation.

    The function now sanitizes any exception details that could leak
    internal transport or configuration information.  Errors are logged
    with their type name, and the client receives a generic, user‑friendly
    message.
    """
    try:
        await email_service.send_share_email(conversation_id, email)
        return {"status": "sent"}
    except (AmbiguousDeliveryError, ValueError, RuntimeError) as exc:
        # Log the raw exception safely – only the type name and message are stored.
        logger.error(
            "Conversation share email failed – %s: %s",
            type(exc).__name__,
            str(exc),
            exc_info=True,
        )

        # Determine the sanitized response.
        message, status_code = _SANITIZED_MESSAGES.get(
            type(exc), ("Unexpected error.", 500)
        )
        raise HTTPException(status_code=status_code, detail=message) from exc
