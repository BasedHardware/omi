"""
VAD Streaming Gate — Issue #4644

Server-side VAD gate that skips sending silence to Deepgram,
using KeepAlive to maintain the connection and Finalize to flush
pending transcripts on speech→silence transitions.

Modes (VAD_GATE_MODE env var):
  off    — disabled, all audio forwarded (default)
  shadow — VAD runs and logs decisions, but all audio still forwarded
  active — VAD gates audio: silence skipped, KeepAlive sent instead
"""

import audioop
import hashlib
import logging
import os
import sys
import threading
import time
from bisect import bisect_right
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

import numpy as np
import torch

logger = logging.getLogger('vad_gate')

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------
VAD_GATE_MODE = os.getenv('VAD_GATE_MODE', 'off')  # off | shadow | active
VAD_GATE_ROLLOUT_PCT = int(os.getenv('VAD_GATE_ROLLOUT_PCT', '100'))
VAD_GATE_PRE_ROLL_MS = int(os.getenv('VAD_GATE_PRE_ROLL_MS', '300'))
VAD_GATE_HANGOVER_MS = int(os.getenv('VAD_GATE_HANGOVER_MS', '700'))


def is_gate_enabled() -> bool:
    return VAD_GATE_MODE in ('shadow', 'active')


def should_gate_session(uid: str) -> bool:
    """Determine if this session should be gated based on rollout percentage.

    Uses MD5 for stable hashing across processes (Python hash() is randomized).
    """
    if not is_gate_enabled():
        return False
    if VAD_GATE_ROLLOUT_PCT >= 100:
        return True
    digest = hashlib.md5(uid.encode()).hexdigest()
    return (int(digest[:8], 16) % 100) < VAD_GATE_ROLLOUT_PCT


# ---------------------------------------------------------------------------
# Silero VAD model (shared, thread-safe via lock)
# ---------------------------------------------------------------------------
_vad_model = None  # Set LAST during init (used as fast-path sentinel)
_vad_torch = None  # torch module ref for tensor conversion (set before _vad_model)
_vad_model_lock = threading.Lock()
_vad_init_lock = threading.Lock()


def _ensure_vad_model():
    """Lazy-load Silero VAD model (reuses the one from vad.py if already loaded).

    Uses the raw model for per-window speech probability (not VADIterator
    which emits boundary events unsuitable for streaming gating).

    Checks sys.modules for an already-loaded vad.py model to avoid loading
    a duplicate Silero instance (~2MB). Falls back to torch.hub.load if
    vad.py hasn't been imported yet.

    Double-checked locking: _vad_model is set LAST so any thread that sees
    it non-None also sees _vad_torch already set.
    """
    global _vad_model, _vad_torch
    if _vad_model is not None:
        return
    with _vad_init_lock:
        if _vad_model is not None:
            return
        # Reuse model from vad.py if already loaded (avoids duplicate in memory)
        vad_mod = sys.modules.get('utils.stt.vad')
        if vad_mod is not None and hasattr(vad_mod, 'model'):
            _vad_torch = torch  # Set BEFORE _vad_model
            _vad_model = vad_mod.model
        else:
            torch.set_num_threads(1)
            model, _ = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad')
            _vad_torch = torch  # Set BEFORE _vad_model
            _vad_model = model


# ---------------------------------------------------------------------------
# Gate state machine
# ---------------------------------------------------------------------------
class GateState(str, Enum):
    SILENCE = 'silence'
    SPEECH = 'speech'
    HANGOVER = 'hangover'


@dataclass
class GateOutput:
    """Output from processing one audio chunk through the gate."""

    audio_to_send: bytes  # PCM bytes to forward to DG (may be empty)
    should_finalize: bool = False  # call dg_socket.finalize()
    state: GateState = GateState.SILENCE
    is_speech: bool = False  # raw VAD decision for this chunk


