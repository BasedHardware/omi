"""Unit tests for VAD Streaming Gate (Issue #4644)."""

import os
import struct
import tempfile
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from utils.stt.vad_gate import (
    DgWallMapper,
    GateState,
    GatedDeepgramSocket,
    VADStreamingGate,
    is_gate_enabled,
    should_gate_session,
)

# Global speech flag for mock VAD
_mock_is_speech = False
_mock_vad_prob = None  # When set, overrides _mock_is_speech for exact probability control


class _MockVADModel:
    """Mock Silero VAD model that returns speech probability directly.

    Returns 0.9 for speech, 0.1 for silence — matching how the raw model
    works (continuous probability per window, NOT event-based like VADIterator).
    When _mock_vad_prob is set, returns that exact value for boundary testing.
    """

    def __call__(self, tensor, sample_rate):
        if _mock_vad_prob is not None:
            return _mock_vad_prob
        return 0.9 if _mock_is_speech else 0.1

    def reset_states(self):
        pass


@pytest.fixture(autouse=True)
def mock_silero():
    """Mock Silero VAD model to avoid torch dependency in tests.

    Patches the raw model (not VADIterator) and sets _vad_torch=None
    so _run_vad passes numpy arrays directly to the mock.
    """
    mock_model = _MockVADModel()
    with (
        patch('utils.stt.vad_gate._vad_model', mock_model),
        patch('utils.stt.vad_gate._vad_torch', None),
        patch('utils.stt.vad_gate._vad_model_pool', None),
        patch('utils.stt.vad_gate.VAD_GATE_MODEL_POOL_SIZE', 2),
    ):
        global _mock_is_speech, _mock_vad_prob
        _mock_is_speech = False
        _mock_vad_prob = None
        yield


def _make_pcm(duration_ms: int, sample_rate: int = 16000, channels: int = 1) -> bytes:
    """Generate silent PCM16 audio of given duration.

    For stereo (channels=2), generates interleaved L/R samples.
    """
    n_samples = int(sample_rate * channels * duration_ms / 1000)
    return struct.pack(f'<{n_samples}h', *([0] * n_samples))


def _set_vad_speech(is_speech: bool):
    """Configure mock VAD to return speech or silence."""
    global _mock_is_speech, _mock_vad_prob
    _mock_is_speech = is_speech
    _mock_vad_prob = None  # Clear exact prob when using bool mode


def _set_vad_prob(prob: float):
    """Configure mock VAD to return an exact probability value."""
    global _mock_vad_prob
    _mock_vad_prob = prob


def _make_pcm_with_amplitude(duration_ms: int, amplitude: float, sample_rate: int = 16000, channels: int = 1) -> bytes:
    """Generate PCM16 audio with a known amplitude (RMS ≈ amplitude/√2 for sine, amplitude for DC).

    Uses a DC offset for simplicity: all samples = amplitude * 32768.
    After float conversion, RMS = amplitude exactly.
    """
    n_samples = int(sample_rate * channels * duration_ms / 1000)
    value = int(amplitude * 32768)
    value = max(-32768, min(32767, value))
    return struct.pack(f'<{n_samples}h', *([value] * n_samples))


class TestVADStreamingGate:
    def _make_gate(self, mode='active', sample_rate=16000):
        return VADStreamingGate(
            sample_rate=sample_rate,
            channels=1,
            mode=mode,
            uid='test-uid',
            session_id='test-session',
        )

    def test_silence_produces_empty_output(self):
        """In active mode, silence should produce no audio to send."""
        gate = self._make_gate()
        _set_vad_speech(False)
        chunk = _make_pcm(30)
        out = gate.process_audio(chunk, time.time())
        assert out.audio_to_send == b''
        assert not out.should_finalize

    def test_speech_sends_audio_with_preroll(self):
        """Speech onset should send pre-roll buffer + current chunk."""
        gate = self._make_gate()
        t = time.time()

        # Feed 5 silence chunks (150ms) to fill pre-roll
        _set_vad_speech(False)
        for i in range(5):
            gate.process_audio(_make_pcm(30), t + i * 0.03)

        # Then speech
        _set_vad_speech(True)
        chunk = _make_pcm(30)
        out = gate.process_audio(chunk, t + 0.15)

        # Should have pre-roll + current chunk
        assert len(out.audio_to_send) > len(chunk)
        assert out.is_speech
        assert not out.should_finalize

    def test_speech_continues_sending(self):
        """During continuous speech, all audio should be sent (via pre-roll + direct).

        Note: First chunk may buffer in VAD (480 samples < 512 window), so speech
        detection triggers on chunk 2. Pre-roll then sends chunk 1+2 together.
        Total audio sent must equal total audio input.
        """
        gate = self._make_gate()
        _set_vad_speech(True)
        t = time.time()

        total_sent = b''
        total_input = b''
        for i in range(10):
            chunk = _make_pcm(30)
            total_input += chunk
            out = gate.process_audio(chunk, t + i * 0.03)
            total_sent += out.audio_to_send

        # All audio accounted for (pre-roll captures early chunks, sends on detection)
        assert len(total_sent) == len(total_input)

    def test_hangover_then_finalize(self):
        """After speech ends, hangover sends audio, then exactly one finalize fires."""
        gate = self._make_gate()
        t = time.time()

        # Speech for 5 chunks
        _set_vad_speech(True)
        for i in range(5):
            gate.process_audio(_make_pcm(30), t + i * 0.03)

        # Silence - should enter hangover, still sending
        _set_vad_speech(False)
        out = gate.process_audio(_make_pcm(30), t + 0.15)
        assert out.state == GateState.HANGOVER
        assert out.audio_to_send != b''
        assert not out.should_finalize

        # Continue silence past hangover (700ms default)
        finalize_count = 0
        for i in range(30):  # 900ms of silence
            out = gate.process_audio(_make_pcm(30), t + 0.18 + i * 0.03)
            if out.should_finalize:
                finalize_count += 1

        # Exactly one finalize event on hangover→silence transition
        assert finalize_count == 1
        assert out.state == GateState.SILENCE

    def test_hangover_boundary_timing(self):
        """Hangover must not expire before hangover_ms, must expire after."""
        gate = self._make_gate()
        t = time.time()

        # Speech for 5 chunks (150ms)
        _set_vad_speech(True)
        for i in range(5):
            gate.process_audio(_make_pcm(30), t + i * 0.03)

        # Silence starts
        _set_vad_speech(False)

        # Feed silence just under hangover (700ms): 22 chunks = 660ms since last speech
        for i in range(22):
            out = gate.process_audio(_make_pcm(30), t + 0.15 + i * 0.03)
        assert out.state == GateState.HANGOVER, "Should still be in HANGOVER at 660ms"
        assert not out.should_finalize

        # Next chunk pushes past 700ms: 23rd = 690ms, 24th = 720ms
        out = gate.process_audio(_make_pcm(30), t + 0.15 + 22 * 0.03)
        out = gate.process_audio(_make_pcm(30), t + 0.15 + 23 * 0.03)
        assert out.should_finalize or out.state == GateState.SILENCE

    def test_hangover_exact_boundary_stays_in_hangover(self):
        """At exactly hangover_ms, gate should still be in HANGOVER (uses > not >=)."""
        gate = self._make_gate()
        t = time.time()

        # Speech for 5 chunks (150ms), last speech at cursor=150ms
        _set_vad_speech(True)
        for i in range(5):
            gate.process_audio(_make_pcm(30), t + i * 0.03)

        # Silence: feed chunks until exactly 700ms since last speech
        # Last speech at 150ms cursor, hangover=700ms, so 700/30 = 23.33 chunks
        # 23 silence chunks = 690ms since last speech → still HANGOVER
        # 24th chunk pushes cursor to 720ms → should finalize
        _set_vad_speech(False)
        for i in range(23):
            out = gate.process_audio(_make_pcm(30), t + 0.15 + i * 0.03)
        # At 23 silence chunks (690ms since last speech), still in HANGOVER
        assert out.state == GateState.HANGOVER
        assert not out.should_finalize

        # 24th chunk: 720ms since last speech > 700ms → finalize
        out = gate.process_audio(_make_pcm(30), t + 0.15 + 23 * 0.03)
        assert out.should_finalize
        assert out.state == GateState.SILENCE

    def test_hangover_cancelled_by_speech(self):
        """If speech resumes during hangover, no finalize should happen."""
        gate = self._make_gate()
        t = time.time()

        # Speech
        _set_vad_speech(True)
        for i in range(5):
            gate.process_audio(_make_pcm(30), t + i * 0.03)

        # Brief silence (in hangover)
        _set_vad_speech(False)
        out = gate.process_audio(_make_pcm(30), t + 0.15)
        assert out.state == GateState.HANGOVER

        # Speech resumes
        _set_vad_speech(True)
        out = gate.process_audio(_make_pcm(30), t + 0.18)
        assert out.state == GateState.SPEECH
        assert not out.should_finalize
        assert out.audio_to_send != b''

    def test_continuous_speech_no_mid_utterance_drop(self):
        """Continuous speech must never transition to SILENCE mid-utterance.

        Regression test for P0: VADIterator returns None during ongoing speech
        (only emits start/end events). Raw model returns probability per window,
        so continuous speech should keep the gate in SPEECH state.
        """
        gate = self._make_gate()
        t = time.time()

        # 50 chunks of continuous speech (~1.5s) — well past hangover window
        _set_vad_speech(True)
        entered_speech = False
        for i in range(50):
            out = gate.process_audio(_make_pcm(30), t + i * 0.03)
            if out.state == GateState.SPEECH:
                entered_speech = True
            # Once in SPEECH, must never go to SILENCE during continuous speech
            if entered_speech:
                assert out.state in (
                    GateState.SPEECH,
                    GateState.HANGOVER,
                ), f"Dropped to {out.state} at chunk {i} during continuous speech"
                assert not out.should_finalize, f"Finalized at chunk {i} during continuous speech"

        assert entered_speech, "Never entered SPEECH state during continuous speech"

    def test_8khz_speech_detection(self):
        """VAD should detect speech at 8kHz via resampling to 16kHz."""
        gate = self._make_gate(sample_rate=8000)
        t = time.time()

        # Feed silence, then speech at 8kHz (30ms = 240 samples, resampled to 480)
        _set_vad_speech(False)
        for i in range(5):
            gate.process_audio(_make_pcm(30, sample_rate=8000), t + i * 0.03)

        _set_vad_speech(True)
        # Need multiple chunks for buffer to fill (240→480 resampled, window=512)
        total_sent = b''
        for i in range(5):
            out = gate.process_audio(_make_pcm(30, sample_rate=8000), t + 0.15 + i * 0.03)
            total_sent += out.audio_to_send

        assert len(total_sent) > 0, "8kHz speech should be detected after buffer fills"

    def test_preroll_capacity_truncation(self):
        """Pre-roll buffer should truncate to maxlen when silence exceeds capacity."""
        gate = self._make_gate()
        t = time.time()
        chunk = _make_pcm(30)

        # Feed 20 silence chunks (600ms) — exceeds 300ms pre-roll capacity (maxlen=11)
        _set_vad_speech(False)
        for i in range(20):
            gate.process_audio(chunk, t + i * 0.03)

        # Speech — pre-roll should contain at most 11 chunks
        _set_vad_speech(True)
        out = gate.process_audio(chunk, t + 0.60)
        # Pre-roll + current chunk in the output; max 11 chunks in deque + current
        assert len(out.audio_to_send) <= len(chunk) * 12
        assert len(out.audio_to_send) > 0

    def test_shadow_mode_sends_all_audio(self):
        """Shadow mode should always send all audio regardless of VAD."""
        gate = self._make_gate(mode='shadow')
        chunk = _make_pcm(30)

        _set_vad_speech(False)
        out = gate.process_audio(chunk, time.time())
        assert out.audio_to_send == chunk  # All audio sent even during silence

        _set_vad_speech(True)
        out = gate.process_audio(chunk, time.time())
        assert out.audio_to_send == chunk

    def test_metrics(self):
        """Gate should track speech/silence/finalize counts."""
        gate = self._make_gate()
        t = time.time()

        # 3 silence chunks
        _set_vad_speech(False)
        for i in range(3):
            gate.process_audio(_make_pcm(30), t + i * 0.03)

        # 2 speech chunks
        _set_vad_speech(True)
        for i in range(2):
            gate.process_audio(_make_pcm(30), t + 0.09 + i * 0.03)

        metrics = gate.get_metrics()
        assert metrics['chunks_total'] == 5
        assert metrics['chunks_silence'] == 3
        assert metrics['chunks_speech'] == 2
        assert metrics['mode'] == 'active'


