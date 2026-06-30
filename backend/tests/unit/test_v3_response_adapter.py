import inspect

import pytest

from utils.memory.v3_memory_read_service import (
    V3CompatibilityReadPath,
    V3MemoryReadServiceResult,
)
from utils.memory.v3_response_adapter import (
    V3ResponseShapeError,
    adapt_v3_memory_response,
)

ALLOWED_HEADERS = {
    'X-Omi-Memory-Read-Source',
    'X-Omi-Memory-Read-Decision',
    'X-Omi-Memory-Next-Cursor',
    'Link',
}


def _envelope(**overrides):
    values = {
        'http_status': 200,
        'read_plan': 'memory_compatibility_projection',
        'read_path': V3CompatibilityReadPath.MEMORY_COMPATIBILITY_PROJECTION,
        'read_decision': 'memory_compatibility_projection_primary',
        'headers': {
            'X-Omi-Memory-Read-Source': 'memory_compatibility_projection',
            'X-Omi-Memory-Read-Decision': 'memory_compatibility_projection_primary',
        },
        'body': [{'id': 'memory-1', 'uid': 'uid-a', 'content': 'legacy MemoryDB body only'}],
        'archive_default_available': False,
        'stale_short_term_default_visible': False,
    }
    values.update(overrides)
    return V3MemoryReadServiceResult(**values)


def test_projection_ready_response_preserves_exact_list_memorydb_body_and_adds_only_allowed_headers():
    body = [{'id': 'memory-1', 'uid': 'uid-a', 'content': 'legacy MemoryDB body only'}]
    envelope = _envelope(
        body=body,
        headers={
            'X-Omi-Memory-Read-Source': 'memory_compatibility_projection',
            'X-Omi-Memory-Read-Decision': 'memory_compatibility_projection_primary',
            'X-Omi-Memory-Next-Cursor': 'v3.next',
            'Link': '<v3.next>; rel="next"',
            'X-Unsafe-Debug': 'must-not-leak',
        },
    )

    response = adapt_v3_memory_response(envelope, memorydb_items=body)

    assert response.http_status == 200
    assert response.body is body
    assert response.body == body
    assert set(response.headers) == ALLOWED_HEADERS
    assert response.headers['X-Omi-Memory-Read-Source'] == 'memory_compatibility_projection'
    assert response.headers['X-Omi-Memory-Read-Decision'] == 'memory_compatibility_projection_primary'
    assert response.headers['X-Omi-Memory-Next-Cursor'] == 'v3.next'
    assert response.headers['Link'] == '<v3.next>; rel="next"'
    assert response.legacy_fallback_marker_present is False
    assert response.archive_default_available is False
    assert response.stale_short_term_default_visible is False
    assert 'source' not in response.body[0]
    assert 'policy' not in response.body[0]
    assert 'cursor' not in response.body[0]


def test_enabled_empty_response_is_empty_list_with_memory_headers_and_no_fallback_marker():
    envelope = _envelope(
        read_decision='memory_projection_empty_no_legacy_fallback',
        headers={
            'X-Omi-Memory-Read-Source': 'memory_compatibility_projection',
            'X-Omi-Memory-Read-Decision': 'memory_projection_empty_no_legacy_fallback',
        },
        body=[],
    )

    response = adapt_v3_memory_response(envelope, memorydb_items=[])

    assert response.http_status == 200
    assert response.body == []
    assert response.headers == {
        'X-Omi-Memory-Read-Source': 'memory_compatibility_projection',
        'X-Omi-Memory-Read-Decision': 'memory_projection_empty_no_legacy_fallback',
    }
    assert response.legacy_fallback_marker_present is False
    assert response.archive_default_available is False
    assert response.stale_short_term_default_visible is False


def test_fail_closed_and_denied_responses_have_no_body_data_and_no_legacy_fallback_marker():
    cases = [
        _envelope(
            http_status=503,
            read_plan='fail_closed',
            read_path=V3CompatibilityReadPath.FAIL_CLOSED,
            read_decision='enrolled_missing_fail_closed',
            headers={
                'X-Omi-Memory-Read-Source': 'none',
                'X-Omi-Memory-Read-Decision': 'enrolled_missing_fail_closed',
            },
            body=None,
        ),
        _envelope(
            http_status=403,
            read_plan='deny',
            read_path=V3CompatibilityReadPath.DENY,
            read_decision='no_default_memory_grant_privacy_consent_deny',
            headers={
                'X-Omi-Memory-Read-Source': 'none',
                'X-Omi-Memory-Read-Decision': 'no_default_memory_grant_privacy_consent_deny',
            },
            body=None,
        ),
    ]

    for envelope in cases:
        response = adapt_v3_memory_response(envelope, memorydb_items=[{'id': 'must-not-leak'}])

        assert response.http_status == envelope.http_status
        assert response.body is None
        assert response.headers == envelope.headers
        assert response.legacy_fallback_marker_present is False
        assert response.archive_default_available is False
        assert response.stale_short_term_default_visible is False


def test_adapter_rejects_memory_only_fields_that_would_leak_through_list_memorydb_body():
    forbidden_items = [
        {'id': 'memory-1', 'content': 'x', 'source': 'memory_items'},
        {'id': 'memory-1', 'content': 'x', 'policy': {'tier': 'short_term'}},
        {'id': 'memory-1', 'content': 'x', 'read_decision': 'memory_projection'},
        {'id': 'memory-1', 'content': 'x', 'cursor': 'v3.next'},
        {'id': 'memory-1', 'content': 'x', 'memory_policy': 'default'},
        {'id': 'memory-1', 'content': 'x', 'archive_default_available': False},
        {'id': 'memory-1', 'content': 'x', 'stale_short_term_default_visible': False},
    ]

    for item in forbidden_items:
        with pytest.raises(V3ResponseShapeError) as exc:
            adapt_v3_memory_response(_envelope(body=[item]), memorydb_items=[item])
        assert exc.value.reason == 'memory_only_body_field_forbidden'


def test_archive_default_unavailable_and_stale_short_term_are_explicit_proof_fields_not_body_fields():
    body = [{'id': 'memory-1', 'content': 'legacy MemoryDB body only'}]
    response = adapt_v3_memory_response(_envelope(body=body), memorydb_items=body)

    assert response.archive_default_available is False
    assert response.stale_short_term_default_visible is False
    assert 'archive_default_available' not in response.body[0]
    assert 'stale_short_term_default_visible' not in response.body[0]


def test_response_adapter_is_pure_local_and_has_no_route_database_cloud_or_testclient_dependency():
    source = inspect.getsource(__import__('utils.memory.v3_response_adapter', fromlist=['']))
    forbidden = [
        'FastAPI',
        'TestClient',
        'routers.',
        'database.',
        'firebase',
        'firestore',
        'pinecone',
        'requests.',
        'httpx.',
        'openai',
        'legacy_fallback_marker_present=True',
        'archive_default_available=True',
        'stale_short_term_default_visible=True',
    ]
    for token in forbidden:
        assert token not in source
