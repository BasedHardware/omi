import io
import os
import sys
import wave
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock, patch

import numpy as np
import pytest
import soundfile as sf

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

os.environ.setdefault("PARAKEET_MODEL", "nvidia/parakeet-tdt-0.6b-v3")
os.environ.setdefault("PARAKEET_DEVICE", "cpu")
os.environ.setdefault("PARAKEET_TORCH_COMPILE", "false")
os.environ.setdefault("PARAKEET_CUDA_GRAPHS", "false")
os.environ.setdefault("PARAKEET_INFERENCE_MODE", "nemo")

PARAKEET_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../parakeet"))


@pytest.fixture(scope="module", autouse=True)
def _parakeet_modules():
    """Load the parakeet subservice modules fresh against faked torch/nemo.

    torch and nemo are not installed in the test environment, and the parakeet
    modules import them at module top level. This module-scoped fixture installs
    sanctioned fakes via ``stub_modules`` and exec's each parakeet module fresh
    inside the block, exposing the public symbols the tests need as module
    globals. On teardown ``stub_modules`` evicts every module loaded here so
    nothing leaks to later test files.
    """
    os.environ["PARAKEET_STREAM_MODEL"] = ""
    if str(PARAKEET_DIR) not in sys.path:
        sys.path.insert(0, PARAKEET_DIR)

    torch_fake = AutoMockModule("torch")
    torch_fake.cuda.is_available.return_value = False
    torch_fake.cuda.memory_allocated.return_value = 0
    _torch_props = MagicMock()
    _torch_props.total_memory = 16 * 1024**3
    torch_fake.cuda.get_device_properties.return_value = _torch_props
    torch_fake.cuda.empty_cache = MagicMock()
    torch_fake.cuda.mem_get_info.return_value = (10 * 1024**3, 16 * 1024**3)
    torch_fake.inference_mode = lambda: (lambda fn: fn)
    torch_fake.compile = lambda m: m
    torch_fake.backends.cudnn = MagicMock()

    nemo_asr_fake = AutoMockModule("nemo.collections.asr")
    nemo_fake = AutoMockModule("nemo")
    nemo_fake.collections.asr = nemo_asr_fake
    nemo_collections_fake = AutoMockModule("nemo.collections")
    nemo_collections_fake.asr = nemo_asr_fake

    fakes = {
        "torch": torch_fake,
        "nemo": nemo_fake,
        "nemo.collections": nemo_collections_fake,
        "nemo.collections.asr": nemo_asr_fake,
    }
    with stub_modules(fakes):
        gpu_worker = load_module_fresh("gpu_worker", os.path.join(PARAKEET_DIR, "gpu_worker.py"))
        batch_engine = load_module_fresh("batch_engine", os.path.join(PARAKEET_DIR, "batch_engine.py"))
        load_module_fresh("speaker_math", os.path.join(PARAKEET_DIR, "speaker_math.py"))
        load_module_fresh("transcribe", os.path.join(PARAKEET_DIR, "transcribe.py"))
        load_module_fresh("stream_handler", os.path.join(PARAKEET_DIR, "stream_handler.py"))
        load_module_fresh("main", os.path.join(PARAKEET_DIR, "main.py"))

        g = sys.modules[__name__]
        g.GPUWorker = gpu_worker.GPUWorker
        g.AudioDurationExceededError = gpu_worker.AudioDurationExceededError
        g.BatchEngine = batch_engine.BatchEngine
        g.QueueFullError = batch_engine.QueueFullError
        yield


def _make_app_with_mocks(gpu_ready=True, nim_mode=False):
    import importlib.util

    parakeet_main = sys.modules.get("main")
    if parakeet_main is None or os.path.abspath(getattr(parakeet_main, "__file__", "") or "") != os.path.join(
        PARAKEET_DIR, "main.py"
    ):
        spec = importlib.util.spec_from_file_location("main", os.path.join(PARAKEET_DIR, "main.py"))
        parakeet_main = importlib.util.module_from_spec(spec)
        sys.modules["main"] = parakeet_main
        spec.loader.exec_module(parakeet_main)

    os.makedirs("_temp", exist_ok=True)
    parakeet_main.start_time = 0.0

    mock_gpu = MagicMock(spec=GPUWorker)
    mock_gpu.is_ready = gpu_ready

    mock_engine = MagicMock(spec=BatchEngine)
    mock_engine._pending = []
    mock_engine.metrics = {
        "total_requests": 10,
        "total_batches": 3,
        "total_files": 10,
        "rejected_requests": 0,
        "pending_requests": 0,
    }

    if nim_mode:
        parakeet_main.gpu_worker = None
        parakeet_main.batch_engine = None
    else:
        parakeet_main.gpu_worker = mock_gpu
        parakeet_main.batch_engine = mock_engine

    return parakeet_main.app, parakeet_main, mock_gpu, mock_engine


