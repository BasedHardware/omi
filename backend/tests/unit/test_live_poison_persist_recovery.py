"""Strictly rejected live rows must not strand retained speech on one generation."""

import asyncio
import sys
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from google.api_core.exceptions import InvalidArgument
from pydantic import ValidationError

from database import conversations as db
from models.conversation_enums import ConversationSource
from models.transcript_segment import TranscriptSegment
from routers.listen import conversations as controller_module, transcripts
from tests.unit.test_live_oversized_persist_recovery import _processor as _base_processor, _raw_segments, _run_until
from tests.unit.test_manual_speaker_assignments import world, read


def _processor(monkeypatch, *, segments, update, rollover):
    processor, state, clock = _base_processor(monkeypatch, segments=segments, update=update, rollover=rollover)

    async def escape():
        await rollover(rollover=True)

    processor.host.conversations.rollover_after_transcript_decode_failure = escape
    return processor, state, clock


def _nested_transcript_blob():
    depth = sys.getrecursionlimit() + 32
    return '[' * depth + '0' + ']' * depth


def test_null_transcript_row_merges_as_empty(world):
    store, path, _ = world
    store.rows[path]['transcript_segments'] = None
    fresh = _raw_segments(1)
    for raw in fresh:
        raw['is_user'] = False
    merged = db.update_conversation_segments('u', 'c', [], live_segments=fresh)
    assert merged.created_ids == {'segment-0'}
    assert read(world)['transcript_segments'] == merged.segments


@pytest.mark.parametrize('blob', [{}, {'corrupt': True}, False, 0, '', 'corrupt'])
def test_non_null_poison_still_fails_closed(world, blob):
    store, path, _ = world
    store.rows[path]['transcript_segments'] = blob
    before = deepcopy(store.rows)
    with pytest.raises(db.TranscriptSegmentsDecodeError):
        db.update_conversation_segments('u', 'c', [], live_segments=_raw_segments(1))
    assert store.rows == before


@pytest.mark.asyncio
async def test_transaction_commit_is_marked_before_post_commit_reply_fault(world, monkeypatch):
    store, path, _ = world
    store.rows[path]['transcript_segments'] = []

    async def persist(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    host = SimpleNamespace(
        request=SimpleNamespace(uid='u'),
        is_multi_channel=False,
        state=SimpleNamespace(speaker_map_dirty=False, source_position_map=None),
        persistence=SimpleNamespace(call=persist),
        speakers=SimpleNamespace(segment_assignments={}, speaker_to_person={}, segment_identity_status={}),
    )
    processor = object.__new__(transcripts.TranscriptProcessor)
    processor.host = host
    processor.cache = transcripts.ConversationCache(None)
    processor.cache.data = deepcopy(store.rows[path])
    processor._legacy_segments_committed = False
    monkeypatch.setattr(transcripts, 'late_audio_intake_enabled', lambda: False)
    monkeypatch.setattr(transcripts, 'publish_committed', AsyncMock(side_effect=ValueError('synthetic reply fault')))
    raw = dict(_raw_segments(1)[0], is_user=False)
    with pytest.raises(ValueError, match='synthetic reply fault'):
        await processor._update_live_conversation(
            SimpleNamespace(id='c', transcript_segments=[]),
            [TranscriptSegment(**raw)],
            [],
            datetime.now(timezone.utc),
            None,
        )
    assert processor._legacy_segments_committed is True
    assert [s['id'] for s in read(world)['transcript_segments']] == [raw['id']]


@pytest.mark.asyncio
@pytest.mark.parametrize('probe_fault', ['none', 'raise', 'noop'])
async def test_dict_poison_rolls_over_and_commits_entire_drain_once(world, monkeypatch, probe_fault):
    store, old_path, _ = world
    store.rows[old_path]['transcript_segments'] = {'corrupt': True}
    fresh_path = (*old_path[:-1], 'fresh')
    original = deepcopy(store.rows[old_path])
    attempts, probes, commits = [], [], []
    retained = _raw_segments(8)  # Above the oversized shrink floor: lose no tail.

    async def update(_conversation, segments, _photos, _finished, _started):
        owner = state.current_conversation_id
        attempts.append(owner)
        incoming = [dict(id=s.id, text=s.text, start=s.start, end=s.end, is_user=False) for s in segments]
        merged = db.update_conversation_segments('u', owner, [], live_segments=incoming)
        commits.append((owner, [s.id for s in segments]))
        return SimpleNamespace(id=owner), [], []

    async def rollover(**kwargs):
        assert kwargs == {'rollover': True}
        probes.append((len(attempts), clock[0]))
        assert list(processor.segment_buffer) == retained
        if len(probes) == 1 and probe_fault == 'raise':
            raise RuntimeError('synthetic unavailable')
        if len(probes) == 1 and probe_fault == 'noop':
            return
        store.rows[fresh_path] = dict(id='fresh', status='in_progress', transcript_segments=[])
        state.current_conversation_id = 'fresh'

    processor, state, clock = _processor(monkeypatch, segments=deepcopy(retained), update=update, rollover=rollover)
    state.current_conversation_id = 'c'
    processor._oversized_rollover_probe_at = 0.0
    await _run_until(processor, clock, lambda: bool(commits), max_ticks=250)
    assert probes[0][0] == transcripts.LEGACY_VALUE_ERROR_ROLLOVER_FAILURES
    if probe_fault != 'none':
        assert len(probes) == 2
        assert probes[1][1] - probes[0][1] >= transcripts.OVERSIZED_ROLLOVER_PROBE_SECONDS
    assert commits == [('fresh', [raw['id'] for raw in retained])]
    assert not processor.segment_buffer
    assert store.rows[old_path] == original
    saved = read((store, fresh_path, []))['transcript_segments']
    # The production merge may absorb adjacent same-speaker IDs; every word
    # must still appear exactly once, exclusively on the fresh generation.
    assert ' '.join(raw['text'] for raw in saved) == ' '.join(raw['text'] for raw in retained)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'boundary', ['conversation', 'conversation_at_threshold', 'transient', 'post_commit', 'success', 'late_reply']
)
async def test_value_error_debt_does_not_cross_boundaries(monkeypatch, boundary):
    attempts = []

    async def update(*args):
        attempts.append(state.current_conversation_id)
        if len(attempts) == (5 if boundary == 'conversation_at_threshold' else 4):
            if boundary in {'conversation', 'conversation_at_threshold'}:
                state.current_conversation_id = 'other'
            elif boundary == 'transient':
                raise RuntimeError('synthetic transient')
            elif boundary == 'post_commit':
                processor._legacy_segments_committed = True
            else:
                processor.segment_buffer.extend(_raw_segments(2))
                if boundary == 'late_reply':
                    raise transcripts.LateTranscriptReplyError()
                return SimpleNamespace(id=state.current_conversation_id), [], []
        raise db.TranscriptSegmentsDecodeError('undecodable transcript_segments: dict')

    rollover = AsyncMock()
    processor, state, clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = 0.0
    await _run_until(processor, clock, lambda: len(attempts) >= (4 if boundary == 'post_commit' else 7))
    rollover.assert_not_awaited()
    assert len(processor.segment_buffer) == (0 if boundary == 'post_commit' else 2)


