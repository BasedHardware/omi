"""
Shared service functions for conversation retrieval.
Used by both LangChain tools (mobile chat) and REST router (desktop/web).
"""

import re
from datetime import datetime, timezone
from typing import Any, List, Optional, Set

import database.conversations as conversations_db
import database.users as users_db
import database.vector_db as vector_db
from database.auth import get_user_name
from models.conversation import Conversation
from models.other import Person
from utils.conversations.factory import deserialize_conversation
from utils.conversations.mcp_transcript_search import (
    ChatTranscriptSearch,
    chat_transcript_coverage_note,
    chat_transcript_excerpts,
    merge_chat_conversation_ids,
    search_chat_transcript_chunks,
)
from utils.conversations.render import conversations_to_string
from utils.conversations.transcript_for_llm import owner_safe_transcript_segments
from utils.conversations.search import (
    conversation_matches_date_range,
    keyword_search_conversation_ids,
    parse_exact_conversation_reference,
)
from utils.retrieval.safety import safe_isoformat
from utils.model_text import (
    DisplayClock,
    UNTRUSTED_LEGEND,
    format_date,
    none_found,
    truncation_note,
    untrusted_block,
    withheld_note,
)
from utils.user_clock import clock_for_uid
from utils.retrieval.tool_services.transcript_search import search_saved_transcripts_text
import logging

logger = logging.getLogger(__name__)


def _date_scope(start_dt: Optional[datetime], end_dt: Optional[datetime], clock: DisplayClock) -> str:
    if start_dt and end_dt:
        return f"between {format_date(start_dt, clock)} and {format_date(end_dt, clock)}"
    if start_dt:
        return f"after {format_date(start_dt, clock)}"
    if end_dt:
        return f"before {format_date(end_dt, clock)}"
    return "in the requested scope"


def _withheld_notes(locked: int = 0, discarded: int = 0) -> str:
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


def _owner_safe_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    safe_rows: list[dict[str, Any]] = []
    owner_notes: dict[str, str] = {}
    for row in rows:
        copied = dict(row)
        safe_segments, note = owner_safe_transcript_segments(
            [segment for segment in (row.get('transcript_segments') or []) if isinstance(segment, dict)]
        )
        copied['transcript_segments'] = safe_segments
        safe_rows.append(copied)
        if note and row.get('id'):
            owner_notes[str(row['id'])] = note
    return safe_rows, owner_notes


def _append_conversation_source(
    source_sink: Optional[List[dict[str, Any]]], conversation: Conversation, *, excerpt: Optional[str] = None
) -> None:
    if source_sink is None:
        return
    structured = getattr(conversation, 'structured', None)
    source_sink.append(
        {
            'kind': 'conversation',
            'source_id': conversation.id,
            'title': str(getattr(structured, 'title', None) or 'Conversation')[:160],
            'preview': (
                ' '.join(excerpt.split())[:600] if excerpt else str(getattr(structured, 'overview', None) or '')[:600]
            ),
            'created_at': safe_isoformat(getattr(conversation, 'created_at', None)),
        }
    )