class TestDgWallMapper:
    def test_no_checkpoints_passthrough(self):
        """With no checkpoints, DG time equals wall time."""
        mapper = DgWallMapper()
        assert mapper.dg_to_wall_rel(5.0) == 5.0

    def test_single_checkpoint_offset(self):
        """Single checkpoint maps DG time with correct offset."""
        mapper = DgWallMapper()

        # First speech at wall=0.0, DG=0.0
        mapper.on_audio_sent(5.0, 0.0)  # 5s of speech
        assert mapper.dg_to_wall_rel(2.5) == 2.5  # Within first segment, no offset

    def test_gap_creates_offset(self):
        """After a silence gap, DG timestamps should be offset to wall time."""
        mapper = DgWallMapper()

        # Speech 1: 5s of audio starting at wall=0.0
        mapper.on_audio_sent(5.0, 0.0)

        # Silence gap: 10s of real time (wall=5.0 to wall=15.0)
        mapper.on_silence_skipped()

        # Speech 2: resumes at wall=15.0, DG continues at 5.0
        mapper.on_audio_sent(3.0, 15.0)

        # DG time 2.0 → should map to wall 2.0 (first segment)
        assert mapper.dg_to_wall_rel(2.0) == 2.0

        # DG time 6.0 → should map to wall 16.0 (second segment, 1s in)
        assert mapper.dg_to_wall_rel(6.0) == 16.0

        # DG time 7.5 → should map to wall 17.5
        assert mapper.dg_to_wall_rel(7.5) == 17.5

    def test_multiple_gaps(self):
        """Multiple silence gaps should accumulate offsets correctly."""
        mapper = DgWallMapper()

        # Speech 1: 3s at wall=0
        mapper.on_audio_sent(3.0, 0.0)
        mapper.on_silence_skipped()

        # Gap 1: 5s (wall 3→8)
        # Speech 2: 2s at wall=8
        mapper.on_audio_sent(2.0, 8.0)
        mapper.on_silence_skipped()

        # Gap 2: 7s (wall 10→17)
        # Speech 3: 4s at wall=17
        mapper.on_audio_sent(4.0, 17.0)

        # DG=1.0 → wall=1.0 (segment 1)
        assert mapper.dg_to_wall_rel(1.0) == 1.0
        # DG=4.0 → wall=9.0 (segment 2, 1s in: 8.0 + (4.0-3.0))
        assert mapper.dg_to_wall_rel(4.0) == 9.0
        # DG=6.0 → wall=18.0 (segment 3, 1s in: 17.0 + (6.0-5.0))
        assert mapper.dg_to_wall_rel(6.0) == 18.0

    def test_boundary_values(self):
        """Test exact checkpoint boundaries."""
        mapper = DgWallMapper()

        mapper.on_audio_sent(5.0, 0.0)
        mapper.on_silence_skipped()
        mapper.on_audio_sent(5.0, 10.0)

        # Exactly at second checkpoint start
        assert mapper.dg_to_wall_rel(5.0) == 10.0

    def test_monotonicity_enforced(self):
        """Pre-roll subtraction can cause non-monotonic wall times.

        When a brief silence gap has a larger pre-roll buffer than the preceding
        transition, pre_roll_wall_rel = wall_rel - pre_roll_duration can go below
        the previous checkpoint's wall time. The mapper must clamp the new
        checkpoint's wall time to at least prev_wall + dg_elapsed, ensuring
        remapped timestamps are always monotonically increasing.
        """
        mapper = DgWallMapper()

        # Speech 1: 3s at wall=2.0 → dg [0, 3), wall [2, 5)
        mapper.on_audio_sent(3.0, 2.0)
        mapper.on_silence_skipped()

        # Speech 2: 1.5s at wall=34.77 → dg [3, 4.5)
        mapper.on_audio_sent(1.5, 34.77)
        mapper.on_silence_skipped()

        # Speech 3: pre-roll gives wall=34.67 (< 34.77!)
        # Clamped to prev_wall + dg_elapsed = 34.77 + (4.5-3.0) = 36.27
        mapper.on_audio_sent(2.0, 34.67)

        # dg=4.0 in segment 2 (CP2: dg=3.0, wall=34.77) → 34.77 + 1.0 = 35.77
        result_seg2 = mapper.dg_to_wall_rel(4.0)
        assert result_seg2 == pytest.approx(35.77, abs=0.01)

        # dg=5.0 in segment 3 (CP3: dg=4.5, wall=36.27) → 36.27 + 0.5 = 36.77
        result_seg3 = mapper.dg_to_wall_rel(5.0)
        assert result_seg3 == pytest.approx(36.77, abs=0.01)

        # Monotonicity: earlier DG time maps to earlier wall time
        assert result_seg2 < result_seg3, "Timestamps must be monotonically increasing"

    def test_checkpoint_compaction(self):
        """Compaction should keep first checkpoint as anchor + recent checkpoints."""
        mapper = DgWallMapper()
        # Override cap to small value for testing
        mapper._MAX_CHECKPOINTS = 5

        for i in range(10):
            mapper.on_audio_sent(1.0, float(i * 2))
            mapper.on_silence_skipped()

        # Should have at most 5 checkpoints
        assert len(mapper._checkpoints) <= 5
        # First checkpoint must remain as anchor for early timestamp remaps
        assert mapper._checkpoints[0] == (0.0, 0.0)
        assert mapper.dg_to_wall_rel(0.5) == 0.5
        # Most recent checkpoint should still work for remap
        last_dg = mapper._checkpoints[-1][0]
        result = mapper.dg_to_wall_rel(last_dg + 0.5)
        assert result == mapper._checkpoints[-1][1] + 0.5


