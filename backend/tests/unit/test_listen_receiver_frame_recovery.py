"""Listen receiver frame-level recovery regressions."""

import json
from types import SimpleNamespace

import pytest

from routers.listen.receiver import ListenReceiver
from utils.product_telemetry import set_product_telemetry_client_for_tests


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture(autouse=True)
def _reset_product_telemetry_client():
    yield
    set_product_telemetry_client_for_tests(None)


class _FramesWebSocket:
    def __init__(self, frames):
        self.frames = iter(frames)

    async def receive(self):
        return next(self.frames)


class _BrokenDecoder:
    def decode(self, *_args, **_kwargs):
        raise ValueError('malformed frame')


class _TelemetryClient:
    def __init__(self):
        self.events = []

    def capture(self, **event):
        self.events.append(event)


class _VadGate:
    def get_metrics(self):
        return {'speech_ms_total': 1250, 'mode': 'active'}

    def to_json_log(self):
        return self.get_metrics()


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
    live_transcription_starts = []
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
        use_custom_stt=True,
        audio_bytes_send=None,
        transcripts=SimpleNamespace(enqueue=received_segments.extend),
        start_live_transcription=lambda: live_transcription_starts.append(True),
    )
    receiver = ListenReceiver(host, [], {})
    setattr(receiver, decoder_attribute, _BrokenDecoder())

    await receiver.receive_data()

    assert received_segments == [{'id': 'recovered', 'text': 'Recovered transcript', 'stt_provider': 'test-provider'}]
    assert live_transcription_starts == [True]
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


@pytest.mark.anyio
async def test_receiver_emits_decoded_audio_duration_at_session_end():
    telemetry = _TelemetryClient()
    set_product_telemetry_client_for_tests(telemetry)
    websocket = _FramesWebSocket([{'bytes': b'\x01\x00' * 16000}, {'type': 'websocket.disconnect', 'code': 1000}])
    host = SimpleNamespace(
        request=SimpleNamespace(websocket=websocket, codec='pcm16', sample_rate=16000, uid='user-1'),
        state=SimpleNamespace(
            active=True,
            close_code=1001,
            last_audio_received_time=None,
            last_activity_time=None,
            first_audio_byte_timestamp=None,
            last_usage_record_timestamp=None,
            audio_ring_buffer=None,
            current_conversation_id='conversation-1',
        ),
        limits=SimpleNamespace(ws_receive_timeout=1.0),
        is_multi_channel=False,
        frame_size=320,
        use_custom_stt=True,
        audio_bytes_send=None,
        recording_session_id='recording-1',
        transcripts=SimpleNamespace(enqueue=lambda _: None),
        start_live_transcription=lambda: None,
    )
    receiver = ListenReceiver(host, [], {})

    await receiver.receive_data()

    assert telemetry.events[0]['event'] == 'Encoded Audio Duration Measured'
    assert telemetry.events[0]['properties']['duration_seconds'] == 1.0
    assert telemetry.events[0]['properties']['recording_id'] == 'recording-1'


@pytest.mark.anyio
async def test_receiver_emits_speech_positive_duration_at_session_end():
    telemetry = _TelemetryClient()
    set_product_telemetry_client_for_tests(telemetry)
    websocket = _FramesWebSocket([{'type': 'websocket.disconnect', 'code': 1000}])
    host = SimpleNamespace(
        request=SimpleNamespace(websocket=websocket, codec='pcm16', uid='user-1'),
        state=SimpleNamespace(
            active=True,
            close_code=1001,
            last_audio_received_time=None,
            last_activity_time=None,
            first_audio_byte_timestamp=None,
            last_usage_record_timestamp=None,
            audio_ring_buffer=None,
            current_conversation_id='conversation-1',
        ),
        limits=SimpleNamespace(ws_receive_timeout=1.0),
        is_multi_channel=False,
        frame_size=320,
        use_custom_stt=True,
        audio_bytes_send=None,
        recording_session_id='recording-1',
        transcripts=SimpleNamespace(enqueue=lambda _: None),
        start_live_transcription=lambda: None,
    )
    receiver = ListenReceiver(host, [], {})
    receiver.vad_gate = _VadGate()

    await receiver.receive_data()

    assert telemetry.events[0]['event'] == 'Speech Positive Duration Measured'
    assert telemetry.events[0]['properties']['duration_seconds'] == 1.25
    assert telemetry.events[0]['properties']['measurement'] == 'server_vad'
