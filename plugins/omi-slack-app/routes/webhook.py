from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from ..error_handler import http_exception
from ..slack_client import SlackClient

router = APIRouter()


@router.post("/webhook")
async def webhook(request: Request) -> JSONResponse:
    """
    Receive Slack event payloads.

    Invalid JSON results in a generic 400 error without echoing the
    original parsing exception.
    """
    try:
        payload = await request.json()
    except Exception as e:  # pragma: no cover – exercised via tests
        raise http_exception(
            status_code=400,
            user_message="Invalid JSON payload",
            original=e,
        )

    try:
        client = SlackClient()
        await client.handle_event(payload)
        return JSONResponse(content={"ok": True})
    except Exception as e:  # pragma: no cover – exercised via tests
        raise http_exception(
            status_code=500,
            user_message="Failed to process webhook event",
            original=e,
        )
