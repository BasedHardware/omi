import logging
import math
import os
from typing import Any, Dict, List, Literal, Optional, Tuple, Union, overload

import httpx
import numpy as np

import requests
from pydub import AudioSegment  # pydub is untyped

from utils.stt.local_vad import (
    VADAudioDecodeError,
    VADProcessingError,
    VAD_SAMPLE_RATE,
    segments_from_16khz_samples as _segments_from_16khz_samples,
)
from database import redis_db
from utils.executors import db_executor, storage_executor, sync_executor, run_blocking
from utils.http_client import get_stt_client
from utils.log_sanitizer import sanitize_provider_error
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

HOSTED_VAD_CONNECT_TIMEOUT_SECONDS_ENV = 'HOSTED_VAD_CONNECT_TIMEOUT_SECONDS'
HOSTED_VAD_READ_TIMEOUT_SECONDS_ENV = 'HOSTED_VAD_READ_TIMEOUT_SECONDS'
VAD_CACHE_TTL_SECONDS_ENV = 'VAD_CACHE_TTL_SECONDS'
DEFAULT_HOSTED_VAD_CONNECT_TIMEOUT_SECONDS = 3.0
DEFAULT_HOSTED_VAD_READ_TIMEOUT_SECONDS = 30.0
MAX_HOSTED_VAD_CONNECT_TIMEOUT_SECONDS = 30.0
MAX_HOSTED_VAD_READ_TIMEOUT_SECONDS = 60.0
DEFAULT_VAD_CACHE_TTL_SECONDS = 86400
MIN_VAD_CACHE_TTL_SECONDS = 300
MAX_VAD_CACHE_TTL_SECONDS = 86400


class VADEmptyError(ValueError):
    """The VAD found no speech segments in the audio."""


