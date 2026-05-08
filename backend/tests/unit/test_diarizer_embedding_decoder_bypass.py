"""Regression tests for diarizer embedding decoder bypass.

These tests verify the endpoint preloads audio into memory and passes
{"waveform", "sample_rate"} to pyannote inference instead of a file path.
"""

import io
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch

import numpy as np


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
    fake_fastapi.HTTPException = Exception
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
        spec = importlib.util.spec_from_file_location("test_diarizer_embedding", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module


def test_load_audio_for_inference_returns_waveform_dict():
    mod = _load_module()
    mod.torchaudio.load = MagicMock(return_value=("fake-waveform", 22050))

    result = mod._load_audio_for_inference("/tmp/audio.wav")

    mod.torchaudio.load.assert_called_once_with("/tmp/audio.wav")
    assert result == {"waveform": "fake-waveform", "sample_rate": 22050}


def test_embedding_endpoint_passes_preloaded_audio_to_inference():
    mod = _load_module()
    mod._validate_audio_duration = MagicMock()
    mod._load_audio_for_inference = MagicMock(return_value={"waveform": "wf", "sample_rate": 16000})
    mod.embedding_inference = MagicMock(return_value=np.array([1.0, 2.0], dtype=np.float32))

    upload = SimpleNamespace(filename="sample.wav", file=io.BytesIO(b"fake-wav"))

    with patch("builtins.open", mock_open()):
        with patch.object(mod.shutil, "copyfileobj"):
            with patch.object(mod.os.path, "exists", return_value=True):
                with patch.object(mod.os, "remove"):
                    result = mod.embedding_endpoint(upload)

    mod._validate_audio_duration.assert_called_once()
    mod._load_audio_for_inference.assert_called_once()
    mod.embedding_inference.assert_called_once_with({"waveform": "wf", "sample_rate": 16000})
    assert result == [1.0, 2.0]
