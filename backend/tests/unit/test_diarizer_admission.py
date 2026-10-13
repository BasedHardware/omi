import importlib
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_queue_rejects_before_body_and_recovers(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'diarizer'))
    admission = importlib.import_module('admission')
    api = importlib.import_module('api_v2')
    queue = admission.AdmissionQueue(capacity=1)
    calls = []

    def worker(body, content_type, minimum, maximum):
        calls.append((bytes(body), content_type, minimum, maximum))
        return {'turns': []}

    app = FastAPI()
    app.include_router(api.create_router(worker, queue))
    try:
        with TestClient(app) as client:
            with queue.admit():
                response = client.post('/v2/diarization', content=b'a', headers={'content-type': 'audio/pcm'})
                assert response.status_code == 429
                assert response.headers['retry-after'] == '30'
                assert calls == []
            assert client.post('/v2/diarization?min_speakers=3&max_speakers=2', content=b'a').status_code == 422
            assert (
                client.post('/v2/diarization', content=b'ab', headers={'content-type': 'audio/pcm'}).status_code == 200
            )
            assert calls == [(b'ab', 'audio/pcm', None, None)]
            assert queue.depth == 0
    finally:
        queue.executor.shutdown()
