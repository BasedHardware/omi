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
    fake_embedding.initialize_embeddings = lambda **_kw: None
    fake_embedding.embedding_endpoint = blocked_embedding
    fake_embedding.embedding_endpoint_v2 = blocked_embedding
    fake_diarization = ModuleType('diarization')
    fake_diarization.initialize_diarization = lambda: None
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


def load_service(monkeypatch, entrypoint, *, startup_failure=None, inference=None):
    """Load real service/startup and embedding initializer with hermetic models."""
    import importlib.util
    import sys
    from types import ModuleType, SimpleNamespace

    root = Path(__file__).resolve().parents[2] / 'diarizer'
    monkeypatch.syspath_prepend(str(root))
    loaded = []

    def model(name, **kwargs):
        key = 'batch_pipeline' if kwargs.get('revision') and 'community' in name else name
        loaded.append(key)
        if startup_failure == key:
            raise RuntimeError('synthetic model-load failure')
        return SimpleNamespace(to=lambda _device: None)

    torch = ModuleType('torch')
    torch.device = lambda name: name
    torch.cuda = SimpleNamespace(is_available=lambda: False)
    pyannote = ModuleType('pyannote.audio')
    pyannote.Model = SimpleNamespace(from_pretrained=model)
    pyannote.Pipeline = SimpleNamespace(from_pretrained=model)
    pyannote.Inference = lambda _model, **_kw: SimpleNamespace(to=lambda _device: None)
    for name, value in [('torch', torch), ('torchaudio', ModuleType('torchaudio')), ('pyannote.audio', pyannote)]:
        monkeypatch.setitem(sys.modules, name, value)

    def load(name):
        spec = importlib.util.spec_from_file_location(name, root / (name + '.py'))
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        return module

    embedding = load('embedding')
    embedding.embedding_endpoint = lambda _file: [1.0]
    embedding.embedding_endpoint_v2 = lambda _file: [1.0]
    load('diarization')
    final = load('final_pass')
    final.decode_audio = lambda *_args: None
    final.infer = inference or (lambda *_args: {})
    service = load(entrypoint)
    return service, loaded


@pytest.mark.parametrize(
    'model',
    [
        'pyannote/embedding',
        'pyannote/wespeaker-voxceleb-resnet34-LM',
        'pyannote/speaker-diarization-community-1',
        'batch_pipeline',
    ],
)
def test_model_load_failure_is_fatal_at_startup(monkeypatch, model):
    monkeypatch.setenv('DIARIZATION_V2_ENABLED', 'true')
    entrypoint = 'batch_main' if model == 'batch_pipeline' else 'main'
    service, _ = load_service(monkeypatch, entrypoint, startup_failure=model)
    with pytest.raises(RuntimeError, match='model-load failure'):
        with TestClient(service.app):
            pytest.fail('startup must fail before serving a request')


def test_legacy_startup_loads_all_models_without_enabling_batch(monkeypatch):
    monkeypatch.delenv('DIARIZATION_V2_ENABLED', raising=False)
    service, loaded = load_service(monkeypatch, 'main')
    with TestClient(service.app) as client:
        assert loaded == [
            'pyannote/embedding',
            'pyannote/wespeaker-voxceleb-resnet34-LM',
            'pyannote/speaker-diarization-community-1',
        ]
        assert client.get('/health').status_code == 200
        assert client.post('/v2/diarization').status_code == 404


def test_batch_startup_requires_enable_and_loads_only_batch_models(monkeypatch):
    monkeypatch.delenv('DIARIZATION_V2_ENABLED', raising=False)
    service, loaded = load_service(monkeypatch, 'batch_main')
    with pytest.raises(RuntimeError, match='DIARIZATION_V2_ENABLED'):
        with TestClient(service.app):
            pytest.fail('disabled batch app must not listen')
    assert loaded == []
    monkeypatch.setenv('DIARIZATION_V2_ENABLED', 'true')
    with TestClient(service.app) as client:
        assert loaded == ['pyannote/wespeaker-voxceleb-resnet34-LM', 'batch_pipeline']
        assert client.post('/v2/embedding').status_code == 404


@pytest.mark.asyncio
async def test_embedding_completes_while_batch_diarization_holds_slot(monkeypatch):
    import asyncio
    import threading
    import httpx

    root = Path(__file__).resolve().parents[2] / 'diarizer'
    monkeypatch.syspath_prepend(str(root))
    admission = importlib.import_module('admission')
    entered, release = threading.Event(), threading.Event()

    def blocked_inference(*_args):
        with admission.GPU_LOCK:
            entered.set()
            assert release.wait(5)
        return {'turns': []}

    legacy, _ = load_service(monkeypatch, 'main')
    batch, _ = load_service(monkeypatch, 'batch_main', inference=blocked_inference)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=legacy.app), base_url='http://legacy') as live:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=batch.app), base_url='http://batch') as offline:
            diarization = asyncio.create_task(
                offline.post('/v2/diarization', content=b'ab', headers={'content-type': 'audio/pcm'})
            )
            try:
                for _ in range(1000):
                    if entered.is_set():
                        break
                    await asyncio.sleep(0.001)
                assert entered.is_set() and not diarization.done()
                for path in ('/v1/embedding', '/v2/embedding'):
                    result = await asyncio.wait_for(live.post(path, files={'file': ('synthetic.wav', b'ab')}), 0.5)
                    assert result.status_code == 200 and result.json() == [1.0]
                assert not diarization.done()
            finally:
                release.set()
                assert (await diarization).status_code == 200
