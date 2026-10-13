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


@pytest.mark.asyncio
async def test_health_and_metrics_remain_live_when_legacy_embedding_exhausts_thread_pool(monkeypatch):
    import asyncio
    import importlib.util
    import sys
    import threading
    from types import ModuleType
    import anyio
    import httpx

    service_root = Path(__file__).resolve().parents[2] / 'diarizer'
    monkeypatch.syspath_prepend(str(service_root))
    entered, release = threading.Event(), threading.Event()

    def blocked_embedding(_file):
        entered.set()
        assert release.wait(5)
        return [1.0]

    fake_embedding = ModuleType('embedding')
    fake_embedding.embedding_endpoint = blocked_embedding
    fake_embedding.embedding_endpoint_v2 = blocked_embedding
    fake_diarization = ModuleType('diarization')
    fake_diarization.diarization_endpoint = lambda _file: []
    fake_final = ModuleType('final_pass')
    fake_final.decode_audio = lambda *_a: None
    fake_final.infer = lambda *_a: {}
    for name, module in [('embedding', fake_embedding), ('diarization', fake_diarization), ('final_pass', fake_final)]:
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location('diarizer_health_fixture', service_root / 'main.py')
    service = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(service)
    limiter = anyio.to_thread.current_default_thread_limiter()
    original = limiter.total_tokens
    limiter.total_tokens = 1
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=service.app), base_url='http://synthetic'
        ) as client:
            embedding = asyncio.create_task(client.post('/v2/embedding', files={'file': ('synthetic.wav', b'ab')}))
            try:
                for _ in range(1000):
                    if entered.is_set():
                        break
                    await asyncio.sleep(0.001)
                assert entered.is_set()
                assert (await asyncio.wait_for(client.get('/health'), 0.5)).json() == {'status': 'healthy'}
                assert (await asyncio.wait_for(client.get('/metrics'), 0.5)).status_code == 200
            finally:
                release.set()
                assert (await embedding).status_code == 200
    finally:
        limiter.total_tokens = original
