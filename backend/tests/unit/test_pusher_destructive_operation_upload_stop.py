"""A storage-authority fence must stop the upload loop, not feed it retries.

Failure-Class: FC-deletion-fenced-writes-retried-forever — instance in
``backend/routers/pusher.py`` ``process_private_cloud_queue`` (observed
2026-10-13 in the pusher container at ~84 errors/30m: ``Private cloud batch
upload failed (retry 3): external data write blocked by destructive
operation <uid> <conversation>``): while an account is being deleted, the
storage authority's write fence (``external_write_fence``) refuses every
batch with ``DestructiveOperationInProgress`` — a refusal whose gate row
stays live for hours. The upload loop treated it like any transient error:
every flushed batch was retried the full three-attempt ladder (each attempt
re-reading the same two authority documents that prove the fence), the
attempt-3 ERROR line fired per batch (~28 doomed batches/30m for the
connected sessions of one deleting account), and the queue kept accepting
fresh audio for the rest of the session. The failure-class rule — a
permanently refused write must move to its terminal disposition on the
first refusal, never be replayed — already holds for the fenced terminal
writes in finalization; this pins it for the live upload lane: the first
fence refusal latches the session, the queued backlog drops with its
budget released, later chunks drop at admission, one warning is logged,
and the session itself stays healthy (the socket closes 1000, the journey
is not marked failed — audio loss here is the deletion working as
designed). Ordinary transient failures keep the existing three-attempt
retry ladder unchanged. On the parent commit every test here fails: the
fenced batch is retried four times, the queue keeps uploading, and the
session is torn down as failed.
"""

import asyncio
import struct
from collections import deque
from unittest.mock import MagicMock

import pytest
from starlette.websockets import WebSocketState

import routers.pusher as pusher
from database.legal_holds import DestructiveOperationInProgress


class FakeWebSocket:
    def __init__(self, frames=()):
        self.frames = deque(frames)
        self.client_state = WebSocketState.CONNECTED
        self.close_code = None

    async def accept(self):
        return None

    async def close(self, code=1000, reason=None):
        self.close_code = code
        self.client_state = WebSocketState.DISCONNECTED

    async def receive_bytes(self):
        await asyncio.sleep(0)
        if self.frames:
            return self.frames.popleft()
        raise asyncio.CancelledError()

    async def send_bytes(self, _data):
        return None


def _audio_frame(conversation: str = 'conversation') -> bytes:
    return struct.pack('<I', 103) + conversation.encode()


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'false')
    monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda uid: None)
    monkeypatch.setattr(pusher, 'is_audio_bytes_app_enabled', lambda uid: False)
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
    monkeypatch.setattr(pusher.users_db, 'get_data_protection_level', lambda uid: 'standard')
    monkeypatch.setattr(pusher, 'PUSHER_ACTIVE_WS_CONNECTIONS', MagicMock())
    monkeypatch.setattr(pusher_protocol_metric(), 'PUSHER_QUEUE_DROPS', MagicMock())
    monkeypatch.setattr(pusher_protocol_metric(), 'PUSHER_QUEUE_DROPPED_BYTES', MagicMock())
    monkeypatch.setattr(pusher, 'PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS', MagicMock())


def pusher_protocol_metric():
    import utils.pusher_protocol as pusher_protocol

    return pusher_protocol


@pytest.fixture
def fenced_upload(monkeypatch):
    """The storage authority refuses every batch with the account-deletion fence."""
    upload = MagicMock(
        side_effect=DestructiveOperationInProgress('external data write blocked by destructive operation')
    )
    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', upload)
    return upload


@pytest.fixture
def journey(monkeypatch):
    journey = MagicMock()
    monkeypatch.setattr(pusher, 'JourneyAttempt', MagicMock(return_value=journey))
    return journey


@pytest.mark.asyncio
async def test_fenced_batch_is_never_retried(runtime, fenced_upload, journey):
    """The first fence refusal is terminal for the batch: one attempt, no ladder."""
    websocket = FakeWebSocket([_audio_frame(), struct.pack('<I', 101) + struct.pack('d', 1.0) + b'\\x00\\x00'])

    await pusher._websocket_util_trigger(websocket, 'uid', 8000)

    assert (
        fenced_upload.call_count == 1
    ), 'a fenced upload must stop on its first refusal — the gate row stays live for hours'
    assert websocket.close_code == 1000, 'the fence is policy, not a session fault'
    journey.finish.assert_called_once_with('success')


