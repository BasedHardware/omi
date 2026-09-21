"""
Centralised error handling utilities for the OMI Slack app plugin.

All public functions in this module return generic, user‑facing error
messages while logging the original exception details on the server.
This prevents accidental leakage of sensitive stack traces or internal
state to API consumers.
"""

import logging
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from typing import Any, Dict

# Re‑use the plugin's logger if it exists; otherwise fall back to a module logger.
try:
    from .logger import logger  # type: ignore
except Exception:  # pragma: no cover
    logger = logging.getLogger(__name__)


def _log_exception(e: Exception) -> None:
    """Log the exception with traceback for debugging purposes."""
    logger.exception("Unhandled exception in OMI Slack app: %s", e)


def http_exception(status_code: int, user_message: str, *, original: Exception | None = None) -> HTTPException:
    """
    Return an HTTPException with a generic user‑facing message.

    Parameters
    ----------
    status_code: int
        The HTTP status code to return.
    user_message: str
        A short, non‑technical message that will be sent to the client.
    original: Exception | None
        The original exception (if any) to be logged.
    """
    if original is not None:
        _log_exception(original)
    return HTTPException(status_code=status_code, detail=user_message)


def json_error_response(status_code: int, user_message: str, *, original: Exception | None = None) -> JSONResponse:
    """
    Return a JSONResponse containing a generic error payload.

    The payload format matches the existing endpoints that return a dict
    with ``success`` and ``error`` keys.
    """
    if original is not None:
        _log_exception(original)

    payload: Dict[str, Any] = {"success": False, "error": user_message}
    return JSONResponse(status_code=status_code, content=payload)
