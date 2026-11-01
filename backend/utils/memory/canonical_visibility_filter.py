"""Shared canonical default-visibility filter (WS-L / overnight finding B).

§1.3: processed + active + short_term memories remain default-visible even though the
L2 lifecycle filter withholds them until explicit disposition.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import Iterator, List, Optional

from database.product_memory_items import filter_default_product_memory_items
from models.product_memory import (
    MemoryAccessPolicy,
    MemoryItemStatus,
    MemoryTier,
    ProcessingState,
    MemoryItem,
    effective_short_term_expiry,
    is_default_access_eligible,
)
from utils.observability.fallback import record_fallback

_L2_PROCESSED_REQUIRES_DISPOSITION = "short_term_l2_processed_requires_explicit_lifecycle_disposition"
logger = logging.getLogger(__name__)

# Keyset list reads call this filter once per row. Batch those observations so
# one page emits one warning instead of one warning per expired short-term item.
_batched_expiry_observations: ContextVar[Optional[List[int]]] = ContextVar(
    "batched_canonical_expiry_observations",
    default=None,
)


def _expired_active_pending_terminal_count(items: List[MemoryItem], *, now: datetime) -> int:
    expired_pending_terminal_apply = 0
    for item in items:
        if (
            item.tier == MemoryTier.short_term
            and item.status == MemoryItemStatus.active
            and item.processing_state == ProcessingState.processed
            and effective_short_term_expiry(item) <= now
        ):
            expired_pending_terminal_apply += 1
    return expired_pending_terminal_apply


def _emit_expiry_disposition_observation(count: int) -> None:
    if count <= 0:
        return
    logger.warning(
        "canonical_memory_expiry_observation: expired_active_pending_terminal_apply count=%d",
        count,
    )
    record_fallback(
        component='memory_analytics',
        from_mode='ttl_hidden',
        to_mode='readable_pending_adjudication',
        reason='policy',
        outcome='degraded',
        log=logger,
    )


@contextmanager
def batch_canonical_expiry_observations() -> Iterator[None]:
    """Collect per-row expiry observations and emit one warning for the batch.

    Visibility is unchanged. The batch only collapses the read-path log that
    the keyset walker used to emit once per singleton filter call.
    """
    counts = [0]
    token = _batched_expiry_observations.set(counts)
    try:
        yield
    finally:
        _batched_expiry_observations.reset(token)
        _emit_expiry_disposition_observation(counts[0])


def _log_expiry_disposition_observations(items: List[MemoryItem], *, now: datetime) -> None:
    count = _expired_active_pending_terminal_count(items, now=now)
    if not count:
        return
    batch = _batched_expiry_observations.get()
    if batch is not None:
        batch[0] += count
        return
    _emit_expiry_disposition_observation(count)


def filter_canonical_default_visible_items(
    items: List[MemoryItem],
    *,
    policy: MemoryAccessPolicy,
    now: datetime,
) -> List[MemoryItem]:
    """Return default-visible canonical items, including §1.3 processed short_term."""
    _log_expiry_disposition_observations(items, now=now)
    report = filter_default_product_memory_items(items, policy=policy, now=now)
    visible_by_id = {
        item.memory_id: item for item in report.visible_items if item.processing_state == ProcessingState.processed
    }

    for item in items:
        if item.memory_id in visible_by_id:
            continue
        decision = report.decisions.get(item.memory_id)
        if decision is None or not decision.lifecycle_reason:
            continue
        if (
            decision.lifecycle_reason == _L2_PROCESSED_REQUIRES_DISPOSITION
            and item.tier == MemoryTier.short_term
            and item.status == MemoryItemStatus.active
            and item.processing_state == ProcessingState.processed
            and is_default_access_eligible(item, policy, now=now).allowed
        ):
            visible_by_id[item.memory_id] = item

    # §user-review: exclude memories explicitly rejected by the user.
    for item in items:
        promotion = item.promotion or {}
        if promotion.get("user_review") is False and item.memory_id in visible_by_id:
            del visible_by_id[item.memory_id]

    return sorted(visible_by_id.values(), key=lambda item: (-item.updated_at.timestamp(), item.memory_id))
