import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from database import conversations as db
from models.transcript_segment import TranscriptSegment
from routers.listen import transcripts
from tests.unit.test_listen_speaker_id_failover import (
    CONV,
    FailoverStack,
    _frames_for,
    _owner,
    _provider_segment,
    _silence,
    _stall_frame,
    _wait_for,
)
from tests.unit.test_manual_speaker_assignments import read, world
from utils.conversations.merge_conversations import _merge_transcript_segments
from utils.conversations.smart_merge_policy import rebase_donor_segments
from utils.product_telemetry import set_product_telemetry_client_for_tests
from utils.speaker_assignment import process_speaker_assigned_segments

T0 = 1_700_000_000.0


@pytest.fixture
def telemetry():
    class _Client:
        def capture(self, **event):
            pass

    set_product_telemetry_client_for_tests(_Client())
    yield
    set_product_telemetry_client_for_tests(None)


async def _stop(stack):
    stack.state.active = False
    stack.state.shutdown_event.set()
    await stack.finish()
    for task in stack.tasks:
        task.cancel()
    await asyncio.gather(*stack.tasks, return_exceptions=True)
    stack.restore()


def speech_dict(sid, text, start, end, **extra):
    raw = dict(
        id=sid,
        speaker='SPEAKER_00',
        speaker_id=0,
        text=text,
        start=start,
        end=end,
        is_user=False,
        person_id=None,
    )
    raw.update(extra)
    return raw


async def test_known_window_persists_and_wire_stays_clean(monkeypatch, telemetry):
    stack = FailoverStack(monkeypatch, v2=False)
    loop_task = asyncio.create_task(stack.processor.process_loop())
    stack.tasks.append(loop_task)
    transcript_frames = []
    stack.host.transcript_send = transcript_frames.append
    try:
        await stack.host.speakers.refresh_for_conversation(CONV)
        assert await stack.receiver.initialize_stt()
        websocket = await stack.run_receive(_frames_for(_silence(2.0) + _owner(3.0)))
        stack.provider(0)['callback']([_provider_segment('seg-1', 2.0, 5.0, 'a known window line.')])

        (stored,) = await _wait_for(
            lambda: stack.decode_segments() or None, timeout=15.0, message='persisted segment', stack=stack
        )
        assert stored['audio_capture_start'] == pytest.approx(T0 + 2.0, abs=0.75)
        assert stored['audio_capture_end'] == pytest.approx(T0 + 5.0, abs=0.75)
        assert stored['start'] == pytest.approx(0.0, abs=0.01)
        assert stored['end'] == pytest.approx(3.0, abs=0.01)

        await _wait_for(
            lambda: transcript_frames and websocket.sent_json,
            timeout=15.0,
            message='delivered transcript',
            stack=stack,
        )
        assert any(any(item.get('id') == 'seg-1' for item in batch) for batch in transcript_frames), transcript_frames
        delivered = [item for batch in websocket.sent_json for item in batch if isinstance(batch, list)]
        assert any(item.get('id') == 'seg-1' for item in delivered), websocket.sent_json
        for item in delivered:
            assert 'audio_capture_start' not in item and 'audio_capture_end' not in item
        for frame in transcript_frames:
            for item in frame:
                assert 'audio_capture_start' not in item and 'audio_capture_end' not in item
    finally:
        await _stop(stack)


