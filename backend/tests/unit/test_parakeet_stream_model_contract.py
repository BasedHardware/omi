"""Behavioral tests for the NeMo streaming model selection contract."""

from __future__ import annotations

import os
import sys
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

PARAKEET_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../parakeet"))
TRANSCRIBE_PATH = Path(PARAKEET_DIR) / "transcribe.py"
if PARAKEET_DIR not in sys.path:
    sys.path.insert(0, PARAKEET_DIR)


@pytest.fixture
def transcribe_module(monkeypatch):
    """Load transcribe.py without leaking its import-time env snapshot."""

    monkeypatch.setenv("PARAKEET_INFERENCE_MODE", "nemo")
    # An explicitly empty value prevents this hermetic test from downloading a
    # checkpoint while still exercising the production default helper below.
    monkeypatch.setenv("PARAKEET_STREAM_MODEL", "")
    spec = importlib.util.spec_from_file_location("parakeet_stream_model_contract", TRANSCRIBE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _model_with_family(family: str):
    model = MagicMock()
    model.preprocessor = SimpleNamespace()
    model.encoder = SimpleNamespace()
    model.tokenizer = SimpleNamespace()
    model.change_decoding_strategy = MagicMock()
    model.decoding = SimpleNamespace(
        decoding=SimpleNamespace(
            _model_type=SimpleNamespace(value=family),
            decoding_computer=MagicMock(),
        )
    )
    return model


def test_default_tdt_model_is_validated_against_loaded_decoder(transcribe_module):
    model = _model_with_family("tdt")
    default_name = transcribe_module.DEFAULT_STREAM_MODEL_NAME

    assert transcribe_module._validate_stream_model(model, default_name) == "tdt"


def test_explicit_rnnt_override_is_validated_as_rnnt(transcribe_module):
    model = _model_with_family("rnnt")
    model_name = "nvidia/parakeet-rnnt-1.1b"

    assert transcribe_module._validate_stream_model(model, model_name) == "rnnt"


def test_declared_tdt_model_rejects_an_rnnt_decoder(transcribe_module):
    model = _model_with_family("rnnt")
    model_name = transcribe_module.DEFAULT_STREAM_MODEL_NAME

    with pytest.raises(RuntimeError, match="declares tdt but loaded decoder is rnnt"):
        transcribe_module._validate_stream_model(model, model_name)


def test_nemo_loader_uses_checkpoint_autodetection_before_concrete_fallbacks(monkeypatch, transcribe_module):
    loaded = MagicMock()
    loaded.eval.return_value = loaded
    calls = []

    class ASRModel:
        @classmethod
        def from_pretrained(cls, **kwargs):
            calls.append(cls.__name__)
            return loaded

    monkeypatch.setattr(transcribe_module, "nemo_asr", SimpleNamespace(models=SimpleNamespace(ASRModel=ASRModel)))
    monkeypatch.setattr(transcribe_module, "_torch", SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)))

    assert transcribe_module._load_nemo_model(transcribe_module.DEFAULT_STREAM_MODEL_NAME) is loaded
    assert calls == ["ASRModel"]


def test_default_tdt_resolves_the_immutable_huggingface_artifact(monkeypatch, transcribe_module):
    calls = []

    def fake_download(**kwargs):
        calls.append(kwargs)
        return "/cache/parakeet-tdt-0.6b-v3.nemo"

    monkeypatch.setattr(transcribe_module, "_hf_hub_download", fake_download)

    assert (
        transcribe_module._resolve_stream_model_path(transcribe_module.DEFAULT_STREAM_MODEL_NAME)
        == "/cache/parakeet-tdt-0.6b-v3.nemo"
    )
    assert calls == [
        {
            "repo_id": "nvidia/parakeet-tdt-0.6b-v3",
            "filename": "parakeet-tdt-0.6b-v3.nemo",
            "revision": "541d1f99c6b0c3cd0b11a95167540bb8edefd82b",
        }
    ]


def test_pinned_stream_artifact_uses_restore_from(monkeypatch, transcribe_module):
    loaded = MagicMock()
    loaded.eval.return_value = loaded
    calls = []

    class ASRModel:
        @classmethod
        def restore_from(cls, **kwargs):
            calls.append(kwargs)
            return loaded

    monkeypatch.setattr(
        transcribe_module,
        "nemo_asr",
        SimpleNamespace(models=SimpleNamespace(ASRModel=ASRModel)),
    )
    monkeypatch.setattr(transcribe_module, "_torch", SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)))

    assert (
        transcribe_module._load_nemo_model(
            transcribe_module.DEFAULT_STREAM_MODEL_NAME,
            model_path="/cache/parakeet-tdt-0.6b-v3.nemo",
        )
        is loaded
    )
    assert calls == [{"restore_path": "/cache/parakeet-tdt-0.6b-v3.nemo", "map_location": "cpu"}]
