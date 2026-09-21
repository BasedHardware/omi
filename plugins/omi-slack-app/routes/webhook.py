import json
import logging
from fastapi import APIRouter, HTTPException, Request, status
from ..error_handler import log_and_raise_400, log_and_raise_500

router = APIRouter()
_logger = logging.getLogger("omi_slack_app.webhook")

@router.post("/webhook")
async def slack_event(request: Request):
    try:
        payload = await request.json()
    except Exception as e:
        # Previously leaked raw JSON error
        raise log_and_raise_400("Invalid JSON payload", e)

    try:
        # Placeholder for processing the Slack event payload
        return {"ok": True}
    except Exception as e:
        raise log_and_raise_500(e)
