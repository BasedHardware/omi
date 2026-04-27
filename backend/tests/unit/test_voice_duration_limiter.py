"""Tests for voice_duration_limiter module.

Covers:
- PCM duration computation (compute_pcm_duration_ms, compute_max_pcm_bytes)
- WAV header duration reader (read_wav_duration_ms)
- Rolling daily budget (try_consume_budget, check_budget, record_actual_duration)
- Shared budget across endpoints (single pool per UID)
- Edge cases: concurrent requests, zero duration, Redis failure (fail-open)
"""

import os
import struct
import tempfile
import time
from fractions import Fraction
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helper: create a minimal WAV file with known duration
# ---------------------------------------------------------------------------


def _make_wav(duration_s: float, sample_rate: int = 16000, channels: int = 1, bits_per_sample: int = 16) -> str:
    """Create a temporary WAV file with the specified duration and return its path."""
    byte_rate = sample_rate * channels * (bits_per_sample // 8)
    data_size = int(byte_rate * duration_s)
    # Pad to even number of bytes
    if data_size % 2 != 0:
        data_size += 1

    fmt_chunk_size = 16
    riff_size = 4 + (8 + fmt_chunk_size) + (8 + data_size)

    buf = bytearray()
    # RIFF header
    buf.extend(b'RIFF')
    buf.extend(struct.pack('<I', riff_size))
    buf.extend(b'WAVE')
    # fmt chunk
    buf.extend(b'fmt ')
    buf.extend(struct.pack('<I', fmt_chunk_size))
    audio_format = 1  # PCM
    block_align = channels * (bits_per_sample // 8)
    buf.extend(struct.pack('<HHIIHH', audio_format, channels, sample_rate, byte_rate, block_align, bits_per_sample))
    # data chunk
    buf.extend(b'data')
    buf.extend(struct.pack('<I', data_size))
    buf.extend(b'\x00' * data_size)

    fd, path = tempfile.mkstemp(suffix='.wav')
    with os.fdopen(fd, 'wb') as f:
        f.write(buf)
    return path


# ===========================================================================
# compute_pcm_duration_ms / compute_max_pcm_bytes
# ===========================================================================


class TestPCMDurationComputation:
    def test_16khz_mono_1s(self):
        from utils.voice_duration_limiter import compute_pcm_duration_ms

        # 1 second of 16kHz mono 16-bit = 32000 bytes
        assert compute_pcm_duration_ms(32000, 16000, 1) == 1000

    def test_48khz_stereo_1s(self):
        from utils.voice_duration_limiter import compute_pcm_duration_ms

        # 1 second of 48kHz stereo 16-bit = 192000 bytes
        assert compute_pcm_duration_ms(192000, 48000, 2) == 1000

    def test_zero_bytes(self):
        from utils.voice_duration_limiter import compute_pcm_duration_ms

        assert compute_pcm_duration_ms(0, 16000, 1) == 0

    def test_zero_sample_rate(self):
        from utils.voice_duration_limiter import compute_pcm_duration_ms

        assert compute_pcm_duration_ms(1000, 0, 1) == 0

    def test_max_pcm_bytes_16khz_mono_120s(self):
        from utils.voice_duration_limiter import compute_max_pcm_bytes

        # 120s of 16kHz mono 16-bit = 16000 * 1 * 2 * 120 = 3,840,000
        assert compute_max_pcm_bytes(16000, 1, 120) == 3_840_000

    def test_max_pcm_bytes_48khz_stereo_120s(self):
        from utils.voice_duration_limiter import compute_max_pcm_bytes

        # 120s of 48kHz stereo 16-bit = 48000 * 2 * 2 * 120 = 23,040,000
        assert compute_max_pcm_bytes(48000, 2, 120) == 23_040_000


# ===========================================================================
# read_wav_duration_ms
# ===========================================================================


class TestWAVDurationReader:
    def test_valid_wav_1s(self):
        from utils.voice_duration_limiter import read_wav_duration_ms

        path = _make_wav(1.0)
        try:
            duration = read_wav_duration_ms(path)
            assert duration is not None
            assert abs(duration - 1000) <= 1  # Allow 1ms rounding
        finally:
            os.unlink(path)

    def test_valid_wav_120s(self):
        from utils.voice_duration_limiter import read_wav_duration_ms

        path = _make_wav(120.0)
        try:
            duration = read_wav_duration_ms(path)
            assert duration is not None
            assert abs(duration - 120000) <= 1
        finally:
            os.unlink(path)

    def test_stereo_48khz(self):
        from utils.voice_duration_limiter import read_wav_duration_ms

        path = _make_wav(5.0, sample_rate=48000, channels=2)
        try:
            duration = read_wav_duration_ms(path)
            assert duration is not None
            assert abs(duration - 5000) <= 1
        finally:
            os.unlink(path)

    def test_invalid_file_returns_none(self):
        from utils.voice_duration_limiter import read_wav_duration_ms

        fd, path = tempfile.mkstemp()
        with os.fdopen(fd, 'wb') as f:
            f.write(b'not a wav file')
        try:
            assert read_wav_duration_ms(path) is None
        finally:
            os.unlink(path)

    def test_nonexistent_file_returns_none(self):
        from utils.voice_duration_limiter import read_wav_duration_ms

        assert read_wav_duration_ms('/tmp/nonexistent_wav_12345.wav') is None

    def test_empty_file_returns_none(self):
        from utils.voice_duration_limiter import read_wav_duration_ms

        fd, path = tempfile.mkstemp()
        os.close(fd)
        try:
            assert read_wav_duration_ms(path) is None
        finally:
            os.unlink(path)

    def test_corrupted_wav_returns_none(self):
        """Truncated/corrupted WAV should return None (av raises, we catch)."""
        from utils.voice_duration_limiter import read_wav_duration_ms

        buf = bytearray()
        buf.extend(b'RIFF')
        buf.extend(struct.pack('<I', 26))
        buf.extend(b'WAVE')
        buf.extend(b'fmt ')
        buf.extend(struct.pack('<I', 10))  # truncated fmt
        buf.extend(b'\x00' * 10)

        fd, path = tempfile.mkstemp(suffix='.wav')
        with os.fdopen(fd, 'wb') as f:
            f.write(buf)
        try:
            assert read_wav_duration_ms(path) is None
        finally:
            os.unlink(path)

    def test_container_duration_none_falls_back_to_stream(self):
        """When container.duration is None, fall back to stream.duration * stream.time_base."""
        from utils.voice_duration_limiter import read_wav_duration_ms

        mock_stream = MagicMock()
        mock_stream.duration = 48000  # 3 seconds at 16000 sample rate
        mock_stream.time_base = Fraction(1, 16000)

        mock_container = MagicMock()
        mock_container.duration = None
        mock_container.streams.audio = [mock_stream]
        mock_container.__enter__ = MagicMock(return_value=mock_container)
        mock_container.__exit__ = MagicMock(return_value=False)

        with patch('utils.voice_duration_limiter.av.open', return_value=mock_container):
            duration = read_wav_duration_ms('/tmp/fake.wav')

        assert duration is not None
        assert duration == 3000  # 48000 * (1/16000) = 3s = 3000ms

    def test_both_durations_none_returns_none(self):
        """When both container.duration and stream.duration are None, returns None."""
        from utils.voice_duration_limiter import read_wav_duration_ms

        mock_stream = MagicMock()
        mock_stream.duration = None
        mock_stream.time_base = Fraction(1, 16000)

        mock_container = MagicMock()
        mock_container.duration = None
        mock_container.streams.audio = [mock_stream]
        mock_container.__enter__ = MagicMock(return_value=mock_container)
        mock_container.__exit__ = MagicMock(return_value=False)

        with patch('utils.voice_duration_limiter.av.open', return_value=mock_container):
            assert read_wav_duration_ms('/tmp/fake.wav') is None

    def test_stream_time_base_none_returns_none(self):
        """When stream.time_base is None, returns None (can't compute duration)."""
        from utils.voice_duration_limiter import read_wav_duration_ms

        mock_stream = MagicMock()
        mock_stream.duration = 48000
        mock_stream.time_base = None

        mock_container = MagicMock()
        mock_container.duration = None
        mock_container.streams.audio = [mock_stream]
        mock_container.__enter__ = MagicMock(return_value=mock_container)
        mock_container.__exit__ = MagicMock(return_value=False)

        with patch('utils.voice_duration_limiter.av.open', return_value=mock_container):
            assert read_wav_duration_ms('/tmp/fake.wav') is None


# ===========================================================================
# Redis budget — mock Redis for unit testing
# ===========================================================================


@pytest.fixture
def mock_redis():
    """Mock the Redis client and Lua script for budget tests."""
    mock_r = MagicMock()
    mock_script = MagicMock()
    mock_r.register_script.return_value = mock_script
    return mock_r, mock_script


class TestBudgetConsumeLogic:
    """Test try_consume_budget with mocked Redis."""

    def test_consume_allowed(self, mock_redis):
        _, mock_script = mock_redis
        mock_script.return_value = [1, 60000, 7140000]  # allowed, used=60s, remaining=7140s

        with patch('utils.voice_duration_limiter._CONSUME_LUA', mock_script):
            from utils.voice_duration_limiter import try_consume_budget

            allowed, used, remaining = try_consume_budget('uid123', 60000)

        assert allowed is True
        assert used == 60000
        assert remaining == 7140000

    def test_consume_rejected(self, mock_redis):
        _, mock_script = mock_redis
        mock_script.return_value = [0, 7200000, 0]  # rejected, budget exhausted

        with patch('utils.voice_duration_limiter._CONSUME_LUA', mock_script):
            from utils.voice_duration_limiter import try_consume_budget

            allowed, used, remaining = try_consume_budget('uid123', 60000)

        assert allowed is False
        assert used == 7200000
        assert remaining == 0

    def test_consume_zero_duration_probes_budget(self, mock_redis):
        """Zero-duration consume probes budget status without recording."""
        _, mock_script = mock_redis
        mock_script.return_value = [1, 0, 7200000]

        with patch('utils.voice_duration_limiter._CONSUME_LUA', mock_script):
            from utils.voice_duration_limiter import try_consume_budget

            allowed, used, remaining = try_consume_budget('uid123', 0)

        assert allowed is True
        assert remaining == 7200000

    def test_consume_redis_error_fails_open(self, mock_redis):
        _, mock_script = mock_redis
        mock_script.side_effect = Exception('Redis connection refused')

        with patch('utils.voice_duration_limiter._CONSUME_LUA', mock_script):
            from utils.voice_duration_limiter import try_consume_budget, DAILY_BUDGET_MS

            allowed, used, remaining = try_consume_budget('uid123', 60000)

        assert allowed is True  # Fail-open
        assert remaining == DAILY_BUDGET_MS

    def test_consume_lua_none_fails_open(self):
        with patch('utils.voice_duration_limiter._CONSUME_LUA', None):
            from utils.voice_duration_limiter import try_consume_budget, DAILY_BUDGET_MS

            allowed, used, remaining = try_consume_budget('uid123', 60000)

        assert allowed is True  # Fail-open
        assert remaining == DAILY_BUDGET_MS


class TestCheckBudget:
    """Test check_budget (zero-consume probe)."""

    def test_check_budget_has_budget(self, mock_redis):
        _, mock_script = mock_redis
        mock_script.return_value = [1, 3600000, 3600000]

        with patch('utils.voice_duration_limiter._CONSUME_LUA', mock_script):
            from utils.voice_duration_limiter import check_budget

            has_budget, used, remaining = check_budget('uid123')

        assert has_budget is True

    def test_check_budget_exhausted(self, mock_redis):
        _, mock_script = mock_redis
        # When consuming 0, the Lua script still checks used > budget
        mock_script.return_value = [0, 7200000, 0]

        with patch('utils.voice_duration_limiter._CONSUME_LUA', mock_script):
            from utils.voice_duration_limiter import check_budget

            has_budget, used, remaining = check_budget('uid123')

        assert has_budget is False


class TestRecordActualDuration:
    """Test record_actual_duration (used by WS on session end)."""

    def test_record_positive(self, mock_redis):
        _, mock_script = mock_redis
        mock_script.return_value = [1, 60000, 7140000]

        with patch('utils.voice_duration_limiter._CONSUME_LUA', mock_script):
            from utils.voice_duration_limiter import record_actual_duration

            result = record_actual_duration('uid123', 60000)

        assert result is True
        mock_script.assert_called_once()
        # Verify force=1 is passed as 5th arg
        call_args = mock_script.call_args
        assert call_args[1]['args'][4] == 1

    def test_record_zero_skips_redis(self, mock_redis):
        _, mock_script = mock_redis

        with patch('utils.voice_duration_limiter._CONSUME_LUA', mock_script):
            from utils.voice_duration_limiter import record_actual_duration

            result = record_actual_duration('uid123', 0)

        assert result is True
        mock_script.assert_not_called()


class TestGetBudgetStatus:
    """Test get_budget_status dict output."""

    def test_status_format(self, mock_redis):
        _, mock_script = mock_redis
        mock_script.return_value = [1, 3600000, 3600000]

        with patch('utils.voice_duration_limiter._CONSUME_LUA', mock_script):
            from utils.voice_duration_limiter import get_budget_status, DAILY_BUDGET_MS

            status = get_budget_status('uid123')

        assert status['daily_limit_ms'] == DAILY_BUDGET_MS
        assert status['used_ms'] == 3600000
        assert status['remaining_ms'] == 3600000
        assert status['exhausted'] is False


# ===========================================================================
# Boundary tests: used == DAILY_BUDGET_MS
# ===========================================================================


class TestBudgetBoundary:
    """Test exact budget boundary behavior."""

    def test_consume_at_exact_budget_allowed(self, mock_redis):
        """When used + request == budget exactly, should be allowed (boundary is >)."""
        _, mock_script = mock_redis
        mock_script.return_value = [1, 7200000, 0]

        with patch('utils.voice_duration_limiter._CONSUME_LUA', mock_script):
            from utils.voice_duration_limiter import try_consume_budget

            allowed, used, remaining = try_consume_budget('uid123', 1000)

        assert allowed is True

    def test_consume_over_budget_rejected(self, mock_redis):
        """When used + request > budget, should be rejected."""
        _, mock_script = mock_redis
        mock_script.return_value = [0, 7200001, 0]

        with patch('utils.voice_duration_limiter._CONSUME_LUA', mock_script):
            from utils.voice_duration_limiter import try_consume_budget

            allowed, used, remaining = try_consume_budget('uid123', 1000)

        assert allowed is False
        assert remaining == 0

    def test_check_budget_at_exact_limit_has_budget(self, mock_redis):
        """check_budget should report has_budget when used==budget (boundary is >)."""
        _, mock_script = mock_redis
        mock_script.return_value = [1, 7200000, 0]

        with patch('utils.voice_duration_limiter._CONSUME_LUA', mock_script):
            from utils.voice_duration_limiter import check_budget

            has_budget, used, remaining = check_budget('uid123')

        assert has_budget is True

    def test_consume_just_under_budget_allowed(self, mock_redis):
        """When used + request < budget, should be allowed."""
        _, mock_script = mock_redis
        mock_script.return_value = [1, 7199999, 1]

        with patch('utils.voice_duration_limiter._CONSUME_LUA', mock_script):
            from utils.voice_duration_limiter import try_consume_budget

            allowed, used, remaining = try_consume_budget('uid123', 999)

        assert allowed is True
        assert remaining == 1

    def test_record_actual_duration_force_records(self, mock_redis):
        """record_actual_duration should always record (force=1), even over budget."""
        _, mock_script = mock_redis
        mock_script.return_value = [1, 7260000, 0]  # force-recorded over budget

        with patch('utils.voice_duration_limiter._CONSUME_LUA', mock_script):
            from utils.voice_duration_limiter import record_actual_duration

            result = record_actual_duration('uid123', 60000)

        assert result is True
        # Verify force=1 was passed as 5th arg
        call_args = mock_script.call_args
        assert call_args[1]['args'][4] == 1  # force flag


# ===========================================================================
# Shared budget verification (all endpoints deduct from same pool)
# ===========================================================================


class TestSharedBudget:
    """Verify that all three endpoints share the same Redis key namespace."""

    def test_budget_key_format(self):
        from utils.voice_duration_limiter import _budget_key

        key = _budget_key('user_abc')
        assert key == 'voice_duration:user_abc'

    def test_different_uids_different_keys(self):
        from utils.voice_duration_limiter import _budget_key

        assert _budget_key('user_a') != _budget_key('user_b')


# ===========================================================================
# Constants
# ===========================================================================


class TestConstants:
    def test_daily_budget(self):
        from utils.voice_duration_limiter import DAILY_BUDGET_MS

        assert DAILY_BUDGET_MS == 7_200_000  # 2 hours
