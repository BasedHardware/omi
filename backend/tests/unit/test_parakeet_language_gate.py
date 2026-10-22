"""Pure routing rule of the Parakeet spoken-language gate (no torch, no model)."""

import os

import numpy as np
import pytest

from testing.import_isolation import load_module_fresh

PARAKEET_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../parakeet"))


@pytest.fixture(scope="module")
def gate():
    return load_module_fresh("parakeet_language_gate_under_test", os.path.join(PARAKEET_DIR, "language_gate.py"))


def test_p_supported_sums_the_parakeet_languages(gate):
    verdict = gate.decide({"es": 0.5, "pt": 0.46, "gl": 0.04}, 10.0, "whisper-base")
    assert verdict.route == "parakeet"
    assert verdict.language == "es"
    assert verdict.p_supported == pytest.approx(0.96)


@pytest.mark.parametrize(
    "seconds,p,route",
    [(0.99, 1.0, "multilingual"), (3.0, 0.9778, "multilingual"), (3.0, 0.985, "parakeet"),
     (6.0, 0.9218, "multilingual"), (6.0, 0.95, "parakeet")],
)  # fmt: skip
def test_thresholds_by_duration(gate, seconds, p, route):
    assert gate.decide({"en": p, "ja": 1 - p}, seconds, "m").route == route


@pytest.mark.parametrize("language", ["ja", "zh", "ko", "vi", "hi", "ar", "th", "id", "tr"])
def test_confident_unsupported_speech_never_routes_parakeet(gate, language):
    verdict = gate.decide({language: 0.99, "en": 0.01}, 30.0, "m")
    assert verdict.route == "multilingual" and verdict.language == language


def test_non_finite_scores_are_ignored(gate):
    verdict = gate.decide({"en": float("nan"), "ja": 0.9}, 10.0, "m")
    assert verdict.route == "multilingual" and verdict.language == "ja"
    assert gate.decide({}, 10.0, "m").route == "multilingual"


def test_language_set_matches_backend_policy(gate):
    from config.stt_provider_policy import STTServingSurface, parakeet_supports_language

    for code in gate.PARAKEET_LANGUAGES:
        assert parakeet_supports_language(STTServingSurface.PRERECORDED, code), code
    for code in ("ja", "zh", "ko", "vi", "hi", "ar", "th", "id", "tr"):
        assert not parakeet_supports_language(STTServingSurface.PRERECORDED, code), code


def test_model_defaults_on_and_unknown_values_are_off(gate, monkeypatch):
    monkeypatch.delenv("PARAKEET_LID_MODEL", raising=False)
    assert gate.configured_model() == "whisper-base"
    monkeypatch.setenv("PARAKEET_LID_MODEL", "off")
    assert gate.configured_model() == "off"
    monkeypatch.setenv("PARAKEET_LID_MODEL", " Whisper-Base ")
    assert gate.configured_model() == "whisper-base"
    monkeypatch.setenv("PARAKEET_LID_MODEL", "mms-lid-126")
    assert gate.configured_model() == "off"
    assert gate.load("cpu") is None


def test_resample_and_mono(gate):
    x = np.ones((48000 * 2, 2), dtype=np.float32)
    y = gate.to_mono_16k(x, 48000)
    assert y.ndim == 1 and len(y) == 32000 and y.dtype == np.float32