@pytest.mark.asyncio
async def test_fenced_session_drops_the_queued_backlog_without_uploading(runtime, fenced_upload, journey):
    """Once the fence latches, batches already held for upload drop fast instead of
    replaying a write the authority just refused."""
    frames = [
        _audio_frame('conversation-a'),
        struct.pack('<I', 101) + struct.pack('d', 1.0) + b'\\x00\\x00',
        # A second conversation whose batch only becomes ready after the latch.
        _audio_frame('conversation-b'),
        struct.pack('<I', 101) + struct.pack('d', 2.0) + b'\\x00\\x00',
    ]
    websocket = FakeWebSocket(frames)

    await pusher._websocket_util_trigger(websocket, 'uid', 8000)

    assert fenced_upload.call_count == 1, 'no upload is attempted after the fence latched'
    pusher.PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS.inc.assert_called_with()


@pytest.mark.asyncio
async def test_fenced_session_stops_accepting_new_chunks(runtime, fenced_upload, journey):
    """Chunks arriving after the latch drop at admission — they are never batched,
    so the byte budget is returned and no further upload can even form."""
    upload_sizes: list[int] = []

    def _upload(chunks, *_args, **_kwargs):
        upload_sizes.append(sum(len(chunk['data']) for chunk in chunks))
        raise DestructiveOperationInProgress('external data write blocked by destructive operation')

    fenced_upload.side_effect = _upload
    frames = [
        _audio_frame(),
        struct.pack('<I', 101) + struct.pack('d', 1.0) + b'\\x00\\x00',
        struct.pack('<I', 101) + struct.pack('d', 2.0) + b'\\x00\\x00',
    ]
    websocket = FakeWebSocket(frames)

    await pusher._websocket_util_trigger(websocket, 'uid', 8000)

    assert len(upload_sizes) == 1, 'exactly one upload was attempted before the latch'
    assert websocket.close_code == 1000


@pytest.mark.asyncio
async def test_fenced_refusal_is_counted_once_as_policy_exhaustion(runtime, fenced_upload, journey, monkeypatch):
    """The fence refusal lands on the fallback counter as policy/exhausted — the same
    vocabulary the deleted-conversation drop uses — never as a generic failure."""
    fallbacks: list[dict] = []

    def _spy(**kwargs):
        fallbacks.append(kwargs)

    monkeypatch.setattr(pusher, 'record_fallback', _spy)
    websocket = FakeWebSocket([_audio_frame(), struct.pack('<I', 101) + struct.pack('d', 1.0) + b'\\x00\\x00'])

    await pusher._websocket_util_trigger(websocket, 'uid', 8000)

    policy_events = [event for event in fallbacks if event.get('reason') == 'policy']
    assert policy_events, 'the fence refusal is recorded on the fallback counter'
    for event in policy_events:
        assert event['component'] == 'pusher'
        assert event['from_mode'] == 'private_cloud_sync'
        assert event['to_mode'] == 'drop'
        assert event['outcome'] == 'exhausted'


@pytest.mark.asyncio
async def test_fenced_session_logs_one_stop_line_not_per_batch_errors(
    runtime, fenced_upload, journey, monkeypatch, caplog
):
    """The loop must not log a doomed-retry ERROR per batch for hours: one bounded
    warning carries the stop decision for the session."""
    import logging

    frames = [
        _audio_frame(),
        struct.pack('<I', 101) + struct.pack('d', 1.0) + b'\\x00\\x00',
        struct.pack('<I', 101) + struct.pack('d', 2.0) + b'\\x00\\x00',
    ]
    websocket = FakeWebSocket(frames)

    with caplog.at_level(logging.WARNING, logger='routers.pusher'):
        await pusher._websocket_util_trigger(websocket, 'uid', 8000)

    stops = [record for record in caplog.records if 'fenced by a destructive operation' in record.getMessage()]
    assert len(stops) == 1, 'exactly one stop line for the session'
    assert all(
        'Private cloud batch upload failed' not in record.getMessage() for record in caplog.records
    ), 'the doomed-retry error line must never fire for a fenced account'


@pytest.mark.asyncio
async def test_transient_failures_keep_the_full_retry_ladder(runtime, journey, monkeypatch):
    """Only the fence is terminal: an ordinary upload error keeps today's behavior —
    the whole three-attempt ladder, then the drop with a failed journey."""
    upload = MagicMock(side_effect=RuntimeError('storage unavailable'))
    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', upload)
    frames = [
        _audio_frame(),
        struct.pack('<I', 101) + struct.pack('d', 1.0) + b'\\x00\\x00',
    ]
    websocket = FakeWebSocket(frames)

    await pusher._websocket_util_trigger(websocket, 'uid', 8000)

    assert upload.call_count == pusher.PRIVATE_CLOUD_SYNC_MAX_RETRIES + 1
    pusher.PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS.inc.assert_called_once_with()
    journey.finish.assert_called_once_with('failure')


