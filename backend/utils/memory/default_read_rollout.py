"""Canonical default read rollout module (WS-G8a).

Neutral ``default_read_rollout`` is the source of truth. Legacy ``default_read_rollout`` remains an importable alias.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Literal, Optional, cast

from config.memory_rollout import (
    MemoryRolloutCapabilities,
    MemoryRolloutMode,
    MemoryRolloutState,
    decide_memory_rollout_capabilities,
)
from database.memory_collections import MemoryCollections
from utils.memory.memory_read_rollout_core import extract_consumer_grants

SUPPORTED_DEFAULT_READ_CONSUMERS = {'mcp', 'developer_api', 'omi_chat'}
DEFAULT_READ_OBSERVABILITY_CONSUMERS = ('mcp', 'developer_api', 'omi_chat')
DEFAULT_READ_ROLLOUT_SCHEMA_VERSION = 1
DEFAULT_READ_ROLLOUT_TIMEOUT_SECONDS = 2.0
DEFAULT_READ_ROLLOUT_METRIC_NAME = 'default_read_rollout_decisions_total'
GLOBAL_READ_GATE_PATH = 'memory_control/global_read_gate'
WRITE_CONVERGENCE_GATE_PATH = 'memory_control/write_convergence_gate'
_LOW_CARDINALITY_FALLBACK_REASON_BUCKETS = {
    'malformed_rollout_state',
    'missing_chat_default_memory_grant',
    'missing_developer_default_memory_grant',
    'missing_mcp_default_memory_grant',
    'missing_rollout_state',
    'rollout_read_failed',
    'uid_mismatch',
    'unsupported_consumer',
    'unsupported_rollout_schema',
    'memory_reads_disabled',
}


class MemoryReadDecision(str, Enum):
    USE_MEMORY = 'USE_MEMORY'
    USE_LEGACY_SAFE = 'USE_LEGACY_SAFE'
    DENY_MEMORY = 'DENY_MEMORY'
    SHADOW_ONLY = 'SHADOW_ONLY'


@dataclass(frozen=True)
class GlobalReadGateDecision:
    source_path: str
    read_decision: MemoryReadDecision
    reason: str = 'ok'

    @property
    def fallback_reason(self) -> Optional[str]:
        if self.read_decision == MemoryReadDecision.USE_MEMORY:
            return None
        return self.reason


@dataclass(frozen=True)
class WriteConvergencePolicy:
    source_path: str
    ready: bool
    reason: str = 'ok'


@dataclass(frozen=True)
class DefaultReadRolloutDecision:
    uid: str
    source_path: str
    consumer: str
    rollout_capabilities: MemoryRolloutCapabilities
    app_has_default_memory_grant: bool
    archive_capability: bool = False
    vector_projection_commit_id: Optional[str] = None
    vector_repair_outbox_enabled: bool = False
    reason: str = 'ok'
    explicit_read_decision: MemoryReadDecision | None = None

    @property
    def read_decision(self) -> MemoryReadDecision:
        if self.explicit_read_decision is not None:
            return self.explicit_read_decision
        if self.memory_default_enabled:
            return MemoryReadDecision.USE_MEMORY
        if (
            self.rollout_capabilities.shadow_artifacts_enabled
            and not self.rollout_capabilities.memory_reads_enabled
            and self.app_has_default_memory_grant
        ):
            return MemoryReadDecision.SHADOW_ONLY
        return MemoryReadDecision.DENY_MEMORY

    @property
    def memory_default_enabled(self) -> bool:
        return self.rollout_capabilities.memory_reads_enabled and self.app_has_default_memory_grant

    @property
    def memory_default_mcp_enabled(self) -> bool:
        return self.consumer == 'mcp' and self.memory_default_enabled

    @property
    def memory_default_developer_enabled(self) -> bool:
        return self.consumer == 'developer_api' and self.memory_default_enabled

    @property
    def memory_default_chat_enabled(self) -> bool:
        return self.consumer == 'omi_chat' and self.memory_default_enabled

    @property
    def grant_reason_key(self) -> str:
        if self.consumer == 'developer_api':
            return 'developer'
        if self.consumer == 'omi_chat':
            return 'chat'
        return self.consumer

    @property
    def fallback_reason(self) -> Optional[str]:
        if self.read_decision == MemoryReadDecision.DENY_MEMORY and self.reason != 'ok':
            return self.reason
        if self.memory_default_enabled:
            return None
        if self.read_decision == MemoryReadDecision.SHADOW_ONLY:
            return 'shadow_only'
        if self.read_decision == MemoryReadDecision.USE_LEGACY_SAFE:
            return self.reason
        if self.reason != 'ok':
            return self.reason
        if not self.rollout_capabilities.memory_reads_enabled:
            return 'memory_reads_disabled'
        if not self.app_has_default_memory_grant:
            return f'missing_{self.grant_reason_key}_default_memory_grant'
        return f'memory_default_{self.grant_reason_key}_disabled'


RolloutStateReadError = Literal['malformed_rollout_state', 'rollout_read_failed']
RolloutStateDocRead = tuple[str, object | None, RolloutStateReadError | None]
Payload = dict[str, Any]
GuardDetail = dict[str, Any]
ObservabilityPayload = dict[str, Any]
AuditEvent = dict[str, Any]
ConsumerCounters = dict[str, Any]
DecisionCounters = dict[str, Any]
AuditEventsPayload = dict[str, Any]
ObservabilityReport = dict[str, Any]


def _payload_or_none(value: object) -> Payload | None:
    return cast(Payload, value) if isinstance(value, dict) else None


def _stage_gates_payload(value: object) -> dict[Any, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError('malformed_stage_gates')
    return cast(dict[Any, Any], value)


def normalize_global_read_gate(data: Any) -> GlobalReadGateDecision:
    """Normalize global memory read kill-switch state.

    This gate is deliberately independent from per-user
    `users/{uid}/memory_control/state`. Missing or malformed config denies memory
    reads so product routes can fail before per-user Firestore/vector/item reads.
    """

    payload = _payload_or_none(data)
    if payload is None:
        return GlobalReadGateDecision(
            source_path=GLOBAL_READ_GATE_PATH,
            read_decision=MemoryReadDecision.DENY_MEMORY,
            reason='missing_global_read_gate',
        )
    memory_reads_enabled = payload.get('memory_reads_enabled')
    kill_switch_active = payload.get('kill_switch_active')
    if not isinstance(memory_reads_enabled, bool) or not isinstance(kill_switch_active, bool):
        return GlobalReadGateDecision(
            source_path=GLOBAL_READ_GATE_PATH,
            read_decision=MemoryReadDecision.DENY_MEMORY,
            reason='malformed_global_read_gate',
        )
    if kill_switch_active:
        return GlobalReadGateDecision(
            source_path=GLOBAL_READ_GATE_PATH,
            read_decision=MemoryReadDecision.DENY_MEMORY,
            reason='global_memory_read_kill_switch_active',
        )
    if not memory_reads_enabled:
        return GlobalReadGateDecision(
            source_path=GLOBAL_READ_GATE_PATH,
            read_decision=MemoryReadDecision.DENY_MEMORY,
            reason='global_memory_reads_disabled',
        )
    return GlobalReadGateDecision(source_path=GLOBAL_READ_GATE_PATH, read_decision=MemoryReadDecision.USE_MEMORY)


def read_global_read_gate(*, db_client: Any) -> GlobalReadGateDecision:
    """Read the global emergency memory product-read gate before per-user rollout state."""

    try:
        snapshot = _get_firestore_document_snapshot(db_client.document(GLOBAL_READ_GATE_PATH))
        data = snapshot.to_dict() if getattr(snapshot, 'exists', True) else None
    except (TypeError, ValueError, AttributeError):
        return GlobalReadGateDecision(
            source_path=GLOBAL_READ_GATE_PATH,
            read_decision=MemoryReadDecision.DENY_MEMORY,
            reason='malformed_global_read_gate',
        )
    except Exception:
        return GlobalReadGateDecision(
            source_path=GLOBAL_READ_GATE_PATH,
            read_decision=MemoryReadDecision.DENY_MEMORY,
            reason='global_read_gate_read_failed',
        )
    return normalize_global_read_gate(data)


def normalize_write_convergence_gate(data: Any) -> WriteConvergencePolicy:
    """Normalize server-owned write convergence/outbox readiness.

    External legacy-memory writes may only bypass the memory read split-brain guard
    when all durable convergence bits are explicitly boolean true. Missing,
    malformed, or partially ready config fails safe and keeps legacy writes
    blocked for memory/shadow read consumers.
    """

    payload = _payload_or_none(data)
    if payload is None:
        return WriteConvergencePolicy(
            source_path=WRITE_CONVERGENCE_GATE_PATH,
            ready=False,
            reason='missing_write_convergence_gate',
        )
    required_true_fields = (
        'durable_outbox_enabled',
        'dual_write_projection_ready',
        'delete_convergence_ready',
        'idempotency_contract_ready',
    )
    for field in required_true_fields:
        if not isinstance(payload.get(field), bool):
            return WriteConvergencePolicy(
                source_path=WRITE_CONVERGENCE_GATE_PATH,
                ready=False,
                reason='malformed_write_convergence_gate',
            )
    if not all(payload[field] is True for field in required_true_fields):
        return WriteConvergencePolicy(
            source_path=WRITE_CONVERGENCE_GATE_PATH,
            ready=False,
            reason='write_convergence_not_ready',
        )
    return WriteConvergencePolicy(source_path=WRITE_CONVERGENCE_GATE_PATH, ready=True)


def read_write_convergence_gate(*, db_client: Any) -> WriteConvergencePolicy:
    """Read server-owned durable write convergence/outbox readiness."""

    try:
        snapshot = _get_firestore_document_snapshot(db_client.document(WRITE_CONVERGENCE_GATE_PATH))
        data = snapshot.to_dict() if getattr(snapshot, 'exists', True) else None
    except (TypeError, ValueError, AttributeError):
        return WriteConvergencePolicy(
            source_path=WRITE_CONVERGENCE_GATE_PATH,
            ready=False,
            reason='malformed_write_convergence_gate',
        )
    except Exception:
        return WriteConvergencePolicy(
            source_path=WRITE_CONVERGENCE_GATE_PATH,
            ready=False,
            reason='write_convergence_gate_read_failed',
        )
    return normalize_write_convergence_gate(data)


def disabled_default_read_rollout_decision(
    *, uid: str, source_path: str, consumer: str, reason: str
) -> DefaultReadRolloutDecision:
    return DefaultReadRolloutDecision(
        uid=uid,
        source_path=source_path,
        consumer=consumer,
        rollout_capabilities=MemoryRolloutCapabilities(
            uid=uid,
            mode=MemoryRolloutMode.off,
            legacy_only=True,
            shadow_artifacts_enabled=False,
            memory_writes_enabled=False,
            memory_reads_enabled=False,
            legacy_reads_authoritative=True,
        ),
        app_has_default_memory_grant=False,
        archive_capability=False,
        reason=reason,
        explicit_read_decision=MemoryReadDecision.DENY_MEMORY,
    )


def legacy_safe_default_read_rollout_decision(
    *, uid: str, source_path: str, consumer: str, reason: str
) -> DefaultReadRolloutDecision:
    """Mark an explicit legacy-only endpoint/caller as safe by policy.

    This is intentionally opt-in: malformed/missing/no-grant memory control state
    must not be interpreted as a safe legacy downgrade for default memory reads.
    """

    return DefaultReadRolloutDecision(
        uid=uid,
        source_path=source_path,
        consumer=consumer,
        rollout_capabilities=MemoryRolloutCapabilities(
            uid=uid,
            mode=MemoryRolloutMode.off,
            legacy_only=True,
            shadow_artifacts_enabled=False,
            memory_writes_enabled=False,
            memory_reads_enabled=False,
            legacy_reads_authoritative=True,
        ),
        app_has_default_memory_grant=False,
        archive_capability=False,
        reason=reason,
        explicit_read_decision=MemoryReadDecision.USE_LEGACY_SAFE,
    )


@dataclass(frozen=True)
class LegacyMemoryWriteGuardDecision:
    allowed: bool
    detail: GuardDetail
    status_code: int = 200


def assert_legacy_memory_write_allowed_for_default_read_decision(
    decision: DefaultReadRolloutDecision,
    *,
    operation: str,
    write_convergence_policy: WriteConvergencePolicy | None = None,
) -> LegacyMemoryWriteGuardDecision:
    """Guard legacy external memory writes while default memory reads are enabled.

    Developer/MCP create/edit/delete currently mutate legacy `memories` state while
    memory reads hydrate from `memory_items`. Until a server-owned convergence/dual-write
    policy is explicitly passed, block those legacy mutations for consumers whose
    persisted rollout says memory reads are authoritative or shadowed. Missing or
    malformed control state also fails safe; explicitly disabled legacy-safe reads
    preserve existing legacy write behavior.
    """

    fail_safe_reasons = {'missing_rollout_state', 'malformed_rollout_state', 'uid_mismatch'}
    should_block = decision.read_decision in {MemoryReadDecision.USE_MEMORY, MemoryReadDecision.SHADOW_ONLY}
    should_block = should_block or decision.fallback_reason in fail_safe_reasons
    if not should_block:
        return LegacyMemoryWriteGuardDecision(
            allowed=True,
            detail={
                'enabled': True,
                'reason': 'legacy_memory_write_allowed',
                'consumer': decision.consumer,
                'operation': operation,
                'read_decision': decision.read_decision.value,
                'source_path': decision.source_path,
            },
        )
    if write_convergence_policy is not None and write_convergence_policy.ready:
        return LegacyMemoryWriteGuardDecision(
            allowed=True,
            detail={
                'enabled': True,
                'reason': 'legacy_memory_write_allowed_with_memory_convergence',
                'consumer': decision.consumer,
                'operation': operation,
                'read_decision': decision.read_decision.value,
                'source_path': decision.source_path,
                'convergence_source_path': write_convergence_policy.source_path,
            },
        )
    convergence_reason = None
    if write_convergence_policy is not None:
        convergence_reason = write_convergence_policy.reason
    return LegacyMemoryWriteGuardDecision(
        allowed=False,
        status_code=409,
        detail={
            'enabled': False,
            'reason': 'memory_default_read_legacy_write_blocked',
            'consumer': decision.consumer,
            'operation': operation,
            'read_decision': decision.read_decision.value,
            'source_path': decision.source_path,
            'convergence_reason': convergence_reason,
        },
    )


def guard_legacy_memory_write(
    uid: str,
    db_client: Any,
    *,
    consumer: str,
    operation: str,
) -> LegacyMemoryWriteGuardDecision:
    """Read rollout state and evaluate legacy write guard for external memory mutations."""

    rollout = read_default_read_rollout(uid=uid, db_client=db_client, consumer=consumer)
    return assert_legacy_memory_write_allowed_for_default_read_decision(
        rollout,
        operation=operation,
        write_convergence_policy=read_write_convergence_gate(db_client=db_client),
    )


def _consumer_default_memory_grant_enabled(data: dict[str, Any], consumer: str) -> bool:
    return extract_consumer_grants(data, consumer).default_memory


def _consumer_archive_capability_value(data: dict[str, Any], consumer: str) -> bool | None:
    return extract_consumer_grants(data, consumer).archive_capability


def normalize_default_read_rollout_decision(
    *, uid: str, source_path: str, consumer: str, data: Any
) -> DefaultReadRolloutDecision:
    """Normalize a fetched `users/{uid}/memory_control/state` doc for default memory reads.

    Missing, malformed, uid-mismatched, disabled, or consumer-grant-less docs fail
    closed. Archive is intentionally not derived from persisted grants here:
    default read consumers must keep `archive_capability=False` and use separate
    explicit Archive routes/capabilities.
    """

    if consumer not in SUPPORTED_DEFAULT_READ_CONSUMERS:
        return disabled_default_read_rollout_decision(
            uid=uid, source_path=source_path, consumer=consumer, reason='unsupported_consumer'
        )

    try:
        payload = _payload_or_none(data)
        if payload is None:
            return disabled_default_read_rollout_decision(
                uid=uid, source_path=source_path, consumer=consumer, reason='missing_rollout_state'
            )
        if payload.get('uid') != uid:
            return disabled_default_read_rollout_decision(
                uid=uid, source_path=source_path, consumer=consumer, reason='uid_mismatch'
            )
        if payload.get('schema_version') != DEFAULT_READ_ROLLOUT_SCHEMA_VERSION:
            return disabled_default_read_rollout_decision(
                uid=uid, source_path=source_path, consumer=consumer, reason='unsupported_rollout_schema'
            )

        state = MemoryRolloutState(
            uid=uid,
            mode=payload.get('mode', MemoryRolloutMode.off.value),
            mode_epoch=int(payload.get('mode_epoch', 0) or 0),
            cutover_epoch=int(payload.get('cutover_epoch', 0) or 0),
            account_generation=int(payload.get('account_generation', 0) or 0),
            last_reconciled_legacy_revision=payload.get('last_reconciled_legacy_revision'),
            fallback_projection_ready=payload.get('fallback_projection_ready') is True,
            persistent_memory_writes_started=payload.get('persistent_memory_writes_started') is True,
            decommission_reconciled=payload.get('decommission_reconciled') is True,
            writes_blocked=payload.get('writes_blocked') is True,
            stage_gates=_stage_gates_payload(payload.get('stage_gates')),
        )
        vector_projection_commit_id = payload.get('vector_projection_commit_id')
        if not isinstance(vector_projection_commit_id, str) or not vector_projection_commit_id.strip():
            vector_projection_commit_id = None
        vector_repair_outbox_enabled = payload.get('vector_repair_outbox_enabled') is True
        return DefaultReadRolloutDecision(
            uid=uid,
            source_path=source_path,
            consumer=consumer,
            rollout_capabilities=decide_memory_rollout_capabilities(uid, state.mode, state),
            app_has_default_memory_grant=_consumer_default_memory_grant_enabled(payload, consumer),
            archive_capability=False,
            vector_projection_commit_id=vector_projection_commit_id,
            vector_repair_outbox_enabled=vector_repair_outbox_enabled,
            reason='ok',
        )
    except (TypeError, ValueError, AttributeError):
        return disabled_default_read_rollout_decision(
            uid=uid, source_path=source_path, consumer=consumer, reason='malformed_rollout_state'
        )


def normalize_archive_read_rollout_decision(
    *, uid: str, source_path: str, consumer: str, data: Any
) -> DefaultReadRolloutDecision:
    """Normalize persisted control state for explicit Archive product reads.

    Archive access is intentionally stronger than default-memory reads: callers
    need the usual memory default-read authorization plus a distinct server-owned
    Archive capability in `users/{uid}/memory_control/state`. Client query flags
    are not interpreted here and cannot grant Archive access.
    """

    default_decision = normalize_default_read_rollout_decision(
        uid=uid, source_path=source_path, consumer=consumer, data=data
    )
    if default_decision.read_decision != MemoryReadDecision.USE_MEMORY:
        return default_decision

    archive_capability = _consumer_archive_capability_value(data, consumer)
    if archive_capability is None:
        return DefaultReadRolloutDecision(
            uid=uid,
            source_path=source_path,
            consumer=consumer,
            rollout_capabilities=default_decision.rollout_capabilities,
            app_has_default_memory_grant=default_decision.app_has_default_memory_grant,
            archive_capability=False,
            vector_projection_commit_id=default_decision.vector_projection_commit_id,
            vector_repair_outbox_enabled=default_decision.vector_repair_outbox_enabled,
            reason='malformed_archive_capability',
            explicit_read_decision=MemoryReadDecision.DENY_MEMORY,
        )
    if not archive_capability:
        return DefaultReadRolloutDecision(
            uid=uid,
            source_path=source_path,
            consumer=consumer,
            rollout_capabilities=default_decision.rollout_capabilities,
            app_has_default_memory_grant=default_decision.app_has_default_memory_grant,
            archive_capability=False,
            vector_projection_commit_id=default_decision.vector_projection_commit_id,
            vector_repair_outbox_enabled=default_decision.vector_repair_outbox_enabled,
            reason=f'missing_{default_decision.grant_reason_key}_archive_capability',
            explicit_read_decision=MemoryReadDecision.DENY_MEMORY,
        )
    return DefaultReadRolloutDecision(
        uid=uid,
        source_path=source_path,
        consumer=consumer,
        rollout_capabilities=default_decision.rollout_capabilities,
        app_has_default_memory_grant=default_decision.app_has_default_memory_grant,
        archive_capability=True,
        vector_projection_commit_id=default_decision.vector_projection_commit_id,
        vector_repair_outbox_enabled=default_decision.vector_repair_outbox_enabled,
        reason='ok',
        explicit_read_decision=MemoryReadDecision.USE_MEMORY,
    )


def _get_firestore_document_snapshot(document_ref: Any) -> Any:
    try:
        return document_ref.get(timeout=DEFAULT_READ_ROLLOUT_TIMEOUT_SECONDS)
    except TypeError as exc:
        if 'timeout' not in str(exc):
            raise
        return document_ref.get()


def read_default_read_rollout(*, uid: str, db_client: Any, consumer: str) -> DefaultReadRolloutDecision:
    """Read and normalize server-owned persisted default-read rollout state."""

    source_path = MemoryCollections(uid=uid).memory_control_state
    try:
        snapshot = _get_firestore_document_snapshot(db_client.document(source_path))
        data = snapshot.to_dict() if getattr(snapshot, 'exists', True) else None
    except (TypeError, ValueError, AttributeError):
        return disabled_default_read_rollout_decision(
            uid=uid, source_path=source_path, consumer=consumer, reason='malformed_rollout_state'
        )
    except Exception:
        return disabled_default_read_rollout_decision(
            uid=uid, source_path=source_path, consumer=consumer, reason='rollout_read_failed'
        )
    return normalize_default_read_rollout_decision(uid=uid, source_path=source_path, consumer=consumer, data=data)


def read_archive_read_rollout(*, uid: str, db_client: Any, consumer: str) -> DefaultReadRolloutDecision:
    """Read persisted default-read rollout plus server-owned Archive capability."""

    source_path = MemoryCollections(uid=uid).memory_control_state
    try:
        snapshot = _get_firestore_document_snapshot(db_client.document(source_path))
        data = snapshot.to_dict() if getattr(snapshot, 'exists', True) else None
    except (TypeError, ValueError, AttributeError):
        return disabled_default_read_rollout_decision(
            uid=uid, source_path=source_path, consumer=consumer, reason='malformed_rollout_state'
        )
    except Exception:
        return disabled_default_read_rollout_decision(
            uid=uid, source_path=source_path, consumer=consumer, reason='rollout_read_failed'
        )
    return normalize_archive_read_rollout_decision(uid=uid, source_path=source_path, consumer=consumer, data=data)


def read_rollout_state_doc(*, uid: str, db_client: Any) -> RolloutStateDocRead:
    source_path = MemoryCollections(uid=uid).memory_control_state
    try:
        snapshot = _get_firestore_document_snapshot(db_client.document(source_path))
        data = snapshot.to_dict() if getattr(snapshot, 'exists', True) else None
    except (TypeError, ValueError, AttributeError):
        return source_path, None, 'malformed_rollout_state'
    except Exception:
        return source_path, None, 'rollout_read_failed'
    return source_path, data, None


def read_default_read_rollout_decisions(
    *, uid: str, db_client: Any, consumers: Iterable[str] = DEFAULT_READ_OBSERVABILITY_CONSUMERS
) -> dict[str, DefaultReadRolloutDecision]:
    """Read one rollout state doc and derive per-consumer default-read decisions."""

    source_path, data, read_error = read_rollout_state_doc(uid=uid, db_client=db_client)
    decisions: dict[str, DefaultReadRolloutDecision] = {}
    for consumer in consumers:
        if read_error is not None:
            decisions[consumer] = disabled_default_read_rollout_decision(
                uid=uid, source_path=source_path, consumer=consumer, reason=read_error
            )
        else:
            decisions[consumer] = normalize_default_read_rollout_decision(
                uid=uid, source_path=source_path, consumer=consumer, data=data
            )
    return decisions


def build_default_read_rollout_observability(decision: DefaultReadRolloutDecision) -> ObservabilityPayload:
    capabilities = decision.rollout_capabilities
    fallback_reason = decision.fallback_reason
    reason = fallback_reason or decision.reason
    return {
        'consumer': decision.consumer,
        'enabled': decision.memory_default_enabled,
        'reason': reason,
        'read_decision': decision.read_decision.value,
        'mode': capabilities.mode.value,
        'memory_reads_enabled': capabilities.memory_reads_enabled,
        'legacy_reads_authoritative': capabilities.legacy_reads_authoritative,
        'default_memory_grant': decision.app_has_default_memory_grant,
        'archive_default_visible': False,
        'archive_capability': decision.archive_capability,
        'fallback_reason': fallback_reason,
        'capabilities': {
            'legacy_only': capabilities.legacy_only,
            'shadow_artifacts_enabled': capabilities.shadow_artifacts_enabled,
            'memory_writes_enabled': capabilities.memory_writes_enabled,
            'memory_reads_enabled': capabilities.memory_reads_enabled,
            'legacy_reads_authoritative': capabilities.legacy_reads_authoritative,
        },
    }


def build_default_read_rollout_audit_event(decision: DefaultReadRolloutDecision) -> AuditEvent:
    enabled = decision.memory_default_enabled
    return {
        'uid': decision.uid,
        'source_path': decision.source_path,
        'consumer': decision.consumer,
        'enabled': enabled,
        'outcome': 'enabled' if enabled else 'fallback',
        'read_decision': decision.read_decision.value,
        'fallback_reason': decision.fallback_reason,
        'default_memory_grant': decision.app_has_default_memory_grant,
        'memory_reads_enabled': decision.rollout_capabilities.memory_reads_enabled,
        'archive_default_visible': False,
        'archive_capability': decision.archive_capability,
    }


def build_default_read_rollout_decision_counters(events: list[AuditEvent]) -> DecisionCounters:
    counters: DecisionCounters = {
        'total': {'enabled': 0, 'fallback': 0},
        'by_consumer': {},
    }
    total_counters = cast(ConsumerCounters, counters['total'])
    by_consumer = cast(dict[str, ConsumerCounters], counters['by_consumer'])
    for event in events:
        consumer = str(event.get('consumer') or 'unknown')
        consumer_counters = by_consumer.setdefault(consumer, {'enabled': 0, 'fallback': 0, 'fallback_reasons': {}})
        if event.get('enabled') is True:
            total_counters['enabled'] += 1
            consumer_counters['enabled'] += 1
        else:
            total_counters['fallback'] += 1
            consumer_counters['fallback'] += 1
            fallback_reason = str(event.get('fallback_reason') or 'unknown_fallback')
            fallback_reasons = cast(dict[str, int], consumer_counters['fallback_reasons'])
            fallback_reasons[fallback_reason] = fallback_reasons.get(fallback_reason, 0) + 1
    return counters


def build_default_read_rollout_audit_events(decisions: dict[str, DefaultReadRolloutDecision]) -> AuditEventsPayload:
    events = [build_default_read_rollout_audit_event(decision) for decision in decisions.values()]
    return {'events': events, 'counters': build_default_read_rollout_decision_counters(events)}


def _bucket_default_read_consumer(consumer: str) -> str:
    if consumer in SUPPORTED_DEFAULT_READ_CONSUMERS:
        return consumer
    return 'unsupported_consumer'


def _bucket_default_read_fallback_reason(fallback_reason: str | None) -> str:
    if not fallback_reason:
        return 'none'
    if fallback_reason in _LOW_CARDINALITY_FALLBACK_REASON_BUCKETS:
        return fallback_reason
    if fallback_reason.startswith('missing_') and fallback_reason.endswith('_default_memory_grant'):
        return 'missing_default_memory_grant_other'
    if fallback_reason.startswith('memory_default_') and fallback_reason.endswith('_disabled'):
        return 'memory_default_consumer_disabled'
    return 'other'


def _format_prometheus_sample(metric_name: str, labels: dict[str, str], value: int) -> str:
    formatted_labels = ','.join(f'{label}="{str(label_value)}"' for label, label_value in labels.items())
    return f'{metric_name}{{{formatted_labels}}} {int(value)}'


def render_default_read_rollout_metrics(counters: DecisionCounters) -> str:
    """Render local rollout decision counters as low-cardinality Prometheus text.

    The caller passes already-aggregated counters from local rollout audit events.
    Labels are intentionally limited to consumer, outcome, and fallback reason
    bucket. Do not add uid, source_path, app/source identifiers, or raw dynamic
    fallback strings here; those belong in admin/debug JSON, not ops metrics.
    """

    lines = [
        f'# HELP {DEFAULT_READ_ROLLOUT_METRIC_NAME} Local memory default-read rollout decisions by consumer and outcome.',
        f'# TYPE {DEFAULT_READ_ROLLOUT_METRIC_NAME} counter',
    ]
    by_consumer = cast(dict[str, ConsumerCounters], counters.get('by_consumer') or {})
    for consumer, consumer_counters in sorted(by_consumer.items()):
        consumer_bucket = _bucket_default_read_consumer(str(consumer))
        enabled_count = int(consumer_counters.get('enabled', 0) or 0)
        if enabled_count:
            lines.append(
                _format_prometheus_sample(
                    DEFAULT_READ_ROLLOUT_METRIC_NAME,
                    {'consumer': consumer_bucket, 'outcome': 'enabled', 'fallback_reason': 'none'},
                    enabled_count,
                )
            )

        fallback_reasons = cast(dict[str, int], consumer_counters.get('fallback_reasons') or {})
        if fallback_reasons:
            fallback_buckets: dict[str, int] = {}
            for fallback_reason, count in fallback_reasons.items():
                fallback_bucket = _bucket_default_read_fallback_reason(str(fallback_reason))
                fallback_buckets[fallback_bucket] = fallback_buckets.get(fallback_bucket, 0) + int(count or 0)
            for fallback_bucket, count in sorted(fallback_buckets.items()):
                if not count:
                    continue
                lines.append(
                    _format_prometheus_sample(
                        DEFAULT_READ_ROLLOUT_METRIC_NAME,
                        {'consumer': consumer_bucket, 'outcome': 'fallback', 'fallback_reason': fallback_bucket},
                        count,
                    )
                )
        else:
            fallback_count = int(consumer_counters.get('fallback', 0) or 0)
            if fallback_count:
                lines.append(
                    _format_prometheus_sample(
                        DEFAULT_READ_ROLLOUT_METRIC_NAME,
                        {'consumer': consumer_bucket, 'outcome': 'fallback', 'fallback_reason': 'unknown_fallback'},
                        fallback_count,
                    )
                )
    return '\n'.join(lines) + '\n'


def build_default_read_rollout_observability_report(
    decisions: dict[str, DefaultReadRolloutDecision],
) -> ObservabilityReport:
    source_path = next(iter(decisions.values())).source_path if decisions else ''
    uid = next(iter(decisions.values())).uid if decisions else ''
    audit = build_default_read_rollout_audit_events(decisions)
    return {
        'uid': uid,
        'source_path': source_path,
        'archive_default_visible': False,
        'archive_capability': False,
        'decision_audit_events': audit['events'],
        'decision_counters': audit['counters'],
        'decision_metrics_prometheus': render_default_read_rollout_metrics(cast(DecisionCounters, audit['counters'])),
        'consumers': {
            consumer: build_default_read_rollout_observability(decision) for consumer, decision in decisions.items()
        },
    }


# Neutral symbol alias (memory name remains valid via shim)
ReadDecision = MemoryReadDecision
