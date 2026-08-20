"""An undecodable listen stream must report itself, not just drop frames silently.

Dropping a frame keeps the socket alive, so a stream the decoder cannot read is a fail-open
branch: the user records a whole session and gets no transcript, no ring buffer, and no mixed
audio. Prod logged only `Listen audio frame decode failed codec=opus type=OpusError`, one line
per frame — a name that cannot separate a corrupt client stream (`corrupted stream`) from a
decoder the receiver sized wrong (`buffer too small`, the #10701 regression), and no metric to
alert on. The receiver now carries the codec's own message plus the payload size, and reports
the session once the streak proves the whole stream is failing.
"""

import logging
from types import SimpleNamespace

import pytest

from routers.listen import receiver as receiver_module
from routers.listen.receiver import DECODE_FAILURE_STREAK_ALERT, ListenReceiver


@pytest.fixture
def anyio_backend():
    return 'asyncio'


class _OpusError(Exception):
    """Stands in for opuslib.OpusError, whose str() is the libopus message."""


class _ScriptedDecoder:
    """Raises for the frames named in `fail_on`, decodes the rest."""

    def __init__(self, fail_on):
        self.fail_on = set(fail_on)

    def decode(self, data: bytes, frame_size: int = 0, **_kwargs) -> bytes:
        if data in self.fail_on:
            raise _OpusError("b'corrupted stream'")
        return b'\x01\x02' * 320


class _FramesWebSocket:
    def __init__(self, frames):
        self.frames = iter(frames)

    async def receive(self):
        return next(self.frames)


def _host(websocket):
    return SimpleNamespace(
        request=SimpleNamespace(websocket=websocket, codec='opus', sample_rate=16000),
        state=SimpleNamespace(
            active=True,
            close_code=1001,
            last_audio_received_time=None,
            last_activity_time=None,
            first_audio_byte_timestamp=None,
            last_usage_record_timestamp=None,
            audio_ring_buffer=None,
        ),
        limits=SimpleNamespace(ws_receive_timeout=1.0),
        is_multi_channel=False,
        use_custom_stt=True,
        audio_bytes_send=None,
        transcripts=SimpleNamespace(enqueue=lambda _segments: None),
        start_live_transcription=lambda: None,
    )


def _receiver(frames, decoder):
    websocket = _FramesWebSocket(list(frames) + [{'type': 'websocket.disconnect', 'code': 1000}])
    instance = ListenReceiver(_host(websocket), [], {})
    instance.opus_decoder = decoder
    return instance


@pytest.fixture
def recorded_fallbacks(monkeypatch):
    calls = []
    monkeypatch.setattr(receiver_module, 'record_fallback', lambda **kwargs: calls.append(kwargs))
    return calls


@pytest.mark.anyio
async def test_decode_failure_log_names_the_codec_message_and_payload_size(caplog, recorded_fallbacks):
    frame = b'\xff\xff\xff'
    receiver = _receiver([{'bytes': frame}], _ScriptedDecoder({frame}))

    with caplog.at_level(logging.WARNING, logger=receiver_module.__name__):
        await receiver.receive_data()

    (message,) = [record.getMessage() for record in caplog.records if 'decode failed' in record.getMessage()]
    assert 'codec=opus' in message
    assert 'type=_OpusError' in message
    assert f'bytes={len(frame)}' in message
    assert 'corrupted stream' in message
    assert 'streak=1' in message


@pytest.mark.anyio
async def test_whole_stream_undecodable_reports_a_silent_mic_once(recorded_fallbacks):
    frame = b'\xff\xff\xff'
    frames = [{'bytes': frame}] * (DECODE_FAILURE_STREAK_ALERT + 3)
    receiver = _receiver(frames, _ScriptedDecoder({frame}))

    await receiver.receive_data()

    assert receiver.decode_failure_streak == DECODE_FAILURE_STREAK_ALERT + 3
    assert recorded_fallbacks == [
        {
            'component': 'silent_mic',
            'from_mode': 'opus',
            'to_mode': 'none',
            'reason': 'capability_mismatch',
            'outcome': 'exhausted',
        }
    ]


@pytest.mark.anyio
async def test_a_corrupt_packet_among_good_frames_never_reports(recorded_fallbacks):
    bad, good = b'\xff\xff\xff', b'opus-frame'
    frames = [{'bytes': bad}, {'bytes': good}] * (DECODE_FAILURE_STREAK_ALERT + 3)
    receiver = _receiver(frames, _ScriptedDecoder({bad}))

    await receiver.receive_data()

    assert receiver.decode_failure_streak == 0
    assert recorded_fallbacks == []


@pytest.mark.anyio
async def test_multi_channel_decode_failure_names_its_channel(caplog, recorded_fallbacks):
    frame = b'\xff\xff\xff'
    receiver = _receiver([], _ScriptedDecoder({frame}))
    receiver.host.is_multi_channel = True
    receiver.channel_id_to_index = {7: 1}
    receiver.multi_opus_decoders = [None, _ScriptedDecoder({frame})]

    with caplog.at_level(logging.WARNING, logger=receiver_module.__name__):
        await receiver._handle_multi_channel_audio(bytes([7]) + frame)

    (message,) = [record.getMessage() for record in caplog.records if 'decode failed' in record.getMessage()]
    assert 'channel=1' in message
    assert f'bytes={len(frame)}' in message
    assert receiver.decode_failure_streak == 1


@pytest.mark.skipif(receiver_module.opuslib is None, reason='opuslib/libopus unavailable')
@pytest.mark.anyio
async def test_real_libopus_rejection_is_reported_with_its_own_message(caplog, recorded_fallbacks):
    # libopus decodes most arbitrary bytes; b'\xff\xff\xff' is a packet it actually rejects,
    # which is how prod's storm looked from the inside.
    frame = b'\xff\xff\xff'
    receiver = _receiver([{'bytes': frame}], receiver_module.opuslib.Decoder(16000, 1))

    with caplog.at_level(logging.WARNING, logger=receiver_module.__name__):
        await receiver.receive_data()

    (message,) = [record.getMessage() for record in caplog.records if 'decode failed' in record.getMessage()]
    assert 'type=OpusError' in message
    assert 'corrupted stream' in message
