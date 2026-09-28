"""Shared text-to-speech synthesis for mobile and desktop read-aloud routes.

Gemini 3.8 Flash-Lite TTS streams raw 24 kHz mono PCM. Released Omi clients
expect ``audio/mpeg``, so this module incrementally transcodes the provider
stream with FFmpeg instead of buffering a complete WAV response.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing, suppress
from dataclasses import dataclass, field
import json
import logging
import os
import time
from typing import Any, cast, Literal

import httpx

from utils.async_tasks import create_named_task
from utils.http_client import get_tts_client, get_tts_semaphore

logger = logging.getLogger(__name__)

TtsProvider = Literal['gemini', 'legacy']
TtsClient = Literal['mobile', 'desktop']

GEMINI_TTS_MODEL = 'gemini-3.8-flash-lite-tts'
GEMINI_TTS_URL = (
    f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_TTS_MODEL}:streamGenerateContent?alt=sse'
)
GEMINI_PCM_MIME_PREFIX = 'audio/l16'
GEMINI_SAMPLE_RATE = 24_000
DEFAULT_GEMINI_VOICE = 'Charon'
DEFAULT_GEMINI_STYLE = (
    'Clear, friendly, neutral assistant voice at a natural conversational pace; no dramatic emphasis.'
)

_MOBILE_VOICE_MAP = {
    # Sloane, the released mobile client's default ElevenLabs voice.
    'BAMYoBHLZM7lJgJAmFz0': 'Charon',
}
_DESKTOP_VOICE_MAP = {
    'alloy': 'Schedar',
    'ash': 'Charon',
    'ballad': 'Sulafat',
    'coral': 'Leda',
    'echo': 'Iapetus',
    'fable': 'Achird',
    'nova': 'Zephyr',
    'onyx': 'Orus',
    'sage': 'Kore',
    'shimmer': 'Aoede',
    'verse': 'Puck',
    'marin': 'Laomedeia',
    'cedar': 'Gacrux',
}


class TtsError(Exception):
    """Base class for synthesis failures that routes translate to HTTP errors."""


class TtsConfigurationError(TtsError):
    """The selected TTS provider is not configured."""


class TtsUnavailableError(TtsError):
    """The provider or local transcoder could not be reached."""


class TtsUpstreamError(TtsError):
    """The provider rejected a request with an HTTP-shaped status."""

    def __init__(self, status_code: int):
        super().__init__('TTS upstream error')
        self.status_code = status_code


class TtsResponseError(TtsError):
    """The provider returned an invalid or empty audio stream."""


@dataclass(slots=True)
class TtsRequestLog:
    """Emit one content-free observability record for a synthesis request."""

    provider: str
    model: str
    chars: int
    started_at: float = field(default_factory=time.perf_counter)
    first_byte_at: float | None = None
    _finished: bool = False

    def mark_first_byte(self) -> None:
        if self.first_byte_at is None:
            self.first_byte_at = time.perf_counter()

    def finish(self, outcome: str) -> None:
        if self._finished:
            return
        self._finished = True
        first_byte_ms = None
        if self.first_byte_at is not None:
            first_byte_ms = round((self.first_byte_at - self.started_at) * 1000, 1)
        logger.info(
            'tts_request provider=%s model=%s chars=%d latency_to_first_byte_ms=%s outcome=%s',
            self.provider,
            self.model,
            self.chars,
            first_byte_ms,
            outcome,
        )


def get_tts_provider() -> TtsProvider:
    """Read the mutable rollback switch at request time."""

    provider = os.getenv('TTS_PROVIDER', 'gemini').strip().lower()
    if provider not in {'gemini', 'legacy'}:
        raise TtsConfigurationError('TTS_PROVIDER must be gemini or legacy')
    return provider  # type: ignore[return-value]


def map_gemini_voice(voice_id: str, client: TtsClient) -> str:
    """Map released provider-specific voices, defaulting unknown names safely."""

    if client == 'mobile':
        return _MOBILE_VOICE_MAP.get(voice_id, DEFAULT_GEMINI_VOICE)
    return _DESKTOP_VOICE_MAP.get(voice_id.strip().lower(), DEFAULT_GEMINI_VOICE)


def build_gemini_request(*, text: str, voice: str, style: str | None = None) -> dict[str, Any]:
    """Build the GenerateContent TTS request without mixing style into text."""

    return {
        'contents': [
            {
                'role': 'user',
                'parts': [
                    {
                        'text': text,
                        'speech_metadata': {
                            'style': style.strip() if style and style.strip() else DEFAULT_GEMINI_STYLE
                        },
                    }
                ],
            }
        ],
        'generationConfig': {
            'responseModalities': ['AUDIO'],
            'speechConfig': {'voiceConfig': {'voice': voice}},
        },
    }


async def _iter_sse_json(response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    data_lines: list[str] = []
    async for line in response.aiter_lines():
        if not line:
            if data_lines:
                try:
                    event = json.loads('\n'.join(data_lines))
                except json.JSONDecodeError as exc:
                    raise TtsResponseError('Gemini returned malformed streaming JSON') from exc
                if not isinstance(event, dict):
                    raise TtsResponseError('Gemini returned an invalid streaming event')
                data_lines.clear()
                yield cast(dict[str, Any], event)
            continue
        if line.startswith('data:'):
            data_lines.append(line[5:].lstrip())
    if data_lines:
        try:
            event = json.loads('\n'.join(data_lines))
        except json.JSONDecodeError as exc:
            raise TtsResponseError('Gemini returned malformed streaming JSON') from exc
        if not isinstance(event, dict):
            raise TtsResponseError('Gemini returned an invalid streaming event')
        yield cast(dict[str, Any], event)


def _validate_pcm_mime_type(mime_type: object) -> None:
    """Accept Google's documented L16 spelling while pinning our FFmpeg input rate."""

    if not isinstance(mime_type, str):
        raise TtsResponseError('Gemini returned an invalid audio format')
    segments = [segment.strip() for segment in mime_type.split(';')]
    if not segments or segments[0].lower() != GEMINI_PCM_MIME_PREFIX:
        raise TtsResponseError('Gemini returned an unsupported audio format')
    parameters = {
        key.strip().lower(): value.strip().lower()
        for segment in segments[1:]
        if '=' in segment
        for key, value in [segment.split('=', 1)]
    }
    if parameters.get('codec', 'pcm') != 'pcm':
        raise TtsResponseError('Gemini returned an unsupported audio codec')
    if parameters.get('rate', str(GEMINI_SAMPLE_RATE)) != str(GEMINI_SAMPLE_RATE):
        raise TtsResponseError('Gemini returned an unsupported audio sample rate')
    if parameters.get('channels', '1') != '1':
        raise TtsResponseError('Gemini returned an unsupported audio channel count')