class TestGateConfig:
    def test_gate_disabled_by_default(self):
        """Gate should be disabled when VAD_GATE_MODE=off."""
        with patch('utils.stt.vad_gate.VAD_GATE_MODE', 'off'):
            assert not is_gate_enabled()

    def test_gate_enabled_shadow(self):
        with patch('utils.stt.vad_gate.VAD_GATE_MODE', 'shadow'):
            assert is_gate_enabled()

    def test_gate_enabled_active(self):
        with patch('utils.stt.vad_gate.VAD_GATE_MODE', 'active'):
            assert is_gate_enabled()

    def test_rollout_percentage(self):
        """Rollout should be deterministic based on uid hash."""
        with patch('utils.stt.vad_gate.VAD_GATE_MODE', 'active'), patch('utils.stt.vad_gate.VAD_GATE_ROLLOUT_PCT', 50):
            # Same uid should always get same result
            result1 = should_gate_session('user-abc')
            result2 = should_gate_session('user-abc')
            assert result1 == result2

    def test_rollout_100_percent(self):
        """100% rollout should gate all sessions."""
        with patch('utils.stt.vad_gate.VAD_GATE_MODE', 'active'), patch('utils.stt.vad_gate.VAD_GATE_ROLLOUT_PCT', 100):
            assert should_gate_session('any-user')

    def test_rollout_0_percent(self):
        """0% rollout should never gate any session."""
        with patch('utils.stt.vad_gate.VAD_GATE_MODE', 'active'), patch('utils.stt.vad_gate.VAD_GATE_ROLLOUT_PCT', 0):
            assert not should_gate_session('any-user')
            assert not should_gate_session('another-user')

    def test_mode_off_overrides_rollout(self):
        """Mode=off should prevent gating even with 100% rollout."""
        with patch('utils.stt.vad_gate.VAD_GATE_MODE', 'off'), patch('utils.stt.vad_gate.VAD_GATE_ROLLOUT_PCT', 100):
            assert not should_gate_session('any-user')

    def test_rollout_negative_never_gates(self):
        """Negative rollout percentage should never gate any session."""
        with patch('utils.stt.vad_gate.VAD_GATE_MODE', 'active'), patch('utils.stt.vad_gate.VAD_GATE_ROLLOUT_PCT', -1):
            assert not should_gate_session('any-user')

    def test_rollout_over_100_always_gates(self):
        """Rollout > 100 should gate all sessions (same as 100)."""
        with patch('utils.stt.vad_gate.VAD_GATE_MODE', 'active'), patch('utils.stt.vad_gate.VAD_GATE_ROLLOUT_PCT', 200):
            assert should_gate_session('any-user')