class TestHealthEndpoint:

    def test_health_returns_503_when_loading(self):
        app, mod, _, _ = _make_app_with_mocks(gpu_ready=False)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "loading"
        assert data["ready"] is False

    def test_health_returns_200_when_ready(self):
        app, mod, _, _ = _make_app_with_mocks(gpu_ready=True)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["ready"] is True

    def test_health_returns_200_nim_mode(self):
        app, mod, _, _ = _make_app_with_mocks(nim_mode=True)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


class TestBatchMetricsEndpoint:

    def test_batch_metrics_with_engine(self):
        app, mod, _, engine = _make_app_with_mocks()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/batch/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_requests"] == 10
        assert data["total_batches"] == 3

    def test_batch_metrics_without_engine(self):
        app, mod, _, _ = _make_app_with_mocks(nim_mode=True)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/batch/metrics")
        assert resp.status_code == 200
        assert resp.json() == {}


class TestStreamAdmissionEndpoint:
    def test_capacity_rejection_happens_before_stream_session_construction(self):
        app, mod, _, _ = _make_app_with_mocks(gpu_ready=True)
        mod.stream_admission = MagicMock()
        mod.stream_admission.try_acquire.return_value = SimpleNamespace(lease=None, reason='capacity_full')

        with patch.object(mod, 'StreamSession') as stream_session:
            client = TestClient(app, raise_server_exceptions=False)
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect('/v3/stream') as websocket:
                    websocket.receive_json()

        assert exc_info.value.code == 1013
        stream_session.assert_not_called()

    def test_session_construction_failure_releases_admission_lease(self):
        app, mod, _, _ = _make_app_with_mocks(gpu_ready=True)
        lease = MagicMock()
        mod.stream_admission = MagicMock()
        mod.stream_admission.try_acquire.return_value = SimpleNamespace(lease=lease, reason='admitted')

        with patch.object(mod, 'StreamSession', side_effect=RuntimeError('construction failed')):
            client = TestClient(app, raise_server_exceptions=False)
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect('/v3/stream') as websocket:
                    websocket.receive_json()

        assert exc_info.value.code == 1011
        lease.release.assert_called_once_with()

    def test_disconnect_releases_admission_lease_after_ready_handshake(self):
        app, mod, _, _ = _make_app_with_mocks(gpu_ready=True)
        lease = MagicMock()
        mod.stream_admission = MagicMock()
        mod.stream_admission.try_acquire.return_value = SimpleNamespace(lease=lease, reason='admitted')
        session = MagicMock()
        session.flush = AsyncMock(return_value=[])
        session.cleanup = MagicMock()

        with patch.object(mod, 'StreamSession', return_value=session):
            client = TestClient(app, raise_server_exceptions=False)
            with client.websocket_connect('/v3/stream') as websocket:
                assert websocket.receive_json() == {'type': 'ready'}

        lease.release.assert_called_once_with()
        session.cleanup.assert_called_once_with()


