"""Explicit fresh-conversation demand, shared by app and messaging chat."""

import contextvars
import json
import logging
from typing import Any, Dict, Optional, cast
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Import agent_config_context for fallback config access
try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


def _agent_config() -> Optional[Dict[str, Any]]:
    """Retrieve the agent config dict from the context var, or None if unset."""
    try:
        return agent_config_context.get()
    except LookupError:
        return None


def _get_uid(config: Optional[RunnableConfig]) -> str:
    """Extract user ID safely from config or context variable."""
    cfg: Optional[Dict[str, Any]] = cast(Optional[Dict[str, Any]], config)
    if cfg and isinstance(cfg, dict):
        raw_configurable = cfg.get('configurable')
        if isinstance(raw_configurable, dict):
            uid = raw_configurable.get('user_id')
            if isinstance(uid, str) and uid.strip():
                return uid.strip()
    ctx = _agent_config()
    if ctx and isinstance(ctx, dict):
        raw_configurable = ctx.get('configurable')
        if isinstance(raw_configurable, dict):
            uid = raw_configurable.get('user_id')
            if isinstance(uid, str) and uid.strip():
                return uid.strip()
    return ''


def _coerce_int(val: Any, default: int, min_val: int, max_val: int) -> int:
    """Coerce value to int bounded by min_val and max_val, falling back to default."""
    if val is None:
        return default
    try:
        if isinstance(val, (int, float, str)):
            parsed = int(float(val))
            if parsed < min_val:
                return min_val
            if parsed > max_val:
                return max_val
            return parsed
    except (ValueError, TypeError, OverflowError):
        pass
    return default


@tool
def process_recent_conversations(config: RunnableConfig, hours: Any = 6, limit: Any = 20) -> str:
    """Process your recent pending conversations before answering about fresh events.

    Bounded to the last six hours and twenty obligations. Returns progress;
    ready=false means processing is pending and must not be described as complete.
    """
    from utils.conversations.demand_processing import process_recent

    uid = _get_uid(config)
    if not uid:
        raise PermissionError('authenticated owner required')

    safe_hours = _coerce_int(hours, default=6, min_val=1, max_val=6)
    safe_limit = _coerce_int(limit, default=20, min_val=1, max_val=20)

    try:
        return json.dumps(process_recent(uid, hours=safe_hours, limit=safe_limit))
    except PermissionError:
        raise
    except Exception as e:
        logger.warning("Demand processing failed for uid=%s error_type=%s", uid, type(e).__name__)
        return json.dumps({'ready': False, 'status': 'failed', 'error': 'Demand processing temporarily unavailable'})
