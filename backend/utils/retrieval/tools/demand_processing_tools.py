"""Explicit fresh-conversation demand, shared by app and messaging chat."""

import contextvars
import json
import logging
from typing import Any, Dict, Optional, cast
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Fallback agent context var access
try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


def _agent_config() -> Optional[Dict[str, Any]]:
    """Retrieve agent config dict from context var, or None if unset."""
    try:
        return agent_config_context.get()
    except LookupError:
        return None


def _coerce_int(value: Any, default: int, min_val: int, max_val: int) -> int:
    """Safely coerce value to int within [min_val, max_val] range."""
    try:
        if isinstance(value, str):
            coerced = int(float(value.strip()))
        elif isinstance(value, (int, float)):
            coerced = int(value)
        else:
            return default
        return max(min_val, min(coerced, max_val))
    except (ValueError, TypeError, OverflowError):
        return default


def _extract_user_id(config: Optional[Any]) -> Optional[str]:
    """Extract authenticated user ID supporting standard and alternative config structures."""
    cfg: Optional[Dict[str, Any]] = cast(Optional[Dict[str, Any]], config)
    if cfg is None:
        cfg = _agent_config()
    if not isinstance(cfg, dict):
        return None

    raw_configurable = cfg.get('configurable')
    if isinstance(raw_configurable, dict):
        uid = raw_configurable.get('user_id') or raw_configurable.get('uid')
        if isinstance(uid, str) and uid.strip():
            return uid.strip()

    top_uid = cfg.get('user_id') or cfg.get('uid')
    if isinstance(top_uid, str) and top_uid.strip():
        return top_uid.strip()

    return None


@tool
def process_recent_conversations(
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]
    hours: int = 6,
    limit: int = 20,
) -> str:
    """Process your recent pending conversations before answering about fresh events.

    Bounded to the last six hours and twenty obligations. Returns progress;
    ready=false means processing is pending and must not be described as complete.
    """
    from utils.conversations.demand_processing import process_recent

    uid = _extract_user_id(config)
    if not isinstance(uid, str) or not uid:
        raise PermissionError('authenticated owner required')

    clamped_hours = _coerce_int(hours, default=6, min_val=1, max_val=6)
    clamped_limit = _coerce_int(limit, default=20, min_val=1, max_val=20)

    try:
        return json.dumps(process_recent(uid, hours=clamped_hours, limit=clamped_limit))
    except Exception as e:
        logger.warning(f"Error during demand processing for user {uid}: {e}")
        return json.dumps({'ready': False, 'status': 'error', 'error': str(e)})
