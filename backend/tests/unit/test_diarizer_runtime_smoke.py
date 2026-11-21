import importlib
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

def mock_runtime_dependencies(monkeypatch):
    """Mocks dependencies for `runtime_smoke.py` to allow tests to run without them."""
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'diarizer'))

    mock_torch = MagicMock()
    mock_torchaudio = MagicMock()
    mock_pyannote = MagicMock()

    patcher = patch.dict(sys.modules, {
        'torch': mock_torch,
        'torchaudio': mock_torchaudio,
        'pyannote': mock_pyannote,
        'pyannote.audio': mock_pyannote.audio,
    })
    patcher.start()
    return mock_torch, patcher

def test_runtime_smoke_success(monkeypatch):
    mock_torch, patcher = mock_runtime_dependencies(monkeypatch)
    try:
        runtime_smoke = importlib.import_module('runtime_smoke')

        def mock_decode(data, content_type):
            res = MagicMock()
            res.shape = (1, 3)
            res.tolist.return_value = [[0.0, 32767 / 32768, -1.0]]
            return res

        mock_torch.equal.return_value = True

        with patch('runtime_smoke.decode_audio', side_effect=mock_decode):
            runtime_smoke.run_smoke()
    finally:
        patcher.stop()

def test_runtime_smoke_fails_on_wrong_shape(monkeypatch):
    mock_torch, patcher = mock_runtime_dependencies(monkeypatch)
    try:
        runtime_smoke = importlib.import_module('runtime_smoke')

        def mock_decode(data, content_type):
            res = MagicMock()
            res.shape = (1, 4)
            res.tolist.return_value = [[0.0, 32767 / 32768, -1.0]]
            return res

        mock_torch.equal.return_value = True

        with patch('runtime_smoke.decode_audio', side_effect=mock_decode):
            with pytest.raises(AssertionError):
                runtime_smoke.run_smoke()
    finally:
        patcher.stop()

def test_runtime_smoke_fails_on_not_equal(monkeypatch):
    mock_torch, patcher = mock_runtime_dependencies(monkeypatch)
    try:
        runtime_smoke = importlib.import_module('runtime_smoke')

        def mock_decode(data, content_type):
            res = MagicMock()
            res.shape = (1, 3)
            res.tolist.return_value = [[0.0, 32767 / 32768, -1.0]]
            return res

        mock_torch.equal.return_value = False

        with patch('runtime_smoke.decode_audio', side_effect=mock_decode):
            with pytest.raises(AssertionError):
                runtime_smoke.run_smoke()
    finally:
        patcher.stop()

def test_runtime_smoke_fails_on_wrong_tolist(monkeypatch):
    mock_torch, patcher = mock_runtime_dependencies(monkeypatch)
    try:
        runtime_smoke = importlib.import_module('runtime_smoke')

        def mock_decode(data, content_type):
            res = MagicMock()
            res.shape = (1, 3)
            res.tolist.return_value = [[0.0, 0.5, -1.0]]
            return res

        mock_torch.equal.return_value = True

        with patch('runtime_smoke.decode_audio', side_effect=mock_decode):
            with pytest.raises(AssertionError):
                runtime_smoke.run_smoke()
    finally:
        patcher.stop()