async def test_failover_epoch_stores_capture_absolute_not_provider_relative(monkeypatch, telemetry):
    stack = FailoverStack(monkeypatch, v2=False)
    loop_task = asyncio.create_task(stack.processor.process_loop())
    stack.tasks.append(loop_task)
    try:
        await stack.host.speakers.refresh_for_conversation(CONV)
        assert await stack.receiver.initialize_stt()
        await stack.run_receive(_frames_for(_silence(60.0) + _owner(3.0) + _silence(7.0)))
        stack.provider(0)['callback']([_provider_segment('seg-pre', 60.0, 63.0, 'before the failover')])
        await _wait_for(lambda: stack.decode_segments(), timeout=15.0, message='first segment', stack=stack)

        stack.provider(0)['inner'].mark_dead()
        assert await stack.receiver._failover_stt_socket()
        failover_index = len(stack.created_sockets) - 1
        await stack.run_receive(_frames_for(_owner(3.0)) + [_stall_frame(5.0)] + _frames_for(_silence(1.0)))
        stack.provider(failover_index)['callback'](
            [_provider_segment('seg-post', 0.0, 3.0, 'after the failover epoch restart')]
        )

        def _post_stored():
            return next((s for s in stack.decode_segments() if 'failover epoch restart' in s.get('text', '')), None)

        stored = await _wait_for(_post_stored, timeout=15.0, message='post-failover segment', stack=stack)
        assert stored['audio_capture_start'] == pytest.approx(T0 + 70.0, abs=1.5)
        assert T0 + 72.0 <= stored['audio_capture_end'] <= T0 + 79.0
        assert stored['audio_capture_start'] - stored['start'] > 60.0
    finally:
        await _stop(stack)


async def test_unknown_window_and_forged_names_store_nothing(monkeypatch, telemetry):
    stack = FailoverStack(monkeypatch, v2=False)
    loop_task = asyncio.create_task(stack.processor.process_loop())
    stack.tasks.append(loop_task)
    try:
        await stack.host.speakers.refresh_for_conversation(CONV)
        stack.request.websocket = stack.websocket
        stack.state.first_audio_byte_timestamp = T0
        forged = dict(
            id='seg-forged',
            text='forged names must be dropped.',
            speaker='SPEAKER_01',
            speaker_id=1,
            start=0.0,
            end=1.0,
            is_user=False,
            person_id=None,
            audio_capture_start=1.0,
            audio_capture_end=2.0,
        )
        proven = dict(
            id='seg-proven',
            text='real provenance wins.',
            speaker='SPEAKER_00',
            speaker_id=0,
            start=1.0,
            end=2.0,
            is_user=False,
            person_id=None,
            audio_capture_start=9.0,
            audio_capture_end=9.5,
            _capture_abs_start=T0 + 50.0,
            _capture_abs_end=T0 + 52.0,
        )
        stack.processor.enqueue([forged, proven])

        def _both_stored():
            return len(stack.decode_segments()) == 2

        await _wait_for(_both_stored, timeout=15.0, message='both segments persisted', stack=stack)
        stored = {s['id']: s for s in stack.decode_segments()}
        assert 'audio_capture_start' not in stored['seg-forged']
        assert 'audio_capture_end' not in stored['seg-forged']
        assert stored['seg-proven']['audio_capture_start'] == pytest.approx(T0 + 50.0)
        assert stored['seg-proven']['audio_capture_end'] == pytest.approx(T0 + 52.0)
    finally:
        await _stop(stack)


@pytest.mark.parametrize('protection_level', ['standard', 'enhanced'])
def test_fields_survive_update_conversation_segments_codecs(world, protection_level):
    store, path, _ = world
    store.rows[path]['data_protection_level'] = protection_level
    segments = [
        speech_dict('s0', 'first.', 0, 1, audio_capture_start=100.0, audio_capture_end=101.0),
        speech_dict('s1', 'second.', 1, 2),
    ]
    result = db.update_conversation_segments('u', 'c', segments)
    assert result is not None
    decoded = read(world)['transcript_segments']
    assert decoded[0]['audio_capture_start'] == 100.0 and decoded[0]['audio_capture_end'] == 101.0
    assert 'audio_capture_start' not in decoded[1]


