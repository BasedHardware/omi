import inspect

from utils.memory.v17_v3_control_reader_contract import (
    V17V3ControlDecisionReason,
    V17V3ControlReaderRequest,
    V17V3ControlRouteFamily,
    V17V3ControlState,
    decide_v17_v3_control_route,
)


def _request(**overrides):
    values = {
        'uid': 'uid-a',
        'expected_account_generation': 7,
        'cursor_v17_read_requested': True,
        'cursor_secret_config_present': True,
        'archive_requested': False,
    }
    values.update(overrides)
    return V17V3ControlReaderRequest(**values)


def _control(**overrides):
    values = {
        'uid': 'uid-a',
        'cohort_enrolled': True,
        'default_memory_grant': True,
        'account_generation': 7,
        'control_generation': 7,
        'projection_ready': True,
        'write_convergence_ready': True,
        'archive_allowed': False,
        'short_term_freshness_default_visible': True,
    }
    values.update(overrides)
    return V17V3ControlState(**values)


def test_non_enrolled_allows_legacy_route_marker_only_and_leaves_offset_compatibility_outside_contract():
    decision = decide_v17_v3_control_route(
        _request(cursor_v17_read_requested=False, cursor_secret_config_present=False),
        _control(
            cohort_enrolled=False, default_memory_grant=False, projection_ready=False, write_convergence_ready=False
        ),
    )

    assert decision.route_family == V17V3ControlRouteFamily.LEGACY_PRIMARY
    assert decision.allowed is True
    assert decision.reason == V17V3ControlDecisionReason.NON_ENROLLED_LEGACY_ALLOWED
    assert decision.fallback_to_legacy_allowed is True
    assert decision.requires_legacy_reader is True
    assert decision.requires_projection_reader is False
    assert decision.archive_default_available is False
    assert decision.stale_short_term_default_visible is False
    assert decision.legacy_offset_behavior_preserved_outside_contract is True


def test_enrolled_all_gates_ready_allows_v17_projection_without_legacy_fallback():
    decision = decide_v17_v3_control_route(_request(), _control())

    assert decision.route_family == V17V3ControlRouteFamily.V17_PROJECTION
    assert decision.allowed is True
    assert decision.reason == V17V3ControlDecisionReason.V17_PROJECTION_ALLOWED
    assert decision.fallback_to_legacy_allowed is False
    assert decision.requires_projection_reader is True
    assert decision.requires_legacy_reader is False
    assert decision.archive_default_available is False
    assert decision.stale_short_term_default_visible is True


def test_missing_control_doc_fails_closed_without_legacy_fallback_for_unknown_gated_path():
    decision = decide_v17_v3_control_route(_request(), None)

    assert decision.route_family == V17V3ControlRouteFamily.FAIL_CLOSED
    assert decision.allowed is False
    assert decision.reason == V17V3ControlDecisionReason.MISSING_CONTROL_DOC
    assert decision.fallback_to_legacy_allowed is False
    assert decision.requires_projection_reader is False
    assert decision.requires_legacy_reader is False


def test_enrolled_fail_closed_reasons_never_fall_back_to_legacy():
    cases = [
        (_control(control_generation=6), V17V3ControlDecisionReason.STALE_GENERATION),
        (_control(default_memory_grant=False), V17V3ControlDecisionReason.NO_DEFAULT_MEMORY_GRANT),
        (_control(projection_ready=False), V17V3ControlDecisionReason.PROJECTION_NOT_READY),
        (_control(write_convergence_ready=False), V17V3ControlDecisionReason.WRITE_CONVERGENCE_NOT_READY),
        (
            _control(short_term_freshness_default_visible=False),
            V17V3ControlDecisionReason.STALE_SHORT_TERM_DEFAULT_HIDDEN,
        ),
    ]

    for control, reason in cases:
        decision = decide_v17_v3_control_route(_request(), control)

        assert decision.route_family == V17V3ControlRouteFamily.FAIL_CLOSED
        assert decision.allowed is False
        assert decision.reason == reason
        assert decision.fallback_to_legacy_allowed is False
        assert decision.requires_projection_reader is False
        assert decision.requires_legacy_reader is False
        assert decision.archive_default_available is False
        assert decision.stale_short_term_default_visible is False


def test_cursor_v17_reads_fail_closed_when_cursor_secret_config_is_missing_or_invalid():
    decision = decide_v17_v3_control_route(_request(cursor_secret_config_present=False), _control())

    assert decision.route_family == V17V3ControlRouteFamily.FAIL_CLOSED
    assert decision.allowed is False
    assert decision.reason == V17V3ControlDecisionReason.INVALID_OR_MISSING_CURSOR_SECRET
    assert decision.fallback_to_legacy_allowed is False
    assert decision.requires_projection_reader is False
    assert decision.requires_legacy_reader is False


def test_archive_request_fails_closed_and_archive_is_default_unavailable_when_not_allowed():
    decision = decide_v17_v3_control_route(_request(archive_requested=True), _control(archive_allowed=False))

    assert decision.route_family == V17V3ControlRouteFamily.FAIL_CLOSED
    assert decision.allowed is False
    assert decision.reason == V17V3ControlDecisionReason.ARCHIVE_NOT_ALLOWED
    assert decision.fallback_to_legacy_allowed is False
    assert decision.archive_default_available is False
    assert decision.requires_projection_reader is False


def test_control_reader_contract_is_pure_local_fake_injectable_and_has_stable_decision_fields():
    decision_fields = set(decide_v17_v3_control_route(_request(), _control()).__dataclass_fields__)
    assert {
        'route_family',
        'allowed',
        'reason',
        'fallback_to_legacy_allowed',
        'archive_default_available',
        'stale_short_term_default_visible',
        'requires_projection_reader',
        'requires_legacy_reader',
    }.issubset(decision_fields)

    source = inspect.getsource(__import__('utils.memory.v17_v3_control_reader_contract', fromlist=['']))
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
