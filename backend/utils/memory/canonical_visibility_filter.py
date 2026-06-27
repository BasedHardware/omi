"""Shared canonical default-visibility filter (WS-L / overnight finding B).

§1.3: processed + active + short_term memories remain default-visible even though the
L2 lifecycle filter withholds them until explicit disposition.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

from database.product_memory_items import filter_default_product_memory_items
from models.product_memory import (
    MemoryAccessPolicy,
    MemoryItemStatus,
    MemoryTier,
    ProcessingState,
    MemoryItem,
    is_default_access_eligible,
)

_L2_PROCESSED_REQUIRES_DISPOSITION = "short_term_l2_processed_requires_explicit_lifecycle_disposition"


def filter_canonical_default_visible_items(
    items: List[MemoryItem],
    *,
    policy: MemoryAccessPolicy,
    now: datetime,
) -> List[MemoryItem]:
    """Return default-visible canonical items, including §1.3 processed short_term."""
    report = filter_default_product_memory_items(items, policy=policy, now=now)
    visible_by_id = {item.memory_id: item for item in report.visible_items}

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
