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
                        'segments': [{'text': 'Recovered transcript', 'start': 0.0, 'end': 1.0}],
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

    assert len(received_segments) == 1
    recovered = received_segments[0]
    assert recovered['text'] == 'Recovered transcript'
    assert recovered['stt_provider'] == 'test-provider'
    assert 'id' not in recovered
    assert 'speech_profile_processed' not in recovered
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


def _speaker_assigned_host(person_lookup):
    return SimpleNamespace(
        request=SimpleNamespace(uid='u1'),
        state=SimpleNamespace(current_conversation_id=None, first_audio_byte_timestamp=None),
        speakers=SimpleNamespace(speaker_to_person={}, segment_assignments={}),
        transcripts=SimpleNamespace(current_session_segments={}),
        private_cloud_sync_enabled=False,
        send_speaker_sample_request=None,
        persistence=SimpleNamespace(call=person_lookup),
    )


@pytest.mark.anyio
async def test_speaker_assigned_rejects_a_person_id_not_owned_by_the_uid():
    async def lookup(_function, _uid, _person_id):
        return None

    host = _speaker_assigned_host(lookup)
    receiver = ListenReceiver(host, [], {})

    await receiver._handle_speaker_assigned(
        {'type': 'speaker_assigned', 'speaker_id': 1, 'person_id': 'other-tenant', 'person_name': 'Mallory'}
    )

    assert host.speakers.speaker_to_person == {}
    assert host.speakers.segment_assignments == {}


@pytest.mark.anyio
async def test_speaker_assigned_accepts_an_owned_person_id():
    async def lookup(_function, _uid, person_id):
        return {'id': person_id}

    host = _speaker_assigned_host(lookup)
    receiver = ListenReceiver(host, [], {})

    await receiver._handle_speaker_assigned(
        {'speaker_id': 1, 'person_id': 'p1', 'person_name': 'Alice', 'segment_ids': ['s1']}
    )

    assert host.speakers.speaker_to_person == {1: ('p1', 'Alice')}
    assert host.speakers.segment_assignments == {'s1': 'p1'}


@pytest.mark.anyio
async def test_speaker_assigned_drops_a_malformed_payload_without_raising():
    async def lookup(*_args):
        raise AssertionError('lookup must not run for a malformed payload')

    host = _speaker_assigned_host(lookup)
    receiver = ListenReceiver(host, [], {})

    await receiver._handle_speaker_assigned({'speaker_id': 'not-an-int', 'person_id': 'p1'})

    assert host.speakers.speaker_to_person == {}
