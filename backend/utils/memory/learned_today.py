"""Deterministic "memories learned today" selection for the daily summary.

The daily summary already carries `knowledge_nuggets`, which are LLM prose with
no memory identity: a client cannot vote on them, correct them, or show what
Omi actually stored. This module picks the real memories the day produced so a
shell can render a native review card.

The selection is a pure filter/sort over the canonical read path
(`MemoryService.read`) — no model call, no new query surface, and no second
memory authority. Review state is deliberately **not** captured here: clients
read `user_review`/`edited` live from the memory so a vote on one device shows
on the other.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Iterable, List, Optional, Sequence

from models.daily_summary_payload import LearnedMemoryRef
from utils.observability.fallback import record_fallback

if TYPE_CHECKING:  # `models.memories` drags in database._client and the Firestore
    # protos; this module is only annotating with MemoryDB, and callers that import
    # it (the users router, the scheduled summary job) must not pay a Firestore
    # import — or, under a stubbed sys.modules test, a duplicate proto registration.
    from models.memories import MemoryDB

logger = logging.getLogger(__name__)

# Cap on rendered review items. Three is the product cap for the card; the card
# is a glance, not a queue.
MEMORIES_LEARNED_LIMIT = 3

# Newest-first read depth. `MemoryService.read` returns the merged canonical +
# historical page ordered by updated_at/created_at descending, so one bounded
# page is enough to cover a single day for any realistic capture rate.
MEMORIES_LEARNED_SCAN_LIMIT = 200

MemoryReader = Callable[..., List["MemoryDB"]]


@dataclass(frozen=True, order=True)
class _MemoryRank:
    """Named sortable key for deterministic review-card ordering."""

    capture_confidence: float
    veracity: float
    created_timestamp: float
    memory_id: str


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _is_eligible(memory: "MemoryDB") -> bool:
    """Exclude every state the review card must never show.

    `MemoryService.read` already drops tombstoned, superseded, hidden, archived
    and restricted rows by service policy. These checks are the product-level
    exclusions on top of that, and they also hold for a caller that injects a
    narrower reader.
    """
    if memory.user_review is False:
        # The owner already rejected this fact; re-asking is the bug.
        return False
    if memory.is_locked:
        return False
    if memory.invalid_at is not None:
        return False
    if memory.superseded_by:
        return False
    if not (memory.content or '').strip():
        return False
    return True


def _from_day(
    memory: "MemoryDB", *, conversation_ids: frozenset[str], start: Optional[datetime], end: Optional[datetime]
) -> bool:
    """Attribute a memory to the day the summary was built from.

    Primary rule: the memory points at one of the conversations the summary was
    generated from. Fallback (a memory with no conversation evidence, e.g. a
    manual capture): its `created_at` falls inside the summary's local-day
    window. A memory that points at a conversation *outside* the summarised set
    is deliberately excluded — it belongs to another day's card.
    """
    # `MemoryDB.memory_id` is a deprecated alias that always mirrors `id`, so
    # `conversation_id` is the only conversation evidence on this model.
    conversation_id = memory.conversation_id
    if conversation_id:
        return conversation_id in conversation_ids
    window_start = _aware(start)
    window_end = _aware(end)
    created_at = _aware(memory.created_at)
    if window_start is None or window_end is None or created_at is None:
        return False
    return window_start <= created_at <= window_end


def _rank(memory: "MemoryDB") -> _MemoryRank:
    """Highest capture_confidence, then veracity, then newest, then stable id."""
    created_at = _aware(memory.created_at)
    created_ts = created_at.timestamp() if created_at else float('-inf')
    return _MemoryRank(
        capture_confidence=-(memory.capture_confidence if memory.capture_confidence is not None else 0.0),
        veracity=-(memory.veracity if memory.veracity is not None else 0.0),
        created_timestamp=-created_ts,
        memory_id=memory.id or '',
    )


def select_memories_learned(
    memories: Iterable["MemoryDB"],
    *,
    conversation_ids: Sequence[str],
    window_start: Optional[datetime] = None,
    window_end: Optional[datetime] = None,
    limit: int = MEMORIES_LEARNED_LIMIT,
) -> List[LearnedMemoryRef]:
    """Pure selection over an already-read memory page."""
    wanted = frozenset(cid for cid in conversation_ids if cid)
    candidates = [
        memory
        for memory in memories
        if _is_eligible(memory) and _from_day(memory, conversation_ids=wanted, start=window_start, end=window_end)
    ]
    candidates.sort(key=_rank)
    return [
        LearnedMemoryRef(
            memory_id=memory.id,
            content=(memory.content or '').strip(),
            category=getattr(memory.category, 'value', memory.category) or '',
            captured_at=_aware(memory.created_at),
        )
        for memory in candidates[: max(0, int(limit))]
    ]


def memories_learned_for_summary(
    uid: str,
    *,
    conversation_ids: Sequence[str],
    window_start: Optional[datetime] = None,
    window_end: Optional[datetime] = None,
    limit: int = MEMORIES_LEARNED_LIMIT,
    read_memories: Optional[MemoryReader] = None,
    scan_limit: int = MEMORIES_LEARNED_SCAN_LIMIT,
) -> List[LearnedMemoryRef]:
    """Read one bounded canonical page and select the day's review items.

    Never raises: the daily summary is the product, and a memory-read failure
    must degrade to "no card", not to "no summary".
    """
    reader = read_memories
    if reader is None:
        from utils.memory.memory_service import MemoryService  # local: heavy import, avoids a cycle

        reader = MemoryService().read
    try:
        page: List["MemoryDB"] = reader(uid, limit=scan_limit, offset=0)
    except Exception as error:  # noqa: BLE001 - the summary must still ship
        # Fail-open: the day still gets a summary, just no review card. That is a
        # correctness change, so it is reported rather than swallowed silently.
        record_fallback(
            component='daily_summary',
            from_mode='memories_learned',
            to_mode='none',
            reason='malformed_doc' if isinstance(error, (TypeError, ValueError)) else 'other',
            outcome='degraded',
            log=logger,
        )
        logger.warning('memories_learned read failed for daily summary: %s', type(error).__name__)
        return []
    return select_memories_learned(
        page,
        conversation_ids=conversation_ids,
        window_start=window_start,
        window_end=window_end,
        limit=limit,
    )


def memory_review_card_block(
    summary_id: str,
    *,
    date: str,
    memories_learned: Sequence[Any],
) -> Optional[dict[str, Any]]:
    """Build the `memoryReviewCard` chat content block, or None when empty.

    Accepts either `LearnedMemoryRef` objects or the stored dict projection so
    both the generator and the router can call it.
    """
    items: List[dict[str, Any]] = []
    for entry in memories_learned or []:
        if isinstance(entry, dict):
            memory_id = entry.get('memory_id')
            content = entry.get('content')
            category = entry.get('category')
        else:
            memory_id = getattr(entry, 'memory_id', None)
            content = getattr(entry, 'content', None)
            category = getattr(entry, 'category', None)
        if not memory_id:
            continue
        items.append({'memoryId': memory_id, 'content': content or '', 'category': category or ''})
    if not items:
        return None
    return {
        'type': 'memoryReviewCard',
        'id': f'{summary_id}:memories',
        'summaryId': summary_id,
        'date': date,
        'items': items,
    }
