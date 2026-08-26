"""
Tools for learning and saving user preferences during conversation.
"""

import contextvars
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, cast

from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]  # langchain @tool decorator partially typed
from langchain_core.runnables import RunnableConfig

from database._client import db
import logging
from models.memories import MemoryDB
from utils.memory.canonical_memory_adapter import search_canonical_memories
from utils.memory.memory_service import MemoryService
from utils.memory.memory_system import MemorySystem
from testing.parity_pack_v0.live_capture import capture_memory_write

logger = logging.getLogger(__name__)

PREFERENCE_DUPLICATE_THRESHOLD = 0.90


def preference_duplicate_message(preference: str, hits: Optional[list]) -> Optional[str]:
    """Return a skip message when hits prove a duplicate preference.

    Scoreless canonical search hits must not suppress unrelated preferences.
    Exact normalized content matches always count; numeric scores only count when
    the search result actually carries a relevance field.
    """
    preferred = " ".join((preference or "").split()).casefold()
    for hit in hits or []:
        raw_score = hit.get("score", hit.get("relevance_score", hit.get("vector_score")))
        content = str(hit.get("content") or "")
        normalized = " ".join(content.split()).casefold()
        if preferred and normalized == preferred:
            return f"Similar preference already exists: {content}"
        if raw_score is None:
            continue
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            continue
        if score >= PREFERENCE_DUPLICATE_THRESHOLD:
            return f"Similar preference already exists: {content}"
    return None


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


def _get_uid(config: RunnableConfig) -> str:
    """Extract user ID from config or context variable."""
    cfg: Optional[Dict[str, Any]] = cast(Optional[Dict[str, Any]], config)
    if cfg and 'configurable' in cfg:
        raw_configurable = cfg.get('configurable')
        if isinstance(raw_configurable, dict):
            configurable: Dict[str, Any] = cast(Dict[str, Any], raw_configurable)
            uid = configurable.get('user_id')
            if uid:
                return uid
    ctx = _agent_config()
    if ctx and 'configurable' in ctx:
        raw_configurable = ctx.get('configurable')
        if isinstance(raw_configurable, dict):
            configurable = cast(Dict[str, Any], raw_configurable)
            return configurable.get('user_id', '')
    return ''


@tool
def save_user_preference_tool(preference: str, config: RunnableConfig = None) -> str:  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
    """Save a learned user preference or personal detail for future conversations.

    Call this when you learn something about the user's preferences, habits, or
    personal details that would be useful to remember across conversations. Examples:
    - "Prefers Google Calendar over Outlook"
    - "Default meeting length is 30 minutes"
    - "Works at Acme Corp as a product manager"
    - "Prefers metric units over imperial"

    Do NOT save ephemeral information (today's mood, current task).
    Do NOT save something already known from existing memories.
    Do NOT ask for confirmation — just save it silently when you learn it.

    Args:
        preference: A clear, concise statement of the preference or personal detail.
    """
    uid = _get_uid(config)
    if not uid:
        return "Error: Could not determine user ID"

    # Duplicate check must not treat scoreless/synthetic positional hits as
    # semantic matches. Canonical search currently returns no relevance score;
    # until real scores are plumbed through, only suppress exact normalized
    # duplicates so unrelated top hits cannot block a new preference.
    try:
        hits = search_canonical_memories(uid, preference, limit=3, db_client=db)
        duplicate = preference_duplicate_message(preference, hits)
        if duplicate:
            content = duplicate.rsplit(": ", 1)[-1]
            logger.info("Skipping duplicate preference: %s", content[:80])
            return duplicate
    except Exception as e:
        logger.warning(f"Could not check for duplicate preferences: {e}")

    now = datetime.now(timezone.utc)
    memory_id = str(uuid.uuid4())
    memory_data = {
        "id": memory_id,
        "uid": uid,
        "content": preference,
        "category": "system",
        "manually_added": False,
        "created_at": now,
        "updated_at": now,
        "reviewed": False,
        "visibility": "private",
        "tags": ["agent-learned"],
    }
    memory_data["scoring"] = MemoryDB.calculate_score(MemoryDB.model_validate(memory_data))

    try:
        MemoryService(db_client=db).create_external_memory(
            uid,
            MemoryDB.model_validate(memory_data),
            memory_system=MemorySystem.CANONICAL,
            consumer="agent_preference",
            operation="save_user_preference",
            upsert_vector=False,
            require_canonical_promotion=True,
        )
        capture_memory_write(
            principal_id=uid,
            source="agent_preference_memory_create",
            session_id=memory_id,
            memories=[memory_data],
        )
        logger.info(f"Saved user preference: {preference[:80]}")
        return f"Preference saved: {preference}"
    except Exception as e:
        logger.error(f"Failed to save preference: {e}")
        return f"Error saving preference: {str(e)}"
