"""Tests for utils.stt.vad — ONNX Silero VAD + hosted fallback.

Covers:
- vad_is_empty() hosted success, hosted failure → ONNX fallback, cache behavior
- _run_file_vad() segment generation, empty/short file, threshold/window boundaries
- ONNX session singleton wiring
"""

import io
import os
import struct
import tempfile
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Pre-mock heavy imports before importing the module under test
# ---------------------------------------------------------------------------
_mock_ort = MagicMock()
_mock_redis = MagicMock()

import sys

sys.modules.setdefault('onnxruntime', _mock_ort)
sys.modules.setdefault('database', MagicMock())
sys.modules.setdefault('database.redis_db', _mock_redis)

from utils.stt import vad
from utils.stt.vad import (
    vad_is_empty,
    _run_file_vad,
    _get_ort_session,
    make_fresh_state,
    run_vad_window,
    VAD_SAMPLE_RATE,
    VAD_WINDOW_SAMPLES,
    VAD_CONTEXT_SAMPLES,
    _STATE_SHAPE,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_wav_bytes(duration_sec: float, freq_hz: float = 0.0, sample_rate: int = 16000) -> bytes:
    """Generate a minimal WAV file in memory.

    freq_hz=0 produces silence; freq_hz>0 produces a sine tone.
    """
    n_samples = int(sample_rate * duration_sec)
    if freq_hz > 0:
        t = np.linspace(0, duration_sec, n_samples, endpoint=False)
        samples = (np.sin(2 * np.pi * freq_hz * t) * 32000).astype(np.int16)
    else:
        samples = np.zeros(n_samples, dtype=np.int16)

    buf = io.BytesIO()
    n_channels = 1
    sample_width = 2
    byte_rate = sample_rate * n_channels * sample_width
    block_align = n_channels * sample_width
    data_size = n_samples * sample_width

    # WAV header
    buf.write(b'RIFF')
    buf.write(struct.pack('<I', 36 + data_size))
    buf.write(b'WAVE')
    buf.write(b'fmt ')
    buf.write(struct.pack('<IHHIIHH', 16, 1, n_channels, sample_rate, byte_rate, block_align, sample_width * 8))
    buf.write(b'data')
    buf.write(struct.pack('<I', data_size))
    buf.write(samples.tobytes())
    return buf.getvalue()


def _write_wav_file(path: str, duration_sec: float, freq_hz: float = 0.0):
    """Write a WAV file to disk."""
    data = _make_wav_bytes(duration_sec, freq_hz)
    with open(path, 'wb') as f:
        f.write(data)


def _mock_run_vad_window_speech(window, state, context):
    """Mock that always detects speech (prob=0.9)."""
    new_state = state.copy()
    new_state += 0.01
    new_context = context.copy()
    return 0.9, new_state, new_context


def _mock_run_vad_window_silence(window, state, context):
    """Mock that never detects speech (prob=0.1)."""
    new_state = state.copy()
    new_context = context.copy()
    return 0.1, new_state, new_context


def _mock_run_vad_window_pattern(pattern):
    """Return a mock that follows a per-window speech/silence pattern.

    pattern: list of bools — True=speech, False=silence.
    Repeats the last value for windows beyond the pattern length.
    """
    call_count = [0]

    def _fn(window, state, context):
        idx = call_count[0]
        call_count[0] += 1
        is_speech = pattern[idx] if idx < len(pattern) else pattern[-1]
        new_state = state.copy()
        new_state += 0.01
        new_context = context.copy()
        return (0.9 if is_speech else 0.1), new_state, new_context

    return _fn


def _mock_make_fresh_state():
    """Return (state, context) tuple matching make_fresh_state signature."""
    return np.zeros(_STATE_SHAPE, dtype=np.float32), np.zeros((1, VAD_CONTEXT_SAMPLES), dtype=np.float32)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the module-level ORT singleton between tests."""
    original = vad._ort_session
    vad._ort_session = None
    yield
    vad._ort_session = original


@pytest.fixture
def tmp_wav_dir(tmp_path):
    return tmp_path


# ---------------------------------------------------------------------------
# Tests: vad_is_empty — hosted success
# ---------------------------------------------------------------------------


class TestVadIsEmptyHostedSuccess:
    """vad_is_empty() when HOSTED_VAD_API_URL is set and succeeds."""

    @patch.dict(os.environ, {'HOSTED_VAD_API_URL': 'http://vad.test/v1/vad'})
    @patch('utils.stt.vad.requests.post')
    @patch.object(vad, 'redis_db')
    def test_hosted_returns_segments(self, mock_redis, mock_post, tmp_wav_dir):
        """Hosted VAD returns segments — vad_is_empty returns False (not empty)."""
        wav_path = str(tmp_wav_dir / 'test.wav')
        _write_wav_file(wav_path, 1.0)

        hosted_segments = [{'start': 0.0, 'end': 0.5, 'duration': 0.5}]
        mock_resp = MagicMock()
        mock_resp.json.return_value = hosted_segments
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        result = vad_is_empty(wav_path)
        assert result is False
        mock_post.assert_called_once()

    @patch.dict(os.environ, {'HOSTED_VAD_API_URL': 'http://vad.test/v1/vad'})
    @patch('utils.stt.vad.requests.post')
    @patch.object(vad, 'redis_db')
    def test_hosted_returns_empty(self, mock_redis, mock_post, tmp_wav_dir):
        """Hosted VAD returns empty list — vad_is_empty returns True."""
        wav_path = str(tmp_wav_dir / 'test.wav')
        _write_wav_file(wav_path, 1.0)

        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        result = vad_is_empty(wav_path)
        assert result is True

    @patch.dict(os.environ, {'HOSTED_VAD_API_URL': 'http://vad.test/v1/vad'})
    @patch('utils.stt.vad.requests.post')
    @patch.object(vad, 'redis_db')
    def test_hosted_return_segments_mode(self, mock_redis, mock_post, tmp_wav_dir):
        """return_segments=True returns the hosted segment list directly."""
        wav_path = str(tmp_wav_dir / 'test.wav')
        _write_wav_file(wav_path, 1.0)

        hosted_segments = [{'start': 0.0, 'end': 1.0, 'duration': 1.0}]
        mock_resp = MagicMock()
        mock_resp.json.return_value = hosted_segments
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        result = vad_is_empty(wav_path, return_segments=True)
        assert result == hosted_segments


# ---------------------------------------------------------------------------
# Tests: vad_is_empty — hosted failure → ONNX fallback
# ---------------------------------------------------------------------------


class TestVadIsEmptyFallback:
    """vad_is_empty() falls back to local ONNX when hosted VAD fails."""

    @patch.dict(os.environ, {'HOSTED_VAD_API_URL': 'http://vad.test/v1/vad'})
    @patch('utils.stt.vad.requests.post', side_effect=Exception('connection refused'))
    @patch('utils.stt.vad._run_file_vad')
    @patch.object(vad, 'redis_db')
    def test_hosted_exception_falls_back(self, mock_redis, mock_local, mock_post, tmp_wav_dir):
        """HTTP exception triggers local ONNX fallback."""
        wav_path = str(tmp_wav_dir / 'test.wav')
        _write_wav_file(wav_path, 1.0)

        mock_local.return_value = [{'start': 0.0, 'end': 0.5, 'duration': 0.5}]

        result = vad_is_empty(wav_path)
        assert result is False
        mock_local.assert_called_once_with(wav_path)

    @patch.dict(os.environ, {'HOSTED_VAD_API_URL': 'http://vad.test/v1/vad'})
    @patch('utils.stt.vad.requests.post')
    @patch('utils.stt.vad._run_file_vad')
    @patch.object(vad, 'redis_db')
    def test_hosted_http_error_falls_back(self, mock_redis, mock_local, mock_post, tmp_wav_dir):
        """HTTP 500 triggers local ONNX fallback."""
        wav_path = str(tmp_wav_dir / 'test.wav')
        _write_wav_file(wav_path, 1.0)

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception('500 Server Error')
        mock_post.return_value = mock_resp

        mock_local.return_value = []

        result = vad_is_empty(wav_path)
        assert result is True
        mock_local.assert_called_once_with(wav_path)

    @patch.dict(os.environ, {}, clear=False)
    @patch('utils.stt.vad._run_file_vad')
    @patch.object(vad, 'redis_db')
    def test_no_hosted_url_goes_straight_to_local(self, mock_redis, mock_local):
        """Without HOSTED_VAD_API_URL, goes directly to local ONNX."""
        # Remove env var if present
        os.environ.pop('HOSTED_VAD_API_URL', None)

        mock_local.return_value = [{'start': 0.0, 'end': 1.0, 'duration': 1.0}]

        result = vad_is_empty('/fake/path.wav')
        assert result is False
        mock_local.assert_called_once_with('/fake/path.wav')


# ---------------------------------------------------------------------------
# Tests: vad_is_empty — cache behavior
# ---------------------------------------------------------------------------


class TestVadIsEmptyCache:
    """vad_is_empty() cache (redis) integration."""

    @patch.object(vad, 'redis_db')
    @patch('utils.stt.vad._run_file_vad')
    def test_cache_hit_returns_cached_segments(self, mock_local, mock_redis):
        """Cache hit returns cached result without calling VAD."""
        os.environ.pop('HOSTED_VAD_API_URL', None)

        cached = [{'start': 0.0, 'end': 2.0, 'duration': 2.0}]
        mock_redis.get_generic_cache.return_value = cached

        result = vad_is_empty('/fake/path.wav', cache=True)
        # cached segments are non-empty → not empty → False
        assert result is False
        mock_local.assert_not_called()

    @patch.object(vad, 'redis_db')
    @patch('utils.stt.vad._run_file_vad')
    def test_cache_hit_return_segments(self, mock_local, mock_redis):
        """Cache hit with return_segments=True returns segments directly."""
        os.environ.pop('HOSTED_VAD_API_URL', None)

        cached = [{'start': 0.5, 'end': 1.5, 'duration': 1.0}]
        mock_redis.get_generic_cache.return_value = cached

        result = vad_is_empty('/fake/path.wav', return_segments=True, cache=True)
        assert result == cached
        mock_local.assert_not_called()

    @patch.object(vad, 'redis_db')
    @patch('utils.stt.vad._run_file_vad')
    def test_cache_hit_empty_list_honored(self, mock_local, mock_redis):
        """Cached empty list [] is a valid cache hit (audio was empty), not a miss."""
        os.environ.pop('HOSTED_VAD_API_URL', None)

        mock_redis.get_generic_cache.return_value = []

        result = vad_is_empty('/fake/path.wav', cache=True)
        assert result is True  # empty segments → audio is empty
        mock_local.assert_not_called()  # should NOT recompute

    @patch.object(vad, 'redis_db')
    @patch('utils.stt.vad._run_file_vad')
    def test_cache_miss_runs_vad_and_stores(self, mock_local, mock_redis):
        """Cache miss runs VAD and stores result in cache."""
        os.environ.pop('HOSTED_VAD_API_URL', None)

        mock_redis.get_generic_cache.return_value = None
        mock_local.return_value = [{'start': 0.0, 'end': 0.5, 'duration': 0.5}]

        result = vad_is_empty('/fake/path.wav', cache=True)
        assert result is False
        mock_redis.set_generic_cache.assert_called_once()
        call_args = mock_redis.set_generic_cache.call_args
        assert call_args[0][0] == 'vad_is_empty:/fake/path.wav'
        assert call_args[1]['ttl'] == 86400

    @patch.object(vad, 'redis_db')
    @patch('utils.stt.vad._run_file_vad')
    def test_no_cache_flag_skips_cache(self, mock_local, mock_redis):
        """cache=False (default) skips cache entirely."""
        os.environ.pop('HOSTED_VAD_API_URL', None)

        mock_local.return_value = []

        result = vad_is_empty('/fake/path.wav', cache=False)
        assert result is True
        mock_redis.get_generic_cache.assert_not_called()
        mock_redis.set_generic_cache.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: _run_file_vad — segment generation
# ---------------------------------------------------------------------------


class TestRunFileVad:
    """_run_file_vad() processes audio files through ONNX Silero VAD."""

    @patch('utils.stt.vad.run_vad_window', side_effect=_mock_run_vad_window_silence)
    @patch('utils.stt.vad.make_fresh_state', side_effect=_mock_make_fresh_state)
    def test_silence_returns_empty(self, mock_state, mock_vad, tmp_wav_dir):
        """Silent audio produces no segments."""
        wav_path = str(tmp_wav_dir / 'silence.wav')
        _write_wav_file(wav_path, 0.5)

        segments = _run_file_vad(wav_path)
        assert segments == []

    @patch('utils.stt.vad.run_vad_window', side_effect=_mock_run_vad_window_speech)
    @patch('utils.stt.vad.make_fresh_state', side_effect=_mock_make_fresh_state)
    def test_all_speech_single_segment(self, mock_state, mock_vad, tmp_wav_dir):
        """Audio with all-speech produces one segment spanning the whole file."""
        wav_path = str(tmp_wav_dir / 'speech.wav')
        _write_wav_file(wav_path, 0.1, freq_hz=440.0)

        segments = _run_file_vad(wav_path)
        assert len(segments) == 1
        assert segments[0]['start'] == 0.0
        assert segments[0]['end'] > 0
        assert segments[0]['duration'] > 0

    @patch('utils.stt.vad.make_fresh_state', side_effect=_mock_make_fresh_state)
    def test_speech_silence_speech_produces_two_segments(self, mock_state, tmp_wav_dir):
        """Speech-silence-speech pattern produces two segments."""
        wav_path = str(tmp_wav_dir / 'pattern.wav')
        # 0.5s = ~15 windows at 512 samples/16kHz (32ms each)
        _write_wav_file(wav_path, 0.5, freq_hz=440.0)

        # Pattern: 2 speech, 2 silence, 2 speech
        pattern = [True, True, False, False, True, True]
        mock_fn = _mock_run_vad_window_pattern(pattern)

        with patch('utils.stt.vad.run_vad_window', side_effect=mock_fn):
            segments = _run_file_vad(wav_path)

        assert len(segments) == 2
        # First segment starts at 0
        assert segments[0]['start'] == 0.0
        # Second segment starts after the silence gap
        assert segments[1]['start'] > segments[0]['end']

    def test_nonexistent_file_returns_empty(self):
        """Missing file returns empty list (no crash)."""
        segments = _run_file_vad('/nonexistent/path/audio.wav')
        assert segments == []

    def test_corrupt_file_returns_empty(self, tmp_wav_dir):
        """Corrupt/unreadable file returns empty list."""
        bad_path = str(tmp_wav_dir / 'corrupt.wav')
        with open(bad_path, 'wb') as f:
            f.write(b'NOT A WAV FILE')

        segments = _run_file_vad(bad_path)
        assert segments == []

    @patch('utils.stt.vad.run_vad_window', side_effect=_mock_run_vad_window_speech)
    @patch('utils.stt.vad.make_fresh_state', side_effect=_mock_make_fresh_state)
    def test_short_file_fewer_than_one_window(self, mock_state, mock_vad, tmp_wav_dir):
        """File shorter than one 512-sample window produces no segments."""
        wav_path = str(tmp_wav_dir / 'tiny.wav')
        # 511 samples at 16kHz = ~31.9ms, just under one 512-sample window
        duration = 511 / 16000
        _write_wav_file(wav_path, duration, freq_hz=440.0)

        segments = _run_file_vad(wav_path)
        # Less than one full window → no windows processed → no segments
        assert segments == []
        mock_vad.assert_not_called()

    @patch('utils.stt.vad.make_fresh_state', side_effect=_mock_make_fresh_state)
    def test_open_segment_closed_at_end(self, mock_state, tmp_wav_dir):
        """Speech at end of file is properly closed."""
        wav_path = str(tmp_wav_dir / 'trail.wav')
        _write_wav_file(wav_path, 0.2, freq_hz=440.0)

        # Pattern: silence then speech (not closed by silence)
        pattern = [False, True, True]
        mock_fn = _mock_run_vad_window_pattern(pattern)

        with patch('utils.stt.vad.run_vad_window', side_effect=mock_fn):
            segments = _run_file_vad(wav_path)

        assert len(segments) == 1
        # Segment starts at window 1 (32ms)
        window_sec = VAD_WINDOW_SAMPLES / VAD_SAMPLE_RATE
        assert abs(segments[0]['start'] - window_sec) < 1e-6


# ---------------------------------------------------------------------------
# Tests: ONNX session wiring
# ---------------------------------------------------------------------------


class TestOnnxSessionWiring:
    """Verify _get_ort_session() singleton behavior."""

    def test_make_fresh_state_shape(self):
        """make_fresh_state returns correct shapes and dtype."""
        state, context = make_fresh_state()
        assert state.shape == _STATE_SHAPE
        assert state.dtype == np.float32
        assert np.all(state == 0)
        assert context.shape == (1, VAD_CONTEXT_SAMPLES)
        assert context.dtype == np.float32
        assert np.all(context == 0)

    def test_make_fresh_state_independent(self):
        """Two calls return independent arrays."""
        s1, c1 = make_fresh_state()
        s2, c2 = make_fresh_state()
        s1[0, 0, 0] = 99.0
        c1[0, 0] = 99.0
        assert s2[0, 0, 0] == 0.0
        assert c2[0, 0] == 0.0

    @patch('utils.stt.vad.ort')
    def test_singleton_reuses_session(self, mock_ort_module):
        """_get_ort_session() returns the same object on repeated calls."""
        mock_session = MagicMock()
        mock_ort_module.InferenceSession.return_value = mock_session
        mock_ort_module.SessionOptions.return_value = MagicMock()
        mock_ort_module.ExecutionMode.ORT_SEQUENTIAL = 0

        vad._ort_session = None
        s1 = _get_ort_session()
        s2 = _get_ort_session()
        assert s1 is s2
        # Only one InferenceSession created
        mock_ort_module.InferenceSession.assert_called_once()

    @patch('utils.stt.vad.ort')
    def test_session_options_configured(self, mock_ort_module):
        """Session options set single-threaded sequential mode."""
        mock_opts = MagicMock()
        mock_ort_module.SessionOptions.return_value = mock_opts
        mock_ort_module.ExecutionMode.ORT_SEQUENTIAL = 0
        mock_ort_module.InferenceSession.return_value = MagicMock()

        vad._ort_session = None
        _get_ort_session()

        assert mock_opts.intra_op_num_threads == 1
        assert mock_opts.inter_op_num_threads == 1
        assert mock_opts.log_severity_level == 3


# ---------------------------------------------------------------------------
# Tests: run_vad_window
# ---------------------------------------------------------------------------


class TestRunVadWindow:
    """Verify run_vad_window() input shaping and output extraction."""

    @patch('utils.stt.vad._get_ort_session')
    def test_input_shapes_and_output(self, mock_get_sess):
        """run_vad_window passes correctly shaped inputs to ORT."""
        mock_sess = MagicMock()
        mock_output = np.array([[0.85]], dtype=np.float32)
        mock_new_state = np.ones(_STATE_SHAPE, dtype=np.float32)
        mock_sess.run.return_value = (mock_output, mock_new_state)
        mock_get_sess.return_value = mock_sess

        window = np.random.randn(VAD_WINDOW_SAMPLES).astype(np.float32)
        state, context = make_fresh_state()

        prob, new_state, new_context = run_vad_window(window, state, context)

        assert isinstance(prob, float)
        assert abs(prob - 0.85) < 1e-5
        assert new_state is mock_new_state
        # Context should be last VAD_CONTEXT_SAMPLES of the window
        assert new_context.shape == (1, VAD_CONTEXT_SAMPLES)

        # Check the input dict passed to sess.run
        call_args = mock_sess.run.call_args
        feed_dict = call_args[1] if call_args[1] else call_args[0][1]
        # Input should be context (64) + window (512) = 576
        assert feed_dict['input'].shape == (1, VAD_CONTEXT_SAMPLES + VAD_WINDOW_SAMPLES)
        assert feed_dict['state'].shape == _STATE_SHAPE
        assert feed_dict['sr'].dtype == np.int64
