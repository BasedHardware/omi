"""Round-3 adversarial-review regressions for the audio-timeline branch.

Locks the wiring the round-1/2 tests missed:

- P0-2: with the capture clock on and v2 persistence OFF, the non-passthrough
  callback still applies the active VAD gate's ``remap_segments`` to provider
  timestamps before anything is buffered, and the epoch translation only
  attaches the capture window (never rewriting start/end) — so flag-off
  stored/emitted times are exactly what origin/main's
  ``make_stream_callback`` produced.
- P1-3: ownership ranges coalesce into runs, so a final arriving 30 s after
  its audio still resolves its owner instead of being dropped by a frame-count
  cap.
- P1-6: a resumed v1 row adopts its persisted ``started_at`` (datetime or ISO
  string) as a non-pinnable origin: offsets project against it and the v2
  marker is never written; an unparseable started_at locks the row legacy
  instead of falling through to a fresh pin.
- P1-7: a v2 drain carrying only photos (or late segments for a previous
  owner plus current photos) still writes the current conversation's photos.
- P2-11: after anchor compaction, strict wall projection refuses samples in
  evicted intervals and the epoch translator rejects such segments.
- P2-12: a callback invoked from a provider SDK thread hops onto the listen
  loop before touching timeline state.
"""

import asyncio
import threading
from collections import deque
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional

import pytest

import routers.listen.receiver as receiver_module
from database import conversations as conversations_db
from routers.listen.contracts import ListenSessionState
from routers.listen.receiver import ListenReceiver
from routers.listen.transcripts import ConversationCache, TranscriptProcessor
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.audio_timeline import CaptureTimeline, ProviderEpochTranslator
from utils.stt.speaker_identity import ConversationSpeakerIdAllocator

RATE = 16000
UID = 'uid-r3'
T0 = 1_700_000_000.0


@pytest.fixture
def anyio_backend():
    return 'asyncio'


class _ShiftGate:
    """Deterministic stand-in for an active VADStreamingGate mapper.

    Mirrors what ``WallTimeMapper.dg_to_wall_rel`` does after the gate skipped
    40 s of silence: provider audio-time t maps to wall-relative t + 40.
    """

    mode = 'active'

    def remap_segments(self, segments):
        for segment in segments:
            segment['start'] = segment['start'] + 40.0
            segment['end'] = segment['end'] + 40.0


def _receiver(monkeypatch, *, v2: bool, gate=None, conversation='conv-r3') -> ListenReceiver:
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
    receiver.vad_gate = gate
    receiver.collected = collected
    return receiver


def _feed_contiguous(receiver: ListenReceiver, seconds: float, *, first_wall: float = T0, frame=0.1):
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


# ---------------------------------------------------------------------------
# P0-2: clock-only callbacks keep the VAD remap for persisted/emitted times
# ---------------------------------------------------------------------------
async def test_clock_only_non_passthrough_remaps_like_origin_main(monkeypatch):
    receiver = _receiver(monkeypatch, v2=False, gate=_ShiftGate())
    first_sample, last_sample = _feed_contiguous(receiver, 3.0)
    callback, _modulate, epoch = receiver._build_stt_callbacks()
    epoch.note_accepted(first_sample, last_sample - first_sample)

    callback([{'id': 's1', 'speaker_id': 0, 'start': 2.0, 'end': 3.0, 'text': 'hello', 'is_user': False}])
    # Wait — no loop hop pending: invoked from the running test loop.
    assert len(receiver.collected) == 1
    segment = receiver.collected[0]
    # Persisted/emitted times are the REMAPPED ones — exactly what
    # make_stream_callback would have produced on origin/main.
    assert segment['start'] == pytest.approx(42.0)
    assert segment['end'] == pytest.approx(43.0)
    # The capture window is attached from the provider timestamps via the
    # accepted send spans, and is NOT the remapped axis.
    assert segment['_capture_abs_start'] == pytest.approx(receiver.capture_timeline.wall(2 * RATE), abs=1e-6)
    assert segment['_capture_abs_end'] == pytest.approx(receiver.capture_timeline.wall(3 * RATE), abs=1e-6)


