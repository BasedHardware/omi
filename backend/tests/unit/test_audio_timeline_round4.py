"""Round-4 re-review regressions for the audio-timeline branch.

Locks the wiring the round-3 re-review flagged:

- N1: ownership fail-open no longer adopts a sample older than the oldest
  retained run (retention may have evicted the run and every boundary that
  would contradict the surviving single conversation); the fail-open applies
  only between retained runs, inside the retention horizon, when the retained
  runs are one conversation.
- N5: a provider callback deferred onto the listen loop runs on its own copy
  of the segment list, an exception inside it increments the rejected
  counter with a bounded log, and a closed loop still drops quietly.
"""

import asyncio
import logging
import time
import threading
from collections import Counter
from collections import deque
from types import SimpleNamespace

import pytest

from routers.listen.contracts import ListenSessionState
from routers.listen.receiver import ListenReceiver
from routers.listen.transcripts import TranscriptProcessor
from models.transcript_segment import TranscriptSegment
from utils.metrics import (
    OMI_AUDIO_TIMELINE_CALLBACK_ERRORS_TOTAL,
    OMI_AUDIO_TIMELINE_MAPPED_TOTAL,
    OMI_AUDIO_TIMELINE_REJECTS_TOTAL,
    OMI_AUDIO_TIMELINE_SEGMENTS_TOTAL,
    OMI_AUDIO_TIMELINE_PAST_SEND_TOTAL,
)

RATE = 16000
UID = 'uid-r4'
T0 = 1_700_000_000.0


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def _receiver(monkeypatch, *, v2: bool, conversation='conv-a') -> ListenReceiver:
    monkeypatch.setenv('AUDIO_TIMELINE_V2', 'true' if v2 else 'false')
    state = ListenSessionState()
    state.current_conversation_id = conversation
    collected = []
    host = SimpleNamespace(
        request=SimpleNamespace(uid=UID, websocket=None, codec='pcm16', sample_rate=RATE, channels=1, source='desktop'),
        state=state,
        is_multi_channel=False,
        use_custom_stt=False,
        audio_bytes_send=None,
        transcripts=SimpleNamespace(enqueue=collected.extend),
        client_device_context=SimpleNamespace(platform='test'),
        stt_service='soniox',
        spawn=lambda coro, *, name: asyncio.create_task(coro),
    )
    receiver = ListenReceiver(host, [], {})
    receiver.collected = collected
    return receiver


def _feed_contiguous(receiver: ListenReceiver, seconds: float, *, first_wall: float = T0, frame=0.5):
    """Feed real accepted frames through the capture clock and ownership map."""
    per_frame = int(frame * RATE)
    pcm = b'\x01\x00' * per_frame
    count = int(seconds / frame)
    first_start = None
    last_end = None
    for i in range(count):
        wall = first_wall + i * frame
        start, end, _ = receiver.capture_timeline.accept(pcm, wall + frame, wall + frame)
        receiver._note_accepted_frame(start, end)
        if first_start is None:
            first_start = start
        last_end = end
    return first_start, last_end


