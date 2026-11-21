"""Explicit fresh-conversation demand, shared by app and messaging chat."""

import json
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _get_user_id(config: Any) -> str:
    if not isinstance(config, dict):
        raise PermissionError('authenticated owner required')
    configurable = config.get('configurable')
    if not isinstance(configurable, dict):
        raise PermissionError('authenticated owner required')
    uid = configurable.get('user_id')
    if not isinstance(uid, str) or not uid:
        raise PermissionError('authenticated owner required')
    return uid


@tool
def process_recent_conversations(config: RunnableConfig, hours: int = 6, limit: int = 20) -> str:
    """Process your recent pending conversations before answering about fresh events.

    Bounded to the last six hours and twenty obligations. Returns progress;
    ready=false means processing is pending and must not be described as complete.
    """
    from utils.conversations.demand_processing import process_recent

    uid = _get_user_id(config)
    try:
        clean_hours = int(hours)
    except (TypeError, ValueError):
        clean_hours = 6
    try:
        clean_limit = int(limit)
    except (TypeError, ValueError):
        clean_limit = 20

    clean_hours = max(1, min(6, clean_hours))
    clean_limit = max(1, min(20, clean_limit))

    try:
        res = process_recent(uid, hours=clean_hours, limit=clean_limit)
        return json.dumps(res)
    except Exception as e:
        logger.error("Failed to process recent conversations for user %s: %s", uid, type(e).__name__, exc_info=True)
        return json.dumps({'error': 'Failed to process recent conversations', 'ready': False})