def _normalize_upstream_status(value: object) -> int:
    """Keep provider-supplied SSE errors within valid HTTP error status bounds."""

    if isinstance(value, int) and not isinstance(value, bool) and 400 <= value <= 599:
        return value
    return 502


async def _iter_gemini_pcm(response: httpx.Response) -> AsyncGenerator[bytes, None]:
    found_audio = False
    async for event in _iter_sse_json(response):
        if 'error' in event:
            error = event['error']
            error_object = cast(dict[str, Any], error) if isinstance(error, dict) else None
            status_code: object = error_object.get('code') if error_object is not None else None
            raise TtsUpstreamError(_normalize_upstream_status(status_code))
        candidates = event.get('candidates', [])
        if not isinstance(candidates, list):
            raise TtsResponseError('Gemini returned invalid audio candidates')
        for candidate in cast(list[object], candidates):
            if not isinstance(candidate, dict):
                raise TtsResponseError('Gemini returned an invalid audio candidate')
            candidate_object = cast(dict[str, Any], candidate)
            content = candidate_object.get('content', {})
            if not isinstance(content, dict):
                raise TtsResponseError('Gemini returned invalid audio content')
            content_object = cast(dict[str, Any], content)
            parts = content_object.get('parts', [])
            if not isinstance(parts, list):
                raise TtsResponseError('Gemini returned invalid audio parts')
            for part in cast(list[object], parts):
                if not isinstance(part, dict):
                    raise TtsResponseError('Gemini returned an invalid audio part')
                part_object = cast(dict[str, Any], part)
                inline_data = part_object.get('inlineData')
                if not inline_data:
                    continue
                if not isinstance(inline_data, dict):
                    raise TtsResponseError('Gemini returned invalid inline audio data')
                inline_data_object = cast(dict[str, Any], inline_data)
                _validate_pcm_mime_type(inline_data_object.get('mimeType'))
                encoded_data = inline_data_object.get('data', '')
                if not isinstance(encoded_data, str):
                    raise TtsResponseError('Gemini returned invalid audio data')
                try:
                    chunk = base64.b64decode(encoded_data, validate=True)
                except (binascii.Error, ValueError) as exc:
                    raise TtsResponseError('Gemini returned invalid audio data') from exc
                if chunk:
                    found_audio = True
                    yield chunk
    if not found_audio:
        raise TtsResponseError('Gemini returned no audio data')