@pytest.mark.parametrize('v2,mode', [(False, 'legacy'), (True, 'v2')])
def test_epoch_metrics_expose_bounded_reasons_and_flag_off_denominator(monkeypatch, v2, mode):
    receiver = _receiver(monkeypatch, v2=v2)
    _feed_contiguous(receiver, 2.0)
    _, _, epoch = receiver._build_stt_callbacks()
    assert epoch is not None
    epoch.provider_label = 'modulate'
    epoch.note_accepted(0, 2 * RATE)
    mapped = OMI_AUDIO_TIMELINE_SEGMENTS_TOTAL.labels(mode=mode, outcome='mapped')
    rejected = OMI_AUDIO_TIMELINE_SEGMENTS_TOTAL.labels(mode=mode, outcome='rejected')
    recovered = OMI_AUDIO_TIMELINE_SEGMENTS_TOTAL.labels(mode=mode, outcome='recovered')
    provider_mapped = OMI_AUDIO_TIMELINE_MAPPED_TOTAL.labels(mode=mode, provider='modulate', send_path='unknown')
    outside = OMI_AUDIO_TIMELINE_REJECTS_TOTAL.labels(
        mode=mode, reason='outside_accepted_sends', provider='modulate', send_path='unknown'
    )
    zero = OMI_AUDIO_TIMELINE_REJECTS_TOTAL.labels(
        mode=mode, reason='zero_length', provider='modulate', send_path='unknown'
    )
    before = (
        mapped._value.get(),
        rejected._value.get(),
        recovered._value.get(),
        outside._value.get(),
        zero._value.get(),
        provider_mapped._value.get(),
    )
    result = epoch.translate(
        [
            {'start': 0.25, 'end': 0.75, 'text': 'inside'},
            {'start': 9.0, 'end': 10.0, 'text': 'outside'},
            {'start': 1.0, 'end': 1.0, 'text': 'partial'},
        ]
    )
    assert [segment['text'] for segment in result] == ['inside', 'outside', 'partial']
    assert rejected._value.get() == before[1] + (1 if v2 else 2)
    assert recovered._value.get() == before[2] + (1 if v2 else 0)
    assert outside._value.get() == before[3] + 1
    assert zero._value.get() == before[4] + (0 if v2 else 1)
    assert mapped._value.get() == before[0] + (0 if v2 else 1)
    assert provider_mapped._value.get() == before[5] + (2 if v2 else 1)


def test_v2_translation_preserves_text_when_provider_interval_cannot_be_placed(monkeypatch):
    receiver = _receiver(monkeypatch, v2=True)
    _feed_contiguous(receiver, 2.0)
    _, _, epoch = receiver._build_stt_callbacks()
    assert epoch is not None
    epoch.note_accepted(0, 2 * RATE)
    result = epoch.translate(
        [
            {'start': 0.25, 'end': 0.75, 'text': 'mapped'},
            {'start': 1.0, 'end': 1.0, 'text': 'point'},
            {'start': 9.0, 'end': 10.0, 'text': 'late'},
        ]
    )
    assert [segment['text'] for segment in result] == ['mapped', 'point', 'late']
    assert result[1]['_capture_end_sample'] > result[1]['_capture_start_sample']
    assert result[2]['audio_alignment'] == 'unplaced'
    assert result[2]['start'] == result[2]['end']


def test_rejected_text_keeps_owner_at_provider_send_across_rollover(monkeypatch):
    receiver = _receiver(monkeypatch, v2=True)
    _feed_contiguous(receiver, 2.0)
    _, _, epoch = receiver._build_stt_callbacks()
    assert epoch is not None
    epoch.provider_label = 'soniox'
    epoch.send_path = 'managed_chain'
    epoch.note_accepted(0, 2 * RATE)
    receiver.host.state.current_conversation_id = 'conv-b'
    past = OMI_AUDIO_TIMELINE_PAST_SEND_TOTAL.labels(provider='soniox', send_path='managed_chain', bucket='inf')
    before = past._value.get()
    receiver._enqueue_translated_segments(epoch.translate([{'text': 'late A', 'start': 200, 'end': 201}]))
    assert receiver.collected[0]['_conversation_id'] == 'conv-a'
    assert receiver.collected[0]['audio_alignment'] == 'unplaced'
    assert past._value.get() == before + 1


def test_ambiguous_send_epoch_uses_counted_current_row_fallback(monkeypatch):
    receiver = _receiver(monkeypatch, v2=True)
    _feed_contiguous(receiver, 2.0)
    _, _, epoch = receiver._build_stt_callbacks()
    epoch.note_accepted(0, 2 * RATE)
    receiver.host.state.current_conversation_id = 'conv-b'
    _feed_contiguous(receiver, 2.0, first_wall=T0 + 2)
    epoch.note_accepted(2 * RATE, 2 * RATE)
    unavailable = OMI_AUDIO_TIMELINE_SEGMENTS_TOTAL.labels(mode='v2', outcome='send_owner_unavailable')
    before = unavailable._value.get()
    receiver._enqueue_translated_segments(epoch.translate([{'text': 'ambiguous late final', 'start': 30, 'end': 31}]))
    assert receiver.collected[0]['_conversation_id'] == 'conv-b'
    assert receiver.collected[0]['audio_alignment'] == 'unplaced'
    assert unavailable._value.get() == before + 1


