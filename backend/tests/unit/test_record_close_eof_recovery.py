"""Prepared EOF attests only a settled socket's own token, never a live deadline."""

import asyncio
import json
import struct
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.websockets import WebSocketDisconnect

from routers import pusher
from tests.unit.test_audio_durable_outbox import Socket, _audio_frames, inline_session, remote
from tests.unit.test_record_seal_repair import source, PATH as REPAIR_PATH
from tests.unit.utils.test_listen_pusher_session import make_session
from utils import executors, pusher_record_barrier as barriers, pusher_record_finish as finish
from utils.batch_pipeline import record_seal_repair as repair
from utils.batch_pipeline.record_producer_proof import producer_tokens_dead
from utils.pusher_record_close import PendingClose


class OpenSocket(Socket):
    def __init__(self):
        super().__init__([])
        self.incoming = asyncio.Queue()
        self.prepared = asyncio.Event()
        self.control_reply = asyncio.Event()

    async def receive_bytes(self):
        frame = await self.incoming.get()
        if frame is None:
            raise WebSocketDisconnect(1000)
        return frame

    async def send_bytes(self, data):
        await super().send_bytes(data)
        if struct.unpack('<I', data[:4])[0] == 206:
            self.control_reply.set()
            if json.loads(data[4:]).get('status') == 'prepared':
                self.prepared.set()


def prepare():
    return (
        struct.pack('<I', 104)
        + json.dumps(
            dict(
                conversation_id='conversation',
                record_close_only=True,
                request_id='request',
                phase='prepare',
                watermark=0,
            )
        ).encode()
    )


@pytest.fixture
def recovery(inline_session, monkeypatch):
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED', 'true')
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED_SERVE_PERCENT', '100')
    client, path, _, _ = inline_session
    client.rows[path]['status'] = 'completed'
    owners, trackers, socket_barriers = [], [], []
    start, tracker_type = finish.start_background_task, executors.ExecutorFutureTracker

    def owner(coro, **kwargs):
        task = start(coro, **kwargs)
        owners.append(task)
        return task

    def tracker(*args):
        value = tracker_type(*args)
        trackers.append(value)
        return value

    def barrier(uid):
        value = barriers.PusherRecordBarrier(uid)
        socket_barriers.append(value)
        return value

    monkeypatch.setattr(finish, 'start_background_task', owner)
    monkeypatch.setattr(pusher, 'ExecutorFutureTracker', tracker)
    monkeypatch.setattr(pusher, 'PusherRecordBarrier', barrier)
    return SimpleNamespace(client=client, path=path, owners=owners, trackers=trackers, barriers=socket_barriers)


async def start_prepared():
    socket = OpenSocket()
    task = asyncio.create_task(
        pusher._websocket_util_trigger(socket, 'owner', 16000, audio_custody=1, record_close_protocol=3)
    )
    for frame in [*_audio_frames('conversation', [b'\x01\x00' * 2]), prepare()]:
        socket.incoming.put_nowait(frame)
    try:
        await asyncio.wait_for(socket.prepared.wait(), 2)
    except BaseException:
        socket.incoming.put_nowait(None)
        await asyncio.wait_for(task, 2)
        raise
    return socket, task


async def end_socket(socket, task, owners):
    socket.incoming.put_nowait(None)
    await asyncio.wait_for(task, 2)
    if owners:
        await asyncio.wait_for(asyncio.gather(*owners), 2)


