"""Boundary tests for the hardened workstreams router error contract."""

import os

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')

import logging
from datetime import datetime, timezone
from functools import partial

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.workstreams as workstreams_router
from models.workstream import WorkIntentReceipt, Workstream
from routers.canonical_task_access import require_canonical_task_user

STANDARD_HEADERS = {
    'Idempotency-Key': 'hardening-test-key-0001',
    'X-Account-Generation': '1',
}
SENSITIVE_MARKER = 'sec_abc123xyz789'
WHITESPACE_ID = '%20%20%20'  # raw path segment that decodes to '   '

ARTIFACT_BODY = {
    'logical_key': 'doc',
    'version': 1,
    'kind': 'report',
    'uri': 's3://bucket/doc',
    'content_hash': 'abcdef1234567890',
}
CHECKPOINT_BODY = {
    'runtime_id': 'runtime-1',
    'last_event_sequence': 0,
    'context_summary': 'ctx',
}

STORE_FUNCTIONS = [
    'resolve_work_intent',
    'get_workstream_detail',
    'update_workstream',
    'append_workstream_event',
    'list_workstream_events',
    'create_artifact_descriptor',
    'transition_artifact_status',
    'list_artifact_descriptors',
    'upsert_continuation_checkpoint',
    'list_continuation_checkpoints',
    'import_task_goal_links',
]

WORKSTREAM_SCOPED_REQUESTS = [
    ('GET', '/v1/workstreams/{workstream_id}', None),
    ('PATCH', '/v1/workstreams/{workstream_id}', {'title': 'Updated title'}),
    ('POST', '/v1/workstreams/{workstream_id}/events', {'kind': 'user_note', 'summary': 'note'}),
    ('GET', '/v1/workstreams/{workstream_id}/events', None),
    ('POST', '/v1/workstreams/{workstream_id}/artifacts', ARTIFACT_BODY),
    ('PATCH', '/v1/workstreams/{workstream_id}/artifacts/artifact-1/status', {'status': 'approved'}),
    ('GET', '/v1/workstreams/{workstream_id}/artifacts', None),
    ('PUT', '/v1/workstreams/{workstream_id}/checkpoints/runtime-1', CHECKPOINT_BODY),
    ('GET', '/v1/workstreams/{workstream_id}/checkpoints', None),
]

LIST_ENDPOINTS = [
    ('/v1/workstreams/ws-1/events', 'list_workstream_events'),
    ('/v1/workstreams/ws-1/artifacts', 'list_artifact_descriptors'),
    ('/v1/workstreams/ws-1/checkpoints', 'list_continuation_checkpoints'),
]


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(workstreams_router.router)
    app.dependency_overrides[require_canonical_task_user] = lambda: 'hardening-user'
    return TestClient(app)


def _store_raiser(exc: Exception):
    def _raise(*_args, **_kwargs):
        raise exc

    return _raise


def _record(calls: list, name: str, *_args, **_kwargs):
    calls.append(name)


def _record_all_store_calls(monkeypatch) -> list:
    calls: list = []
    for store_function in STORE_FUNCTIONS:
        monkeypatch.setattr(
            workstreams_router.workstreams_db,
            store_function,
            partial(_record, calls, store_function),
        )
    return calls


def _real_stored_document_parse_error() -> Exception:
    """Build the real exception shape for a stored document that fails parsing."""

    try:
        Workstream.model_validate({})
    except Exception as exc:  # noqa: BLE001 - captured to replay inside the store boundary
        return exc
    raise AssertionError('Workstream.model_validate should have raised')


def test_work_intent_blank_idempotency_key_is_rejected_before_store(client, monkeypatch):
    calls = _record_all_store_calls(monkeypatch)

    response = client.post(
        '/v1/work-intents',
        json={'origin': 'task', 'task_id': 't1'},
        headers={'Idempotency-Key': '   ', 'X-Account-Generation': '1'},
    )

    assert response.status_code == 400
    assert response.json()['detail'] == 'idempotency_key must not be empty or whitespace'
    assert calls == []


