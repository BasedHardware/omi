import logging
from fastapi import HTTPException, status

_logger = logging.getLogger("omi_slack_app")

def log_and_raise_500(exc: Exception) -> HTTPException:
    """
    Log the full exception (including traceback) and raise a generic 500 error.
    """
    _logger.error("Internal server error in OMI Slack app", exc_info=exc)
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal server error",
    )

def log_and_raise_400(message: str, exc: Exception) -> HTTPException:
    """
    Log the exception and raise a generic 400 error with a safe message.
    """
    _logger.error(message, exc_info=exc)
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=message,
    )
