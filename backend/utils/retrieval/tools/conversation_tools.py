"""
Tools for accessing user conversations.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple, cast
import contextvars
import threading

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]  # langchain @tool decorator partially typed

import database.conversations as conversations_db
import database.users as users_db
import database.vector_db as vector_db
from database.auth import get_user_name
from models.other import Person
from utils.conversations.factory import deserialize_conversation
from utils.conversations.mcp_transcript_search import (
    ChatTranscriptSearch,
    chat_transcript_coverage_note,
    chat_transcript_excerpts,
    merge_chat_conversation_ids,
    search_chat_transcript_chunks,
)
from utils.conversations.render import conversation_to_citation_card, conversations_to_string
from utils.conversations.search import (
    conversation_matches_date_range,
    keyword_search_conversation_ids,
    parse_exact_conversation_reference,
)
from utils.metrics import OMI_CHAT_SEARCH_TOOL_OUTCOMES_TOTAL
from utils.observability.fallback import record_fallback
from utils.retrieval.chat_scope import apply_chat_scope_dates, chat_scope_from_config
from utils.retrieval.turn_refs import register_record_ref
import logging
from utils.model_text import (
    DisplayClock,
    ELAPSED_LEGEND,
    UNTRUSTED_LEGEND,
    format_date,
    none_found,
    truncation_note,
    untrusted_block,
    withheld_note,
)
from utils.user_clock import clock_for_turn
from utils.conversations.transcript_for_llm import owner_safe_transcript_segments

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


def _scoped_conversation_fetch(
    uid: str,
    conversation_id: str,
    *,
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
    include_discarded: bool = False,
    statuses: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Load one owned conversation and enforce the same visibility filters as list fetch."""
    # Prefer get_conversations_by_id so missing stored `id` is backfilled from the doc key
    # (same as list/search hydration); get_conversation alone can silently drop those rows.
    convs = conversations_db.get_conversations_by_id(uid, [conversation_id], include_discarded=True)
    conv = convs[0] if convs else None
    if not conv:
        return [], none_found('conversations', f"for scoped conversation {conversation_id}")
    if conv.get('is_locked', False):
        return [], (
            withheld_note(
                count=1,
                subject='conversations',
                reason='locked on the current plan',
                how_to_access='Upgrade your plan to access them.',
            )
            + '\n'
            + none_found('conversations', f"for scoped conversation {conversation_id}")
        )
    if not include_discarded and conv.get('discarded', False):
        return [], (
            withheld_note(count=1, subject='conversations', reason='discarded')
            + '\n'
            + none_found('conversations', f"for scoped conversation {conversation_id}")
        )
    if statuses:
        raw_status = conv.get('status')
        status_val = getattr(raw_status, 'value', raw_status)
        if status_val is None or str(status_val) not in statuses:
            return [], f"No accessible conversation found for scoped id {conversation_id}."
    start_ts = start_dt.timestamp() if start_dt is not None else None
    end_ts = end_dt.timestamp() if end_dt is not None else None
    if start_ts is not None or end_ts is not None:
        if not conversation_matches_date_range(conv, start_ts, end_ts):
            return [], (
                f"Scoped conversation {conversation_id} is outside the active chat timeframe. "
                "Ask the user to clear or widen the timeframe, or pick that conversation alone."
            )
    return [conv], None


# A wide date range ("analyze my last 30 days") can match hundreds of conversations. Feeding all of
# them to the chat model floods its context, so it freezes or refuses with "that's quite a bit of
# information to process at once" (#4927). Bound both the count and the raw size of what we return.
MAX_CONVERSATIONS_FOR_LLM = 100
MAX_RESULT_CHARS = 60000


def _parse_exact_search_reference(query: str) -> Optional[str]:
    return parse_exact_conversation_reference(query)


def _cap_conversations_for_llm(conversations: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int, bool]:
    """Keep at most ``MAX_CONVERSATIONS_FOR_LLM`` conversations for the chat model.

    The DB returns conversations newest-first, so this keeps the most recent ones. Returns
    ``(capped_list, total_found, truncated)`` where ``truncated`` is True when some were dropped.
    """
    total_found = len(conversations)
    if total_found > MAX_CONVERSATIONS_FOR_LLM:
        return conversations[:MAX_CONVERSATIONS_FOR_LLM], total_found, True
    return list(conversations), total_found, False


