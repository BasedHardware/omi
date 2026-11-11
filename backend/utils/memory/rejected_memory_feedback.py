"""Bounded, sensitivity-safe owner-rejection feedback for memory prompts."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Tuple, cast

from cachetools import TTLCache
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database.firestore_index_registry import RECENT_REJECTED_MEMORY_FEEDBACK_QUERY
from database.memory_collections import MemoryCollections
from models.memory_evidence import SourceState
from models.product_memory import (
    RESTRICTED_SENSITIVITY_LABELS,
    MemoryItem,
    MemoryItemStatus,
)

REJECTED_MEMORY_FEEDBACK_QUERY_LIMIT = 8
REJECTED_MEMORY_FEEDBACK_SCAN_LIMIT = 24
REJECTED_MEMORY_FEEDBACK_ITEM_MAX_CHARS = 180
REJECTED_MEMORY_FEEDBACK_TOTAL_MAX_CHARS = 1_600
REJECTED_MEMORY_FEEDBACK_MAX_AGE = timedelta(days=30)
REJECTED_MEMORY_FEEDBACK_CACHE_TTL_SECONDS = 300
REJECTED_MEMORY_FEEDBACK_CACHE_MAX_USERS = 4_096


@dataclass(frozen=True)
class RejectedMemoryFeedback:
    memory_id: str
    content: str
    updated_at: datetime


_feedback_cache: TTLCache[str, Tuple[RejectedMemoryFeedback, ...]] = TTLCache(
    maxsize=REJECTED_MEMORY_FEEDBACK_CACHE_MAX_USERS,
    ttl=REJECTED_MEMORY_FEEDBACK_CACHE_TTL_SECONDS,
)
_feedback_cache_lock = threading.Lock()


def clear_rejected_memory_feedback_cache(uid: str | None = None) -> None:
    """Invalidate prompt-safe rejection examples for one owner or every owner."""
    with _feedback_cache_lock:
        if uid is None:
            _feedback_cache.clear()
        else:
            _feedback_cache.pop(uid, None)


def bound_rejected_memory_examples(examples: Sequence[str]) -> Tuple[str, ...]:
    """Normalize and hard-bound negative-example text before prompt assembly."""
    bounded: list[str] = []
    seen: set[str] = set()
    total_chars = 0
    for raw_example in examples:
        normalized = " ".join((raw_example or "").split())
        if not normalized:
            continue
        normalized = normalized[:REJECTED_MEMORY_FEEDBACK_ITEM_MAX_CHARS]
        dedup_key = normalized.casefold()
        if dedup_key in seen:
            continue
        if total_chars + len(normalized) > REJECTED_MEMORY_FEEDBACK_TOTAL_MAX_CHARS:
            break
        seen.add(dedup_key)
        bounded.append(normalized)
        total_chars += len(normalized)
        if len(bounded) >= REJECTED_MEMORY_FEEDBACK_QUERY_LIMIT:
            break
    return tuple(bounded)


def _snapshot_payload(snapshot: Any) -> Dict[str, Any]:
    if not getattr(snapshot, "exists", False):
        return {}
    raw = snapshot.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


def _is_prompt_eligible_rejection(item: MemoryItem, *, uid: str, cutoff: datetime) -> bool:
    if (
        item.uid != uid
        or item.status not in {MemoryItemStatus.active, MemoryItemStatus.hidden}
        or item.source_state != SourceState.active
    ):
        return False
    if (item.promotion or {}).get("user_review") is not False:
        return False
    if item.updated_at < cutoff:
        return False
    normalized_labels = {label.strip().lower() for label in item.sensitivity_labels if label and label.strip()}
    return not normalized_labels.intersection(RESTRICTED_SENSITIVITY_LABELS)


def get_recent_rejected_memory_examples(
    uid: str,
    *,
    db_client: Any,
    now: datetime | None = None,
) -> Tuple[str, ...]:
    """Return only the bounded prompt text for L1 extraction."""
    return tuple(
        feedback.content
        for feedback in get_recent_rejected_memory_feedback(
            uid,
            db_client=db_client,
            now=now,
        )
    )


def get_recent_rejected_memory_feedback(
    uid: str,
    *,
    db_client: Any,
    now: datetime | None = None,
) -> Tuple[RejectedMemoryFeedback, ...]:
    """Return newest prompt-eligible owner rejections through one bounded indexed query.

    Only already-filtered, non-restricted text enters the short process-local cache.
    Callers own fail-open behavior so feedback-read failures remain observable.
    """
    with _feedback_cache_lock:
        cached = _feedback_cache.get(uid)
    if cached is not None:
        return tuple(cached)

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("rejected memory feedback time must be timezone-aware")
    cutoff = current_time.astimezone(timezone.utc) - REJECTED_MEMORY_FEEDBACK_MAX_AGE
    collection = db_client.collection(MemoryCollections(uid=uid).memory_items)
    query = RECENT_REJECTED_MEMORY_FEEDBACK_QUERY.build(
        collection,
        {
            "statuses": [MemoryItemStatus.active.value, MemoryItemStatus.hidden.value],
            "source_state": SourceState.active.value,
            "user_review": False,
            "updated_at": cutoff,
        },
        field_filter_factory=FieldFilter,
    )
    query = query.order_by("updated_at", direction=firestore.Query.DESCENDING).order_by("__name__")
    feedback_items: list[RejectedMemoryFeedback] = []
    for snapshot in query.limit(REJECTED_MEMORY_FEEDBACK_SCAN_LIMIT).stream():
        payload = _snapshot_payload(snapshot)
        if not payload:
            continue
        try:
            item = MemoryItem.model_validate(payload)
        except Exception:
            continue
        if getattr(snapshot, "id", None) != item.memory_id:
            continue
        if not _is_prompt_eligible_rejection(item, uid=uid, cutoff=cutoff):
            continue
        normalized_content = bound_rejected_memory_examples([item.content or ""])
        if not normalized_content:
            continue
        feedback_items.append(
            RejectedMemoryFeedback(
                memory_id=item.memory_id,
                content=normalized_content[0],
                updated_at=item.updated_at,
            )
        )

    bounded_contents = bound_rejected_memory_examples([feedback.content for feedback in feedback_items])
    feedback_by_content: dict[str, RejectedMemoryFeedback] = {}
    for feedback in feedback_items:
        feedback_by_content.setdefault(feedback.content, feedback)
    bounded = tuple(feedback_by_content[content] for content in bounded_contents)
    with _feedback_cache_lock:
        _feedback_cache[uid] = bounded
    return bounded
