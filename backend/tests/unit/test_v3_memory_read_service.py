import inspect

from utils.memory.v3.cursor import V3CursorContext, V3Keyset, create_v3_cursor
from utils.memory.v3.memory_read_service import (
    V3MemoryReadRequest,
    V3MemoryReadServiceInput,
    V3MemoryReadServiceResult,
    plan_v3_memory_read,
)
from utils.memory.v3.projection_readiness import DERIVED_COMPATIBILITY_PROJECTION_SOURCE

SECRET = b'unit-test-memory-v3-read-service-secret'


def _projection_context(**overrides):
    values = {
        'uid': 'uid-a',
        'expected_account_generation': 7,
        'account_generation': 7,
        'projection_generation': 7,
        'create_converged': True,
        'update_converged': True,
        'delete_converged': True,
        'projection_source': DERIVED_COMPATIBILITY_PROJECTION_SOURCE,
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


def _cursor_context(**overrides):
    values = {
        'uid': 'uid-a',
        'account_generation': 7,
        'projection_generation': 7,
        'filter_hash': 'default-memory-v1',
        'source': 'memory_compatibility_projection',
        'read_mode': 'default_memory',
        'now_epoch_seconds': 1_800_000_000,
    }
    values.update(overrides)
    return V3CursorContext(**values)


def _service_input(**overrides):
    values = {
        'uid': 'uid-a',
        'enrolled': True,
        'control_state': 'valid',
        'default_memory_grant': True,
        'projection_readiness_context': _projection_context(),
        'request': V3MemoryReadRequest(limit=100, offset=None, cursor=None, v3_cursor_mode=True),
        'page_body': [{'id': 'memory-1', 'content': 'MemoryDB-compatible placeholder'}],
        'cursor_context': _cursor_context(),
        'cursor_secret': SECRET,
        'next_keyset': None,
    }
    values.update(overrides)
    return V3MemoryReadServiceInput(**values)


def test_non_enrolled_returns_explicit_legacy_primary_plan_marker_only_and_preserves_offset_5000_compatibility():
    result = plan_v3_memory_read(
        _service_input(
            enrolled=False,
            control_state='missing',
            projection_readiness_context=None,
            request=V3MemoryReadRequest(limit=5000, offset=0, cursor=None, v3_cursor_mode=False),
            page_body=[{'id': 'must-not-be-read'}],
            cursor_context=None,
            cursor_secret=None,
        )
    )

    assert result.http_status == 200
    assert result.read_plan == 'legacy_primary_plan_only'
    assert result.body is None
    assert result.should_fetch_legacy is False
    assert result.should_fetch_memory_projection is False
    assert result.read_decision == 'non_enrolled_legacy_primary'
    assert result.headers == {
        'X-Omi-Memory-Read-Source': 'legacy_primary',
        'X-Omi-Memory-Read-Decision': 'non_enrolled_legacy_primary',
    }


def test_enrolled_missing_malformed_no_grant_and_projection_not_ready_fail_closed_without_legacy_fallback():
    cases = [
        (_service_input(control_state='missing', default_memory_grant=True), 503, 'enrolled_missing_fail_closed'),
        (_service_input(control_state='malformed', default_memory_grant=True), 503, 'enrolled_malformed_fail_closed'),
        (_service_input(default_memory_grant=False), 403, 'no_default_memory_grant_privacy_consent_deny'),
        (
            _service_input(projection_readiness_context=_projection_context(create_converged=False)),
            503,
            'write_convergence_not_ready',
        ),
        (
            _service_input(projection_readiness_context=_projection_context(freshness_fence_present=False)),
            503,
            'memory_projection_not_ready',
        ),
    ]

    for service_input, status, reason in cases:
        result = plan_v3_memory_read(service_input)

        assert result.http_status == status
        assert result.read_decision == reason
        assert result.should_fetch_legacy is False
        assert result.should_fetch_memory_projection is False
        assert result.legacy_fallback_allowed is False
        assert result.body is None


def test_projection_ready_empty_returns_200_empty_list_no_legacy_fallback_and_header_only_metadata():
    result = plan_v3_memory_read(
        _service_input(
            projection_readiness_context=_projection_context(projection_empty=True), page_body=[{'id': 'legacy'}]
        )
    )

    assert result.http_status == 200
    assert result.read_plan == 'memory_compatibility_projection'
    assert result.body == []
    assert result.should_fetch_legacy is False
    assert result.should_fetch_memory_projection is False
    assert result.legacy_fallback_allowed is False
    assert result.headers['X-Omi-Memory-Read-Source'] == 'memory_compatibility_projection'
    assert result.headers['X-Omi-Memory-Read-Decision'] == 'memory_projection_empty_no_legacy_fallback'
    assert 'X-Omi-Memory-Next-Cursor' not in result.headers
    assert 'Link' not in result.headers


def test_projection_ready_page_passes_memorydb_compatible_body_and_adds_next_cursor_headers_only():
    body = [{'id': 'memory-1', 'content': 'caller supplied MemoryDB-compatible body'}]
    result = plan_v3_memory_read(
        _service_input(page_body=body, next_keyset=V3Keyset(created_at_ms=1_799_999_123_456, memory_id='memory-9'))
    )

    assert result.http_status == 200
    assert result.body == body
    assert result.body is body
    assert result.should_fetch_memory_projection is False
    assert result.read_plan == 'memory_compatibility_projection'
    assert result.headers['X-Omi-Memory-Read-Source'] == 'memory_compatibility_projection'
    assert result.headers['X-Omi-Memory-Read-Decision'] == 'memory_compatibility_projection_primary'
    assert result.headers['X-Omi-Memory-Next-Cursor'].startswith('v3.')
    assert result.headers['Link'] == f'<{result.headers["X-Omi-Memory-Next-Cursor"]}>; rel="next"'
    assert 'source' not in body[0]
    assert 'read_decision' not in body[0]


def test_next_cursor_without_context_fails_closed():
    result = plan_v3_memory_read(
        _service_input(
            cursor_context=None,
            cursor_secret=None,
            next_keyset=V3Keyset(created_at_ms=1_799_999_123_456, memory_id='memory-9'),
        )
    )

    assert result.http_status == 400
    assert result.read_plan == 'fail_closed'
    assert result.read_decision == 'next_cursor_context_missing'
    assert result.headers == {
        'X-Omi-Memory-Read-Source': 'none',
        'X-Omi-Memory-Read-Decision': 'next_cursor_context_missing',
    }


def test_cursor_validation_is_required_in_memory_mode_and_invalid_cursor_never_downgrades_to_offset_or_legacy():
    valid_cursor = create_v3_cursor(
        V3Keyset(created_at_ms=1_799_999_123_456, memory_id='memory-9'),
        _cursor_context(),
        SECRET,
        ttl_seconds=300,
    )

    valid = plan_v3_memory_read(_service_input(request=V3MemoryReadRequest(limit=100, cursor=valid_cursor)))
    assert valid.http_status == 200

    invalid_cases = [
        V3MemoryReadRequest(limit=100, offset=0, cursor=None, v3_cursor_mode=True),
        V3MemoryReadRequest(limit=5000, offset=None, cursor=None, v3_cursor_mode=True),
        V3MemoryReadRequest(limit=100, offset=None, cursor='legacy-offset-25', v3_cursor_mode=True),
    ]
    for request in invalid_cases:
        result = plan_v3_memory_read(_service_input(request=request))

        assert result.http_status == 400
        assert result.read_plan == 'fail_closed'
        assert result.should_fetch_legacy is False
        assert result.should_fetch_memory_projection is False
        assert result.legacy_fallback_allowed is False
        assert result.headers['X-Omi-Memory-Read-Source'] == 'none'
        assert result.read_decision in {
            'offset_not_allowed_in_v3_cursor_mode',
            'legacy_first_page_5000_not_allowed_in_v3_cursor_mode',
            'malformed_cursor',
            'invalid_signature',
        }


def test_archive_default_unavailable_and_stale_short_term_default_visible_are_explicit_non_capabilities():
    result = plan_v3_memory_read(_service_input(requested_archive=True))

    assert result.http_status == 404
    assert result.read_decision == 'archive_default_unavailable'
    assert result.archive_default_available is False
    assert result.stale_short_term_default_visible is False
    assert result.body is None
    assert result.should_fetch_legacy is False
    assert result.should_fetch_memory_projection is False


def test_read_service_is_pure_local_and_does_not_import_routers_database_or_network_clients():
    result_fields = set(V3MemoryReadServiceResult.__dataclass_fields__)
    assert 'fallback_to_legacy' not in result_fields
    assert 'use_legacy_on_error' not in result_fields
    assert 'include_archive_by_default' not in result_fields
    assert 'show_stale_short_term_by_default' not in result_fields

    source = inspect.getsource(__import__('utils.memory.v3.memory_read_service', fromlist=['']))
    forbidden = [
        'routers.memories',
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
