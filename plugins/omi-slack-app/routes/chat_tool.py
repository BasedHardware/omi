import logging
from fastapi import APIRouter, HTTPException, status
from ..error_handler import log_and_raise_500
from ..slack_client import SlackClient

router = APIRouter()
_logger = logging.getLogger("omi_slack_app.chat_tool")
_slack_client = SlackClient()

@router.post("/api/send_message")
async def send_message(payload: dict):
    try:
        await _slack_client.send_message(
            channel=payload["channel"],
            text=payload["text"]
        )
        return {"success": True}
    except Exception as e:
        _logger.error("Failed to send Slack message", exc_info=e)
        raise log_and_raise_500(e)

@router.post("/api/search_messages")
async def search_messages(payload: dict):
    try:
        results = await _slack_client.search_messages(query=payload["query"])
        return {"messages": results}
    except Exception as e:
        _logger.error("Failed to search Slack messages", exc_info=e)
        raise log_and_raise_500(e)

@router.post("/api/search_channels")
async def search_channels(payload: dict):
    try:
        results = await _slack_client.search_channels(query=payload["query"])
        return {"channels": results}
    except Exception as e:
        _logger.error("Failed to search Slack channels", exc_info=e)
        raise log_and_raise_500(e)
