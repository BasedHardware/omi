"""Behavioral tests for the shared Parakeet image's serving-mode contract."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

SERVICE_MODE = Path(__file__).resolve().parents[2] / "parakeet" / "service_mode.py"


@pytest.fixture
def mode():
    return runpy.run_path(str(SERVICE_MODE))


@pytest.mark.parametrize(
    ("env", "expected"),
    [({}, "mixed"), ({"PARAKEET_SERVICE_MODE": "BATCH"}, "batch"), ({"PARAKEET_SERVICE_MODE": " stream "}, "stream")],
)
def test_mode_is_normalized_and_defaults_to_legacy_mixed(mode, env, expected):
    assert mode["get_service_mode"](env) == expected


def test_unknown_mode_fails_closed(mode):
    with pytest.raises(ValueError, match="PARAKEET_SERVICE_MODE"):
        mode["get_service_mode"]({"PARAKEET_SERVICE_MODE": "gpu"})


def test_stream_model_defaults_to_multilingual_tdt(mode):
    assert mode["get_stream_model_name"]({}) == "nvidia/parakeet-tdt-0.6b-v3"
    assert mode["stream_model_identity"]("nvidia/parakeet-tdt-0.6b-v3") == {
        "backend": "nemo",
        "stream_model": "nvidia/parakeet-tdt-0.6b-v3",
        "decoder_family": "tdt",
        "language_support": "multilingual",
        "model_revision": "541d1f99c6b0c3cd0b11a95167540bb8edefd82b",
        "model_artifact": "parakeet-tdt-0.6b-v3.nemo",
    }


def test_explicit_empty_stream_model_still_disables_loading(mode):
    assert mode["get_stream_model_name"]({"PARAKEET_STREAM_MODEL": "  "}) == ""


def test_explicit_rnnt_stream_model_keeps_english_capability(mode):
    identity = mode["stream_model_identity"]("nvidia/parakeet-rnnt-1.1b")
    assert identity["decoder_family"] == "rnnt"
    assert identity["language_support"] == "en"