@pytest.mark.asyncio
async def test_account_deletion_variant_of_the_fence_latches_too(runtime, journey, monkeypatch):
    """The account-deletion block raises the same exception type with a different
    message; the latch keys on the type, so it stops identically."""
    upload = MagicMock(side_effect=DestructiveOperationInProgress('external data write blocked by account deletion'))
    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', upload)
    frames = [
        _audio_frame(),
        struct.pack('<I', 101) + struct.pack('d', 1.0) + b'\\x00\\x00',
        struct.pack('<I', 101) + struct.pack('d', 2.0) + b'\\x00\\x00',
    ]
    websocket = FakeWebSocket(frames)

    await pusher._websocket_util_trigger(websocket, 'uid', 8000)

    assert upload.call_count == 1, 'the account-deletion fence is the same permanent refusal'
    assert websocket.close_code == 1000


@pytest.mark.asyncio
async def test_unfenced_session_still_uploads_every_batch(runtime, journey, monkeypatch):
    """The latch can only be earned by the fence: a session whose uploads all
    succeed keeps its full upload path end to end."""
    upload = MagicMock(return_value=['chunks/uid/conversation/x.batch.bin'])
    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', upload)
    monkeypatch.setattr(pusher.conversations_db, 'create_audio_files_from_chunks', lambda *a, **k: [])
    frames = [
        _audio_frame(),
        struct.pack('<I', 101) + struct.pack('d', 1.0) + b'\\x00\\x00',
    ]
    websocket = FakeWebSocket(frames)

    await pusher._websocket_util_trigger(websocket, 'uid', 8000)

    assert upload.call_count == 1
    pusher.PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS.inc.assert_not_called()
    journey.finish.assert_called_once_with('success')


@pytest.mark.asyncio
async def test_latch_is_per_session_not_process_global(runtime, journey, monkeypatch):
    """The latch lives on the websocket session, not the process: a NEW session for
    the same account still probes the authority once — the fence may have lifted
    between sessions, and a per-process latch would refuse uploads forever."""
    upload = MagicMock(
        side_effect=DestructiveOperationInProgress('external data write blocked by destructive operation')
    )
    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', upload)
    frames = [_audio_frame(), struct.pack('<I', 101) + struct.pack('d', 1.0) + b'\\x00\\x00']

    first = FakeWebSocket(frames)
    await pusher._websocket_util_trigger(first, 'uid', 8000)
    second = FakeWebSocket(frames)
    await pusher._websocket_util_trigger(second, 'uid', 8000)

    assert upload.call_count == 2, 'each session probes the fence exactly once'
    assert first.close_code == 1000 and second.close_code == 1000


@pytest.mark.asyncio
async def test_fenced_v2_span_batch_latches_like_plain_batches(runtime, fenced_upload, journey):
    """A v2 session (acknowledged audio-timeline protocol, spanned chunks) takes the
    same fence path: the span is not a separate write authority, so its refusal
    latches identically."""
    from utils.pusher_protocol import AUDIO_TIMELINE_PROTOCOL

    frames = [
        struct.pack('<I', 100),  # heartbeat
        _audio_frame(),
        struct.pack('<I', 101) + struct.pack('d', 1.0) + b'\\x00\\x00',
        struct.pack('<I', 101) + struct.pack('d', 2.0) + b'\\x00\\x00',
    ]
    websocket = FakeWebSocket(frames)

    await pusher._websocket_util_trigger(websocket, 'uid', 8000, audio_timeline=AUDIO_TIMELINE_PROTOCOL)

    assert fenced_upload.call_count == 1, 'the spanned upload stops on its first fence refusal'
    assert websocket.close_code == 1000
    for call in fenced_upload.call_args_list:
        chunks = call.args[0]
        assert isinstance(chunks, list) and chunks and isinstance(chunks[0], dict) and 'data' in chunks[0]


@pytest.mark.asyncio
async def test_shutdown_flush_after_the_fence_still_closes_cleanly(runtime, fenced_upload, journey):
    """The fence firing during the shutdown flush must not convert the disconnect
    into a failure journey: audio loss here is the deletion working as designed."""
    frames = [
        _audio_frame(),
        struct.pack('<I', 101) + struct.pack('d', 1.0) + b'\\x00\\x00',
    ]
    websocket = FakeWebSocket(frames)

    await pusher._websocket_util_trigger(websocket, 'uid', 8000)

    assert websocket.close_code == 1000
    journey.finish.assert_called_once_with('success')


