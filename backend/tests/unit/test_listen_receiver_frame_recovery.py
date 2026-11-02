"""Listen receiver frame-level recovery regressions."""

import asyncio
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
        request=SimpleNamespace(websocket=websocket, uid='test-uid', codec=codec),
        state=SimpleNamespace(
            current_conversation_id=None,
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

    assert len(received_segments) == 1
    assert received_segments[0]['id'] == 'recovered'
    assert received_segments[0]['text'] == 'Recovered transcript'
    assert received_segments[0]['stt_provider'] == 'test-provider'
    assert received_segments[0]['speaker_id_scope'].endswith(':0')
    # The only bytes frame was undecodable, so no audio was ever accepted for
    # STT: live transcription must not claim it started on a silent stream.
    assert live_transcription_starts == []
    assert host.state.close_code == 1000


@pytest.mark.anyio
async def test_multi_channel_receiver_drops_malformed_opus_frame_without_mixing_it():
    host = SimpleNamespace(
        request=SimpleNamespace(uid='test-uid', codec='opus', sample_rate=16000),
        state=SimpleNamespace(current_conversation_id=None),
        is_multi_channel=True,
        use_custom_stt=True,
    )
    receiver = ListenReceiver(host, [SimpleNamespace()], {1: 0})
    receiver.multi_opus_decoders[0] = _BrokenDecoder()

    await receiver._handle_multi_channel_audio(b'\x01malformed-frame')

    assert receiver.channel_mix_buffers == [bytearray()]


@pytest.mark.anyio
async def test_receiver_emits_decoded_audio_duration_at_session_end(monkeypatch):
    import routers.listen.receiver as receiver_module

    telemetry = _TelemetryClient()
    set_product_telemetry_client_for_tests(telemetry)
    source_events = []
    emit_product_event = receiver_module.emit_product_event

    def capture_source_event(**event):
        source_events.append(event)
        return emit_product_event(**event)

    monkeypatch.setattr(receiver_module, 'emit_product_event', capture_source_event)
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
    assert source_events[0]['properties']['recording_id'] == 'recording-1'
    assert source_events[0]['properties']['conversation_id'] == 'conversation-1'
    assert not {'recording_id', 'conversation_id'} & telemetry.events[0]['properties'].keys()


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


@pytest.mark.anyio
async def test_archive_wait_starts_after_transcript_drain(monkeypatch):
    websocket = _FramesWebSocket([{'type': 'websocket.disconnect', 'code': 1000}])
    host = SimpleNamespace(
        request=SimpleNamespace(websocket=websocket, uid='test-uid', codec='pcm16'),
        state=SimpleNamespace(
            active=True,
            close_code=1001,
            current_conversation_id=None,
            first_audio_byte_timestamp=None,
            last_usage_record_timestamp=None,
        ),
        limits=SimpleNamespace(ws_receive_timeout=1.0),
        is_multi_channel=False,
        use_custom_stt=True,
        audio_bytes_send=None,
        start_live_transcription=lambda: None,
    )
    receiver = ListenReceiver(host, [], {})
    tail_sent = asyncio.Event()
    release_archive = asyncio.Event()

    async def drain(*args):
        tail_sent.set()

    async def slow_archive():
        assert tail_sent.is_set()
        assert receiver.stt_drain_complete.is_set()
        assert not host.state.active
        await release_archive.wait()

    monkeypatch.setattr(receiver, '_teardown_body', drain)
    monkeypatch.setattr(receiver.raw_archive, 'close', slow_archive)
    task = asyncio.create_task(receiver.receive_data())
    try:
        await asyncio.wait_for(receiver.stt_drain_complete.wait(), timeout=1)
        assert tail_sent.is_set()
        assert not task.done()
    finally:
        release_archive.set()
        await asyncio.wait_for(task, timeout=1)
