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
from models.memories import MemoryDB, MemoryCategory

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

    # Use MemoryDB.calculate_score so scoring always matches Firestore-created memories
    # system category → cat_boost = 999 - CATEGORY_BOOSTS['system'] = 999 - 0 = 999
    scoring = MemoryDB.calculate_score(
        MemoryDB(
            id=memory_id,
            uid=uid,
            content=preference,
            category=MemoryCategory.system,
            created_at=now,
            updated_at=now,
            manually_added=False,
        )
    )

    memory_data = {
        'id': memory_id,
        'content': preference,
        'category': 'system',
        'manually_added': False,
        'created_at': now,
        'updated_at': now,
        'reviewed': False,
        'visibility': 'private',
        'tags': ['agent-learned'],
        'scoring': scoring,            # Bug 2 fix: was missing
    }

    try:
        memory_db.create_memory(uid, memory_data)
        logger.info(f"Saved user preference to Firestore: {preference[:80]}")
    except Exception as e:
        logger.error(f"Failed to save preference to Firestore: {e}")
        return f"Error saving preference: {str(e)}"

    # Bug 1 fix: this call was completely missing before
    # Without it the memory exists in Firestore but is invisible to
    # search_memories_tool (vector search) and hidden in get_memories listings.
    try:
        vector_db.upsert_memory_vector(uid, memory_id, preference, 'system')
        logger.info(f"Upserted memory vector for: {preference[:80]}")
    except Exception as e:
        # Non-fatal: memory is persisted; search won't find it until re-embedding
        logger.error(f"Failed to upsert memory vector (memory saved, search delayed): {e}")

    return f"Preference saved: {preference}"
