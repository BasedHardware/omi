import inspect

from utils.memory.v3_projection_readiness import (
    V3ProjectionReadinessContext,
    V3ProjectionReadinessDecision,
    V3ProjectionReadinessState,
    decide_v3_projection_readiness,
)


def _ready_context(**overrides):
    values = {
        'uid': 'uid-a',
        'expected_account_generation': 7,
        'account_generation': 7,
        'projection_generation': 7,
        'create_converged': True,
        'update_converged': True,
        'delete_converged': True,
        'projection_source': 'memory_derived_compatibility_projection',
        'tombstone_fence_present': True,
        'tombstone_fence_generation': 7,
        'source_commit_id': 'source-commit-7',
        'source_version': 'source-version-7',
        'projection_commit_id': 'projection-commit-7',
        'projection_version': 'projection-version-7',
        'freshness_fence_present': True,
        'freshness_fence_generation': 7,
        'projection_empty': False,
    }
    values.update(overrides)
    return V3ProjectionReadinessContext(**values)


def test_ready_memory_derived_projection_allows_v3_read_cutover_with_no_legacy_fallback():
    decision = decide_v3_projection_readiness(_ready_context())

    assert decision.state == V3ProjectionReadinessState.READY
    assert decision.read_cutover_allowed is True
    assert decision.can_return_enabled_empty_list is False
    assert decision.http_status == 200
    assert decision.reason == 'memory_derived_projection_ready'
    assert decision.source == 'memory_derived_compatibility_projection'
    assert decision.legacy_fallback_allowed is False
    assert decision.archive_default_available is False
    assert decision.stale_short_term_default_visible is False
    assert decision.required_account_generation == 7
    assert decision.projection_generation == 7
    assert decision.headers == {
        'X-Omi-Memory-Projection-Readiness': 'ready',
        'X-Omi-Memory-Projection-Source': 'memory_derived_compatibility_projection',
    }


def test_external_write_convergence_for_create_update_delete_is_required_before_memory_reads():
    cases = [
        ('create_converged', 'external_create_convergence_not_ready'),
        ('update_converged', 'external_update_convergence_not_ready'),
        ('delete_converged', 'external_delete_convergence_not_ready'),
    ]

    for field, reason in cases:
        decision = decide_v3_projection_readiness(_ready_context(**{field: False}))

        assert decision.state == V3ProjectionReadinessState.BLOCKED
        assert decision.read_cutover_allowed is False
        assert decision.http_status == 503
        assert decision.reason == reason
        assert decision.legacy_fallback_allowed is False


def test_projection_generation_and_account_generation_must_be_present_current_and_consistent():
    cases = [
        ({'expected_account_generation': None}, 'expected_account_generation_missing'),
        ({'account_generation': None}, 'account_generation_missing'),
        ({'account_generation': 6}, 'account_generation_mismatch'),
        ({'projection_generation': None}, 'projection_generation_missing'),
        ({'projection_generation': 6}, 'projection_generation_stale'),
    ]

    for overrides, reason in cases:
        decision = decide_v3_projection_readiness(_ready_context(**overrides))

        assert decision.state == V3ProjectionReadinessState.BLOCKED
        assert decision.read_cutover_allowed is False
        assert decision.reason == reason
        assert decision.legacy_fallback_allowed is False


def test_projection_source_must_be_memory_derived_not_ad_hoc_mapping_or_legacy_direct_read():
    for source in [None, 'memory_items_ad_hoc_mapping', 'legacy_direct_read', 'users_memories_legacy_projection']:
        decision = decide_v3_projection_readiness(_ready_context(projection_source=source))

        assert decision.state == V3ProjectionReadinessState.BLOCKED
        assert decision.read_cutover_allowed is False
        assert decision.reason == 'projection_source_not_memory_derived'
        assert decision.source == source


def test_tombstone_delete_fence_must_be_present_and_current_before_delete_success_or_read_cutover():
    cases = [
        ({'tombstone_fence_present': False}, 'tombstone_fence_missing'),
        ({'tombstone_fence_generation': None}, 'tombstone_fence_generation_missing'),
        ({'tombstone_fence_generation': 6}, 'tombstone_fence_stale'),
    ]

    for overrides, reason in cases:
        decision = decide_v3_projection_readiness(_ready_context(**overrides))

        assert decision.state == V3ProjectionReadinessState.BLOCKED
        assert decision.read_cutover_allowed is False
        assert decision.reason == reason
        assert decision.legacy_fallback_allowed is False


def test_source_projection_commit_version_and_freshness_fences_are_mandatory():
    cases = [
        ({'source_commit_id': None}, 'source_commit_id_missing'),
        ({'source_version': None}, 'source_version_missing'),
        ({'projection_commit_id': None}, 'projection_commit_id_missing'),
        ({'projection_version': None}, 'projection_version_missing'),
        ({'freshness_fence_present': False}, 'freshness_fence_missing'),
        ({'freshness_fence_generation': None}, 'freshness_fence_generation_missing'),
        ({'freshness_fence_generation': 6}, 'freshness_fence_stale'),
    ]

    for overrides, reason in cases:
        decision = decide_v3_projection_readiness(_ready_context(**overrides))

        assert decision.state == V3ProjectionReadinessState.BLOCKED
        assert decision.read_cutover_allowed is False
        assert decision.reason == reason
        assert decision.legacy_fallback_allowed is False


def test_enabled_empty_projection_can_return_empty_list_only_when_readiness_is_ok():
    ready_empty = decide_v3_projection_readiness(_ready_context(projection_empty=True))

    assert ready_empty.state == V3ProjectionReadinessState.READY_EMPTY
    assert ready_empty.read_cutover_allowed is True
    assert ready_empty.can_return_enabled_empty_list is True
    assert ready_empty.response_body_override == []
    assert ready_empty.reason == 'memory_derived_projection_ready_empty'
    assert ready_empty.legacy_fallback_allowed is False

    blocked_empty = decide_v3_projection_readiness(_ready_context(projection_empty=True, freshness_fence_present=False))
    assert blocked_empty.state == V3ProjectionReadinessState.BLOCKED
    assert blocked_empty.can_return_enabled_empty_list is False
    assert blocked_empty.response_body_override is None
    assert blocked_empty.reason == 'freshness_fence_missing'


def test_projection_readiness_api_does_not_expose_legacy_fallback_knob_or_archive_short_term_default_visibility():
    decision_fields = set(V3ProjectionReadinessDecision.__dataclass_fields__)
    assert 'fallback_to_legacy' not in decision_fields
    assert 'use_legacy_on_projection_failure' not in decision_fields
    assert 'include_archive_by_default' not in decision_fields
    assert 'show_stale_short_term_by_default' not in decision_fields

    source = inspect.getsource(decide_v3_projection_readiness)
    assert 'fallback_to_legacy' not in source
    assert 'use_legacy_on_projection_failure' not in source
    assert 'legacy_fallback_allowed=True' not in source
    assert 'archive_default_available=True' not in source
    assert 'stale_short_term_default_visible=True' not in source
