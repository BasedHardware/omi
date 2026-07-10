"""
Tools for accessing user conversations.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple, cast
import contextvars

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]  # langchain @tool decorator partially typed

import database.conversations as conversations_db
import database.notifications as notification_db
import database.users as users_db
import database.vector_db as vector_db
from models.other import Person
from utils.conversations.factory import deserialize_conversation
from utils.conversations.render import conversations_to_string
from utils.conversations.search import keyword_search_conversation_ids, merge_conversation_search_ids
import logging

logger = logging.getLogger(__name__)

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


# A wide date range ("analyze my last 30 days") can match hundreds of conversations. Feeding all of
# them to the chat model floods its context, so it freezes or refuses with "that's quite a bit of
# information to process at once" (#4927). Bound both the count and the raw size of what we return.
MAX_CONVERSATIONS_FOR_LLM = 100
MAX_RESULT_CHARS = 60000


def _cap_conversations_for_llm(conversations: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int, bool]:
    """Keep at most ``MAX_CONVERSATIONS_FOR_LLM`` conversations for the chat model.

    The DB returns conversations newest-first, so this keeps the most recent ones. Returns
    ``(capped_list, total_found, truncated)`` where ``truncated`` is True when some were dropped.
    """
    total_found = len(conversations)
    if total_found > MAX_CONVERSATIONS_FOR_LLM:
        return conversations[:MAX_CONVERSATIONS_FOR_LLM], total_found, True
    return list(conversations), total_found, False


def _bounded_result(result: str, total_found: int, truncated: bool) -> str:
    """Apply a hard size budget and, when the range was truncated, append a note telling the model
    to summarize what it has and offer to narrow, so it answers instead of freezing (#4927)."""
    if len(result) > MAX_RESULT_CHARS:
        # Cut at a conversation boundary when possible so a record is not split mid-way.
        clipped = result[:MAX_RESULT_CHARS]
        boundary = clipped.rfind("\nConversation #")
        result = clipped[:boundary] if boundary > 0 else clipped
        truncated = True
    if truncated:
        result += (
            f"\n\n[This date range contains {total_found} conversations; only the most recent ones are "
            f"shown to stay within limits. Summarize what is shown and tell the user they can narrow to a "
            f"shorter time frame or a specific topic for more detail.]"
        )
    return result


@tool
def get_conversations_tool(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    include_discarded: bool = False,
    statuses: Optional[str] = "processing,completed",
    max_transcript_segments: int = 0,
    include_transcript: bool = True,
    include_timestamps: bool = False,
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
) -> str:
    """
    Retrieve user conversations with complete details including transcripts, summaries, and metadata.

    Use this tool when:
    - User asks about recent conversations or specific time periods
    - You need conversation transcripts to answer questions
    - User wants to review what they discussed

    **IMPORTANT for summarization queries:**
    When user asks for weekly, monthly, or yearly summaries/overviews:
    - Set a high limit (e.g. 200) and max_transcript_segments=0 to retrieve summaries without transcripts
    - For very wide ranges the result is automatically capped to the most recent conversations so it cannot
      overflow context; summarize what is returned and offer to narrow the range if the user needs more detail
    Examples: "summarize my week", "what did I do this month", "recap my year"

    Transcript retrieval guidance:
    - By default (max_transcript_segments=0), no transcript segments are included
    - Only increase max_transcript_segments when user explicitly needs transcript content
    - Use reasonable limits (10-50 segments) for most queries - this usually covers key parts

    Args:
        start_date: Filter conversations after this date (ISO format in user's timezone: YYYY-MM-DDTHH:MM:SS+HH:MM, e.g. "2024-01-19T15:00:00-08:00")
        end_date: Filter conversations before this date (ISO format in user's timezone: YYYY-MM-DDTHH:MM:SS+HH:MM, e.g. "2024-01-19T23:59:59-08:00")
        limit: Number of conversations to retrieve (default: 20, max: 5000)
        offset: Pagination offset for retrieving additional conversations beyond the limit (default: 0)
        include_discarded: Include discarded conversations (default: False)
        statuses: Filter by processing status (default: "processing,completed")
        max_transcript_segments: Limit transcript segments per conversation (default: 0=none, suggest 10-50, max: 1000, -1=full transcript)
        include_transcript: Include full transcript (default: True)
        include_timestamps: Add timestamps to transcript segments (default: False)

    Returns:
        Formatted string with conversations including transcripts, summaries, action items, events, and attendees.
    """
    logger.info(f"🔧 get_conversations_tool called with params:")
    logger.info(f"   start_date: {start_date}")
    logger.info(f"   end_date: {end_date}")
    logger.info(f"   limit: {limit}")
    logger.info(f"   offset: {offset}")
    logger.info(f"   include_discarded: {include_discarded}")
    logger.info(f"   statuses: {statuses}")
    logger.info(f"   max_transcript_segments: {max_transcript_segments}")
    logger.info(f"   include_transcript: {include_transcript}")
    logger.info(f"   include_timestamps: {include_timestamps}")
    # print(f"   config: {config}")

    # Get config from parameter or context variable (like other tools do)
    cfg: Optional[Dict[str, Any]] = cast(Optional[Dict[str, Any]], config)
    if cfg is None:
        cfg = _agent_config()
        if cfg:
            logger.info(f"🔧 get_conversations_tool - got config from context variable")

    if cfg is None:
        logger.info(f"❌ get_conversations_tool - config is None")
        return "Error: Configuration not available"

    try:
        configurable: Any = cfg.get('configurable')
        uid = configurable.get('user_id')
    except (KeyError, TypeError, AttributeError) as e:
        logger.error(f"❌ get_conversations_tool - error accessing config: {e}")
        return "Error: Configuration not available"

    if not uid:
        logger.info(f"❌ get_conversations_tool - no user_id in config")
        return "Error: User ID not found in configuration"
    logger.info(f"✅ get_conversations_tool - uid: {uid}")

    # Cap max_transcript_segments at 1000 to prevent flooding LLM context
    if max_transcript_segments != -1:
        max_transcript_segments = min(max_transcript_segments, 1000)
        logger.info(f"📊 max_transcript_segments capped at: {max_transcript_segments}")

    # Parse dates if provided (always in UTC)
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

    # Limit to reasonable max
    limit = min(limit, 5000)

    # Parse statuses if provided
    status_list: List[str] = []
    if statuses:
        status_list = [s.strip() for s in statuses.split(',') if s.strip()]

    # Get conversations
    conversations_data: List[Dict[str, Any]] = conversations_db.get_conversations(
        uid,
        limit=limit,
        offset=offset,
        start_date=start_dt,
        end_date=end_dt,
        include_discarded=include_discarded,
        statuses=status_list,
    )

    # Filter out locked conversations (paid plan required)
    if conversations_data:
        conversations_data = [c for c in conversations_data if not c.get('is_locked', False)]

    # Bound how many conversations are formatted for the chat model so a wide date range cannot
    # flood its context and freeze it (#4927). Newest-first, so this keeps the most recent.
    conversations_data, total_found, results_truncated = _cap_conversations_for_llm(conversations_data or [])

    logger.info(
        f"📊 get_conversations_tool - found {total_found} conversations"
        + (f" (showing most recent {len(conversations_data)})" if results_truncated else "")
    )

    if not conversations_data:
        date_info = ""
        if start_dt and end_dt:
            date_info = f" between {start_dt.strftime('%Y-%m-%d')} and {end_dt.strftime('%Y-%m-%d')}"
        elif start_dt:
            date_info = f" after {start_dt.strftime('%Y-%m-%d')}"
        elif end_dt:
            date_info = f" before {end_dt.strftime('%Y-%m-%d')}"

        msg = f"No conversations found{date_info}. The user may not have recorded any conversations yet, or the date range may be outside their conversation history."
        logger.info(f"⚠️ get_conversations_tool - {msg}")
        return msg

    try:
        # Only load people if transcripts will be included (people are used for speaker names in transcripts)
        people: List[Person] = []
        if include_transcript:
            # Get all person IDs from all conversations
            all_person_ids: Set[str] = set()
            for conv_data in conversations_data:
                segments = conv_data.get('transcript_segments', [])
                all_person_ids.update([s.get('person_id') for s in segments if s.get('person_id')])

            logger.info(f"🔍 get_conversations_tool - Found {len(all_person_ids)} unique person IDs")

            # Fetch people data
            if all_person_ids:
                people_data = users_db.get_people_by_ids(uid, list(all_person_ids))
                people = [Person(**p) for p in people_data]
                logger.info(f"🔍 get_conversations_tool - Loaded {len(people)} people")
        else:
            logger.warning(f"🔍 get_conversations_tool - Skipping people loading (transcript not included)")

        # Convert to Conversation objects
        conversations: List[Any] = []
        for conv_data in conversations_data:
            try:
                conversation = deserialize_conversation(conv_data)

                # Limit transcript segments if needed (mimicking integration.py pattern)
                if (
                    max_transcript_segments != -1
                    and conversation.transcript_segments
                    and len(conversation.transcript_segments) > max_transcript_segments
                ):
                    conversation.transcript_segments = conversation.transcript_segments[:max_transcript_segments]

                conversations.append(conversation)
            except Exception as e:
                logger.error(f"Error parsing conversation {conv_data.get('id')}: {str(e)}")
                continue

        logger.info(f"🔍 get_conversations_tool - Converted {len(conversations)} conversation objects")

        # Store conversations in config for citation tracking (as lightweight dicts)
        conversations_collected = configurable.get('conversations_collected', [])
        for conv in conversations:
            conv_dict = conv.model_dump()
            # Remove heavy fields to reduce memory usage
            conv_dict.pop('transcript_segments', None)
            conv_dict.pop('photos', None)
            conv_dict.pop('audio_files', None)
            conversations_collected.append(conv_dict)
        logger.info(
            f"📚 get_conversations_tool - Added {len(conversations)} conversations to collection (total: {len(conversations_collected)})"
        )

        # Return formatted string (timestamps rendered in the user's timezone for correct chat answers)
        result = conversations_to_string(
            conversations,
            use_transcript=include_transcript,
            include_timestamps=include_timestamps,
            people=people,
            tz=notification_db.get_user_time_zone(uid) or 'UTC',
        )
        result = _bounded_result(result, total_found, results_truncated)
        logger.info(f"🔍 get_conversations_tool - Generated result string, length: {len(result)}")
        return result

    except Exception as e:
        error_msg = f"Error formatting conversations: {str(e)}"
        logger.info(f"❌ get_conversations_tool - {error_msg}")
        import traceback

        traceback.print_exc()
        return f"Found {len(conversations_data)} conversations but encountered an error formatting them: {str(e)}"


@tool
def search_conversations_tool(
    query: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 5,
    max_transcript_segments: int = 0,
    include_transcript: bool = True,
    include_timestamps: bool = False,
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
) -> str:
    """
    Search conversations using hybrid keyword + semantic vector search - USE THIS FOR EVENTS/INCIDENTS.

    This tool combines exact keyword matching on conversation titles/summaries (best for proper names
    like people or places) with AI embeddings that find semantically similar conversations even if
    they don't contain the exact keywords. Perfect for finding when specific events happened or
    conversations with a specific person (e.g. "When did I talk to Steph?").

    **CRITICAL: Use this tool for EVENT/INCIDENT questions:**
    - "When did a dog bite me?" → USE THIS TOOL
    - "What happened at the party?" → USE THIS TOOL
    - "When did I get injured?" → USE THIS TOOL
    - "When did I meet John?" → USE THIS TOOL
    - "What did I say about the accident?" → USE THIS TOOL
    - Any "when did X happen?" or "what happened when Y?" questions → USE THIS TOOL

    **When to use this tool:**
    - Questions about SPECIFIC EVENTS or INCIDENTS that happened to the user
    - Searching for concepts, themes, or topics (e.g., "discussions about personal growth", "health-related talks")
    - Finding similar conversations even without exact keyword matches
    - Broad subject searches (e.g., "what have I talked about regarding relationships?")
    - Understanding overall themes or patterns in conversations

    **When NOT to use this tool:**
    - For user preferences/facts (use get_memories_tool for "what's my favorite X?", "do I like Y?")

    **Tip:** For best results, use descriptive phrases about the event or concept you're looking for.

    Transcript retrieval guidance (same as other conversation tools):
    - By default (max_transcript_segments=0), no transcript segments are included
    - Only increase when user explicitly needs transcript content
    - Use 20-50 segments for most queries
    - Avoid -1 (full transcript) unless absolutely critical
    - Maximum allowed is 1000 segments to prevent context overflow

    Args:
        query: Natural language description of the concept/topic to search for (required)
        start_date: Filter conversations after this date (ISO format in user's timezone: YYYY-MM-DDTHH:MM:SS+HH:MM)
        end_date: Filter conversations before this date (ISO format in user's timezone: YYYY-MM-DDTHH:MM:SS+HH:MM)
        limit: Number of conversations to retrieve (default: 5, max: 20)
        max_transcript_segments: Limit transcript segments (default: 0=none, suggest 20-50 for normal use, max: 1000)
        include_transcript: Include full transcript (default: True)
        include_timestamps: Add timestamps to transcript segments (default: False)

    Returns:
        Formatted string with semantically matching conversations ranked by relevance, including transcripts,
        summaries, action items, events, and metadata.
    """
    logger.info(f"🔧 search_conversations_tool called with query: {query}")

    # Get config from parameter or context variable (like other tools do)
    cfg: Optional[Dict[str, Any]] = cast(Optional[Dict[str, Any]], config)
    if cfg is None:
        cfg = _agent_config()
        if cfg:
            logger.info(f"🔧 search_conversations_tool - got config from context variable")

    if cfg is None:
        logger.info(f"❌ search_conversations_tool - config is None")
        return "Error: Configuration not available"

    try:
        configurable: Any = cfg.get('configurable')
        uid = configurable.get('user_id')
    except (KeyError, TypeError, AttributeError) as e:
        logger.error(f"❌ search_conversations_tool - error accessing config: {e}")
        return "Error: Configuration not available"

    if not uid:
        logger.info(f"❌ search_conversations_tool - no user_id in config")
        return "Error: User ID not found in configuration"
    logger.info(f"✅ search_conversations_tool - uid: {uid}, query: {query}, limit: {limit}")

    # Cap max_transcript_segments at 1000 to prevent flooding LLM context
    if max_transcript_segments != -1:
        max_transcript_segments = min(max_transcript_segments, 1000)
        logger.info(f"📊 max_transcript_segments capped at: {max_transcript_segments}")

    # Parse dates to timestamps if provided
    starts_at = None
    ends_at = None

    if start_date:
        try:
            dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                return f"Error: start_date must include timezone in user's timezone format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-19T15:00:00-08:00'): {start_date}"
            logger.info(f"📅 Parsed start_date '{start_date}' as {dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            starts_at = int(dt.timestamp())
        except ValueError as e:
            return f"Error: Invalid start_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone: {start_date} - {str(e)}"

    if end_date:
        try:
            dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                return f"Error: end_date must include timezone in user's timezone format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-19T23:59:59-08:00'): {end_date}"
            logger.info(f"📅 Parsed end_date '{end_date}' as {dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            ends_at = int(dt.timestamp())
        except ValueError as e:
            return f"Error: Invalid end_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone: {end_date} - {str(e)}"

    # Limit to reasonable max
    limit = min(limit, 20)

    try:
        # Hybrid search: keyword (Typesense, exact matches on title/overview — catches proper
        # names that embeddings miss, see #5072) + semantic vector search, keyword hits first.
        keyword_ids = keyword_search_conversation_ids(
            uid=uid, query=query, limit=limit, start_date=starts_at, end_date=ends_at
        )
        vector_ids = vector_db.query_vectors(query=query, uid=uid, starts_at=starts_at, ends_at=ends_at, k=limit)
        conversation_ids = merge_conversation_search_ids(keyword_ids, vector_ids)

        logger.info(
            f"📊 search_conversations_tool - found {len(conversation_ids)} results "
            f"({len(keyword_ids)} keyword, {len(vector_ids)} vector) for query: '{query}'"
        )

        if not conversation_ids:
            date_info = ""
            if starts_at and ends_at:
                date_info = f" in the specified date range"
            elif starts_at:
                date_info = f" after the specified start date"
            elif ends_at:
                date_info = f" before the specified end date"

            msg = f"No conversations found matching the concept '{query}'{date_info}. The user may not have discussed this topic yet, or it may not be in their recorded conversation history."
            logger.info(f"⚠️ search_conversations_tool - {msg}")
            return msg

        # Get full conversation data
        conversations_data: List[Dict[str, Any]] = conversations_db.get_conversations_by_id(uid, conversation_ids)

        if not conversations_data:
            return f"No conversations found matching query: '{query}'"

        # Filter out locked conversations (paid plan required)
        conversations_data = [c for c in conversations_data if not c.get('is_locked', False)]

        if not conversations_data:
            return f"No conversations found matching query: '{query}'"

        logger.info(f"🔍 search_conversations_tool - Loaded {len(conversations_data)} full conversations")

        # Only load people if transcripts will be included
        people: List[Person] = []
        if include_transcript:
            # Get all person IDs
            all_person_ids: Set[str] = set()
            for conv_data in conversations_data:
                segments = conv_data.get('transcript_segments', [])
                all_person_ids.update([s.get('person_id') for s in segments if s.get('person_id')])

            logger.info(f"🔍 search_conversations_tool - Found {len(all_person_ids)} unique person IDs")

            # Fetch people data
            if all_person_ids:
                people_data = users_db.get_people_by_ids(uid, list(all_person_ids))
                people = [Person(**p) for p in people_data]
                logger.info(f"🔍 search_conversations_tool - Loaded {len(people)} people")
        else:
            logger.warning(f"🔍 search_conversations_tool - Skipping people loading (transcript not included)")

        # Convert to Conversation objects
        conversations: List[Any] = []
        for conv_data in conversations_data:
            try:
                conversation = deserialize_conversation(conv_data)

                # Limit transcript segments if needed
                if (
                    max_transcript_segments != -1
                    and conversation.transcript_segments
                    and len(conversation.transcript_segments) > max_transcript_segments
                ):
                    conversation.transcript_segments = conversation.transcript_segments[:max_transcript_segments]

                conversations.append(conversation)
            except Exception as e:
                logger.error(f"Error parsing conversation {conv_data.get('id')}: {str(e)}")
                continue

        logger.info(f"🔍 search_conversations_tool - Converted {len(conversations)} conversation objects")

        # Store conversations in config for citation tracking (as lightweight dicts)
        conversations_collected = configurable.get('conversations_collected', [])
        for conv in conversations:
            conv_dict = conv.model_dump()
            # Remove heavy fields to reduce memory usage
            conv_dict.pop('transcript_segments', None)
            conv_dict.pop('photos', None)
            conv_dict.pop('audio_files', None)
            conversations_collected.append(conv_dict)
        logger.info(
            f"📚 search_conversations_tool - Added {len(conversations)} conversations to collection (total: {len(conversations_collected)})"
        )

        # Return formatted string
        result = f"Found {len(conversations)} conversations semantically matching '{query}':\n\n"
        result += conversations_to_string(
            conversations,
            use_transcript=include_transcript,
            include_timestamps=include_timestamps,
            people=people,
            tz=notification_db.get_user_time_zone(uid) or 'UTC',
        )

        logger.info(f"🔍 search_conversations_tool - Generated result string, length: {len(result)}")

        return result

    except Exception as e:
        logger.warning("search_conversations_tool vector search failed (%s)", type(e).__name__)
        return "Found vector search results but encountered an error processing them."
