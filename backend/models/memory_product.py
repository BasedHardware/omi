"""Memory product response models.

Wire shapes for ``/memory/*`` product search routes. Source of truth for the
product memory search response schema; routers/utils construct dicts matching
these fields.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from models.memory_admin import ReadRolloutConsumerObservability
from models.product_memory import MemoryItem


class MemorySearchPolicyPayload(BaseModel):
    """Access-policy snapshot attached to product memory search responses."""

    consumer: str = Field(description='Memory consumer value (e.g. omi_chat).')
    app_has_default_memory_grant: bool = Field(description='Whether the caller holds the default-memory grant.')
    archive_capability: bool = Field(description='Whether the policy grants Archive access.')
    raw_provenance_capability: bool = Field(description='Whether raw provenance access is granted.')


class MemoryGlobalReadGateObservability(BaseModel):
    """Global memory read kill-switch observability attached to search responses."""

    source_path: str = Field(description='Firestore source path of the global read gate.')
    read_decision: str = Field(description='Server read decision value (USE_MEMORY / SHADOW_ONLY / etc.).')
    fallback_reason: Optional[str] = Field(default=None, description='Fallback reason when reads are disabled.')
    reason: str = Field(description='Effective reason (fallback_reason when present, else the gate reason).')


class ProductRolloutObservability(ReadRolloutConsumerObservability):
    """Per-route default-read rollout observability for product memory routes.

    Extends the base per-consumer observability with the product-route context
    fields added by the shared authorization seam.
    """

    surface: str = Field(description='Product surface that requested the read (e.g. product_default_search).')
    archive_capability_required: bool = Field(description='Whether the route requires Archive capability.')
    archive_capability_granted: bool = Field(description='Whether Archive capability was granted for this request.')
    explicit_archive_request: bool = Field(description='Whether the caller explicitly requested Archive access.')
    app_context: Dict[str, Any] = Field(description='Caller app/key/scope context payload.')
    vector_repair_outbox_enabled: Optional[bool] = Field(
        default=None, description='Present only on the vector search route.'
    )


class ProductMemorySearchResponse(BaseModel):
    """Default-visible product memory search response.

    Returned by ``GET /memory/search``.
    """

    uid: str = Field(description='Authenticated user id.')
    query: str = Field(description='Search query string.')
    items: List[MemoryItem] = Field(description='Default-visible memory items for the current page.')
    total_count: int = Field(description='Total default-visible items matching the query.')
    returned_count: int = Field(description='Number of items returned in this page.')
    limit: int = Field(description='Bounded page size used for this response.')
    offset: int = Field(description='Offset into the result set for this page.')
    archive_default_visible: bool = Field(description='Always false; Archive is never default-visible.')
    policy: MemorySearchPolicyPayload = Field(description='Access-policy snapshot used for this read.')
    global_read_gate: MemoryGlobalReadGateObservability = Field(description='Global read kill-switch observability.')
    rollout: ProductRolloutObservability = Field(description='Per-route default-read rollout observability.')


class ArchiveProductMemorySearchResponse(ProductMemorySearchResponse):
    """Explicit Archive product memory search response.

    Returned by ``GET /memory/archive/search``. Adds the Archive capability
    accounting fields on top of the default search response.
    """

    archive_capability_required: bool = Field(description='Always true for the archive search route.')
    archive_capability_granted: bool = Field(description='Whether Archive capability was granted to the policy.')


class VectorMemorySearchResponse(BaseModel):
    """Default-visible vector memory search response.

    Returned by ``GET /memory/vector/search``. Vector hits are hydrated through
    authoritative ``memory_items`` before returning; the budget/exhaustion and
    repair-purge fields describe that hydration process.
    """

    uid: str = Field(description='Authenticated user id.')
    query: str = Field(description='Search query string.')
    items: List[MemoryItem] = Field(description='Hydrated, default-visible memory items for the current page.')
    scores_by_memory_id: Dict[str, float] = Field(description='Vector similarity score keyed by memory id.')
    projection_commit_ids_by_memory_id: Dict[str, str] = Field(description='Projection commit id keyed by memory id.')
    decisions: Dict[str, str] = Field(description='Per-candidate gateway decision value keyed by memory id.')
    total_count: int = Field(description='Total hydrated results before pagination.')
    returned_count: int = Field(description='Number of items returned in this page.')
    limit: int = Field(description='Bounded page size used for this response.')
    overfetch_factor: int = Field(description='Overfetch multiplier applied to the limit.')
    candidate_budget: int = Field(description='Hard cap on vector candidates considered.')
    max_vector_queries: int = Field(description='Maximum number of vector queries allowed.')
    max_candidate_hydration_reads: int = Field(description='Maximum authoritative hydration reads allowed.')
    timeout_seconds: Optional[float] = Field(default=None, description='Optional deadline in seconds, if set.')
    candidate_request_limit: int = Field(description='Effective per-query candidate request limit.')
    candidate_budget_exhausted: bool = Field(description='Whether the candidate budget was exhausted.')
    vector_query_budget_exhausted: bool = Field(description='Whether the vector query budget was exhausted.')
    hydration_read_budget_exhausted: bool = Field(description='Whether the hydration read budget was exhausted.')
    timeout_exhausted: bool = Field(description='Whether the deadline was reached.')
    search_status: str = Field(description='Coarse search status label (e.g. ok, partial).')
    legacy_fallback_used: bool = Field(description='Always false; legacy fallback is never used by this route.')
    vector_query_count: int = Field(description='Number of vector queries actually issued.')
    queried_candidate_count: int = Field(description='Number of vector candidates queried.')
    hydrated_candidate_count: int = Field(description='Number of candidates hydrated from authoritative items.')
    candidate_hydration_read_count: int = Field(description='Number of authoritative hydration reads performed.')
    hydration_rejected_missing_count: int = Field(description='Candidates rejected as missing authoritative items.')
    hydration_rejected_stale_projection_count: int = Field(description='Candidates rejected for stale projection.')
    hydration_rejected_stale_vector_count: int = Field(description='Candidates rejected for stale vector data.')
    hydration_rejected_access_denied_count: int = Field(description='Candidates rejected by access policy.')
    vector_rejected_count: int = Field(description='Candidates rejected before hydration by the vector layer.')
    repair_purge_candidate_count: int = Field(description='Number of repair-purge candidates identified.')
    repair_purge_candidates: List[Dict[str, Any]] = Field(description='Repair-purge candidate payloads.')
    repair_purge_outbox_record_count: int = Field(description='Number of repair-purge outbox records written.')
    repair_purge_outbox_records: List[Dict[str, Any]] = Field(description='Repair-purge outbox record payloads.')
    archive_default_visible: bool = Field(description='Always false; Archive is never default-visible.')
    telemetry: Dict[str, Any] = Field(description='Vector search telemetry emission summary.')
    policy: MemorySearchPolicyPayload = Field(description='Access-policy snapshot used for this read.')
    global_read_gate: MemoryGlobalReadGateObservability = Field(description='Global read kill-switch observability.')
    rollout: ProductRolloutObservability = Field(description='Per-route default-read rollout observability.')
