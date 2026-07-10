"""
Tools for accessing user memories and facts.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, cast
import contextvars

from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]  # langchain @tool decorator partially typed
from langchain_core.runnables import RunnableConfig

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
from utils.retrieval.hybrid import rrf_rerank
from utils.retrieval.tools.result_bounds import cap_items_for_llm, bounded_result
import logging

logger = logging.getLogger(__name__)

# A broad question ("what do you know about me") can match every memory a user has. Formatting
# all of them floods the chat model's context, so it freezes or refuses (#4927). Bound how many
# are handed to the model at once; the most recent are kept.
MAX_MEMORIES_FOR_LLM = 300

# Import agent_config_context for fallback config access
try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    # Fallback if import fails
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


def _agent_config() -> Optional[Dict[str, Any]]:
    """Retrieve the agent config dict from the context var, or None if unset."""
    try:
        return agent_config_context.get()
    except LookupError:
        return None


@tool
def get_memories_tool(
    limit: int = 50,
    offset: int = 0,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
) -> str:
    """
    Retrieve structured FACTS and PREFERENCES about the user (NOT events/incidents).

    Memories are STATIC FACTS about the user (name, age, preferences, habits, goals, relationships)
    that the system has learned over time. This is DIFFERENT from events/incidents that happened.

    **CRITICAL DISTINCTION - Use the right tool:**
    - "What's my favorite food?" → USE THIS TOOL (preference/fact)
    - "When did I get food poisoning?" → DO NOT USE THIS - use search_conversations_tool (event)
    - "Do I like dogs?" → USE THIS TOOL (preference)
    - "When did a dog bite me?" → DO NOT USE THIS - use search_conversations_tool (event)
    - "What are my hobbies?" → USE THIS TOOL (facts about user)
    - "What happened at the party?" → DO NOT USE THIS - use search_conversations_tool (event)

    Use this tool ONLY when:
    - User asks "what do you know about me?" or "tell me about my preferences"
    - You need background context about the user's preferences to personalize responses
    - User asks about their interests, goals, habits, or relationships (static facts)
    - Questions like "do I like X?", "what's my favorite Y?", "what are my Z?"

    DO NOT use this tool when:
    - User asks about specific events/incidents (use search_conversations_tool instead)
    - Questions like "when did X happen?", "what happened at Y?", "when did I get Z?"

    Memory retrieval guidance - choosing the right limit:
    - For broad questions about the user ("what do you know about me", "tell me about myself",
      "who am I", "what are all my interests"), use a high limit (e.g. 300) to get a comprehensive
      set of facts.
    - For specific questions about a single narrow topic ("what do I know about machine learning"),
      use limit=50-200.
    - For a very large memory bank the result is automatically capped to the most relevant memories
      so it cannot overflow context; summarize what is returned and offer to narrow to a specific
      topic if the user needs more.
    - Use the offset parameter to page through additional memories when needed.

    Args:
        limit: Number of memories to retrieve (default: 50, recommended: 50-200, max per call: 5000)
        offset: Pagination offset for retrieving additional memories beyond the limit (default: 0)
        start_date: Filter memories after this date (ISO format in user's timezone: YYYY-MM-DDTHH:MM:SS+HH:MM, e.g. "2024-01-19T15:00:00-08:00")
        end_date: Filter memories before this date (ISO format in user's timezone: YYYY-MM-DDTHH:MM:SS+HH:MM, e.g. "2024-01-19T23:59:59-08:00")

    Returns:
        Formatted list of facts about the user with categories, dates, and emoji representations.
    """
    logger.info(
        f"🔧 get_memories_tool called - limit: {limit}, offset: {offset}, start_date: {start_date}, end_date: {end_date}"
    )

    # Get config from parameter or context variable (like other tools do)
    cfg: Optional[Dict[str, Any]] = cast(Optional[Dict[str, Any]], config)
    if cfg is None:
        cfg = _agent_config()
        if cfg:
            logger.info(f"🔧 get_memories_tool - got config from context variable")

    if cfg is None:
        logger.info(f"❌ get_memories_tool - config is None")
        return "Error: Configuration not available"

    try:
        configurable: Any = cfg.get('configurable')
        uid = configurable.get('user_id')
    except (KeyError, TypeError, AttributeError) as e:
        logger.error(f"❌ get_memories_tool - error accessing config: {e}")
        return "Error: Configuration not available"

    if not uid:
        logger.info(f"❌ get_memories_tool - no user_id in config")
        return "Error: User ID not found in configuration"
    logger.info(f"✅ get_memories_tool - uid: {uid}, limit: {limit}")

    # Cap at 5000 per call to prevent overloading context
    if limit > 5000:
        logger.info(f"⚠️ get_memories_tool - limit capped from {limit} to 5000")
        limit = 5000

    # Parse dates if provided (must be ISO format with timezone)
    start_dt = None
    end_dt = None

    if start_date:
        try:
            # Parse ISO format with timezone - should be in user's timezone (YYYY-MM-DDTHH:MM:SS+HH:MM)
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            if start_dt.tzinfo is None:
                return f"Error: start_date must include timezone in user's timezone format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-19T15:00:00-08:00'): {start_date}"
            logger.info(f"📅 Parsed start_date '{start_date}' as {start_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        except ValueError as e:
            return f"Error: Invalid start_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone: {start_date} - {str(e)}"

    if end_date:
        try:
            # Parse ISO format with timezone - should be in user's timezone (YYYY-MM-DDTHH:MM:SS+HH:MM)
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            if end_dt.tzinfo is None:
                return f"Error: end_date must include timezone in user's timezone format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-19T23:59:59-08:00'): {end_date}"
            logger.info(f"📅 Parsed end_date '{end_date}' as {end_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        except ValueError as e:
            return f"Error: Invalid end_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone: {end_date} - {str(e)}"

    memory_system = pin_memory_system(uid, db_client=firestore_db)
    if memory_system == MemorySystem.CANONICAL:
        service = MemoryService(db_client=firestore_db)
        if start_dt or end_dt:
            # Date filters present: scan raw canonical pages and apply the date
            # bounds before paginating, mirroring the legacy DB path which pushes
            # start_date/end_date into the query. Reading only the first `limit`
            # page and then filtering would miss matching memories that live on
            # later pages.
            max_scan = 5000
            scan_offset = 0
            date_filtered: List[Any] = []
            while scan_offset < max_scan:
                batch = service.read(uid, limit=500, offset=scan_offset)
                if not batch:
                    break
                for memory in batch:
                    created = memory.created_at
                    if start_dt and created and created < start_dt:
                        continue
                    if end_dt and created and created > end_dt:
                        continue
                    date_filtered.append(memory)
                scan_offset += len(batch)
                if len(batch) < 500:
                    break
            memories = date_filtered[offset : offset + limit]
        else:
            memories = service.read(uid, limit=limit, offset=offset)
        memories_count = len(memories)
        logger.info(f"📊 get_memories_tool - found {memories_count} canonical memories")
        if memories_count >= 500:
            logger.info(f"⚠️ Large number of memories retrieved ({memories_count}). Consider if all are needed.")
        if not memories:
            date_info = ""
            if start_dt and end_dt:
                date_info = f" between {start_dt.strftime('%Y-%m-%d')} and {end_dt.strftime('%Y-%m-%d')}"
            elif start_dt:
                date_info = f" after {start_dt.strftime('%Y-%m-%d')}"
            elif end_dt:
                date_info = f" before {end_dt.strftime('%Y-%m-%d')}"
            msg = (
                f"No memories found{date_info}. The user may not have any recorded facts or memories yet "
                "in the system, or the date range may be outside their memory history."
            )
            logger.info(f"⚠️ get_memories_tool - {msg}")
            return msg
        result = f"User Memories ({len(memories)} total):\n\n{MemoryDB.get_memories_as_str(memories)}"
        return result.strip()

    default_memories = list_default_chat_memories_decision_text(
        uid=uid,
        limit=limit,
        offset=offset,
        db_client=firestore_db,
    )
    if default_memories.read_decision == MemoryReadDecision.USE_MEMORY:
        logger.info("✅ get_memories_tool - using memory default chat memory list results")
        return default_memories.text or "No memory default memories found."
    if default_memories.read_decision != MemoryReadDecision.USE_LEGACY_SAFE:
        logger.info(
            "🛑 get_memories_tool - memory chat memory list denied without legacy fallback: "
            f"{default_memories.fallback_reason}"
        )
        return default_memories.text or "No memories available for this request."

    # Get memories
    memories: List[Any] = []
    try:
        memories = memory_db.get_memories(uid, limit=limit, offset=offset, start_date=start_dt, end_date=end_dt)
    except Exception as e:
        logger.error(e)

    # Filter out locked memories (paid plan required)
    if memories:
        memories = [m for m in memories if not m.get('is_locked', False)]

    # Bound how many memories are formatted for the chat model so a broad question cannot flood
    # its context and freeze it (#4927). The DB returns newest-first, so this keeps the most recent.
    # A full DB page (len >= limit) means more memories likely exist beyond it, so flag that too so
    # the note is not silently dropped when the model requested a small limit (cubic on #8527).
    db_page = memories or []
    more_in_db = len(db_page) >= limit
    memories, page_count, capped = cap_items_for_llm(db_page, MAX_MEMORIES_FOR_LLM)
    results_truncated = capped or more_in_db
    logger.info(
        f"📊 get_memories_tool - page {page_count} memories, showing {len(memories)}, truncated={results_truncated}"
    )

    if not memories:
        date_info = ""
        if start_dt and end_dt:
            date_info = f" between {start_dt.strftime('%Y-%m-%d')} and {end_dt.strftime('%Y-%m-%d')}"
        elif start_dt:
            date_info = f" after {start_dt.strftime('%Y-%m-%d')}"
        elif end_dt:
            date_info = f" before {end_dt.strftime('%Y-%m-%d')}"

        msg = f"No memories found{date_info}. The user may not have any recorded facts or memories yet in the system, or the date range may be outside their memory history."
        logger.info(f"⚠️ get_memories_tool - {msg}")
        return msg

    # Convert dictionaries to MemoryDB objects for proper formatting
    memory_objects: List[MemoryDB] = []
    for memory_data in memories:
        try:
            memory_objects.append(MemoryDB(**memory_data))
        except Exception as e:
            logger.error(f"Error creating MemoryDB object: {e}")
            continue

    if not memory_objects:
        return "Error: Could not parse memories data"

    # Format memories using the Memory model's string formatter. Label the count as "shown" rather
    # than "total": it is the displayed page, which may be a subset of all the user's memories.
    result = f"User Memories ({len(memory_objects)} shown):\n\n"
    result += MemoryDB.get_memories_as_str(memory_objects)

    return bounded_result(result.strip(), results_truncated, noun="memories")


@tool
def search_memories_tool(
    query: str,
    limit: int = 5,
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
) -> str:
    """
    Search memories using semantic vector search to find relevant facts about the user.

    This tool uses AI embeddings to find memories (facts/preferences) that are semantically
    similar to your query, even if they don't contain the exact keywords.

    **When to use this tool:**
    - Searching for specific facts or preferences about the user
    - Finding memories related to a concept or theme
    - Looking up what the user knows/likes/dislikes about a topic
    - Questions like "what do I know about cooking?", "my preferences for travel"

    **When NOT to use this tool:**
    - For finding when specific events happened (use search_conversations_tool instead)
    - Questions like "when did X happen?", "what happened at Y?"

    **Examples:**
    - "cooking preferences" → finds memories about food, cooking habits
    - "work goals" → finds career-related facts and goals
    - "family members" → finds memories about relationships

    Args:
        query: Natural language description of what to search for (required)
        limit: Number of memories to retrieve (default: 5, max: 20)

    Returns:
        Formatted string with semantically matching memories ranked by relevance.
    """
    logger.info(f"🔧 search_memories_tool called with query: {query}")

    # Get config from parameter or context variable
    cfg: Optional[Dict[str, Any]] = cast(Optional[Dict[str, Any]], config)
    if cfg is None:
        cfg = _agent_config()
        if cfg:
            logger.info(f"🔧 search_memories_tool - got config from context variable")

    if cfg is None:
        logger.info(f"❌ search_memories_tool - config is None")
        return "Error: Configuration not available"

    try:
        configurable: Any = cfg.get('configurable')
        uid = configurable.get('user_id')
    except (KeyError, TypeError, AttributeError) as e:
        logger.error(f"❌ search_memories_tool - error accessing config: {e}")
        return "Error: Configuration not available"

    if not uid:
        logger.info(f"❌ search_memories_tool - no user_id in config")
        return "Error: User ID not found in configuration"
    logger.info(f"✅ search_memories_tool - uid: {uid}, query: {query}, limit: {limit}")

    # Cap limit at 20
    limit = min(limit, 20)

    memory_system = pin_memory_system(uid, db_client=firestore_db)
    if memory_system == MemorySystem.CANONICAL:
        matches = MemoryService(db_client=firestore_db).search(uid, query, limit=limit)
        if not matches:
            msg = (
                f"No memories found matching '{query}'. The user may not have any recorded facts about this topic yet."
            )
            logger.info(f"⚠️ search_memories_tool - {msg}")
            return msg
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
    )
    if default_memories.read_decision == MemoryReadDecision.USE_MEMORY:
        logger.info("✅ search_memories_tool - using memory default chat memory results")
        return default_memories.text or f"No memory vector memories found matching '{query}'."
    if default_memories.read_decision != MemoryReadDecision.USE_LEGACY_SAFE:
        logger.info(
            "🛑 search_memories_tool - memory chat memory denied without legacy fallback: "
            f"{default_memories.fallback_reason}"
        )
        return default_memories.text or "No memories available for this request."

    try:
        # Over-fetch then rerank: pull more vector candidates than we need so the
        # keyword (BM25) signal can promote exact-term matches the vector ranking buried.
        fetch_limit = min(limit * 3, 60)
        matches = vector_db.find_similar_memories(uid, query, threshold=0.0, limit=fetch_limit)

        logger.info(f"📊 search_memories_tool - found {len(matches)} results for query: '{query}'")

        if not matches:
            msg = (
                f"No memories found matching '{query}'. The user may not have any recorded facts about this topic yet."
            )
            logger.info(f"⚠️ search_memories_tool - {msg}")
            return msg

        memory_ids: List[str] = [match.get('memory_id') for match in matches if match.get('memory_id')]  # type: ignore[reportAssignmentType]  # match.get returns Any; filtered to truthy str values
        scores_by_id = {match.get('memory_id'): match.get('score', 0) for match in matches}

        if not memory_ids:
            return f"Found matches but no valid memory IDs for query: '{query}'"

        docs_by_id = {m.get('id'): m for m in memory_db.get_memories_by_ids(uid, memory_ids)}

        # Preserve vector order, and drop locked / rejected / superseded memories so the
        # agent never reasons over a fact that is no longer true.
        candidates: List[Dict[str, Any]] = []
        for mid in memory_ids:
            m = docs_by_id.get(mid)
            if not m:
                continue
            if m.get('is_locked', False) or m.get('user_review') is False or m.get('invalid_at') is not None:
                continue
            candidates.append(
                {
                    'id': m.get('id'),
                    'content': m.get('content', ''),
                    'vector_score': scores_by_id.get(mid, 0),
                    '_doc': m,
                }
            )

        if not candidates:
            return f"No memories found matching '{query}'. The content may require a paid plan to access."

        # Semantic score sets the vector rank; RRF then fuses in the BM25 keyword rank.
        candidates.sort(key=lambda c: c.get('vector_score', 0), reverse=True)
        candidates = rrf_rerank(query, candidates, limit)

        # Convert to MemoryDB objects with scores
        memory_objects: List[Dict[str, Any]] = []
        for cand in candidates:
            try:
                memory_obj = MemoryDB(**cand['_doc'])
                memory_objects.append({'memory': memory_obj, 'score': cand.get('vector_score', 0)})
            except Exception as e:
                logger.error(f"Error creating MemoryDB object: {e}")
                continue

        if not memory_objects:
            return f"Found matches but could not retrieve memory details for query: '{query}'"

        logger.info(f"🔍 search_memories_tool - Loaded {len(memory_objects)} full memories")

        # Format results with relevance scores
        result = f"Found {len(memory_objects)} memories matching '{query}':\n\n"
        for item in memory_objects:
            memory = item['memory']
            score = item['score']
            date_str = memory.created_at.strftime('%Y-%m-%d') if memory.created_at else 'Unknown'
            result += (
                f"- {memory.content} (relevance: {score:.2f}, category: {memory.category.value}, date: {date_str})\n"
            )

        logger.info(f"🔍 search_memories_tool - Generated result string, length: {len(result)}")

        return result.strip()

    except Exception as e:
        error_msg = f"Error performing memory search: {str(e)}"
        logger.info(f"❌ search_memories_tool - {error_msg}")
        import traceback

        traceback.print_exc()
        return f"Error searching memories: {str(e)}"
