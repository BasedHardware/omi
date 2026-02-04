"""Tests for Speechmatics confidence threshold helper.

This test file tests the confidence threshold logic in isolation without
importing the full streaming module (which has heavy dependencies).
"""

import logging
import os
import pytest


def get_speechmatics_min_confidence() -> float:
    """Get minimum confidence threshold for Speechmatics transcription.

    This is a copy of the function from utils/stt/streaming.py for testing
    without the heavy import chain (firestore, etc).

    Returns the value of SPEECHMATICS_MIN_CONFIDENCE env var, clamped to [0.0, 1.0].
    Default is 0.4 for backwards compatibility. Set to 0.2-0.3 for far-field audio.
    """
    raw = os.getenv("SPEECHMATICS_MIN_CONFIDENCE", "0.4")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logging.warning("Invalid SPEECHMATICS_MIN_CONFIDENCE=%r; using 0.4", raw)
        return 0.4
    if value < 0.0 or value > 1.0:
        logging.warning(
            "SPEECHMATICS_MIN_CONFIDENCE=%r out of range; clamping to [0.0, 1.0]",
            raw,
        )
        value = min(max(value, 0.0), 1.0)
    return value


class TestGetSpeechmaticsMinConfidence:
    """Tests for get_speechmatics_min_confidence() helper."""

    def test_default_value_when_env_unset(self, monkeypatch):
        """Returns 0.4 when SPEECHMATICS_MIN_CONFIDENCE is not set."""
        monkeypatch.delenv("SPEECHMATICS_MIN_CONFIDENCE", raising=False)
        assert get_speechmatics_min_confidence() == 0.4

    def test_valid_float_value(self, monkeypatch):
        """Returns parsed float when env var is valid."""
        monkeypatch.setenv("SPEECHMATICS_MIN_CONFIDENCE", "0.25")
        assert get_speechmatics_min_confidence() == 0.25

    def test_zero_value_disables_filtering(self, monkeypatch):
        """Zero is valid and effectively disables confidence filtering."""
        monkeypatch.setenv("SPEECHMATICS_MIN_CONFIDENCE", "0.0")
        assert get_speechmatics_min_confidence() == 0.0

    def test_one_value_drops_everything(self, monkeypatch):
        """One is valid (would drop all non-perfect confidence)."""
        monkeypatch.setenv("SPEECHMATICS_MIN_CONFIDENCE", "1.0")
        assert get_speechmatics_min_confidence() == 1.0

    def test_invalid_string_falls_back_to_default(self, monkeypatch, caplog):
        """Invalid string value logs warning and returns default."""
        monkeypatch.setenv("SPEECHMATICS_MIN_CONFIDENCE", "abc")
        with caplog.at_level(logging.WARNING):
            result = get_speechmatics_min_confidence()
        assert result == 0.4
        assert "Invalid SPEECHMATICS_MIN_CONFIDENCE" in caplog.text

    def test_empty_string_falls_back_to_default(self, monkeypatch, caplog):
        """Empty string logs warning and returns default."""
        monkeypatch.setenv("SPEECHMATICS_MIN_CONFIDENCE", "")
        with caplog.at_level(logging.WARNING):
            result = get_speechmatics_min_confidence()
        assert result == 0.4
        assert "Invalid SPEECHMATICS_MIN_CONFIDENCE" in caplog.text

    def test_negative_value_clamped_to_zero(self, monkeypatch, caplog):
        """Negative value is clamped to 0.0 with warning."""
        monkeypatch.setenv("SPEECHMATICS_MIN_CONFIDENCE", "-0.5")
        with caplog.at_level(logging.WARNING):
            result = get_speechmatics_min_confidence()
        assert result == 0.0
        assert "out of range" in caplog.text

    def test_value_above_one_clamped_to_one(self, monkeypatch, caplog):
        """Value > 1.0 is clamped to 1.0 with warning."""
        monkeypatch.setenv("SPEECHMATICS_MIN_CONFIDENCE", "1.5")
        with caplog.at_level(logging.WARNING):
            result = get_speechmatics_min_confidence()
        assert result == 1.0
        assert "out of range" in caplog.text

    def test_scientific_notation_accepted(self, monkeypatch):
        """Scientific notation is valid float syntax."""
        monkeypatch.setenv("SPEECHMATICS_MIN_CONFIDENCE", "2e-1")
        assert get_speechmatics_min_confidence() == 0.2
