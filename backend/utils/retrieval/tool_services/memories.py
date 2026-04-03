"""
Shared service functions for memory retrieval.
Used by both LangChain tools (mobile chat) and REST router (desktop/web).
"""

from datetime import datetime
from typing import Optional

import database.memories as memory_db
import database.vector_db as vector_db
from models.memories import MemoryDB
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

    # Cap limit
    limit = min(limit, 5000)

    # Parse dates
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

    # Fetch
    memories = []
    try:
        memories = memory_db.get_memories(uid, limit=limit, offset=offset, start_date=start_dt, end_date=end_dt)
    except Exception as e:
        logger.error(f"get_memories_text error: {e}")
        return f"Error retrieving memories: {e}"

    # Filter locked
    if memories:
        memories = [m for m in memories if not m.get('is_locked', False)]

    if not memories:
        date_info = ""
        if start_dt and end_dt:
            date_info = f" between {start_dt.strftime('%Y-%m-%d')} and {end_dt.strftime('%Y-%m-%d')}"
        elif start_dt:
            date_info = f" after {start_dt.strftime('%Y-%m-%d')}"
        elif end_dt:
            date_info = f" before {end_dt.strftime('%Y-%m-%d')}"
        return f"No memories found{date_info}."

    # Convert to objects
    memory_objects = []
    for memory_data in memories:
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

    limit = min(limit, 20)

    try:
        matches = vector_db.find_similar_memories(uid, query, threshold=0.0, limit=limit)

        if not matches:
            return f"No memories found matching '{query}'."

        memory_ids = [match.get('memory_id') for match in matches if match.get('memory_id')]
        scores_by_id = {match.get('memory_id'): match.get('score', 0) for match in matches}

        if not memory_ids:
            return f"Found matches but no valid memory IDs for query: '{query}'"

        memories_data = memory_db.get_memories_by_ids(uid, memory_ids)

        # Filter locked
        memories_data = [m for m in memories_data if not m.get('is_locked', False)]
        if not memories_data:
            return f"No memories found matching '{query}'."

        # Format with scores
        memory_objects = []
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
