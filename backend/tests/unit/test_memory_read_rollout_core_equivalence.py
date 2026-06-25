"""Equivalence tests for shared memory read rollout decision core."""

from config.memory_rollout import MemoryRolloutMode, PASSED, MemoryRolloutStageGate
from utils.memory.default_read_rollout import (
    DEFAULT_READ_ROLLOUT_SCHEMA_VERSION,
    MemoryReadDecision,
    normalize_default_read_rollout_decision,
    normalize_global_read_gate,
)
from utils.memory.memory_read_rollout_core import (
    MemoryReadGateBlock,
    extract_consumer_grants,
    surface_rollout_allows_memory_read,
    v3_rollout_allows_memory_read,
)
from utils.memory.v3_compatibility import V3CompatibilityContext, V3CompatibilityReadPath, decide_v3_compatibility
from utils.memory.v3_control_reader_contract import (
    V3ControlDecisionReason,
    V3ControlReadResult,
    V3ControlReaderRequest,
    V3ControlRouteFamily,
    V3ControlState,
    decide_v3_control_route,
)


def _enabled_rollout_doc(*, uid='u1', consumer='omi_chat', grant=True, archive=False):
    return {
        'schema_version': DEFAULT_READ_ROLLOUT_SCHEMA_VERSION,
        'uid': uid,
        'mode': MemoryRolloutMode.read.value,
        'mode_epoch': 1,
        'cutover_epoch': 1,
        'account_generation': 7,
        'fallback_projection_ready': True,
        'persistent_memory_writes_started': True,
        'writes_blocked': False,
        'stage_gates': {
            MemoryRolloutStageGate.shadow.value: PASSED,
            MemoryRolloutStageGate.write.value: PASSED,
            MemoryRolloutStageGate.read.value: PASSED,
        },
        'grants': {consumer: {'default_memory': grant, 'archive': archive}},
    }


def test_extract_consumer_grants_matches_default_read_rollout_normalization():
    doc = _enabled_rollout_doc(consumer='mcp', grant=True, archive=True)
    snapshot = extract_consumer_grants(doc, 'mcp')
    rollout = normalize_default_read_rollout_decision(
        uid='u1',
        source_path='users/u1/memory_control/state',
        consumer='mcp',
        data=doc,
    )

    assert snapshot.default_memory is True
    assert snapshot.archive_capability is True
    assert rollout.app_has_default_memory_grant is True


def test_surface_and_v3_shared_gates_agree_when_convergence_ready():
    global_gate = normalize_global_read_gate({'memory_reads_enabled': True, 'kill_switch_active': False})
    doc = _enabled_rollout_doc(consumer='omi_chat', grant=True)
    rollout = normalize_default_read_rollout_decision(
        uid='u1',
        source_path='users/u1/memory_control/state',
        consumer='omi_chat',
        data=doc,
    )

    surface = surface_rollout_allows_memory_read(
        global_read_gate_open=global_gate.read_decision == MemoryReadDecision.USE_MEMORY,
        default_memory_grant=rollout.app_has_default_memory_grant,
        memory_reads_enabled=rollout.rollout_capabilities.memory_reads_enabled,
    )
    v3 = v3_rollout_allows_memory_read(
        global_read_gate_open=True,
        default_memory_grant=rollout.app_has_default_memory_grant,
        memory_reads_enabled=rollout.rollout_capabilities.memory_reads_enabled,
        write_convergence_ready=True,
        rollout_write_ready=rollout.rollout_capabilities.memory_writes_enabled,
    )

    assert surface.blocked is False
    assert v3.blocked is False
    assert rollout.read_decision == MemoryReadDecision.USE_MEMORY


def test_surface_allows_memory_read_without_write_convergence_but_v3_blocks():
    global_gate = normalize_global_read_gate({'memory_reads_enabled': True, 'kill_switch_active': False})
    doc = _enabled_rollout_doc(consumer='omi_chat', grant=True)
    rollout = normalize_default_read_rollout_decision(
        uid='u1',
        source_path='users/u1/memory_control/state',
        consumer='omi_chat',
        data=doc,
    )

    surface = surface_rollout_allows_memory_read(
        global_read_gate_open=global_gate.read_decision == MemoryReadDecision.USE_MEMORY,
        default_memory_grant=rollout.app_has_default_memory_grant,
        memory_reads_enabled=rollout.rollout_capabilities.memory_reads_enabled,
    )
    v3 = v3_rollout_allows_memory_read(
        global_read_gate_open=True,
        default_memory_grant=rollout.app_has_default_memory_grant,
        memory_reads_enabled=rollout.rollout_capabilities.memory_reads_enabled,
        write_convergence_ready=False,
        rollout_write_ready=rollout.rollout_capabilities.memory_writes_enabled,
    )

    assert surface.blocked is False
    assert v3.blocked is True
    assert v3.block == MemoryReadGateBlock.WRITE_CONVERGENCE_NOT_READY


def test_v3_control_route_and_compatibility_share_write_convergence_block_reason():
    control = V3ControlState(
        uid='u1',
        schema_version=1,
        configured_mode=MemoryRolloutMode.read,
        persisted_mode=MemoryRolloutMode.read,
        effective_mode=MemoryRolloutMode.read,
        mode_epoch=1,
        cutover_epoch=1,
        account_generation=7,
        default_memory_grant=True,
        archive_allowed=False,
        rollout_write_ready=True,
        projection_ready=True,
        global_read_gate_open=True,
        write_convergence_ready=False,
    )
    route = decide_v3_control_route(
        V3ControlReaderRequest('u1', 7, False, True),
        V3ControlReadResult(cohort_enrolled=True, source_path='users/u1/memory_control/state', state=control),
    )
    compat = decide_v3_compatibility(
        V3CompatibilityContext(
            uid='u1',
            enrolled=True,
            control_state='valid',
            default_memory_grant=True,
            write_convergence_ready=False,
            projection_ready=True,
        )
    )

    assert route.route_family == V3ControlRouteFamily.FAIL_CLOSED
    assert route.reason == V3ControlDecisionReason.WRITE_CONVERGENCE_NOT_READY
    assert compat.read_path == V3CompatibilityReadPath.FAIL_CLOSED
    assert compat.reason == 'write_convergence_not_ready'
