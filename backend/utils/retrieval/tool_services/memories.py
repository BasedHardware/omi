"""
Shared service functions for memory retrieval.
Used by both LangChain tools (mobile chat) and REST router (desktop/web).
"""

from datetime import datetime, timezone
from typing import Any, List, Optional

from database._client import db as firestore_db
from utils.model_text import format_date, format_instant, truncation_note
from utils.user_clock import clock_for_uid
from utils.memory.memory_service import MemoryService
from utils.retrieval.tool_services.conversations import parse_iso_date
from utils.retrieval.safety import safe_isoformat
from utils.retrieval.memory_evidence import MAX_MEMORY_EVIDENCE_CHARS, format_memory_evidence, render_memory_evidence
import logging

logger = logging.getLogger(__name__)
_MEMORY_TRUNCATION_RESERVE = 256


def _memory_truncation_suffix(shown: int) -> str:
    return "\n\n" + truncation_note(
        shown=shown,
        total=None,
        unit="memories",
        how_to_get_more="request another page or narrow the topic or date range",
        cut=True,
    )


def _memory_read_date(memory: object) -> Optional[datetime]:
    """Use the creation clock for memory citations and date filters."""
    created_at = getattr(memory, 'created_at', None)
    return created_at if isinstance(created_at, datetime) else None


def get_memories_text(
    uid: str,
    limit: int = 50,
    offset: int = 0,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    view: Optional[str] = None,
    as_of: Optional[datetime] = None,
    now: Optional[datetime] = None,
    source_sink: Optional[List[dict[str, Any]]] = None,
) -> str:
    """Fetch user memories/facts and format as LLM-ready text."""
    # Older clients still send the removed temporal selector. Accept and ignore
    # it so their requests continue to receive the released current-memory view.
    _ = view, as_of
    logger.info(f"get_memories_text - uid: {uid}, limit: {limit}, offset: {offset}")
    clock = clock_for_uid(uid)

    # Cap request bounds before either memory or legacy reads.
    limit = max(1, min(limit, 5000))
    offset = max(0, offset)

    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = parse_iso_date(start_date, 'start_date')
        except ValueError:
            return "Error: Invalid start_date format."
    if end_date:
        try:
            end_dt = parse_iso_date(end_date, 'end_date')
        except ValueError:
            return "Error: Invalid end_date format."

    try:
        service = MemoryService(db_client=firestore_db)
        target_end = min(offset + limit, 5000)
        scan_offset = 0
        visible = []
        max_scan = 5000
        scan_truncated = False
        while scan_offset < max_scan and len(visible) < target_end:
            batch_limit = min(500, max_scan - scan_offset)
            fetch_limit = target_end if scan_offset == 0 else batch_limit
            batch = service.read(uid, limit=fetch_limit, offset=scan_offset, now=now)
            if not batch:
                break
            scan_offset += len(batch)
            for memory in batch:
                if memory.is_locked or getattr(memory, 'user_review', None) is False:
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
        logger.error("get_memories_text failed uid=%s (error_type=%s)", uid, type(e).__name__)
        return "Error retrieving memories. Please try again."
    if not memories:
        date_info = ""
        if start_dt and end_dt:
            date_info = f" between {format_date(start_dt, clock)} and {format_date(end_dt, clock)}"
        elif start_dt:
            date_info = f" after {format_date(start_dt, clock)}"
        elif end_dt:
            date_info = f" before {format_date(end_dt, clock)}"
        suffix = " The bounded scan reached its safety limit; more memories may exist." if scan_truncated else ""
        return f"No memories found{date_info}.{suffix}"

    title = "User Memories"
    if scan_truncated:
        title += " (bounded scan; more may exist)"
    records = []
    for memory in memories:
        # Preserve the existing list formatter's preference for the evidence clock.
        stamp = _memory_read_date(memory)
        if stamp and stamp.tzinfo is not None:
            stamp = stamp.astimezone(timezone.utc)
        date_str = format_instant(stamp, clock) if stamp else 'Unknown'
        records.append(
            format_memory_evidence(
                memory.content,
                suffix=f'date: {date_str}',
                subject_attribution=getattr(memory, 'subject_attribution', 'unknown'),
            )
        )
    included_indices: list[int] = []
    more_available = scan_truncated or len(memories) >= limit
    result = render_memory_evidence(
        records,
        title=title,
        max_chars=MAX_MEMORY_EVIDENCE_CHARS - _MEMORY_TRUNCATION_RESERVE,
        more_available=more_available,
        offset=None if scan_truncated else offset,
        included_indices=included_indices,
    )

    if source_sink is not None:
        # Structured client source metadata; not model-facing prose.
        for index in included_indices[:128]:
            memory = memories[index]
            source_sink.append(
                {
                    'kind': 'memory',
                    'source_id': memory.memory_id or memory.id,
                    'title': 'Memory',
                    'preview': str(memory.content or '')[:600],
                    'created_at': safe_isoformat(_memory_read_date(memory) or memory.created_at),
                }
            )

    if more_available or len(included_indices) < len(records):
        result += _memory_truncation_suffix(len(included_indices))
    return result


def search_memories_text(
    uid: str,
    query: str,
    limit: int = 5,
    view: Optional[str] = None,
    as_of: Optional[datetime] = None,
    source_sink: Optional[List[dict[str, Any]]] = None,
) -> str:
    """Semantic vector search for memories, formatted as LLM-ready text."""
    # Preserve request compatibility while all searches use the current view.
    _ = view, as_of
    logger.info(f"search_memories_text - uid: {uid}, query: {query}, limit: {limit}")

    limit = max(1, min(limit, 20))

    # Memory dates go to the chat model; the UTC date rolls over at a different instant than
    # the user's, so a raw UTC date is a day late for them in the evening (issue #6214).
    clock = clock_for_uid(uid)

    try:
        matches = MemoryService(db_client=firestore_db).search(uid, query, limit=limit)
        matches = [match for match in matches if not match.memory.is_locked]
        if not matches:
            return f"No memories found matching '{query}'."
        records = []
        for match in matches:
            memory = match.memory
            display_date = _memory_read_date(memory)
            date_str = format_date(display_date, clock) if display_date else 'Unknown'
            suffix = f"relevance: {match.score:.2f}, category: {memory.category.value}, date: {date_str}"
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

        if source_sink is not None:
            # Structured client source metadata; not model-facing prose.
            for index in included_indices[:128]:
                memory = matches[index].memory
                source_sink.append(
                    {
                        'kind': 'memory',
                        'source_id': memory.memory_id or memory.id,
                        'title': 'Memory',
                        'preview': str(memory.content or '')[:600],
                        'created_at': safe_isoformat(_memory_read_date(memory) or memory.created_at),
                    }
                )

        if len(included_indices) < len(records):
            result += _memory_truncation_suffix(len(included_indices))
        return result

    except Exception as e:
        logger.error("search_memories_text failed uid=%s (error_type=%s)", uid, type(e).__name__)
        return "Error searching memories. Please try again."
