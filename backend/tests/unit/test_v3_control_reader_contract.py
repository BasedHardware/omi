import inspect

from config.memory_rollout import MemoryRolloutMode
from utils.memory.v3.control_reader_contract import (
    V3ControlDecisionReason,
    V3ControlReadResult,
    V3ControlReaderRequest,
    V3ControlRouteFamily,
    V3ControlState,
    decide_v3_control_route,
)


def _request(**overrides):
    values = {
        'uid': 'uid-a',
        'expected_account_generation': 7,
        'cursor_memory_read_requested': True,
        'cursor_secret_config_present': True,
        'archive_requested': False,
    }
    values.update(overrides)
    return V3ControlReaderRequest(**values)


def _state(**overrides):
    values = {
        'uid': 'uid-a',
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


def _result(**overrides):
    values = {
        'cohort_enrolled': True,
        'source_path': 'users/uid-a/memory_control/state',
        'state': _state(),
        'read_error_reason': None,
    }
    values.update(overrides)
    return V3ControlReadResult(**values)


def test_non_enrolled_allows_legacy_route_marker_only_and_leaves_offset_compatibility_outside_contract():
    decision = decide_v3_control_route(
        _request(cursor_memory_read_requested=False, cursor_secret_config_present=False),
        _result(cohort_enrolled=False, state=None),
    )

    assert decision.route_family == V3ControlRouteFamily.LEGACY_PRIMARY
    assert decision.allowed is True
    assert decision.reason == V3ControlDecisionReason.NON_ENROLLED_LEGACY_ALLOWED
    assert decision.fallback_to_legacy_allowed is True
    assert decision.requires_legacy_reader is True
    assert decision.requires_projection_reader is False
    assert decision.archive_default_available is False
    assert decision.legacy_offset_behavior_preserved_outside_contract is True


def test_enrolled_all_gates_ready_allows_memory_projection_without_legacy_fallback():
    decision = decide_v3_control_route(_request(), _result())

    assert decision.route_family == V3ControlRouteFamily.MEMORY_PROJECTION
    assert decision.allowed is True
    assert decision.reason == V3ControlDecisionReason.MEMORY_PROJECTION_ALLOWED
    assert decision.fallback_to_legacy_allowed is False
    assert decision.requires_projection_reader is True
    assert decision.requires_legacy_reader is False
    assert decision.archive_default_available is False


def test_enrolled_missing_control_doc_fails_closed_without_legacy_fallback():
    decision = decide_v3_control_route(_request(), _result(state=None))

    assert decision.route_family == V3ControlRouteFamily.FAIL_CLOSED
    assert decision.allowed is False
    assert decision.reason == V3ControlDecisionReason.MISSING_CONTROL_DOC
    assert decision.fallback_to_legacy_allowed is False
    assert decision.requires_projection_reader is False
    assert decision.requires_legacy_reader is False


def test_enrolled_read_errors_map_to_typed_fail_closed_reasons():
    for reason in (
        V3ControlDecisionReason.CONTROL_READ_FAILED,
        V3ControlDecisionReason.MALFORMED_CONTROL_DOC,
        V3ControlDecisionReason.UNSUPPORTED_CONTROL_SCHEMA,
    ):
        decision = decide_v3_control_route(_request(), _result(state=None, read_error_reason=reason))
        assert decision.route_family == V3ControlRouteFamily.FAIL_CLOSED
        assert decision.reason == reason
        assert decision.fallback_to_legacy_allowed is False


def test_uid_mismatch_fails_closed_before_mode_or_grant_checks():
    decision = decide_v3_control_route(
        _request(uid='uid-a'),
        _result(state=_state(uid='uid-b', effective_mode=MemoryRolloutMode.off, default_memory_grant=False)),
    )

    assert decision.route_family == V3ControlRouteFamily.FAIL_CLOSED
    assert decision.reason == V3ControlDecisionReason.UID_MISMATCH
    assert decision.fallback_to_legacy_allowed is False


def test_enrolled_off_shadow_write_are_legacy_authoritative_not_fallback():
    for mode in (MemoryRolloutMode.off, MemoryRolloutMode.shadow, MemoryRolloutMode.write):
        decision = decide_v3_control_route(_request(), _result(state=_state(effective_mode=mode)))
        assert decision.route_family == V3ControlRouteFamily.LEGACY_PRIMARY
        assert decision.allowed is True
        assert decision.reason == V3ControlDecisionReason.ROLLOUT_LEGACY_AUTHORITATIVE
        assert decision.fallback_to_legacy_allowed is False
        assert decision.requires_legacy_reader is True


def test_account_generation_only_expected_generation_comparison():
    control = _state(mode_epoch=1, cutover_epoch=1, account_generation=50)
    decision = decide_v3_control_route(_request(expected_account_generation=50), _result(state=control))

    assert decision.route_family == V3ControlRouteFamily.MEMORY_PROJECTION
    assert decision.allowed is True


def test_enrolled_read_fail_closed_reasons_never_fall_back_to_legacy():
    cases = [
        (_state(account_generation=6), V3ControlDecisionReason.STALE_GENERATION, 503),
        (_state(global_read_gate_open=False), V3ControlDecisionReason.GLOBAL_READ_GATE_CLOSED, 503),
        (_state(default_memory_grant=False), V3ControlDecisionReason.NO_DEFAULT_MEMORY_GRANT, 403),
        (_state(rollout_write_ready=False), V3ControlDecisionReason.WRITE_CONVERGENCE_NOT_READY, 503),
        (_state(write_convergence_ready=False), V3ControlDecisionReason.WRITE_CONVERGENCE_NOT_READY, 503),
        (_state(projection_ready=False), V3ControlDecisionReason.PROJECTION_NOT_READY, 503),
    ]

    for control, reason, status in cases:
        decision = decide_v3_control_route(_request(), _result(state=control))

        assert decision.route_family == V3ControlRouteFamily.FAIL_CLOSED
        assert decision.allowed is False
        assert decision.reason == reason
        assert decision.http_status == status
        assert decision.fallback_to_legacy_allowed is False
        assert decision.requires_projection_reader is False
        assert decision.requires_legacy_reader is False
        assert decision.archive_default_available is False


def test_cursor_memory_reads_fail_closed_when_cursor_secret_config_is_missing_or_invalid():
    decision = decide_v3_control_route(_request(cursor_secret_config_present=False), _result())

    assert decision.route_family == V3ControlRouteFamily.FAIL_CLOSED
    assert decision.allowed is False
    assert decision.reason == V3ControlDecisionReason.INVALID_OR_MISSING_CURSOR_SECRET
    assert decision.fallback_to_legacy_allowed is False


def test_archive_request_fails_closed_403_and_archive_is_default_unavailable_when_not_allowed():
    decision = decide_v3_control_route(_request(archive_requested=True), _result(state=_state(archive_allowed=False)))

    assert decision.route_family == V3ControlRouteFamily.FAIL_CLOSED
    assert decision.allowed is False
    assert decision.http_status == 403
    assert decision.reason == V3ControlDecisionReason.ARCHIVE_NOT_ALLOWED
    assert decision.fallback_to_legacy_allowed is False
    assert decision.archive_default_available is False


def test_stale_short_term_is_absent_from_control_matrix():
    state_fields = set(V3ControlState.__dataclass_fields__)
    decision_fields = set(decide_v3_control_route(_request(), _result()).__dataclass_fields__)

    assert 'short_term_freshness_default_visible' not in state_fields
    assert 'stale_short_term_default_visible' not in state_fields
    assert 'stale_short_term_default_visible' not in decision_fields
    assert not any('SHORT_TERM' in item.name for item in V3ControlDecisionReason)


def test_control_reader_contract_is_pure_local_fake_injectable_and_has_stable_decision_fields():
    decision_fields = set(decide_v3_control_route(_request(), _result()).__dataclass_fields__)
    assert {
        'route_family',
        'allowed',
        'reason',
        'fallback_to_legacy_allowed',
        'archive_default_available',
        'requires_projection_reader',
        'requires_legacy_reader',
    }.issubset(decision_fields)

    source = inspect.getsource(__import__('utils.memory.v3.control_reader_contract', fromlist=['']))
    forbidden = [
        'routers.memories',
        'database.',
        'firebase',
        'firestore',
        'pinecone',
        'requests.',
        'httpx.',
        'FastAPI',
    ]
    for token in forbidden:
        assert token not in source
