"""Canonical module for ``utils.memory.v3_control_state_adapter`` (WS-G8b).

Neutral ``v3_control_state_adapter`` is the source of truth. Legacy ``v3_control_state_adapter`` remains an importable alias.
"""

from __future__ import annotations

from config.memory_rollout import MemoryRolloutMode, MemoryRolloutState, decide_memory_rollout_capabilities
from database.memory_collections import MemoryCollections
from utils.memory.default_read_rollout import (
    DEFAULT_READ_ROLLOUT_SCHEMA_VERSION,
    MemoryReadDecision,
    read_global_read_gate,
    read_rollout_state_doc,
    read_write_convergence_gate,
)
from utils.memory.v3_control_reader_contract import (
    V3ControlDecisionReason,
    V3ControlReadResult,
    V3ControlState,
)

V3_DEFAULT_CONSUMER = 'omi_chat'
_MODE_RANK = {
    MemoryRolloutMode.off: 0,
    MemoryRolloutMode.shadow: 1,
    MemoryRolloutMode.write: 2,
    MemoryRolloutMode.read: 3,
}
_READ_ERROR_REASON_MAP = {
    'malformed_rollout_state': V3ControlDecisionReason.MALFORMED_CONTROL_DOC,
    'rollout_read_failed': V3ControlDecisionReason.CONTROL_READ_FAILED,
}


def _mode(value) -> MemoryRolloutMode:
    return value if isinstance(value, MemoryRolloutMode) else MemoryRolloutMode(value)


def resolve_v3_effective_mode(configured_mode, persisted_mode) -> MemoryRolloutMode:
    """Return the lower-ranked mode; global config is a ceiling, not an elevator."""

    configured = _mode(configured_mode)
    persisted = _mode(persisted_mode)
    if _MODE_RANK[configured] <= _MODE_RANK[persisted]:
        return configured
    return persisted


def _read_error_reason(reason: str | None) -> V3ControlDecisionReason:
    return _READ_ERROR_REASON_MAP.get(str(reason or ''), V3ControlDecisionReason.CONTROL_READ_FAILED)


def _consumer_grants(data: dict, consumer: str) -> tuple[bool, bool]:
    grants = data.get('grants')
    if not isinstance(grants, dict):
        return False, False
    consumer_grants = grants.get(consumer)
    if not isinstance(consumer_grants, dict):
        return False, False
    default_memory = consumer_grants.get('default_memory') is True
    archive_value = consumer_grants.get('archive')
    archive_allowed = archive_value if isinstance(archive_value, bool) else False
    return default_memory, archive_allowed


def _missing_or_unsupported_schema(data) -> bool:
    if not isinstance(data, dict):
        return False
    return data.get('schema_version') != DEFAULT_READ_ROLLOUT_SCHEMA_VERSION


def _rollout_state_from_data(*, uid: str, data: dict) -> MemoryRolloutState:
    return MemoryRolloutState(
        uid=uid,
        mode=data.get('mode', MemoryRolloutMode.off.value),
        mode_epoch=int(data.get('mode_epoch', 0) or 0),
        cutover_epoch=int(data.get('cutover_epoch', 0) or 0),
        account_generation=int(data.get('account_generation', 0) or 0),
        last_reconciled_legacy_revision=data.get('last_reconciled_legacy_revision'),
        fallback_projection_ready=data.get('fallback_projection_ready') is True,
        persistent_memory_writes_started=data.get('persistent_memory_writes_started') is True,
        decommission_reconciled=data.get('decommission_reconciled') is True,
        writes_blocked=data.get('writes_blocked') is True,
        stage_gates=data.get('stage_gates') or {},
    )