@pytest.mark.asyncio
async def test_cancelled_rollover_keeps_entire_pristine_drain(monkeypatch):
    async def update(*args):
        raise db.TranscriptSegmentsDecodeError('undecodable transcript_segments: dict')

    rollover = AsyncMock(side_effect=asyncio.CancelledError())
    retained = _raw_segments(8)
    processor, _, clock = _processor(monkeypatch, segments=deepcopy(retained), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = 0.0
    await _run_until(processor, clock, lambda: rollover.await_count > 0)
    assert list(processor.segment_buffer) == retained


@pytest.mark.parametrize(
    'blob,compressed', [('not-json', False), ('not-hex', True), (b'not-zlib', True), ('{}', False)]
)
def test_decoder_encoding_failures_have_specific_type(monkeypatch, blob, compressed):
    monkeypatch.setattr(db.encryption, 'decrypt', lambda value, _owner: value)
    with pytest.raises(db.TranscriptSegmentsDecodeError, match='undecodable transcript_segments'):
        db._decode_transcript_segments_blob('synthetic', blob, compressed)


@pytest.mark.asyncio
@pytest.mark.parametrize('source', ['receipt', 'absorption', 'validation', 'lookalike'])
async def test_unrelated_value_errors_never_split_conversation(monkeypatch, source):
    failures = {
        'receipt': ValueError('undecodable json blob: synthetic'),
        'absorption': ValueError('Cyclic transcript segment absorption'),
        'lookalike': ValueError('undecodable transcript_segments: unrelated validator'),
        'validation': ValidationError.from_exception_data(
            'Synthetic',
            [{'type': 'value_error', 'loc': ('field',), 'input': None, 'ctx': {'error': ValueError('invalid')}}],
        ),
    }
    attempts = []

    async def update(*args):
        attempts.append(True)
        raise failures[source]

    rollover = AsyncMock()
    processor, _, clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=rollover)
    processor._oversized_rollover_probe_at = 0.0
    await _run_until(processor, clock, lambda: len(attempts) == 8)
    assert len(attempts) == 8
    rollover.assert_not_awaited()
    assert len(processor.segment_buffer) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('blob_kind', ['dict', 'nested'])
