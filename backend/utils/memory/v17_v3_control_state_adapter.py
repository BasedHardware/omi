"""Adapter from canonical V17 rollout state to the `/v3` control decision contract.

This module is pure/fake-injectable except for the caller-supplied Firestore-like
``db_client``. It does not import FastAPI routers, does not wire runtime routes,
and reads the existing canonical per-user path
``users/{uid}/memory_control/state`` exactly once for enrolled users.
"""

from __future__ import annotations

from config.v17_memory import V17Mode, V17RolloutState, decide_v17_capabilities
from database.v17_collections import V17Collections
from utils.memory.v17_default_read_rollout import (
    V17_DEFAULT_READ_ROLLOUT_SCHEMA_VERSION,
    V17ReadDecision,
    read_v17_global_read_gate,
    read_v17_rollout_state_doc,
    read_v17_write_convergence_gate,
)
from utils.memory.v17_v3_control_reader_contract import (
    V17V3ControlDecisionReason,
    V17V3ControlReadResult,
    V17V3ControlState,
)

V17_V3_DEFAULT_CONSUMER = 'omi_chat'
_MODE_RANK = {V17Mode.off: 0, V17Mode.shadow: 1, V17Mode.write: 2, V17Mode.read: 3}
_READ_ERROR_REASON_MAP = {
    'malformed_rollout_state': V17V3ControlDecisionReason.MALFORMED_CONTROL_DOC,
    'rollout_read_failed': V17V3ControlDecisionReason.CONTROL_READ_FAILED,
}


def _mode(value) -> V17Mode:
    return value if isinstance(value, V17Mode) else V17Mode(value)


def resolve_v17_v3_effective_mode(configured_mode, persisted_mode) -> V17Mode:
    """Return the lower-ranked mode; global config is a ceiling, not an elevator."""

    configured = _mode(configured_mode)
    persisted = _mode(persisted_mode)
    if _MODE_RANK[configured] <= _MODE_RANK[persisted]:
        return configured
    return persisted


def _read_error_reason(reason: str | None) -> V17V3ControlDecisionReason:
    return _READ_ERROR_REASON_MAP.get(str(reason or ''), V17V3ControlDecisionReason.CONTROL_READ_FAILED)


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
    return data.get('schema_version') != V17_DEFAULT_READ_ROLLOUT_SCHEMA_VERSION


def _rollout_state_from_data(*, uid: str, data: dict) -> V17RolloutState:
    return V17RolloutState(
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


def read_v17_v3_control(*, uid: str, db_client, rollout_config, consumer: str = V17_V3_DEFAULT_CONSUMER):
    """Read canonical V17 rollout state and derive the `/v3` control contract.

    Non-enrolled users are identified solely by rollout cohort membership and do
    not trigger a Firestore read. Enrolled users must have a persisted control doc;
    missing or unreadable state fails closed and is not reinterpreted as
    non-enrollment.
    """

    source_path = V17Collections(uid=uid).memory_control_state
    if uid not in getattr(rollout_config, 'enabled_users', set()):
        return V17V3ControlReadResult(cohort_enrolled=False, source_path=source_path)

    source_path, data, read_error = read_v17_rollout_state_doc(uid=uid, db_client=db_client)
    if read_error is not None:
        return V17V3ControlReadResult(
            cohort_enrolled=True,
            source_path=source_path,
            read_error_reason=_read_error_reason(read_error),
        )
    if data is None:
        return V17V3ControlReadResult(
            cohort_enrolled=True,
            source_path=source_path,
            read_error_reason=V17V3ControlDecisionReason.MISSING_CONTROL_DOC,
        )
    if not isinstance(data, dict):
        return V17V3ControlReadResult(
            cohort_enrolled=True,
            source_path=source_path,
            read_error_reason=V17V3ControlDecisionReason.MALFORMED_CONTROL_DOC,
        )
    if data.get('uid') != uid:
        try:
            state = V17V3ControlState(
                uid=str(data.get('uid')),
                schema_version=data.get('schema_version'),
                configured_mode=_mode(getattr(rollout_config, 'mode', V17Mode.off)),
                persisted_mode=_mode(data.get('mode', V17Mode.off.value)),
                effective_mode=V17Mode.off,
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
        return V17V3ControlReadResult(
            cohort_enrolled=True,
            source_path=source_path,
            state=state,
            read_error_reason=V17V3ControlDecisionReason.UID_MISMATCH,
        )
    if _missing_or_unsupported_schema(data):
        return V17V3ControlReadResult(
            cohort_enrolled=True,
            source_path=source_path,
            read_error_reason=V17V3ControlDecisionReason.UNSUPPORTED_CONTROL_SCHEMA,
        )

    try:
        configured_mode = _mode(getattr(rollout_config, 'mode', V17Mode.off))
        persisted = _rollout_state_from_data(uid=uid, data=data)
        persisted_mode = _mode(persisted.mode)
        effective_mode = resolve_v17_v3_effective_mode(configured_mode, persisted_mode)
        capabilities = decide_v17_capabilities(uid, effective_mode, persisted)
        default_memory_grant, archive_allowed = _consumer_grants(data, consumer)
    except (TypeError, ValueError, AttributeError):
        return V17V3ControlReadResult(
            cohort_enrolled=True,
            source_path=source_path,
            read_error_reason=V17V3ControlDecisionReason.MALFORMED_CONTROL_DOC,
        )

    global_read_gate_open = False
    write_convergence_ready = False
    if effective_mode == V17Mode.read:
        global_gate = read_v17_global_read_gate(db_client=db_client)
        write_gate = read_v17_write_convergence_gate(db_client=db_client)
        global_read_gate_open = global_gate.read_decision == V17ReadDecision.USE_V17
        write_convergence_ready = write_gate.ready

    return V17V3ControlReadResult(
        cohort_enrolled=True,
        source_path=source_path,
        state=V17V3ControlState(
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
            rollout_write_ready=capabilities.v17_writes_enabled,
            projection_ready=capabilities.v17_reads_enabled,
            global_read_gate_open=global_read_gate_open,
            write_convergence_ready=write_convergence_ready,
        ),
    )
