from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional

from config.v17_memory import V17Capabilities, V17Mode, V17RolloutState, decide_v17_capabilities
from database.v17_collections import V17Collections

SUPPORTED_DEFAULT_READ_CONSUMERS = {'mcp', 'developer_api', 'omi_chat'}
DEFAULT_READ_OBSERVABILITY_CONSUMERS = ('mcp', 'developer_api', 'omi_chat')
V17_DEFAULT_READ_ROLLOUT_METRIC_NAME = 'v17_default_read_rollout_decisions_total'
V17_GLOBAL_READ_GATE_PATH = 'memory_control/v17_global_read_gate'
V17_WRITE_CONVERGENCE_GATE_PATH = 'memory_control/v17_write_convergence_gate'
_LOW_CARDINALITY_FALLBACK_REASON_BUCKETS = {
    'malformed_rollout_state',
    'missing_chat_default_memory_grant',
    'missing_developer_default_memory_grant',
    'missing_mcp_default_memory_grant',
    'missing_rollout_state',
    'uid_mismatch',
    'unsupported_consumer',
    'v17_reads_disabled',
}


class V17ReadDecision(str, Enum):
    USE_V17 = 'USE_V17'
    USE_LEGACY_SAFE = 'USE_LEGACY_SAFE'
    DENY_MEMORY = 'DENY_MEMORY'
    SHADOW_ONLY = 'SHADOW_ONLY'


@dataclass(frozen=True)
class V17GlobalReadGateDecision:
    source_path: str
    read_decision: V17ReadDecision
    reason: str = 'ok'

    @property
    def fallback_reason(self) -> Optional[str]:
        if self.read_decision == V17ReadDecision.USE_V17:
            return None
        return self.reason


@dataclass(frozen=True)
class V17WriteConvergencePolicy:
    source_path: str
    ready: bool
    reason: str = 'ok'


@dataclass(frozen=True)
class V17DefaultReadRolloutDecision:
    uid: str
    source_path: str
    consumer: str
    rollout_capabilities: V17Capabilities
    app_has_default_memory_grant: bool
    archive_capability: bool = False
    vector_projection_commit_id: Optional[str] = None
    reason: str = 'ok'
    explicit_read_decision: V17ReadDecision | None = None

    @property
    def read_decision(self) -> V17ReadDecision:
        if self.explicit_read_decision is not None:
            return self.explicit_read_decision
        if self.v17_default_enabled:
            return V17ReadDecision.USE_V17
        if (
            self.rollout_capabilities.shadow_artifacts_enabled
            and not self.rollout_capabilities.v17_reads_enabled
            and self.app_has_default_memory_grant
        ):
            return V17ReadDecision.SHADOW_ONLY
        return V17ReadDecision.DENY_MEMORY

    @property
    def v17_default_enabled(self) -> bool:
        return self.rollout_capabilities.v17_reads_enabled and self.app_has_default_memory_grant

    @property
    def v17_default_mcp_enabled(self) -> bool:
        return self.consumer == 'mcp' and self.v17_default_enabled

    @property
    def v17_default_developer_enabled(self) -> bool:
        return self.consumer == 'developer_api' and self.v17_default_enabled

    @property
    def v17_default_chat_enabled(self) -> bool:
        return self.consumer == 'omi_chat' and self.v17_default_enabled

    @property
    def grant_reason_key(self) -> str:
        if self.consumer == 'developer_api':
            return 'developer'
        if self.consumer == 'omi_chat':
            return 'chat'
        return self.consumer

    @property
    def fallback_reason(self) -> Optional[str]:
        if self.read_decision == V17ReadDecision.DENY_MEMORY and self.reason != 'ok':
            return self.reason
        if self.v17_default_enabled:
            return None
        if self.read_decision == V17ReadDecision.SHADOW_ONLY:
            return 'shadow_only'
        if self.read_decision == V17ReadDecision.USE_LEGACY_SAFE:
            return self.reason
        if self.reason != 'ok':
            return self.reason
        if not self.rollout_capabilities.v17_reads_enabled:
            return 'v17_reads_disabled'
        if not self.app_has_default_memory_grant:
            return f'missing_{self.grant_reason_key}_default_memory_grant'
        return f'v17_default_{self.grant_reason_key}_disabled'


