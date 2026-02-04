"""Tests for Speechmatics confidence threshold helper.

This test file tests the confidence threshold logic in isolation without
importing the full streaming module (which has heavy dependencies).
"""

import logging
import math
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
    # Handle special float values (nan, inf)
    if math.isnan(value) or math.isinf(value):
        logging.warning(
            "SPEECHMATICS_MIN_CONFIDENCE=%r is nan/inf; using 0.4",
            raw,
        )
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

    def test_nan_value_falls_back_to_default(self, monkeypatch, caplog):
        """NaN value logs warning and returns default."""
        monkeypatch.setenv("SPEECHMATICS_MIN_CONFIDENCE", "nan")
        with caplog.at_level(logging.WARNING):
            result = get_speechmatics_min_confidence()
        assert result == 0.4
        assert "nan/inf" in caplog.text

    def test_inf_value_falls_back_to_default(self, monkeypatch, caplog):
        """Infinity value logs warning and returns default."""
        monkeypatch.setenv("SPEECHMATICS_MIN_CONFIDENCE", "inf")
        with caplog.at_level(logging.WARNING):
            result = get_speechmatics_min_confidence()
        assert result == 0.4
        assert "nan/inf" in caplog.text

    def test_negative_inf_value_falls_back_to_default(self, monkeypatch, caplog):
        """Negative infinity value logs warning and returns default."""
        monkeypatch.setenv("SPEECHMATICS_MIN_CONFIDENCE", "-inf")
        with caplog.at_level(logging.WARNING):
            result = get_speechmatics_min_confidence()
        assert result == 0.4
        assert "nan/inf" in caplog.text


def should_drop_low_confidence_token(r_type: str, r_confidence: float, min_confidence: float) -> bool:
    """Determine if a Speechmatics token should be dropped due to low confidence.

    This is a copy of the logic from utils/stt/streaming.py for testing
    without the heavy import chain (firestore, etc).

    - Punctuation tokens bypass confidence filtering (preserve sentence boundaries)
    - Word tokens are dropped if confidence < min_confidence
    """
    if r_type == "punctuation":
        return False  # Never drop punctuation
    return r_confidence < min_confidence


class TestShouldDropLowConfidenceToken:
    """Tests for confidence filtering logic including punctuation bypass."""

    def test_word_below_threshold_is_dropped(self):
        """Word token below threshold should be dropped."""
        assert should_drop_low_confidence_token("word", 0.3, 0.4) is True

    def test_word_at_threshold_is_kept(self):
        """Word token at exactly threshold should be kept."""
        assert should_drop_low_confidence_token("word", 0.4, 0.4) is False

    def test_word_above_threshold_is_kept(self):
        """Word token above threshold should be kept."""
        assert should_drop_low_confidence_token("word", 0.8, 0.4) is False

    def test_punctuation_bypasses_threshold_low_confidence(self):
        """Punctuation with low confidence should NOT be dropped."""
        assert should_drop_low_confidence_token("punctuation", 0.1, 0.4) is False

    def test_punctuation_bypasses_threshold_zero_confidence(self):
        """Punctuation with zero confidence should NOT be dropped."""
        assert should_drop_low_confidence_token("punctuation", 0.0, 0.4) is False

    def test_punctuation_with_high_confidence_kept(self):
        """Punctuation with high confidence is also kept."""
        assert should_drop_low_confidence_token("punctuation", 0.9, 0.4) is False

    def test_zero_threshold_keeps_all_words(self):
        """Zero threshold disables filtering for words."""
        assert should_drop_low_confidence_token("word", 0.01, 0.0) is False

    def test_one_threshold_drops_imperfect_words(self):
        """Threshold of 1.0 drops all non-perfect confidence words."""
        assert should_drop_low_confidence_token("word", 0.99, 1.0) is True
        assert should_drop_low_confidence_token("word", 1.0, 1.0) is False
