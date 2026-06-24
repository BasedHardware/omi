import inspect

from utils.memory.v3_projection_readiness import V17_DERIVED_COMPATIBILITY_PROJECTION_SOURCE
from utils.memory.v3_route_planner import V17V3RoutePlanInput, plan_v17_v3_memory_route
from utils.memory.v3_write_convergence import V17V3ExternalWriteOperation, V17V3WriteConvergenceStatus


def _projection_context(**overrides):
    values = {
        'uid': 'uid-a',
        'expected_account_generation': 7,
        'account_generation': 7,
        'projection_generation': 7,
        'create_converged': True,
        'update_converged': True,
        'delete_converged': True,
        'projection_source': V17_DERIVED_COMPATIBILITY_PROJECTION_SOURCE,
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
    return values


def _write_context(operation, **overrides):
    values = {
        'uid': 'uid-a',
        'enrolled': True,
        'operation': operation,
        'write_surface_active': True,
        'reads_blocked_for_cohort': False,
        'v17_authoritative_write_path_available': True,
        'status': V17V3WriteConvergenceStatus.CONVERGED,
        'expected_account_generation': 7,
        'observed_account_generation': 7,
        'durable_outbox_fence': True,
        'independent_dual_write': False,
        'swallowed_failure': False,
        'projection_update_committed': True,
        'projection_commit_id': 'projection-commit-7',
        'projection_generation': 7,
        'tombstone_committed': operation == V17V3ExternalWriteOperation.DELETE,
        'projection_removal_committed': operation == V17V3ExternalWriteOperation.DELETE,
        'vector_cleanup_outbox_fence': operation == V17V3ExternalWriteOperation.DELETE,
    }
    values.update(overrides)
    return values


def _write_contexts(**overrides):
    return [
        _write_context(V17V3ExternalWriteOperation.CREATE, **overrides),
        _write_context(V17V3ExternalWriteOperation.UPDATE, **overrides),
        _write_context(V17V3ExternalWriteOperation.DELETE, **overrides),
    ]


def _plan_input(**overrides):
    values = {
        'uid': 'uid-a',
        'query_params': {'limit': '100'},
        'enrolled': True,
        'control_state': 'valid',
        'default_memory_grant': True,
        'projection_readiness_context': _projection_context(),
        'write_convergence_contexts': _write_contexts(),
        'page_body': [{'id': 'memory-1', 'content': 'MemoryDB-compatible placeholder'}],
        'memorydb_items': [{'id': 'memory-1', 'content': 'MemoryDB-compatible placeholder'}],
    }
    values.update(overrides)
    return V17V3RoutePlanInput(**values)


def test_non_enrolled_route_plan_is_legacy_primary_marker_only_and_preserves_legacy_limit_offset_semantics():
    plan = plan_v17_v3_memory_route(
        _plan_input(
            enrolled=False,
            control_state='missing',
            query_params={'limit': '25', 'offset': '50'},
            default_memory_grant=None,
            projection_readiness_context=None,
            write_convergence_contexts=[],
            page_body=[{'id': 'must-not-be-used'}],
            memorydb_items=[{'id': 'must-not-be-used'}],
        )
    )

    assert plan.plan_kind == 'legacy_primary_plan_only'
    assert plan.http_status == 200
    assert plan.response is None
    assert plan.adapted_request.legacy_primary is True
    assert plan.adapted_request.limit == 25
    assert plan.adapted_request.offset == 50
    assert plan.should_fetch_legacy is False
    assert plan.should_fetch_v17_projection is False
    assert plan.legacy_fallback_allowed is False
    assert plan.route_wired is False


def test_enrolled_valid_request_composes_local_seams_into_v17_memorydb_response_with_additive_headers():
    memorydb_items = [{'id': 'memory-1', 'content': 'MemoryDB-compatible placeholder'}]
    plan = plan_v17_v3_memory_route(_plan_input(memorydb_items=memorydb_items, page_body=memorydb_items))

    assert plan.plan_kind == 'v17_response_envelope'
    assert plan.http_status == 200
    assert plan.response.body == memorydb_items
    assert plan.response.headers['X-Omi-Memory-Read-Source'] == 'v17_compatibility_projection'
    assert plan.response.headers['X-Omi-Memory-Read-Decision'] == 'v17_compatibility_projection_primary'
    assert plan.read_envelope.body == memorydb_items
    assert plan.adapted_request.source == 'v17_compatibility_projection'
    assert plan.adapted_request.read_mode == 'default_memory'
    assert plan.should_fetch_legacy is False
    assert plan.should_fetch_v17_projection is False
    assert plan.legacy_fallback_allowed is False


def test_enrolled_invalid_request_cursor_filter_and_archive_fail_closed_without_legacy_fallback():
    cases = [
        ({'limit': '100', 'offset': '0'}, 'offset_not_allowed_in_v17_cursor_mode'),
        ({'limit': '25', 'source': 'legacy_primary'}, 'unsupported_filter'),
        ({'limit': '25', 'include_archive': 'true'}, 'archive_not_launched_on_v3_default'),
    ]

    for query_params, reason in cases:
        plan = plan_v17_v3_memory_route(_plan_input(query_params=query_params))

        assert plan.plan_kind == 'fail_closed'
        assert plan.http_status == 400
        assert plan.fail_closed_reason == reason
        assert plan.response is None
        assert plan.should_fetch_legacy is False
        assert plan.should_fetch_v17_projection is False
        assert plan.legacy_fallback_allowed is False


def test_enrolled_malformed_no_grant_projection_not_ready_and_write_not_ready_fail_closed_without_fallback():
    cases = [
        (_plan_input(control_state='malformed'), 503, 'enrolled_malformed_fail_closed'),
        (_plan_input(default_memory_grant=False), 403, 'no_default_memory_grant_privacy_consent_deny'),
        (
            _plan_input(projection_readiness_context=_projection_context(freshness_fence_present=False)),
            503,
            'v17_projection_not_ready',
        ),
        (
            _plan_input(
                write_convergence_contexts=_write_contexts(status=V17V3WriteConvergenceStatus.PARTIAL),
            ),
            503,
            'write_convergence_not_ready',
        ),
    ]

    for route_input, status, reason in cases:
        plan = plan_v17_v3_memory_route(route_input)

        assert plan.plan_kind in {'fail_closed', 'deny'}
        assert plan.http_status == status
        assert plan.fail_closed_reason == reason
        assert plan.response is None
        assert plan.should_fetch_legacy is False
        assert plan.should_fetch_v17_projection is False
        assert plan.legacy_fallback_allowed is False


def test_enabled_empty_returns_200_empty_response_without_legacy_fallback():
    plan = plan_v17_v3_memory_route(
        _plan_input(
            projection_readiness_context=_projection_context(projection_empty=True),
            page_body=[{'id': 'legacy-stale'}],
            memorydb_items=[{'id': 'legacy-stale'}],
        )
    )

    assert plan.plan_kind == 'v17_response_envelope'
    assert plan.http_status == 200
    assert plan.response.body == []
    assert plan.response.headers['X-Omi-Memory-Read-Decision'] == 'v17_projection_empty_no_legacy_fallback'
    assert plan.should_fetch_legacy is False
    assert plan.legacy_fallback_allowed is False


def test_route_planner_preserves_archive_default_unavailable_and_no_stale_short_term_default_visible():
    plan = plan_v17_v3_memory_route(_plan_input(query_params={'limit': '25', 'include_archive': 'true'}))

    assert plan.archive_default_available is False
    assert plan.stale_short_term_default_visible is False
    assert plan.should_fetch_legacy is False


def test_route_planner_is_pure_local_and_does_not_import_route_or_external_clients():
    source = inspect.getsource(__import__('utils.memory.v17_v3_route_planner', fromlist=['']))
    forbidden = [
        'routers.memories',
        'FastAPI',
        'Depends',
        'database.',
        'firebase',
        'firestore',
        'pinecone',
        'requests.',
        'httpx.',
        'openai',
        'legacy_fallback_allowed=True',
        'archive_default_available=True',
        'stale_short_term_default_visible=True',
    ]
    for token in forbidden:
        assert token not in source