def normalize_v17_global_read_gate(data) -> V17GlobalReadGateDecision:
    """Normalize global V17 read kill-switch state.

    This gate is deliberately independent from per-user
    `users/{uid}/memory_control/state`. Missing or malformed config denies V17
    reads so product routes can fail before per-user Firestore/vector/item reads.
    """

    if not isinstance(data, dict):
        return V17GlobalReadGateDecision(
            source_path=V17_GLOBAL_READ_GATE_PATH,
            read_decision=V17ReadDecision.DENY_MEMORY,
            reason='missing_global_read_gate',
        )
    v17_reads_enabled = data.get('v17_reads_enabled')
    kill_switch_active = data.get('kill_switch_active')
    if not isinstance(v17_reads_enabled, bool) or not isinstance(kill_switch_active, bool):
        return V17GlobalReadGateDecision(
            source_path=V17_GLOBAL_READ_GATE_PATH,
            read_decision=V17ReadDecision.DENY_MEMORY,
            reason='malformed_global_read_gate',
        )
    if kill_switch_active:
        return V17GlobalReadGateDecision(
            source_path=V17_GLOBAL_READ_GATE_PATH,
            read_decision=V17ReadDecision.DENY_MEMORY,
            reason='global_v17_read_kill_switch_active',
        )
    if not v17_reads_enabled:
        return V17GlobalReadGateDecision(
            source_path=V17_GLOBAL_READ_GATE_PATH,
            read_decision=V17ReadDecision.DENY_MEMORY,
            reason='global_v17_reads_disabled',
        )
    return V17GlobalReadGateDecision(source_path=V17_GLOBAL_READ_GATE_PATH, read_decision=V17ReadDecision.USE_V17)


def read_v17_global_read_gate(*, db_client) -> V17GlobalReadGateDecision:
    """Read the global emergency V17 product-read gate before per-user rollout state."""

    try:
        snapshot = db_client.document(V17_GLOBAL_READ_GATE_PATH).get()
        data = snapshot.to_dict() if getattr(snapshot, 'exists', True) else None
    except Exception:
        return V17GlobalReadGateDecision(
            source_path=V17_GLOBAL_READ_GATE_PATH,
            read_decision=V17ReadDecision.DENY_MEMORY,
            reason='malformed_global_read_gate',
        )
    return normalize_v17_global_read_gate(data)


