from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..error_handler import json_error_response
from ..slack_client import SlackClient

router = APIRouter()


@router.post("/api/send_message")
async def send_message(request: Request) -> JSONResponse:
    """
    Chat‑tool endpoint used by the front‑end to send a message to Slack.
    """
    try:
        payload = await request.json()
        client = SlackClient()
        await client.send_message(payload)
        return JSONResponse(content={"success": True})
    except Exception as e:  # pragma: no cover – exercised via tests
        return json_error_response(
            status_code=500,
            user_message="Internal server error",
            original=e,
        )


@router.post("/api/search_messages")
async def search_messages(request: Request) -> JSONResponse:
    """
    Search Slack messages.
    """
    try:
        payload = await request.json()
        client = SlackClient()
        results = await client.search_messages(payload)
        return JSONResponse(content={"success": True, "results": results})
    except Exception as e:  # pragma: no cover – exercised via tests
        return json_error_response(
            status_code=500,
            user_message="Internal server error",
            original=e,
        )


@router.post("/api/search_channels")
async def search_channels(request: Request) -> JSONResponse:
    """
    Search Slack channels.
    """
    try:
        payload = await request.json()
        client = SlackClient()
        results = await client.search_channels(payload)
        return JSONResponse(content={"success": True, "results": results})
    except Exception as e:  # pragma: no cover – exercised via tests
        return json_error_response(
            status_code=500,
            user_message="Internal server error",
            original=e,
        )