class TestV1TranscribeEndpoint:

    def test_v1_returns_503_when_loading(self):
        app, mod, _, _ = _make_app_with_mocks(gpu_ready=False)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/v1/transcribe", files={"file": ("test.wav", b"fake", "audio/wav")})
        assert resp.status_code == 503
        assert "loading" in resp.json()["detail"].lower()

    def test_v1_batch_submit_returns_result(self):
        app, mod, _, engine = _make_app_with_mocks(gpu_ready=True)

        async def fake_submit(path, timestamps=True, owns_file=False):
            return {
                "text": "batch result",
                "timestamp": {"segment": [{"segment": "batch result", "start": 0.0, "end": 1.0}]},
            }

        engine.submit = AsyncMock(side_effect=fake_submit)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/v1/transcribe", files={"file": ("test.wav", b"fake audio data", "audio/wav")})
        assert resp.status_code == 200
        data = resp.json()
        assert data["text"] == "batch result"

    def test_v1_queue_full_returns_503(self):
        app, mod, _, engine = _make_app_with_mocks(gpu_ready=True)
        engine.submit = AsyncMock(side_effect=QueueFullError("full"))
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/v1/transcribe", files={"file": ("test.wav", b"fake", "audio/wav")})
        assert resp.status_code == 503
        assert "overloaded" in resp.json()["detail"].lower()


class TestV2TranscribeEndpoint:

    def test_v2_returns_503_when_loading(self):
        app, mod, _, _ = _make_app_with_mocks(gpu_ready=False)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/v2/transcribe", files={"file": ("test.wav", b"fake", "audio/wav")}, data={"diarize": "true"}
        )
        assert resp.status_code == 503

    def test_v2_batch_submit_with_diarize_false(self):
        app, mod, _, engine = _make_app_with_mocks(gpu_ready=True)

        async def fake_submit(path, timestamps=True, owns_file=False):
            return {"text": "v2 result", "timestamp": {"segment": [{"segment": "v2 result", "start": 0.0, "end": 1.0}]}}

        engine.submit = AsyncMock(side_effect=fake_submit)

        with patch("main.transcribe_file_v2") as mock_v2:
            mock_v2.return_value = {
                "text": "v2 result",
                "segments": [{"text": "v2 result", "start": 0.0, "end": 1.0, "speaker": "SPEAKER_0"}],
                "detected_language": "en",
            }
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/v2/transcribe", files={"file": ("test.wav", b"fake", "audio/wav")}, data={"diarize": "false"}
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["text"] == "v2 result"

    def test_v2_queue_full_returns_503(self):
        app, mod, _, engine = _make_app_with_mocks(gpu_ready=True)
        engine.submit = AsyncMock(side_effect=QueueFullError("full"))
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/v2/transcribe", files={"file": ("test.wav", b"fake", "audio/wav")}, data={"diarize": "true"}
        )
        assert resp.status_code == 503


def _make_wav_bytes(duration_s=2.0, sample_rate=16000, channels=1, sampwidth=2):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        n_frames = int(sample_rate * duration_s)
        wf.writeframes(b'\x00' * n_frames * channels * sampwidth)
    return buf.getvalue()


class TestAudioDurationFromBytes:

    def test_valid_wav_returns_positive_duration(self):
        from main import _get_audio_duration_from_bytes

        data = _make_wav_bytes(duration_s=2.0, sample_rate=16000)
        dur = _get_audio_duration_from_bytes(data)
        assert abs(dur - 2.0) < 0.01

    def test_invalid_bytes_returns_zero(self):
        from main import _get_audio_duration_from_bytes

        assert _get_audio_duration_from_bytes(b"not a wav") == 0.0

    def test_empty_bytes_returns_zero(self):
        from main import _get_audio_duration_from_bytes

        assert _get_audio_duration_from_bytes(b"") == 0.0

    def test_invalid_bytes_return_inf_when_guard_enabled(self):
        _, mod, _, _ = _make_app_with_mocks(gpu_ready=True)
        mod._max_file_duration_sec = 5.0
        try:
            assert mod._get_audio_duration_from_bytes(b"not audio") == float('inf')
        finally:
            mod._max_file_duration_sec = 0.0

    def test_flac_returns_positive_duration(self):
        from main import _get_audio_duration_from_bytes

        buf = io.BytesIO()
        sf.write(buf, np.zeros(16000 * 3, dtype='float32'), 16000, format='FLAC')
        dur = _get_audio_duration_from_bytes(buf.getvalue())
        assert abs(dur - 3.0) < 0.01

    def test_v1_with_real_wav_observes_audio_duration(self):
        app, mod, _, engine = _make_app_with_mocks(gpu_ready=True)

        async def fake_submit(path, timestamps=True, owns_file=False):
            return {"text": "ok", "timestamp": {"segment": [{"segment": "ok", "start": 0.0, "end": 1.0}]}}

        engine.submit = AsyncMock(side_effect=fake_submit)
        wav_data = _make_wav_bytes(duration_s=1.5, sample_rate=16000)
        before = mod.AUDIO_DURATION._sum.get()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/v1/transcribe", files={"file": ("test.wav", wav_data, "audio/wav")})
        assert resp.status_code == 200
        after = mod.AUDIO_DURATION._sum.get()
        assert after - before >= 1.4