def normalize_v17_write_convergence_gate(data) -> V17WriteConvergencePolicy:
    """Normalize server-owned write convergence/outbox readiness.

    External legacy-memory writes may only bypass the V17 read split-brain guard
    when all durable convergence bits are explicitly boolean true. Missing,
    malformed, or partially ready config fails safe and keeps legacy writes
    blocked for V17/shadow read consumers.
    """

    if not isinstance(data, dict):
        return V17WriteConvergencePolicy(
            source_path=V17_WRITE_CONVERGENCE_GATE_PATH,
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
        if not isinstance(data.get(field), bool):
            return V17WriteConvergencePolicy(
                source_path=V17_WRITE_CONVERGENCE_GATE_PATH,
                ready=False,
                reason='malformed_write_convergence_gate',
            )
    if not all(data[field] is True for field in required_true_fields):
        return V17WriteConvergencePolicy(
            source_path=V17_WRITE_CONVERGENCE_GATE_PATH,
            ready=False,
            reason='write_convergence_not_ready',
        )
    return V17WriteConvergencePolicy(source_path=V17_WRITE_CONVERGENCE_GATE_PATH, ready=True)


def read_v17_write_convergence_gate(*, db_client) -> V17WriteConvergencePolicy:
    """Read server-owned durable write convergence/outbox readiness."""

    try:
        snapshot = db_client.document(V17_WRITE_CONVERGENCE_GATE_PATH).get()
        data = snapshot.to_dict() if getattr(snapshot, 'exists', True) else None
    except Exception:
        return V17WriteConvergencePolicy(
            source_path=V17_WRITE_CONVERGENCE_GATE_PATH,
            ready=False,
            reason='malformed_write_convergence_gate',
        )
    return normalize_v17_write_convergence_gate(data)


def disabled_v17_default_read_rollout_decision(
    *, uid: str, source_path: str, consumer: str, reason: str
) -> V17DefaultReadRolloutDecision:
    return V17DefaultReadRolloutDecision(
        uid=uid,
        source_path=source_path,
        consumer=consumer,
        rollout_capabilities=V17Capabilities(
            uid=uid,
            mode=V17Mode.off,
            legacy_only=True,
            shadow_artifacts_enabled=False,
            v17_writes_enabled=False,
            v17_reads_enabled=False,
            legacy_reads_authoritative=True,
        ),
        app_has_default_memory_grant=False,
        archive_capability=False,
        reason=reason,
        explicit_read_decision=V17ReadDecision.DENY_MEMORY,
    )


def legacy_safe_v17_default_read_rollout_decision(
    *, uid: str, source_path: str, consumer: str, reason: str
) -> V17DefaultReadRolloutDecision:
    """Mark an explicit legacy-only endpoint/caller as safe by policy.

    This is intentionally opt-in: malformed/missing/no-grant V17 control state
    must not be interpreted as a safe legacy downgrade for default V17 reads.
    """

    return V17DefaultReadRolloutDecision(
        uid=uid,
        source_path=source_path,
        consumer=consumer,
        rollout_capabilities=V17Capabilities(
            uid=uid,
            mode=V17Mode.off,
            legacy_only=True,
            shadow_artifacts_enabled=False,
            v17_writes_enabled=False,
            v17_reads_enabled=False,
            legacy_reads_authoritative=True,
        ),
        app_has_default_memory_grant=False,
        archive_capability=False,
        reason=reason,
        explicit_read_decision=V17ReadDecision.USE_LEGACY_SAFE,
    )


@dataclass(frozen=True)
class V17LegacyMemoryWriteGuardDecision:
    allowed: bool
    detail: dict
    status_code: int = 200


def assert_legacy_memory_write_allowed_for_default_read_decision(
    decision: V17DefaultReadRolloutDecision,
    *,
    operation: str,
    allow_write_convergence: bool = False,
    write_convergence_policy: V17WriteConvergencePolicy | None = None,
) -> V17LegacyMemoryWriteGuardDecision:
    """Guard legacy external memory writes while default V17 reads are enabled.

    Developer/MCP create/edit/delete currently mutate legacy `memories` state while
    V17 reads hydrate from `memory_items`. Until a server-owned convergence/dual-write
    policy is explicitly passed, block those legacy mutations for consumers whose
    persisted rollout says V17 reads are authoritative or shadowed. Missing or
    malformed control state also fails safe; explicitly disabled legacy-safe reads
    preserve existing legacy write behavior.
    """

    fail_safe_reasons = {'missing_rollout_state', 'malformed_rollout_state', 'uid_mismatch'}
    should_block = decision.read_decision in {V17ReadDecision.USE_V17, V17ReadDecision.SHADOW_ONLY}
    should_block = should_block or decision.fallback_reason in fail_safe_reasons
    if not should_block:
        return V17LegacyMemoryWriteGuardDecision(
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
        return V17LegacyMemoryWriteGuardDecision(
            allowed=True,
            detail={
                'enabled': True,
                'reason': 'legacy_memory_write_allowed_with_v17_convergence',
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
    elif allow_write_convergence:
        convergence_reason = 'legacy_boolean_convergence_override_ignored'
    return V17LegacyMemoryWriteGuardDecision(
        allowed=False,
        status_code=409,
        detail={
            'enabled': False,
            'reason': 'v17_default_read_legacy_write_blocked',
            'consumer': decision.consumer,
            'operation': operation,
            'read_decision': decision.read_decision.value,
            'source_path': decision.source_path,
            'convergence_reason': convergence_reason,
        },
    )


def _consumer_default_memory_grant_enabled(data: dict, consumer: str) -> bool:
    grants = data.get('grants')
    if isinstance(grants, dict):
        if consumer == 'developer_api':
            grant_keys = ['developer', 'developer_api']
        elif consumer == 'omi_chat':
            grant_keys = ['omi_chat', 'chat']
        else:
            grant_keys = [consumer]
        for grant_key in grant_keys:
            consumer_grants = grants.get(grant_key)
            if isinstance(consumer_grants, dict) and consumer_grants.get('default_memory') is True:
                return True

    if consumer == 'mcp':
        return data.get('mcp_default_memory_grant') is True
    if consumer == 'developer_api':
        return data.get('developer_default_memory_grant') is True
    if consumer == 'omi_chat':
        return data.get('omi_chat_default_memory_grant') is True or data.get('chat_default_memory_grant') is True
    return False


def _consumer_archive_capability_value(data: dict, consumer: str) -> bool | None:
    grants = data.get('grants')
    if isinstance(grants, dict):
        if consumer == 'developer_api':
            grant_keys = ['developer', 'developer_api']
        elif consumer == 'omi_chat':
            grant_keys = ['omi_chat', 'chat']
        else:
            grant_keys = [consumer]
        for grant_key in grant_keys:
            consumer_grants = grants.get(grant_key)
            if isinstance(consumer_grants, dict) and 'archive' in consumer_grants:
                archive_capability = consumer_grants.get('archive')
                if not isinstance(archive_capability, bool):
                    return None
                return archive_capability

    top_level_keys = []
    if consumer == 'mcp':
        top_level_keys = ['mcp_archive_capability']
    elif consumer == 'developer_api':
        top_level_keys = ['developer_archive_capability', 'developer_api_archive_capability']
    elif consumer == 'omi_chat':
        top_level_keys = ['omi_chat_archive_capability', 'chat_archive_capability']
    for key in top_level_keys:
        if key in data:
            archive_capability = data.get(key)
            if not isinstance(archive_capability, bool):
                return None
            return archive_capability
    return False


def normalize_v17_default_read_rollout_decision(
    *, uid: str, source_path: str, consumer: str, data
) -> V17DefaultReadRolloutDecision:
    """Normalize a fetched `users/{uid}/memory_control/state` doc for default V17 reads.

    Missing, malformed, uid-mismatched, disabled, or consumer-grant-less docs fail
    closed. Archive is intentionally not derived from persisted grants here:
    default read consumers must keep `archive_capability=False` and use separate
    explicit Archive routes/capabilities.
    """

    if consumer not in SUPPORTED_DEFAULT_READ_CONSUMERS:
        return disabled_v17_default_read_rollout_decision(
            uid=uid, source_path=source_path, consumer=consumer, reason='unsupported_consumer'
        )

    try:
        if not isinstance(data, dict):
            return disabled_v17_default_read_rollout_decision(
                uid=uid, source_path=source_path, consumer=consumer, reason='missing_rollout_state'
            )
        if data.get('uid', uid) != uid:
            return disabled_v17_default_read_rollout_decision(
                uid=uid, source_path=source_path, consumer=consumer, reason='uid_mismatch'
            )

        state = V17RolloutState(
            uid=uid,
            mode=data.get('mode', V17Mode.off.value),
            mode_epoch=int(data.get('mode_epoch', 0) or 0),
            cutover_epoch=int(data.get('cutover_epoch', 0) or 0),
            account_generation=int(data.get('account_generation', 0) or 0),
            last_reconciled_legacy_revision=data.get('last_reconciled_legacy_revision'),
            fallback_projection_ready=data.get('fallback_projection_ready') is True,
            persistent_v17_writes_started=data.get('persistent_v17_writes_started') is True,
            decommission_reconciled=data.get('decommission_reconciled') is True,
            writes_blocked=data.get('writes_blocked') is True,
            stage_gates=data.get('stage_gates') or {},
        )
        vector_projection_commit_id = data.get('vector_projection_commit_id')
        if not isinstance(vector_projection_commit_id, str) or not vector_projection_commit_id.strip():
            vector_projection_commit_id = None
        return V17DefaultReadRolloutDecision(
            uid=uid,
            source_path=source_path,
            consumer=consumer,
            rollout_capabilities=decide_v17_capabilities(uid, state.mode, state),
            app_has_default_memory_grant=_consumer_default_memory_grant_enabled(data, consumer),
            archive_capability=False,
            vector_projection_commit_id=vector_projection_commit_id,
            reason='ok',
        )
    except (TypeError, ValueError, AttributeError):
        return disabled_v17_default_read_rollout_decision(
            uid=uid, source_path=source_path, consumer=consumer, reason='malformed_rollout_state'
        )


def normalize_v17_archive_read_rollout_decision(
    *, uid: str, source_path: str, consumer: str, data
) -> V17DefaultReadRolloutDecision:
    """Normalize persisted control state for explicit Archive product reads.

    Archive access is intentionally stronger than default-memory reads: callers
    need the usual V17 default-read authorization plus a distinct server-owned
    Archive capability in `users/{uid}/memory_control/state`. Client query flags
    are not interpreted here and cannot grant Archive access.
    """

    default_decision = normalize_v17_default_read_rollout_decision(
        uid=uid, source_path=source_path, consumer=consumer, data=data
    )
    if default_decision.read_decision != V17ReadDecision.USE_V17:
        return default_decision

    archive_capability = _consumer_archive_capability_value(data, consumer)
    if archive_capability is None:
        return V17DefaultReadRolloutDecision(
            uid=uid,
            source_path=source_path,
            consumer=consumer,
            rollout_capabilities=default_decision.rollout_capabilities,
            app_has_default_memory_grant=default_decision.app_has_default_memory_grant,
            archive_capability=False,
            vector_projection_commit_id=default_decision.vector_projection_commit_id,
            reason='malformed_archive_capability',
            explicit_read_decision=V17ReadDecision.DENY_MEMORY,
        )
    if not archive_capability:
        return V17DefaultReadRolloutDecision(
            uid=uid,
            source_path=source_path,
            consumer=consumer,
            rollout_capabilities=default_decision.rollout_capabilities,
            app_has_default_memory_grant=default_decision.app_has_default_memory_grant,
            archive_capability=False,
            vector_projection_commit_id=default_decision.vector_projection_commit_id,
            reason=f'missing_{default_decision.grant_reason_key}_archive_capability',
            explicit_read_decision=V17ReadDecision.DENY_MEMORY,
        )
    return V17DefaultReadRolloutDecision(
        uid=uid,
        source_path=source_path,
        consumer=consumer,
        rollout_capabilities=default_decision.rollout_capabilities,
        app_has_default_memory_grant=default_decision.app_has_default_memory_grant,
        archive_capability=True,
        vector_projection_commit_id=default_decision.vector_projection_commit_id,
        reason='ok',
        explicit_read_decision=V17ReadDecision.USE_V17,
    )


def read_v17_default_read_rollout(*, uid: str, db_client, consumer: str) -> V17DefaultReadRolloutDecision:
    """Read and normalize server-owned persisted default-read rollout state."""

    source_path = V17Collections(uid=uid).memory_control_state
    try:
        snapshot = db_client.document(source_path).get()
        data = snapshot.to_dict() if getattr(snapshot, 'exists', True) else None
    except (TypeError, ValueError, AttributeError):
        return disabled_v17_default_read_rollout_decision(
            uid=uid, source_path=source_path, consumer=consumer, reason='malformed_rollout_state'
        )
    return normalize_v17_default_read_rollout_decision(uid=uid, source_path=source_path, consumer=consumer, data=data)


def read_v17_archive_read_rollout(*, uid: str, db_client, consumer: str) -> V17DefaultReadRolloutDecision:
    """Read persisted default-read rollout plus server-owned Archive capability."""

    source_path = V17Collections(uid=uid).memory_control_state
    try:
        snapshot = db_client.document(source_path).get()
        data = snapshot.to_dict() if getattr(snapshot, 'exists', True) else None
    except (TypeError, ValueError, AttributeError):
        return disabled_v17_default_read_rollout_decision(
            uid=uid, source_path=source_path, consumer=consumer, reason='malformed_rollout_state'
        )
    return normalize_v17_archive_read_rollout_decision(uid=uid, source_path=source_path, consumer=consumer, data=data)


def _read_v17_default_rollout_state_doc(*, uid: str, db_client):
    source_path = V17Collections(uid=uid).memory_control_state
    try:
        snapshot = db_client.document(source_path).get()
        data = snapshot.to_dict() if getattr(snapshot, 'exists', True) else None
    except (TypeError, ValueError, AttributeError):
        return source_path, None, 'malformed_rollout_state'
    return source_path, data, None


def read_v17_default_read_rollout_decisions(
    *, uid: str, db_client, consumers: Iterable[str] = DEFAULT_READ_OBSERVABILITY_CONSUMERS
) -> dict[str, V17DefaultReadRolloutDecision]:
    """Read one rollout state doc and derive per-consumer default-read decisions."""

    source_path, data, read_error = _read_v17_default_rollout_state_doc(uid=uid, db_client=db_client)
    decisions = {}
    for consumer in consumers:
        if read_error is not None:
            decisions[consumer] = disabled_v17_default_read_rollout_decision(
                uid=uid, source_path=source_path, consumer=consumer, reason=read_error
            )
        else:
            decisions[consumer] = normalize_v17_default_read_rollout_decision(
                uid=uid, source_path=source_path, consumer=consumer, data=data
            )
    return decisions


def build_v17_default_read_rollout_observability(decision: V17DefaultReadRolloutDecision) -> dict:
    capabilities = decision.rollout_capabilities
    fallback_reason = decision.fallback_reason
    reason = fallback_reason or decision.reason
    return {
        'consumer': decision.consumer,
        'enabled': decision.v17_default_enabled,
        'reason': reason,
        'read_decision': decision.read_decision.value,
        'mode': capabilities.mode.value,
        'v17_reads_enabled': capabilities.v17_reads_enabled,
        'legacy_reads_authoritative': capabilities.legacy_reads_authoritative,
        'default_memory_grant': decision.app_has_default_memory_grant,
        'archive_default_visible': False,
        'archive_capability': decision.archive_capability,
        'fallback_reason': fallback_reason,
        'capabilities': {
            'legacy_only': capabilities.legacy_only,
            'shadow_artifacts_enabled': capabilities.shadow_artifacts_enabled,
            'v17_writes_enabled': capabilities.v17_writes_enabled,
            'v17_reads_enabled': capabilities.v17_reads_enabled,
            'legacy_reads_authoritative': capabilities.legacy_reads_authoritative,
        },
    }


def build_v17_default_read_rollout_audit_event(decision: V17DefaultReadRolloutDecision) -> dict:
    enabled = decision.v17_default_enabled
    return {
        'uid': decision.uid,
        'source_path': decision.source_path,
        'consumer': decision.consumer,
        'enabled': enabled,
        'outcome': 'enabled' if enabled else 'fallback',
        'read_decision': decision.read_decision.value,
        'fallback_reason': decision.fallback_reason,
        'default_memory_grant': decision.app_has_default_memory_grant,
        'v17_reads_enabled': decision.rollout_capabilities.v17_reads_enabled,
        'archive_default_visible': False,
        'archive_capability': decision.archive_capability,
    }


def build_v17_default_read_rollout_decision_counters(events: list[dict]) -> dict:
    counters = {'total': {'enabled': 0, 'fallback': 0}, 'by_consumer': {}}
    for event in events:
        consumer = str(event.get('consumer') or 'unknown')
        consumer_counters = counters['by_consumer'].setdefault(
            consumer, {'enabled': 0, 'fallback': 0, 'fallback_reasons': {}}
        )
        if event.get('enabled') is True:
            counters['total']['enabled'] += 1
            consumer_counters['enabled'] += 1
        else:
            counters['total']['fallback'] += 1
            consumer_counters['fallback'] += 1
            fallback_reason = str(event.get('fallback_reason') or 'unknown_fallback')
            consumer_counters['fallback_reasons'][fallback_reason] = (
                consumer_counters['fallback_reasons'].get(fallback_reason, 0) + 1
            )
    return counters


def build_v17_default_read_rollout_audit_events(decisions: dict[str, V17DefaultReadRolloutDecision]) -> dict:
    events = [build_v17_default_read_rollout_audit_event(decision) for decision in decisions.values()]
    return {'events': events, 'counters': build_v17_default_read_rollout_decision_counters(events)}


def _bucket_v17_default_read_consumer(consumer: str) -> str:
    if consumer in SUPPORTED_DEFAULT_READ_CONSUMERS:
        return consumer
    return 'unsupported_consumer'


def _bucket_v17_default_read_fallback_reason(fallback_reason: str | None) -> str:
    if not fallback_reason:
        return 'none'
    if fallback_reason in _LOW_CARDINALITY_FALLBACK_REASON_BUCKETS:
        return fallback_reason
    if fallback_reason.startswith('missing_') and fallback_reason.endswith('_default_memory_grant'):
        return 'missing_default_memory_grant_other'
    if fallback_reason.startswith('v17_default_') and fallback_reason.endswith('_disabled'):
        return 'v17_default_consumer_disabled'
    return 'other'


def _format_prometheus_sample(metric_name: str, labels: dict[str, str], value: int) -> str:
    formatted_labels = ','.join(f'{label}="{str(label_value)}"' for label, label_value in labels.items())
    return f'{metric_name}{{{formatted_labels}}} {int(value)}'


def render_v17_default_read_rollout_metrics(counters: dict) -> str:
    """Render local rollout decision counters as low-cardinality Prometheus text.

    The caller passes already-aggregated counters from local rollout audit events.
    Labels are intentionally limited to consumer, outcome, and fallback reason
    bucket. Do not add uid, source_path, app/source identifiers, or raw dynamic
    fallback strings here; those belong in admin/debug JSON, not ops metrics.
    """

    lines = [
        f'# HELP {V17_DEFAULT_READ_ROLLOUT_METRIC_NAME} Local V17 default-read rollout decisions by consumer and outcome.',
        f'# TYPE {V17_DEFAULT_READ_ROLLOUT_METRIC_NAME} counter',
    ]
    for consumer, consumer_counters in sorted((counters.get('by_consumer') or {}).items()):
        consumer_bucket = _bucket_v17_default_read_consumer(str(consumer))
        enabled_count = int((consumer_counters or {}).get('enabled', 0) or 0)
        if enabled_count:
            lines.append(
                _format_prometheus_sample(
                    V17_DEFAULT_READ_ROLLOUT_METRIC_NAME,
                    {'consumer': consumer_bucket, 'outcome': 'enabled', 'fallback_reason': 'none'},
                    enabled_count,
                )
            )

        fallback_reasons = (consumer_counters or {}).get('fallback_reasons') or {}
        if fallback_reasons:
            fallback_buckets: dict[str, int] = {}
            for fallback_reason, count in fallback_reasons.items():
                fallback_bucket = _bucket_v17_default_read_fallback_reason(str(fallback_reason))
                fallback_buckets[fallback_bucket] = fallback_buckets.get(fallback_bucket, 0) + int(count or 0)
            for fallback_bucket, count in sorted(fallback_buckets.items()):
                if not count:
                    continue
                lines.append(
                    _format_prometheus_sample(
                        V17_DEFAULT_READ_ROLLOUT_METRIC_NAME,
                        {'consumer': consumer_bucket, 'outcome': 'fallback', 'fallback_reason': fallback_bucket},
                        count,
                    )
                )
        else:
            fallback_count = int((consumer_counters or {}).get('fallback', 0) or 0)
            if fallback_count:
                lines.append(
                    _format_prometheus_sample(
                        V17_DEFAULT_READ_ROLLOUT_METRIC_NAME,
                        {'consumer': consumer_bucket, 'outcome': 'fallback', 'fallback_reason': 'unknown_fallback'},
                        fallback_count,
                    )
                )
    return '\n'.join(lines) + '\n'


def build_v17_default_read_rollout_observability_report(
    decisions: dict[str, V17DefaultReadRolloutDecision],
) -> dict:
    source_path = next(iter(decisions.values())).source_path if decisions else ''
    uid = next(iter(decisions.values())).uid if decisions else ''
    audit = build_v17_default_read_rollout_audit_events(decisions)
    return {
        'uid': uid,
        'source_path': source_path,
        'archive_default_visible': False,
        'archive_capability': False,
        'decision_audit_events': audit['events'],
        'decision_counters': audit['counters'],
        'decision_metrics_prometheus': render_v17_default_read_rollout_metrics(audit['counters']),
        'consumers': {
            consumer: build_v17_default_read_rollout_observability(decision) for consumer, decision in decisions.items()
        },
    }
