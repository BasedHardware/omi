"""
Tools for learning and saving user preferences during conversation.
"""

import contextvars
import uuid
from datetime import datetime, timezone

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

import database.memories as memory_db
import database.vector_db as vector_db
import logging
from models.memories import MemoryDB

logger = logging.getLogger(__name__)

# Import agent_config_context for fallback config access
try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


def _get_uid(config: RunnableConfig) -> str:
    """Extract user ID from config or context variable."""
    if config and 'configurable' in config:
        uid = config['configurable'].get('user_id')
        if uid:
            return uid
    ctx = agent_config_context.get()
    if ctx and 'configurable' in ctx:
        return ctx['configurable'].get('user_id', '')
    return ''


@tool
def save_user_preference_tool(preference: str, config: RunnableConfig = None) -> str:
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

    # Check for duplicate preferences via semantic search
    try:
        existing = vector_db.find_similar_memories(uid, preference, threshold=0.90, limit=3)
        if existing:
            content = existing[0].get('content', '')
            score = existing[0].get('score', 0)
            logger.info(f"Skipping duplicate preference (score={score:.2f}): {content[:80]}")
            return f"Similar preference already exists: {content}"
    except Exception as e:
        logger.warning(f"Could not check for duplicate preferences: {e}")

    now = datetime.now(timezone.utc)
    memory_id = str(uuid.uuid4())
    memory_data = {
        'id': memory_id,
        'uid': uid,
        'content': preference,
        'category': 'system',
        'manually_added': False,
        'created_at': now,
        'updated_at': now,
        'reviewed': False,
        'visibility': 'private',
        'tags': ['agent-learned'],
    }
    memory_data['scoring'] = MemoryDB.calculate_score(MemoryDB.model_validate(memory_data))

    try:
        memory_db.create_memory(uid, memory_data)
        logger.info(f"Saved user preference: {preference[:80]}")
        return f"Preference saved: {preference}"
    except Exception as e:
        logger.error(f"Failed to save preference: {e}")
        return f"Error saving preference: {str(e)}"
