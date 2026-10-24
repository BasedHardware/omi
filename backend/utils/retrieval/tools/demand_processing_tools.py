"""Explicit fresh-conversation demand, shared by app and messaging chat."""

import json
from typing import Any
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool


def _get_user_id(config: Any) -> str:
    if not isinstance(config, dict):
        raise PermissionError('authenticated owner required')
    configurable = config.get('configurable')
    uid = configurable.get('user_id') if isinstance(configurable, dict) else config.get('user_id')
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

    bounded_hours = max(1, min(clean_hours, 6))
    bounded_limit = max(1, min(clean_limit, 20))

    try:
        return json.dumps(process_recent(uid, hours=bounded_hours, limit=bounded_limit))
    except Exception as e:
        return json.dumps({'error': str(e), 'ready': False})