def test_work_intent_success_forwards_key_and_generation(client, monkeypatch):
    captured = {}
    receipt = WorkIntentReceipt(
        receipt_id='receipt-1',
        workstream_id='w1',
        task_id='t1',
        newly_created=True,
        created_at=datetime.now(timezone.utc),
    )

    def resolve(uid, request, **kwargs):
        captured.update(uid=uid, request=request, **kwargs)
        return receipt

    monkeypatch.setattr(workstreams_router.workstreams_db, 'resolve_work_intent', resolve)
    refreshed = []
    monkeypatch.setattr(
        workstreams_router,
        'refresh_workstream_association_index',
        lambda uid, workstream_id: refreshed.append((uid, workstream_id)),
    )

    response = client.post(
        '/v1/work-intents',
        json={'origin': 'task', 'task_id': 't1'},
        headers=STANDARD_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()['workstream_id'] == 'w1'
    assert captured['idempotency_key'] == STANDARD_HEADERS['Idempotency-Key']
    assert captured['account_generation'] == 1
    assert refreshed == [('hardening-user', 'w1')]


@pytest.mark.parametrize(('method', 'path_template', 'json_body'), WORKSTREAM_SCOPED_REQUESTS)
def test_whitespace_workstream_id_is_rejected_before_store(client, monkeypatch, method, path_template, json_body):
    calls = _record_all_store_calls(monkeypatch)

    response = client.request(
        method,
        path_template.format(workstream_id=WHITESPACE_ID),
        json=json_body,
        headers=STANDARD_HEADERS,
    )

    assert response.status_code == 400
    assert response.json()['detail'] == 'workstream_id must not be empty or whitespace'
    assert calls == []


def test_whitespace_artifact_id_is_rejected_before_store(client, monkeypatch):
    calls = _record_all_store_calls(monkeypatch)

    response = client.patch(
        f'/v1/workstreams/ws-1/artifacts/{WHITESPACE_ID}/status',
        json={'status': 'approved'},
        headers=STANDARD_HEADERS,
    )

    assert response.status_code == 400
    assert response.json()['detail'] == 'artifact_id must not be empty or whitespace'
    assert calls == []


def test_whitespace_runtime_id_is_rejected_before_store(client, monkeypatch):
    calls = _record_all_store_calls(monkeypatch)

    response = client.put(
        f'/v1/workstreams/ws-1/checkpoints/{WHITESPACE_ID}',
        json=CHECKPOINT_BODY,
        headers=STANDARD_HEADERS,
    )

    assert response.status_code == 400
    assert response.json()['detail'] == 'runtime_id must not be empty or whitespace'
    assert calls == []


def test_checkpoint_runtime_id_path_and_body_mismatch_is_422(client, monkeypatch):
    calls = _record_all_store_calls(monkeypatch)

    response = client.put(
        '/v1/workstreams/ws-1/checkpoints/runtime-1',
        json={**CHECKPOINT_BODY, 'runtime_id': 'runtime-2'},
        headers=STANDARD_HEADERS,
    )

    assert response.status_code == 422
    assert response.json()['detail'] == 'runtime_id path and body must match'
    assert calls == []


def test_surrounding_whitespace_in_ids_is_normalized_before_store(client, monkeypatch):
    captured = []

    def detail(uid, workstream_id):
        captured.append(workstream_id)
        raise workstreams_router.workstreams_db.WorkstreamNotFoundError(workstream_id)

    monkeypatch.setattr(workstreams_router.workstreams_db, 'get_workstream_detail', detail)

    response = client.get('/v1/workstreams/%20ws-1%20')

    assert response.status_code == 404
    assert captured == ['ws-1']


@pytest.mark.parametrize(
    ('method', 'path', 'json_body', 'store_function'),
    [
        ('GET', '/v1/workstreams/ws-1', None, 'get_workstream_detail'),
        ('POST', '/v1/workstreams/ws-1/events', {'kind': 'user_note', 'summary': 'note'}, 'append_workstream_event'),
        ('PUT', '/v1/workstreams/ws-1/checkpoints/runtime-1', CHECKPOINT_BODY, 'upsert_continuation_checkpoint'),
    ],
)
def test_store_not_found_maps_to_404_across_routes(client, monkeypatch, method, path, json_body, store_function):
    monkeypatch.setattr(
        workstreams_router.workstreams_db,
        store_function,
        _store_raiser(workstreams_router.workstreams_db.WorkstreamNotFoundError('ws-1')),
    )

    response = client.request(method, path, json=json_body, headers=STANDARD_HEADERS)

    assert response.status_code == 404
    assert response.json()['detail'] == 'Workflow resource not found'


@pytest.mark.parametrize('error_name', ['WorkstreamConflictError', 'WorkstreamGenerationMismatchError'])
@pytest.mark.parametrize(
    ('method', 'path', 'json_body', 'store_function'),
    [
        ('PATCH', '/v1/workstreams/ws-1', {'title': 'Updated title'}, 'update_workstream'),
        ('POST', '/v1/workstreams/ws-1/artifacts', ARTIFACT_BODY, 'create_artifact_descriptor'),
    ],
)
def test_store_conflicts_map_to_409_across_routes(
    client, monkeypatch, error_name, method, path, json_body, store_function
):
    error_type = getattr(workstreams_router.workstreams_db, error_name)
    monkeypatch.setattr(workstreams_router.workstreams_db, store_function, _store_raiser(error_type('stale state')))

    response = client.request(method, path, json=json_body, headers=STANDARD_HEADERS)

    assert response.status_code == 409
    assert response.json()['detail'] == 'Workflow operation conflicts with current state'


@pytest.mark.parametrize(
    'exc_factory',
    [
        lambda: ValueError(f'Cannot parse stored workstream document at users/{SENSITIVE_MARKER}/workstreams/ws-1'),
        _real_stored_document_parse_error,
        lambda: TypeError(f"'NoneType' object is not subscriptable at users/{SENSITIVE_MARKER}/workstreams/ws-1"),
    ],
    ids=['value-error', 'pydantic-validation-error', 'type-error'],
)
def test_store_deserialization_faults_are_masked_500_not_400(client, monkeypatch, exc_factory):
    """Malformed stored documents are server-side data faults, never client errors."""

    monkeypatch.setattr(workstreams_router.workstreams_db, 'get_workstream_detail', _store_raiser(exc_factory()))

    response = client.get('/v1/workstreams/ws-1')

    assert response.status_code == 500
    assert response.json()['detail'] == 'An internal server error occurred'
    assert SENSITIVE_MARKER not in response.text


def test_unhandled_store_errors_are_masked_and_logged_sanitized(client, monkeypatch, caplog):
    caplog.set_level(logging.ERROR, logger='routers.workstreams')
    monkeypatch.setattr(
        workstreams_router.workstreams_db,
        'get_workstream_detail',
        _store_raiser(RuntimeError(f'firestore read failed for users/{SENSITIVE_MARKER}/workstreams/ws-1')),
    )

    response = client.get('/v1/workstreams/ws-1')

    assert response.status_code == 500
    assert response.json()['detail'] == 'An internal server error occurred'
    assert SENSITIVE_MARKER not in response.text
    records = [record for record in caplog.records if record.name == 'routers.workstreams']
    assert len(records) == 1
    log_line = records[0].getMessage()
    assert 'Unhandled workstreams error' in log_line
    assert SENSITIVE_MARKER not in log_line
    assert '***' in log_line  # the token-like run in the exception text is masked


@pytest.mark.parametrize(('path', 'store_function'), LIST_ENDPOINTS)
def test_list_endpoints_mask_unexpected_store_failures(client, monkeypatch, path, store_function):
    monkeypatch.setattr(
        workstreams_router.workstreams_db,
        store_function,
        _store_raiser(RuntimeError(f'firestore query failed for users/{SENSITIVE_MARKER}')),
    )

    response = client.get(path)

    assert response.status_code == 500
    assert response.json()['detail'] == 'An internal server error occurred'
    assert SENSITIVE_MARKER not in response.text


@pytest.mark.parametrize(('path', 'store_function'), LIST_ENDPOINTS)
def test_list_endpoints_preserve_empty_stream_results(client, monkeypatch, path, store_function):
    """List routes stream queries for unknown workstreams: empty list, not an error."""

    monkeypatch.setattr(workstreams_router.workstreams_db, store_function, lambda *_args, **_kwargs: [])

    response = client.get(path)

    assert response.status_code == 200
    assert response.json() == []


def test_update_workstream_success_path_returns_workstream(client, monkeypatch):
    now = datetime.now(timezone.utc)
    workstream = Workstream(
        workstream_id='ws-1',
        title='Updated title',
        objective='obj',
        status='open',
        created_at=now,
        updated_at=now,
    )
    captured = {}

    def update(uid, workstream_id, request, **_kwargs):
        captured.update(uid=uid, workstream_id=workstream_id)
        return workstream

    monkeypatch.setattr(workstreams_router.workstreams_db, 'update_workstream', update)
    monkeypatch.setattr(workstreams_router, 'refresh_workstream_association_index', lambda uid, workstream_id: None)

    response = client.patch('/v1/workstreams/ws-1', json={'title': 'Updated title'}, headers=STANDARD_HEADERS)

    assert response.status_code == 200
    assert response.json()['workstream_id'] == 'ws-1'
    assert captured == {'uid': 'hardening-user', 'workstream_id': 'ws-1'}
