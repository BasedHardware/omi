"""Unit tests for the TTS proxy (/v2/tts/synthesize).

Covers input validation (voice_id, text length, empty text) by importing the
pure helpers directly.

Network behavior is mocked here; shared request construction and real FFmpeg
transcoding are covered by ``test_tts_synthesis.py``.
"""

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from models.tts import (
    DEFAULT_MODEL_ID,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_VOICE_ID,
    TtsSynthesizeRequest,
)
from routers import tts as tts_router
from utils.tts import TtsUpstreamError


# ---------------------------------------------------------------------------
# voice_id validation
# ---------------------------------------------------------------------------
def test_valid_voice_id_alphanumeric():
    assert tts_router._is_valid_voice_id("BAMYoBHLZM7lJgJAmFz0")
    assert tts_router._is_valid_voice_id("abc123")
    assert tts_router._is_valid_voice_id("A")


def test_reject_voice_id_path_traversal():
    assert not tts_router._is_valid_voice_id("../../history")
    assert not tts_router._is_valid_voice_id("../v1/voices")
    assert not tts_router._is_valid_voice_id("foo/bar")


def test_reject_voice_id_special_chars():
    assert not tts_router._is_valid_voice_id("id-with-dash")
    assert not tts_router._is_valid_voice_id("id_with_underscore")
    assert not tts_router._is_valid_voice_id("id with space")
    assert not tts_router._is_valid_voice_id("id?query=1")


def test_reject_voice_id_empty():
    assert not tts_router._is_valid_voice_id("")


def test_voice_id_length_boundaries():
    assert tts_router._is_valid_voice_id("a" * 128)
    assert not tts_router._is_valid_voice_id("a" * 129)


# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------
def test_burst_limit_matches_desktop():
    assert tts_router._TTS_BURST_PER_MINUTE == 50


def test_daily_char_limit_matches_desktop():
    assert tts_router._TTS_DAILY_CHAR_LIMIT == 10_000


def test_request_char_limit_matches_desktop():
    assert tts_router._TTS_REQUEST_CHAR_LIMIT == 5_000


def test_burst_window_matches_desktop():
    assert tts_router._TTS_BURST_WINDOW_SECS == 60


# ---------------------------------------------------------------------------
# Model defaults
# ---------------------------------------------------------------------------
def test_default_voice_id_is_sloane():
    assert DEFAULT_VOICE_ID == "BAMYoBHLZM7lJgJAmFz0"


def test_default_model_id():
    assert DEFAULT_MODEL_ID == "eleven_turbo_v2_5"


def test_default_output_format():
    assert DEFAULT_OUTPUT_FORMAT == "mp3_44100_128"


def test_request_model_applies_defaults():
    req = TtsSynthesizeRequest(text="hello")
    assert req.text == "hello"
    assert req.voice_id == "BAMYoBHLZM7lJgJAmFz0"
    assert req.model_id == "eleven_turbo_v2_5"
    assert req.output_format == "mp3_44100_128"
    assert req.voice_settings is None


def test_request_model_rejects_empty_text():
    with pytest.raises(ValidationError):
        TtsSynthesizeRequest(text="")


async def _audio_chunks():
    yield b'mp3'


async def _allow_rate_limit(*_args, **_kwargs):
    return 0, None


@pytest.mark.asyncio
async def test_route_uses_shared_gemini_stream_and_preserves_audio_mpeg(monkeypatch):
    calls = []

    async def open_stream(**kwargs):
        calls.append(kwargs)
        return _audio_chunks()

    monkeypatch.setattr(tts_router, 'run_blocking', _allow_rate_limit)
    monkeypatch.setattr(tts_router, 'get_tts_provider', lambda: 'gemini')
    monkeypatch.setattr(tts_router, 'open_gemini_mp3_stream', open_stream)

    response = await tts_router.tts_synthesize(TtsSynthesizeRequest(text='hello', voice_id='UnknownVoice1'), uid='u')
    body = b''.join([chunk async for chunk in response.body_iterator])

    assert response.media_type == 'audio/mpeg'
    assert body == b'mp3'
    assert calls == [{'text': 'hello', 'voice_id': 'UnknownVoice1', 'client': 'mobile'}]


@pytest.mark.asyncio
async def test_route_preserves_gemini_upstream_status_for_client_fallback(monkeypatch):
    async def fail_stream(**_kwargs):
        raise TtsUpstreamError(429)

    monkeypatch.setattr(tts_router, 'run_blocking', _allow_rate_limit)
    monkeypatch.setattr(tts_router, 'get_tts_provider', lambda: 'gemini')
    monkeypatch.setattr(tts_router, 'open_gemini_mp3_stream', fail_stream)

    with pytest.raises(HTTPException) as exc_info:
        await tts_router.tts_synthesize(TtsSynthesizeRequest(text='hello'), uid='u')
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_route_legacy_rollback_requires_elevenlabs_key(monkeypatch):
    monkeypatch.setattr(tts_router, 'run_blocking', _allow_rate_limit)
    monkeypatch.setenv('TTS_PROVIDER', 'legacy')
    monkeypatch.delenv('ELEVENLABS_API_KEY', raising=False)

    with pytest.raises(HTTPException) as exc_info:
        await tts_router.tts_synthesize(TtsSynthesizeRequest(text='hello'), uid='u')
    assert exc_info.value.status_code == 503