class TestGatedDeepgramSocket:
    """Tests for the GatedDeepgramSocket wrapper."""

    def _make_gate(self, mode='active'):
        return VADStreamingGate(
            sample_rate=16000,
            channels=1,
            mode=mode,
            uid='test',
            session_id='test',
        )

    def test_passthrough_without_gate(self):
        """Without gate, send() passes audio directly to connection."""
        mock_conn = MagicMock()
        socket = GatedDeepgramSocket(mock_conn, gate=None)
        socket.send(b'\x00' * 960)
        mock_conn.send.assert_called_once_with(b'\x00' * 960)

    def test_gated_silence_not_forwarded(self):
        """With active gate, silence should not be forwarded to connection."""
        mock_conn = MagicMock()
        gate = self._make_gate()
        socket = GatedDeepgramSocket(mock_conn, gate=gate)

        _set_vad_speech(False)
        # Feed enough silence to fill VAD buffer
        for _ in range(5):
            socket.send(_make_pcm(30), wall_time=time.time())

        mock_conn.send.assert_not_called()

    def test_gated_speech_forwarded(self):
        """With active gate, speech should be forwarded to connection."""
        mock_conn = MagicMock()
        gate = self._make_gate()
        socket = GatedDeepgramSocket(mock_conn, gate=gate)

        _set_vad_speech(True)
        t = time.time()
        for i in range(5):
            socket.send(_make_pcm(30), wall_time=t + i * 0.03)

        assert mock_conn.send.call_count > 0

    def test_finalize_called_on_speech_end(self):
        """Wrapper should call finalize on speech→silence transition."""
        mock_conn = MagicMock()
        gate = self._make_gate()
        socket = GatedDeepgramSocket(mock_conn, gate=gate)

        t = time.time()
        # Speech
        _set_vad_speech(True)
        for i in range(5):
            socket.send(_make_pcm(30), wall_time=t + i * 0.03)

        # Silence past hangover
        _set_vad_speech(False)
        for i in range(30):
            socket.send(_make_pcm(30), wall_time=t + 0.15 + i * 0.03)

        mock_conn.finalize.assert_called()

    def test_send_finalize_exception_swallowed(self):
        """If finalize() throws during speech->silence in send(), it should be swallowed."""
        mock_conn = MagicMock()
        mock_conn.finalize.side_effect = RuntimeError("connection closed")
        gate = self._make_gate()
        socket = GatedDeepgramSocket(mock_conn, gate=gate)

        t = time.time()
        # Speech
        _set_vad_speech(True)
        for i in range(5):
            socket.send(_make_pcm(30), wall_time=t + i * 0.03)

        # Silence past hangover — should not raise despite finalize error
        _set_vad_speech(False)
        for i in range(30):
            socket.send(_make_pcm(30), wall_time=t + 0.15 + i * 0.03)

        mock_conn.finalize.assert_called()

    def test_finish_shadow_mode_no_finalize(self):
        """finish() in shadow mode should NOT call finalize before finish."""
        mock_conn = MagicMock()
        gate = self._make_gate(mode='shadow')
        socket = GatedDeepgramSocket(mock_conn, gate=gate)
        socket.finish()

        mock_conn.finalize.assert_not_called()
        mock_conn.finish.assert_called_once()

    def test_remap_segments_noop_without_gate(self):
        """remap_segments() should be a no-op when gate is None."""
        mock_conn = MagicMock()
        socket = GatedDeepgramSocket(mock_conn, gate=None)
        segments = [{'start': 1.0, 'end': 2.0, 'text': 'hello'}]
        socket.remap_segments(segments)
        assert segments[0]['start'] == 1.0
        assert segments[0]['end'] == 2.0

    def test_remap_segments_noop_shadow_mode(self):
        """remap_segments() should be a no-op in shadow mode."""
        mock_conn = MagicMock()
        gate = self._make_gate(mode='shadow')
        socket = GatedDeepgramSocket(mock_conn, gate=gate)
        segments = [{'start': 1.0, 'end': 2.0, 'text': 'hello'}]
        socket.remap_segments(segments)
        assert segments[0]['start'] == 1.0
        assert segments[0]['end'] == 2.0

    def test_finish_finalizes_when_gated(self):
        """finish() should call finalize before finish when gate is active."""
        mock_conn = MagicMock()
        gate = self._make_gate(mode='active')
        socket = GatedDeepgramSocket(mock_conn, gate=gate)
        socket.finish()

        mock_conn.finalize.assert_called_once()
        mock_conn.finish.assert_called_once()

    def test_remap_segments(self):
        """remap_segments should adjust DG timestamps to wall-clock."""
        mock_conn = MagicMock()
        gate = self._make_gate()
        socket = GatedDeepgramSocket(mock_conn, gate=gate)

        # Simulate a silence gap via mapper directly
        gate.dg_wall_mapper.on_audio_sent(5.0, 0.0)
        gate.dg_wall_mapper.on_silence_skipped()
        gate.dg_wall_mapper.on_audio_sent(3.0, 15.0)

        segments = [{'start': 6.0, 'end': 7.0, 'text': 'hello'}]
        socket.remap_segments(segments)
        assert segments[0]['start'] == 16.0
        assert segments[0]['end'] == 17.0

    def test_is_gated_property(self):
        """is_gated should reflect whether gate is present."""
        mock_conn = MagicMock()
        assert not GatedDeepgramSocket(mock_conn, gate=None).is_gated
        assert GatedDeepgramSocket(mock_conn, gate=self._make_gate()).is_gated

    def test_finalize_passthrough(self):
        """finalize() should call the underlying connection's finalize."""
        mock_conn = MagicMock()
        socket = GatedDeepgramSocket(mock_conn, gate=self._make_gate())
        socket.finalize()
        mock_conn.finalize.assert_called_once()

    def test_finish_swallows_finalize_exception(self):
        """finish() should swallow exceptions from finalize before calling finish."""
        mock_conn = MagicMock()
        mock_conn.finalize.side_effect = RuntimeError("connection closed")
        gate = self._make_gate(mode='active')
        socket = GatedDeepgramSocket(mock_conn, gate=gate)
        # Should not raise despite finalize error
        socket.finish()
        mock_conn.finalize.assert_called_once()
        mock_conn.finish.assert_called_once()

    def test_get_metrics_returns_dict_when_gated(self):
        """get_metrics() should return gate metrics when gate is present."""
        mock_conn = MagicMock()
        gate = self._make_gate()
        socket = GatedDeepgramSocket(mock_conn, gate=gate)
        metrics = socket.get_metrics()
        assert metrics is not None
        assert 'chunks_total' in metrics
        assert 'mode' in metrics
        assert metrics['mode'] == 'active'

    def test_get_metrics_returns_none_without_gate(self):
        """get_metrics() should return None when no gate is present."""
        mock_conn = MagicMock()
        socket = GatedDeepgramSocket(mock_conn, gate=None)
        assert socket.get_metrics() is None

    def test_keepalive_sent_during_extended_silence(self):
        """Keepalive should be sent after VAD_GATE_KEEPALIVE_SEC of silence."""
        mock_conn = MagicMock()
        gate = self._make_gate()
        socket = GatedDeepgramSocket(mock_conn, gate=gate)

        t = 1000.0
        # Feed enough speech to trigger detection (need >= 512 samples at 16kHz)
        _set_vad_speech(True)
        for i in range(5):
            socket.send(_make_pcm(30), wall_time=t + i * 0.03)

        # Silence to trigger hangover then SILENCE state
        _set_vad_speech(False)
        for i in range(30):
            socket.send(_make_pcm(30), wall_time=t + 0.15 + i * 0.03)

        # Now in SILENCE state. Set _last_send_wall_time directly for clarity
        last_send = gate._last_send_wall_time
        assert last_send is not None

        # Send a chunk 25s later — should trigger keepalive
        socket.send(_make_pcm(30), wall_time=last_send + 25.0)

        mock_conn.keep_alive.assert_called()
        assert gate._keepalive_count > 0

    def test_keepalive_records_via_gate_api(self):
        """Socket should call gate.record_keepalive instead of mutating internals."""
        mock_conn = MagicMock()
        gate = self._make_gate()
        gate.record_keepalive = MagicMock(wraps=gate.record_keepalive)
        socket = GatedDeepgramSocket(mock_conn, gate=gate)

        t = 1000.0
        _set_vad_speech(False)
        for i in range(5):
            socket.send(_make_pcm(30), wall_time=t + i * 0.03)

        socket.send(_make_pcm(30), wall_time=t + 25.0)

        mock_conn.keep_alive.assert_called_once()
        gate.record_keepalive.assert_called_once_with(t + 25.0)

    def test_keepalive_not_sent_in_shadow_mode(self):
        """Keepalive should NOT be sent in shadow mode (all audio forwarded)."""
        mock_conn = MagicMock()
        gate = self._make_gate(mode='shadow')
        socket = GatedDeepgramSocket(mock_conn, gate=gate)

        _set_vad_speech(False)
        t = 1000.0
        for i in range(5):
            socket.send(_make_pcm(30), wall_time=t + i * 0.03)
        # Skip 25 seconds
        socket.send(_make_pcm(30), wall_time=t + 25.0)

        mock_conn.keep_alive.assert_not_called()

    def test_finalize_error_tracked_in_metrics(self):
        """Finalize exceptions should increment finalize_errors counter."""
        mock_conn = MagicMock()
        mock_conn.finalize.side_effect = RuntimeError("connection closed")
        gate = self._make_gate()
        socket = GatedDeepgramSocket(mock_conn, gate=gate)

        t = 1000.0
        _set_vad_speech(True)
        for i in range(5):
            socket.send(_make_pcm(30), wall_time=t + i * 0.03)

        _set_vad_speech(False)
        for i in range(30):
            socket.send(_make_pcm(30), wall_time=t + 0.15 + i * 0.03)

        metrics = socket.get_metrics()
        assert metrics['finalize_errors'] > 0

    def test_keepalive_on_initial_prolonged_silence(self):
        """Keepalive should trigger even if no audio was ever sent (initial silence)."""
        mock_conn = MagicMock()
        gate = self._make_gate()
        socket = GatedDeepgramSocket(mock_conn, gate=gate)

        t = 1000.0
        # Only silence — _last_send_wall_time stays None, but _first_audio_wall_time is set
        _set_vad_speech(False)
        for i in range(5):
            socket.send(_make_pcm(30), wall_time=t + i * 0.03)

        # _last_send_wall_time should be None (no audio forwarded)
        assert gate._last_send_wall_time is None
        # _first_audio_wall_time should be set
        assert gate._first_audio_wall_time == t

        # Send chunk 25s after first audio — should trigger keepalive via fallback
        socket.send(_make_pcm(30), wall_time=t + 25.0)
        mock_conn.keep_alive.assert_called()
        assert gate._keepalive_count > 0

    def test_finish_tracks_finalize_errors(self):
        """finish() should increment finalize_errors when finalize throws."""
        mock_conn = MagicMock()
        mock_conn.finalize.side_effect = RuntimeError("connection closed")
        gate = self._make_gate(mode='active')
        socket = GatedDeepgramSocket(mock_conn, gate=gate)

        assert gate._finalize_errors == 0
        socket.finish()
        assert gate._finalize_errors == 1
        mock_conn.finish.assert_called_once()


class TestActivateMode:
    """Tests for shadow→active mode switching (preseconds solution)."""

    def _make_gate(self, mode='shadow'):
        return VADStreamingGate(
            sample_rate=16000,
            channels=1,
            mode=mode,
            uid='test',
            session_id='test',
        )

    def test_activate_switches_shadow_to_active(self):
        """activate() should switch mode from shadow to active."""
        gate = self._make_gate(mode='shadow')
        assert gate.mode == 'shadow'
        gate.activate()
        assert gate.mode == 'active'

    def test_activate_resets_state_to_silence(self):
        """activate() should reset state machine to SILENCE regardless of prior state."""
        gate = self._make_gate(mode='shadow')
        # Shadow mode doesn't update _state via the state machine, so set it directly
        gate._state = GateState.SPEECH

        gate.activate()
        assert gate._state == GateState.SILENCE
        assert gate.mode == 'active'

    def test_activate_noop_if_already_active(self):
        """activate() should be a no-op if already in active mode."""
        gate = self._make_gate(mode='active')
        gate._state = GateState.SPEECH
        gate.activate()
        # State should NOT be reset since mode was already active
        assert gate._state == GateState.SPEECH

    def test_shadow_then_active_gates_silence(self):
        """After activate(), silence should be gated (not forwarded)."""
        gate = self._make_gate(mode='shadow')
        t = 1000.0

        # Shadow mode: silence is forwarded
        _set_vad_speech(False)
        out = gate.process_audio(_make_pcm(30), t)
        assert out.audio_to_send != b''

        # Activate
        gate.activate()

        # Active mode: silence should be gated
        out = gate.process_audio(_make_pcm(30), t + 0.05)
        assert out.audio_to_send == b''

    def test_activate_clears_preroll(self):
        """activate() should clear pre-roll buffer."""
        gate = self._make_gate(mode='shadow')
        _set_vad_speech(False)
        for i in range(5):
            gate.process_audio(_make_pcm(30), time.time())
        assert gate._pre_roll_total_ms == 0.0  # Shadow mode doesn't use pre-roll

        gate.activate()
        assert len(gate._pre_roll) == 0
        assert gate._pre_roll_total_ms == 0.0

    def test_activate_syncs_mapper_cursor(self):
        """activate() should advance DgWallMapper cursor to match shadow phase audio."""
        gate = self._make_gate(mode='shadow')
        t = 1000.0

        # Send 10 chunks of 30ms in shadow (300ms total)
        _set_vad_speech(False)
        for i in range(10):
            gate.process_audio(_make_pcm(30), t + i * 0.03)

        assert gate._audio_cursor_ms == pytest.approx(300.0, abs=1.0)

        gate.activate()

        # Mapper DG cursor should be 0.3s (not 0.0)
        assert gate.dg_wall_mapper._dg_cursor_sec == pytest.approx(0.3, abs=0.01)

    def test_shadow_active_remap_continuous(self):
        """After shadow→active, remapped timestamps should be continuous, not over-shifted."""
        gate = self._make_gate(mode='shadow')
        t = 1000.0

        # Shadow phase: 35s of audio (1167 chunks at 30ms)
        _set_vad_speech(False)
        for i in range(1167):
            gate.process_audio(_make_pcm(30), t + i * 0.03)

        # Activate after 35s
        gate.activate()
        wall_at_activation = t + 1167 * 0.03

        # Active: 5s silence (skipped)
        for i in range(167):
            gate.process_audio(_make_pcm(30), wall_at_activation + i * 0.03)

        # Active: speech at wall ~40s
        _set_vad_speech(True)
        for i in range(5):
            gate.process_audio(_make_pcm(30), wall_at_activation + 5.0 + i * 0.03)

        # Simulate DG returning a timestamp during the active speech phase
        # DG time should be ~35.3s (35s shadow + 0.3s pre-roll of active speech)
        dg_time = 35.3
        remapped = gate.dg_wall_mapper.dg_to_wall_rel(dg_time)

        # Wall-relative time should be around 40s (activation + 5s silence + 0.3s into speech)
        # NOT 75s (which would happen if mapper cursor wasn't synced)
        assert remapped < 50.0, f"Remapped {remapped} is over-shifted (cursor sync bug)"
        assert remapped > 35.0, f"Remapped {remapped} is too early"


