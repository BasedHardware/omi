from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..error_handler import json_error_response
from ..slack_client import SlackClient

router = APIRouter()


@router.post("/update-channel")
async def update_channel(request: Request) -> JSONResponse:
    """
    Update a Slack channel configuration.

    Returns a generic error payload on any exception.
    """
    try:
        payload = await request.json()
        client = SlackClient()
        await client.update_channel(payload)
        return JSONResponse(content={"success": True})
    except Exception as e:  # pragma: no cover – exercised via tests
        return json_error_response(
            status_code=500,
            user_message="Internal server error",
            original=e,
        )