def _date_scope(start_dt: Optional[datetime], end_dt: Optional[datetime], clock: DisplayClock) -> str:
    if start_dt and end_dt:
        return f"between {format_date(start_dt, clock)} and {format_date(end_dt, clock)}"
    if start_dt:
        return f"after {format_date(start_dt, clock)}"
    if end_dt:
        return f"before {format_date(end_dt, clock)}"
    return "in the requested scope"


def _withheld_conversation_notes(locked: int = 0, discarded: int = 0) -> str:
    notes = [
        withheld_note(
            count=locked,
            subject='conversations',
            reason='locked on the current plan',
            how_to_access='Upgrade your plan to access them.',
        ),
        withheld_note(count=discarded, subject='conversations', reason='discarded'),
    ]
    return '\n'.join(note for note in notes if note)


def _owner_safe_conversation_rows(
    conversations: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Copy rows for transcript excerpt rebuilding after applying the shared owner gate."""
    safe_rows: List[Dict[str, Any]] = []
    owner_notes: Dict[str, str] = {}
    for conversation in conversations:
        copied = dict(conversation)
        segments = conversation.get('transcript_segments') or []
        safe_segments, owner_note = owner_safe_transcript_segments(
            [segment for segment in segments if isinstance(segment, dict)]
        )
        copied['transcript_segments'] = safe_segments
        safe_rows.append(copied)
        if owner_note and conversation.get('id'):
            owner_notes[str(conversation['id'])] = owner_note
    return safe_rows, owner_notes


def _bounded_result(result: str, total_found: int, truncated: bool, *, already_bounded: bool = False) -> str:
    """Apply a hard size budget and, when the range was truncated, append a note telling the model
    to summarize what it has and offer to narrow, so it answers instead of freezing (#4927)."""
    if not already_bounded and len(result) > MAX_RESULT_CHARS:
        # Cut at a conversation boundary when possible so a record is not split mid-way.
        clipped = result[:MAX_RESULT_CHARS]
        boundary = clipped.rfind("\nConversation #")
        result = clipped[:boundary] if boundary > 0 else clipped
        truncated = True
    if truncated:
        shown = result.count('Conversation #')
        note = truncation_note(
            shown=shown,
            total=total_found if total_found >= shown else None,
            unit='conversations',
            how_to_get_more='Narrow the date range or request a specific topic for more detail.',
            cut=total_found <= shown,
        )
        if note:
            result += '\n\n' + note
    return result


# Citation [k] resolves to conversations_collected[k - 1]. Tool calls in one model turn run on
# executor threads that share that list, so numbering a record and appending its card is one step.
_collected_conversations_lock = threading.Lock()


def _render_addressable_conversations(conversations, *, configurable, admitted_ids=None, **render_options) -> str:
    """Publish cards and refs only for records actually admitted to the model's budget.

    A conversation already collected this turn keeps its citation number instead of gaining a
    duplicate card.
    """
    if not isinstance(configurable, dict):
        configurable = {}
    collected = configurable.get('conversations_collected', [])
    blocks = []
    used = 0
    elapsed_legend_emitted = False
    untrusted_legend_emitted = False
    with _collected_conversations_lock:
        numbers = {card.get('id'): number for number, card in enumerate(collected, start=1)}
        for conversation in conversations:
            number = numbers.get(conversation.id)
            block = conversations_to_string(
                [conversation], include_refs=True, index_start=number or len(collected) + 1, **render_options
            )
            if ELAPSED_LEGEND in block:
                if elapsed_legend_emitted:
                    block = block.replace(ELAPSED_LEGEND + '\n', '', 1)
                else:
                    elapsed_legend_emitted = True
            if UNTRUSTED_LEGEND in block:
                if untrusted_legend_emitted:
                    block = block.replace(UNTRUSTED_LEGEND + '\n', '', 1)
                else:
                    untrusted_legend_emitted = True
            size = len(block) + (len('\n\n---------------------\n\n') if blocks else 0)
            if used + size > MAX_RESULT_CHARS:
                if not blocks:
                    blocks.append(
                        'Error: Conversation exceeds the chat read budget; request fewer transcript segments '
                        'or omit the transcript.'
                    )
                else:
                    blocks.append(
                        truncation_note(
                            shown=len(blocks),
                            total=len(conversations),
                            unit='conversations',
                            how_to_get_more='Narrow the read for more detail.',
                        )
                    )
                break
            blocks.append(block)
            used += size
            if number is None:
                collected.append(conversation_to_citation_card(conversation))
                numbers[conversation.id] = len(collected)
            register_record_ref(configurable, 'conversations', conversation.id)
            if admitted_ids is not None:
                admitted_ids.add(conversation.id)
            for person in render_options.get('people') or ():
                if person.id in conversation.get_person_ids():
                    register_record_ref(configurable, 'people', person.id)
    return '\n\n---------------------\n\n'.join(blocks)


@tool
def get_conversations_tool(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: Any = 20,
    offset: Any = 0,
    include_discarded: bool = False,
    statuses: Optional[str] = "processing,completed",
    max_transcript_segments: Any = 0,
    include_transcript: bool = True,
    include_timestamps: bool = False,
    config: RunnableConfig = None,
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
    cfg: Optional[Dict[str, Any]] = cast(Optional[Dict[str, Any]], config)
    if cfg is None:
        cfg = _agent_config()

    if cfg is None:
        return "Error: Configuration not available"

    configurable = cfg.get('configurable') if isinstance(cfg.get('configurable'), dict) else {}
    uid = configurable.get('user_id') or cfg.get('user_id')

    if not uid:
        return "Error: User ID not found in configuration"
    display_clock = clock_for_turn(configurable, str(uid))

    scope = chat_scope_from_config(configurable)
    start_date, end_date, scope_err = apply_chat_scope_dates(scope, start_date, end_date)
    if scope_err:
        return f"Error: {scope_err}"

    try:
        max_transcript_segments = int(max_transcript_segments)
        limit = int(limit)
        offset = int(offset)
    except (TypeError, ValueError):
        return "Error: Invalid numeric parameter format"

    if max_transcript_segments != -1:
        max_transcript_segments = min(max_transcript_segments, 1000)
    limit = min(limit, 5000)

    start_dt = None
    end_dt = None

    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            if start_dt.tzinfo is None:
                return f"Error: start_date must include timezone in user's timezone format YYYY-MM-DDTHH:MM:SS+HH:MM"
        except ValueError as e:
            return f"Error: Invalid start_date format: {e}"

    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            if end_dt.tzinfo is None:
                return f"Error: end_date must include timezone in user's timezone format YYYY-MM-DDTHH:MM:SS+HH:MM"
        except ValueError as e:
            return f"Error: Invalid end_date format: {e}"

    status_list: List[str] = [s.strip() for s in statuses.split(',')] if statuses else []
    locked_count = 0
    try:
        scoped_id = (scope or {}).get("conversation_id") if scope else None
        if scoped_id:
            conversations_data, scoped_err = _scoped_conversation_fetch(
                uid, str(scoped_id), start_dt=start_dt, end_dt=end_dt, include_discarded=include_discarded, statuses=status_list or None
            )
            if scoped_err:
                return scoped_err
            conversations_data = [] if offset > 0 else conversations_data[:limit]
        else:
            conversations_data = conversations_db.get_conversations(
                uid, limit=limit, offset=offset, start_date=start_dt, end_date=end_dt, include_discarded=include_discarded, statuses=status_list
            )
        if conversations_data:
            locked_count = sum(1 for conversation in conversations_data if conversation.get('is_locked', False))
            conversations_data = [c for c in conversations_data if not c.get('is_locked', False)]
    except Exception as e:
        logger.error(f"Error: {e}")
        return "An unexpected error occurred while fetching conversations."

    conversations_data, total_found, results_truncated = _cap_conversations_for_llm(conversations_data or [])

    if not conversations_data:
        msg = none_found('conversations', _date_scope(start_dt, end_dt, display_clock))
        withheld = _withheld_conversation_notes(locked=locked_count)
        return f"{msg}\n{withheld}" if withheld else msg

    try:
        people: List[Person] = []
        user_name = (get_user_name(str(uid), use_default=False) or 'User') if include_transcript else None
        if include_transcript:
            all_person_ids: Set[str] = {s.get('person_id') for c in conversations_data for s in c.get('transcript_segments', []) if s.get('person_id')}
            if all_person_ids:
                people = [Person(**p) for p in users_db.get_people_by_ids(uid, list(all_person_ids))]

        conversations: List[Any] = []
        truncation_notes: Dict[str, str] = {}
        for conv_data in conversations_data:
            try:
                conversation = deserialize_conversation(conv_data)
                if include_transcript:
                    conversation.transcript_segments, _ = owner_safe_transcript_segments(conversation.transcript_segments or [])
                if max_transcript_segments != -1 and conversation.transcript_segments and len(conversation.transcript_segments) > max_transcript_segments:
                    total_segments = len(conversation.transcript_segments)
                    conversation.transcript_segments = conversation.transcript_segments[:max_transcript_segments]
                    truncation_notes[conversation.id] = truncation_note(len(conversation.transcript_segments), total_segments, 'transcript segments', 'Increase max_transcript_segments.')
                conversations.append(conversation)
            except Exception:
                continue

        result = _render_addressable_conversations(
            conversations, configurable=configurable, use_transcript=include_transcript, include_timestamps=include_timestamps, people=people, user_name=user_name, clock=display_clock, truncation_notes=truncation_notes
        )
        withheld = _withheld_conversation_notes(locked=locked_count)
        if withheld:
            result = withheld + '\n\n' + result
        return _bounded_result(result, total_found, results_truncated, already_bounded=True)
    except Exception as e:
        logger.error(f"Error: {e}")
        return "An unexpected error occurred."


@tool
def search_conversations_tool(
    query: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: Any = 5,
    max_transcript_segments: Any = 0,
    include_transcript: bool = True,
    include_timestamps: bool = False,
    config: RunnableConfig = None,
) -> str:
    """
    Search conversations by topic/event or exact canonical conversation ID/share URL.

    CRITICAL: Use this tool whenever the user asks about specific events, meetings, topics, decisions,
    or people mentioned in past conversations.

    When to use:
    - User asks "What did I discuss with X about Y?", "When did we talk about Z?", or references a past event.
    - You need to verify facts, dates, commitments, or details from previous meetings.
    - User provides an exact conversation ID or share URL.

    When NOT to use:
    - Broad summaries of recent time periods (use `get_conversations_tool` instead).
    - Questions unrelated to user's recorded conversations.

    **CRITICAL CITATION RULE:** Every single fact, quote, or claim derived from search results MUST be
    supported by a citation reference [k] matching the conversation card number. Never guess an answer
    without transcript or cited evidence.

    Args:
        query: Natural language description of the concept/topic to search for (required)
        start_date: Filter conversations after this date (ISO format in user's timezone: YYYY-MM-DDTHH:MM:SS+HH:MM, e.g. "2024-01-19T15:00:00-08:00")
        end_date: Filter conversations before this date (ISO format in user's timezone: YYYY-MM-DDTHH:MM:SS+HH:MM, e.g. "2024-01-19T23:59:59-08:00")
        limit: Number of conversations to retrieve (default: 5, max: 20)
        max_transcript_segments: Limit transcript segments per conversation (default: 0=none, suggest 20-50 for detailed review, max: 1000)
        include_transcript: Include full transcript (default: True)
        include_timestamps: Add timestamps to transcript segments (default: False)
    Returns:
        Matching conversations with summaries, action items, attendees, and relevant transcript excerpts.
    """
    cfg: Optional[Dict[str, Any]] = cast(Optional[Dict[str, Any]], config)
    if cfg is None:
        cfg = _agent_config()

    if cfg is None:
        return "Error: Configuration not available"

    if not len(query or ''):
        return "Error: Query cannot be empty"

    configurable = cfg.get('configurable') if isinstance(cfg.get('configurable'), dict) else {}
    uid = configurable.get('user_id') or cfg.get('user_id')

    if not uid:
        return "Error: User ID not found in configuration"
    display_clock = clock_for_turn(configurable, str(uid))
    exact_conversation_id = _parse_exact_search_reference(query)

    scope = chat_scope_from_config(configurable)
    start_date, end_date, scope_err = apply_chat_scope_dates(scope, start_date, end_date)
    if scope_err:
        return f"Error: {scope_err}"

    try:
        max_transcript_segments = int(max_transcript_segments)
        limit = int(limit)
    except (TypeError, ValueError):
        return "Error: Invalid numeric parameter format"

    if max_transcript_segments != -1:
        max_transcript_segments = min(max_transcript_segments, 1000)
    limit = min(limit, 20)

    start_dt = None
    end_dt = None
    starts_at = None
    ends_at = None

    if start_date:
        try:
            dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                return f"Error: start_date must include timezone in user's timezone format YYYY-MM-DDTHH:MM:SS+HH:MM"
            start_dt = dt
            starts_at = int(dt.timestamp())
        except ValueError as e:
            return f"Error: Invalid start_date format for {start_date!r}: {e}"

    if end_date:
        try:
            dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                return f"Error: end_date must include timezone in user's timezone format YYYY-MM-DDTHH:MM:SS+HH:MM"
            end_dt = dt
            ends_at = int(dt.timestamp())
        except ValueError as e:
            return f"Error: Invalid end_date format for {end_date!r}: {e}"

    scoped_id = (scope or {}).get("conversation_id") if scope else None
    if scoped_id and exact_conversation_id and exact_conversation_id != str(scoped_id):
        return f"Error: Chat is scoped to conversation {scoped_id}; cannot load a different conversation reference."

    conversations_data: List[Dict[str, Any]] = []
    withheld_locked = 0
    withheld_discarded = 0
    transcript_search = ChatTranscriptSearch([], False)
    keyword_degraded = False

    try:
        if scoped_id:
            conversations_data, scoped_err = _scoped_conversation_fetch(
                uid, str(scoped_id), start_dt=start_dt, end_dt=end_dt, include_discarded=False, statuses=None
            )
            if scoped_err:
                return scoped_err
        elif exact_conversation_id:
            conversations_data = conversations_db.get_conversations_by_id(uid, [exact_conversation_id], include_discarded=True)
            conversations_data = [c for c in conversations_data if conversation_matches_date_range(c, starts_at, ends_at)]
            withheld_locked = sum(1 for row in conversations_data if row.get('is_locked', False) and not row.get('discarded', False))
            withheld_discarded = sum(1 for row in conversations_data if row.get('discarded', False))
            conversations_data = [c for c in conversations_data if not c.get('is_locked', False) and not c.get('discarded', False)]
        else:
            keyword_ids = []
            try:
                keyword_ids = keyword_search_conversation_ids(
                    uid=uid, query=query, limit=limit, start_date=starts_at, end_date=ends_at, raise_on_error=True
                )
                OMI_CHAT_SEARCH_TOOL_OUTCOMES_TOTAL.labels(outcome="keyword_success").inc()
            except Exception as kw_err:
                logger.warning("Keyword search failed during conversation search; falling back to vector/semantic search: %s", kw_err)
                record_fallback("conversation_keyword_search", kw_err)
                OMI_CHAT_SEARCH_TOOL_OUTCOMES_TOTAL.labels(outcome="keyword_fallback").inc()
                keyword_degraded = True

            index_available = getattr(vector_db, 'index', None) is not None
            query_vector = vector_db.embeddings.embed_query(query) if index_available else None
            vector_ids = vector_db.query_vectors(
                query=query,
                uid=uid,
                starts_at=starts_at,
                ends_at=ends_at,
                k=limit,
                **({'query_vector': query_vector} if query_vector is not None else {}),
            )
            transcript_search = search_chat_transcript_chunks(
                uid,
                query,
                limit=limit,
                starts_at=starts_at,
                ends_at=ends_at,
                query_vector=query_vector,
                index_available=index_available,
                search_transcript_chunks=vector_db.search_transcript_chunks,
            )
            conversation_ids = merge_chat_conversation_ids(keyword_ids, transcript_search.conversation_ids, vector_ids, limit)
            conversations_data = conversations_db.get_conversations_by_id(uid, conversation_ids, include_discarded=True)
            conversations_data = [c for c in conversations_data if conversation_matches_date_range(c, starts_at, ends_at)]
            withheld_locked = sum(1 for row in conversations_data if row.get('is_locked', False) and not row.get('discarded', False))
            withheld_discarded = sum(1 for row in conversations_data if row.get('discarded', False))
            conversations_data = [c for c in conversations_data if not c.get('is_locked', False) and not c.get('discarded', False)]
            OMI_CHAT_SEARCH_TOOL_OUTCOMES_TOTAL.labels(outcome="success").inc()

        if not conversations_data:
            msg = none_found('conversations', f"matching query {query!r}")
            coverage_note = chat_transcript_coverage_note(transcript_search)
            if coverage_note:
                msg += f"\n\n{coverage_note}"
            withheld = _withheld_conversation_notes(withheld_locked, withheld_discarded)
            return f"{msg}\n{withheld}" if withheld else msg

        people: List[Person] = []
        user_name = (get_user_name(str(uid), use_default=False) or 'User') if include_transcript else None
        if include_transcript:
            all_person_ids: Set[str] = {
                s.get('person_id') for c in conversations_data for s in c.get('transcript_segments', []) if s.get('person_id')
            }
            if all_person_ids:
                people = [Person(**p) for p in users_db.get_people_by_ids(uid, list(all_person_ids))]

        conversations: List[Any] = []
        truncation_notes: Dict[str, str] = {}
        for conv_data in conversations_data:
            try:
                conversation = deserialize_conversation(conv_data)
                if include_transcript:
                    conversation.transcript_segments, _ = owner_safe_transcript_segments(conversation.transcript_segments or [])
                if max_transcript_segments != -1 and conversation.transcript_segments and len(conversation.transcript_segments) > max_transcript_segments:
                    total_segments = len(conversation.transcript_segments)
                    conversation.transcript_segments = conversation.transcript_segments[:max_transcript_segments]
                    truncation_notes[conversation.id] = truncation_note(
                        len(conversation.transcript_segments), total_segments, 'transcript segments', 'Increase max_transcript_segments.'
                    )
                conversations.append(conversation)
            except Exception:
                continue

        admitted_ids: Set[str] = set()
        result = _render_addressable_conversations(
            conversations,
            configurable=configurable,
            admitted_ids=admitted_ids,
            use_transcript=include_transcript,
            include_timestamps=include_timestamps,
            people=people,
            user_name=user_name,
            clock=display_clock,
            truncation_notes=truncation_notes,
        )
        withheld = _withheld_conversation_notes(withheld_locked, withheld_discarded)
        if withheld:
            result = withheld + '\n\n' + result

        if include_transcript and admitted_ids:
            excerpt_rows, owner_notes = _owner_safe_conversation_rows(
                [row for row in conversations_data if row.get('id') in admitted_ids]
            )
            transcript_excerpts = chat_transcript_excerpts(excerpt_rows, transcript_search, clock=display_clock)
            if transcript_excerpts:
                excerpt_blocks: List[str] = []
                for cid, excerpt in transcript_excerpts.items():
                    owner_prefix = (owner_notes.get(cid, '') + '\n') if owner_notes.get(cid) else ''
                    excerpt_block = (
                        f"\n\nVerbatim transcript excerpt from conversation {cid}:\n"
                        f"{owner_prefix}"
                        f"{UNTRUSTED_LEGEND}\n"
                        f"{untrusted_block('transcript', excerpt)}"
                    )
                    excerpt_blocks.append(excerpt_block)
                combined_excerpts = ''.join(excerpt_blocks)
                if len(result) + len(combined_excerpts) <= MAX_RESULT_CHARS:
                    result += combined_excerpts
                else:
                    remaining_budget = MAX_RESULT_CHARS - len(result)
                    if remaining_budget > 200:
                        result += combined_excerpts[:remaining_budget]
                        result += '\n\n[Additional transcript excerpts omitted to fit size budget.]'
                    else:
                        result += '\n\n[Transcript excerpts omitted to fit size budget.]'

        coverage_note = chat_transcript_coverage_note(transcript_search)
        if coverage_note:
            result += f"\n\n{coverage_note}"

        if keyword_degraded:
            result += '\n\n[Keyword index temporarily unavailable; results are semantic-only]'

        return result
    except Exception as e:
        logger.error(f"Error in search_conversations_tool: {e}")
        OMI_CHAT_SEARCH_TOOL_OUTCOMES_TOTAL.labels(outcome="error").inc()
        return "An unexpected error occurred during search."