def test_send_owner_checks_the_entire_capture_span(monkeypatch):
    receiver = _receiver(monkeypatch, v2=True)
    receiver.host.state.conversation_sample_ranges = deque(
        [(0, RATE, 'conv-a'), (RATE, 2 * RATE, 'conv-b'), (2 * RATE, 3 * RATE, 'conv-a')]
    )
    assert receiver._proven_send_owner(0, 3 * RATE) is None
    assert receiver._proven_send_owner(2 * RATE, RATE) == 'conv-a'


async def test_v2_persist_exception_requeues_pristine_batch():
    processor = object.__new__(TranscriptProcessor)
    processor.segment_buffer = deque([{'id': 's1', 'text': 'kept', 'start': T0, 'end': T0 + 1}])
    processor.photo_buffer = deque()
    processor._v2_retry_counts = {}
    processor._v2_legacy_fallback = deque()
    processor._v2_legacy_fallback_ids = set()
    processor._v2_retry_until = 0.0
    processor._v2_committed_ids = set()
    processor._v2_photos_committed = False
    processor._v2_photos_requeued = False
    processor._v2_photo_failures = 0
    processor.host = SimpleNamespace(
        state=SimpleNamespace(active=False, capture_timeline_v2=True, current_conversation_id='conv-a'),
        wait=lambda seconds: asyncio.sleep(min(seconds, 0.01), result=False),
        speakers=SimpleNamespace(tasks=[], drain=lambda **kwargs: asyncio.sleep(0)),
    )
    attempts = []

    async def persist(segments, photos, diarized):
        attempts.append([dict(segment) for segment in segments])
        segments[0]['start'] = -1
        if len(attempts) == 1:
            raise RuntimeError('one transient database error')

    processor._process_v2_batches = persist
    processor.flush_speaker_assignments = lambda owner: asyncio.sleep(0)
    await processor.process_loop()
    assert len(attempts) == 2
    assert attempts[0] == attempts[1] == [{'id': 's1', 'text': 'kept', 'start': T0, 'end': T0 + 1}]
    assert not processor.segment_buffer


def test_every_provider_segment_reaches_owner_or_counted_unplaced_fallback(monkeypatch):
    """A receiver continue/drop path fails this text multiset invariant."""
    receiver = _receiver(monkeypatch, v2=True)
    _feed_contiguous(receiver, 2.0)
    receiver.host.state.current_conversation_id = 'conv-b'
    _feed_contiguous(receiver, 2.0, first_wall=T0 + 2.0)
    _, _, epoch = receiver._build_stt_callbacks()
    assert epoch is not None
    epoch.note_accepted(0, 4 * RATE)
    provider = [
        {'text': 'owner A', 'start': 0.2, 'end': 0.6},
        {'text': 'owner B', 'start': 2.2, 'end': 2.6},
        {'text': 'straddle', 'start': 1.9, 'end': 2.1},
        {'text': 'outside', 'start': 20.0, 'end': 21.0},
        {'text': 'point', 'start': 2.5, 'end': 2.5},
        {'text': 'non numeric', 'start': 'bad', 'end': 2.0},
        {'text': 'non finite', 'start': float('nan'), 'end': 2.0},
    ]
    translated = epoch.translate(provider)
    translated.append({'text': 'missing window', 'start': T0, 'end': T0, 'is_user': False})
    receiver._enqueue_translated_segments(translated)
    expected = Counter(item['text'] for item in provider) + Counter({'missing window': 1})
    assert Counter(item['text'] for item in receiver.collected) == expected
    assert {item['_conversation_id'] for item in receiver.collected} <= {'conv-a', 'conv-b'}
    for item in receiver.collected:
        if item['text'] in {'straddle', 'outside', 'non numeric', 'non finite', 'missing window'}:
            assert item['audio_alignment'] == 'unplaced'


