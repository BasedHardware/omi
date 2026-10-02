import sys
from unittest.mock import MagicMock
import pytest

# Hermetic isolation: mock process_conversation if not available
if 'utils.conversations.process_conversation' not in sys.modules:
    mock_pc = MagicMock()
    sys.modules['utils.conversations.process_conversation'] = mock_pc

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from routers import agents as router_module


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router_module.router)
    with TestClient(app) as tc:
        yield tc


def test_hume_callback_success(client, monkeypatch):
    called = []

    def fake_process(provider, request_id, callback):
        called.append((provider, request_id, callback))

    monkeypatch.setattr(router_module, 'process_user_expression_measurement_callback', fake_process)

    payload = {'job_id': 'job-abc-123', 'status': 'COMPLETED', 'predictions': []}
    resp = client.post('/v1/agents/hume/callback', json=payload)
    assert resp.status_code == 200
    assert resp.json() == {}
    assert len(called) == 1
    assert called[0][1] == 'job-abc-123'


def test_hume_callback_empty_dict_returns_400(client):
    resp = client.post('/v1/agents/hume/callback', json={})
    assert resp.status_code == 400
    assert resp.json()['detail'] == 'Job callback is invalid'


def test_hume_callback_missing_job_id_returns_400(client):
    payload = {'status': 'COMPLETED', 'predictions': []}
    resp = client.post('/v1/agents/hume/callback', json=payload)
    assert resp.status_code == 400
    assert resp.json()['detail'] == 'Job ID is required'


def test_hume_callback_whitespace_job_id_returns_400(client):
    payload = {'job_id': '   ', 'status': 'COMPLETED'}
    resp = client.post('/v1/agents/hume/callback', json=payload)
    assert resp.status_code == 400
    assert resp.json()['detail'] == 'Job ID is required'


def test_hume_callback_parse_error_returns_400(client, monkeypatch):
    def fake_from_dict(model, data):
        raise ValueError("Corrupt predictions shape")

    monkeypatch.setattr(router_module.hume.HumeJobCallbackModel, 'from_dict', fake_from_dict)
    resp = client.post('/v1/agents/hume/callback', json={'job_id': 'j1'})
    assert resp.status_code == 400
    assert resp.json()['detail'] == 'Job callback is invalid'


def test_hume_callback_process_error_returns_500_sanitized(client, monkeypatch):
    def fake_process(provider, request_id, callback):
        raise RuntimeError("Database connection dropped on internal_hume_store_sec_999")

    monkeypatch.setattr(router_module, 'process_user_expression_measurement_callback', fake_process)
    payload = {'job_id': 'job-fail-1', 'status': 'COMPLETED'}
    resp = client.post('/v1/agents/hume/callback', json=payload)
    assert resp.status_code == 500
    assert resp.json()['detail'] == 'Failed to process callback'
    assert 'internal_hume_store' not in resp.text


def test_hume_callback_propagates_http_exception(client, monkeypatch):
    def fake_process(provider, request_id, callback):
        raise HTTPException(status_code=403, detail='Provider forbidden')

    monkeypatch.setattr(router_module, 'process_user_expression_measurement_callback', fake_process)
    payload = {'job_id': 'job-perm-1', 'status': 'COMPLETED'}
    resp = client.post('/v1/agents/hume/callback', json=payload)
    assert resp.status_code == 403
    assert resp.json()['detail'] == 'Provider forbidden'