async def test_clock_only_passthrough_keeps_provider_times(monkeypatch):
    receiver = _receiver(monkeypatch, v2=False, gate=_ShiftGate())
    first_sample, last_sample = _feed_contiguous(receiver, 3.0)
    _callback, modulate_callback, epoch = receiver._build_stt_callbacks()
    epoch.note_accepted(first_sample, last_sample - first_sample)

    modulate_callback([{'id': 's1', 'speaker_id': 0, 'start': 2.0, 'end': 3.0, 'text': 'hello', 'is_user': False}])
    segment = receiver.collected[0]
    # Passthrough providers never had a remap on origin/main; keep that.
    assert segment['start'] == pytest.approx(2.0)
    assert segment['end'] == pytest.approx(3.0)
    assert '_capture_abs_start' in segment


async def test_v2_callback_projects_times_and_skips_gate_mapper(monkeypatch):
    receiver = _receiver(monkeypatch, v2=True, gate=_ShiftGate())
    first_sample, last_sample = _feed_contiguous(receiver, 3.0)
    callback, _modulate, epoch = receiver._build_stt_callbacks()
    epoch.note_accepted(first_sample, last_sample - first_sample)

    callback([{'id': 's1', 'speaker_id': 0, 'start': 2.0, 'end': 3.0, 'text': 'hello', 'is_user': False}])
    assert len(receiver.collected) == 1
    segment = receiver.collected[0]
    projected_start = receiver.capture_timeline.wall(2 * RATE)
    # v2: the send-map translation replaces the gate mapper — never both.
    assert segment['start'] == pytest.approx(projected_start)
    assert segment['end'] == pytest.approx(receiver.capture_timeline.wall(3 * RATE))
    assert segment['_conversation_id'] == receiver.host.state.current_conversation_id


async def test_clock_only_unmappable_segment_keeps_transcript(monkeypatch):
    receiver = _receiver(monkeypatch, v2=False, gate=_ShiftGate())
    _feed_contiguous(receiver, 3.0)
    callback, _modulate, _epoch = receiver._build_stt_callbacks()

    # Provider timestamps beyond every accepted send (a hallucination): with
    # the flag off the transcript must survive with legacy times, window-less.
    callback([{'id': 's1', 'speaker_id': 0, 'start': 99.0, 'end': 100.0, 'text': 'ghost', 'is_user': False}])
    segment = receiver.collected[0]
    assert segment['start'] == pytest.approx(139.0)  # remapped like origin/main
    assert '_capture_abs_start' not in segment


# ---------------------------------------------------------------------------
# P2-12: provider SDK threads hop onto the listen loop
# ---------------------------------------------------------------------------
async def test_callback_from_sdk_thread_runs_on_listen_loop(monkeypatch):
    receiver = _receiver(monkeypatch, v2=False, gate=None)
    _feed_contiguous(receiver, 1.0)
    callback, _modulate, epoch = receiver._build_stt_callbacks()
    seen_threads = []
    receiver.host.transcripts.enqueue = lambda segments: seen_threads.append(threading.get_ident())
    first_sample, last_sample = 0, RATE
    epoch.note_accepted(first_sample, last_sample - first_sample)

    loop_thread = threading.get_ident()
    worker = threading.Thread(
        target=callback,
        args=([{'id': 's1', 'speaker_id': 0, 'start': 0.0, 'end': 1.0, 'text': 'x', 'is_user': False}],),
    )
    worker.start()
    for _ in range(100):
        await asyncio.sleep(0.01)
        if seen_threads:
            break
    worker.join(timeout=5)
    assert seen_threads, 'the deferred callback never ran'
    assert seen_threads[0] == loop_thread, 'an off-loop callback mutated listen state directly'


# ---------------------------------------------------------------------------
# P1-3: ownership runs are coalesced; a 30 s-late final keeps its owner
# ---------------------------------------------------------------------------
async def test_late_final_resolves_owner_after_thirty_seconds(monkeypatch):
    receiver = _receiver(monkeypatch, v2=True)
    first, _ = _feed_contiguous(receiver, 30.0)  # conversation A: samples 0..30s
    receiver.host.state.current_conversation_id = 'conv-b'
    b_first, _ = _feed_contiguous(receiver, 5.0, first_wall=T0 + 30.0)

    # One run per conversation, not one per frame (300+ frames fed above).
    ranges = receiver.host.state.conversation_sample_ranges
    assert len(ranges) == 2, f'ranges must coalesce into runs, got {len(ranges)}'

    # A final for audio that started 30 s ago still resolves conv A.
    _callback, _modulate, epoch = receiver._build_stt_callbacks()
    receiver.collected.clear()
    receiver._enqueue_translated_segments(
        [
            {
                'id': 'late',
                'speaker_id': 0,
                'start': receiver.capture_timeline.wall(first + RATE),
                'end': receiver.capture_timeline.wall(first + 2 * RATE),
                'text': 'late final',
                'is_user': False,
                '_capture_start_sample': first + RATE,
                '_capture_end_sample': first + 2 * RATE,
            }
        ]
    )
    assert len(receiver.collected) == 1
    assert receiver.collected[0]['_conversation_id'] == 'conv-r3'

    # A segment straddling the A→B boundary is still dropped (fail closed).
    receiver.collected.clear()
    receiver._enqueue_translated_segments(
        [
            {
                'id': 'straddle',
                'speaker_id': 0,
                'start': 0.0,
                'end': 0.0,
                'text': 'straddle',
                'is_user': False,
                '_capture_start_sample': first,
                '_capture_end_sample': b_first + RATE,
            }
        ]
    )
    assert receiver.collected == []


