"""Shared canonical default-visibility filter (WS-L / overnight finding B).

§1.3: processed + active + short_term memories remain default-visible even though the
L2 lifecycle filter withholds them until explicit disposition.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List

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


def _log_expiry_disposition_observations(items: List[MemoryItem], *, now: datetime) -> None:
    expired_pending_terminal_apply = 0
    for item in items:
        if (
            item.tier == MemoryTier.short_term
            and item.status == MemoryItemStatus.active
            and item.processing_state == ProcessingState.processed
            and effective_short_term_expiry(item) <= now
        ):
            expired_pending_terminal_apply += 1
    if expired_pending_terminal_apply:
        logger.warning(
            "canonical_memory_expiry_observation: expired_active_pending_terminal_apply count=%d",
            expired_pending_terminal_apply,
        )
        record_fallback(
            component='memory_analytics',
            from_mode='ttl_hidden',
            to_mode='readable_pending_adjudication',
            reason='policy',
            outcome='degraded',
            log=logger,
        )


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
