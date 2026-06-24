"""Canonical alias module for ``models.v17_memory_search_gateway`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from models.v17_memory_search_gateway import (
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