async def _feed_ffmpeg(process: asyncio.subprocess.Process, pcm_chunks: AsyncIterator[bytes]) -> None:
    if process.stdin is None:
        raise TtsUnavailableError('FFmpeg stdin is unavailable')
    try:
        async for chunk in pcm_chunks:
            process.stdin.write(chunk)
            await process.stdin.drain()
    finally:
        process.stdin.close()
        with suppress(BrokenPipeError, ConnectionResetError):
            await process.stdin.wait_closed()


async def _read_ffmpeg_stderr(process: asyncio.subprocess.Process) -> bytes:
    if process.stderr is None:
        return b''
    data = await process.stderr.read()
    return data[-8192:]


async def _stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    with suppress(ProcessLookupError):
        process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        with suppress(ProcessLookupError):
            process.kill()
        await process.wait()


async def transcode_pcm_to_mp3(pcm_chunks: AsyncIterator[bytes]) -> AsyncGenerator[bytes, None]:
    """Incrementally convert Gemini's signed 16-bit mono PCM to MP3."""

    try:
        process = await asyncio.create_subprocess_exec(
            'ffmpeg',
            '-hide_banner',
            '-loglevel',
            'error',
            '-f',
            's16le',
            '-ar',
            str(GEMINI_SAMPLE_RATE),
            '-ac',
            '1',
            '-i',
            'pipe:0',
            '-codec:a',
            'libmp3lame',
            '-b:a',
            '128k',
            '-f',
            'mp3',
            'pipe:1',
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (OSError, RuntimeError) as exc:
        raise TtsUnavailableError('FFmpeg is unavailable') from exc

    if process.stdout is None:
        await _stop_process(process)
        raise TtsUnavailableError('FFmpeg stdout is unavailable')

    feeder = create_named_task(_feed_ffmpeg(process, pcm_chunks), name='tts_ffmpeg_pcm_feed')
    stderr_reader = create_named_task(_read_ffmpeg_stderr(process), name='tts_ffmpeg_stderr')
    try:
        while chunk := await process.stdout.read(16_384):
            yield chunk
        await feeder
        return_code = await process.wait()
        stderr = await stderr_reader
        if return_code != 0:
            logger.error('tts_ffmpeg_failed return_code=%d stderr_bytes=%d', return_code, len(stderr))
            raise TtsResponseError('FFmpeg failed to transcode audio')
    finally:
        if not feeder.done():
            feeder.cancel()
        if not stderr_reader.done():
            stderr_reader.cancel()
        await _stop_process(process)
        for task in (feeder, stderr_reader):
            with suppress(asyncio.CancelledError, Exception):
                await task


async def _gemini_mp3_stream(
    response: httpx.Response,
    upstream_cm: object,
    semaphore: asyncio.Semaphore,
    metrics: TtsRequestLog,
) -> AsyncGenerator[bytes, None]:
    outcome = 'success'
    try:
        pcm_stream = _iter_gemini_pcm(response)
        # Validate a real provider audio chunk before starting FFmpeg. Some
        # muxers can emit container bytes before consuming input; priming PCM
        # first keeps initial provider/SSE failures on the pre-header HTTP path.
        first_pcm = await anext(pcm_stream)
        async with aclosing(transcode_pcm_to_mp3(_prepend_chunk(first_pcm, pcm_stream))) as mp3_stream:
            async for chunk in mp3_stream:
                metrics.mark_first_byte()
                yield chunk
    except asyncio.CancelledError:
        outcome = 'cancelled'
        raise
    except GeneratorExit:
        outcome = 'cancelled'
        raise
    except Exception:
        outcome = 'stream_error'
        raise
    finally:
        try:
            await upstream_cm.__aexit__(None, None, None)  # type: ignore[attr-defined]
        finally:
            semaphore.release()
            metrics.finish(outcome)


async def _prepend_chunk(first_chunk: bytes, remainder: AsyncGenerator[bytes, None]) -> AsyncIterator[bytes]:
    try:
        yield first_chunk
        async for chunk in remainder:
            yield chunk
    finally:
        with suppress(Exception):
            await remainder.aclose()


async def open_gemini_mp3_stream(
    *,
    text: str,
    voice_id: str,
    client: TtsClient,
    style: str | None = None,
) -> AsyncIterator[bytes]:
    """Open, validate, and prime a Gemini-to-MP3 stream before HTTP headers."""

    metrics = TtsRequestLog(provider='gemini', model=GEMINI_TTS_MODEL, chars=len(text))
    api_key = os.getenv('GEMINI_API_KEY', '').strip()
    if not api_key:
        metrics.finish('not_configured')
        raise TtsConfigurationError('GEMINI_API_KEY is not configured')

    # Gemini 3.8 TTS is not served by Vertex AI. This direct Gemini API call is
    # intentional even when USE_VERTEX_AI=true for the backend's LLM traffic.
    body = build_gemini_request(text=text, voice=map_gemini_voice(voice_id, client), style=style)
    headers = {'Content-Type': 'application/json', 'x-goog-api-key': api_key}
    http_client = get_tts_client()
    semaphore = get_tts_semaphore()
    await semaphore.acquire()
    try:
        upstream_cm = http_client.stream('POST', GEMINI_TTS_URL, json=body, headers=headers, timeout=60.0)
        response = await upstream_cm.__aenter__()
    except asyncio.CancelledError:
        semaphore.release()
        metrics.finish('cancelled')
        raise
    except httpx.HTTPError as exc:
        semaphore.release()
        metrics.finish('transport_error')
        raise TtsUnavailableError('Gemini TTS request failed') from exc
    except Exception as exc:
        semaphore.release()
        metrics.finish('transport_error')
        raise TtsUnavailableError('Gemini TTS request failed') from exc

    if response.status_code >= 400:
        status_code = response.status_code
        try:
            # The status is authoritative; a broken/partial error body must not
            # turn a typed provider rejection into an unhandled application 500.
            with suppress(Exception):
                await response.aread()
        finally:
            try:
                with suppress(Exception):
                    await upstream_cm.__aexit__(None, None, None)
            finally:
                semaphore.release()
                metrics.finish(f'upstream_{status_code}')
        raise TtsUpstreamError(status_code)

    stream = _gemini_mp3_stream(response, upstream_cm, semaphore, metrics)
    try:
        first_chunk = await anext(stream)
    except StopAsyncIteration as exc:
        metrics.finish('empty_audio')
        raise TtsResponseError('Gemini returned no audio data') from exc
    return _prepend_chunk(first_chunk, stream)
