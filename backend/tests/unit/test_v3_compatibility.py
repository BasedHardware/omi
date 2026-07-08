import inspect

from utils.memory.v3_compatibility import (
    V3CompatibilityContext,
    V3CompatibilityDecision,
    V3CompatibilityReadPath,
    decide_v3_compatibility,
    describe_v3_cursor_mode,
)


def test_non_enrolled_v3_call_remains_legacy_primary_and_safe_without_memory_cutover():
    decision = decide_v3_compatibility(V3CompatibilityContext(uid='u1', enrolled=False, control_state='missing'))

    assert decision.read_path == V3CompatibilityReadPath.LEGACY_PRIMARY
    assert decision.http_status == 200
    assert decision.body_contract == 'List[MemoryDB]'
    assert decision.legacy_primary_allowed is True
    assert decision.legacy_fallback_allowed is False
    assert decision.headers == {
        'X-Omi-Memory-Read-Source': 'legacy_primary',
        'X-Omi-Memory-Read-Decision': 'non_enrolled_legacy_primary',
    }


def test_enrolled_missing_malformed_uid_mismatch_unsupported_or_timeout_fail_closed_without_legacy_fallback():
    for state in ['missing', 'malformed', 'uid_mismatch', 'unsupported_schema', 'control_timeout']:
        decision = decide_v3_compatibility(V3CompatibilityContext(uid='u1', enrolled=True, control_state=state))

        assert decision.read_path == V3CompatibilityReadPath.FAIL_CLOSED
        assert decision.http_status == 503
        assert decision.legacy_primary_allowed is False
        assert decision.legacy_fallback_allowed is False
        assert decision.reason == f'enrolled_{state}_fail_closed'
        assert decision.headers['X-Omi-Memory-Read-Source'] == 'none'
        assert decision.headers['X-Omi-Memory-Read-Decision'] == decision.reason


def test_enrolled_no_default_memory_grant_defaults_to_product_overridable_403_privacy_deny():
    decision = decide_v3_compatibility(
        V3CompatibilityContext(uid='u1', enrolled=True, control_state='valid', default_memory_grant=False)
    )

    assert decision.read_path == V3CompatibilityReadPath.DENY
    assert decision.http_status == 403
    assert decision.reason == 'no_default_memory_grant_privacy_consent_deny'
    assert decision.product_overridable is True
    assert decision.legacy_primary_allowed is False
    assert decision.legacy_fallback_allowed is False


def test_enrolled_enabled_empty_and_projection_empty_returns_memory_empty_list_without_legacy_fallback():
    decision = decide_v3_compatibility(
        V3CompatibilityContext(
            uid='u1',
            enrolled=True,
            control_state='valid',
            default_memory_grant=True,
            write_convergence_ready=True,
            projection_ready=True,
            projection_empty=True,
        )
    )

    assert decision.read_path == V3CompatibilityReadPath.MEMORY_COMPATIBILITY_PROJECTION
    assert decision.http_status == 200
    assert decision.response_body_override == []
    assert decision.reason == 'memory_projection_empty_no_legacy_fallback'
    assert decision.legacy_primary_allowed is False
    assert decision.legacy_fallback_allowed is False
    assert decision.headers == {
        'X-Omi-Memory-Read-Source': 'memory_compatibility_projection',
        'X-Omi-Memory-Read-Decision': 'memory_projection_empty_no_legacy_fallback',
    }


def test_projection_or_write_convergence_not_ready_fails_closed_before_memory_read_cutover():
    not_ready_cases = [
        V3CompatibilityContext(
            uid='u1',
            enrolled=True,
            control_state='valid',
            default_memory_grant=True,
            write_convergence_ready=False,
            projection_ready=True,
        ),
        V3CompatibilityContext(
            uid='u1',
            enrolled=True,
            control_state='valid',
            default_memory_grant=True,
            write_convergence_ready=True,
            projection_ready=False,
        ),
    ]

    for context in not_ready_cases:
        decision = decide_v3_compatibility(context)

        assert decision.read_path == V3CompatibilityReadPath.FAIL_CLOSED
        assert decision.http_status == 503
        assert decision.reason in {'write_convergence_not_ready', 'memory_projection_not_ready'}
        assert decision.legacy_fallback_allowed is False


def test_archive_is_default_unavailable_and_response_metadata_is_header_only_additive():
    decision = decide_v3_compatibility(
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

    assert decision.read_path == V3CompatibilityReadPath.DENY
    assert decision.http_status == 404
    assert decision.reason == 'archive_default_unavailable'
    assert decision.archive_available is False
    assert decision.body_contract == 'List[MemoryDB]'
    assert decision.metadata_location == 'headers'
    assert 'source' not in decision.body_additions
    assert 'read_decision' not in decision.body_additions


def test_cursor_mode_is_signed_opaque_keyset_generation_bound_and_never_uses_offset_or_5000_override():
    cursor = describe_v3_cursor_mode()

    assert cursor.enabled_mode == 'additive_memory_cursor'
    assert cursor.opaque is True
    assert cursor.signed is True
    assert cursor.keyset_fields == ('created_at_desc', 'memory_id_desc')
    assert cursor.generation_bound is True
    assert cursor.projection_bound is True
    assert cursor.allows_offset is False
    assert cursor.applies_first_page_5000_override is False


def test_decision_service_api_does_not_expose_unsafe_fallback_after_enrolled_error_or_memory_write_states():
    decision_fields = set(V3CompatibilityDecision.__dataclass_fields__)
    assert 'fallback_to_legacy' not in decision_fields
    assert 'use_legacy_on_error' not in decision_fields

    source = inspect.getsource(decide_v3_compatibility)
    assert 'fallback_to_legacy' not in source
    assert 'use_legacy_on_error' not in source
    assert 'legacy_fallback_allowed=True' not in source

    for state in ['malformed', 'missing', 'control_timeout']:
        decision = decide_v3_compatibility(V3CompatibilityContext(uid='u1', enrolled=True, control_state=state))
        assert decision.legacy_primary_allowed is False
        assert decision.legacy_fallback_allowed is False

    memory_write_not_converged = decide_v3_compatibility(
        V3CompatibilityContext(
            uid='u1',
            enrolled=True,
            control_state='valid',
            default_memory_grant=True,
            write_convergence_ready=False,
            projection_ready=True,
        )
    )
    assert memory_write_not_converged.legacy_fallback_allowed is False
