"""Regression tests for the v3 memory mutation HTTP contract."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.memories import MemoryDB
from routers import memories
from tests.unit.test_memory_service_parity import _sample_memory_dict


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.add_api_route('/v3/memories/{memory_id}', memories.edit_memory, methods=['PATCH'])
    app.add_api_route(
        '/v3/memories/{memory_id}/visibility',
        memories.update_memory_visibility,
        methods=['PATCH'],
    )
    for route in app.routes:
        if getattr(route, 'path', '').startswith('/v3/memories/{memory_id}'):
            for dependency in route.dependant.dependencies:
                app.dependency_overrides[dependency.call] = lambda: 'test-user'

    monkeypatch.setattr(
        memories,
        '_validate_mutable_memory',
        lambda *_args, **_kwargs: {'category': 'system'},
    )
    monkeypatch.setattr(memories, 'submit_with_context', lambda *_args, **_kwargs: None)

    calls = []
    state = {"updated": None}

    class _UniversalMemoryService:
        def __init__(self, **_kwargs):
            pass

        def update_content(self, uid, memory_id, value):
            calls.append(('content', uid, memory_id, value))
            if state["updated"] is not None:
                return state["updated"]
            return MemoryDB.model_validate(_sample_memory_dict(memory_id))

        def update_visibility(self, uid, memory_id, value):
            calls.append(('visibility', uid, memory_id, value))

    monkeypatch.setattr(memories, 'MemoryService', _UniversalMemoryService)
    with TestClient(app) as test_client:
        test_client.memory_calls = calls
        test_client.memory_state = state
        yield test_client


def test_edit_memory_accepts_canonical_json_body(client, monkeypatch):
    response = client.patch('/v3/memories/memory-1', json={'value': 'Updated content'})

    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}
    assert client.memory_calls == [('content', 'test-user', 'memory-1', 'Updated content')]


def test_edit_memory_retains_legacy_query_parameter(client, monkeypatch):
    response = client.patch('/v3/memories/memory-1', params={'value': 'Legacy content'})

    assert response.status_code == 200
    assert client.memory_calls == [('content', 'test-user', 'memory-1', 'Legacy content')]


def test_canonical_body_takes_precedence_over_legacy_query_parameter(client, monkeypatch):
    response = client.patch(
        '/v3/memories/memory-1',
        params={'value': 'Legacy content'},
        json={'value': 'Canonical content'},
    )

    assert response.status_code == 200
    assert client.memory_calls == [('content', 'test-user', 'memory-1', 'Canonical content')]


def test_ledger_edit_returns_authoritative_replacement(client):
    payload = _sample_memory_dict("replacement")
    payload.update(
        {
            "content": "Lives in Brooklyn",
            "ledger_schema_version": "knowledge_ledger.v1",
            "kind": "fact",
            "subject_scope": "primary_user",
            "slot": "home_city",
            "intent_backed": True,
            "write_reason": "direct_user_statement",
        }
    )
    client.memory_state["updated"] = MemoryDB.model_validate(payload)

    response = client.patch('/v3/memories/prior', json={'value': 'Lives in Brooklyn'})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["memory"]["id"] == "replacement"
    assert body["memory"]["ledger_schema_version"] == "knowledge_ledger.v1"


def test_ledger_edit_retry_reaches_lineage_aware_service(client, monkeypatch):
    def reject_active_only_preflight(*_args, **_kwargs):
        raise AssertionError("edit must not preflight through the active-only fetch path")

    monkeypatch.setattr(memories, "_validate_mutable_memory", reject_active_only_preflight)
    payload = _sample_memory_dict("replacement")
    payload.update(
        {
            "ledger_schema_version": "knowledge_ledger.v1",
            "kind": "fact",
            "subject_scope": "primary_user",
            "slot": "home_city",
            "intent_backed": True,
            "write_reason": "direct_user_statement",
        }
    )
    client.memory_state["updated"] = MemoryDB.model_validate(payload)

    first = client.patch('/v3/memories/prior', json={'value': 'Lives in Brooklyn'})
    retry = client.patch('/v3/memories/prior', json={'value': 'Lives in Brooklyn'})

    assert first.status_code == 200
    assert retry.status_code == 200
    assert [call for call in client.memory_calls if call[0] == "content"] == [
        ('content', 'test-user', 'prior', 'Lives in Brooklyn'),
        ('content', 'test-user', 'prior', 'Lives in Brooklyn'),
    ]


@pytest.mark.parametrize('json_body', [None, {}, {'content': 'wrong field'}, {'value': {'nested': 'object'}}])
def test_edit_memory_rejects_missing_or_malformed_value(client, json_body):
    response = client.patch('/v3/memories/memory-1', json=json_body)

    assert response.status_code == 422


def test_visibility_accepts_canonical_json_body(client, monkeypatch):
    response = client.patch('/v3/memories/memory-1/visibility', json={'value': 'public'})

    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}
    assert client.memory_calls == [('visibility', 'test-user', 'memory-1', 'public')]


def test_visibility_retains_legacy_query_parameter(client, monkeypatch):
    response = client.patch('/v3/memories/memory-1/visibility', params={'value': 'private'})

    assert response.status_code == 200
    assert client.memory_calls == [('visibility', 'test-user', 'memory-1', 'private')]


@pytest.mark.parametrize(
    ('json_body', 'expected_status'),
    [
        (None, 422),
        ({}, 422),
        ({'visibility': 'public'}, 422),
        ({'value': {'nested': 'object'}}, 422),
        ({'value': 'shared'}, 400),
    ],
)
def test_visibility_rejects_missing_malformed_or_unknown_value(client, json_body, expected_status):
    response = client.patch('/v3/memories/memory-1/visibility', json=json_body)

    assert response.status_code == expected_status