# ---------------------------------------------------------------------------
# P2-11: anchor compaction fails closed for evicted intervals
# ---------------------------------------------------------------------------
def test_wall_strict_refuses_evicted_intervals():
    import utils.audio_timeline as at

    timeline = CaptureTimeline(sample_rate=RATE)
    # One frame per forced 3 s arrival gap: each mints an anchor.
    pcm = b'\x01\x00' * RATE  # 1 s of audio per accept
    sample = 0
    wall = 1000.0
    for _i in range(at.MAX_ANCHORS + 2):
        _start, end, _ = timeline.accept(pcm, wall + 1.0, wall + 1.0)
        sample = end
        wall += 4.0  # 3 s gap after 1 s of audio
    assert timeline.compacted_below_sample is not None
    # Recent samples still project.
    assert timeline.wall_strict(sample - RATE) is not None
    # A sample inside an evicted interval refuses instead of extrapolating.
    assert timeline.wall_strict(int(timeline.compacted_below_sample * 0.5)) is None
    # Non-strict keeps the historical best-effort projection.
    assert timeline.wall(int(timeline.compacted_below_sample * 0.5)) > 0


def test_translator_rejects_evicted_interval_segments():
    timeline = CaptureTimeline(sample_rate=RATE)
    pcm = b'\x01\x00' * RATE
    wall = 1000.0
    accepted = []
    for _i in range(70):
        start, end, _ = timeline.accept(pcm, wall + 1.0, wall + 1.0)
        accepted.append((start, end))
        wall += 4.0
    old_start, old_end = accepted[0]
    translator = ProviderEpochTranslator(timeline, RATE)
    translator.note_accepted(old_start, old_end - old_start)
    assert timeline.compacted_below_sample is not None and timeline.compacted_below_sample > old_start

    out = translator.translate([{'id': 'old', 'start': 0.0, 'end': 1.0, 'text': 'x'}])
    assert [segment['text'] for segment in out] == ['x']
    assert out[0]['audio_alignment'] == 'unplaced'
    assert out[0]['start'] == out[0]['end'] == timeline.wall(timeline.next_sample)
    assert translator.rejected_segments == 1


# ---------------------------------------------------------------------------
# P1-6 / P1-7 / P2-13: v2 batch persistence semantics
# ---------------------------------------------------------------------------
def _seed_row(store, cid, *, started_at, segments=(), status='in_progress'):
    row = {
        'id': cid,
        'status': status,
        'created_at': datetime.fromtimestamp(T0 - 120, tz=timezone.utc),
        'started_at': started_at,
        'finished_at': datetime.fromtimestamp(T0 - 120, tz=timezone.utc),
        'structured': {},
        'transcript_segments': list(segments),
    }
    store.rows[('users', UID, 'conversations', cid)] = row
    return row


