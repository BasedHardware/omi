from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from models.product_memory import (
    AccessDecision,
    MemoryAccessPolicy,
    MemoryTier,
    MemoryItem,
    is_default_access_eligible,
)
from utils.memory.short_term_lifecycle import ShortTermLifecycleDecision, evaluate_short_term_lifecycle

LifecycleAuditMetadata = Dict[str, Any]


def _empty_memory_items() -> List[MemoryItem]:
    return []


def _empty_decisions() -> Dict[str, "ProductMemoryItemDecision"]:
    return {}


def _empty_lifecycle_audit_metadata() -> Dict[str, LifecycleAuditMetadata]:
    return {}


@dataclass(frozen=True)
class ProductMemoryItemDecision:
    allowed: bool
    reason: str
    access_reason: str
    lifecycle_reason: Optional[str] = None


@dataclass(frozen=True)
class DefaultProductMemoryReadReport:
    visible_items: List[MemoryItem] = field(default_factory=_empty_memory_items)
    decisions: Dict[str, ProductMemoryItemDecision] = field(default_factory=_empty_decisions)
    lifecycle_audit_metadata: Dict[str, LifecycleAuditMetadata] = field(default_factory=_empty_lifecycle_audit_metadata)


def _current_time(now: Optional[datetime]) -> datetime:
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError('product memory read timestamp must be timezone-aware')
    return current_time.astimezone(timezone.utc)


def _decision_from_access(access: AccessDecision) -> ProductMemoryItemDecision:
    return ProductMemoryItemDecision(allowed=access.allowed, reason=access.reason, access_reason=access.reason)


def _decision_from_lifecycle(
    access: AccessDecision, lifecycle: ShortTermLifecycleDecision
) -> ProductMemoryItemDecision:
    lifecycle_reason = str(lifecycle.audit_metadata['decision_reason'])
    if not lifecycle.default_access_allowed:
        return ProductMemoryItemDecision(
            allowed=False,
            reason=lifecycle_reason,
            access_reason=access.reason,
            lifecycle_reason=lifecycle_reason,
        )
    if not access.allowed:
        return ProductMemoryItemDecision(
            allowed=False,
            reason=access.reason,
            access_reason=access.reason,
            lifecycle_reason=lifecycle_reason,
        )
    return ProductMemoryItemDecision(
        allowed=True,
        reason=access.reason,
        access_reason=access.reason,
        lifecycle_reason=lifecycle_reason,
    )


def filter_default_product_memory_items(
    items: Iterable[MemoryItem], *, policy: MemoryAccessPolicy, now: Optional[datetime] = None
) -> DefaultProductMemoryReadReport:
    """Filter authoritative memory memory items for default product reads.

    This helper is intentionally narrow: callers pass already-fetched authoritative
    `memory_items`, and the seam returns only default-visible Short-term/Long-term
    items. Archive remains excluded by the base product policy and Short-term
    freshness/L2/source-tombstone handling is delegated to the deterministic
    lifecycle evaluator so later workers can persist the exposed audit metadata.
    """

    current_time = _current_time(now)
    visible_items: List[MemoryItem] = []
    decisions: Dict[str, ProductMemoryItemDecision] = {}
    lifecycle_audit_metadata: Dict[str, LifecycleAuditMetadata] = {}

    for item in items:
        access = is_default_access_eligible(item, policy, now=current_time)
        if item.tier == MemoryTier.short_term:
            lifecycle = evaluate_short_term_lifecycle(item, now=current_time)
            audit_metadata = dict(lifecycle.audit_metadata)
            audit_metadata['requires_lifecycle_decision'] = lifecycle.requires_lifecycle_decision
            audit_metadata['default_access_allowed'] = lifecycle.default_access_allowed
            audit_metadata['outcome'] = lifecycle.outcome.value
            lifecycle_audit_metadata[item.memory_id] = audit_metadata
            decision = _decision_from_lifecycle(access, lifecycle)
        else:
            decision = _decision_from_access(access)

        decisions[item.memory_id] = decision
        if decision.allowed:
            visible_items.append(item)

    return DefaultProductMemoryReadReport(
        visible_items=visible_items,
        decisions=decisions,
        lifecycle_audit_metadata=lifecycle_audit_metadata,
    )
