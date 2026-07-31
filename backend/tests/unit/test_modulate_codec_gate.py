import asyncio

import pytest

from config.stt_provider_policy import STTServingSurface, modulate_supports_codec
from utils.stt import streaming
from utils.stt.streaming import STTService, SafeModulateSocket, get_stt_service_for_language

DECODED_CODECS = ['opus', 'opus_fs320', 'aac', 'lc3', 'lc3_fs1030', 'pcm8']
UNDECODED_CODECS = ['pcm16', 'linear16', 'PCM16', ' linear16 ']


@pytest.mark.parametrize('codec', DECODED_CODECS)
def test_decoded_codecs_stay_eligible_for_velma(codec):
    assert modulate_supports_codec(codec) is True


@pytest.mark.parametrize('codec', UNDECODED_CODECS)
def test_undecoded_pcm_codecs_are_excluded_from_velma(codec):
    assert modulate_supports_codec(codec) is False


def test_unknown_codec_is_not_excluded():
    assert modulate_supports_codec(None) is True
    assert modulate_supports_codec('') is True


def test_selection_routes_decoded_codec_to_velma(monkeypatch):
    monkeypatch.setattr(streaming, 'stt_service_models', ['modulate-velma-2', 'parakeet'])
    service, language, model = get_stt_service_for_language('en', surface=STTServingSurface.STREAMING, codec='opus')
    assert service == STTService.modulate
    assert model == 'velma-2'
    assert language == 'multi'


def test_selection_skips_velma_for_raw_pcm(monkeypatch):
    monkeypatch.setattr(streaming, 'stt_service_models', ['modulate-velma-2', 'parakeet'])
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://parakeet.invalid')
    service, _, _ = get_stt_service_for_language('en', surface=STTServingSurface.STREAMING, codec='pcm16')
    assert service != STTService.modulate


def test_selection_without_codec_is_unchanged(monkeypatch):
    monkeypatch.setattr(streaming, 'stt_service_models', ['modulate-velma-2', 'parakeet'])
    service, _, _ = get_stt_service_for_language('en', surface=STTServingSurface.STREAMING)
    assert service == STTService.modulate


def test_preferred_service_cannot_bypass_the_codec_gate(monkeypatch):
    monkeypatch.setattr(streaming, 'stt_service_models', ['parakeet', 'modulate-velma-2'])
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://parakeet.invalid')
    service, _, _ = get_stt_service_for_language(
        'en', surface=STTServingSurface.STREAMING, preferred_service='modulate', codec='linear16'
    )
    assert service != STTService.modulate


class _StubWS:
    def __init__(self):
        self.sent = []

    async def send(self, data):
        self.sent.append(data)

    async def close(self):
        return None

    def __aiter__(self):
        async def _gen():
            if False:
                yield None

        return _gen()


def _socket(loop, context=None):
    sock = SafeModulateSocket(_StubWS(), lambda segments: None, loop, stream_context=context)
    sock._recv_task.cancel()
    sock._send_task.cancel()
    return sock


def test_stream_shape_log_reports_frame_geometry():
    loop = asyncio.new_event_loop()
    try:
        sock = _socket(loop, {'codec': 'pcm16', 'sample_rate': 16000, 'language': 'en'})
        sock.send(b'\x00' * 960)
        sock.send(b'\x00' * 320)
        line = sock._stream_shape_log()
    finally:
        loop.close()

    assert 'codec=pcm16' in line
    assert 'sample_rate=16000' in line
    assert 'language=en' in line
    assert 'frames=2' in line
    assert 'bytes=1280' in line
    assert 'odd_frames=0' in line
    assert 'min_frame=320' in line
    assert 'max_frame=960' in line
    assert 'last_frame=320' in line


def test_stream_shape_log_counts_odd_frames():
    loop = asyncio.new_event_loop()
    try:
        sock = _socket(loop)
        sock.send(b'\x00' * 101)
        sock.send(b'\x00' * 100)
        line = sock._stream_shape_log()
    finally:
        loop.close()

    assert 'odd_frames=1' in line
    assert 'frames=2' in line