def test_v2_persist_retry_is_bounded_and_backed_off():
    processor = object.__new__(TranscriptProcessor)
    processor.segment_buffer = deque()
    processor._v2_retry_counts = {}
    processor._v2_legacy_fallback = deque()
    processor._v2_legacy_fallback_ids = set()
    processor._v2_retry_until = 0.0
    processor._v2_committed_ids = set()
    exhausted = OMI_AUDIO_TIMELINE_SEGMENTS_TOTAL.labels(mode='v2', outcome='persist_retry_exhausted')
    before = exhausted._value.get()
    for attempt in range(1, 7):
        processor._queue_v2_retry([{'id': 'persistent-failure', 'text': 'kept until bounded exhaustion'}])
        if attempt <= 5:
            assert len(processor.segment_buffer) == attempt
            assert processor._v2_retry_until > time.monotonic()
    assert len(processor.segment_buffer) == 5
    assert exhausted._value.get() == before + 1
    assert 'persistent-failure' not in processor._v2_retry_counts
    assert [item['text'] for item in processor._v2_legacy_fallback] == ['kept until bounded exhaustion']


def test_speaker_work_requires_a_proven_capture_window():
    queue = asyncio.Queue()
    processor = object.__new__(TranscriptProcessor)
    processor.host = SimpleNamespace(
        speakers=SimpleNamespace(queue=queue, person_embeddings={'voice': object()}, speaker_to_person={}),
        state=SimpleNamespace(speaker_id_enabled=True, current_conversation_id='active'),
    )
    processor.suggested_segments = set()
    raw = [
        {'id': 'unplaced', 'speaker_id': 0, 'start': -1, 'end': -1, 'audio_alignment': 'unplaced'},
        {'id': 'rejected-v1', 'speaker_id': 0, 'start': 100, 'end': 101, '_capture_window_unavailable': True},
        {'id': 'mapped', 'speaker_id': 0, 'start': 1, 'end': 2},
    ]
    processor._queue_raw_detections(raw, {'mapped': (T0 + 1, T0 + 2)}, T0)
    assert queue.qsize() == 1
    assert queue.get_nowait()['abs_start'] == T0 + 1


def test_unplaced_marker_survives_serialization_without_changing_v1_segments():
    legacy = TranscriptSegment(text='before', is_user=False, start=1, end=2)
    unplaced = TranscriptSegment(text='after', is_user=False, start=2, end=2, audio_alignment='unplaced')
    assert 'audio_alignment' not in legacy.model_dump()
    assert 'audio_alignment' not in legacy.model_dump_json()
    assert unplaced.model_dump()['audio_alignment'] == 'unplaced'
    combined = TranscriptSegment.combine_segments([legacy], [unplaced])
    assert [segment.text for segment in combined.segments] == ['before', 'after']


def test_capture_run_survives_persistence_and_blocks_cross_gap_merge():
    before = TranscriptSegment(text='first', is_user=False, start=0, end=1, audio_capture_run=0)
    after = TranscriptSegment(text='second', is_user=False, start=1.5, end=2.5, audio_capture_run=5 * RATE)
    assert before.model_dump()['audio_capture_run'] == 0
    assert after.model_dump()['audio_capture_run'] == 5 * RATE
    combined = TranscriptSegment.combine_segments([before], [after])
    assert [segment.text for segment in combined.segments] == ['first', 'second']


