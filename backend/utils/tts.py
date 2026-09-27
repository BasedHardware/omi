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
from contextlib import suppress
from dataclasses import dataclass, field
import json
import logging
import os
import time
from typing import Any, Literal

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
DEFAULT_GEMINI_VOICE = 'Aoede'
DEFAULT_GEMINI_STYLE = 'Warm, natural, conversational, and easy to understand.'

_MOBILE_VOICE_MAP = {
    # Sloane, the released mobile client's default ElevenLabs voice.
    'BAMYoBHLZM7lJgJAmFz0': 'Aoede',
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
                data_lines.clear()
                yield event
            continue
        if line.startswith('data:'):
            data_lines.append(line[5:].lstrip())
    if data_lines:
        try:
            yield json.loads('\n'.join(data_lines))
        except json.JSONDecodeError as exc:
            raise TtsResponseError('Gemini returned malformed streaming JSON') from exc


async def _iter_gemini_pcm(response: httpx.Response) -> AsyncIterator[bytes]:
    found_audio = False
    async for event in _iter_sse_json(response):
        if 'error' in event:
            status_code = event['error'].get('code', 502)
            raise TtsUpstreamError(status_code if isinstance(status_code, int) else 502)
        for candidate in event.get('candidates', []):
            for part in candidate.get('content', {}).get('parts', []):
                inline_data = part.get('inlineData')
                if not inline_data:
                    continue
                mime_type = inline_data.get('mimeType', '')
                if not mime_type.startswith(GEMINI_PCM_MIME_PREFIX):
                    raise TtsResponseError('Gemini returned an unsupported audio format')
                try:
                    chunk = base64.b64decode(inline_data.get('data', ''), validate=True)
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
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()


async def transcode_pcm_to_mp3(pcm_chunks: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
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
        async for chunk in transcode_pcm_to_mp3(_iter_gemini_pcm(response)):
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
            with suppress(httpx.HTTPError):
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
