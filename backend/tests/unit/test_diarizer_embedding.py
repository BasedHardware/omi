"""Tests for diarizer embedding.py"""
import io
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch
import wave

import numpy as np
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
MODULE_PATH = BACKEND_DIR / "diarizer" / "embedding.py"

def _load_module():
    fake_torch = ModuleType("torch")
    fake_torch.cuda = SimpleNamespace(is_available=lambda: False)
    fake_torch.device = lambda value: value

    fake_torchaudio = ModuleType("torchaudio")
    fake_torchaudio.info = MagicMock()
    fake_torchaudio.load = MagicMock(return_value=("waveform", 16000))

    fake_fastapi = ModuleType("fastapi")
    class HTTPException(Exception):
        def __init__(self, status_code, detail=None):
            self.status_code = status_code
            self.detail = detail
    fake_fastapi.HTTPException = HTTPException
    fake_fastapi.UploadFile = object

    class _FakeModel:
        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            return cls()

    class _FakeInference:
        def __init__(self, *args, **kwargs):
            pass

        def to(self, device):
            self.device = device

        def __call__(self, value):
            return np.array([0.1, 0.2], dtype=np.float32)

    fake_pyannote = ModuleType("pyannote")
    fake_pyannote_audio = ModuleType("pyannote.audio")
    fake_pyannote_audio.Model = _FakeModel
    fake_pyannote_audio.Inference = _FakeInference

    with patch.dict(
        sys.modules,
        {
            "torch": fake_torch,
            "torchaudio": fake_torchaudio,
            "fastapi": fake_fastapi,
            "pyannote": fake_pyannote,
            "pyannote.audio": fake_pyannote_audio,
        },
    ):
        spec = importlib.util.spec_from_file_location("test_diarizer_embedding_full", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module

def test_get_audio_duration_from_file_wave_success():
    mod = _load_module()
    mock_wave = MagicMock()
    mock_wave.getframerate.return_value = 16000
    mock_wave.getnframes.return_value = 32000

    with patch.object(mod.wave, "open", MagicMock(return_value=MagicMock(__enter__=MagicMock(return_value=mock_wave)))):
        duration = mod._get_audio_duration_from_file("dummy.wav")
        assert duration == 2.0

def test_get_audio_duration_from_file_wave_zero_framerate():
    mod = _load_module()
    mock_wave = MagicMock()
    mock_wave.getframerate.return_value = 0

    with patch.object(mod.wave, "open", MagicMock(return_value=MagicMock(__enter__=MagicMock(return_value=mock_wave)))):
        duration = mod._get_audio_duration_from_file("dummy.wav")
        assert duration == 0.0

def test_get_audio_duration_from_file_fallback_to_torchaudio():
    mod = _load_module()
    # wave.open raises wave.Error
    mod.wave.open = MagicMock(side_effect=wave.Error)

    mock_info = SimpleNamespace(sample_rate=16000, num_frames=48000)
    mod.torchaudio.info.return_value = mock_info

    duration = mod._get_audio_duration_from_file("dummy.mp3")
    assert duration == 3.0
    mod.torchaudio.info.assert_called_once_with("dummy.mp3")

def test_get_audio_duration_from_file_fallback_zero_sample_rate():
    mod = _load_module()
    mod.wave.open = MagicMock(side_effect=wave.Error)

    mock_info = SimpleNamespace(sample_rate=0, num_frames=48000)
    mod.torchaudio.info.return_value = mock_info

    duration = mod._get_audio_duration_from_file("dummy.mp3")
    assert duration == 0.0

def test_get_audio_duration_from_file_all_fail():
    mod = _load_module()
    mod.wave.open = MagicMock(side_effect=wave.Error)
    mod.torchaudio.info.side_effect = Exception("failed")

    duration = mod._get_audio_duration_from_file("dummy.mp3")
    assert duration == 0.0

def test_validate_audio_duration_success():
    mod = _load_module()
    mod.MIN_EMBEDDING_AUDIO_DURATION = 0.5
    with patch.object(mod, "_get_audio_duration_from_file", return_value=1.0):
        mod._validate_audio_duration("dummy.wav")  # Should not raise

def test_validate_audio_duration_too_short():
    mod = _load_module()
    mod.MIN_EMBEDDING_AUDIO_DURATION = 0.5
    with patch.object(mod, "_get_audio_duration_from_file", return_value=0.2):
        with pytest.raises(mod.HTTPException) as exc:
            mod._validate_audio_duration("dummy.wav")
        assert exc.value.status_code == 422
        assert exc.value.detail["error"] == "audio_too_short"

def test_embedding_endpoint_success():
    mod = _load_module()
    mod._validate_audio_duration = MagicMock()
    mod._load_audio_for_inference = MagicMock(return_value={"waveform": "wf", "sample_rate": 16000})
    mod.embedding_inference = MagicMock(return_value=np.array([1.1, 2.2], dtype=np.float32))

    upload = SimpleNamespace(filename="test.wav", file=io.BytesIO(b"data"))

    with patch("builtins.open", mock_open()):
        with patch.object(mod.shutil, "copyfileobj"):
            with patch.object(mod.os.path, "exists", return_value=True):
                with patch.object(mod.os, "remove"):
                    result = mod.embedding_endpoint(upload)

    np.testing.assert_allclose(result, [1.1, 2.2], rtol=1e-5)
    mod.embedding_inference.assert_called_once_with({"waveform": "wf", "sample_rate": 16000})

def test_embedding_endpoint_v2_success():
    mod = _load_module()
    mod._validate_audio_duration = MagicMock()
    mod._load_audio_for_inference = MagicMock(return_value={"waveform": "wf", "sample_rate": 16000})
    mod.embedding_inference_v2 = MagicMock(return_value=np.array([3.3, 4.4], dtype=np.float32))

    upload = SimpleNamespace(filename="test_v2.wav", file=io.BytesIO(b"data"))

    with patch("builtins.open", mock_open()):
        with patch.object(mod.shutil, "copyfileobj"):
            with patch.object(mod.os.path, "exists", return_value=True):
                with patch.object(mod.os, "remove") as mock_remove:
                    result = mod.embedding_endpoint_v2(upload)
                    mock_remove.assert_called_once()

    np.testing.assert_allclose(result, [3.3, 4.4], rtol=1e-5)
    mod.embedding_inference_v2.assert_called_once_with({"waveform": "wf", "sample_rate": 16000})