def _positive_timeout_seconds(env_name: str, default: float, maximum: float) -> float:
    raw_value = os.getenv(env_name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
        if math.isfinite(value) and 0 < value <= maximum:
            return value
    except ValueError:
        pass
    logger.warning(
        'Invalid or excessive %s=%r; using safe default %.1fs (maximum %.1fs)',
        env_name,
        raw_value,
        default,
        maximum,
    )
    return default


def _hosted_vad_timeout_seconds() -> Tuple[float, float]:
    """Return bounded hosted-VAD connect/read deadlines from current env."""

    return (
        _positive_timeout_seconds(
            HOSTED_VAD_CONNECT_TIMEOUT_SECONDS_ENV,
            DEFAULT_HOSTED_VAD_CONNECT_TIMEOUT_SECONDS,
            MAX_HOSTED_VAD_CONNECT_TIMEOUT_SECONDS,
        ),
        _positive_timeout_seconds(
            HOSTED_VAD_READ_TIMEOUT_SECONDS_ENV,
            DEFAULT_HOSTED_VAD_READ_TIMEOUT_SECONDS,
            MAX_HOSTED_VAD_READ_TIMEOUT_SECONDS,
        ),
    )


def _vad_cache_ttl_seconds() -> int:
    """Return the current bounded sync-VAD cache TTL, preserving the 24h default."""
    raw_value = os.getenv(VAD_CACHE_TTL_SECONDS_ENV)
    if raw_value is None:
        return DEFAULT_VAD_CACHE_TTL_SECONDS
    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_VAD_CACHE_TTL_SECONDS
    if MIN_VAD_CACHE_TTL_SECONDS <= value <= MAX_VAD_CACHE_TTL_SECONDS:
        return value
    return DEFAULT_VAD_CACHE_TTL_SECONDS


def _hosted_vad_httpx_timeout() -> httpx.Timeout:
    connect_timeout, read_timeout = _hosted_vad_timeout_seconds()
    return httpx.Timeout(
        connect=connect_timeout,
        read=read_timeout,
        write=read_timeout,
        pool=connect_timeout,
    )


def _hosted_vad_fallback_reason(exc: BaseException) -> str:
    if isinstance(exc, (requests.Timeout, httpx.TimeoutException)):
        return 'timeout'
    response = getattr(exc, 'response', None)
    if response is not None:
        status_code = getattr(response, 'status_code', None)
        if isinstance(status_code, int):
            if status_code == 429:
                return 'provider_429'
            if status_code >= 500:
                return 'provider_5xx'
    return 'other'


def _record_hosted_vad_fallback(exc: BaseException) -> None:
    record_fallback(
        component='vad',
        from_mode='hosted',
        to_mode='local_onnx',
        reason=_hosted_vad_fallback_reason(exc),
        outcome='degraded',
    )


@overload
def vad_is_empty(file_path: str, return_segments: Literal[True], cache: bool = False) -> List[Dict[str, Any]]: ...


@overload
def vad_is_empty(file_path: str, return_segments: Literal[False] = False, cache: bool = False) -> bool: ...


def vad_is_empty(
    file_path: str, return_segments: bool = False, cache: bool = False
) -> Union[bool, List[Dict[str, Any]]]:
    """Uses hosted pyannote VAD (best quality) with local ONNX Silero fallback."""
    caching_key = f'vad_is_empty:{file_path}'
    if cache:
        cached = redis_db.get_generic_cache(caching_key)
        if cached is not None:
            if return_segments:
                return cached
            return len(cached) == 0

    segments: Optional[List[Dict[str, Any]]] = None
    hosted_vad_url = os.getenv('HOSTED_VAD_API_URL')
    if hosted_vad_url:
        try:
            with open(file_path, 'rb') as file:
                files = {'file': (file_path.split('/')[-1], file, 'audio/wav')}
                response = requests.post(hosted_vad_url, files=files, timeout=_hosted_vad_timeout_seconds())
                response.raise_for_status()
                segments = response.json()  # untyped external JSON response
        except Exception as e:
            _record_hosted_vad_fallback(e)
            logger.warning('Hosted VAD unavailable, falling back to local ONNX VAD: %s', sanitize_provider_error(e))

    if segments is None:
        segments = _run_file_vad(file_path)

    if cache:
        redis_db.set_generic_cache(caching_key, segments, ttl=_vad_cache_ttl_seconds())
    if return_segments:
        return segments
    logger.info(f'vad_is_empty {len(segments) == 0}')
    return len(segments) == 0


def _run_file_vad(
    file_path: str,
    threshold: float = 0.5,
    *,
    raise_on_decode_error: bool = False,
) -> List[Dict[str, Any]]:
    """Process an entire audio file through Silero-VAD ONNX.

    Reads the file, resamples to 16 kHz mono, and iterates 512-sample windows
    with 64-sample context. Returns list of dicts: [{start, end, duration}, ...]
    """
    try:
        audio: Any = AudioSegment.from_file(file_path)  # type: ignore[reportUnknownMemberType]  # pydub untyped
    except Exception as e:
        if raise_on_decode_error:
            raise VADAudioDecodeError('audio could not be decoded for VAD') from e
        logger.error('Failed to read audio file: %s', sanitize_provider_error(e))
        return []

    # Convert to 16 kHz mono float32
    audio = audio.set_frame_rate(VAD_SAMPLE_RATE).set_channels(1).set_sample_width(2)  # type: ignore[reportUnknownMemberType]  # pydub untyped
    samples = np.array(audio.get_array_of_samples(), dtype=np.float32) / 32768.0  # type: ignore[reportUnknownMemberType]  # pydub untyped
    del audio

    try:
        return _segments_from_16khz_samples(samples, threshold=threshold)
    except Exception as e:
        if raise_on_decode_error:
            raise VADProcessingError('local VAD could not evaluate audio') from e
        raise
    finally:
        del samples


def vad_is_empty_strict(file_path: str) -> bool:
    """Classify local audio silence while preserving decode/VAD failures.

    This eligibility seam is for boundaries where an empty result is a terminal
    semantic decision. Legacy ``vad_is_empty`` retains its fail-soft behavior.
    """

    return len(_run_file_vad(file_path, raise_on_decode_error=True)) == 0


def linear16_pcm_is_silent(audio_bytes: bytes, *, sample_rate: int, channels: int) -> bool:
    """Make a strict local speech decision for raw signed 16-bit PCM.

    This intentionally bypasses the hosted VAD: raw PCM is a request-boundary
    eligibility decision and must never turn an unavailable external service
    into a false "silence" result. Decode and inference failures remain typed
    so callers can return a retryable/invalid failure instead.
    """
    if sample_rate <= 0 or channels < 1 or len(audio_bytes) % (2 * channels) != 0:
        raise VADAudioDecodeError('invalid linear16 PCM shape')
    try:
        audio: Any = AudioSegment(
            data=audio_bytes,
            sample_width=2,
            frame_rate=sample_rate,
            channels=channels,
        )
        audio = audio.set_frame_rate(VAD_SAMPLE_RATE).set_channels(1).set_sample_width(2)  # type: ignore[reportUnknownMemberType]  # pydub untyped
        samples = np.array(audio.get_array_of_samples(), dtype=np.float32) / 32768.0  # type: ignore[reportUnknownMemberType]  # pydub untyped
    except Exception as e:
        raise VADAudioDecodeError('linear16 PCM could not be decoded for VAD') from e

    try:
        return len(_segments_from_16khz_samples(samples)) == 0
    except Exception as e:
        raise VADProcessingError('local VAD could not evaluate linear16 PCM') from e
    finally:
        del samples


def _read_file(path: str) -> bytes:
    with open(path, 'rb') as f:
        return f.read()


@overload
async def async_vad_is_empty(
    file_path: str, return_segments: Literal[True], cache: bool = False
) -> List[Dict[str, Any]]: ...


@overload
async def async_vad_is_empty(file_path: str, return_segments: Literal[False] = False, cache: bool = False) -> bool: ...


async def async_vad_is_empty(
    file_path: str, return_segments: bool = False, cache: bool = False
) -> Union[bool, List[Dict[str, Any]]]:
    """Async version of vad_is_empty using httpx.AsyncClient for hosted VAD."""
    caching_key = f'vad_is_empty:{file_path}'
    if cache:
        if exists := await run_blocking(db_executor, redis_db.get_generic_cache, caching_key):
            if return_segments:
                return exists
            return len(exists) == 0

    segments: Optional[List[Dict[str, Any]]] = None
    hosted_vad_url = os.getenv('HOSTED_VAD_API_URL')
    if hosted_vad_url:
        try:
            file_data = await run_blocking(storage_executor, _read_file, file_path)
            files = {'file': (file_path.split('/')[-1], file_data, 'audio/wav')}
            client = get_stt_client()
            response = await client.post(hosted_vad_url, files=files, timeout=_hosted_vad_httpx_timeout())
            response.raise_for_status()
            segments = response.json()  # untyped external JSON response
        except Exception as e:
            _record_hosted_vad_fallback(e)
            logger.warning('Hosted VAD unavailable, falling back to local VAD: %s', sanitize_provider_error(e))

    if segments is None:
        segments = await run_blocking(sync_executor, _run_file_vad, file_path)

    if cache:
        await run_blocking(db_executor, redis_db.set_generic_cache, caching_key, segments, ttl=60 * 60 * 24)
    if return_segments:
        return segments
    logger.info(f'async_vad_is_empty {len(segments) == 0}')
    return len(segments) == 0


def apply_vad_for_speech_profile(file_path: str) -> None:
    logger.info(f'apply_vad_for_speech_profile {file_path}')
    voice_segments = vad_is_empty(file_path, return_segments=True)
    if len(voice_segments) == 0:
        raise VADEmptyError("Audio is empty")
    joined_segments: List[Dict[str, Any]] = []
    for i, segment in enumerate(voice_segments):
        if joined_segments and (segment['start'] - joined_segments[-1]['end']) < 1:
            joined_segments[-1]['end'] = segment['end']
        else:
            joined_segments.append(segment)

    # Load audio file once instead of repeatedly in the loop
    full_audio: Any = AudioSegment.from_wav(file_path)  # type: ignore[reportUnknownMemberType]  # pydub untyped

    trimmed_aseg: Any = AudioSegment.empty()
    try:
        # trim silence out of file_path, but leave 1 sec of silence within chunks
        for i, segment in enumerate(joined_segments):
            start = segment['start'] * 1000
            end = segment['end'] * 1000
            trimmed_aseg += full_audio[start:end]  # type: ignore[reportUnknownMemberType]  # pydub untyped
            if i < len(joined_segments) - 1:
                trimmed_aseg += full_audio[end : end + 1000]  # type: ignore[reportUnknownMemberType]  # pydub untyped

        # file_path.replace('.wav', '-cleaned.wav')
        trimmed_aseg.export(file_path, format="wav")  # type: ignore[reportUnknownMemberType]  # pydub untyped
    finally:
        # Explicitly free memory
        del full_audio
        del trimmed_aseg
