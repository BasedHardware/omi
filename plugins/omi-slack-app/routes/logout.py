import logging
from fastapi import APIRouter, HTTPException, status
from ..error_handler import log_and_raise_500

router = APIRouter()
_logger = logging.getLogger("omi_slack_app.logout")

@router.post("/logout")
async def logout():
    try:
        # Placeholder for logout logic
        return {"success": True}
    except Exception as e:
        _logger.error("Logout failed", exc_info=e)
        raise log_and_raise_500(e)
