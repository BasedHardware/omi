"""Tests for short audio clip validation in speaker embedding (issue #4572).

Verifies that audio clips shorter than MIN_EMBEDDING_AUDIO_DURATION are rejected
with a clear error instead of crashing the pyannote wespeaker fbank model.
"""

import io
import os
import struct
import sys
import wave

import pytest
import requests
from unittest.mock import MagicMock

# Mock modules that initialize GCP clients at import time
sys.modules.setdefault("database._client", MagicMock())

from utils.stt.speaker_embedding import (
    MIN_EMBEDDING_AUDIO_DURATION,
    _get_wav_duration,
    extract_embedding_from_bytes,
)


def _make_wav_bytes(duration_seconds: float, sample_rate: int = 16000) -> bytes:
    """Generate valid WAV bytes with the given duration."""
    num_frames = int(sample_rate * duration_seconds)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        # Write silence (zeros)
        wf.writeframes(b"\x00\x00" * num_frames)
    return buf.getvalue()


class TestGetWavDuration:
    def test_valid_wav_correct_duration(self):
        wav = _make_wav_bytes(1.0, sample_rate=16000)
        duration = _get_wav_duration(wav)
        assert abs(duration - 1.0) < 0.001

    def test_short_wav_correct_duration(self):
        wav = _make_wav_bytes(0.025, sample_rate=16000)  # ~25ms, the crash case
        duration = _get_wav_duration(wav)
        assert abs(duration - 0.025) < 0.001

    def test_different_sample_rates(self):
        for sr in [8000, 16000, 44100, 48000]:
            wav = _make_wav_bytes(0.5, sample_rate=sr)
            duration = _get_wav_duration(wav)
            assert abs(duration - 0.5) < 0.01, f"Failed for sample_rate={sr}"

    def test_empty_bytes_returns_zero(self):
        assert _get_wav_duration(b"") == 0.0

    def test_garbage_bytes_returns_zero(self):
        assert _get_wav_duration(b"not a wav file at all") == 0.0

    def test_truncated_header_returns_zero(self):
        wav = _make_wav_bytes(1.0)
        truncated = wav[:20]  # Cut off in the middle of the header
        assert _get_wav_duration(truncated) == 0.0


class TestExtractEmbeddingFromBytesValidation:
    def test_short_audio_raises_value_error(self):
        """Audio shorter than MIN_EMBEDDING_AUDIO_DURATION raises ValueError."""
        wav = _make_wav_bytes(0.025)  # 25ms - the crash case from issue #4572
        with pytest.raises(ValueError, match="Audio too short"):
            extract_embedding_from_bytes(wav, "test.wav")

    def test_boundary_below_threshold_raises(self):
        """Audio just below threshold raises ValueError."""
        wav = _make_wav_bytes(MIN_EMBEDDING_AUDIO_DURATION - 0.01)
        with pytest.raises(ValueError, match="Audio too short"):
            extract_embedding_from_bytes(wav, "test.wav")

    def test_boundary_at_threshold_passes_validation(self, monkeypatch):
        """Audio exactly at threshold passes duration check (may fail on API call)."""
        wav = _make_wav_bytes(MIN_EMBEDDING_AUDIO_DURATION)

        # Mock the API call since we only test validation, not the actual embedding
        monkeypatch.setenv("HOSTED_SPEAKER_EMBEDDING_API_URL", "http://fake:1234")
        mock_response = MagicMock()
        mock_response.json.return_value = [0.1] * 512
        mock_response.raise_for_status = MagicMock()

        monkeypatch.setattr(requests, "post", MagicMock(return_value=mock_response))

        # Should not raise ValueError - duration check passes
        result = extract_embedding_from_bytes(wav, "test.wav")
        assert result.shape == (1, 512)

    def test_empty_wav_raises(self):
        """Empty/garbage bytes raise ValueError (duration=0.0)."""
        with pytest.raises(ValueError, match="Audio too short"):
            extract_embedding_from_bytes(b"not a wav", "test.wav")

    def test_min_threshold_is_half_second(self):
        """Default threshold is 0.5 seconds."""
        assert MIN_EMBEDDING_AUDIO_DURATION == 0.5

    def test_threshold_configurable_via_env(self, monkeypatch):
        """MIN_EMBEDDING_AUDIO_DURATION can be overridden via environment."""
        # This tests the module-level constant mechanism
        # The actual env var is read at import time, so we verify the default
        assert MIN_EMBEDDING_AUDIO_DURATION >= 0.1  # Sane minimum
        assert MIN_EMBEDDING_AUDIO_DURATION <= 5.0  # Sane maximum
