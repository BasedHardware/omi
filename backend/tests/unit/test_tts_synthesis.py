import asyncio
import base64
import math
import shutil
import struct

import pytest

from utils import tts


class _FakeResponse:
    def __init__(self, *, status_code=200, lines=None):
        self.status_code = status_code
        self._lines = lines or []

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aread(self):
        return b'provider error'


class _FakeStreamContext:
    def __init__(self, response):
        self.response = response
        self.exited = False

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, *_args):
        self.exited = True


class _FakeClient:
    def __init__(self, response):
        self.context = _FakeStreamContext(response)
        self.request = None

    def stream(self, method, url, **kwargs):
        self.request = (method, url, kwargs)
        return self.context


def _pcm_tone(seconds=0.25):
    samples = int(tts.GEMINI_SAMPLE_RATE * seconds)
    return b''.join(
        struct.pack('<h', int(4000 * math.sin(2 * math.pi * 440 * index / tts.GEMINI_SAMPLE_RATE)))
        for index in range(samples)
    )


def _sse_audio_lines(pcm):
    encoded = base64.b64encode(pcm).decode()
    return [
        'data: {"candidates":[{"content":{"parts":[{"inlineData":{"mimeType":"audio/L16;codec=pcm;rate=24000","data":"'
        + encoded
        + '"}}]}}]}',
        '',
    ]


async def _collect(iterator):
    return b''.join([chunk async for chunk in iterator])


def test_provider_switch_defaults_to_gemini_and_supports_legacy(monkeypatch):
    monkeypatch.delenv('TTS_PROVIDER', raising=False)
    assert tts.get_tts_provider() == 'gemini'
    monkeypatch.setenv('TTS_PROVIDER', 'legacy')
    assert tts.get_tts_provider() == 'legacy'
    monkeypatch.setenv('TTS_PROVIDER', 'other')
    with pytest.raises(tts.TtsConfigurationError):
        tts.get_tts_provider()


def test_request_keeps_verbatim_text_separate_from_style_and_selects_audio():
    request = tts.build_gemini_request(text='Read only these words.', voice='Kore', style='speak slowly')
    part = request['contents'][0]['parts'][0]
    assert part == {'text': 'Read only these words.', 'speech_metadata': {'style': 'speak slowly'}}
    assert request['generationConfig'] == {
        'responseModalities': ['AUDIO'],
        'speechConfig': {'voiceConfig': {'voice': 'Kore'}},
    }


def test_provider_specific_voice_names_map_and_unknowns_use_safe_default():
    assert tts.map_gemini_voice('BAMYoBHLZM7lJgJAmFz0', 'mobile') == 'Charon'
    assert tts.map_gemini_voice('shimmer', 'desktop') == 'Aoede'
    assert tts.map_gemini_voice('cedar', 'desktop') == 'Gacrux'
    assert tts.map_gemini_voice('future-provider-voice', 'desktop') == tts.DEFAULT_GEMINI_VOICE


def test_default_voice_and_style_match_the_live_assistant():
    request = tts.build_gemini_request(text='Hello.', voice=tts.DEFAULT_GEMINI_VOICE)
    assert tts.DEFAULT_GEMINI_VOICE == 'Charon'
    assert request['contents'][0]['parts'][0]['speech_metadata']['style'] == (
        'Clear, friendly, neutral assistant voice at a natural conversational pace; no dramatic emphasis.'
    )


@pytest.mark.asyncio
@pytest.mark.skipif(shutil.which('ffmpeg') is None, reason='FFmpeg is verified in serving-image smoke tests')
async def test_pcm_stream_is_transcoded_to_mp3():
    async def chunks():
        yield _pcm_tone()

    output = await _collect(tts.transcode_pcm_to_mp3(chunks()))
    assert len(output) > 100
    assert output.startswith(b'ID3') or (output[0] == 0xFF and output[1] & 0xE0 == 0xE0)


@pytest.mark.asyncio
async def test_open_stream_uses_gemini_api_key_even_when_vertex_is_enabled(monkeypatch):
    response = _FakeResponse(lines=_sse_audio_lines(_pcm_tone()))
    client = _FakeClient(response)
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.setenv('USE_VERTEX_AI', 'true')
    monkeypatch.setattr(tts, 'get_tts_client', lambda: client)
    monkeypatch.setattr(tts, 'get_tts_semaphore', lambda: __import__('asyncio').Semaphore(1))

    async def fake_transcoder(pcm_chunks):
        assert await _collect(pcm_chunks) == _pcm_tone()
        yield b'ID3mock-mp3'

    monkeypatch.setattr(tts, 'transcode_pcm_to_mp3', fake_transcoder)

    output = await _collect(
        await tts.open_gemini_mp3_stream(
            text='Hello',
            voice_id='unknown',
            client='desktop',
            style='friendly',
        )
    )

    assert output.startswith(b'ID3') or output[0] == 0xFF
    assert client.request is not None
    method, url, kwargs = client.request
    assert method == 'POST'
    assert url == tts.GEMINI_TTS_URL
    assert kwargs['headers']['x-goog-api-key'] == 'test-key'
    assert kwargs['json']['contents'][0]['parts'][0]['speech_metadata']['style'] == 'friendly'
    assert client.context.exited


