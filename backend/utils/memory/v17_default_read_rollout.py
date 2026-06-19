from dataclasses import dataclass
from typing import Iterable, Optional

from config.v17_memory import V17Capabilities, V17Mode, V17RolloutState, decide_v17_capabilities
from database.v17_collections import V17Collections

SUPPORTED_DEFAULT_READ_CONSUMERS = {'mcp', 'developer_api', 'omi_chat'}
DEFAULT_READ_OBSERVABILITY_CONSUMERS = ('mcp', 'developer_api', 'omi_chat')


@dataclass(frozen=True)
class V17DefaultReadRolloutDecision:
    uid: str
    source_path: str
    consumer: str
    rollout_capabilities: V17Capabilities
    app_has_default_memory_grant: bool
    archive_capability: bool = False
    reason: str = 'ok'

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
        if self.v17_default_enabled:
            return None
        if self.reason != 'ok':
            return self.reason
        if not self.rollout_capabilities.v17_reads_enabled:
            return 'v17_reads_disabled'
        if not self.app_has_default_memory_grant:
            return f'missing_{self.grant_reason_key}_default_memory_grant'
        return f'v17_default_{self.grant_reason_key}_disabled'


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
        return V17DefaultReadRolloutDecision(
            uid=uid,
            source_path=source_path,
            consumer=consumer,
            rollout_capabilities=decide_v17_capabilities(uid, state.mode, state),
            app_has_default_memory_grant=_consumer_default_memory_grant_enabled(data, consumer),
            archive_capability=False,
            reason='ok',
        )
    except (TypeError, ValueError, AttributeError):
        return disabled_v17_default_read_rollout_decision(
            uid=uid, source_path=source_path, consumer=consumer, reason='malformed_rollout_state'
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
        'consumers': {
            consumer: build_v17_default_read_rollout_observability(decision) for consumer, decision in decisions.items()
        },
    }
