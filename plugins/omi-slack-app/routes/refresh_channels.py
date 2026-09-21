from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..error_handler import json_error_response
from ..slack_client import SlackClient

router = APIRouter()


@router.post("/refresh-channels")
async def refresh_channels() -> JSONResponse:
    """
    Refresh the list of Slack channels known to the app.

    Returns a generic error payload on any exception.
    """
    try:
        client = SlackClient()
        await client.refresh_channels()
        return JSONResponse(content={"success": True})
    except Exception as e:  # pragma: no cover – exercised via tests
        return json_error_response(
            status_code=500,
            user_message="Internal server error",
            original=e,
        )