class TestDurationGuardHTTP413:

    def test_v1_returns_413_for_oversized_wav(self):
        app, mod, _, engine = _make_app_with_mocks(gpu_ready=True)
        mod._max_file_duration_sec = 5.0
        wav_data = _make_wav_bytes(duration_s=10.0, sample_rate=16000)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/v1/transcribe", files={"file": ("long.wav", wav_data, "audio/wav")})
        assert resp.status_code == 413
        assert "exceeds limit" in resp.json()["detail"].lower()
        mod._max_file_duration_sec = 0.0

    def test_v2_returns_413_for_oversized_wav(self):
        app, mod, _, engine = _make_app_with_mocks(gpu_ready=True)
        mod._max_file_duration_sec = 5.0
        wav_data = _make_wav_bytes(duration_s=10.0, sample_rate=16000)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/v2/transcribe", files={"file": ("long.wav", wav_data, "audio/wav")}, data={"diarize": "true"}
        )
        assert resp.status_code == 413
        assert "exceeds limit" in resp.json()["detail"].lower()
        mod._max_file_duration_sec = 0.0

    def test_v1_returns_413_for_oversized_flac(self):
        app, mod, _, engine = _make_app_with_mocks(gpu_ready=True)
        mod._max_file_duration_sec = 5.0
        try:
            buf = io.BytesIO()
            sf.write(buf, np.zeros(16000 * 10, dtype='float32'), 16000, format='FLAC')
            flac_data = buf.getvalue()
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/v1/transcribe", files={"file": ("long.flac", flac_data, "audio/flac")})
            assert resp.status_code == 413
            assert "exceeds limit" in resp.json()["detail"].lower()
        finally:
            mod._max_file_duration_sec = 0.0

    def test_v1_rejects_unprobeable_audio_before_batch(self):
        app, mod, _, engine = _make_app_with_mocks(gpu_ready=True)
        mod._max_file_duration_sec = 5.0
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/v1/transcribe", files={"file": ("bad.bin", b"not audio", "application/octet-stream")})
            assert resp.status_code == 413
            assert "cannot determine audio duration" in resp.json()["detail"].lower()
            engine.submit.assert_not_called()
        finally:
            mod._max_file_duration_sec = 0.0

    def test_v2_rejects_unprobeable_audio_before_batch(self):
        app, mod, _, engine = _make_app_with_mocks(gpu_ready=True)
        mod._max_file_duration_sec = 5.0
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/v2/transcribe",
                files={"file": ("bad.bin", b"not audio", "application/octet-stream")},
                data={"diarize": "true"},
            )
            assert resp.status_code == 413
            assert "cannot determine audio duration" in resp.json()["detail"].lower()
            engine.submit.assert_not_called()
        finally:
            mod._max_file_duration_sec = 0.0

    def test_unprobeable_upload_does_not_poison_audio_duration_metric(self):
        app, mod, _, engine = _make_app_with_mocks(gpu_ready=True)
        mod._max_file_duration_sec = 5.0
        try:
            audio_dur_hist = mod.AUDIO_DURATION
            before_sum = audio_dur_hist._sum.get()
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/v1/transcribe", files={"file": ("bad.bin", b"not audio", "application/octet-stream")})
            assert resp.status_code == 413
            after_sum = audio_dur_hist._sum.get()
            assert after_sum == before_sum, f"AUDIO_DURATION sum changed from {before_sum} to {after_sum}"
            import math

            assert math.isfinite(after_sum), "AUDIO_DURATION sum is not finite"
        finally:
            mod._max_file_duration_sec = 0.0

    def test_v1_passes_when_under_limit(self):
        app, mod, _, engine = _make_app_with_mocks(gpu_ready=True)
        mod._max_file_duration_sec = 60.0

        async def fake_submit(path, timestamps=True, owns_file=False):
            return {"text": "ok", "timestamp": {"segment": [{"segment": "ok", "start": 0.0, "end": 1.0}]}}

        engine.submit = AsyncMock(side_effect=fake_submit)
        wav_data = _make_wav_bytes(duration_s=5.0, sample_rate=16000)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/v1/transcribe", files={"file": ("short.wav", wav_data, "audio/wav")})
        assert resp.status_code == 200
        mod._max_file_duration_sec = 0.0

    def test_v1_returns_413_on_AudioDurationExceededError(self):
        app, mod, _, engine = _make_app_with_mocks(gpu_ready=True)
        engine.submit = AsyncMock(side_effect=AudioDurationExceededError("too long"))
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/v1/transcribe", files={"file": ("test.wav", b"fake", "audio/wav")})
        assert resp.status_code == 413
        assert "too long" in resp.json()["detail"]

    def test_v2_returns_413_on_AudioDurationExceededError(self):
        app, mod, _, engine = _make_app_with_mocks(gpu_ready=True)
        engine.submit = AsyncMock(side_effect=AudioDurationExceededError("too long"))
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/v2/transcribe", files={"file": ("test.wav", b"fake", "audio/wav")}, data={"diarize": "true"}
        )
        assert resp.status_code == 413
        assert "too long" in resp.json()["detail"]

    def test_v1_guard_disabled_when_zero(self):
        app, mod, _, engine = _make_app_with_mocks(gpu_ready=True)
        mod._max_file_duration_sec = 0.0

        async def fake_submit(path, timestamps=True, owns_file=False):
            return {"text": "ok", "timestamp": {"segment": [{"segment": "ok", "start": 0.0, "end": 1.0}]}}

        engine.submit = AsyncMock(side_effect=fake_submit)
        wav_data = _make_wav_bytes(duration_s=3600.0, sample_rate=16000)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/v1/transcribe", files={"file": ("huge.wav", wav_data, "audio/wav")})
        assert resp.status_code == 200

    def test_v2_passes_when_under_limit(self):
        app, mod, _, engine = _make_app_with_mocks(gpu_ready=True)
        mod._max_file_duration_sec = 60.0

        async def fake_submit(path, timestamps=True, owns_file=False):
            return {"text": "ok", "timestamp": {"segment": [{"segment": "ok", "start": 0.0, "end": 1.0}]}}

        engine.submit = AsyncMock(side_effect=fake_submit)
        with patch("main.transcribe_file_v2") as mock_v2:
            mock_v2.return_value = {"text": "ok", "segments": [], "detected_language": "en"}
            wav_data = _make_wav_bytes(duration_s=5.0, sample_rate=16000)
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/v2/transcribe", files={"file": ("short.wav", wav_data, "audio/wav")}, data={"diarize": "false"}
            )
        assert resp.status_code == 200
        mod._max_file_duration_sec = 0.0

    def test_v1_boundary_exact_limit_passes(self):
        app, mod, _, engine = _make_app_with_mocks(gpu_ready=True)
        mod._max_file_duration_sec = 5.0

        async def fake_submit(path, timestamps=True, owns_file=False):
            return {"text": "ok", "timestamp": {"segment": [{"segment": "ok", "start": 0.0, "end": 1.0}]}}

        engine.submit = AsyncMock(side_effect=fake_submit)
        wav_data = _make_wav_bytes(duration_s=5.0, sample_rate=16000)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/v1/transcribe", files={"file": ("exact.wav", wav_data, "audio/wav")})
        assert resp.status_code == 200
        mod._max_file_duration_sec = 0.0


class TestMetricsEndpoint:

    def test_metrics_endpoint_contains_new_series(self):
        app, mod, _, _ = _make_app_with_mocks()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/metrics")
        assert resp.status_code == 200
        body = resp.text
        for name in [
            "parakeet_rtfx",
            "parakeet_audio_duration_seconds",
            "parakeet_queue_duration_seconds",
            "parakeet_inference_duration_seconds",
            "parakeet_gpu_oom_total",
            "parakeet_requests_total",
        ]:
            assert name in body, f"Missing metric: {name}"
