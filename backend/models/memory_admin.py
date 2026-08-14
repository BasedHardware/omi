"""Memory admin response models.

Wire shapes for ``/memory/admin/*`` routes. Source of truth for the memory
admin response schema; routers/utils construct dicts matching these fields.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class ReadRolloutCapabilities(BaseModel):
    """Raw memory default-read rollout capability flags for one consumer."""

    legacy_only: bool = Field(description='Whether the consumer is legacy-only (no default memory).')
    shadow_artifacts_enabled: bool = Field(description='Whether shadow artifacts are enabled.')
    memory_writes_enabled: bool = Field(description='Whether memory writes are enabled.')
    memory_reads_enabled: bool = Field(description='Whether memory reads are enabled.')
    legacy_reads_authoritative: bool = Field(description='Whether legacy reads remain authoritative.')


class ReadRolloutConsumerObservability(BaseModel):
    """Per-consumer default-read rollout decision observability.

    Produced by ``build_default_read_rollout_observability``. Shared between the
    admin rollout report (``consumers`` map values) and the product-route
    ``rollout`` field (extended by ``ProductRolloutObservability``).
    """

    consumer: str = Field(description='Memory consumer (mcp, developer_api, omi_chat).')
    enabled: bool = Field(description='Whether default memory reads are enabled for this consumer.')
    reason: str = Field(description='Effective reason (fallback_reason when present, else the decision reason).')
    read_decision: str = Field(description='Server read decision value (USE_MEMORY or DENY_MEMORY).')
    mode: str = Field(description='Rollout capabilities mode value.')
    memory_reads_enabled: bool = Field(description='Whether memory reads are enabled by capabilities.')
    legacy_reads_authoritative: bool = Field(description='Whether legacy reads remain authoritative.')
    default_memory_grant: bool = Field(description='Whether the app holds the default-memory grant.')
    archive_default_visible: bool = Field(description='Always false; Archive is never default-visible.')
    archive_capability: bool = Field(description='Persisted Archive capability flag for the consumer.')
    fallback_reason: Optional[str] = Field(default=None, description='Fallback reason when reads are not enabled.')
    capabilities: ReadRolloutCapabilities = Field(description='Raw rollout capability flags.')


class ShortTermLifecycleRunResponse(BaseModel):
    """Counts and outcome of a Short-term lifecycle worker run for one user.

    Returned by ``POST /memory/admin/users/{uid}/short-term-lifecycle/run``.
    """

    uid: str = Field(description='User id the lifecycle worker ran for.')
    run_id: str = Field(description='Idempotency/run id supplied by the caller.')
    evaluated_at: str = Field(description='ISO-8601 timestamp the run was evaluated at (UTC).')
    evaluated_count: int = Field(description='Total items evaluated (created + existing + skipped).')
    created_count: int = Field(description='Newly persisted lifecycle transition records.')
    existing_count: int = Field(description='Already-persisted transition records observed.')
    skipped_count: int = Field(description='Items skipped (no transition required).')
    transition_count: int = Field(description='Items that produced a transition (created + existing).')
    skipped_memory_ids: List[str] = Field(description='Memory ids that were skipped.')
    default_access_allowed: bool = Field(
        description='Whether default access was allowed (always false for this admin report).'
    )
    archive_default_visible: bool = Field(description='Always false; Archive is never default-visible.')
