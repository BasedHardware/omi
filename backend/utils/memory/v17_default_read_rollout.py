from dataclasses import dataclass
from typing import Optional

from config.v17_memory import V17Capabilities, V17Mode, V17RolloutState, decide_v17_capabilities
from database.v17_collections import V17Collections

SUPPORTED_DEFAULT_READ_CONSUMERS = {'mcp', 'developer_api'}


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
    def grant_reason_key(self) -> str:
        if self.consumer == 'developer_api':
            return 'developer'
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
        grant_keys = ['developer', 'developer_api'] if consumer == 'developer_api' else [consumer]
        for grant_key in grant_keys:
            consumer_grants = grants.get(grant_key)
            if isinstance(consumer_grants, dict) and consumer_grants.get('default_memory') is True:
                return True

    if consumer == 'mcp':
        return data.get('mcp_default_memory_grant') is True
    if consumer == 'developer_api':
        return data.get('developer_default_memory_grant') is True
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