def _processor(monkeypatch, store, *, current: Optional[str], photos_sink=None):
    monkeypatch.setattr(conversations_db, 'get_firestore_client', lambda: store)

    def _row(cid):
        return store.rows.get(('users', UID, 'conversations', cid)) or {}

    class _Persistence:
        @staticmethod
        async def call(fn, *args, **kwargs):
            if fn is conversations_db.update_conversation_segments:
                return fn(*args, **kwargs)
            if fn is conversations_db.update_conversation_finished_at:
                _uid, cid, finished = args
                _row(cid)['finished_at'] = finished
                return True
            if fn is conversations_db.store_conversation_photos:
                _uid, cid, photos = args
                if photos_sink is not None:
                    photos_sink.extend(photos)
                _row(cid).setdefault('photos', []).extend(p.model_dump() for p in photos)
                return True
            if fn is conversations_db.update_conversation:
                _uid, cid, patch = args
                _row(cid).update(patch)
                return True
            if fn is conversations_db.get_conversation:
                return dict(_row(args[1]))
            raise AssertionError(f'unexpected persistence call: {fn}')

    async def loader(cid):
        return dict(_row(cid))

    websocket_sent = []

    async def send_json(payload):
        websocket_sent.append(payload)

    state = ListenSessionState()
    state.current_conversation_id = current
    state.first_audio_byte_timestamp = T0
    state.speaker_id_enabled = False
    host = SimpleNamespace(
        request=SimpleNamespace(uid=UID, websocket=SimpleNamespace(send_json=send_json), codec='pcm16'),
        state=state,
        persistence=_Persistence(),
        speakers=SimpleNamespace(
            segment_assignments={},
            speaker_to_person={},
            segment_identity_status={},
            person_embeddings={},
            queue=None,
        ),
        conversations=SimpleNamespace(create_new_in_progress_conversation=_async_noop),
        onboarding_handler=None,
        transcript_send=None,
        pusher_enabled=True,
        user_has_credits=True,
        client_kind='test',
        language='en',
        send_event=lambda event: None,
        emit_speaker_suggestion=lambda *a, **k: None,
        complete_live_transcription=lambda: None,
    )
    processor = object.__new__(TranscriptProcessor)
    processor.host = host
    processor.cache = ConversationCache(loader)
    processor.segment_buffer = deque()
    processor.current_session_segments = {}
    processor.suggested_segments = set()
    processor.speaker_id_allocator = ConversationSpeakerIdAllocator()
    processor.translation_coordinator = None
    processor.translation_language = None
    return processor, websocket_sent


async def _async_noop(*args, **kwargs):
    return None


def _v2_segment(segment_id, start, end, owner, text='hello'):
    return {
        'id': segment_id,
        'speaker': 'SPEAKER_00',
        'speaker_id': 0,
        'start': start,
        'end': end,
        'text': text,
        'is_user': False,
        'person_id': None,
        '_conversation_id': owner,
    }


async def test_resumed_v1_row_is_never_marked_v2(monkeypatch):
    from routers.listen.contracts import ConversationCaptureOrigin

    store = StrictFirestore()
    resumed_started = datetime.fromtimestamp(T0 - 60, tz=timezone.utc)
    _seed_row(store, 'conv-resumed', started_at=resumed_started)
    processor, _sent = _processor(monkeypatch, store, current='conv-resumed')
    # A resumed row: adopted origin, not pinnable.
    processor.host.state.conversation_capture_origins['conv-resumed'] = ConversationCaptureOrigin(
        resumed_started.timestamp(), pinnable=False
    )

    await processor._process_v2_batches([_v2_segment('s1', T0 - 60 + 10.0, T0 - 60 + 12.0, 'conv-resumed')], [], {})

    row = store.rows[('users', UID, 'conversations', 'conv-resumed')]
    assert 'audio_timeline' not in row, 'a resumed v1 row must never gain the v2 marker'
    assert row['started_at'] == resumed_started, 'the adopted origin must not move'
    segments = conversations_db._decode_transcript_segments_strict(
        UID, row.get('transcript_segments', []), bool(row.get('transcript_segments_compressed'))
    )
    assert segments and abs(segments[0]['start'] - 10.0) < 0.05, 'offsets project against the adopted started_at'


async def test_resumed_row_with_string_started_at_adopts_it(monkeypatch):
    from routers.listen.contracts import ConversationCaptureOrigin
    from routers.listen.conversations import LiveConversationController

    # The controller's adopt path parses the ISO string instead of falling
    # through to a fresh pin.
    state = ListenSessionState()
    host = SimpleNamespace(state=state)
    host.state.capture_timeline = object()  # clock present
    controller = LiveConversationController(host)
    controller._adopt_capture_timeline('conv-str', '2023-11-14T22:13:20+00:00')
    origin = state.conversation_capture_origins['conv-str']
    assert origin.pinnable is False
    assert origin.wall == pytest.approx(datetime.fromisoformat('2023-11-14T22:13:20+00:00').timestamp())
    assert 'conv-str' not in state.conversations_awaiting_capture_origin

    # A garbage started_at locks the row legacy; it must NOT wait for a fresh pin.
    controller._adopt_capture_timeline('conv-junk', 'not-a-timestamp')
    assert 'conv-junk' in state.conversations_legacy_locked
    assert 'conv-junk' not in state.conversations_awaiting_capture_origin
    assert 'conv-junk' not in state.conversation_capture_origins

    # And the batch path keeps a legacy-locked row out of v2 persistence.
    store = StrictFirestore()
    _seed_row(store, 'conv-junk', started_at='not-a-timestamp')
    processor, _sent = _processor(monkeypatch, store, current='conv-junk')
    processor.host.state.conversations_legacy_locked.add('conv-junk')
    await processor._process_v2_batches([_v2_segment('s1', T0 + 1.0, T0 + 2.0, 'conv-junk')], [], {})
    row = store.rows[('users', UID, 'conversations', 'conv-junk')]
    assert 'audio_timeline' not in row
    segments = conversations_db._decode_transcript_segments_strict(
        UID, row.get('transcript_segments', []), bool(row.get('transcript_segments_compressed'))
    )
    assert segments, 'the transcript is kept on the legacy projection base'