@pytest.mark.parametrize('multi_channel', [False, True])
async def test_real_controller_finalizes_displaced_row_without_blocking_speech(
    world, monkeypatch, multi_channel, blob_kind
):
    store, old_path, _ = world
    store.rows[old_path]['transcript_segments'] = (
        {'corrupt': True} if blob_kind == 'dict' else _nested_transcript_blob()
    )
    monkeypatch.setattr(db.encryption, 'decrypt', lambda value, _owner: value)
    finalization_entered, release_finalization = asyncio.Event(), asyncio.Event()
    committed, dispatched, tasks = [], [], []
    real_start = controller_module.start_background_task

    def track(coro, *, name):
        task = real_start(coro, name=name)
        tasks.append(task)
        return task

    async def persist(fn, *args, **kwargs):
        name = fn.__name__
        if name == 'open_live_recording_session':
            return dict(
                conversation_id=args[2],
                requires_rollover=False,
                lifecycle_version=1,
                lifecycle_phase='in_progress',
                lifecycle_sequence=0,
            )
        if name == 'create_in_progress_conversation':
            store.rows[(*old_path[:-1], args[1]['id'])] = deepcopy(args[1])
            return True
        if name == 'get_conversation':
            return deepcopy(store.rows.get((*old_path[:-1], args[1])))
        if name == 'request_finalization':
            assert args[1] == 'c'
            finalization_entered.set()
            await release_finalization.wait()
            store.rows[old_path]['status'] = 'processing'
            return dict(route='pusher', job_id='synthetic-job', dispatch_generation=1)
        if name == 'get_meetings_in_time_range':
            return []
        if name in {'arm', 'set_in_progress_conversation_id', 'record_recording_session_event'}:
            return None
        raise AssertionError(f'unexpected persistence operation: {name}')

    async def update(_conversation, segments, _photos, _finished, _started):
        owner = state.current_conversation_id
        incoming = [dict(id=s.id, text=s.text, start=s.start, end=s.end, is_user=False) for s in segments]
        db.update_conversation_segments('u', owner, [], live_segments=incoming)
        committed.append(owner)
        return SimpleNamespace(id=owner), [], []

    async def dispatch(owner, *_args):
        dispatched.append(owner)

    processor, state, clock = _processor(monkeypatch, segments=_raw_segments(2), update=update, rollover=AsyncMock())
    host = processor.host
    state.current_conversation_id = 'c'
    host.is_multi_channel = multi_channel
    host.request = SimpleNamespace(
        uid='u',
        source='phone_call' if multi_channel else 'omi',
        conversation_role='ambient',
        call_id=None,
        geolocation=None,
    )
    host.client_device_context = SimpleNamespace(client_device_id='synthetic-device', platform='desktop')
    host.client_conversation_id = None
    host.recording_session_id = 'synthetic-recording'
    host.recording_session_ids_by_conversation = {'c': 'synthetic-recording'}
    host.language = 'en'
    host.private_cloud_sync_enabled = False
    host.use_custom_stt = True
    host.client_kind = 'unknown'
    host.conversation_creation_timeout = 120
    host.persistence = SimpleNamespace(call=persist)
    host.request_conversation_processing = dispatch
    host.speakers.refresh_for_conversation = AsyncMock()
    host.spawn = track
    host.conversations = controller_module.LiveConversationController(host)
    monkeypatch.setattr(controller_module, 'start_background_task', track)
    monkeypatch.setattr(controller_module, 'get_byok_keys', lambda: None)
    processor._oversized_rollover_probe_at = 0.0
    try:
        await _run_until(processor, clock, lambda: bool(committed) and finalization_entered.is_set())
        assert committed == [state.current_conversation_id]
        assert committed[0] != 'c'
        assert store.rows[old_path].get('status') != 'processing'
        assert tasks and not tasks[0].done()
        # The transcript task has already ended. Its displaced-row finalization
        # must still finish through the normal pusher handoff after teardown.
        state.active = False
        release_finalization.set()
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=2)
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=2)
        assert dispatched == ['c']
        assert store.rows[old_path]['status'] == 'processing'
    finally:
        release_finalization.set()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('photo_fault', ['false', 'raise', 'permanent'])