@pytest.mark.asyncio
@pytest.mark.parametrize('durable_tail', [False, True])
async def test_prepared_eof_settled_token_needs_repair_tail_proof(recovery, source, monkeypatch, durable_tail):
    socket, task = await start_prepared()
    token = recovery.barriers[0].upload_sessions['conversation']
    admission_before = barriers._CLOSE_REFUSAL_COUNTERS['admission']._value.get()
    await end_socket(socket, task, recovery.owners)
    tokens = recovery.client.rows[recovery.path]['record_upload_sessions']
    assert list(tokens) == [token]
    assert 'abandoned_at' in tokens[token]
    assert producer_tokens_dead(tokens, None)
    assert not recovery.client.rows[recovery.path].get('record_audio_closed')
    assert not finish._closed_record_drains
    assert barriers._CLOSE_REFUSAL_COUNTERS['admission']._value.get() == admission_before
    store, client, artifacts = source
    client.rows[REPAIR_PATH]['record_upload_sessions'] = tokens
    if not durable_tail:
        monkeypatch.setattr(repair, 'retained_record_units', lambda *args, **kwargs: iter([(100, 1, [])]))
    planned = repair.plan_seals(store, ['pending'], object(), artifacts)
    assert planned['entries'][0]['disposition'] == ('eligible' if durable_tail else 'proof_refused')
    assert repair.apply_seals(store, planned, planned['plan_sha256']) == (
        {'sealed': 1} if durable_tail else {'proof_refused': 1}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('reconnect', [False, True])
async def test_eof_waits_for_real_executor_and_never_attests_reconnect_token(recovery, reconnect):
    socket, task = await start_prepared()
    old_token = recovery.barriers[0].upload_sessions['conversation']
    tracker = recovery.trackers[0]
    entered, release = asyncio.Event(), threading.Event()
    loop = asyncio.get_running_loop()

    def late_executor_work():
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(10)

    with tracker.scope():
        late = asyncio.create_task(executors.run_blocking(executors.storage_executor, late_executor_work))
    new_socket = new_task = None
    try:
        await asyncio.wait_for(entered.wait(), 2)
        late.cancel()
        await asyncio.gather(late, return_exceptions=True)
        await end_socket(socket, task, [])
        await asyncio.sleep(0)
        tokens = recovery.client.rows[recovery.path]['record_upload_sessions']
        assert tracker.pending and 'abandoned_at' not in tokens[old_token]
        assert not producer_tokens_dead(tokens, None)
        assert recovery.owners and not recovery.owners[0].done()
        if reconnect:
            new_socket, new_task = await start_prepared()
            new_token = recovery.barriers[1].upload_sessions['conversation']
            assert new_token != old_token
        release.set()
        await asyncio.wait_for(asyncio.gather(*recovery.owners), 2)
        tokens = recovery.client.rows[recovery.path]['record_upload_sessions']
        assert 'abandoned_at' in tokens[old_token]
        if reconnect:
            assert 'abandoned_at' not in tokens[new_token]
            assert not producer_tokens_dead(tokens, None)
            assert not new_task.done()
    finally:
        release.set()
        await asyncio.gather(late, return_exceptions=True)
        if new_socket is not None:
            await end_socket(new_socket, new_task, recovery.owners)
        if not task.done():
            await end_socket(socket, task, recovery.owners)
        if recovery.owners:
            await asyncio.wait_for(asyncio.gather(*recovery.owners), 2)


@pytest.mark.asyncio
async def test_live_handshake_deadline_keeps_producer_fenced(recovery):
    socket, task = await start_prepared()
    try:
        clock = [1000.0]
        session = make_session(
            deps_overrides={'monotonic': lambda: clock[0], 'finish_recording_audio': AsyncMock(return_value=False)}
        )
        session.pusher_connected = session.record_close_supported = True
        session.pusher_ws = SimpleNamespace(send=AsyncMock())
        await session.request_recording_close('conv-1')
        session.pending_record_closes['conv-1'].prepared = True
        clock[0] += 31
        await session.request_recording_close('conv-1')
        assert not session.pending_record_closes
        tokens = recovery.client.rows[recovery.path]['record_upload_sessions']
        assert tokens and all('abandoned_at' not in value for value in tokens.values())
        assert not producer_tokens_dead(tokens, None)
        assert not task.done() and not recovery.owners
    finally:
        await end_socket(socket, task, recovery.owners)


@pytest.mark.asyncio
@pytest.mark.parametrize('cohort', ['off', 'outside'])
async def test_disabled_or_noncohort_never_enters_prepared_recovery(recovery, monkeypatch, cohort):
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED', 'false' if cohort == 'off' else 'true')
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED_SERVE_PERCENT', '0')
    monkeypatch.setattr(
        pusher, 'abandon_evicted_record_drain', Mock(side_effect=AssertionError('inert recovery called'))
    )
    socket = Socket([*_audio_frames('conversation', [b'\x01\x00' * 2]), prepare()])
    await pusher._websocket_util_trigger(socket, 'owner', 16000, audio_custody=1, record_close_protocol=3)
    assert not recovery.owners
    assert recovery.client.rows[recovery.path]['record_upload_sessions'] == {}


@pytest.mark.asyncio
@pytest.mark.parametrize('unsettled', ['worker', 'executor'])
async def test_prepared_recovery_deadline_retains_fence_without_cancelling_work(monkeypatch, unsettled):
    monkeypatch.setattr(finish, 'PREPARED_ABANDON_DEADLINE_SECONDS', 0.5)
    release = asyncio.Event()
    task = asyncio.create_task(release.wait() if unsettled == 'worker' else asyncio.sleep(0))
    tracker = executors.ExecutorFutureTracker(executors.storage_executor)
    future = asyncio.get_running_loop().create_future()
    if unsettled == 'executor':
        tracker.observe(executors.storage_executor, future)
    barrier = SimpleNamespace(forget_evicted_tokens=Mock(), abandon_recordings=AsyncMock())
    owners = []
    start = finish.start_background_task

    def owner(coro, **kwargs):
        value = start(coro, **kwargs)
        owners.append(value)
        return value

    monkeypatch.setattr(finish, 'start_background_task', owner)
    try:
        assert finish.abandon_evicted_record_drain(task, barrier, tracker, prepared={'record'})
        await asyncio.wait_for(owners[0], 2)
        barrier.abandon_recordings.assert_not_awaited()
        assert not future.cancelled()
        if unsettled == 'worker':
            assert not task.done()
        else:
            assert tracker.pending
        assert owners[0] not in finish._abandon_record_drains
    finally:
        release.set()
        future.set_result(None)
        await task


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', [False, True])
async def test_aborted_live_rollover_seals_like_legacy_without_ending_socket(recovery, monkeypatch, enabled):
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED', str(enabled).lower())
    socket = OpenSocket()
    task = asyncio.create_task(
        pusher._websocket_util_trigger(socket, 'owner', 16000, audio_custody=1, record_close_protocol=3)
    )
    for frame in [*_audio_frames('conversation', [b'\x01\x00' * 2]), prepare()]:
        socket.incoming.put_nowait(frame)
    try:
        await asyncio.wait_for(socket.control_reply.wait(), 2)
        projected = asyncio.Event()
        loop = asyncio.get_running_loop()
        upload = pusher.upload_audio_chunks_batch

        def capture(*args, **kwargs):
            result = upload(*args, **kwargs)
            loop.call_soon_threadsafe(projected.set)
            return result

        monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', capture)
        if enabled:
            clock = [100.0]
            relay = SimpleNamespace(send=AsyncMock(side_effect=socket.incoming.put_nowait))
            session = make_session(
                deps_overrides={'finish_recording_audio': AsyncMock(return_value=True), 'monotonic': lambda: clock[0]},
                config_overrides={'uid': 'owner'},
            )
            session.pusher_ws, session.pusher_connected = relay, True
            session.record_close_supported = session.record_close_abort_supported = True
            session.pending_record_closes['conversation'] = PendingClose(
                request_id='request', socket=relay, prepared=True, base=4, deadline=99
            )
            await session.request_recording_close('conversation')
        socket.incoming.put_nowait(struct.pack('<I', 103) + b'successor')
        await asyncio.wait_for(projected.wait(), 2)
        async with asyncio.timeout(2):
            while not recovery.client.rows[recovery.path].get('record_audio_closed'):
                await asyncio.sleep(0)
        row = recovery.client.rows[recovery.path]
        assert row.get('record_audio_closed')
        assert not row['record_upload_sessions']
        assert not task.done()
    finally:
        await end_socket(socket, task, recovery.owners)


@pytest.mark.parametrize('durable', [False, True])
async def test_pusher_abort_requires_source_proof_and_hands_off_current_buffer(recovery, durable):
    socket, task = await start_prepared()
    try:
        socket.control_reply.clear()
        abort = dict(
            conversation_id='conversation',
            record_close_only=True,
            request_id='request',
            phase='abort',
            watermark=4,
            source_tail_durable=durable,
        )
        socket.incoming.put_nowait(struct.pack('<I', 104) + json.dumps(abort).encode())
        await asyncio.wait_for(socket.control_reply.wait(), 2)
        replies = [json.loads(frame[4:]) for frame in socket.sent if struct.unpack('<I', frame[:4])[0] == 206]
        assert replies[-1]['status'] == ('aborted' if durable else 'tail_not_durable')
        row = recovery.client.rows[recovery.path]
        assert not row.get('record_audio_closed')  # Abort itself never requests closure.
        assert row['record_upload_sessions']
        assert not recovery.owners
    finally:
        await end_socket(socket, task, recovery.owners)
    if durable:
        assert row['record_audio_closed'] and not recovery.owners
    else:
        assert not row.get('record_audio_closed')
        assert all('abandoned_at' in token for token in row['record_upload_sessions'].values())


async def test_abort_keeps_existing_close_queue_fenced_during_pusher_tail_commit(recovery, monkeypatch):
    socket, task = await start_prepared()
    legacy = asyncio.Event()
    entered, release = asyncio.Event(), asyncio.Event()

    async def finalized(*args, **kwargs):
        legacy.set()

    monkeypatch.setattr(pusher, 'process_conversation_task', AsyncMock(side_effect=finalized))
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 60)
    try:
        # A prior ordinary close request exists, followed by a source tail that
        # the prepared fence still owns. Abort must not unblock that queue yet.
        socket.incoming.put_nowait(struct.pack('<I', 104) + json.dumps({'conversation_id': 'conversation'}).encode())
        await asyncio.wait_for(legacy.wait(), 2)
        commit = pusher._commit_durable_audio_window

        async def paused_commit(**kwargs):
            entered.set()
            await release.wait()
            return await commit(**kwargs)

        monkeypatch.setattr(pusher, '_commit_durable_audio_window', paused_commit)
        socket.incoming.put_nowait(_audio_frames('conversation', [b'\x02\x00' * 2], start=1000 + 2 / 16000)[1])
        abort = dict(
            conversation_id='conversation',
            record_close_only=True,
            request_id='request',
            phase='abort',
            watermark=8,
            source_tail_durable=True,
        )
        socket.incoming.put_nowait(struct.pack('<I', 104) + json.dumps(abort).encode())
        await asyncio.wait_for(entered.wait(), 2)
        row = recovery.client.rows[recovery.path]
        assert row['record_upload_sessions'] and not row.get('record_audio_closed')
        assert not task.done()
        release.set()
        async with asyncio.timeout(2):
            while not row.get('record_audio_closed'):
                await asyncio.sleep(0)
        assert not row['record_upload_sessions'] and not task.done()
    finally:
        release.set()
        await end_socket(socket, task, recovery.owners)
