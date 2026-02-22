"""Unit tests for VAD Streaming Gate (Issue #4644)."""

import struct
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


class _MockVADModel:
    """Mock Silero VAD model that returns speech probability directly.

    Returns 0.9 for speech, 0.1 for silence — matching how the raw model
    works (continuous probability per window, NOT event-based like VADIterator).
    """

    def __call__(self, tensor, sample_rate):
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
    real_lock = threading.Lock()
    with patch('utils.stt.vad_gate._vad_model', mock_model), patch('utils.stt.vad_gate._vad_torch', None), patch(
        'utils.stt.vad_gate._vad_model_lock', real_lock
    ):
        global _mock_is_speech
        _mock_is_speech = False
        yield


def _make_pcm(duration_ms: int, sample_rate: int = 16000, channels: int = 1) -> bytes:
    """Generate silent PCM16 audio of given duration."""
    n_samples = int(sample_rate * channels * duration_ms / 1000)
    return struct.pack(f'<{n_samples}h', *([0] * n_samples))


def _set_vad_speech(is_speech: bool):
    """Configure mock VAD to return speech or silence."""
    global _mock_is_speech
    _mock_is_speech = is_speech


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