async def test_photo_only_drain_writes_photos(monkeypatch):
    from models.conversation_photo import ConversationPhoto

    store = StrictFirestore()
    _seed_row(store, 'conv-photo', started_at=datetime.fromtimestamp(T0 - 5, tz=timezone.utc))
    photos_sink = []
    processor, _sent = _processor(monkeypatch, store, current='conv-photo', photos_sink=photos_sink)
    photo = ConversationPhoto(id='ph1', base64='ZmFrZQ==', description='a photo', discarded=False)

    # No segments at all: the photo must still land on the current row.
    await processor._process_v2_batches([], [photo], {})
    row = store.rows[('users', UID, 'conversations', 'conv-photo')]
    assert row.get('photos') and row['photos'][0]['id'] == 'ph1'
    assert 'audio_timeline' not in row, 'photos alone never pin the marker'


async def test_late_owner_drain_still_writes_current_photos(monkeypatch):
    from models.conversation_photo import ConversationPhoto
    from routers.listen.contracts import ConversationCaptureOrigin

    store = StrictFirestore()
    old_started = datetime.fromtimestamp(T0 - 200, tz=timezone.utc)
    _seed_row(store, 'conv-old', started_at=old_started)
    _seed_row(store, 'conv-cur', started_at=datetime.fromtimestamp(T0 - 5, tz=timezone.utc))
    processor, sent = _processor(monkeypatch, store, current='conv-cur', photos_sink=[])
    processor.host.state.conversation_capture_origins['conv-old'] = ConversationCaptureOrigin(
        old_started.timestamp(), pinnable=False
    )
    photo = ConversationPhoto(id='ph2', base64='ZmFrZQ==', description='another', discarded=False)

    # Only late segments for the previous owner, plus a photo for the current one.
    diarized: dict = {}
    await processor._process_v2_batches(
        [_v2_segment('late1', old_started.timestamp() + 1.0, old_started.timestamp() + 2.0, 'conv-old')],
        [photo],
        diarized,
    )
    old_row = store.rows[('users', UID, 'conversations', 'conv-old')]
    cur_row = store.rows[('users', UID, 'conversations', 'conv-cur')]
    old_segments = conversations_db._decode_transcript_segments_strict(
        UID, old_row.get('transcript_segments', []), bool(old_row.get('transcript_segments_compressed'))
    )
    assert old_segments, 'the late owner keeps its transcript'
    assert abs(old_segments[0]['start'] - 1.0) < 0.05
    assert cur_row.get('photos') and cur_row['photos'][0]['id'] == 'ph2'
    # Persist-only: nothing about the late owner is delivered on the client WS.
    assert sent == []
    # Diarization accounting covers the late owner too.
    assert diarized.get('conv-old') == {0}


async def test_fresh_v2_row_still_pins_marker(monkeypatch):
    from routers.listen.contracts import ConversationCaptureOrigin

    store = StrictFirestore()
    _seed_row(store, 'conv-fresh', started_at=datetime.fromtimestamp(T0 - 60, tz=timezone.utc))
    processor, _sent = _processor(monkeypatch, store, current='conv-fresh')
    processor.host.state.conversation_capture_origins['conv-fresh'] = ConversationCaptureOrigin(T0 + 1.0, pinnable=True)

    await processor._process_v2_batches([_v2_segment('s1', T0 + 1.0, T0 + 2.0, 'conv-fresh')], [], {})
    row = store.rows[('users', UID, 'conversations', 'conv-fresh')]
    assert row.get('audio_timeline') == {'version': 2}
    assert row['started_at'].timestamp() == pytest.approx(T0 + 1.0)