# ---------------------------------------------------------------------------
# DG ↔ Wall-clock timestamp mapper
# ---------------------------------------------------------------------------
class DgWallMapper:
    """Maps DG audio-time timestamps to wall-clock-relative timestamps.

    DG timestamps are continuous (only counting audio actually sent).
    When we skip silence via KeepAlive, DG time compresses vs wall time.
    This mapper tracks checkpoints at each silence→speech transition to
    convert DG timestamps back to wall-clock-relative timestamps.
    """

    _MAX_CHECKPOINTS = 500  # Cap to bound memory for long sessions

    def __init__(self):
        self._lock = threading.Lock()
        # Each checkpoint: (dg_sec, wall_rel_sec) at silence→speech transition
        self._checkpoints: List[Tuple[float, float]] = []
        self._dg_cursor_sec: float = 0.0
        self._sending: bool = False

    def on_audio_sent(self, chunk_duration_sec: float, chunk_wall_rel_sec: float) -> None:
        """Called when audio is actually sent to DG."""
        with self._lock:
            if not self._sending:
                # Enforce monotonicity: the new checkpoint's wall time must be at
                # least prev_wall + (dg_elapsed since prev checkpoint).  Pre-roll
                # subtraction can produce wall times below the previous checkpoint,
                # and simple clamping to prev_wall creates overlapping wall-time
                # ranges that cause non-monotonic remapped timestamps.
                if self._checkpoints:
                    prev_dg, prev_wall = self._checkpoints[-1]
                    min_wall = prev_wall + (self._dg_cursor_sec - prev_dg)
                    chunk_wall_rel_sec = max(chunk_wall_rel_sec, min_wall)
                self._checkpoints.append((self._dg_cursor_sec, chunk_wall_rel_sec))
                # Compact: keep only recent checkpoints to bound memory
                if len(self._checkpoints) > self._MAX_CHECKPOINTS:
                    self._checkpoints = self._checkpoints[-self._MAX_CHECKPOINTS :]
                self._sending = True
            self._dg_cursor_sec += chunk_duration_sec

    def on_silence_skipped(self) -> None:
        """Called when silence is skipped (not sent to DG)."""
        with self._lock:
            self._sending = False

    def dg_to_wall_rel(self, dg_sec: float) -> float:
        """Convert DG audio-time to wall-clock-relative time."""
        with self._lock:
            cps = self._checkpoints[:]
        if not cps:
            return dg_sec
        dg_marks = [c[0] for c in cps]
        i = max(bisect_right(dg_marks, dg_sec) - 1, 0)
        cp_dg, cp_wall = cps[i]
        return cp_wall + (dg_sec - cp_dg)