@pytest.mark.asyncio
async def test_fenced_session_never_schedules_voice_learning(runtime, fenced_upload, journey, monkeypatch):
    """Voice learning is scheduled only from an authoritative uploaded manifest; a
    fenced session has none, so the retry scheduler must never fire."""
    scheduled: list = []
    monkeypatch.setattr(pusher, 'schedule_person_voice_learning_retry', lambda uid, conv: scheduled.append(conv))
    frames = [
        _audio_frame(),
        struct.pack('<I', 101) + struct.pack('d', 1.0) + b'\\x00\\x00',
    ]
    websocket = FakeWebSocket(frames)

    await pusher._websocket_util_trigger(websocket, 'uid', 8000)

    assert scheduled == [], 'no successful manifest exists to learn from'


@pytest.mark.asyncio
async def test_transient_failure_then_fence_drops_the_held_retry_batch(runtime, journey, monkeypatch):
    """A batch already held on the ready lane from an earlier transient failure is
    dropped, not uploaded, once the fence latches — the held retry is still a write
    the authority has refused for the session."""
    attempts: list = []

    def upload(chunks, *_args, **_kwargs):
        attempts.append(len(chunks))
        if len(attempts) == 1:
            raise RuntimeError('transient storage blip')
        raise DestructiveOperationInProgress('external data write blocked by destructive operation')

    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', MagicMock(side_effect=upload))
    frames = [
        _audio_frame(),
        struct.pack('<I', 101) + struct.pack('d', 1.0) + b'\\x00\\x00',
        struct.pack('<I', 101) + struct.pack('d', 2.0) + b'\\x00\\x00',
    ]
    websocket = FakeWebSocket(frames)

    await pusher._websocket_util_trigger(websocket, 'uid', 8000)

    assert attempts == [1, 1], 'the held retry batch was not re-attempted after the latch'
    assert websocket.close_code == 1000


@pytest.mark.asyncio
async def test_fenced_session_drops_without_queue_overflow_telemetry(runtime, fenced_upload, journey, monkeypatch):
    """Deliberate fence drops are not queue overflow: the OOM-protection drop
    counters must stay silent while the fallback counter carries the refusal."""
    import utils.pusher_protocol as pusher_protocol

    queue_drops = MagicMock()
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPS', queue_drops)
    frames = [
        _audio_frame(),
        struct.pack('<I', 101) + struct.pack('d', 1.0) + b'\\x00\\x00',
        struct.pack('<I', 101) + struct.pack('d', 2.0) + b'\\x00\\x00',
    ]
    websocket = FakeWebSocket(frames)

    await pusher._websocket_util_trigger(websocket, 'uid', 8000)

    overflow = [call for call in queue_drops.labels.call_args_list if call.kwargs.get('queue') == 'private_cloud']
    assert overflow == [], 'fence drops are deliberate policy, never overflow'


@pytest.mark.asyncio
async def test_fence_with_nothing_queued_is_a_clean_noop(runtime, fenced_upload, journey):
    """A fence refusal on a conversation switch flush with an empty backlog must
    latch without touching counters or tearing the session down."""
    frames = [
        _audio_frame(),
        _audio_frame('conversation-two'),
    ]
    websocket = FakeWebSocket(frames)

    await pusher._websocket_util_trigger(websocket, 'uid', 8000)

    pusher.PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS.inc.assert_not_called()
    assert websocket.close_code == 1000
    journey.finish.assert_called_once_with('success')


@pytest.mark.asyncio
async def test_session_closes_cleanly_after_a_fenced_backlog_drain(runtime, fenced_upload, journey):
    """End to end: fence on the first flush, backlog drains by drop, the queue loop
    terminates (no busy spin), and the session closes 1000."""
    frames = [
        _audio_frame(),
        struct.pack('<I', 101) + struct.pack('d', 1.0) + b'\\x00\\x00',
        struct.pack('<I', 101) + struct.pack('d', 3.0) + b'\\x00\\x00',
        struct.pack('<I', 101) + struct.pack('d', 5.0) + b'\\x00\\x00',
    ]
    websocket = FakeWebSocket(frames)

    await asyncio.wait_for(pusher._websocket_util_trigger(websocket, 'uid', 8000), timeout=10.0)

    assert fenced_upload.call_count == 1
    assert websocket.close_code == 1000
    journey.finish.assert_called_once_with('success')
