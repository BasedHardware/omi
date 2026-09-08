"""Opus frames longer than the negotiated duration must still decode.

`Decoder.decode(data, frame_size)` treats `frame_size` as the capacity of the output
buffer, not as a declaration of the packet's frame length; libopus answers
OPUS_BUFFER_TOO_SMALL when a packet holds more samples than fit. Passing the negotiated
duration therefore dropped every frame of any session whose client sent longer frames
than its `codec` query parameter implied — prod logged a sustained
`Listen audio frame decode failed codec=opus type=OpusError` storm with no audio ever
reaching STT, the ring buffer, or the audio-bytes consumers.
"""

from types import SimpleNamespace

import pytest

from routers.listen.receiver import ListenReceiver, opus_decode_capacity


@pytest.fixture
def anyio_backend():
    return 'asyncio'


class _BufferTooSmall(Exception):
    """Stands in for opuslib.OpusError(b'buffer too small')."""


class _ContractOpusDecoder:
    """Mirrors libopus' decode contract for a fixed frame length.

    Real `opuslib.Decoder.decode` writes at most `samples_per_frame` samples and raises
    when the caller's buffer cannot hold them, so the buffer size only ever needs to be
    large enough — a 10 ms packet under a 120 ms buffer still yields 10 ms of PCM.
    """

    def __init__(self, samples_per_frame: int):
        self.samples_per_frame = samples_per_frame
        self.rejected = 0

    def decode(self, data: bytes, frame_size: int) -> bytes:
        if frame_size < self.samples_per_frame:
            self.rejected += 1
            raise _BufferTooSmall('buffer too small')
        return b'\x01\x02' * self.samples_per_frame


class _FramesWebSocket:
    def __init__(self, frames):
        self.frames = iter(frames)

    async def receive(self):
        return next(self.frames)


class _RingBuffer:
    def __init__(self):
        self.written = bytearray()

    def write(self, pcm: bytes, _timestamp: float) -> None:
        self.written.extend(pcm)


def _host(websocket, sample_rate: int, ring_buffer, audio_bytes):
    return SimpleNamespace(
        request=SimpleNamespace(websocket=websocket, codec='opus', sample_rate=sample_rate),
        state=SimpleNamespace(
            active=True,
            close_code=1001,
            last_audio_received_time=None,
            last_activity_time=None,
            first_audio_byte_timestamp=None,
            last_usage_record_timestamp=None,
            audio_ring_buffer=ring_buffer,
        ),
        limits=SimpleNamespace(ws_receive_timeout=1.0),
        is_multi_channel=False,
        use_custom_stt=True,
        audio_bytes_send=lambda pcm, _now: audio_bytes.extend(pcm),
        transcripts=SimpleNamespace(enqueue=lambda _segments: None),
        start_live_transcription=lambda: None,
    )


def test_opus_decode_capacity_covers_the_longest_opus_frame():
    # 120 ms is the longest frame Opus can carry, so no legal packet can overflow it.
    assert opus_decode_capacity(16000) == 1920
    assert opus_decode_capacity(48000) == 5760
    assert opus_decode_capacity(8000) == 960


@pytest.mark.anyio
@pytest.mark.parametrize('frame_ms', [20, 40, 60])
async def test_receiver_decodes_frames_longer_than_the_negotiated_duration(frame_ms):
    sample_rate = 16000
    samples_per_frame = sample_rate // 1000 * frame_ms
    ring_buffer = _RingBuffer()
    audio_bytes = bytearray()
    websocket = _FramesWebSocket(
        [
            {'bytes': b'opus-frame-1'},
            {'bytes': b'opus-frame-2'},
            {'type': 'websocket.disconnect', 'code': 1000},
        ]
    )
    decoder = _ContractOpusDecoder(samples_per_frame)
    receiver = ListenReceiver(_host(websocket, sample_rate, ring_buffer, audio_bytes), [], {})
    receiver.opus_decoder = decoder

    await receiver.receive_data()

    assert decoder.rejected == 0
    assert len(ring_buffer.written) == 2 * samples_per_frame * 2
    assert len(audio_bytes) == 2 * samples_per_frame * 2


@pytest.mark.anyio
async def test_receiver_still_decodes_the_negotiated_ten_millisecond_frame():
    sample_rate = 16000
    ring_buffer = _RingBuffer()
    audio_bytes = bytearray()
    websocket = _FramesWebSocket(
        [
            {'bytes': b'opus-frame-1'},
            {'type': 'websocket.disconnect', 'code': 1000},
        ]
    )
    receiver = ListenReceiver(_host(websocket, sample_rate, ring_buffer, audio_bytes), [], {})
    receiver.opus_decoder = _ContractOpusDecoder(160)

    await receiver.receive_data()

    # A larger buffer never inflates the output: the packet's own frame length decides it.
    assert len(ring_buffer.written) == 160 * 2
    assert len(audio_bytes) == 160 * 2


@pytest.mark.anyio
async def test_multi_channel_receiver_decodes_frames_longer_than_twenty_milliseconds():
    sample_rate = 16000
    samples_per_frame = sample_rate // 1000 * 60
    host = SimpleNamespace(
        request=SimpleNamespace(codec='opus', sample_rate=sample_rate),
        state=SimpleNamespace(fair_use_dg_budget_exhausted=False, fair_use_track_dg_usage=False),
        use_custom_stt=True,
        audio_bytes_send=None,
    )
    receiver = ListenReceiver(host, [SimpleNamespace()], {1: 0})
    decoder = _ContractOpusDecoder(samples_per_frame)
    receiver.multi_opus_decoders[0] = decoder

    await receiver._handle_multi_channel_audio(b'\x01opus-frame-1')

    assert decoder.rejected == 0
