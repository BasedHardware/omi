"""Memory admin response models.

Wire shapes for ``/memory/admin/*`` routes. Source of truth for the memory
admin response schema; routers/utils construct dicts matching these fields.
"""

from typing import Dict, List, Optional

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
    read_decision: str = Field(
        description='Server read decision value (USE_MEMORY / SHADOW_ONLY / USE_LEGACY_SAFE / DENY_MEMORY).'
    )
    mode: str = Field(description='Rollout capabilities mode value.')
    memory_reads_enabled: bool = Field(description='Whether memory reads are enabled by capabilities.')
    legacy_reads_authoritative: bool = Field(description='Whether legacy reads remain authoritative.')
    default_memory_grant: bool = Field(description='Whether the app holds the default-memory grant.')
    archive_default_visible: bool = Field(description='Always false; Archive is never default-visible.')
    archive_capability: bool = Field(description='Persisted Archive capability flag for the consumer.')
    fallback_reason: Optional[str] = Field(default=None, description='Fallback reason when reads are not enabled.')
    capabilities: ReadRolloutCapabilities = Field(description='Raw rollout capability flags.')


class ReadRolloutAuditEvent(BaseModel):
    """One per-consumer default-read rollout decision audit event."""

    uid: str = Field(description='User id the decision was evaluated for.')
    source_path: str = Field(description='Firestore source path of the rollout state doc.')
    consumer: str = Field(description='Memory consumer.')
    enabled: bool = Field(description='Whether default memory reads are enabled.')
    outcome: str = Field(description='Outcome label: "enabled" or "fallback".')
    read_decision: str = Field(description='Server read decision value.')
    fallback_reason: Optional[str] = Field(default=None, description='Fallback reason, if any.')
    default_memory_grant: bool = Field(description='Whether the app holds the default-memory grant.')
    memory_reads_enabled: bool = Field(description='Whether memory reads are enabled by capabilities.')
    archive_default_visible: bool = Field(description='Always false.')
    archive_capability: bool = Field(description='Persisted Archive capability flag for the consumer.')


class ReadRolloutTotalCounters(BaseModel):
    """Aggregate enabled/fallback decision counts across all consumers."""

    enabled: int = Field(description='Number of consumers with default reads enabled.')
    fallback: int = Field(description='Number of consumers in fallback.')


class ReadRolloutConsumerCounters(BaseModel):
    """Enabled/fallback decision counts for one consumer."""

    enabled: int = Field(description='Count of enabled decisions for this consumer.')
    fallback: int = Field(description='Count of fallback decisions for this consumer.')
    fallback_reasons: Dict[str, int] = Field(description='Fallback reason -> count map for this consumer.')


class ReadRolloutDecisionCounters(BaseModel):
    """Aggregated rollout decision counters."""

    total: ReadRolloutTotalCounters = Field(description='Aggregate counts across all consumers.')
    by_consumer: Dict[str, ReadRolloutConsumerCounters] = Field(
        description='Per-consumer counts keyed by consumer name.'
    )


class MemoryReadRolloutObservabilityReport(BaseModel):
    """Admin observability report for one user's default-read rollout decisions.

    Returned by ``GET /memory/admin/users/{uid}/read-rollout-decision``.
    """

    uid: str = Field(description='User id the rollout decision was inspected for.')
    source_path: str = Field(description='Firestore source path of the rollout state doc.')
    archive_default_visible: bool = Field(description='Always false; Archive is never default-visible.')
    archive_capability: bool = Field(description='Always false at the report level.')
    decision_audit_events: List[ReadRolloutAuditEvent] = Field(description='Per-consumer decision audit events.')
    decision_counters: ReadRolloutDecisionCounters = Field(description='Aggregated enabled/fallback decision counters.')
    decision_metrics_prometheus: str = Field(description='Low-cardinality Prometheus text rendering of the counters.')
    consumers: Dict[str, ReadRolloutConsumerObservability] = Field(
        description='Per-consumer observability keyed by consumer name.'
    )


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
