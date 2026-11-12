"""Shared local-only Silero VAD; no cache, provider, or backend service imports."""

import logging
import math
import os
import threading
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    import onnxruntime as ort  # onnxruntime is untyped
except ImportError:  # pragma: no cover - pusher image ships without onnxruntime
    ort = None

logger = logging.getLogger(__name__)


class VADAudioDecodeError(RuntimeError):
    """Audio could not be decoded for a strict speech-eligibility decision."""


class VADProcessingError(RuntimeError):
    """The local VAD could not make a trustworthy speech decision."""


# ---------------------------------------------------------------------------
# Singleton ONNX Silero-VAD session (process-wide, thread-safe)
# ---------------------------------------------------------------------------
_ASSETS_DIR = os.path.join(os.path.dirname(__file__), 'assets')
_MODEL_PATH = os.path.join(_ASSETS_DIR, 'silero_vad.onnx')

_ort_session: Optional[Any] = None
_ort_init_lock = threading.Lock()

# ONNX model constants — Silero VAD v6 (full model, opset 16)
# At 16 kHz the model requires 512-sample windows (32 ms) plus a 64-sample
# context tail from the previous chunk prepended to each inference call.
# The context is critical — without it the recurrent state cannot track
# speech across chunks and probabilities stay near zero.
VAD_SAMPLE_RATE = 16000
VAD_WINDOW_SAMPLES = 512  # 32 ms at 16 kHz
VAD_CONTEXT_SAMPLES = 64  # prepended to each window
_STATE_SHAPE = (2, 1, 128)


def _get_ort_session() -> Any:
    """Lazy-init the shared ONNX InferenceSession (singleton, thread-safe).

    ORT InferenceSession.run() is thread-safe for different input data.
    Recurrent state is passed per-call, not stored on the session.
    """
    global _ort_session
    if _ort_session is not None:
        return _ort_session
    if ort is None:
        raise RuntimeError('onnxruntime is unavailable; local Silero VAD cannot run')
    with _ort_init_lock:
        if _ort_session is not None:
            return _ort_session
        opts: Any = ort.SessionOptions()  # type: ignore[reportUnknownMemberType]  # onnxruntime untyped
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL  # type: ignore[reportUnknownMemberType]  # onnxruntime untyped
        opts.log_severity_level = 3  # suppress ORT warnings
        _ort_session = ort.InferenceSession(_MODEL_PATH, sess_options=opts)
        logger.info('Silero-VAD ONNX session initialized (model=%s)', _MODEL_PATH)
        return _ort_session


def make_fresh_state() -> Tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    """Return zeroed recurrent state + context for a new VAD stream.

    Returns (state, context) where:
      state: float32 (2, 1, 128) — ONNX recurrent state
      context: float32 (1, 64) — tail of previous window
    """
    return np.zeros(_STATE_SHAPE, dtype=np.float32), np.zeros((1, VAD_CONTEXT_SAMPLES), dtype=np.float32)


def run_vad_window(
    audio_window: np.ndarray[Any, Any],
    state: np.ndarray[Any, Any],
    context: np.ndarray[Any, Any],
) -> Tuple[float, np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    """Run VAD on a single 512-sample window.

    Args:
        audio_window: float32 array of shape (512,) — 16 kHz mono
        state: float32 array of shape (2, 1, 128) — recurrent state
        context: float32 array of shape (1, 64) — context from previous window

    Returns:
        (speech_probability: float, new_state: np.ndarray, new_context: np.ndarray)
    """
    sess = _get_ort_session()
    audio_2d = audio_window.reshape(1, -1).astype(np.float32)
    # Prepend context from previous chunk — required by Silero ONNX wrapper
    x = np.concatenate([context, audio_2d], axis=1)  # shape: (1, 576)
    sr = np.array(VAD_SAMPLE_RATE, dtype=np.int64)
    output, new_state = sess.run(  # type: ignore[reportUnknownVariableType,reportUnknownMemberType]  # onnxruntime untyped
        None,
        {
            'input': x,
            'state': state,
            'sr': sr,
        },
    )
    new_context = audio_2d[:, -VAD_CONTEXT_SAMPLES:]  # save tail as next context
    return float(output[0][0]), new_state, new_context  # type: ignore[reportUnknownVariableType,reportUnknownArgumentType]  # onnxruntime untyped


def segments_from_16khz_samples(samples: np.ndarray[Any, Any], *, threshold: float = 0.5) -> List[Dict[str, Any]]:
    """Run Silero over 16 kHz mono samples and return speech segments."""
    state, context = make_fresh_state()
    is_speech_flags: List[bool] = []

    # Process in 512-sample windows
    offset = 0
    while offset + VAD_WINDOW_SAMPLES <= len(samples):
        window = samples[offset : offset + VAD_WINDOW_SAMPLES]
        prob, state, context = run_vad_window(window, state, context)
        if not math.isfinite(prob) or not 0 <= prob <= 1:
            raise VADProcessingError('invalid local VAD probability')
        is_speech_flags.append(prob > threshold)
        offset += VAD_WINDOW_SAMPLES
    # Convert per-window flags to time segments
    window_sec = VAD_WINDOW_SAMPLES / VAD_SAMPLE_RATE
    segments: List[Dict[str, Any]] = []
    in_speech = False
    start = 0.0
    for i, flag in enumerate(is_speech_flags):
        t = i * window_sec
        if flag and not in_speech:
            in_speech = True
            start = t
        elif not flag and in_speech:
            in_speech = False
            end = t
            segments.append({'start': start, 'end': end, 'duration': end - start})
    # Close any open segment
    if in_speech:
        end = len(is_speech_flags) * window_sec
        segments.append({'start': start, 'end': end, 'duration': end - start})

    return segments


def offline_pcm_speech_segments(pcm: bytes) -> List[Dict[str, Any]]:
    """Strict, local-only VAD for canonical stored 16kHz mono PCM16.

    Include the final partial window; VAD failure propagates to the compaction
    caller, which retains uncompressed behavior. No hosted request or cache.
    """
    if not pcm or len(pcm) % 2 or len(pcm) > 7200 * 32000:
        raise VADAudioDecodeError('invalid stored PCM shape')
    samples = np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768
    duration = len(samples) / VAD_SAMPLE_RATE
    remainder = len(samples) % VAD_WINDOW_SAMPLES
    if remainder:
        samples = np.pad(samples, (0, VAD_WINDOW_SAMPLES - remainder))
    result = segments_from_16khz_samples(samples)
    return [
        {**span, 'end': min(duration, span['end']), 'duration': min(duration, span['end']) - span['start']}
        for span in result
        if span['start'] < duration
    ]