class TestCostMetrics:
    """Tests for bytes_sent/bytes_skipped tracking."""

    def _make_gate(self, mode='active'):
        return VADStreamingGate(
            sample_rate=16000,
            channels=1,
            mode=mode,
            uid='test',
            session_id='test',
        )

    def test_bytes_sent_tracked_on_speech(self):
        """bytes_sent should accumulate when audio is forwarded."""
        gate = self._make_gate()
        _set_vad_speech(True)
        t = time.time()
        # Need multiple chunks to fill VAD buffer (512 samples at 16kHz, each 30ms chunk = 480 samples)
        for i in range(3):
            gate.process_audio(_make_pcm(30), t + i * 0.03)
        metrics = gate.get_metrics()
        assert metrics['bytes_sent'] > 0

    def test_bytes_skipped_tracked_on_silence(self):
        """bytes_skipped should accumulate for silence not forwarded to DG."""
        gate = self._make_gate()
        _set_vad_speech(False)
        t = 1000.0
        # Feed 15 silence chunks (450ms) — exceeds 300ms pre-roll, causing eviction
        for i in range(15):
            gate.process_audio(_make_pcm(30), t + i * 0.03)
        metrics = gate.get_metrics()
        assert metrics['bytes_skipped'] > 0

    def test_bytes_skipped_counts_unsent_preroll_without_eviction(self):
        """Even short silence should count as skipped when never sent."""
        gate = self._make_gate()
        chunk = _make_pcm(30)
        _set_vad_speech(False)
        gate.process_audio(chunk, 1000.0)

        metrics = gate.get_metrics()
        assert metrics['bytes_received'] == len(chunk)
        assert metrics['bytes_sent'] == 0
        assert metrics['bytes_skipped'] == len(chunk)

    def test_bytes_saved_ratio(self):
        """bytes_saved_ratio should reflect skipped/(sent+skipped)."""
        gate = self._make_gate()
        t = 1000.0

        # 20 silence chunks (600ms) — exceeds 300ms pre-roll, evicting ~300ms
        _set_vad_speech(False)
        for i in range(20):
            gate.process_audio(_make_pcm(30), t + i * 0.03)

        # 5 speech chunks
        _set_vad_speech(True)
        for i in range(5):
            gate.process_audio(_make_pcm(30), t + 0.60 + i * 0.03)

        metrics = gate.get_metrics()
        assert metrics['bytes_saved_ratio'] > 0
        assert metrics['bytes_saved_ratio'] < 1.0

    def test_shadow_mode_tracks_bytes_sent(self):
        """In shadow mode, all bytes should be counted as sent."""
        gate = self._make_gate(mode='shadow')
        _set_vad_speech(False)
        chunk = _make_pcm(30)
        gate.process_audio(chunk, time.time())
        metrics = gate.get_metrics()
        assert metrics['bytes_sent'] == len(chunk)
        assert metrics['bytes_skipped'] == 0


class TestStructuredMetricsLog:
    def test_to_json_log_contains_derived_fields(self):
        gate = VADStreamingGate(sample_rate=16000, channels=1, mode='active', uid='u1', session_id='s1')
        t = 1000.0

        _set_vad_speech(False)
        gate.process_audio(_make_pcm(30), t)
        _set_vad_speech(True)
        gate.process_audio(_make_pcm(40), t + 0.03)

        payload = gate.to_json_log()
        assert payload['event'] == 'vad_gate_metrics'
        assert payload['uid'] == 'u1'
        assert payload['session_id'] == 's1'
        assert 'session_duration_sec' in payload
        assert 'speech_ratio' in payload
        assert 'estimated_savings_pct' in payload
        assert payload['estimated_savings_pct'] == pytest.approx(payload['bytes_saved_ratio'] * 100.0, abs=0.001)


class _StatefulMockModel:
    def __init__(self):
        self._state = 0

    def __call__(self, tensor, sample_rate):
        self._state += 1
        return 0.9 if self._state >= 2 else 0.1

    def reset_states(self):
        self._state = 0


class _SlowMockModel:
    def __init__(self, sleep_sec):
        self.sleep_sec = sleep_sec

    def __call__(self, tensor, sample_rate):
        time.sleep(self.sleep_sec)
        return 0.1

    def reset_states(self):
        pass


class TestModelPoolAndState:
    def test_session_state_persists_across_chunks(self):
        """Second chunk should see carried LSTM-like state and trigger speech."""
        model = _StatefulMockModel()
        with (
            patch('utils.stt.vad_gate._vad_model', model),
            patch('utils.stt.vad_gate._vad_torch', None),
            patch('utils.stt.vad_gate._vad_model_pool', None),
            patch('utils.stt.vad_gate.VAD_GATE_MODEL_POOL_SIZE', 1),
        ):
            gate = VADStreamingGate(sample_rate=16000, channels=1, mode='active', uid='test', session_id='test')
            out1 = gate.process_audio(_make_pcm(40), 1000.0)
            out2 = gate.process_audio(_make_pcm(40), 1000.04)

            assert not out1.is_speech
            assert out2.is_speech

    def test_model_pool_allows_parallel_inference(self):
        """Two sessions should infer concurrently when pool size > 1."""
        sleep_sec = 0.2
        model = _SlowMockModel(sleep_sec=sleep_sec)
        with (
            patch('utils.stt.vad_gate._vad_model', model),
            patch('utils.stt.vad_gate._vad_torch', None),
            patch('utils.stt.vad_gate._vad_model_pool', None),
            patch('utils.stt.vad_gate.VAD_GATE_MODEL_POOL_SIZE', 2),
        ):
            gate1 = VADStreamingGate(sample_rate=16000, channels=1, mode='active', uid='u1', session_id='s1')
            gate2 = VADStreamingGate(sample_rate=16000, channels=1, mode='active', uid='u2', session_id='s2')
            barrier = threading.Barrier(3)
            chunk = _make_pcm(40)  # >= 1 VAD window at 16kHz

            def _run(gate, wall_time):
                barrier.wait()
                gate.process_audio(chunk, wall_time)

            t1 = threading.Thread(target=_run, args=(gate1, 1000.0))
            t2 = threading.Thread(target=_run, args=(gate2, 1000.0))
            t1.start()
            t2.start()
            start = time.perf_counter()
            barrier.wait()
            t1.join()
            t2.join()
            elapsed = time.perf_counter() - start

            assert elapsed < sleep_sec * 1.75


