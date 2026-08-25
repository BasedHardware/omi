"""Regression tests for the v3 memory mutation HTTP contract."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import memories


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

    monkeypatch.setattr(memories, '_canonical_write_enabled_or_fail_closed', lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        memories,
        '_validate_mutable_memory',
        lambda *_args, **_kwargs: {'category': 'system'},
    )
    monkeypatch.setattr(memories, 'upsert_memory_vector', lambda *_args, **_kwargs: None)
    return TestClient(app)


def test_edit_memory_accepts_canonical_json_body(client, monkeypatch):
    calls = []
    monkeypatch.setattr(memories.memories_db, 'edit_memory', lambda *args: calls.append(args))

    response = client.patch('/v3/memories/memory-1', json={'value': 'Updated content'})

    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}
    assert calls == [('test-user', 'memory-1', 'Updated content')]


def test_edit_memory_retains_legacy_query_parameter(client, monkeypatch):
    calls = []
    monkeypatch.setattr(memories.memories_db, 'edit_memory', lambda *args: calls.append(args))

    response = client.patch('/v3/memories/memory-1', params={'value': 'Legacy content'})

    assert response.status_code == 200
    assert calls == [('test-user', 'memory-1', 'Legacy content')]


def test_canonical_body_takes_precedence_over_legacy_query_parameter(client, monkeypatch):
    calls = []
    monkeypatch.setattr(memories.memories_db, 'edit_memory', lambda *args: calls.append(args))

    response = client.patch(
        '/v3/memories/memory-1',
        params={'value': 'Legacy content'},
        json={'value': 'Canonical content'},
    )

    assert response.status_code == 200
    assert calls == [('test-user', 'memory-1', 'Canonical content')]


@pytest.mark.parametrize('json_body', [None, {}, {'content': 'wrong field'}, {'value': {'nested': 'object'}}])
def test_edit_memory_rejects_missing_or_malformed_value(client, json_body):
    response = client.patch('/v3/memories/memory-1', json=json_body)

    assert response.status_code == 422


def test_visibility_accepts_canonical_json_body(client, monkeypatch):
    calls = []
    monkeypatch.setattr(memories.memories_db, 'change_memory_visibility', lambda *args: calls.append(args))

    response = client.patch('/v3/memories/memory-1/visibility', json={'value': 'public'})

    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}
    assert calls == [('test-user', 'memory-1', 'public')]


def test_visibility_retains_legacy_query_parameter(client, monkeypatch):
    calls = []
    monkeypatch.setattr(memories.memories_db, 'change_memory_visibility', lambda *args: calls.append(args))

    response = client.patch('/v3/memories/memory-1/visibility', params={'value': 'private'})

    assert response.status_code == 200
    assert calls == [('test-user', 'memory-1', 'private')]


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