def test_fields_survive_smart_merge_rebase_and_manual_merge():
    survivor = {'id': 's', 'started_at': datetime.fromtimestamp(T0, tz=timezone.utc)}
    donor = {'id': 'd', 'started_at': datetime.fromtimestamp(T0 + 3600, tz=timezone.utc)}
    survivor_segments = [speech_dict('a', 'first.', 0, 1, audio_capture_start=T0, audio_capture_end=T0 + 1)]
    donor_segments = [speech_dict('b', 'second.', 0, 1, audio_capture_start=T0 + 3600, audio_capture_end=T0 + 3601)]

    merged = rebase_donor_segments(survivor, survivor_segments, donor, donor_segments)
    by_id = {s['id']: s for s in merged}
    assert by_id['b']['start'] == pytest.approx(3600.0)
    assert (by_id['a']['audio_capture_start'], by_id['a']['audio_capture_end']) == (T0, T0 + 1)
    assert (by_id['b']['audio_capture_start'], by_id['b']['audio_capture_end']) == (T0 + 3600, T0 + 3601)

    convs = [
        dict(
            transcript_segments=survivor_segments,
            started_at=survivor['started_at'],
            finished_at=datetime.fromtimestamp(T0 + 60, tz=timezone.utc),
        ),
        dict(
            transcript_segments=donor_segments,
            started_at=donor['started_at'],
            finished_at=datetime.fromtimestamp(T0 + 3660, tz=timezone.utc),
        ),
    ]
    merged2 = _merge_transcript_segments(convs)
    by_id2 = {s['id']: s for s in merged2}
    assert by_id2['a']['audio_capture_start'] == T0
    assert by_id2['b']['audio_capture_start'] == T0 + 3600


def test_fields_survive_speaker_identity_overlay_and_model_reprocess():
    seg = TranscriptSegment(**speech_dict('s0', 'line.', 0, 1, audio_capture_start=100.0, audio_capture_end=101.0))
    seg.assign_resolved_speaker(3, 'cluster:7')
    assert (seg.audio_capture_start, seg.audio_capture_end) == (100.0, 101.0)
    assert 'audio_capture_start' in seg.model_dump()

    segments = [seg, TranscriptSegment(**speech_dict('s1', 'other.', 1, 2, speaker_id=1))]
    process_speaker_assigned_segments(segments, {'s1': 'person-x'}, {3: ('person-y', 'Y')})
    assert segments[0].person_id == 'person-y'
    assert segments[0].audio_capture_start == 100.0
    assert 'audio_capture_start' not in segments[1].model_dump()

    reprocessed = [s.model_dump() for s in segments]
    assert reprocessed[0]['audio_capture_end'] == 101.0
    assert 'audio_capture_start' not in reprocessed[1]


async def test_fresh_write_rotation_keeps_capture_fields(world, monkeypatch):
    store, path, _ = world
    store.rows[path]['transcript_segments'] = []

    async def persist(fn, *args, **kwargs):
        if fn is db.update_conversation_segments:
            return fn(*args, **kwargs)
        return True

    async def load(_conversation_id):
        return deepcopy(store.rows[path])

    monkeypatch.setattr(
        transcripts,
        'deserialize_conversation',
        lambda _data: SimpleNamespace(id='c', transcript_segments=[]),
    )
    host = SimpleNamespace(
        request=SimpleNamespace(uid='u'),
        state=SimpleNamespace(speaker_map_dirty=False, current_conversation_id='c'),
        persistence=SimpleNamespace(call=persist),
        speakers=SimpleNamespace(segment_assignments={}, speaker_to_person={}, segment_identity_status={}),
    )
    processor = object.__new__(transcripts.TranscriptProcessor)
    processor.host = host
    processor.cache = transcripts.ConversationCache(load)
    fresh = TranscriptSegment(
        **speech_dict('n0', 'rotated line.', 0, 1, audio_capture_start=100.0, audio_capture_end=101.0)
    )
    result = await processor._write_fresh([fresh], [], datetime.now(timezone.utc), None)
    assert result is not None
    stored = read(world)['transcript_segments']
    assert stored[0]['audio_capture_start'] == 100.0 and stored[0]['audio_capture_end'] == 101.0
