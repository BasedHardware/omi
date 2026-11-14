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
from database import voice_preferences
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


# ---------------------------------------------------------------------------
# output_format plumbing
# ---------------------------------------------------------------------------
def test_device_format_is_supported():
    assert "ulaw_8000" in tts_router._EL_OUTPUT_FORMATS
    assert DEFAULT_OUTPUT_FORMAT in tts_router._EL_OUTPUT_FORMATS


def test_output_format_rejected_when_unsupported():
    # Anything not on the allowlist must fail before touching the URL.
    for bad in ("", "mp3", "vorbis_48000", "../../history", "pcm_16000; x=1"):
        assert bad not in tts_router._EL_OUTPUT_FORMATS


def test_el_url_puts_format_in_query_not_body():
    url = tts_router._el_tts_url("VOICEID123", "ulaw_8000")
    assert url == "https://api.elevenlabs.io/v1/text-to-speech/VOICEID123?output_format=ulaw_8000"


def test_media_type_matches_format_family():
    assert tts_router._el_output_media_type("mp3_44100_128") == "audio/mpeg"
    assert tts_router._el_output_media_type("pcm_16000") == "audio/L16"
    assert tts_router._el_output_media_type("ulaw_8000") == "audio/basic"


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


async def _allow_rate_limit(_executor, function, *_args, **_kwargs):
    if function is voice_preferences.get_assistant_voice:
        return 'Charon'
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
    monkeypatch.delenv('DEEPGRAM_API_KEY', raising=False)

    with pytest.raises(HTTPException) as exc_info:
        await tts_router.tts_synthesize(TtsSynthesizeRequest(text='hello'), uid='u')
    assert exc_info.value.status_code == 503


def test_deepgram_output_format_allowlist_rejects_injection():
    assert tts_router._dg_params('pcm_8000&model=evil') is None
    assert tts_router._dg_params('ulaw_8000&encoding=mp3') is None
    assert tts_router._dg_params('mp3_44100_128;foo=bar') is None
    assert tts_router._dg_params('pcm_99999') is None
    assert 'pcm_8000&model=evil' not in tts_router._DG_OUTPUT_FORMATS


def test_deepgram_output_format_allowlist_accepts_supported_formats():
    assert tts_router._dg_params('ulaw_8000') == {
        'encoding': 'mulaw',
        'sample_rate': '8000',
        'container': 'none',
    }
    assert tts_router._dg_params('mp3_44100_128') == {'encoding': 'mp3', 'container': 'mp3'}
    assert tts_router._dg_params('pcm_16000') == {
        'encoding': 'linear16',
        'sample_rate': '16000',
        'container': 'none',
    }


@pytest.mark.asyncio
async def test_direct_deepgram_rejects_injected_output_format_before_request(monkeypatch):
    monkeypatch.setenv('DEEPGRAM_API_KEY', 'dg-key')
    monkeypatch.delenv('ELEVENLABS_API_KEY', raising=False)

    called = {'stream': False}

    class _Client:
        def stream(self, *args, **kwargs):
            called['stream'] = True
            raise AssertionError('upstream request must not be made for invalid output_format')

    monkeypatch.setattr(tts_router, 'get_tts_client', lambda: _Client())

    with pytest.raises(HTTPException) as exc_info:
        await tts_router._stream_direct_tts(
            uid='u',
            req=TtsSynthesizeRequest(text='hello', output_format='pcm_8000&model=evil'),
            text='hello',
            voice_id=DEFAULT_VOICE_ID,
            char_count=5,
        )
    assert exc_info.value.status_code == 400
    assert called['stream'] is False