# ---------------------------------------------------------------------------
# VAD Streaming Gate (per-session)
# ---------------------------------------------------------------------------
class VADStreamingGate:
    """Per-session VAD gate that decides whether to send audio to DG.

    Uses Silero VAD model's speech probability (not start/end events) for
    robust per-chunk speech detection. Buffers VAD input samples to handle
    chunk sizes smaller than the VAD window (e.g. 30ms at 8kHz = 240 < 256).

    Args:
        sample_rate: Input audio sample rate (Hz)
        channels: Number of audio channels
        mode: 'shadow' or 'active'
        uid: User ID for logging
        session_id: Session ID for logging
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        mode: str = 'active',
        uid: str = '',
        session_id: str = '',
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.mode = mode
        self.uid = uid
        self.session_id = session_id

        # VAD setup — always resample to 16kHz for best accuracy
        # Uses raw model probability (not VADIterator events) for continuous
        # per-window speech classification suitable for streaming gating.
        self._vad_sample_rate = 16000
        _ensure_vad_model()
        self._vad_window_samples = 512  # Silero recommended for 16kHz
        self._vad_buffer = np.array([], dtype=np.float32)  # Buffer for cross-chunk accumulation
        self._speech_threshold = 0.5  # Probability threshold for speech

        # State machine
        self._state = GateState.SILENCE
        self._audio_cursor_ms: float = 0.0
        self._last_speech_ms: float = 0.0
        self._pre_roll_ms = VAD_GATE_PRE_ROLL_MS
        self._hangover_ms = VAD_GATE_HANGOVER_MS

        # Pre-roll buffer: stores recent audio chunks for playback on speech onset
        max_pre_roll_chunks = max(1, int(self._pre_roll_ms / 30) + 1)
        self._pre_roll: deque = deque(maxlen=max_pre_roll_chunks)

        # Timestamp mapper
        self.dg_wall_mapper = DgWallMapper()

        # Metrics (for shadow mode logging)
        self._chunks_total = 0
        self._chunks_speech = 0
        self._chunks_silence = 0
        self._finalize_count = 0
        self._first_audio_wall_time: Optional[float] = None

    def _convert_for_vad(self, pcm_data: bytes) -> np.ndarray:
        """Convert audio to float32 at 16kHz mono for VAD."""
        # Convert to mono if stereo
        data = pcm_data
        if self.channels == 2:
            data = audioop.tomono(data, 2, 0.5, 0.5)

        data_int16 = np.frombuffer(data, dtype=np.int16)

        # Resample to 16kHz if needed
        if self.sample_rate != self._vad_sample_rate:
            # Simple linear interpolation resampling
            ratio = self._vad_sample_rate / self.sample_rate
            n_out = int(len(data_int16) * ratio)
            indices = np.linspace(0, len(data_int16) - 1, n_out)
            data_int16 = np.interp(indices, np.arange(len(data_int16)), data_int16.astype(np.float64)).astype(np.int16)

        return data_int16.astype(np.float32) / 32768.0

    def _run_vad(self, pcm_data: bytes) -> bool:
        """Run Silero VAD on audio chunk. Returns True if speech detected.

        Calls the raw model directly for per-window speech probability.
        VADIterator is NOT used because it emits boundary events (start/end)
        and returns None during continuous speech, which would cause the gate
        to drop audio mid-utterance.

        Resets model hidden state before each batch so shared model state
        doesn't leak between sessions. Within a batch, LSTM context carries
        over naturally for better accuracy.

        Buffers samples across chunks to handle cases where chunk size < window size.
        """
        float_data = self._convert_for_vad(pcm_data)

        # Append to buffer
        self._vad_buffer = np.concatenate([self._vad_buffer, float_data])

        speech_detected = False
        with _vad_model_lock:
            _vad_model.reset_states()
            # Process all complete windows in buffer
            while len(self._vad_buffer) >= self._vad_window_samples:
                window = self._vad_buffer[: self._vad_window_samples]
                self._vad_buffer = self._vad_buffer[self._vad_window_samples :]

                # Convert to tensor for production Silero; mock accepts numpy
                if _vad_torch is not None:
                    tensor = _vad_torch.from_numpy(window.copy())
                else:
                    tensor = window
                prob = _vad_model(tensor, self._vad_sample_rate)
                # Silero returns tensor; mock returns float
                if hasattr(prob, 'item'):
                    prob = prob.item()
                if prob > self._speech_threshold:
                    speech_detected = True

        # Keep buffer bounded (max 1 window of leftover)
        if len(self._vad_buffer) > self._vad_window_samples:
            self._vad_buffer = self._vad_buffer[-self._vad_window_samples :]

        return speech_detected

    def process_audio(self, pcm_data: bytes, wall_time: float) -> GateOutput:
        """Process an audio chunk through the VAD gate.

        Args:
            pcm_data: Raw PCM16 audio bytes
            wall_time: Wall-clock timestamp of this chunk

        Returns:
            GateOutput with audio to send and control signals
        """
        if self._first_audio_wall_time is None:
            self._first_audio_wall_time = wall_time

        self._chunks_total += 1

        # Track audio time
        n_samples = len(pcm_data) // (2 * self.channels)
        chunk_ms = (n_samples * 1000.0) / self.sample_rate
        self._audio_cursor_ms += chunk_ms

        # Run VAD
        is_speech = self._run_vad(pcm_data)

        if is_speech:
            self._last_speech_ms = self._audio_cursor_ms
            self._chunks_speech += 1
        else:
            self._chunks_silence += 1

        # Shadow mode: log but send everything
        if self.mode == 'shadow':
            return GateOutput(
                audio_to_send=pcm_data,
                should_finalize=False,
                state=self._state,
                is_speech=is_speech,
            )

        # Active mode: state machine
        prev_state = self._state
        output = self._update_state(pcm_data, is_speech, wall_time)

        if prev_state != self._state:
            logger.info(
                'VADGate state %s->%s uid=%s session=%s speech=%s cursor=%.1fms',
                prev_state.value,
                self._state.value,
                self.uid,
                self.session_id,
                is_speech,
                self._audio_cursor_ms,
            )

        return output

    def _update_state(self, pcm_data: bytes, is_speech: bool, wall_time: float) -> GateOutput:
        """State machine transition logic."""
        wall_rel = wall_time - self._first_audio_wall_time if self._first_audio_wall_time else 0.0
        chunk_duration_sec = len(pcm_data) / (2.0 * self.channels * self.sample_rate)

        if self._state == GateState.SILENCE:
            # Buffer for pre-roll
            self._pre_roll.append(pcm_data)

            if is_speech:
                # Transition: SILENCE → SPEECH
                self._state = GateState.SPEECH
                # Emit pre-roll + current chunk
                pre_roll_audio = b''.join(self._pre_roll)
                self._pre_roll.clear()

                # Record mapper checkpoint for pre-roll start
                pre_roll_duration = len(pre_roll_audio) / (2.0 * self.channels * self.sample_rate)
                pre_roll_wall_rel = max(0.0, wall_rel - pre_roll_duration + chunk_duration_sec)
                self.dg_wall_mapper.on_audio_sent(pre_roll_duration, pre_roll_wall_rel)

                return GateOutput(
                    audio_to_send=pre_roll_audio,
                    should_finalize=False,
                    state=GateState.SPEECH,
                    is_speech=True,
                )
            else:
                # Stay in SILENCE: skip audio, mapper tracks gap
                self.dg_wall_mapper.on_silence_skipped()
                return GateOutput(
                    audio_to_send=b'',
                    should_finalize=False,
                    state=GateState.SILENCE,
                    is_speech=False,
                )

        elif self._state == GateState.SPEECH:
            # Send audio to DG
            self.dg_wall_mapper.on_audio_sent(chunk_duration_sec, wall_rel)

            if not is_speech:
                # Transition: SPEECH → HANGOVER
                self._state = GateState.HANGOVER

            return GateOutput(
                audio_to_send=pcm_data,
                should_finalize=False,
                state=self._state,
                is_speech=is_speech,
            )

        elif self._state == GateState.HANGOVER:
            time_since_speech_ms = self._audio_cursor_ms - self._last_speech_ms

            if is_speech:
                # Speech resumed: HANGOVER → SPEECH (no finalize needed)
                self._state = GateState.SPEECH
                self.dg_wall_mapper.on_audio_sent(chunk_duration_sec, wall_rel)
                return GateOutput(
                    audio_to_send=pcm_data,
                    should_finalize=False,
                    state=GateState.SPEECH,
                    is_speech=True,
                )

            if time_since_speech_ms > self._hangover_ms:
                # Hangover expired: HANGOVER → SILENCE + finalize
                self._state = GateState.SILENCE
                self._finalize_count += 1
                self._pre_roll.clear()
                self._pre_roll.append(pcm_data)
                self.dg_wall_mapper.on_silence_skipped()
                return GateOutput(
                    audio_to_send=b'',
                    should_finalize=True,
                    state=GateState.SILENCE,
                    is_speech=False,
                )

            # Still in hangover: send audio
            self.dg_wall_mapper.on_audio_sent(chunk_duration_sec, wall_rel)
            return GateOutput(
                audio_to_send=pcm_data,
                should_finalize=False,
                state=GateState.HANGOVER,
                is_speech=False,
            )

        # Fallback: send everything
        return GateOutput(audio_to_send=pcm_data, is_speech=is_speech)

    def get_metrics(self) -> dict:
        """Return gate metrics for logging/monitoring."""
        total = self._chunks_total or 1
        return {
            'chunks_total': self._chunks_total,
            'chunks_speech': self._chunks_speech,
            'chunks_silence': self._chunks_silence,
            'silence_ratio': self._chunks_silence / total,
            'finalize_count': self._finalize_count,
            'state': self._state.value,
            'mode': self.mode,
        }


# ---------------------------------------------------------------------------
# Gated Deepgram Socket — wraps raw DG connection with VAD gate
# ---------------------------------------------------------------------------
class GatedDeepgramSocket:
    """Wraps a Deepgram LiveConnection with built-in VAD gate.

    When gate is active:
      - send() runs VAD internally, only forwards speech audio to DG
      - Automatically calls finalize() on speech→silence transitions
      - finish() flushes pending transcript before closing
    When gate is None or mode='shadow':
      - Acts as transparent pass-through

    This keeps all VAD logic out of transcribe.py.
    """

    def __init__(self, dg_connection, gate: Optional['VADStreamingGate'] = None):
        self._conn = dg_connection
        self._gate = gate

    def send(self, data: bytes, wall_time: Optional[float] = None) -> None:
        """Send audio through VAD gate (if active), then to DG."""
        if self._gate is None:
            return self._conn.send(data)

        gate_out = self._gate.process_audio(data, wall_time or time.time())
        if gate_out.audio_to_send:
            self._conn.send(gate_out.audio_to_send)
        if gate_out.should_finalize:
            try:
                self._conn.finalize()
            except Exception:
                pass

    def finalize(self) -> None:
        """Flush pending transcript."""
        self._conn.finalize()

    def finish(self) -> None:
        """Close DG connection. Flushes first if gate is active."""
        if self._gate is not None and self._gate.mode == 'active':
            try:
                self._conn.finalize()
            except Exception:
                pass
        self._conn.finish()

    def remap_segments(self, segments: list) -> None:
        """Remap DG timestamps from audio-time to wall-clock-relative time."""
        if self._gate is not None and self._gate.mode == 'active':
            for seg in segments:
                seg['start'] = self._gate.dg_wall_mapper.dg_to_wall_rel(seg['start'])
                seg['end'] = self._gate.dg_wall_mapper.dg_to_wall_rel(seg['end'])

    def get_metrics(self) -> Optional[dict]:
        """Return gate metrics, or None if no gate."""
        if self._gate is not None:
            return self._gate.get_metrics()
        return None

    @property
    def is_gated(self) -> bool:
        return self._gate is not None
