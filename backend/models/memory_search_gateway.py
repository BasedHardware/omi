from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from models.product_memory import (
    MemoryAccessPolicy,
    MemoryItem,
    is_archive_access_eligible,
    is_default_access_eligible,
)


class SearchMode(str, Enum):
    default = "default"
    archive_explicit = "archive_explicit"


class SearchDecision(str, Enum):
    allowed = "allowed"
    missing_authoritative_item = "missing_authoritative_item"
    stale_projection = "stale_projection"
    stale_vector = "stale_vector"
    access_denied = "access_denied"


class VectorRepairPurgeReason(str, Enum):
    missing_authoritative_item = "missing_authoritative_item"
    stale_projection_commit = "stale_projection_commit"
    missing_vector_freshness_metadata = "missing_vector_freshness_metadata"
    stale_account_generation = "stale_account_generation"
    cross_user_vector_metadata = "cross_user_vector_metadata"
    stale_item_revision = "stale_item_revision"
    stale_source_commit = "stale_source_commit"
    stale_content_hash = "stale_content_hash"
    stale_vector_updated_at = "stale_vector_updated_at"


class SearchVectorHit(BaseModel):
    vector_id: Optional[str] = None
    memory_id: str
    score: float
    projection_commit_id: str
    vector_updated_at: datetime
    uid: Optional[str] = None
    account_generation: Optional[int] = None
    item_revision: Optional[int] = None
    source_commit_id: Optional[str] = None
    content_hash: Optional[str] = None


class HydratedSearchResult(BaseModel):
    item: MemoryItem
    score: float
    projection_commit_id: str


class SearchGatewayResult(BaseModel):
    results: List[HydratedSearchResult] = Field(default_factory=list)
    decisions: Dict[str, SearchDecision] = Field(default_factory=dict)
    repair_purge_candidates: List[Dict[str, Any]] = Field(default_factory=list[Dict[str, Any]])