def test_v2_keeps_unparseable_and_nonfinite_text_but_legacy_retains_old_policy():
    from utils.audio_timeline import CaptureTimeline, ProviderEpochTranslator

    timeline = CaptureTimeline(RATE)
    timeline.accept(b'\x01\x00' * RATE, T0, T0)
    cases = [
        {'start': 'bad', 'end': 1.0, 'text': 'bad number'},
        {'start': float('nan'), 'end': 1.0, 'text': 'nonfinite'},
    ]
    v2 = ProviderEpochTranslator(timeline, RATE, project_times=True)
    legacy = ProviderEpochTranslator(timeline, RATE, project_times=False)
    assert [segment['text'] for segment in v2.translate(cases)] == ['bad number', 'nonfinite']
    assert all(segment['audio_alignment'] == 'unplaced' for segment in v2.translate(cases))
    assert legacy.translate(cases) == []


def test_unplaced_text_with_evicted_owner_keeps_send_owner(monkeypatch):
    receiver = _receiver(monkeypatch, v2=True, conversation='current')
    _feed_contiguous(receiver, 2.0)
    receiver.host.state.conversation_sample_ranges = deque([(RATE, 2 * RATE, 'current')])
    receiver._enqueue_translated_segments(
        [
            {
                'start': T0 - 60,
                'end': T0 - 60,
                'text': 'late final',
                'audio_alignment': 'unplaced',
                '_capture_unplaced': True,
                '_provider_send_owner': 'send-owner',
            }
        ]
    )
    assert len(receiver.collected) == 1
    assert receiver.collected[0]['_conversation_id'] == 'send-owner'
    assert receiver.collected[0]['start'] == receiver.collected[0]['end'] == T0 - 60


# ---------------------------------------------------------------------------
# N1: the owner fail-open cannot reach below the oldest retained run
# ---------------------------------------------------------------------------
async def test_final_older_than_retained_runs_keeps_unplaced_text(monkeypatch):
    receiver = _receiver(monkeypatch, v2=True)
    _feed_contiguous(receiver, 30.0, frame=0.5)  # conversation A: [0, 30s)
    receiver.host.state.current_conversation_id = 'conv-b'
    # 125 s of B: more than the 120 s retention past A's end, so A's run is
    # evicted and the retained window shows only B.
    _feed_contiguous(receiver, 125.0, first_wall=T0 + 30.0, frame=1.0)

    ranges = receiver.host.state.conversation_sample_ranges
    assert len(ranges) == 1 and ranges[0][2] == 'conv-b', "retention must have trimmed conversation A's run"

    fallback = OMI_AUDIO_TIMELINE_SEGMENTS_TOTAL.labels(mode='v2', outcome='late_owner_fallback')
    before = fallback._value.get()
    receiver._enqueue_translated_segments(
        [
            {
                'id': 'ancient',
                'speaker_id': 0,
                'start': receiver.capture_timeline.wall(RATE),
                'end': receiver.capture_timeline.wall(2 * RATE),
                'text': 'late final for conversation A',
                'is_user': False,
                '_capture_start_sample': RATE,
                '_capture_end_sample': 2 * RATE,
                '_provider_send_owner': 'conv-a',
            }
        ]
    )
    assert [segment['text'] for segment in receiver.collected] == ['late final for conversation A']
    assert receiver.collected[0]['_conversation_id'] == 'conv-a'
    assert receiver.collected[0]['audio_alignment'] == 'unplaced'
    assert fallback._value.get() == before + 1


async def test_single_conversation_gap_inside_horizon_fails_open(monkeypatch):
    receiver = _receiver(monkeypatch, v2=True)
    receiver.host.state.current_conversation_id = 'conv-now'
    state = receiver.host.state

    # A wall gap the session never accepted audio for, bracketed by one
    # conversation's runs, inside the retention horizon: fail open.
    state.conversation_sample_ranges = deque([(RATE * 10, RATE * 20, 'conv-a'), (RATE * 25, RATE * 30, 'conv-a')])
    assert receiver._owner_for_sample(RATE * 22) == 'conv-a'

    # The same single-conversation gap outside the retention horizon is
    # ambiguous: runs covering the sample were eligible for eviction.
    state.conversation_sample_ranges = deque([(RATE * 10, RATE * 20, 'conv-a'), (RATE * 200, RATE * 210, 'conv-a')])
    assert receiver._owner_for_sample(RATE * 50) is None

    # A boundary inside the retained window never fails open.
    state.conversation_sample_ranges = deque([(RATE * 10, RATE * 20, 'conv-a'), (RATE * 25, RATE * 30, 'conv-b')])
    assert receiver._owner_for_sample(RATE * 22) is None


