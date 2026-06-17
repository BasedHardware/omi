import asyncio
import io
import os
import struct
import sys
import wave
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

os.environ.setdefault("PARAKEET_MODEL", "nvidia/parakeet-tdt-0.6b-v3")
os.environ.setdefault("PARAKEET_DEVICE", "cpu")
os.environ.setdefault("PARAKEET_TORCH_COMPILE", "false")
os.environ.setdefault("PARAKEET_CUDA_GRAPHS", "false")
os.environ.setdefault("PARAKEET_INFERENCE_MODE", "nemo")

_torch = MagicMock()
_torch.cuda.is_available.return_value = False
_torch.cuda.memory_allocated.return_value = 0
_torch_props = MagicMock()
_torch_props.total_memory = 16 * 1024**3
_torch.cuda.get_device_properties.return_value = _torch_props
_torch.cuda.empty_cache = MagicMock()
_torch.inference_mode = lambda: (lambda fn: fn)
_torch.compile = lambda m: m
_torch.backends.cudnn = MagicMock()
sys.modules["torch"] = _torch

_nemo_asr = MagicMock()
_nemo = MagicMock()
_nemo.collections.asr = _nemo_asr
sys.modules["nemo"] = _nemo
sys.modules["nemo.collections"] = _nemo.collections
sys.modules["nemo.collections.asr"] = _nemo_asr

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../parakeet"))

import importlib

os.environ["PARAKEET_STREAM_MODEL"] = ""
if "transcribe" in sys.modules:
    _existing = sys.modules["transcribe"]
    if not hasattr(_existing, "__file__") or _existing.__file__ is None:
        del sys.modules["transcribe"]
        import transcribe  # noqa: F811

        importlib.reload(transcribe)

if "main" in sys.modules:
    _existing_main = sys.modules["main"]
    if not hasattr(_existing_main, "__file__") or _existing_main.__file__ is None:
        del sys.modules["main"]

from gpu_worker import GPUWorker
from batch_engine import BatchEngine, QueueFullError

from fastapi.testclient import TestClient


def _make_app_with_mocks(gpu_ready=True, nim_mode=False):
    import main as parakeet_main

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
