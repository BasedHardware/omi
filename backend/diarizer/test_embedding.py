"""
Unit tests for audio duration validation in embedding module.

These tests focus on the validation logic and don't require model loading.
To run: cd backend/diarizer && python -m pytest test_embedding.py -v
"""

import io
import os
import tempfile
import wave

import numpy as np
import pytest
from fastapi import HTTPException

# Import only the validation function and constant to avoid model loading
from embedding import _validate_audio_duration, MIN_AUDIO_DURATION_SECONDS


def create_wav_file(duration_seconds: float, sample_rate: int = 16000) -> str:
    """Create a temporary WAV file with the specified duration."""
    num_samples = int(duration_seconds * sample_rate)
    samples = np.zeros(num_samples, dtype=np.int16)

    fd, path = tempfile.mkstemp(suffix='.wav')
    try:
        with wave.open(path, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(samples.tobytes())
    finally:
        os.close(fd)

    return path


class TestValidateAudioDuration:
    """Tests for _validate_audio_duration function."""

    def test_rejects_audio_shorter_than_minimum(self):
        """Audio shorter than MIN_AUDIO_DURATION_SECONDS should raise HTTPException."""
        path = create_wav_file(0.025)  # 25ms
        try:
            with pytest.raises(HTTPException) as exc_info:
                _validate_audio_duration(path)
            assert exc_info.value.status_code == 400
            assert "Audio too short" in exc_info.value.detail
        finally:
            os.unlink(path)

    def test_accepts_audio_at_minimum_duration(self):
        """Audio at exactly minimum duration should pass."""
        path = create_wav_file(MIN_AUDIO_DURATION_SECONDS)
        try:
            duration = _validate_audio_duration(path)
            assert duration >= MIN_AUDIO_DURATION_SECONDS
        finally:
            os.unlink(path)

    def test_accepts_audio_longer_than_minimum(self):
        """Audio longer than minimum duration should pass."""
        path = create_wav_file(0.5)  # 500ms
        try:
            duration = _validate_audio_duration(path)
            assert duration >= 0.5
        finally:
            os.unlink(path)

    def test_error_includes_actual_duration(self):
        """Error message should include actual audio duration."""
        path = create_wav_file(0.030)  # 30ms
        try:
            with pytest.raises(HTTPException) as exc_info:
                _validate_audio_duration(path)
            # Duration should be in the error message
            assert "0.03" in exc_info.value.detail
        finally:
            os.unlink(path)

    def test_error_includes_minimum_duration(self):
        """Error message should include minimum required duration."""
        path = create_wav_file(0.025)
        try:
            with pytest.raises(HTTPException) as exc_info:
                _validate_audio_duration(path)
            assert str(MIN_AUDIO_DURATION_SECONDS) in exc_info.value.detail
        finally:
            os.unlink(path)

    def test_invalid_file_raises_error(self):
        """Invalid audio file should raise HTTPException with file read error."""
        fd, path = tempfile.mkstemp(suffix='.wav')
        try:
            os.write(fd, b"not a valid wav file")
            os.close(fd)
            with pytest.raises(HTTPException) as exc_info:
                _validate_audio_duration(path)
            assert exc_info.value.status_code == 400
            assert "Failed to read audio file" in exc_info.value.detail
        finally:
            os.unlink(path)
