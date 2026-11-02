"""
Tools for accessing user memories and facts.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast
import contextvars

from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]  # langchain @tool decorator partially typed
from langchain_core.runnables import RunnableConfig

from database._client import db as firestore_db
from models.memories import MemoryDB
from utils.memory.memory_service import MemoryService
from utils.model_text import format_date, format_instant, lookup_failed, truncation_note
from utils.user_clock import clock_for_config
from utils.messaging.memory_privacy import (
    channel_private_filter_active,
    is_channel_private_memory,
    omit_channel_private,
)
from utils.retrieval.chat_scope import apply_chat_scope_dates, chat_scope_from_config
from utils.retrieval.turn_refs import register_record_ref
from utils.retrieval.memory_evidence import MAX_MEMORY_EVIDENCE_CHARS, format_memory_evidence, render_memory_evidence
from utils.retrieval.tools.result_bounds import cap_items_for_llm
from utils.messaging.projection import surface_runtime

import logging

logger = logging.getLogger(__name__)

# A broad question ("what do you know about me") can match every memory a user has. Formatting
# all of them floods the chat model's context, so it freezes or refuses (#4927). Bound how many
# are handed to the model at once; the most recent are kept.
MAX_MEMORIES_FOR_LLM = 300
_MEMORY_TRUNCATION_RESERVE = 256


def _memory_truncation_suffix(shown: int) -> str:
    return "\n\n" + truncation_note(
        shown=shown,
        total=None,
        unit="memories",
        how_to_get_more="request another page or narrow the topic or date range",
        cut=True,
    )


def _publish_memory_refs(configurable, memories):
    channel_items = configurable.get('channel_items')
    for memory in memories:
        memory_id = getattr(memory, 'id', None)
        register_record_ref(configurable, 'memories', memory_id)
        if memory_id and isinstance(channel_items, list):
            channel_items.append({'kind': 'memory', 'id': memory_id, 'title': memory.content[:100]})


def _channel_empty_memories(date_info=''):
    runtime = surface_runtime.get()
    if runtime is None or runtime.surface == 'app':
        return None
    return (
        f"No memories are available to this chat for this query{date_info}. "
        "Privacy, review, and temporal filters can withhold saved memories. "
        "This does not prove the user has no saved personal facts. "
        "Use any supplied activity context accurately and distinguish it from retrieved memories."
    )


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


def _memory_tools_blocked_by_chat_scope(configurable: Any) -> Optional[str]:
    """Conversation hard-scope cannot be honored by global memory tools (#4515)."""
    scope = chat_scope_from_config(configurable)
    if scope and scope.get("conversation_id"):
        return (
            "Error: Chat is scoped to a single conversation. "
            "Use get_conversations_tool or search_conversations_tool for that conversation; "
            "memory fact tools are unavailable while conversation scope is active."
        )
    return None


def _memory_in_scope(created_at: Optional[datetime], start_dt: Optional[datetime], end_dt: Optional[datetime]) -> bool:
    if created_at is None:
        return not (start_dt or end_dt)
    if start_dt is not None and created_at < start_dt:
        return False
    if end_dt is not None and created_at > end_dt:
        return False
    return True


def _parse_date_from_chat_scope(value: object) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("chat_scope dates must include a timezone")
    return parsed


def _memory_read_date(memory: object) -> Optional[datetime]:
    """Use memory creation time for date ranges and display."""
    created_at = getattr(memory, 'created_at', None)
    return created_at if isinstance(created_at, datetime) else None


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

    memories: List[MemoryDB] = []
    try:
        configurable: Any = cfg.get('configurable')
        uid = configurable.get('user_id')
    except (KeyError, TypeError, AttributeError) as e:
        logger.error(f"❌ get_memories_tool - error accessing config: {e}")
        return "Error: Configuration not available"

    if not uid:
        logger.info(f"❌ get_memories_tool - no user_id in config")
        return "Error: User ID not found in configuration"
    clock = clock_for_config(config or _agent_config(), uid)
    logger.info(f"✅ get_memories_tool - uid: {uid}, limit: {limit}")

    blocked = _memory_tools_blocked_by_chat_scope(configurable)
    if blocked:
        return blocked

    start_date, end_date, scope_err = apply_chat_scope_dates(chat_scope_from_config(configurable), start_date, end_date)
    if scope_err:
        return f"Error: {scope_err}"

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
            logger.info("Parsed start_date")
        except ValueError as e:
            return f"Error: Invalid start_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone: {start_date} - {str(e)}"

    if end_date:
        try:
            # Parse ISO format with timezone - should be in user's timezone (YYYY-MM-DDTHH:MM:SS+HH:MM)
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            if end_dt.tzinfo is None:
                return f"Error: end_date must include timezone in user's timezone format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-19T23:59:59-08:00'): {end_date}"
            logger.info("Parsed end_date")
        except ValueError as e:
            return f"Error: Invalid end_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone: {end_date} - {str(e)}"

    memories: List[MemoryDB] = []
    scan_truncated = False
    try:
        service = MemoryService(db_client=firestore_db)
        # Product/API reads retain a short locked preview for released clients,
        # but chat context must never receive paid-plan locked content. Keep the
        # privacy boundary at this LLM-facing consumer even though all rows now
        # come through the universal MemoryService.
        target_end = min(max(offset, 0) + limit, 5000)
        scan_offset = 0
        visible: List[MemoryDB] = []
        max_scan = 5000
        while scan_offset < max_scan and len(visible) < target_end:
            batch_limit = min(500, max_scan - scan_offset)
            fetch_limit = target_end if scan_offset == 0 else batch_limit
            batch = service.read(uid, limit=fetch_limit, offset=scan_offset)
            if not batch:
                break
            scan_offset += len(batch)
            for memory in batch:
                if memory.is_locked or getattr(memory, 'user_review', None) is False:
                    continue
                if not _memory_in_scope(memory.created_at, start_dt, end_dt):
                    continue
                visible.append(memory)
            if len(batch) < fetch_limit:
                break
        scan_truncated = scan_offset >= max_scan and len(visible) < target_end
        memories = omit_channel_private(visible[max(offset, 0) : target_end], configurable)
    except Exception as e:
        logger.error("get_memories_tool retrieval failed error_type=%s", type(e).__name__, exc_info=True)
        return lookup_failed('memories')

    # Bound how many memories are formatted for the chat model so a broad question cannot flood
    # its context and freeze it (#4927). The DB returns newest-first, so this keeps the most recent.
    # A full DB page (len >= limit) means more memories likely exist beyond it, so flag that too so
    # the note is not silently dropped when the model requested a small limit (cubic on #8527).
    db_page = memories or []
    more_in_db = len(db_page) >= limit
    memories, page_count, capped = cap_items_for_llm(db_page, MAX_MEMORIES_FOR_LLM)
    results_truncated = capped or more_in_db or scan_truncated
    logger.info(
        f"📊 get_memories_tool - page {page_count} memories, showing {len(memories)}, truncated={results_truncated}"
    )

    if not memories:
        date_info = ""
        if start_dt and end_dt:
            date_info = f" between {format_date(start_dt, clock)} and {format_date(end_dt, clock)}"
        elif start_dt:
            date_info = f" after {format_date(start_dt, clock)}"
        elif end_dt:
            date_info = f" before {format_date(end_dt, clock)}"

        msg = _channel_empty_memories(date_info)
        if msg is None:
            msg = f"No memories found{date_info}. The user may not have any recorded facts or memories yet in the system, or the date range may be outside their memory history."
        if scan_truncated:
            msg += " The bounded scan reached its safety limit; more memories may exist."
        logger.info(f"⚠️ get_memories_tool - {msg}")
        return msg

    title = "User Memories"
    records = []
    for memory in memories:
        stamp = _memory_read_date(memory)
        if stamp and stamp.tzinfo is not None:
            stamp = stamp.astimezone(timezone.utc)
        date_str = format_instant(stamp, clock) if stamp else 'Unknown'
        memory_id = getattr(memory, 'id', None)
        records.append(
            format_memory_evidence(
                memory.content,
                suffix=f'memory_id: {memory_id}, date: {date_str}' if memory_id else f'date: {date_str}',
                subject_attribution=getattr(memory, 'subject_attribution', 'unknown'),
            )
        )
    included_indices: list[int] = []
    result = render_memory_evidence(
        records,
        title=title,
        max_chars=MAX_MEMORY_EVIDENCE_CHARS - _MEMORY_TRUNCATION_RESERVE,
        more_available=results_truncated,
        offset=None if scan_truncated else max(offset, 0),
        included_indices=included_indices,
    )
    _publish_memory_refs(configurable, [memories[index] for index in included_indices])
    if results_truncated or len(included_indices) < len(records):
        result += _memory_truncation_suffix(len(included_indices))
    return result


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
    clock = clock_for_config(config or _agent_config(), uid)
    logger.info('search_memories_tool uid=%s limit=%s', uid, limit)

    blocked = _memory_tools_blocked_by_chat_scope(configurable)
    if blocked:
        return blocked

    scope = chat_scope_from_config(configurable) or {}
    _, _, scope_err = apply_chat_scope_dates(scope, None, None)
    if scope_err:
        return f"Error: {scope_err}"
    scope_start_dt = _parse_date_from_chat_scope(scope.get("start_date"))
    scope_end_dt = _parse_date_from_chat_scope(scope.get("end_date"))

    # Cap limit at 20
    limit = min(limit, 20)

    try:
        if not (scope_start_dt or scope_end_dt):
            matches = MemoryService(db_client=firestore_db).search(uid, query, limit=limit)
        else:
            service = MemoryService(db_client=firestore_db)
            matches = service.search(uid, query, limit=limit, candidate_limit=limit * 3)
        hide_private = channel_private_filter_active(configurable)
        matches = [
            match
            for match in matches
            if not match.memory.is_locked and not (hide_private and is_channel_private_memory(match.memory))
        ]
        if scope_start_dt or scope_end_dt:
            matches = [
                m
                for m in matches
                if _memory_in_scope(
                    _memory_read_date(m.memory),
                    scope_start_dt,
                    scope_end_dt,
                )
            ][:limit]
        if not matches:
            channel_msg = _channel_empty_memories()
            if channel_msg is not None:
                logger.info('search_memories_tool empty channel result')
                return channel_msg
            msg = (
                f"No memories found matching '{query}'. The user may not have any recorded facts about this topic yet."
            )
            logger.info('search_memories_tool empty result')
            return msg

        records = []
        for match in matches:
            memory = match.memory
            score = match.score
            display_date = _memory_read_date(memory)
            date_str = format_date(display_date, clock) if display_date else 'Unknown'
            memory_id = getattr(memory, 'id', None)
            memory_id_prefix = f'memory_id: {memory_id}, ' if memory_id else ''
            suffix = f"{memory_id_prefix}relevance: {score:.2f}, category: {memory.category.value}, date: {date_str}"
            records.append(
                format_memory_evidence(
                    memory.content,
                    suffix=suffix,
                    subject_attribution=getattr(memory, 'subject_attribution', 'unknown'),
                )
            )

        included_indices: list[int] = []
        result = render_memory_evidence(
            records,
            title=f"Memories matching '{query}'",
            max_chars=MAX_MEMORY_EVIDENCE_CHARS - _MEMORY_TRUNCATION_RESERVE,
            included_indices=included_indices,
        )
        _publish_memory_refs(configurable, [matches[index].memory for index in included_indices])

        if len(included_indices) < len(records):
            result += _memory_truncation_suffix(len(included_indices))

        logger.info(f"🔍 search_memories_tool - Generated result string, length: {len(result)}")

        return result.strip()

    except Exception as e:
        # The exception text can carry provider keys and user content; keep the
        # type for diagnosis and leave the message out of the log.
        logger.error("search_memories_tool failed error_type=%s", type(e).__name__, exc_info=True)
        return "Error searching memories. Please try again."
