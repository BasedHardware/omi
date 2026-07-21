"""Equivalence tests for shared memory read rollout decision core."""

import utils.memory.v3.compatibility as v3_compatibility
import utils.memory.v3.control_reader_contract as v3_control_reader_contract
from config.memory_rollout import MemoryRolloutMode, PASSED, MemoryRolloutStageGate
from utils.memory.default_read_rollout import (
    DEFAULT_READ_ROLLOUT_SCHEMA_VERSION,
    MemoryReadDecision,
    normalize_default_read_rollout_decision,
    normalize_global_read_gate,
)
from utils.memory.memory_read_rollout_core import (
    EnrolledMemoryReadGateResult,
    MemoryReadGateBlock,
    extract_consumer_grants,
    surface_rollout_allows_memory_read,
    v3_rollout_allows_memory_read,
)
from utils.memory.product_authorization import (
    ProductAuthorizationContext,
    authorize_memory_product_memory_route,
)
from utils.memory.v3.compatibility import V3CompatibilityContext, V3CompatibilityReadPath, decide_v3_compatibility
from utils.memory.v3.control_reader_contract import (
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


def _control_state(**overrides):
    values = {
        'uid': 'u1',
        'schema_version': 1,
        'configured_mode': MemoryRolloutMode.read,
        'persisted_mode': MemoryRolloutMode.read,
        'effective_mode': MemoryRolloutMode.read,
        'mode_epoch': 1,
        'cutover_epoch': 1,
        'account_generation': 7,
        'default_memory_grant': True,
        'archive_allowed': False,
        'rollout_write_ready': True,
        'projection_ready': True,
        'global_read_gate_open': True,
        'write_convergence_ready': True,
    }
    values.update(overrides)
    return V3ControlState(**values)


def _control_route(state, *, archive_requested=False):
    return decide_v3_control_route(
        V3ControlReaderRequest('u1', 7, False, True, archive_requested),
        V3ControlReadResult(cohort_enrolled=True, source_path='users/u1/memory_control/state', state=state),
    )


def test_global_read_gate_closed_blocks_shared_core_and_v3_control():
    gate = v3_rollout_allows_memory_read(
        global_read_gate_open=False,
        default_memory_grant=True,
        memory_reads_enabled=True,
        write_convergence_ready=True,
        rollout_write_ready=True,
    )
    assert gate.blocked is True
    assert gate.block == MemoryReadGateBlock.GLOBAL_READ_GATE_CLOSED

    route = _control_route(_control_state(global_read_gate_open=False))
    assert route.route_family == V3ControlRouteFamily.FAIL_CLOSED
    assert route.reason == V3ControlDecisionReason.GLOBAL_READ_GATE_CLOSED
    assert route.http_status == 503


def test_grant_denied_blocks_surface_v3_and_compatibility_with_distinct_statuses():
    for grant in (False, None):
        surface = surface_rollout_allows_memory_read(
            global_read_gate_open=True,
            default_memory_grant=bool(grant) if grant is not None else False,
            memory_reads_enabled=True,
        )
        v3 = v3_rollout_allows_memory_read(
            global_read_gate_open=True,
            default_memory_grant=grant,
            memory_reads_enabled=True,
            write_convergence_ready=True,
            rollout_write_ready=True,
        )
        assert surface.blocked is True
        assert surface.block == MemoryReadGateBlock.NO_DEFAULT_MEMORY_GRANT
        assert v3.blocked is True
        assert v3.block == MemoryReadGateBlock.NO_DEFAULT_MEMORY_GRANT

    route = _control_route(_control_state(default_memory_grant=False))
    assert route.route_family == V3ControlRouteFamily.FAIL_CLOSED
    assert route.reason == V3ControlDecisionReason.NO_DEFAULT_MEMORY_GRANT
    assert route.http_status == 403

    compat = decide_v3_compatibility(
        V3CompatibilityContext(uid='u1', enrolled=True, control_state='valid', default_memory_grant=False)
    )
    assert compat.read_path == V3CompatibilityReadPath.DENY
    assert compat.http_status == 403
    assert compat.reason == 'no_default_memory_grant_privacy_consent_deny'


def test_projection_not_ready_blocks_surface_v3_control_and_compatibility():
    surface = surface_rollout_allows_memory_read(
        global_read_gate_open=True,
        default_memory_grant=True,
        memory_reads_enabled=False,
    )
    v3 = v3_rollout_allows_memory_read(
        global_read_gate_open=True,
        default_memory_grant=True,
        memory_reads_enabled=False,
        write_convergence_ready=True,
        rollout_write_ready=True,
    )
    assert surface.block == MemoryReadGateBlock.PROJECTION_NOT_READY
    assert v3.block == MemoryReadGateBlock.PROJECTION_NOT_READY

    route = _control_route(_control_state(projection_ready=False))
    assert route.route_family == V3ControlRouteFamily.FAIL_CLOSED
    assert route.reason == V3ControlDecisionReason.PROJECTION_NOT_READY

    compat = decide_v3_compatibility(
        V3CompatibilityContext(
            uid='u1',
            enrolled=True,
            control_state='valid',
            default_memory_grant=True,
            write_convergence_ready=True,
            projection_ready=False,
        )
    )
    assert compat.read_path == V3CompatibilityReadPath.FAIL_CLOSED
    assert compat.reason == 'memory_projection_not_ready'


def test_rollout_write_not_ready_blocks_v3_control_but_compatibility_handles_distinctly():
    # /v3 control couples rollout-write-readiness into write convergence.
    route = _control_route(_control_state(rollout_write_ready=False, write_convergence_ready=True))
    assert route.route_family == V3ControlRouteFamily.FAIL_CLOSED
    assert route.reason == V3ControlDecisionReason.WRITE_CONVERGENCE_NOT_READY

    # Compatibility only models the durable write-convergence bit (not the rollout
    # write phase), so write_convergence_ready=True clears its convergence gate and
    # it proceeds to a memory projection decision.
    compat = decide_v3_compatibility(
        V3CompatibilityContext(
            uid='u1',
            enrolled=True,
            control_state='valid',
            default_memory_grant=True,
            write_convergence_ready=True,
            projection_ready=True,
        )
    )
    assert compat.read_path == V3CompatibilityReadPath.MEMORY_COMPATIBILITY_PROJECTION
    assert compat.http_status == 200


def test_archive_semantics_differ_404_compatibility_vs_403_control():
    compat = decide_v3_compatibility(
        V3CompatibilityContext(
            uid='u1',
            enrolled=True,
            control_state='valid',
            default_memory_grant=True,
            write_convergence_ready=True,
            projection_ready=True,
            requested_archive=True,
        )
    )
    assert compat.read_path == V3CompatibilityReadPath.DENY
    assert compat.http_status == 404
    assert compat.reason == 'archive_default_unavailable'

    route = _control_route(_control_state(archive_allowed=False), archive_requested=True)
    assert route.route_family == V3ControlRouteFamily.FAIL_CLOSED
    assert route.reason == V3ControlDecisionReason.ARCHIVE_NOT_ALLOWED
    assert route.http_status == 403


def _use_memory_global_gate(**_kwargs):
    return normalize_global_read_gate({'memory_reads_enabled': True, 'kill_switch_active': False})


def _surface_rollout_reader_factory(doc):
    def _reader(*, uid, db_client, consumer):
        return normalize_default_read_rollout_decision(
            uid=uid,
            source_path='users/u1/memory_control/state',
            consumer=consumer,
            data=doc,
        )

    return _reader


def test_authorize_surface_route_uses_shared_gate_and_does_not_require_write_convergence():
    # Enabled rollout, grant present, NO write-convergence input anywhere: surface
    # must still allow because surface reads do not require write convergence.
    reader = _surface_rollout_reader_factory(_enabled_rollout_doc(consumer='omi_chat', grant=True))
    context = ProductAuthorizationContext(uid='u1', consumer='omi_chat', surface='omi_chat')

    decision = authorize_memory_product_memory_route(
        context,
        db_client=None,
        read_global_gate=_use_memory_global_gate,
        read_default_rollout=reader,
        read_archive_rollout=reader,
    )

    assert decision.allowed is True
    assert decision.read_decision == MemoryReadDecision.USE_MEMORY


def test_authorize_surface_route_denies_when_shared_gate_blocks_on_disabled_reads():
    # mode off => memory_reads disabled => shared gate blocks => surface denies with
    # the existing reason string, proving the shared evaluator participates.
    disabled_doc = {
        'schema_version': DEFAULT_READ_ROLLOUT_SCHEMA_VERSION,
        'uid': 'u1',
        'mode': MemoryRolloutMode.off.value,
        'grants': {'omi_chat': {'default_memory': True}},
    }
    reader = _surface_rollout_reader_factory(disabled_doc)
    context = ProductAuthorizationContext(uid='u1', consumer='omi_chat', surface='omi_chat')

    decision = authorize_memory_product_memory_route(
        context,
        db_client=None,
        read_global_gate=_use_memory_global_gate,
        read_default_rollout=reader,
        read_archive_rollout=reader,
    )

    assert decision.allowed is False
    assert decision.read_decision == MemoryReadDecision.DENY_MEMORY
    assert decision.reason == 'memory_reads_disabled'


def test_v3_compatibility_unmapped_gate_block_fails_closed(monkeypatch):
    def _blocked(*_args, **_kwargs):
        return EnrolledMemoryReadGateResult(blocked=True, block=MemoryReadGateBlock.NO_DEFAULT_MEMORY_GRANT)

    monkeypatch.setattr(v3_compatibility, 'evaluate_enrolled_memory_read_gates', _blocked)
    compat = decide_v3_compatibility(
        V3CompatibilityContext(
            uid='u1',
            enrolled=True,
            control_state='valid',
            default_memory_grant=True,
            write_convergence_ready=True,
            projection_ready=True,
        )
    )
    assert compat.read_path == V3CompatibilityReadPath.FAIL_CLOSED
    assert compat.http_status == 503
    assert compat.reason == 'enrolled_read_gate_blocked_fail_closed'


def test_v3_control_route_unmapped_gate_block_fails_closed(monkeypatch):
    def _blocked(**_kwargs):
        return EnrolledMemoryReadGateResult(blocked=True, block=MemoryReadGateBlock.NONE)

    monkeypatch.setattr(v3_control_reader_contract, 'v3_rollout_allows_memory_read', _blocked)
    route = _control_route(_control_state())
    assert route.route_family == V3ControlRouteFamily.FAIL_CLOSED
    assert route.reason == V3ControlDecisionReason.ENROLLED_READ_GATE_BLOCKED
    assert route.http_status == 503
