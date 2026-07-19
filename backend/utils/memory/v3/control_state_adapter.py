"""Canonical module for ``utils.memory.v3.control_state_adapter`` (WS-G8b).

This module adapts persisted control state for the V3 read path.
"""

from __future__ import annotations

from typing import Any, cast

from config.memory_rollout import (
    MemoryRolloutConfig,
    MemoryRolloutMode,
    MemoryRolloutState,
    decide_memory_rollout_capabilities,
)
from database.memory_collections import MemoryCollections
from utils.memory.default_read_rollout import (
    DEFAULT_READ_ROLLOUT_SCHEMA_VERSION,
    MemoryReadDecision,
    read_global_read_gate,
    read_rollout_state_doc,
    read_write_convergence_gate,
)
from utils.memory.memory_read_rollout_core import extract_consumer_grants
from utils.memory.v3.control_reader_contract import (
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


def _mode(value: MemoryRolloutMode | str) -> MemoryRolloutMode:
    return value if isinstance(value, MemoryRolloutMode) else MemoryRolloutMode(value)


def resolve_v3_effective_mode(
    configured_mode: MemoryRolloutMode | str, persisted_mode: MemoryRolloutMode | str
) -> MemoryRolloutMode:
    """Return the lower-ranked mode; global config is a ceiling, not an elevator."""

    configured = _mode(configured_mode)
    persisted = _mode(persisted_mode)
    if _MODE_RANK[configured] <= _MODE_RANK[persisted]:
        return configured
    return persisted


def _read_error_reason(reason: str | None) -> V3ControlDecisionReason:
    return _READ_ERROR_REASON_MAP.get(str(reason or ''), V3ControlDecisionReason.CONTROL_READ_FAILED)


def _consumer_grants(data: dict[str, Any], consumer: str) -> tuple[bool, bool]:
    snapshot = extract_consumer_grants(data, consumer)
    archive_allowed = snapshot.archive_capability if snapshot.archive_capability is not None else False
    return snapshot.default_memory, archive_allowed


def _missing_or_unsupported_schema(data: dict[str, Any]) -> bool:
    return data.get('schema_version') != DEFAULT_READ_ROLLOUT_SCHEMA_VERSION


def _rollout_state_from_data(*, uid: str, data: dict[str, Any]) -> MemoryRolloutState:
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


def read_v3_control(
    *, uid: str, db_client: Any, rollout_config: MemoryRolloutConfig, consumer: str = V3_DEFAULT_CONSUMER
) -> V3ControlReadResult:
    """Read canonical memory rollout state and derive the `/v3` control contract.

    Non-enrolled users are identified solely by rollout cohort membership and do
    not trigger a Firestore read. Enrolled users must have a persisted control doc;
    missing or unreadable state fails closed and is not reinterpreted as
    non-enrollment.
    """

    source_path = MemoryCollections(uid=uid).memory_control_state
    if uid not in rollout_config.enabled_users:
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
    payload = cast(dict[str, Any], data)
    if payload.get('uid') != uid:
        return V3ControlReadResult(
            cohort_enrolled=True,
            source_path=source_path,
            state=None,
            read_error_reason=V3ControlDecisionReason.UID_MISMATCH,
        )
    if _missing_or_unsupported_schema(payload):
        return V3ControlReadResult(
            cohort_enrolled=True,
            source_path=source_path,
            read_error_reason=V3ControlDecisionReason.UNSUPPORTED_CONTROL_SCHEMA,
        )

    try:
        configured_mode = _mode(getattr(rollout_config, 'mode', MemoryRolloutMode.off))
        persisted = _rollout_state_from_data(uid=uid, data=payload)
        persisted_mode = _mode(persisted.mode)
        effective_mode = resolve_v3_effective_mode(configured_mode, persisted_mode)
        capabilities = decide_memory_rollout_capabilities(uid, effective_mode, persisted)
        default_memory_grant, archive_allowed = _consumer_grants(payload, consumer)
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
            schema_version=payload.get('schema_version'),
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
