"""Listen receiver frame-level recovery regressions."""

import json
from types import SimpleNamespace

import pytest

from routers.listen.receiver import ListenReceiver


@pytest.fixture
def anyio_backend():
    return 'asyncio'


class _FramesWebSocket:
    def __init__(self, frames):
        self.frames = iter(frames)

    async def receive(self):
        return next(self.frames)


class _BrokenDecoder:
    def decode(self, *_args, **_kwargs):
        raise ValueError('malformed frame')


@pytest.mark.anyio
@pytest.mark.parametrize(
    ('codec', 'decoder_attribute'),
    [
        ('opus', 'opus_decoder'),
        ('aac', 'aac_decoder'),
        ('lc3', 'lc3_decoder'),
    ],
)
async def test_receiver_drops_malformed_codec_frame_and_continues_to_custom_transcript(codec, decoder_attribute):
    received_segments = []
    websocket = _FramesWebSocket(
        [
            {'text': '{not valid json'},
            {'bytes': b'malformed-frame'},
            {
                'text': json.dumps(
                    {
                        'type': 'suggested_transcript',
                        'stt_provider': 'test-provider',
                        'segments': [{'id': 'recovered', 'text': 'Recovered transcript'}],
                    }
                )
            },
            {'type': 'websocket.disconnect', 'code': 1000},
        ]
    )
    host = SimpleNamespace(
        request=SimpleNamespace(websocket=websocket, codec=codec),
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
        frame_size=320,
        use_custom_stt=True,
        audio_bytes_send=None,
        transcripts=SimpleNamespace(enqueue=received_segments.extend),
    )
    receiver = ListenReceiver(host, [], {})
    setattr(receiver, decoder_attribute, _BrokenDecoder())

    await receiver.receive_data()

    assert received_segments == [{'id': 'recovered', 'text': 'Recovered transcript', 'stt_provider': 'test-provider'}]
    assert host.state.close_code == 1000


@pytest.mark.anyio
async def test_multi_channel_receiver_drops_malformed_opus_frame_without_mixing_it():
    host = SimpleNamespace(
        request=SimpleNamespace(codec='opus', sample_rate=16000),
        state=SimpleNamespace(),
        use_custom_stt=True,
    )
    receiver = ListenReceiver(host, [SimpleNamespace()], {1: 0})
    receiver.multi_opus_decoders[0] = _BrokenDecoder()

    await receiver._handle_multi_channel_audio(b'\x01malformed-frame')

    assert receiver.channel_mix_buffers == [bytearray()]
