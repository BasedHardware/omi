"""Backward-compatible shim — canonical definitions live in ``models.memory_search_gateway`` (WS-G G6)."""

from models.memory_search_gateway import (
    HydratedSearchResult,
    SearchDecision,
    SearchGatewayResult,
    SearchMode,
    SearchVectorHit,
    VectorRepairPurgeReason,
    hydrate_and_filter_vector_hits,
)

__all__ = [
    "HydratedSearchResult",
    "SearchDecision",
    "SearchGatewayResult",
    "SearchMode",
    "SearchVectorHit",
    "VectorRepairPurgeReason",
    "hydrate_and_filter_vector_hits",
]