async def test_committed_speech_is_not_replayed_after_photo_failure(world, monkeypatch, photo_fault):
    store, path, _ = world
    store.rows[path]['transcript_segments'] = []
    writes, photo_attempts = [], []
    rollover = AsyncMock()
    real_update = transcripts.TranscriptProcessor._update_live_conversation

    async def persist(fn, *args, **kwargs):
        if fn is db.store_conversation_photos:
            photo_attempts.append(True)
            if len(photo_attempts) == 1:
                if photo_fault == 'raise':
                    raise ValueError('synthetic photo failure')
                if photo_fault == 'permanent':
                    raise InvalidArgument('document exceeds the maximum allowed size')
                return False
            return True
        if fn is db.update_conversation_finished_at:
            return True
        result = fn(*args, **kwargs)
        writes.append(True)
        return result

    async def update(_conversation, segments, photos, finished, started):
        return await real_update(
            processor,
            SimpleNamespace(id='c', transcript_segments=[], source=ConversationSource.openglass),
            [TranscriptSegment(id=s.id, text=s.text, start=s.start, end=s.end, is_user=False) for s in segments],
            photos,
            finished,
            started,
        )

    processor, state, clock = _processor(
        monkeypatch, segments=[dict(raw, is_user=False) for raw in _raw_segments(2)], update=update, rollover=rollover
    )
    monkeypatch.setattr(transcripts, 'TranscriptSegment', TranscriptSegment)
    state.current_conversation_id = 'c'
    state.speaker_map_dirty = False
    state.source_position_map = None
    processor.host.is_multi_channel = False
    processor.host.request.uid = 'u'
    processor._oversized_rollover_probe_at = 0.0
    processor.host.persistence = SimpleNamespace(call=persist)
    processor.host.speakers.segment_assignments = {}
    processor.host.speakers.speaker_to_person = {}
    processor.host.speakers.segment_identity_status = {}
    processor.cache = transcripts.ConversationCache(None, monotonic=lambda: clock[0])
    processor.cache.data = deepcopy(store.rows[path])
    processor.cache.conversation_id = 'c'
    processor.cache.loaded_at = clock[0]
    processor.photo_buffer.append(SimpleNamespace(id='synthetic-photo'))
    monkeypatch.setattr(transcripts, 'late_audio_intake_enabled', lambda: False)
    monkeypatch.setattr(transcripts, 'publish_committed', AsyncMock())
    await _run_until(processor, clock, lambda: len(photo_attempts) == 2)
    assert len(writes) == 1
    rollover.assert_not_awaited()
    assert not processor.segment_buffer and not processor.photo_buffer
    assert ' '.join(s['text'] for s in read(world)['transcript_segments']) == 'word 0 word 1'


def test_nested_json_is_a_decoder_failure_and_remains_finalizable(monkeypatch):
    blob = _nested_transcript_blob()
    monkeypatch.setattr(db.encryption, 'decrypt', lambda value, _owner: value)
    with pytest.raises(db.TranscriptSegmentsDecodeError) as caught:
        db._decode_transcript_segments_blob('synthetic', blob, False)
    assert isinstance(caught.value.__cause__, RecursionError)
    # This is the lifecycle's real content predicate. It must admit recovery
    # without interpreting malformed data as empty or raising again.
    assert db.raw_conversation_has_content('synthetic', {'transcript_segments': blob})


@pytest.mark.parametrize(
    'prefix',
    [
        'undecodable transcript_segments',
        'undecodable json blob',
        'undecodable manual_speaker_assignments',
        'Cyclic transcript segment absorption',
    ],
)
def test_reason_logs_only_fixed_vocabulary(prefix):
    payload = 'SyntheticPrivatePayload@example.invalid/abcdefghijklmnopqrstuvwxyz12'
    assert transcripts._legacy_persist_reason(ValueError(f'{prefix}: {payload}')) == prefix
    assert transcripts._legacy_persist_reason(ValueError(payload)) == 'other'
    assert transcripts._legacy_persist_reason(ValueError(f'{payload}: {prefix}')) == 'other'
    assert len(transcripts._legacy_persist_reason(ValueError(prefix))) <= 60


@pytest.mark.asyncio
async def test_loop_error_log_contains_no_private_error_payload(monkeypatch, caplog):
    payload = 'SyntheticPrivatePayload@example.invalid/abcdefghijklmnopqrstuvwxyz12'

    async def update(*args):
        raise ValueError(f'undecodable transcript_segments: {payload}')

    processor, _, clock = _processor(monkeypatch, segments=_raw_segments(1), update=update, rollover=AsyncMock())
    await _run_until(processor, clock, lambda: bool(caplog.records))
    messages = [r.getMessage() for r in caplog.records if 'Live transcript persist failed' in r.getMessage()]
    assert messages
    assert all('reason=undecodable transcript_segments' in message and payload not in message for message in messages)
