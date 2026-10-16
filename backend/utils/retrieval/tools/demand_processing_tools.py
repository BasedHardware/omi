"""Explicit fresh-conversation demand, shared by app and messaging chat."""

import json
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool


@tool
def process_recent_conversations(hours: int = 6, limit: int = 20, config: RunnableConfig = None) -> str:
    """Process your recent pending conversations before answering about fresh events.

    Bounded to the last six hours and twenty obligations. Returns progress;
    ready=false means processing is pending and must not be described as complete.
    """
    from utils.conversations.demand_processing import process_recent

    uid = (config or {}).get('configurable', {}).get('user_id')
    if not uid:
        raise PermissionError('authenticated owner required')
    return json.dumps(process_recent(uid, hours=hours, limit=limit))
