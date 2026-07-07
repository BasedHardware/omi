"""
Shared service functions for memory retrieval.
Used by both LangChain tools (mobile chat) and REST router (desktop/web).
"""

from typing import Optional, Any, Dict, List, cast

import database.memories as memory_db
import database.vector_db as vector_db
from database._client import db as firestore_db
from models.memories import MemoryDB
from utils.memory.memory_service import MemoryService
from utils.memory.memory_system import MemorySystem
from utils.memory.surface_routing import pin_memory_system
from utils.memory.chat_memory_adapter import (
    list_default_chat_memories_decision_text,
    search_memory_default_chat_memories_vector_decision_text,
)
from utils.memory.default_read_rollout import MemoryReadDecision
from utils.retrieval.tool_services.conversations import parse_iso_date
import logging

logger = logging.getLogger(__name__)


def get_memories_text(
    uid: str,
    limit: int = 50,
    offset: int = 0,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """Fetch user memories/facts and format as LLM-ready text."""
    logger.info(f"get_memories_text - uid: {uid}, limit: {limit}, offset: {offset}")

    # Cap request bounds before either memory or legacy reads.
    limit = max(1, min(limit, 5000))
    offset = max(0, offset)

    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = parse_iso_date(start_date, 'start_date')
        except ValueError as e:
            return f"Error: Invalid start_date format: {e}"
    if end_date:
        try:
            end_dt = parse_iso_date(end_date, 'end_date')
        except ValueError as e:
            return f"Error: Invalid end_date format: {e}"

    memory_system = pin_memory_system(uid, db_client=firestore_db)
    if memory_system == MemorySystem.CANONICAL:
        memories = MemoryService(db_client=firestore_db).read(uid, limit=limit, offset=offset)
        if start_dt or end_dt:
            filtered: List[MemoryDB] = []
            for memory in memories:
                created = memory.created_at
                if start_dt and created and created < start_dt:
                    continue
                if end_dt and created and created > end_dt:
                    continue
                filtered.append(memory)
            memories = filtered
        if not memories:
            return "No memories found."
        return f"User Memories ({len(memories)} total):\n\n{MemoryDB.get_memories_as_str(memories)}".strip()

    default_memories = list_default_chat_memories_decision_text(
        uid=uid,
        limit=limit,
        offset=offset,
        db_client=firestore_db,
        allow_legacy_safe_fallback=True,
    )
    if default_memories.read_decision == MemoryReadDecision.USE_MEMORY:
        logger.info("get_memories_text - using memory default chat memory list results")
        return default_memories.text or "No memory default memories found."
    if default_memories.read_decision != MemoryReadDecision.USE_LEGACY_SAFE:
        logger.info(
            "get_memories_text - memory default memory list denied without legacy fallback: "
            f"{default_memories.fallback_reason}"
        )
        return default_memories.text or "No memories available for this request."

    # Fetch
    memories_data: List[Dict[str, Any]] = []
    try:
        memories_data = memory_db.get_memories(uid, limit=limit, offset=offset, start_date=start_dt, end_date=end_dt)
    except Exception as e:
        logger.error(f"get_memories_text error: {e}")
        return f"Error retrieving memories: {e}"

    # Filter locked
    if memories_data:
        memories_data = [m for m in memories_data if not m.get('is_locked', False)]

    if not memories_data:
        date_info = ""
        if start_dt and end_dt:
            date_info = f" between {start_dt.strftime('%Y-%m-%d')} and {end_dt.strftime('%Y-%m-%d')}"
        elif start_dt:
            date_info = f" after {start_dt.strftime('%Y-%m-%d')}"
        elif end_dt:
            date_info = f" before {end_dt.strftime('%Y-%m-%d')}"
        return f"No memories found{date_info}."

    # Convert to objects
    memory_objects: List[MemoryDB] = []
    for memory_data in memories_data:
        try:
            memory_objects.append(MemoryDB(**memory_data))
        except Exception as e:
            logger.error(f"Error creating MemoryDB object: {e}")
            continue

    if not memory_objects:
        return "Error: Could not parse memories data"

    result = f"User Memories ({len(memory_objects)} total):\n\n"
    result += MemoryDB.get_memories_as_str(memory_objects)
    return result.strip()


def search_memories_text(
    uid: str,
    query: str,
    limit: int = 5,
) -> str:
    """Semantic vector search for memories, formatted as LLM-ready text."""
    logger.info(f"search_memories_text - uid: {uid}, query: {query}, limit: {limit}")

    limit = max(1, min(limit, 20))

    memory_system = pin_memory_system(uid, db_client=firestore_db)
    if memory_system == MemorySystem.CANONICAL:
        matches = MemoryService(db_client=firestore_db).search(uid, query, limit=limit)
        if not matches:
            return f"No memories found matching '{query}'."
        result = f"Found {len(matches)} memories matching '{query}':\n\n"
        for match in matches:
            memory = match.memory
            date_str = memory.created_at.strftime('%Y-%m-%d') if memory.created_at else 'Unknown'
            result += (
                f"- {memory.content} (relevance: {match.score:.2f}, "
                f"category: {memory.category.value}, date: {date_str})\n"
            )
        return result.strip()

    default_memories = search_memory_default_chat_memories_vector_decision_text(
        uid=uid,
        query=query,
        limit=limit,
        db_client=firestore_db,
        allow_legacy_safe_fallback=True,
    )
    if default_memories.read_decision == MemoryReadDecision.USE_MEMORY:
        logger.info("search_memories_text - using memory default chat vector memory results")
        return default_memories.text or f"No memory vector memories found matching '{query}'."
    if default_memories.read_decision != MemoryReadDecision.USE_LEGACY_SAFE:
        logger.info(
            "search_memories_text - memory default memory vector search denied without legacy fallback: "
            f"{default_memories.fallback_reason}"
        )
        return default_memories.text or "No memories available for this request."

    try:
        matches = vector_db.find_similar_memories(uid, query, threshold=0.0, limit=limit)

        if not matches:
            return f"No memories found matching '{query}'."

        memory_ids = [cast(str, match.get('memory_id')) for match in matches if match.get('memory_id')]
        scores_by_id = {match.get('memory_id'): match.get('score', 0) for match in matches}

        if not memory_ids:
            return f"Found matches but no valid memory IDs for query: '{query}'"

        memories_data = memory_db.get_memories_by_ids(uid, memory_ids)

        # Filter locked
        memories_data = [m for m in memories_data if not m.get('is_locked', False)]
        if not memories_data:
            return f"No memories found matching '{query}'."

        # Format with scores
        memory_objects: List[Dict[str, Any]] = []
        for memory_data in memories_data:
            try:
                memory_obj = MemoryDB(**memory_data)
                score = scores_by_id.get(memory_data.get('id'), 0)
                memory_objects.append({'memory': memory_obj, 'score': score})
            except Exception as e:
                logger.error(f"Error creating MemoryDB object: {e}")
                continue

        if not memory_objects:
            return f"Found matches but could not retrieve memory details for query: '{query}'"

        result = f"Found {len(memory_objects)} memories matching '{query}':\n\n"
        for item in memory_objects:
            memory = item['memory']
            score = item['score']
            date_str = memory.created_at.strftime('%Y-%m-%d') if memory.created_at else 'Unknown'
            result += (
                f"- {memory.content} (relevance: {score:.2f}, category: {memory.category.value}, date: {date_str})\n"
            )

        return result.strip()

    except Exception as e:
        logger.error(f"search_memories_text error: {e}")
        return f"Error searching memories: {e}"
