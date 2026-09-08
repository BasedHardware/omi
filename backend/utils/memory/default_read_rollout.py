"""Universal default-memory authorization and global incident gate.

Released rollout-shaped response fields remain compatibility metadata; they do
not select users or storage authorities.
"""

# LIFECYCLE: permanent

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, cast

from config.memory_rollout import (
    MemoryRolloutCapabilities,
    universal_memory_capabilities,
)
from database.memory_collections import MemoryCollections

SUPPORTED_DEFAULT_READ_CONSUMERS = {'mcp', 'developer_api', 'omi_chat'}
DEFAULT_READ_ROLLOUT_SCHEMA_VERSION = 1
DEFAULT_READ_ROLLOUT_TIMEOUT_SECONDS = 2.0
GLOBAL_READ_GATE_PATH = 'memory_control/global_read_gate'


class MemoryReadDecision(str, Enum):
    USE_MEMORY = 'USE_MEMORY'
    DENY_MEMORY = 'DENY_MEMORY'


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
        if self.reason != 'ok':
            return self.reason
        if not self.app_has_default_memory_grant:
            return f'missing_{self.grant_reason_key}_default_memory_grant'
        return f'memory_default_{self.grant_reason_key}_disabled'


Payload = dict[str, Any]
ObservabilityPayload = dict[str, Any]


def _payload_or_none(value: object) -> Payload | None:
    return cast(Payload, value) if isinstance(value, dict) else None


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
    """Read the global emergency gate before optional consumer-grant state."""

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


def disabled_default_read_rollout_decision(
    *, uid: str, source_path: str, consumer: str, reason: str
) -> DefaultReadRolloutDecision:
    return DefaultReadRolloutDecision(
        uid=uid,
        source_path=source_path,
        consumer=consumer,
        rollout_capabilities=universal_memory_capabilities(uid),
        app_has_default_memory_grant=False,
        archive_capability=False,
        reason=reason,
        explicit_read_decision=MemoryReadDecision.DENY_MEMORY,
    )


def _consumer_grants(data: dict[str, Any], consumer: str) -> tuple[bool, bool]:
    """Return universal defaults plus any explicit server-owned consumer grant.

    Older accounts need no control-document backfill. An existing explicit grant
    remains authoritative, including an explicit false opt-out. Malformed grant
    structures fail closed instead of being treated as rollout state.
    """

    if 'grants' not in data:
        return True, False
    grants = data['grants']
    if not isinstance(grants, dict):
        raise ValueError('malformed_grants')
    if consumer not in grants:
        return True, False
    consumer_grants = grants[consumer]
    if not isinstance(consumer_grants, dict):
        raise ValueError('malformed_consumer_grant')
    default_memory = consumer_grants.get('default_memory')
    if not isinstance(default_memory, bool):
        raise ValueError('malformed_default_memory_grant')
    archive = consumer_grants.get('archive', False)
    if not isinstance(archive, bool):
        raise ValueError('malformed_archive_capability')
    return default_memory, archive


def normalize_default_read_rollout_decision(
    *, uid: str, source_path: str, consumer: str, data: Any
) -> DefaultReadRolloutDecision:
    """Normalize optional consumer grants without restoring per-UID rollout."""

    if consumer not in SUPPORTED_DEFAULT_READ_CONSUMERS:
        return disabled_default_read_rollout_decision(
            uid=uid, source_path=source_path, consumer=consumer, reason='unsupported_consumer'
        )

    try:
        if data is None:
            payload: Payload = {}
        else:
            payload = _payload_or_none(data) or {}
            if not isinstance(data, dict):
                raise ValueError('malformed_memory_control_state')
        if payload.get('uid', uid) != uid:
            return disabled_default_read_rollout_decision(
                uid=uid, source_path=source_path, consumer=consumer, reason='uid_mismatch'
            )
        if payload.get('schema_version', DEFAULT_READ_ROLLOUT_SCHEMA_VERSION) != DEFAULT_READ_ROLLOUT_SCHEMA_VERSION:
            return disabled_default_read_rollout_decision(
                uid=uid, source_path=source_path, consumer=consumer, reason='unsupported_memory_control_schema'
            )
        account_generation = payload.get('account_generation', 0)
        if not isinstance(account_generation, int) or isinstance(account_generation, bool) or account_generation < 0:
            raise ValueError('malformed_account_generation')
        default_memory_grant, _ = _consumer_grants(payload, consumer)
        vector_projection_commit_id = payload.get('vector_projection_commit_id')
        if not isinstance(vector_projection_commit_id, str) or not vector_projection_commit_id.strip():
            vector_projection_commit_id = None
        vector_repair_outbox_enabled = payload.get('vector_repair_outbox_enabled') is True
        return DefaultReadRolloutDecision(
            uid=uid,
            source_path=source_path,
            consumer=consumer,
            rollout_capabilities=universal_memory_capabilities(uid, account_generation=account_generation),
            app_has_default_memory_grant=default_memory_grant,
            archive_capability=False,
            vector_projection_commit_id=vector_projection_commit_id,
            vector_repair_outbox_enabled=vector_repair_outbox_enabled,
            reason='ok',
        )
    except (TypeError, ValueError, AttributeError):
        return disabled_default_read_rollout_decision(
            uid=uid, source_path=source_path, consumer=consumer, reason='malformed_memory_control_state'
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

    payload = cast(dict[str, Any], data) if isinstance(data, dict) else {}
    try:
        _, archive_capability = _consumer_grants(payload, consumer)
    except ValueError:
        return disabled_default_read_rollout_decision(
            uid=uid, source_path=source_path, consumer=consumer, reason='malformed_memory_control_state'
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
            uid=uid, source_path=source_path, consumer=consumer, reason='malformed_memory_control_state'
        )
    except Exception:
        return disabled_default_read_rollout_decision(
            uid=uid, source_path=source_path, consumer=consumer, reason='memory_control_read_failed'
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
            uid=uid, source_path=source_path, consumer=consumer, reason='malformed_memory_control_state'
        )
    except Exception:
        return disabled_default_read_rollout_decision(
            uid=uid, source_path=source_path, consumer=consumer, reason='memory_control_read_failed'
        )
    return normalize_archive_read_rollout_decision(uid=uid, source_path=source_path, consumer=consumer, data=data)


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


# Neutral symbol alias (memory name remains valid via shim)
ReadDecision = MemoryReadDecision