class TestSpeechThreshold:
    """Tests for configurable speech threshold."""

    def test_threshold_from_env(self):
        """Speech threshold should be configurable via env var."""
        with patch('utils.stt.vad_gate.VAD_GATE_SPEECH_THRESHOLD', 0.3):
            gate = VADStreamingGate(sample_rate=16000, channels=1, mode='active')
            assert gate._speech_threshold == 0.3

    def test_threshold_from_env_high(self):
        """High threshold should require stronger speech signal."""
        with patch('utils.stt.vad_gate.VAD_GATE_SPEECH_THRESHOLD', 0.8):
            gate = VADStreamingGate(sample_rate=16000, channels=1, mode='active')
            assert gate._speech_threshold == 0.8

    def test_threshold_boundary_exact(self):
        """Probability exactly equal to threshold should NOT trigger speech (strict >)."""
        gate = VADStreamingGate(sample_rate=16000, channels=1, mode='active')
        threshold = gate._speech_threshold
        # Prob == threshold → silence (strict > comparison)
        # Use 40ms chunk to exceed VAD window (512 samples = 32ms at 16kHz)
        _set_vad_prob(threshold)
        t = 1000.0
        out = gate.process_audio(_make_pcm(40), t)
        assert gate._state == GateState.SILENCE
        assert out.audio_to_send == b''

    def test_threshold_boundary_just_above(self):
        """Probability just above threshold should trigger speech."""
        gate = VADStreamingGate(sample_rate=16000, channels=1, mode='active')
        threshold = gate._speech_threshold
        # Prob just above threshold → speech
        # Use 40ms chunk to exceed VAD window (512 samples = 32ms at 16kHz)
        _set_vad_prob(threshold + 0.001)
        t = 1000.0
        out = gate.process_audio(_make_pcm(40), t)
        assert gate._state == GateState.SPEECH
        assert len(out.audio_to_send) > 0


class TestTimeBasedPreRoll:
    """Tests for time-based pre-roll buffer eviction."""

    def _make_gate(self, mode='active'):
        return VADStreamingGate(
            sample_rate=16000,
            channels=1,
            mode=mode,
            uid='test',
            session_id='test',
        )

    def test_preroll_respects_ms_limit(self):
        """Pre-roll should evict oldest chunks when total exceeds pre_roll_ms."""
        gate = self._make_gate()
        t = 1000.0

        # Default pre_roll_ms = 300ms. Feed 20 chunks of 30ms = 600ms total.
        _set_vad_speech(False)
        for i in range(20):
            gate.process_audio(_make_pcm(30), t + i * 0.03)

        # Pre-roll should be around 300ms, not 600ms
        assert gate._pre_roll_total_ms <= gate._pre_roll_ms + 30  # Allow one chunk margin

    def test_preroll_works_with_variable_chunk_sizes(self):
        """Pre-roll should work correctly with 20ms and 40ms chunks."""
        gate = self._make_gate()
        t = 1000.0

        _set_vad_speech(False)
        # Mix of 20ms and 40ms chunks
        for i in range(10):
            if i % 2 == 0:
                gate.process_audio(_make_pcm(20), t + i * 0.03)
            else:
                gate.process_audio(_make_pcm(40), t + i * 0.03)

        assert gate._pre_roll_total_ms <= gate._pre_roll_ms + 40  # Allow one chunk margin

    def test_preroll_emitted_on_speech_onset(self):
        """All pre-roll audio should be sent when speech is detected."""
        gate = self._make_gate()
        t = 1000.0

        # Fill pre-roll with silence
        _set_vad_speech(False)
        for i in range(15):
            gate.process_audio(_make_pcm(30), t + i * 0.03)

        # Speech detected — pre-roll should be emitted
        _set_vad_speech(True)
        out = gate.process_audio(_make_pcm(30), t + 15 * 0.03)
        assert len(out.audio_to_send) > len(_make_pcm(30))  # More than just current chunk
        assert gate._pre_roll_total_ms == 0.0  # Pre-roll should be cleared


class TestMapperMonotonicity:
    """Property-style invariant tests for DgWallMapper."""

    def test_monotonicity_across_many_transitions(self):
        """Varied speech/silence transitions must produce monotonic wall times."""
        mapper = DgWallMapper()
        wall = 0.0
        # Simulate 20 speech/silence transitions with varying durations
        for i in range(20):
            speech_dur = 1.0 + (i % 5) * 0.5  # 1.0 to 3.5s
            silence_dur = 0.5 + (i % 3) * 2.0  # 0.5 to 4.5s
            mapper.on_audio_sent(speech_dur, wall)
            wall += speech_dur
            mapper.on_silence_skipped()
            wall += silence_dur

        # Sample 100 DG timestamps and verify monotonicity
        prev_wall = -1.0
        for j in range(100):
            dg_t = j * 0.5  # 0 to 49.5s DG time
            wall_t = mapper.dg_to_wall_rel(dg_t)
            assert wall_t >= prev_wall, f"Non-monotonic at dg={dg_t}: {wall_t} < {prev_wall}"
            prev_wall = wall_t

    def test_large_time_precision(self):
        """Mapper should handle large wall/DG times without precision loss."""
        mapper = DgWallMapper()
        # Start at t=1_000_000 (like a real epoch)
        mapper.on_audio_sent(5.0, 1_000_000.0)
        mapper.on_silence_skipped()
        mapper.on_audio_sent(3.0, 1_000_010.0)
        # DG=6.0 → wall=1_000_011.0
        assert mapper.dg_to_wall_rel(6.0) == pytest.approx(1_000_011.0, abs=0.001)


class TestKeepaliveBoundary:
    """Tests for keepalive timing precision."""

    def _make_gate(self, mode='active'):
        return VADStreamingGate(
            sample_rate=16000,
            channels=1,
            mode=mode,
            uid='test',
            session_id='test',
        )

    def test_keepalive_exact_boundary(self):
        """Keepalive should NOT fire at 19.99s, SHOULD fire at 20.0s."""
        gate = self._make_gate()
        gate._first_audio_wall_time = 1000.0
        gate._last_send_wall_time = 1000.0
        # At 19.99s: no keepalive
        assert not gate.needs_keepalive(1019.99)
        # At 20.0s: keepalive
        assert gate.needs_keepalive(1020.0)

    def test_keepalive_no_spam(self):
        """After keepalive fires, next chunk should NOT trigger another immediately."""
        mock_conn = MagicMock()
        gate = self._make_gate()
        socket = GatedDeepgramSocket(mock_conn, gate=gate)

        t = 1000.0
        # Feed speech then silence
        _set_vad_speech(True)
        for i in range(5):
            socket.send(_make_pcm(30), wall_time=t + i * 0.03)
        _set_vad_speech(False)
        for i in range(30):
            socket.send(_make_pcm(30), wall_time=t + 0.15 + i * 0.03)

        last_send = gate._last_send_wall_time
        # First keepalive at +25s
        socket.send(_make_pcm(30), wall_time=last_send + 25.0)
        assert mock_conn.keep_alive.call_count == 1

        # Next chunk 0.03s later should NOT trigger another keepalive
        socket.send(_make_pcm(30), wall_time=last_send + 25.03)
        assert mock_conn.keep_alive.call_count == 1  # Still just 1


class TestStereoAudio:
    """Tests for stereo audio path through VAD."""

    def test_stereo_speech_detection(self):
        """VAD should detect speech with stereo (2-channel) audio."""
        gate = VADStreamingGate(
            sample_rate=16000,
            channels=2,
            mode='active',
            uid='test',
            session_id='test',
        )
        t = 1000.0

        # Silence
        _set_vad_speech(False)
        for i in range(5):
            gate.process_audio(_make_pcm(30, channels=2), t + i * 0.03)

        # Speech
        _set_vad_speech(True)
        total_sent = b''
        for i in range(5):
            out = gate.process_audio(_make_pcm(30, channels=2), t + 0.15 + i * 0.03)
            total_sent += out.audio_to_send

        assert len(total_sent) > 0, "Stereo speech should be detected"


class TestFinishErrorPublicAPI:
    """Tests for finish() error tracking via public API (get_metrics)."""

    def test_finish_error_in_metrics(self):
        """get_metrics() should show finalize_errors after finish() failure."""
        mock_conn = MagicMock()
        mock_conn.finalize.side_effect = RuntimeError("closed")
        gate = VADStreamingGate(
            sample_rate=16000,
            channels=1,
            mode='active',
            uid='test',
            session_id='test',
        )
        socket = GatedDeepgramSocket(mock_conn, gate=gate)
        socket.finish()
        metrics = socket.get_metrics()
        assert metrics['finalize_errors'] == 1


