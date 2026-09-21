from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from typing import Any

from ..error_handler import http_exception
from ..logger import logger
from ..slack_client import SlackClient

router = APIRouter()


@router.get("/auth")
async def auth_route(state: str = "", code: str = "") -> Any:
    """
    OAuth entry point for the Slack app.

    On success the user is redirected to the front‑end; on failure a
    generic HTTP 500 error is returned without leaking internal details.
    """
    try:
        # Assume SlackClient handles the OAuth flow.
        client = SlackClient()
        await client.complete_oauth(state=state, code=code)
        # Redirect to a configured success page (placeholder here).
        return RedirectResponse(url="/")
    except Exception as e:  # pragma: no cover – exercised via tests
        # Log and raise a generic error.
        raise http_exception(
            status_code=500,
            user_message="OAuth initialization failed",
            original=e,
        )