# ---------------------------------------------------------------------------
# N5: the loop hop copies the segment list and counts deferred failures
# ---------------------------------------------------------------------------
class _CaptureLoop:
    """Stand-in for the listen loop: records deferred callbacks for manual run."""

    def __init__(self):
        self.callbacks = []

    def call_soon_threadsafe(self, callback, *args):
        self.callbacks.append((callback, args))


class _ClosedLoop:
    def call_soon_threadsafe(self, callback, *args):
        raise RuntimeError('Event loop is closed')


def test_deferred_callback_runs_on_its_own_segment_list(monkeypatch):
    receiver = _receiver(monkeypatch, v2=True)
    loop = _CaptureLoop()
    receiver._listen_loop = loop
    seen = []
    segments = [{'id': 's1'}, {'id': 's2'}]

    receiver._run_on_listen_loop(seen.extend, segments)
    segments.clear()  # a provider may reuse its buffer once the callback returns
    assert seen == [], 'nothing runs until the listen loop does'
    callback, args = loop.callbacks[0]
    callback(*args)
    assert seen == [{'id': 's1'}, {'id': 's2'}], 'the hop must carry its own copy of the list'


@pytest.mark.parametrize('v2,mode', [(True, 'v2'), (False, 'legacy')])
def test_deferred_callback_exception_counts_batch_event(monkeypatch, caplog, v2, mode):
    receiver = _receiver(monkeypatch, v2=v2)
    loop = _CaptureLoop()
    receiver._listen_loop = loop

    def boom(segments):
        raise ValueError('provider callback exploded')

    rejected = OMI_AUDIO_TIMELINE_SEGMENTS_TOTAL.labels(mode=mode, outcome='rejected')
    reason = OMI_AUDIO_TIMELINE_CALLBACK_ERRORS_TOTAL.labels(mode=mode, provider='unknown')
    before = rejected._value.get()
    reason_before = reason._value.get()
    with caplog.at_level(logging.WARNING, logger='routers.listen.receiver'):
        receiver._run_on_listen_loop(boom, [{'id': 's1', 'text': 'late text', 'start': 0, 'end': 1}])
        callback, args = loop.callbacks[0]
        callback(*args)  # must not raise out of the deferred action
    assert rejected._value.get() == before
    assert reason._value.get() == reason_before + 1
    assert [segment['text'] for segment in receiver.collected] == (['late text'] if v2 else [])
    assert any('Listen STT callback failed' in record.message for record in caplog.records)
    # The bounded log never carries segment content or identity.
    assert 's1' not in caplog.text


def test_closed_loop_hands_off_callback_instead_of_dropping(monkeypatch, caplog):
    receiver = _receiver(monkeypatch, v2=True)
    receiver._listen_loop = _ClosedLoop()
    ran = []

    with caplog.at_level(logging.WARNING, logger='routers.listen.receiver'):
        receiver._run_on_listen_loop(ran.append, [{'id': 's1'}])  # must not raise

    assert ran == [[{'id': 's1'}]]


def test_closed_loop_persists_late_callback_batch(monkeypatch):
    receiver = _receiver(monkeypatch, v2=True)
    receiver._listen_loop = _ClosedLoop()
    saved = []
    buffer = deque()

    async def persist(segments, photos, diarized):
        saved.extend(segments)

    receiver.host.transcripts = SimpleNamespace(segment_buffer=buffer, _process_v2_batches=persist)
    receiver._run_on_listen_loop(buffer.extend, [{'id': 'late', 'text': 'late text', 'start': T0, 'end': T0}])
    assert [segment['text'] for segment in saved] == ['late text']
    assert not buffer
