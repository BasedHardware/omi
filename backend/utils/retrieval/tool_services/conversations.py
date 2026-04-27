"""
Shared service functions for conversation retrieval.
Used by both LangChain tools (mobile chat) and REST router (desktop/web).
"""

import re
from datetime import datetime, timezone
from typing import List, Optional

import database.conversations as conversations_db
import database.users as users_db
import database.vector_db as vector_db
from models.conversation import Conversation
from models.other import Person
from utils.conversations.factory import deserialize_conversation
from utils.conversations.render import conversations_to_string
import logging

logger = logging.getLogger(__name__)


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
) -> str:
    """Fetch conversations and format as LLM-ready text."""
    logger.info(f"get_conversations_text - uid: {uid}, limit: {limit}, offset: {offset}")

    # Cap limits
    if max_transcript_segments != -1:
        max_transcript_segments = min(max_transcript_segments, 1000)
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

    # Parse statuses
    status_list = []
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

    # Filter locked
    if conversations_data:
        conversations_data = [c for c in conversations_data if not c.get('is_locked', False)]

    if not conversations_data:
        date_info = ""
        if start_dt and end_dt:
            date_info = f" between {start_dt.strftime('%Y-%m-%d')} and {end_dt.strftime('%Y-%m-%d')}"
        elif start_dt:
            date_info = f" after {start_dt.strftime('%Y-%m-%d')}"
        elif end_dt:
            date_info = f" before {end_dt.strftime('%Y-%m-%d')}"
        return f"No conversations found{date_info}."

    # Load people for speaker names
    people = []
    if include_transcript:
        all_person_ids = set()
        for conv_data in conversations_data:
            segments = conv_data.get('transcript_segments', [])
            all_person_ids.update([s.get('person_id') for s in segments if s.get('person_id')])
        if all_person_ids:
            people_data = users_db.get_people_by_ids(uid, list(all_person_ids))
            people = [Person(**p) for p in people_data]

    # Convert to objects
    conversations = []
    for conv_data in conversations_data:
        try:
            conversation = deserialize_conversation(conv_data)
            if (
                max_transcript_segments != -1
                and conversation.transcript_segments
                and len(conversation.transcript_segments) > max_transcript_segments
            ):
                conversation.transcript_segments = conversation.transcript_segments[:max_transcript_segments]
            conversations.append(conversation)
        except Exception as e:
            logger.error(f"Error parsing conversation {conv_data.get('id')}: {e}")
            continue

    return conversations_to_string(
        conversations, use_transcript=include_transcript, include_timestamps=include_timestamps, people=people
    )


def search_conversations_text(
    uid: str,
    query: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 5,
    max_transcript_segments: int = 0,
    include_transcript: bool = True,
    include_timestamps: bool = False,
) -> str:
    """Semantic vector search for conversations, formatted as LLM-ready text."""
    logger.info(f"search_conversations_text - uid: {uid}, query: {query}, limit: {limit}")

    # Cap limits
    if max_transcript_segments != -1:
        max_transcript_segments = min(max_transcript_segments, 1000)
    limit = min(limit, 20)

    # Parse date filters to timestamps
    starts_at = None
    ends_at = None
    if start_date:
        try:
            dt = parse_iso_date(start_date, 'start_date')
            starts_at = int(dt.timestamp())
        except ValueError as e:
            return f"Error: Invalid start_date format: {e}"
    if end_date:
        try:
            dt = parse_iso_date(end_date, 'end_date')
            ends_at = int(dt.timestamp())
        except ValueError as e:
            return f"Error: Invalid end_date format: {e}"

    # Guard one-sided date ranges: vector_db.query_vectors sets both $gte and $lte
    # when starts_at is provided, so we need to fill in the missing bound.
    if starts_at is not None and ends_at is None:
        ends_at = int(datetime.now(timezone.utc).timestamp()) + 86400  # tomorrow
    if ends_at is not None and starts_at is None:
        starts_at = 0  # epoch

    try:
        conversation_ids = vector_db.query_vectors(query=query, uid=uid, starts_at=starts_at, ends_at=ends_at, k=limit)

        if not conversation_ids:
            date_info = ""
            if starts_at and ends_at:
                date_info = " in the specified date range"
            elif starts_at:
                date_info = " after the specified start date"
            elif ends_at:
                date_info = " before the specified end date"
            return f"No conversations found matching '{query}'{date_info}."

        conversations_data = conversations_db.get_conversations_by_id(uid, conversation_ids)
        if not conversations_data:
            return f"No conversations found matching query: '{query}'"

        # Filter locked
        conversations_data = [c for c in conversations_data if not c.get('is_locked', False)]
        if not conversations_data:
            return f"No conversations found matching query: '{query}'"

        # Load people
        people = []
        if include_transcript:
            all_person_ids = set()
            for conv_data in conversations_data:
                segments = conv_data.get('transcript_segments', [])
                all_person_ids.update([s.get('person_id') for s in segments if s.get('person_id')])
            if all_person_ids:
                people_data = users_db.get_people_by_ids(uid, list(all_person_ids))
                people = [Person(**p) for p in people_data]

        # Convert
        conversations = []
        for conv_data in conversations_data:
            try:
                conversation = deserialize_conversation(conv_data)
                if (
                    max_transcript_segments != -1
                    and conversation.transcript_segments
                    and len(conversation.transcript_segments) > max_transcript_segments
                ):
                    conversation.transcript_segments = conversation.transcript_segments[:max_transcript_segments]
                conversations.append(conversation)
            except Exception as e:
                logger.error(f"Error parsing conversation {conv_data.get('id')}: {e}")
                continue

        result = f"Found {len(conversations)} conversations semantically matching '{query}':\n\n"
        result += conversations_to_string(
            conversations, use_transcript=include_transcript, include_timestamps=include_timestamps, people=people
        )
        return result

    except Exception as e:
        logger.error(f"search_conversations_text error: {e}")
        return f"Error performing conversation search: {e}"
