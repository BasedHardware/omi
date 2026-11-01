"""Custom STT with "send raw audio to Omi" off: the transcript must still persist.

The app's composite socket then forwards only `suggested_transcript` text to
/v4/listen, so no binary frame ever reaches `_mark_first_audio`. The legacy
persistence loop needs a clock origin before it writes segments; without one it
dropped every batch and the empty conversation was deleted at close.
"""

import asyncio
import json
from collections import deque
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import routers.listen.receiver as receiver_module
import routers.listen.transcripts as transcripts_module
from models.transcript_segment import CombineSegmentsResult
from routers.listen.receiver import ListenReceiver
from routers.listen.transcripts import TranscriptProcessor
from utils.transcribe_decisions import custom_stt_clock_origin

NOW = 1_800_000_000.0


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture
def funnel(monkeypatch):
    outcomes = []
    monkeypatch.setattr(receiver_module, 'record_listen_audio_outcome', lambda **kwargs: outcomes.append(kwargs))
    monkeypatch.setattr(receiver_module.time, 'time', lambda: NOW)
    return outcomes


class _FramesWebSocket:
    def __init__(self, frames):
        self.frames = iter(frames)

    async def receive(self):
        return next(self.frames)


def _suggested(*segments):
    return {'text': json.dumps({'type': 'suggested_transcript', 'stt_provider': 'customLive', 'segments': segments})}


def _receiver(state, frames, enqueue, *, use_custom_stt=True):
    live_transcription_starts = []
    host = SimpleNamespace(
        request=SimpleNamespace(websocket=_FramesWebSocket(frames), codec='opus'),
        state=state,
        limits=SimpleNamespace(ws_receive_timeout=1.0),
        is_multi_channel=False,
        use_custom_stt=use_custom_stt,
        audio_bytes_send=None,
        transcripts=SimpleNamespace(enqueue=enqueue),
        start_live_transcription=lambda: live_transcription_starts.append(True),
    )
    return ListenReceiver(host, [], {}), live_transcription_starts


def _state(first_audio_byte_timestamp=None):
    state = SimpleNamespace(
        active=True,
        close_code=1001,
        last_audio_received_time=None,
        last_activity_time=None,
        first_audio_byte_timestamp=first_audio_byte_timestamp,
        last_usage_record_timestamp=None,
        audio_ring_buffer=None,
        last_transcript_time=None,
        words_transcribed_since_last_record=0,
        current_conversation_id='conversation-1',
        speaker_id_done=asyncio.Event(),
    )
    state.speaker_id_done.set()
    return state


def _processor(monkeypatch, state, persisted):
    class Segment:
        def __init__(self, **data):
            self.id = data['id']
            self.text = data['text']
            self.start = data['start']
            self.end = data['end']
            self.speech_profile_processed = data['speech_profile_processed']
            self.is_user = False
            self.speaker_id = data.get('speaker_id')

        def model_dump(self):
            return {'id': self.id, 'text': self.text}

        @staticmethod
        def combine_segments(_existing, new_segments):
            return CombineSegmentsResult(segments=new_segments, joined=[], removed_ids=[], absorbed_into={})

    async def wait(_seconds):
        state.active = False
        return False

    async def cache_get(_conversation_id):
        return {'transcript_segments': []}

    async def update(_conversation, segments, _photos, _finished_at, started_at):
        persisted.append((segments, started_at))
        return SimpleNamespace(id='conversation-1'), segments, []

    async def no_op(*_args, **_kwargs):
        return None

    async def send_json(_payload):
        return None

    host = SimpleNamespace(
        state=state,
        wait=wait,
        request=SimpleNamespace(uid='user-1', onboarding_mode=False, websocket=SimpleNamespace(send_json=send_json)),
        transcript_send=None,
        user_has_credits=True,
        pusher_enabled=True,
        onboarding_handler=None,
        use_custom_stt=True,
        send_event=lambda _event: None,
        speakers=SimpleNamespace(drain=no_op, tasks=set()),
        complete_live_transcription=lambda: None,
    )
    processor = object.__new__(TranscriptProcessor)
    processor.host = host
    processor.segment_buffer = deque()
    processor._v2_legacy_fallback = deque()
    processor._v2_legacy_fallback_ids = set()
    processor.photo_buffer = deque()
    processor.cache = SimpleNamespace(get=cache_get)
    processor.current_session_segments = {}
    processor.speaker_id_allocator = SimpleNamespace(
        hydrate=lambda _segments: None, hydrate_receipt=MagicMock(), assign=lambda _segment: None
    )
    processor._update_live_conversation = update
    processor._translate = no_op
    processor._speaker_detection = no_op
    processor.flush_speaker_assignments = no_op
    processor._flush_failures = 0
    processor._flush_backoff_until = 0.0
    monkeypatch.setattr(transcripts_module, 'TranscriptSegment', Segment)
    monkeypatch.setattr(transcripts_module, 'deserialize_conversation', lambda _data: SimpleNamespace())
    return processor


