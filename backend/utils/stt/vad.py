import asyncio
import os
import threading

import numpy as np
import onnxruntime as ort
import requests
from fastapi import HTTPException
from pydub import AudioSegment

from database import redis_db
from utils.executors import critical_executor, storage_executor
from utils.http_client import get_stt_client
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton ONNX Silero-VAD session (process-wide, thread-safe)
# ---------------------------------------------------------------------------
_ASSETS_DIR = os.path.join(os.path.dirname(__file__), 'assets')
_MODEL_PATH = os.path.join(_ASSETS_DIR, 'silero_vad.onnx')

_ort_session = None
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


def _get_ort_session() -> ort.InferenceSession:
    """Lazy-init the shared ONNX InferenceSession (singleton, thread-safe).

    ORT InferenceSession.run() is thread-safe for different input data.
    Recurrent state is passed per-call, not stored on the session.
    """
    global _ort_session
    if _ort_session is not None:
        return _ort_session
    with _ort_init_lock:
        if _ort_session is not None:
            return _ort_session
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        opts.log_severity_level = 3  # suppress ORT warnings
        _ort_session = ort.InferenceSession(_MODEL_PATH, sess_options=opts)
        logger.info('Silero-VAD ONNX session initialized (model=%s)', _MODEL_PATH)
        return _ort_session


def make_fresh_state() -> tuple:
    """Return zeroed recurrent state + context for a new VAD stream.

    Returns (state, context) where:
      state: float32 (2, 1, 128) — ONNX recurrent state
      context: float32 (1, 64) — tail of previous window
    """
    return np.zeros(_STATE_SHAPE, dtype=np.float32), np.zeros((1, VAD_CONTEXT_SAMPLES), dtype=np.float32)


def run_vad_window(audio_window: np.ndarray, state: np.ndarray, context: np.ndarray) -> tuple:
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
    output, new_state = sess.run(
        None,
        {
            'input': x,
            'state': state,
            'sr': sr,
        },
    )
    new_context = audio_2d[:, -VAD_CONTEXT_SAMPLES:]  # save tail as next context
    return float(output[0][0]), new_state, new_context


def vad_is_empty(file_path, return_segments: bool = False, cache: bool = False):
    """Uses hosted pyannote VAD (best quality) with local ONNX Silero fallback."""
    caching_key = f'vad_is_empty:{file_path}'
    if cache:
        cached = redis_db.get_generic_cache(caching_key)
        if cached is not None:
            if return_segments:
                return cached
            return len(cached) == 0

    segments = None
    hosted_vad_url = os.getenv('HOSTED_VAD_API_URL')
    if hosted_vad_url:
        try:
            with open(file_path, 'rb') as file:
                files = {'file': (file_path.split('/')[-1], file, 'audio/wav')}
                response = requests.post(hosted_vad_url, files=files, timeout=300)
                response.raise_for_status()
                segments = response.json()
        except Exception as e:
            logger.warning(f'Hosted VAD unavailable, falling back to local ONNX VAD for {file_path}: {e}')

    if segments is None:
        segments = _run_file_vad(file_path)

    if cache:
        redis_db.set_generic_cache(caching_key, segments, ttl=60 * 60 * 24)
    if return_segments:
        return segments
    logger.info(f'vad_is_empty {len(segments) == 0}')
    return len(segments) == 0


def _run_file_vad(file_path: str, threshold: float = 0.5) -> list:
    """Process an entire audio file through Silero-VAD ONNX.

    Reads the file, resamples to 16 kHz mono, and iterates 512-sample windows
    with 64-sample context. Returns list of dicts: [{start, end, duration}, ...]
    """
    try:
        audio = AudioSegment.from_file(file_path)
    except Exception as e:
        logger.error(f'Failed to read audio file {file_path}: {e}')
        return []

    # Convert to 16 kHz mono float32
    audio = audio.set_frame_rate(VAD_SAMPLE_RATE).set_channels(1).set_sample_width(2)
    samples = np.array(audio.get_array_of_samples(), dtype=np.float32) / 32768.0
    del audio

    state, context = make_fresh_state()
    is_speech_flags = []

    # Process in 512-sample windows
    offset = 0
    while offset + VAD_WINDOW_SAMPLES <= len(samples):
        window = samples[offset : offset + VAD_WINDOW_SAMPLES]
        prob, state, context = run_vad_window(window, state, context)
        is_speech_flags.append(prob > threshold)
        offset += VAD_WINDOW_SAMPLES
    del samples

    # Convert per-window flags to time segments
    window_sec = VAD_WINDOW_SAMPLES / VAD_SAMPLE_RATE
    segments = []
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


def _read_file(path: str) -> bytes:
    with open(path, 'rb') as f:
        return f.read()


async def async_vad_is_empty(file_path, return_segments: bool = False, cache: bool = False):
    """Async version of vad_is_empty using httpx.AsyncClient for hosted VAD."""
    caching_key = f'vad_is_empty:{file_path}'
    if cache:
        if exists := redis_db.get_generic_cache(caching_key):
            if return_segments:
                return exists
            return len(exists) == 0

    segments = None
    hosted_vad_url = os.getenv('HOSTED_VAD_API_URL')
    if hosted_vad_url:
        try:
            loop = asyncio.get_running_loop()
            file_data = await loop.run_in_executor(storage_executor, _read_file, file_path)
            files = {'file': (file_path.split('/')[-1], file_data, 'audio/wav')}
            client = get_stt_client()
            response = await client.post(hosted_vad_url, files=files)
            response.raise_for_status()
            segments = response.json()
        except Exception as e:
            logger.warning(f'Hosted VAD unavailable, falling back to local VAD for {file_path}: {e}')

    if segments is None:
        loop = asyncio.get_running_loop()
        segments = await loop.run_in_executor(critical_executor, _run_file_vad, file_path)

    if cache:
        redis_db.set_generic_cache(caching_key, segments, ttl=60 * 60 * 24)
    if return_segments:
        return segments
    logger.info(f'async_vad_is_empty {len(segments) == 0}')
    return len(segments) == 0


def apply_vad_for_speech_profile(file_path: str):
    logger.info(f'apply_vad_for_speech_profile {file_path}')
    voice_segments = vad_is_empty(file_path, return_segments=True)
    if len(voice_segments) == 0:  # TODO: front error on post-processing, audio sent is bad.
        raise HTTPException(status_code=400, detail="Audio is empty")
    joined_segments = []
    for i, segment in enumerate(voice_segments):
        if joined_segments and (segment['start'] - joined_segments[-1]['end']) < 1:
            joined_segments[-1]['end'] = segment['end']
        else:
            joined_segments.append(segment)

    # Load audio file once instead of repeatedly in the loop
    full_audio = AudioSegment.from_wav(file_path)

    try:
        # trim silence out of file_path, but leave 1 sec of silence within chunks
        trimmed_aseg = AudioSegment.empty()
        for i, segment in enumerate(joined_segments):
            start = segment['start'] * 1000
            end = segment['end'] * 1000
            trimmed_aseg += full_audio[start:end]
            if i < len(joined_segments) - 1:
                trimmed_aseg += full_audio[end : end + 1000]

        # file_path.replace('.wav', '-cleaned.wav')
        trimmed_aseg.export(file_path, format="wav")
    finally:
        # Explicitly free memory
        del full_audio
        del trimmed_aseg
