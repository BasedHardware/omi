from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from models.v17_product_memory import (
    MemoryAccessPolicy,
    V17MemoryItem,
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


class SearchVectorHit(BaseModel):
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
    item: V17MemoryItem
    score: float
    projection_commit_id: str


class SearchGatewayResult(BaseModel):
    results: List[HydratedSearchResult] = Field(default_factory=list)
    decisions: Dict[str, SearchDecision] = Field(default_factory=dict)


def hydrate_and_filter_vector_hits(
    *,
    hits: List[SearchVectorHit],
    authoritative_items: Dict[str, V17MemoryItem],
    policy: MemoryAccessPolicy,
    mode: SearchMode,
    required_projection_commit_id: Optional[str],
) -> SearchGatewayResult:
    """Fail-closed vector gateway.

    Vector hits are never returned directly. Every hit must hydrate against the
    authoritative memory item and pass projection freshness + access checks.
    """
    results: List[HydratedSearchResult] = []
    decisions: Dict[str, SearchDecision] = {}
    for hit in sorted(hits, key=lambda item: item.score, reverse=True):
        item = authoritative_items.get(hit.memory_id)
        if item is None:
            decisions[hit.memory_id] = SearchDecision.missing_authoritative_item
            continue
        if required_projection_commit_id and hit.projection_commit_id != required_projection_commit_id:
            decisions[hit.memory_id] = SearchDecision.stale_projection
            continue
        if hit.uid is not None and hit.uid != item.uid:
            decisions[hit.memory_id] = SearchDecision.stale_vector
            continue
        if hit.account_generation is not None and hit.account_generation != item.account_generation:
            decisions[hit.memory_id] = SearchDecision.stale_vector
            continue
        if hit.item_revision is not None and hit.item_revision != item.item_revision:
            decisions[hit.memory_id] = SearchDecision.stale_vector
            continue
        if hit.source_commit_id is not None and hit.source_commit_id != item.source_commit_id:
            decisions[hit.memory_id] = SearchDecision.stale_vector
            continue
        if hit.content_hash is not None and hit.content_hash != item.content_hash:
            decisions[hit.memory_id] = SearchDecision.stale_vector
            continue
        if hit.vector_updated_at < item.updated_at:
            decisions[hit.memory_id] = SearchDecision.stale_vector
            continue
        access = (
            is_archive_access_eligible(item, policy)
            if mode == SearchMode.archive_explicit
            else is_default_access_eligible(item, policy)
        )
        if not access.allowed:
            decisions[hit.memory_id] = SearchDecision.access_denied
            continue
        decisions[hit.memory_id] = SearchDecision.allowed
        results.append(HydratedSearchResult(item=item, score=hit.score, projection_commit_id=hit.projection_commit_id))
    return SearchGatewayResult(results=results, decisions=decisions)