class TestGateCreationIntegration:
    """Integration tests mirroring transcribe.py gate creation/activation wiring.

    These tests exercise the exact branching logic from:
    - routers/transcribe.py:742 (gate creation with preseconds → shadow)
    - routers/transcribe.py:1801 (activation in flush_stt_buffer)
    """

    def test_gate_not_created_when_disabled(self):
        """Gate should not be created when VAD_GATE_MODE=off."""
        with patch('utils.stt.vad_gate.VAD_GATE_MODE', 'off'):
            assert not is_gate_enabled()

    def test_transcribe_gate_creation_with_preseconds(self):
        """Mirror transcribe.py:742 — active mode + preseconds > 0 → shadow gate."""
        with (
            patch('utils.stt.vad_gate.VAD_GATE_MODE', 'active'),
            patch('utils.stt.vad_gate.VAD_GATE_ROLLOUT_PCT', 100),
        ):
            # Mirror transcribe.py:742-752
            uid = 'test-uid'
            speech_profile_preseconds = 8.0  # Has speech profile
            assert is_gate_enabled() and should_gate_session(uid)

            from utils.stt.vad_gate import VAD_GATE_MODE as _mode

            gate_mode = _mode
            if speech_profile_preseconds > 0 and _mode == 'active':
                gate_mode = 'shadow'

            vad_gate = VADStreamingGate(
                sample_rate=16000,
                channels=1,
                mode=gate_mode,
                uid=uid,
                session_id='sess',
            )
            assert vad_gate.mode == 'shadow'

    def test_transcribe_gate_creation_without_preseconds(self):
        """Mirror transcribe.py:742 — active mode + no preseconds → active gate."""
        with (
            patch('utils.stt.vad_gate.VAD_GATE_MODE', 'active'),
            patch('utils.stt.vad_gate.VAD_GATE_ROLLOUT_PCT', 100),
        ):
            uid = 'test-uid'
            speech_profile_preseconds = 0.0  # No speech profile
            assert is_gate_enabled() and should_gate_session(uid)

            from utils.stt.vad_gate import VAD_GATE_MODE as _mode

            gate_mode = _mode
            if speech_profile_preseconds > 0 and _mode == 'active':
                gate_mode = 'shadow'

            vad_gate = VADStreamingGate(
                sample_rate=16000,
                channels=1,
                mode=gate_mode,
                uid=uid,
                session_id='sess',
            )
            assert vad_gate.mode == 'active'

    def test_transcribe_flush_activation_path(self):
        """Mirror transcribe.py:1801 — profile complete triggers shadow→active."""
        with patch('utils.stt.vad_gate.VAD_GATE_MODE', 'active'):
            from utils.stt.vad_gate import VAD_GATE_MODE as _mode

            # Setup: gate in shadow mode (preseconds > 0)
            vad_gate = VADStreamingGate(
                sample_rate=16000,
                channels=1,
                mode='shadow',
                uid='test',
                session_id='sess',
            )
            t = 1000.0
            # Simulate 8s of shadow mode audio (profile phase)
            _set_vad_speech(False)
            for i in range(267):
                vad_gate.process_audio(_make_pcm(30), t + i * 0.03)

            # Mirror transcribe.py:1795-1802 activation condition
            deepgram_profile_socket = MagicMock()  # Non-None = profile was active
            profile_complete = True
            if profile_complete and deepgram_profile_socket:
                deepgram_profile_socket = None
                # transcribe.py:1801
                if vad_gate is not None and _mode == 'active' and vad_gate.mode == 'shadow':
                    vad_gate.activate()

            assert vad_gate.mode == 'active'
            assert vad_gate._state == GateState.SILENCE
            assert vad_gate.dg_wall_mapper._dg_cursor_sec == pytest.approx(8.0, abs=0.1)

    def test_transcribe_no_activation_without_profile_socket(self):
        """No activation when there's no profile socket (preseconds == 0)."""
        with patch('utils.stt.vad_gate.VAD_GATE_MODE', 'active'):
            from utils.stt.vad_gate import VAD_GATE_MODE as _mode

            vad_gate = VADStreamingGate(
                sample_rate=16000,
                channels=1,
                mode='active',
                uid='test',
                session_id='sess',
            )
            deepgram_profile_socket = None  # No profile socket
            profile_complete = True

            # Mirror transcribe.py:1795-1802
            if profile_complete and deepgram_profile_socket:
                if vad_gate is not None and _mode == 'active' and vad_gate.mode == 'shadow':
                    vad_gate.activate()

            # Gate stays in active mode, never went through shadow
            assert vad_gate.mode == 'active'

    def test_gate_init_failure_results_in_none(self):
        """Mirror transcribe.py:752 — if VADStreamingGate() raises, vad_gate stays None."""
        with (
            patch('utils.stt.vad_gate.VAD_GATE_MODE', 'active'),
            patch('utils.stt.vad_gate.VAD_GATE_ROLLOUT_PCT', 100),
        ):
            # Simulate construction failure (e.g. model load error)
            vad_gate = None
            try:
                with patch.object(VADStreamingGate, '__init__', side_effect=RuntimeError('model load failed')):
                    vad_gate = VADStreamingGate(
                        sample_rate=16000,
                        channels=1,
                        mode='active',
                        uid='test',
                        session_id='sess',
                    )
            except Exception:
                vad_gate = None

            # Transcription should continue without gate
            assert vad_gate is None

    def test_gated_socket_wraps_main_not_profile(self):
        """GatedDeepgramSocket wraps main DG socket; profile socket has no gate."""
        main_conn = MagicMock()
        profile_conn = MagicMock()
        gate = VADStreamingGate(
            sample_rate=16000,
            channels=1,
            mode='shadow',
            uid='test',
            session_id='sess',
        )
        # Mirror transcribe.py: main socket gets gated, profile doesn't
        main_socket = GatedDeepgramSocket(main_conn, gate=gate)
        profile_socket = GatedDeepgramSocket(profile_conn, gate=None)

        assert main_socket.is_gated
        assert not profile_socket.is_gated


class TestFailOpen:
    """Tests for fail-open resilience: VAD errors must not drop user audio."""

    def test_gated_socket_falls_back_on_process_error(self):
        """Runtime VAD error should disable gate and send data directly."""
        mock_conn = MagicMock()
        gate = VADStreamingGate(
            sample_rate=16000,
            channels=1,
            mode='active',
            uid='test',
            session_id='sess',
        )
        gated = GatedDeepgramSocket(mock_conn, gate=gate)
        assert gated.is_gated

        # Make process_audio raise
        with patch.object(gate, 'process_audio', side_effect=RuntimeError('model crash')):
            gated.send(b'\x00' * 640, wall_time=1.0)

        # Data should have been sent directly to DG
        mock_conn.send.assert_called_once_with(b'\x00' * 640)
        # Gate should be disabled for rest of session
        assert gated._gate is None
        assert not gated.is_gated
        # Mode set to 'off' to prevent stale timestamp remapping
        assert gate.mode == 'off'

    def test_gated_socket_sends_normally_after_fallback(self):
        """After fallback, subsequent sends go directly to DG (no gate)."""
        mock_conn = MagicMock()
        gate = VADStreamingGate(
            sample_rate=16000,
            channels=1,
            mode='active',
            uid='test',
            session_id='sess',
        )
        gated = GatedDeepgramSocket(mock_conn, gate=gate)

        # Trigger fallback
        with patch.object(gate, 'process_audio', side_effect=RuntimeError('crash')):
            gated.send(b'\x00' * 640, wall_time=1.0)

        mock_conn.reset_mock()
        # Subsequent send should go directly without gate
        gated.send(b'\x01' * 640, wall_time=2.0)
        mock_conn.send.assert_called_once_with(b'\x01' * 640)