def parse_iso_date(date_str: str, param_name: str) -> datetime:
    """Parse ISO date string with timezone. Raises ValueError on bad format."""
    # Recover '+' lost to URL query param decoding (servers decode '+' as space)
    cleaned = re.sub(r' (\d{2}:\d{2})$', r'+\1', date_str)
    dt = datetime.fromisoformat(cleaned.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError(
            f"{param_name} must include timezone in format YYYY-MM-DDTHH:MM:SS+HH:MM "
            f"(e.g., '2024-01-19T15:00:00-08:00'): {date_str}"
        )
    return dt


def get_conversations_text(
    uid: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    include_discarded: bool = False,
    statuses: Optional[str] = "processing,completed",
    max_transcript_segments: int = 0,
    include_transcript: bool = True,
    include_timestamps: bool = False,
    source_sink: Optional[List[dict[str, Any]]] = None,
) -> str:
    """Fetch conversations and format as LLM-ready text."""
    logger.info(f"get_conversations_text - uid: {uid}, limit: {limit}, offset: {offset}")

    # Cap limits
    if max_transcript_segments != -1:
        max_transcript_segments = min(max_transcript_segments, 1000)
    limit = min(limit, 5000)
    display_clock = clock_for_uid(uid)

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

    # Parse statuses
    status_list: List[str] = []
    if statuses:
        status_list = [s.strip() for s in statuses.split(',') if s.strip()]

    # Fetch
    try:
        conversations_data = conversations_db.get_conversations(
            uid,
            limit=limit,
            offset=offset,
            start_date=start_dt,
            end_date=end_dt,
            include_discarded=include_discarded,
            statuses=status_list,
        )
    except Exception as e:
        logger.error(f"get_conversations_text error: {e}")
        return f"Error retrieving conversations: {e}"

    # Count withheld rows before any transcript or structured content is hydrated into a model object.
    locked_count = 0
    if conversations_data:
        locked_count = sum(1 for conversation in conversations_data if conversation.get('is_locked', False))
        conversations_data = [c for c in conversations_data if not c.get('is_locked', False)]

    if not conversations_data:
        message = none_found('conversations', _date_scope(start_dt, end_dt, display_clock))
        withheld = _withheld_notes(locked=locked_count)
        return f"{message}\n{withheld}" if withheld else message

    # Load people for speaker names
    people: List[Person] = []
    if include_transcript:
        all_person_ids: Set[str] = set()
        for conv_data in conversations_data:
            segments = conv_data.get('transcript_segments', [])
            all_person_ids.update([s.get('person_id') for s in segments if s.get('person_id')])
        if all_person_ids:
            people_data = users_db.get_people_by_ids(uid, list(all_person_ids))
            for p in people_data:
                try:
                    people.append(Person(**p))
                except Exception as e:
                    # A legacy/malformed person doc (e.g. missing the required name) must not 500 the
                    # whole conversation list; skip it so that speaker's name just goes unresolved. Mirrors
                    # the deserialize_conversation loop below and search_conversations_text's guard.
                    logger.warning(f"get_conversations_text skipping malformed person {p.get('id')}: {e}")
                    continue

    # Convert to objects
    conversations: List[Conversation] = []
    truncation_notes: dict[str, str] = {}
    for conv_data in conversations_data:
        try:
            conversation = deserialize_conversation(conv_data)
            if include_transcript:
                safe_segments, _ = owner_safe_transcript_segments(conversation.transcript_segments or [])
                conversation.transcript_segments = safe_segments
            if (
                max_transcript_segments != -1
                and conversation.transcript_segments
                and len(conversation.transcript_segments) > max_transcript_segments
            ):
                total_segments = len(conversation.transcript_segments)
                conversation.transcript_segments = conversation.transcript_segments[:max_transcript_segments]
                note = truncation_note(
                    shown=len(conversation.transcript_segments),
                    total=total_segments,
                    unit='transcript segments',
                    how_to_get_more='Increase max_transcript_segments or set it to -1 for the full transcript.',
                )
                if note:
                    truncation_notes[conversation.id] = note
            conversations.append(conversation)
        except Exception as e:
            logger.error(f"Error parsing conversation {conv_data.get('id')}: {e}")
            continue

    for conversation in conversations[:128]:
        _append_conversation_source(source_sink, conversation)

    result = conversations_to_string(
        conversations,
        use_transcript=include_transcript,
        include_timestamps=include_timestamps,
        people=people,
        user_name=(get_user_name(uid, use_default=False) or 'User') if include_transcript else None,
        clock=display_clock,
        truncation_notes=truncation_notes,
    )
    withheld = _withheld_notes(locked=locked_count)
    return f"{withheld}\n\n{result}" if withheld else result


def search_conversations_text(
    uid: str,
    query: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 5,
    max_transcript_segments: int = 0,
    include_transcript: bool = True,
    include_timestamps: bool = False,
    source_sink: Optional[List[dict[str, Any]]] = None,
    transcript_query: Optional[str] = None,
    transcript_cursor: Optional[str] = None,
) -> str:
    """Hybrid keyword + semantic vector search for conversations, formatted as LLM-ready text."""
    exact_conversation_id = parse_exact_conversation_reference(query)
    logger.info(
        "search_conversations_text - uid=%s query_mode=%s query_len=%s limit=%s",
        uid,
        'exact-reference' if exact_conversation_id else 'semantic',
        len(query or ''),
        limit,
    )

    # Cap limits
    if max_transcript_segments != -1:
        max_transcript_segments = min(max_transcript_segments, 1000)
    limit = min(limit, 20)
    display_clock = clock_for_uid(uid)

    # Parse date filters to timestamps
    starts_at = None
    ends_at = None
    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = parse_iso_date(start_date, 'start_date')
            starts_at = int(start_dt.timestamp())
        except ValueError as e:
            return f"Error: Invalid start_date format: {e}"
    if end_date:
        try:
            end_dt = parse_iso_date(end_date, 'end_date')
            ends_at = int(end_dt.timestamp())
        except ValueError as e:
            return f"Error: Invalid end_date format: {e}"

    if transcript_cursor is not None and transcript_query is None:
        return 'Error: transcript_cursor requires the original transcript_query.'
    if transcript_query is not None:
        if not include_transcript:
            return 'Error: direct transcript search requires include_transcript=true.'
        return search_saved_transcripts_text(
            uid,
            transcript_query,
            start_date=start_dt,
            end_date=end_dt,
            limit=limit,
            cursor=transcript_cursor,
            conversation_id=exact_conversation_id,
            clock=display_clock,
            source_sink=source_sink,
        )

    # Guard one-sided date ranges: vector_db.query_vectors sets both $gte and $lte
    # when starts_at is provided, so we need to fill in the missing bound.
    if starts_at is not None and ends_at is None:
        ends_at = int(datetime.now(timezone.utc).timestamp()) + 86400  # tomorrow
    if ends_at is not None and starts_at is None:
        starts_at = 0  # epoch

    transcript_search = ChatTranscriptSearch([], False)
    try:
        if exact_conversation_id:
            conversation_ids = [exact_conversation_id]
        else:
            # Share the query embedding between summary and transcript vector namespaces.
            keyword_ids = keyword_search_conversation_ids(
                uid=uid, query=query, limit=limit, start_date=starts_at, end_date=ends_at
            )
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
            conversation_ids = merge_chat_conversation_ids(
                keyword_ids, transcript_search.conversation_ids, vector_ids, limit
            )

        if not conversation_ids:
            scope = f" {_date_scope(start_dt, end_dt, display_clock)}" if start_dt or end_dt else ''
            return none_found('conversations', f"matching query {query!r}{scope}") + (
                ' ' + chat_transcript_coverage_note(transcript_search.searched) if not exact_conversation_id else ''
            )

        conversations_data = conversations_db.get_conversations_by_id(uid, conversation_ids, include_discarded=True)
        if not conversations_data:
            scope = f" in {_date_scope(start_dt, end_dt, display_clock)}" if start_dt or end_dt else ''
            return none_found('conversations', f"matching query {query!r}{scope}") + (
                ' ' + chat_transcript_coverage_note(transcript_search.searched) if not exact_conversation_id else ''
            )

        # Search indexes can contain stale date metadata; the hydrated document is authoritative.
        conversations_data = [c for c in conversations_data if conversation_matches_date_range(c, starts_at, ends_at)]
        # Count withheld metadata only; locked rows never become model-facing Conversation objects.
        locked_count = sum(
            1 for row in conversations_data if not row.get('discarded', False) and row.get('is_locked', False)
        )
        discarded_count = sum(1 for row in conversations_data if row.get('discarded', False))
        conversations_data = [
            c for c in conversations_data if not c.get('is_locked', False) and not c.get('discarded', False)
        ]
        if not conversations_data:
            scope = f" in {_date_scope(start_dt, end_dt, display_clock)}" if start_dt or end_dt else ''
            message = none_found('conversations', f"matching query {query!r}{scope}")
            withheld = _withheld_notes(locked_count, discarded_count)
            return (
                message
                + (f"\n{withheld}" if withheld else '')
                + (' ' + chat_transcript_coverage_note(transcript_search.searched) if not exact_conversation_id else '')
            )

        # Load people
        people: List[Person] = []
        if include_transcript:
            all_person_ids: Set[str] = set()
            for conv_data in conversations_data:
                segments = conv_data.get('transcript_segments', [])
                all_person_ids.update([s.get('person_id') for s in segments if s.get('person_id')])
            if all_person_ids:
                people_data = users_db.get_people_by_ids(uid, list(all_person_ids))
                for p in people_data:
                    try:
                        people.append(Person(**p))
                    except Exception as e:
                        # A legacy/malformed person doc (e.g. missing the required name) must not error out the
                        # whole conversation search; skip it so that speaker's name just goes unresolved. Mirrors
                        # the get_conversations_text guard above.
                        logger.warning(f"search_conversations_text skipping malformed person {p.get('id')}: {e}")
                        continue

        # Convert
        conversations: List[Conversation] = []
        truncation_notes: dict[str, str] = {}
        for conv_data in conversations_data:
            try:
                conversation = deserialize_conversation(conv_data)
                if include_transcript:
                    safe_segments, _ = owner_safe_transcript_segments(conversation.transcript_segments or [])
                    conversation.transcript_segments = safe_segments
                if (
                    max_transcript_segments != -1
                    and conversation.transcript_segments
                    and len(conversation.transcript_segments) > max_transcript_segments
                ):
                    total_segments = len(conversation.transcript_segments)
                    conversation.transcript_segments = conversation.transcript_segments[:max_transcript_segments]
                    note = truncation_note(
                        shown=len(conversation.transcript_segments),
                        total=total_segments,
                        unit='transcript segments',
                        how_to_get_more='Increase max_transcript_segments or set it to -1 for the full transcript.',
                    )
                    if note:
                        truncation_notes[conversation.id] = note
                conversations.append(conversation)
            except Exception as e:
                logger.error("Error parsing conversation search result: %s", type(e).__name__)
                continue

        rendered_ids = {conversation.id for conversation in conversations}
        excerpt_rows, excerpt_owner_notes = (
            _owner_safe_rows([row for row in conversations_data if row.get('id') in rendered_ids])
            if include_transcript
            else ([], {})
        )
        transcript_excerpts = (
            chat_transcript_excerpts(
                excerpt_rows,
                transcript_search,
                clock=display_clock,
            )
            if include_transcript
            else {}
        )

        for conversation in conversations[:128]:
            _append_conversation_source(source_sink, conversation, excerpt=transcript_excerpts.get(conversation.id))

        result_header = (
            f"Found {len(conversations)} conversations matching exactly '{query}':"
            if exact_conversation_id
            else (
                f"{len(conversations)} nearest conversations for '{query}' "
                "(semantic search returns the closest matches even when none is relevant; check before citing)"
            )
        )
        result = result_header + '\n\n'
        withheld = _withheld_notes(locked_count, discarded_count)
        if withheld:
            result = withheld + '\n\n' + result
        result += conversations_to_string(
            conversations,
            use_transcript=include_transcript,
            include_timestamps=include_timestamps,
            people=people,
            user_name=(get_user_name(uid, use_default=False) or 'User') if include_transcript else None,
            clock=display_clock,
            truncation_notes=truncation_notes,
        )
        for cid, excerpt in transcript_excerpts.items():
            owner_note = excerpt_owner_notes.get(cid)
            result += (
                f"\n\nVerbatim transcript excerpt from conversation {cid}:\n"
                + (owner_note + '\n' if owner_note else '')
                + untrusted_block('transcript', excerpt)
            )
        if transcript_excerpts and UNTRUSTED_LEGEND not in result:
            result = f"{UNTRUSTED_LEGEND}\n{result}"
        if not exact_conversation_id:
            result += '\n\n' + chat_transcript_coverage_note(transcript_search.searched)
        return result

    except Exception as e:
        logger.error(f"search_conversations_text error: {e}")
        return f"Error performing conversation search: {e}"