@pytest.mark.anyio
async def test_custom_transcript_without_raw_audio_is_persisted(monkeypatch, funnel):
    state = _state()
    persisted = []
    processor = _processor(monkeypatch, state, persisted)
    receiver, live_transcription_starts = _receiver(
        state,
        [
            _suggested(
                {'id': 'a', 'text': 'Hola', 'start': 81.0, 'end': 82.5},
                {'id': 'b', 'text': 'Buenos días', 'start': 83.0, 'end': 84.0},
            ),
            {'type': 'websocket.disconnect', 'code': 1000},
        ],
        processor.segment_buffer.extend,
    )

    await receiver.receive_data()
    await processor.process_loop()

    assert len(persisted) == 1
    segments, started_at = persisted[0]
    assert [segment.id for segment in segments] == ['a', 'b']
    # The provider stream began about `end` seconds before its latest segment arrived.
    assert state.first_audio_byte_timestamp == NOW - 84.0
    assert started_at.timestamp() == NOW - 84.0
    assert [segment.start for segment in segments] == [81.0, 83.0]
    assert started_at.timestamp() + segments[0].start == NOW - 3.0
    # No audio was accepted: the first-audio funnel, provider journey and
    # usage window stay untouched.
    assert funnel == []
    assert live_transcription_starts == []
    assert state.last_usage_record_timestamp is None


def _text_receiver(state, enqueued, *, use_custom_stt=True):
    host = SimpleNamespace(
        request=SimpleNamespace(codec='opus'),
        state=state,
        is_multi_channel=False,
        use_custom_stt=use_custom_stt,
        transcripts=SimpleNamespace(enqueue=enqueued.extend),
    )
    return ListenReceiver(host, [], {})


@pytest.mark.anyio
async def test_custom_transcript_keeps_an_existing_audio_clock(funnel):
    state = _state(first_audio_byte_timestamp=NOW - 300.0)
    enqueued = []
    receiver = _text_receiver(state, enqueued)

    await receiver._handle_text(_suggested({'id': 'a', 'text': 'Hola', 'start': 1.0, 'end': 2.0})['text'])

    assert state.first_audio_byte_timestamp == NOW - 300.0
    assert [segment['id'] for segment in enqueued] == ['a']


@pytest.mark.anyio
async def test_custom_transcript_clock_never_starts_in_the_future(funnel):
    state = _state()
    enqueued = []
    receiver = _text_receiver(state, enqueued)

    await receiver._handle_text(
        _suggested({'id': 'a', 'text': 'Hola', 'end': -5.0}, {'id': 'b', 'text': 'Sí', 'end': float('inf')})['text']
    )

    assert state.first_audio_byte_timestamp == NOW
    assert len(enqueued) == 2


@pytest.mark.anyio
async def test_suggested_transcript_outside_custom_stt_sets_no_clock(funnel):
    state = _state()
    enqueued = []
    receiver = _text_receiver(state, enqueued, use_custom_stt=False)

    await receiver._handle_text(_suggested({'id': 'a', 'text': 'Hola', 'start': 1.0, 'end': 2.0})['text'])

    assert state.first_audio_byte_timestamp is None
    assert enqueued == []


@pytest.mark.parametrize(
    ('segments', 'origin'),
    [
        ([{'end': 3.0}, {'end': 7.5}], NOW - 7.5),
        ([{'end': True}, {'end': 'soon'}, {'text': 'no end'}, 'not a segment'], NOW),
        ([], None),
        ({'end': 7.5}, None),
        (None, None),
    ],
)
def test_custom_stt_clock_origin(segments, origin):
    assert custom_stt_clock_origin(segments, NOW) == origin
