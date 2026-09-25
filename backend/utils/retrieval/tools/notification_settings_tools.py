import logging
from typing import Any, Dict, Optional

# Existing imports
# from backend.utils.retrieval.firestore import (
#     set_daily_summary_enabled,
#     get_daily_summary_hour_local,
#     set_daily_summary_hour_local,
# )
# from backend.utils.retrieval.tools import some_other_helpers

logger = logging.getLogger(__name__)

def manage_daily_summary_tool(
    user_id: str,
    enable: Optional[bool] = None,
    hour: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Manage the daily summary settings for a user.

    Parameters
    ----------
    user_id : str
        The unique identifier for the user.
    enable : Optional[bool]
        If provided, enable or disable the daily summary.
    hour : Optional[int]
        If provided, set the local hour for the daily summary.

    Returns
    -------
    Dict[str, Any]
        A dictionary containing the result of the operation. On success,
        the dictionary will contain the updated settings. On failure,
        it will contain an 'error' key with a user‑friendly message.
    """
    result: Dict[str, Any] = {}

    # 1. Handle enable/disable
    if enable is not None:
        try:
            set_daily_summary_enabled(user_id, enable)
            result["enabled"] = enable
        except Exception as exc:  # pragma: no cover
            logger.error(
                f"Failed to set daily summary enabled state for user {user_id}",
                exc_info=True,
            )
            result["error"] = (
                "Failed to update daily summary settings. "
                "Please try again later."
            )
            return result

    # 2. Handle hour setting
    if hour is not None:
        try:
            set_daily_summary_hour_local(user_id, hour)
            result["hour"] = hour
        except Exception as exc:  # pragma: no cover
            logger.error(
                f"Failed to set daily summary hour for user {user_id}",
                exc_info=True,
            )
            result["error"] = (
                "Failed to update daily summary hour. "
                "Please try again later."
            )
            return result

    # 3. Retrieve current hour if requested
    if hour is None:
        try:
            current_hour = get_daily_summary_hour_local(user_id)
            result["hour"] = current_hour
        except Exception as exc:  # pragma: no cover
            logger.error(
                f"Failed to retrieve daily summary hour for user {user_id}",
                exc_info=True,
            )
            result["error"] = (
                "Failed to retrieve daily summary hour. "
                "Please try again later."
            )
            return result

    return result