class TestRemapSegments:
    """Tests for VADStreamingGate.remap_segments() — the extracted remap method."""

    def _make_gate(self, mode='active'):
        return VADStreamingGate(
            sample_rate=16000,
            channels=1,
            mode=mode,
            uid='test',
            session_id='test',
        )

    def test_remap_active_mode(self):
        """In active mode, segments should be remapped with mapper offsets."""
        gate = self._make_gate(mode='active')
        # Simulate a silence gap via mapper
        gate.dg_wall_mapper.on_audio_sent(5.0, 0.0)
        gate.dg_wall_mapper.on_silence_skipped()
        gate.dg_wall_mapper.on_audio_sent(3.0, 15.0)

        segments = [{'start': 6.0, 'end': 7.0, 'text': 'hello'}]
        gate.remap_segments(segments)
        assert segments[0]['start'] == 16.0
        assert segments[0]['end'] == 17.0

    def test_remap_shadow_mode_noop(self):
        """In shadow mode, segments should remain unchanged."""
        gate = self._make_gate(mode='shadow')
        gate.dg_wall_mapper.on_audio_sent(5.0, 0.0)
        gate.dg_wall_mapper.on_silence_skipped()
        gate.dg_wall_mapper.on_audio_sent(3.0, 15.0)

        segments = [{'start': 6.0, 'end': 7.0, 'text': 'hello'}]
        gate.remap_segments(segments)
        assert segments[0]['start'] == 6.0
        assert segments[0]['end'] == 7.0

    def test_remap_off_mode_noop(self):
        """In off mode (fail-open case), segments should remain unchanged."""
        gate = self._make_gate(mode='active')
        gate.mode = 'off'  # Simulate fail-open
        gate.dg_wall_mapper.on_audio_sent(5.0, 0.0)
        gate.dg_wall_mapper.on_silence_skipped()
        gate.dg_wall_mapper.on_audio_sent(3.0, 15.0)

        segments = [{'start': 6.0, 'end': 7.0, 'text': 'hello'}]
        gate.remap_segments(segments)
        assert segments[0]['start'] == 6.0
        assert segments[0]['end'] == 7.0

    def test_remap_empty_segments(self):
        """Empty segment list should be handled gracefully."""
        gate = self._make_gate(mode='active')
        segments = []
        gate.remap_segments(segments)
        assert segments == []

    def test_remap_zero_duration_segment(self):
        """Segment with start == end should be remapped correctly."""
        gate = self._make_gate(mode='active')
        gate.dg_wall_mapper.on_audio_sent(5.0, 0.0)
        gate.dg_wall_mapper.on_silence_skipped()
        gate.dg_wall_mapper.on_audio_sent(3.0, 15.0)

        segments = [{'start': 6.0, 'end': 6.0, 'text': ''}]
        gate.remap_segments(segments)
        assert segments[0]['start'] == 16.0
        assert segments[0]['end'] == 16.0

    def test_remap_preserves_other_fields(self):
        """Remap should only modify start/end, leaving text, speaker, etc. untouched."""
        gate = self._make_gate(mode='active')
        gate.dg_wall_mapper.on_audio_sent(5.0, 0.0)
        gate.dg_wall_mapper.on_silence_skipped()
        gate.dg_wall_mapper.on_audio_sent(3.0, 15.0)

        segments = [
            {
                'start': 6.0,
                'end': 7.0,
                'text': 'hello world',
                'speaker': 'SPEAKER_00',
                'is_user': True,
                'person_id': None,
            }
        ]
        gate.remap_segments(segments)
        assert segments[0]['text'] == 'hello world'
        assert segments[0]['speaker'] == 'SPEAKER_00'
        assert segments[0]['is_user'] is True
        assert segments[0]['person_id'] is None

    def test_remap_multiple_segments(self):
        """Multiple segments should all be remapped correctly."""
        gate = self._make_gate(mode='active')
        # Build a mapper with one silence gap: 5s audio, gap, 3s audio at wall=15s
        gate.dg_wall_mapper.on_audio_sent(5.0, 0.0)
        gate.dg_wall_mapper.on_silence_skipped()
        gate.dg_wall_mapper.on_audio_sent(3.0, 15.0)

        segments = [
            {'start': 1.0, 'end': 2.0, 'text': 'first'},
            {'start': 5.5, 'end': 6.5, 'text': 'second'},
            {'start': 7.0, 'end': 7.5, 'text': 'third'},
        ]
        gate.remap_segments(segments)
        # First segment is in the first audio block (0-5s maps to wall 0-5s)
        assert segments[0]['start'] == 1.0
        assert segments[0]['end'] == 2.0
        # Second segment is in the second audio block (5s+ maps to wall 15s+)
        assert segments[1]['start'] == 15.5
        assert segments[1]['end'] == 16.5
        # Third segment also in second block
        assert segments[2]['start'] == 17.0
        assert segments[2]['end'] == 17.5

    def test_remap_active_no_checkpoints_passthrough(self):
        """Active mode with no mapper checkpoints should still remap (identity mapping)."""
        gate = self._make_gate(mode='active')
        # No on_audio_sent calls — mapper has no checkpoints
        segments = [{'start': 3.0, 'end': 4.0, 'text': 'test'}]
        gate.remap_segments(segments)
        # With no checkpoints, dg_to_wall_rel returns the input unchanged
        assert segments[0]['start'] == 3.0
        assert segments[0]['end'] == 4.0

    def test_remap_malformed_segments_missing_keys(self):
        """Segments missing start/end keys should raise KeyError (not silently pass)."""
        gate = self._make_gate(mode='active')
        gate.dg_wall_mapper.on_audio_sent(5.0, 0.0)

        with pytest.raises(KeyError):
            gate.remap_segments([{'text': 'no timestamps'}])

    def test_remap_malformed_segments_none_values(self):
        """Segments with None start/end should raise TypeError during remap."""
        gate = self._make_gate(mode='active')
        gate.dg_wall_mapper.on_audio_sent(5.0, 0.0)

        with pytest.raises(TypeError):
            gate.remap_segments([{'start': None, 'end': None}])


class TestGatedSocketRemapDelegation:
    """Tests for GatedDeepgramSocket.remap_segments() delegation to gate."""

    def _make_gate(self, mode='active'):
        return VADStreamingGate(
            sample_rate=16000,
            channels=1,
            mode=mode,
            uid='test',
            session_id='test',
        )

    def test_gated_socket_remap_delegates_to_gate(self):
        """GatedDeepgramSocket.remap_segments() should delegate to gate.remap_segments()."""
        mock_conn = MagicMock()
        gate = self._make_gate(mode='active')
        gate.remap_segments = MagicMock(wraps=gate.remap_segments)
        socket = GatedDeepgramSocket(mock_conn, gate=gate)

        segments = [{'start': 1.0, 'end': 2.0, 'text': 'test'}]
        socket.remap_segments(segments)
        gate.remap_segments.assert_called_once_with(segments)

    def test_gated_socket_remap_noop_without_gate(self):
        """Without gate, remap_segments() should leave segments unchanged."""
        mock_conn = MagicMock()
        socket = GatedDeepgramSocket(mock_conn, gate=None)

        segments = [{'start': 1.0, 'end': 2.0, 'text': 'test'}]
        socket.remap_segments(segments)
        assert segments[0]['start'] == 1.0
        assert segments[0]['end'] == 2.0


class TestAudioCapture:
    """Tests for audio capture in GatedDeepgramSocket (transcript quality validation)."""

    def _make_gate(self, mode='active', session_id='test-session'):
        return VADStreamingGate(
            sample_rate=16000,
            channels=1,
            mode=mode,
            uid='test',
            session_id=session_id,
        )

    def test_capture_writes_raw_and_gated_files(self):
        """Both raw and gated PCM files should be written with correct content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {'VAD_GATE_AUDIO_CAPTURE_DIR': tmpdir}):
                mock_conn = MagicMock()
                gate = self._make_gate()
                socket = GatedDeepgramSocket(mock_conn, gate=gate)

                t = 1000.0
                speech_chunk = _make_pcm_with_amplitude(30, 0.5)
                silent_chunk = _make_pcm(30)

                # Send speech chunks (will be in both raw and gated)
                _set_vad_speech(True)
                for i in range(5):
                    socket.send(speech_chunk, wall_time=t + i * 0.03)

                # Send silence chunks past hangover (700ms default) — need >24 chunks of 30ms
                _set_vad_speech(False)
                for i in range(30):
                    socket.send(silent_chunk, wall_time=t + 0.15 + i * 0.03)

                socket.finish()

                raw_path = os.path.join(tmpdir, 'test-session_raw.pcm')
                gated_path = os.path.join(tmpdir, 'test-session_gated.pcm')

                assert os.path.exists(raw_path), 'Raw capture file should exist'
                assert os.path.exists(gated_path), 'Gated capture file should exist'

                raw_size = os.path.getsize(raw_path)
                gated_size = os.path.getsize(gated_path)

                # Raw should have all 35 chunks, gated should have fewer (speech + hangover only)
                assert raw_size == len(speech_chunk) * 5 + len(silent_chunk) * 30
                assert gated_size > 0, 'Gated file should have some speech audio'
                assert gated_size < raw_size, 'Gated file should be smaller than raw'

    def test_capture_disabled_when_no_dir(self):
        """No capture files should be created when env var is empty."""
        with patch.dict(os.environ, {'VAD_GATE_AUDIO_CAPTURE_DIR': ''}):
            mock_conn = MagicMock()
            gate = self._make_gate()
            socket = GatedDeepgramSocket(mock_conn, gate=gate)

            assert socket._raw_file is None
            assert socket._gated_file is None

            # Should still work without capture
            _set_vad_speech(True)
            socket.send(_make_pcm(30), wall_time=1000.0)
            socket.finish()

    def test_capture_files_closed_on_finish(self):
        """Capture files should be properly closed after finish()."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {'VAD_GATE_AUDIO_CAPTURE_DIR': tmpdir}):
                mock_conn = MagicMock()
                gate = self._make_gate()
                socket = GatedDeepgramSocket(mock_conn, gate=gate)

                assert socket._raw_file is not None
                assert socket._gated_file is not None
                assert not socket._raw_file.closed
                assert not socket._gated_file.closed

                socket.finish()

                assert socket._raw_file.closed
                assert socket._gated_file.closed
