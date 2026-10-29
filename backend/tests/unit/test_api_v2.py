import asyncio
from unittest.mock import Mock
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import sys
from pathlib import Path
import importlib

def _get_modules(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'diarizer'))
    api = importlib.import_module('api_v2')
    admission = importlib.import_module('admission')
    return api, admission

def test_api_v2_min_speakers_exceeds_max_speakers(monkeypatch):
    api, admission = _get_modules(monkeypatch)
    queue = admission.AdmissionQueue(capacity=1)
    worker = Mock()
    router = api.create_router(worker, queue)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post("/v2/diarization?min_speakers=5&max_speakers=3", content=b"audio data")
    assert response.status_code == 422
    assert "min_speakers exceeds max_speakers" in response.json()['detail']

def test_api_v2_capacity_exceeded(monkeypatch):
    api, admission = _get_modules(monkeypatch)
    queue = admission.AdmissionQueue(capacity=1)
    def mock_worker(body, content_type, min_speakers, max_speakers):
        return {"result": "success"}
    router = api.create_router(mock_worker, queue)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    with queue.admit():
        response = client.post("/v2/diarization", content=b"audio data")

    assert response.status_code == 429
    assert "diarization queue full" in response.json()['detail']
    assert response.headers['Retry-After'] == '30'

def test_api_v2_success(monkeypatch):
    api, admission = _get_modules(monkeypatch)
    queue = admission.AdmissionQueue(capacity=1)
    def mock_worker(body, content_type, min_speakers, max_speakers):
        return {"result": "success", "body_len": len(body)}
    router = api.create_router(mock_worker, queue)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post("/v2/diarization?min_speakers=1&max_speakers=5", content=b"audio data", headers={"content-type": "audio/pcm"})

    assert response.status_code == 200
    assert response.json() == {"result": "success", "body_len": 10}
    assert queue.depth == 0

def test_api_v2_worker_exception(monkeypatch):
    api, admission = _get_modules(monkeypatch)
    queue = admission.AdmissionQueue(capacity=1)
    def mock_worker(body, content_type, min_speakers, max_speakers):
        raise ValueError("worker error")
    router = api.create_router(mock_worker, queue)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    with pytest.raises(ValueError, match="worker error"):
        client.post("/v2/diarization", content=b"audio data")
    assert queue.depth == 0

def test_api_v2_audio_exceeds_two_hours(monkeypatch):
    api, admission = _get_modules(monkeypatch)
    queue = admission.AdmissionQueue(capacity=1)
    worker = Mock()
    router = api.create_router(worker, queue)
    app = FastAPI()
    app.include_router(router)

    # Use monkeypatch to temporarily modify MAX_AUDIO_SECONDS
    monkeypatch.setattr(api, 'MAX_AUDIO_SECONDS', 0)

    client = TestClient(app)
    response = client.post("/v2/diarization", content=b"0" * 65537)
    assert response.status_code == 413
    assert "audio exceeds two hours" in response.json()['detail']
    assert queue.depth == 0

@pytest.mark.asyncio
async def test_api_v2_upload_disconnected(monkeypatch):
    api, admission = _get_modules(monkeypatch)
    queue = admission.AdmissionQueue(capacity=1)
    worker = Mock()
    router = api.create_router(worker, queue)

    # manually call the router function with a mock request
    route = next(route for route in router.routes if route.path == "/v2/diarization")
    diarization_v2 = route.endpoint

    async def mock_receive():
        return {'type': 'http.disconnect'}

    request = Request(scope={'type': 'http', 'method': 'POST', 'path': '/v2/diarization', 'headers': []}, receive=mock_receive)

    with pytest.raises(Exception) as excinfo:
        await diarization_v2(request=request, min_speakers=None, max_speakers=None)

    assert excinfo.value.status_code == 400
    assert "upload disconnected" in excinfo.value.detail
    assert queue.depth == 0
