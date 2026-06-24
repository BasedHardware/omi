"""Canonical alias module for ``models.v17_memory_contracts`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from models.v17_memory_contracts import (
    DurableMemoryPatch,
    DurablePatchDecision,
    EvidenceRef,
    L1MemoryArchiveClass,
    L1MemoryArchiveItem,
    L2MemoryRoute,
    L2SearchPlan,
    L2SearchRequest,
    L2SearchResult,
    LifecycleState,
    SourceBackedMemoryCandidate,
    WorkingMemoryObservation,
    derive_allowed_use,
    deterministic_contract_id,
    filter_l1_archive_for_normal_search,
)

# Neutral symbol aliases (WS-G Wave 31) — same types, canonical names for new code.
WorkingObservation = WorkingMemoryObservation
WorkingObservationArchiveItem = L1MemoryArchiveItem
PromotionRoute = L2MemoryRoute

__all__ = [
    "DurableMemoryPatch",
    "DurablePatchDecision",
    "EvidenceRef",
    "L1MemoryArchiveClass",
    "L1MemoryArchiveItem",
    "L2MemoryRoute",
    "L2SearchPlan",
    "L2SearchRequest",
    "L2SearchResult",
    "LifecycleState",
    "PromotionRoute",
    "SourceBackedMemoryCandidate",
    "WorkingMemoryObservation",
    "WorkingObservation",
    "WorkingObservationArchiveItem",
    "derive_allowed_use",
    "deterministic_contract_id",
    "filter_l1_archive_for_normal_search",
]
