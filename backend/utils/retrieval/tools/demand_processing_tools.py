"""Explicit fresh-conversation demand, shared by app and messaging chat."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)


def _resolve_uid(config: RunnableConfig | None) -> Optional[str]:
    """Safely extract user ID from nested configurable or top-level config."""
    if not config or not isinstance(config, dict):
        return None
    configurable = config.get('configurable')
    if isinstance(configurable, dict):
        uid = configurable.get('user_id') or configurable.get('uid')
        if isinstance(uid, str) and uid.strip():
            return uid.strip()
    top_uid = config.get('user_id') or config.get('uid')
    if isinstance(top_uid, str) and top_uid.strip():
        return top_uid.strip()
    return None


@tool
def process_recent_conversations(
    hours: int = 6,
    limit: int = 20,
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
) -> str:
    """Process your recent pending conversations before answering about fresh events.

    Bounded to the last six hours and twenty obligations. Returns progress;
    ready=false means processing is pending and must not be described as complete.
    """
    from utils.conversations.demand_processing import process_recent

    uid = _resolve_uid(config)
    if not uid:
        raise PermissionError('authenticated owner required')

    # Coerce and bound hours (bounded to 1-6 hours)
    try:
        hours_val = int(hours) if hours is not None else 6
    except (ValueError, TypeError):
        hours_val = 6
    hours_val = max(1, min(6, hours_val))

    # Coerce and bound limit (bounded to 1-20 obligations)
    try:
        limit_val = int(limit) if limit is not None else 20
    except (ValueError, TypeError):
        limit_val = 20
    limit_val = max(1, min(20, limit_val))

    try:
        res = process_recent(uid, hours=hours_val, limit=limit_val)
        return json.dumps(res)
    except Exception as exc:
        logger.exception("process_recent_conversations failed uid=%s: %s", sanitize(str(uid)), sanitize(str(exc)))
        return json.dumps({"ready": False, "error": "Unable to process recent conversations right now."})