@pytest.mark.asyncio
async def test_direct_deepgram_encodes_query_params(monkeypatch):
    monkeypatch.setenv('DEEPGRAM_API_KEY', 'dg-key')
    monkeypatch.delenv('ELEVENLABS_API_KEY', raising=False)

    captured = {}

    class _Resp:
        status_code = 200

        async def aiter_bytes(self):
            yield b'audio'

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _CM:
        async def __aenter__(self):
            return _Resp()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Client:
        def stream(self, method, url, json=None, headers=None, timeout=None):
            captured['method'] = method
            captured['url'] = url
            captured['json'] = json
            captured['headers'] = headers
            return _CM()

    class _Sem:
        async def acquire(self):
            return None

        def release(self):
            return None

    monkeypatch.setattr(tts_router, 'get_tts_client', lambda: _Client())
    monkeypatch.setattr(tts_router, 'get_tts_semaphore', lambda: _Sem())

    response = await tts_router._stream_direct_tts(
        uid='u',
        req=TtsSynthesizeRequest(text='hello', output_format='ulaw_8000', model_id='aura-2-thalia-en'),
        text='hello',
        voice_id=DEFAULT_VOICE_ID,
        char_count=5,
    )
    body = b''.join([chunk async for chunk in response.body_iterator])

    assert body == b'audio'
    assert captured['url'].startswith('https://api.deepgram.com/v1/speak?')
    assert 'model=aura-2-thalia-en' in captured['url']
    assert 'encoding=mulaw' in captured['url']
    assert 'sample_rate=8000' in captured['url']
    assert 'container=none' in captured['url']
    assert '%26' not in captured['url']
    assert ' ' not in captured['url']


@pytest.mark.asyncio
async def test_route_legacy_default_format_with_deepgram_key_uses_inline_elevenlabs(monkeypatch):
    monkeypatch.setattr(tts_router, 'run_blocking', _allow_rate_limit)
    monkeypatch.setenv('TTS_PROVIDER', 'legacy')
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'el-key')
    monkeypatch.setenv('DEEPGRAM_API_KEY', 'dg-key')

    called = {'direct': False}

    async def _unexpected_direct(**kwargs):
        called['direct'] = True
        raise AssertionError('direct TTS path should not be used for default legacy MP3 when ElevenLabs is configured')

    class _Resp:
        status_code = 200

        async def aiter_bytes(self):
            yield b'mp3'

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _CM:
        async def __aenter__(self):
            return _Resp()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Client:
        def stream(self, method, url, json=None, headers=None, timeout=None):
            assert 'api.elevenlabs.io' in url
            return _CM()

    class _Sem:
        async def acquire(self):
            return None

        def release(self):
            return None

    monkeypatch.setattr(tts_router, '_stream_direct_tts', _unexpected_direct)
    monkeypatch.setattr(tts_router, 'get_tts_client', lambda: _Client())
    monkeypatch.setattr(tts_router, 'get_tts_semaphore', lambda: _Sem())

    response = await tts_router.tts_synthesize(TtsSynthesizeRequest(text='hello'), uid='u')
    body = b''.join([chunk async for chunk in response.body_iterator])

    assert body == b'mp3'
    assert called['direct'] is False


@pytest.mark.asyncio
async def test_route_legacy_default_format_deepgram_only_uses_direct(monkeypatch):
    monkeypatch.setattr(tts_router, 'run_blocking', _allow_rate_limit)
    monkeypatch.setenv('TTS_PROVIDER', 'legacy')
    monkeypatch.delenv('ELEVENLABS_API_KEY', raising=False)
    monkeypatch.setenv('DEEPGRAM_API_KEY', 'dg-key')

    called = {'direct': False}

    async def _direct(**kwargs):
        called['direct'] = True

        async def _chunks():
            yield b'dg'

        return tts_router.StreamingResponse(_chunks(), media_type='audio/mpeg')

    monkeypatch.setattr(tts_router, '_stream_direct_tts', _direct)

    response = await tts_router.tts_synthesize(TtsSynthesizeRequest(text='hello'), uid='u')
    body = b''.join([chunk async for chunk in response.body_iterator])

    assert body == b'dg'
    assert called['direct'] is True