def read_v3_control(*, uid: str, db_client, rollout_config, consumer: str = V3_DEFAULT_CONSUMER):
    """Read canonical memory rollout state and derive the `/v3` control contract.

    Non-enrolled users are identified solely by rollout cohort membership and do
    not trigger a Firestore read. Enrolled users must have a persisted control doc;
    missing or unreadable state fails closed and is not reinterpreted as
    non-enrollment.
    """

    source_path = MemoryCollections(uid=uid).memory_control_state
    if uid not in getattr(rollout_config, 'enabled_users', set()):
        return V3ControlReadResult(cohort_enrolled=False, source_path=source_path)

    source_path, data, read_error = read_rollout_state_doc(uid=uid, db_client=db_client)
    if read_error is not None:
        return V3ControlReadResult(
            cohort_enrolled=True,
            source_path=source_path,
            read_error_reason=_read_error_reason(read_error),
        )
    if data is None:
        return V3ControlReadResult(
            cohort_enrolled=True,
            source_path=source_path,
            read_error_reason=V3ControlDecisionReason.MISSING_CONTROL_DOC,
        )
    if not isinstance(data, dict):
        return V3ControlReadResult(
            cohort_enrolled=True,
            source_path=source_path,
            read_error_reason=V3ControlDecisionReason.MALFORMED_CONTROL_DOC,
        )
    if data.get('uid') != uid:
        try:
            state = V3ControlState(
                uid=str(data.get('uid')),
                schema_version=data.get('schema_version'),
                configured_mode=_mode(getattr(rollout_config, 'mode', MemoryRolloutMode.off)),
                persisted_mode=_mode(data.get('mode', MemoryRolloutMode.off.value)),
                effective_mode=MemoryRolloutMode.off,
                mode_epoch=0,
                cutover_epoch=0,
                account_generation=None,
                default_memory_grant=False,
                archive_allowed=False,
                rollout_write_ready=False,
                projection_ready=False,
                global_read_gate_open=False,
                write_convergence_ready=False,
            )
        except (TypeError, ValueError, AttributeError):
            state = None
        return V3ControlReadResult(
            cohort_enrolled=True,
            source_path=source_path,
            state=state,
            read_error_reason=V3ControlDecisionReason.UID_MISMATCH,
        )
    if _missing_or_unsupported_schema(data):
        return V3ControlReadResult(
            cohort_enrolled=True,
            source_path=source_path,
            read_error_reason=V3ControlDecisionReason.UNSUPPORTED_CONTROL_SCHEMA,
        )

    try:
        configured_mode = _mode(getattr(rollout_config, 'mode', MemoryRolloutMode.off))
        persisted = _rollout_state_from_data(uid=uid, data=data)
        persisted_mode = _mode(persisted.mode)
        effective_mode = resolve_v3_effective_mode(configured_mode, persisted_mode)
        capabilities = decide_memory_rollout_capabilities(uid, effective_mode, persisted)
        default_memory_grant, archive_allowed = _consumer_grants(data, consumer)
    except (TypeError, ValueError, AttributeError):
        return V3ControlReadResult(
            cohort_enrolled=True,
            source_path=source_path,
            read_error_reason=V3ControlDecisionReason.MALFORMED_CONTROL_DOC,
        )

    global_read_gate_open = False
    write_convergence_ready = False
    if effective_mode == MemoryRolloutMode.read:
        global_gate = read_global_read_gate(db_client=db_client)
        write_gate = read_write_convergence_gate(db_client=db_client)
        global_read_gate_open = global_gate.read_decision == MemoryReadDecision.USE_MEMORY
        write_convergence_ready = write_gate.ready

    return V3ControlReadResult(
        cohort_enrolled=True,
        source_path=source_path,
        state=V3ControlState(
            uid=uid,
            schema_version=data.get('schema_version'),
            configured_mode=configured_mode,
            persisted_mode=persisted_mode,
            effective_mode=effective_mode,
            mode_epoch=persisted.mode_epoch,
            cutover_epoch=persisted.cutover_epoch,
            account_generation=persisted.account_generation,
            default_memory_grant=default_memory_grant,
            archive_allowed=archive_allowed,
            rollout_write_ready=capabilities.memory_writes_enabled,
            projection_ready=capabilities.memory_reads_enabled,
            global_read_gate_open=global_read_gate_open,
            write_convergence_ready=write_convergence_ready,
        ),
    )


# Neutral symbol aliases (memory names remain valid via shim)
V3_DEFAULT_CONSUMER = V3_DEFAULT_CONSUMER
