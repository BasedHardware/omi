"""Custody ACKs follow the transcript transaction and the coverage write."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from routers.listen import coverage, transcripts
from routers.listen.runtime import ListenSessionRuntime
from models.transcript_segment import TranscriptSegment
from utils.committed_capture import PROOF_KIND
from utils.manual_speaker_assignments import merge_live_segments
from utils.other.live_audio_archive import LiveAudioArchive


def snapshot():
    return {
        'proof': PROOF_KIND,
        'runs': [
            {
                'capture_root': 'capture-test',
                'clock_epoch': 0,
                'channel': 'mono',
                'source_frame_start': 10,
                'source_frame_end': 15,
            },
        ],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize('durable', [False, True])
@pytest.mark.parametrize('lifecycle_mode', ['shadow', 'serve'])
@pytest.mark.parametrize('capture_mode', ['shadow', 'serve'])
@pytest.mark.parametrize('archive_state', ['none', 'pending', 'disabled'])
async def test_ack_only_after_successful_durable_segment_write(
    monkeypatch, durable, lifecycle_mode, capture_mode, archive_state
):
    monkeypatch.setenv('LIFECYCLE_V2_MODE', lifecycle_mode)
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', capture_mode)
    order = []
    segment = TranscriptSegment(id='segment-test', text='', speaker='SPEAKER_00', is_user=False, start=0, end=1)

    async def persist(fn, *args, **kwargs):
        if fn is transcripts.conversations_db.update_conversation_segments:
            order.append('durable')
            return merge_live_segments([], [segment.model_dump()], {}) if durable else False
        if fn is transcripts.conversations_db.update_conversation_finished_at:
            order.append('legacy_timestamp')
        if fn is coverage.record_committed:
            order.append('ledger')
            return [
                coverage.CaptureCommittedEvent(
                    conversation_id='conversation-test', capture_root='capture-test', source_start=10, source_end=15
                )
            ]
        return True

    mapper = SimpleNamespace(committed_snapshot=lambda *a: snapshot(), acknowledge=Mock(), runs=[{}])
    host = SimpleNamespace(
        request=SimpleNamespace(uid='test-account'),
        state=SimpleNamespace(speaker_map_dirty=False, source_position_map=mapper),
        is_multi_channel=False,
        persistence=SimpleNamespace(call=persist),
        send_event=lambda e: order.append('event'),
        speakers=SimpleNamespace(segment_assignments={}, speaker_to_person={}, segment_identity_status={}),
    )
    pending = []

    async def defer(key, callback):
        pending.append(callback)

    if archive_state == 'pending':
        host.private_cloud_sync_enabled = True
        host.receiver = SimpleNamespace(raw_archive=SimpleNamespace(durable=True, defer_ack=defer))
    elif archive_state == 'disabled':
        monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'true')
        host.private_cloud_sync_enabled = False
        host.receiver = SimpleNamespace(raw_archive=LiveAudioArchive(host))
    processor = object.__new__(transcripts.TranscriptProcessor)
    processor.host = host
    processor.cache = transcripts.ConversationCache(None)
    current = SimpleNamespace(id='conversation-test', transcript_segments=[])
    result = await processor._update_live_conversation(current, [segment], [], datetime.now(timezone.utc), None)
    assert bool(result) is durable
    expected = ['durable', 'ledger'] if durable and archive_state != 'pending' else ['durable']
    if durable and archive_state != 'pending' and capture_mode == 'serve':
        expected.append('event')
    if durable and lifecycle_mode == 'shadow':
        expected.append('legacy_timestamp')
    assert order == expected
    if durable and archive_state == 'pending':
        assert len(pending) == 1
        await pending[0]()
        assert order[-1] == ('event' if capture_mode == 'serve' else 'ledger')


def test_unknown_receipt_and_off_mode_never_claim_coverage(monkeypatch):
    assert coverage.record_committed('test-account', 'conversation-test', {'proof': 'received'}) == []
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'off')
    assert coverage.record_committed('test-account', 'conversation-test', snapshot()) == []


@pytest.mark.parametrize('mode', ['shadow', 'serve'])
def test_committed_frame_ranges_are_recorded_before_events(monkeypatch, mode):
    import sys
    from types import ModuleType

    authority = ModuleType('utils.capture.coverage')
    records = []
    authority.record = lambda account, key, rec: records.append((key, rec))
    monkeypatch.setitem(sys.modules, 'utils.capture.coverage', authority)
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', mode)
    events = coverage.record_committed('test-account', 'conversation-test', snapshot())
    assert len(records) == 1
    assert len(events) == (1 if mode == 'serve' else 0)
    key, record = records[0]
    assert key.channel == 'mono' and key.clock_epoch == '0'
    assert [(r.start, r.end) for r in record.ranges] == [(10, 15)]
    if events:
        assert (events[0].source_start, events[0].source_end) == (10, 15)
    authority.record = Mock(side_effect=RuntimeError('fixture unavailable'))
    assert coverage.record_committed('test-account', 'conversation-test', snapshot()) == []


@pytest.mark.asyncio
async def test_runtime_emits_the_contract_event_as_socket_json():
    from unittest.mock import AsyncMock

    runtime = object.__new__(ListenSessionRuntime)
    socket = SimpleNamespace(send_json=AsyncMock())
    runtime.state = SimpleNamespace(active=True)
    runtime.request = SimpleNamespace(websocket=socket)
    event = coverage.CaptureCommittedEvent(
        conversation_id='conversation-test', capture_root='capture-test', source_start=10, source_end=15
    )
    assert await runtime.asend_event(event)
    wire = socket.send_json.await_args.args[0]
    assert wire == event.model_dump(mode='json')
    assert wire['type'] == 'capture_committed'


@pytest.mark.asyncio
async def test_optional_publication_failure_does_not_fail_an_already_durable_flush(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    host = SimpleNamespace(
        request=SimpleNamespace(uid='synthetic'),
        persistence=SimpleNamespace(call=AsyncMock(side_effect=RuntimeError('unavailable'))),
    )
    await coverage.publish_committed(host, 'synthetic', snapshot())