def hydrate_and_filter_vector_hits(
    *,
    hits: List[SearchVectorHit],
    authoritative_items: Dict[str, MemoryItem],
    policy: MemoryAccessPolicy,
    mode: SearchMode,
    required_projection_commit_id: str,
    required_account_generation: int,
    now: Optional[datetime] = None,
) -> SearchGatewayResult:
    """Fail-closed vector gateway.

    Vector hits are never returned directly. Every hit must hydrate against the
    authoritative memory item and pass projection freshness + access checks.
    Hydration rejects that prove a stale vector ID are returned as repair/purge
    candidates for a fake-injectable worker/outbox seam; access-policy rejects
    are not purge candidates.
    """
    results: List[HydratedSearchResult] = []
    decisions: Dict[str, SearchDecision] = {}
    repair_purge_candidates: List[Dict[str, Any]] = []
    for hit in sorted(hits, key=lambda item: item.score, reverse=True):
        item = authoritative_items.get(hit.memory_id)
        if item is None:
            decisions[hit.memory_id] = SearchDecision.missing_authoritative_item
            repair_purge_candidates.append(
                _repair_purge_candidate(
                    hit=hit,
                    reason=VectorRepairPurgeReason.missing_authoritative_item,
                    required_projection_commit_id=required_projection_commit_id,
                    required_account_generation=required_account_generation,
                    authoritative_item=None,
                )
            )
            continue
        if hit.projection_commit_id != required_projection_commit_id:
            decisions[hit.memory_id] = SearchDecision.stale_projection
            repair_purge_candidates.append(
                _repair_purge_candidate(
                    hit=hit,
                    reason=VectorRepairPurgeReason.stale_projection_commit,
                    required_projection_commit_id=required_projection_commit_id,
                    required_account_generation=required_account_generation,
                    authoritative_item=item,
                )
            )
            continue
        if hit.uid is None or hit.account_generation is None or hit.item_revision is None:
            decisions[hit.memory_id] = SearchDecision.stale_vector
            repair_purge_candidates.append(
                _repair_purge_candidate(
                    hit=hit,
                    reason=VectorRepairPurgeReason.missing_vector_freshness_metadata,
                    required_projection_commit_id=required_projection_commit_id,
                    required_account_generation=required_account_generation,
                    authoritative_item=item,
                )
            )
            continue
        if item.source_commit_id is not None and hit.source_commit_id is None:
            decisions[hit.memory_id] = SearchDecision.stale_vector
            repair_purge_candidates.append(
                _repair_purge_candidate(
                    hit=hit,
                    reason=VectorRepairPurgeReason.missing_vector_freshness_metadata,
                    required_projection_commit_id=required_projection_commit_id,
                    required_account_generation=required_account_generation,
                    authoritative_item=item,
                )
            )
            continue
        if item.content_hash is not None and hit.content_hash is None:
            decisions[hit.memory_id] = SearchDecision.stale_vector
            repair_purge_candidates.append(
                _repair_purge_candidate(
                    hit=hit,
                    reason=VectorRepairPurgeReason.missing_vector_freshness_metadata,
                    required_projection_commit_id=required_projection_commit_id,
                    required_account_generation=required_account_generation,
                    authoritative_item=item,
                )
            )
            continue
        if item.account_generation != required_account_generation:
            decisions[hit.memory_id] = SearchDecision.stale_vector
            repair_purge_candidates.append(
                _repair_purge_candidate(
                    hit=hit,
                    reason=VectorRepairPurgeReason.stale_account_generation,
                    required_projection_commit_id=required_projection_commit_id,
                    required_account_generation=required_account_generation,
                    authoritative_item=item,
                )
            )
            continue
        if hit.uid != item.uid:
            decisions[hit.memory_id] = SearchDecision.stale_vector
            repair_purge_candidates.append(
                _repair_purge_candidate(
                    hit=hit,
                    reason=VectorRepairPurgeReason.cross_user_vector_metadata,
                    required_projection_commit_id=required_projection_commit_id,
                    required_account_generation=required_account_generation,
                    authoritative_item=item,
                )
            )
            continue
        if hit.account_generation != item.account_generation:
            decisions[hit.memory_id] = SearchDecision.stale_vector
            repair_purge_candidates.append(
                _repair_purge_candidate(
                    hit=hit,
                    reason=VectorRepairPurgeReason.stale_account_generation,
                    required_projection_commit_id=required_projection_commit_id,
                    required_account_generation=required_account_generation,
                    authoritative_item=item,
                )
            )
            continue
        if hit.item_revision != item.item_revision:
            decisions[hit.memory_id] = SearchDecision.stale_vector
            repair_purge_candidates.append(
                _repair_purge_candidate(
                    hit=hit,
                    reason=VectorRepairPurgeReason.stale_item_revision,
                    required_projection_commit_id=required_projection_commit_id,
                    required_account_generation=required_account_generation,
                    authoritative_item=item,
                )
            )
            continue
        if hit.source_commit_id != item.source_commit_id:
            decisions[hit.memory_id] = SearchDecision.stale_vector
            repair_purge_candidates.append(
                _repair_purge_candidate(
                    hit=hit,
                    reason=VectorRepairPurgeReason.stale_source_commit,
                    required_projection_commit_id=required_projection_commit_id,
                    required_account_generation=required_account_generation,
                    authoritative_item=item,
                )
            )
            continue
        if hit.content_hash != item.content_hash:
            decisions[hit.memory_id] = SearchDecision.stale_vector
            repair_purge_candidates.append(
                _repair_purge_candidate(
                    hit=hit,
                    reason=VectorRepairPurgeReason.stale_content_hash,
                    required_projection_commit_id=required_projection_commit_id,
                    required_account_generation=required_account_generation,
                    authoritative_item=item,
                )
            )
            continue
        if hit.vector_updated_at < item.updated_at:
            decisions[hit.memory_id] = SearchDecision.stale_vector
            repair_purge_candidates.append(
                _repair_purge_candidate(
                    hit=hit,
                    reason=VectorRepairPurgeReason.stale_vector_updated_at,
                    required_projection_commit_id=required_projection_commit_id,
                    required_account_generation=required_account_generation,
                    authoritative_item=item,
                )
            )
            continue
        access = (
            is_archive_access_eligible(item, policy, now=now)
            if mode == SearchMode.archive_explicit
            else is_default_access_eligible(item, policy, now=now)
        )
        if not access.allowed:
            decisions[hit.memory_id] = SearchDecision.access_denied
            continue
        decisions[hit.memory_id] = SearchDecision.allowed
        results.append(HydratedSearchResult(item=item, score=hit.score, projection_commit_id=hit.projection_commit_id))
    return SearchGatewayResult(
        results=results,
        decisions=decisions,
        repair_purge_candidates=repair_purge_candidates,
    )


def _repair_purge_candidate(
    *,
    hit: SearchVectorHit,
    reason: VectorRepairPurgeReason,
    required_projection_commit_id: str,
    required_account_generation: int,
    authoritative_item: Optional[MemoryItem],
) -> Dict[str, Any]:
    decision = (
        SearchDecision.missing_authoritative_item
        if reason == VectorRepairPurgeReason.missing_authoritative_item
        else SearchDecision.stale_vector
    )
    if reason == VectorRepairPurgeReason.stale_projection_commit:
        decision = SearchDecision.stale_projection
    return {
        "vector_id": hit.vector_id or hit.memory_id,
        "memory_id": hit.memory_id,
        "reason": reason.value,
        "decision": decision.value,
        "required_projection_commit_id": required_projection_commit_id,
        "observed_projection_commit_id": hit.projection_commit_id,
        "required_account_generation": required_account_generation,
        "observed_account_generation": hit.account_generation,
        "authoritative_account_generation": authoritative_item.account_generation if authoritative_item else None,
        "observed_item_revision": hit.item_revision,
        "authoritative_item_revision": authoritative_item.item_revision if authoritative_item else None,
        "observed_source_commit_id": hit.source_commit_id,
        "authoritative_source_commit_id": authoritative_item.source_commit_id if authoritative_item else None,
        "observed_content_hash": hit.content_hash,
        "authoritative_content_hash": authoritative_item.content_hash if authoritative_item else None,
    }


__all__ = [
    "HydratedSearchResult",
    "SearchDecision",
    "SearchGatewayResult",
    "SearchMode",
    "SearchVectorHit",
    "VectorRepairPurgeReason",
    "hydrate_and_filter_vector_hits",
]