@pytest.mark.asyncio
async def test_closing_returned_stream_releases_upstream_and_semaphore(monkeypatch):
    response = _FakeResponse(lines=_sse_audio_lines(_pcm_tone()))
    client = _FakeClient(response)
    semaphore = asyncio.Semaphore(1)
    transcoder_closed = False

    async def fake_transcoder(_pcm_chunks):
        nonlocal transcoder_closed
        try:
            yield b'ID3first-chunk'
            await asyncio.Event().wait()
        finally:
            transcoder_closed = True

    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.setattr(tts, 'get_tts_client', lambda: client)
    monkeypatch.setattr(tts, 'get_tts_semaphore', lambda: semaphore)
    monkeypatch.setattr(tts, 'transcode_pcm_to_mp3', fake_transcoder)

    stream = await tts.open_gemini_mp3_stream(
        text='Hello',
        voice_id='unknown',
        client='desktop',
    )
    assert await anext(stream) == b'ID3first-chunk'
    assert semaphore.locked()

    await stream.aclose()

    assert client.context.exited
    assert not semaphore.locked()
    assert transcoder_closed


@pytest.mark.asyncio
async def test_open_stream_maps_provider_http_error(monkeypatch):
    client = _FakeClient(_FakeResponse(status_code=429))
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.setattr(tts, 'get_tts_client', lambda: client)
    monkeypatch.setattr(tts, 'get_tts_semaphore', lambda: __import__('asyncio').Semaphore(1))

    with pytest.raises(tts.TtsUpstreamError) as exc_info:
        await tts.open_gemini_mp3_stream(text='Hello', voice_id='voice', client='mobile')

    assert exc_info.value.status_code == 429
    assert client.context.exited


@pytest.mark.asyncio
async def test_open_stream_requires_gemini_api_key(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    with pytest.raises(tts.TtsConfigurationError):
        await tts.open_gemini_mp3_stream(text='Hello', voice_id='voice', client='mobile')


@pytest.mark.asyncio
async def test_initial_stream_error_is_raised_before_transcoder_can_emit_headers(monkeypatch):
    response = _FakeResponse(lines=['data: {"error":{"code":503}}', ''])
    client = _FakeClient(response)
    transcoder_started = False

    async def fake_transcoder(_pcm_chunks):
        nonlocal transcoder_started
        transcoder_started = True
        yield b'container-header'

    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.setattr(tts, 'get_tts_client', lambda: client)
    monkeypatch.setattr(tts, 'get_tts_semaphore', lambda: __import__('asyncio').Semaphore(1))
    monkeypatch.setattr(tts, 'transcode_pcm_to_mp3', fake_transcoder)

    with pytest.raises(tts.TtsUpstreamError) as exc_info:
        await tts.open_gemini_mp3_stream(text='Hello', voice_id='voice', client='mobile')

    assert exc_info.value.status_code == 503
    assert transcoder_started is False
    assert client.context.exited


@pytest.mark.asyncio
async def test_invalid_sse_error_code_maps_to_bad_gateway(monkeypatch):
    response = _FakeResponse(lines=['data: {"error":{"code":1}}', ''])
    client = _FakeClient(response)
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.setattr(tts, 'get_tts_client', lambda: client)
    monkeypatch.setattr(tts, 'get_tts_semaphore', lambda: asyncio.Semaphore(1))

    with pytest.raises(tts.TtsUpstreamError) as exc_info:
        await tts.open_gemini_mp3_stream(text='Hello', voice_id='voice', client='mobile')

    assert exc_info.value.status_code == 502
    assert client.context.exited


@pytest.mark.asyncio
async def test_malformed_inline_audio_is_a_typed_response_error(monkeypatch):
    lines = [
        'data: {"candidates":[{"content":{"parts":[{"inlineData":{"mimeType":"audio/L16;rate=24000","data":{}}}]}}]}',
        '',
    ]
    client = _FakeClient(_FakeResponse(lines=lines))
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.setattr(tts, 'get_tts_client', lambda: client)
    monkeypatch.setattr(tts, 'get_tts_semaphore', lambda: __import__('asyncio').Semaphore(1))

    with pytest.raises(tts.TtsResponseError):
        await tts.open_gemini_mp3_stream(text='Hello', voice_id='voice', client='mobile')

    assert client.context.exited


def test_pcm_mime_rejects_a_rate_that_does_not_match_ffmpeg_input():
    with pytest.raises(tts.TtsResponseError, match='sample rate'):
        tts._validate_pcm_mime_type('audio/L16;codec=pcm;rate=16000')


@pytest.mark.parametrize(
    ('mime_type', 'message'),
    [
        ('audio/L16;codec=opus;rate=24000', 'codec'),
        ('audio/L16;codec=pcm;rate=24000;channels=2', 'channel count'),
    ],
)
def test_pcm_mime_rejects_parameters_that_do_not_match_ffmpeg_input(mime_type, message):
    with pytest.raises(tts.TtsResponseError, match=message):
        tts._validate_pcm_mime_type(mime_type)
