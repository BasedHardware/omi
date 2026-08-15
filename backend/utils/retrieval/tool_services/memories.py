"""
Shared service functions for memory retrieval.
Used by both LangChain tools (mobile chat) and REST router (desktop/web).
"""

from datetime import datetime, timezone
from typing import Any, List, Optional

import database.notifications as notification_db
from database._client import db as firestore_db
from models.memories import MemoryDB
from utils.conversations.render import format_local_date, resolve_display_tz
from utils.memory.memory_service import MemoryService
from utils.retrieval.tool_services.conversations import parse_iso_date
from utils.retrieval.safety import safe_isoformat
import logging

logger = logging.getLogger(__name__)


def get_memories_text(
    uid: str,
    limit: int = 50,
    offset: int = 0,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    now: Optional[datetime] = None,
    source_sink: Optional[List[dict[str, Any]]] = None,
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

    try:
        service = MemoryService(db_client=firestore_db)
        target_end = min(offset + limit, 5000)
        scan_offset = 0
        visible = []
        max_scan = 5000
        while scan_offset < max_scan and len(visible) < target_end:
            batch_limit = min(500, max_scan - scan_offset)
            fetch_limit = target_end if scan_offset == 0 else batch_limit
            batch = service.read(uid, limit=fetch_limit, offset=scan_offset, now=now)
            if not batch:
                break
            scan_offset += len(batch)
            for memory in batch:
                if memory.is_locked:
                    continue
                created = memory.created_at
                if start_dt and created and created < start_dt:
                    continue
                if end_dt and created and created > end_dt:
                    continue
                visible.append(memory)
            if len(batch) < fetch_limit:
                break
        memories = visible[offset:target_end]
    except Exception as e:
        logger.error(f"get_memories_text error: {e}")
        return f"Error retrieving memories: {e}"
    if not memories:
        date_info = ""
        if start_dt and end_dt:
            date_info = f" between {start_dt.strftime('%Y-%m-%d')} and {end_dt.strftime('%Y-%m-%d')}"
        elif start_dt:
            date_info = f" after {start_dt.strftime('%Y-%m-%d')}"
        elif end_dt:
            date_info = f" before {end_dt.strftime('%Y-%m-%d')}"
        return f"No memories found{date_info}."

    if source_sink is not None:
        for memory in memories[:128]:
            source_sink.append(
                {
                    'kind': 'memory',
                    'source_id': memory.memory_id or memory.id,
                    'title': 'Memory',
                    'preview': str(memory.content or '')[:600],
                    'created_at': safe_isoformat(memory.created_at),
                }
            )

    return f"User Memories ({len(memories)} total):\n\n{MemoryDB.get_memories_as_str(memories)}".strip()


def search_memories_text(
    uid: str,
    query: str,
    limit: int = 5,
    source_sink: Optional[List[dict[str, Any]]] = None,
) -> str:
    """Semantic vector search for memories, formatted as LLM-ready text."""
    logger.info(f"search_memories_text - uid: {uid}, query: {query}, limit: {limit}")

    limit = max(1, min(limit, 20))

    # Memory dates go to the chat model; the UTC date rolls over at a different instant than
    # the user's, so a raw UTC date is a day late for them in the evening (issue #6214).
    try:
        display_tz, _ = resolve_display_tz(notification_db.get_user_time_zone(uid))
    except Exception as tz_error:
        logger.warning(f"search_memories_text - timezone lookup failed, formatting dates in UTC: {tz_error}")
        display_tz = timezone.utc

    try:
        matches = MemoryService(db_client=firestore_db).search(uid, query, limit=limit)
        matches = [match for match in matches if not match.memory.is_locked]
        if not matches:
            return f"No memories found matching '{query}'."
        result = f"Found {len(matches)} memories matching '{query}':\n\n"
        for match in matches:
            memory = match.memory
            date_str = format_local_date(memory.created_at, display_tz) if memory.created_at else 'Unknown'
            result += f"- {memory.content} (relevance: {match.score:.2f}, category: {memory.category.value}, date: {date_str})\n"

        if source_sink is not None:
            for match in matches[:128]:
                memory = match.memory
                source_sink.append(
                    {
                        'kind': 'memory',
                        'source_id': memory.memory_id or memory.id,
                        'title': 'Memory',
                        'preview': str(memory.content or '')[:600],
                        'created_at': safe_isoformat(memory.created_at),
                    }
                )

        return result.strip()

    except Exception as e:
        logger.error(f"search_memories_text error: {e}")
        return f"Error searching memories: {e}"
