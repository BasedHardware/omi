"""Real-router fault injection for committed receipt capacity ownership.

Synthetic storage/strict Firestore fixtures are shared with the outbox suite.
Blocked work explicitly expires its capacity deadline; healthy work never
races a reduced real-clock budget.
"""

import asyncio
import struct
import threading
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.websockets import WebSocketDisconnect

from tests.unit.test_audio_durable_outbox import (
    Socket,
    _audio_frames,
    _sent_receipts,
    inline_session,
    remote,
    pusher,
    finish_module,
    barrier_module,
)
from utils import pusher_receive_metrics as metrics
from utils.other.audio_outbox import commit_pcm


@pytest.fixture
def saturated(inline_session, monkeypatch):
    client, path, barrier, projected = inline_session
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_QUEUE_MAX_SIZE', 1)
    monkeypatch.setattr(pusher, 'RECORD_INLINE_FINISH_TIMEOUT', 0.5)
    monkeypatch.setattr(pusher, 'BG_DRAIN_TIMEOUT', 0.5)
    entered, pressure, release, waiting = (asyncio.Event() for _ in range(4))
    queues, owners, timeouts = [], [], []
    real_queue = pusher.RecordProjectionQueue
    real_run = pusher.run_blocking
    real_pressure = pusher.record_would_drop
    real_start = finish_module.start_background_task
    real_timeout = asyncio.timeout
    real_observe = pusher.observe_work
    drain_active = [False]

    @contextmanager
    def observe(stage):
        with real_observe(stage):
            if stage == 'drain':
                drain_active[0] = True
            try:
                yield
            finally:
                if stage == 'drain':
                    drain_active[0] = False

    def queue(**kwargs):
        result = real_queue(**kwargs)
        queues.append(result)
        return result

    async def run(executor, fn, *args, **kwargs):
        if fn is pusher.read_pcm:
            entered.set()
            await release.wait()
        return await real_run(executor, fn, *args, **kwargs)

    def observe_pressure(stage):
        real_pressure(stage)
        if stage == 'pusher_queue':
            pressure.set()

    def start(coro, **kwargs):
        owner = real_start(coro, **kwargs)
        owners.append(owner)
        return owner

    def timeout(seconds):
        result = real_timeout(seconds)
        if seconds in (None, 300):
            timeouts.append(result)
            waiting.set()
        return result

    monkeypatch.setattr(pusher, 'RecordProjectionQueue', queue)
    monkeypatch.setattr(pusher, 'observe_work', observe)
    monkeypatch.setattr(pusher, 'run_blocking', run)
    monkeypatch.setattr(pusher, 'record_would_drop', observe_pressure)
    monkeypatch.setattr(finish_module, 'start_background_task', start)
    monkeypatch.setattr(finish_module.asyncio, 'timeout', timeout)
    finish = AsyncMock(wraps=barrier.finish_recording)
    monkeypatch.setattr(barrier, 'finish_recording', finish)

    def socket(*, extra=True):
        frames = _audio_frames('conversation', [b'\x01\x00' * 160] * 3)
        if extra:
            frames.append(struct.pack('<I', 100))
        sock = Socket(frames)
        sock.reads = 0
        real_receive = sock.receive_bytes

        async def receive():
            if sock.reads == 2:
                await entered.wait()  # Hold the real worker before filling its queue.
            sock.reads += 1
            return await real_receive()

        sock.receive_bytes = receive
        return sock

    return SimpleNamespace(
        client=client,
        path=path,
        barrier=barrier,
        projected=projected,
        entered=entered,
        pressure=pressure,
        release=release,
        waiting=waiting,
        queues=queues,
        owners=owners,
        timeouts=timeouts,
        socket=socket,
        finish=finish,
        drain_active=drain_active,
    )


async def at_capacity(state):
    await asyncio.wait_for(state.pressure.wait(), 5)
    await asyncio.wait_for(state.waiting.wait(), 5)
    assert state.queues[0].pending_projection is not None
    assert state.queues[0].has_conversation('conversation')
    assert state.client.rows[state.path]['record_upload_sessions']
    state.finish.assert_not_awaited()


async def collect(state, handler):
    state.release.set()
    await asyncio.gather(handler, *state.owners, return_exceptions=True)


@pytest.mark.asyncio
async def test_expiry_enters_drain_with_slot_intact_and_late_finish(saturated, remote):
    state = saturated
    sock = state.socket()
    before = metrics.SOCKET_CLOSED.labels('queue_wait_timeout', '<5m', 'audio')._value.get()
    handler = asyncio.create_task(pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1))
    try:
        await at_capacity(state)
        assert sock.reads == 4 and len(_sent_receipts(sock)) == 3
        state.timeouts[-1].reschedule(asyncio.get_running_loop().time() - 1)
        await asyncio.wait_for(handler, 5)
        assert sock.reads == 4 and len(sock.frames) == 1  # No heartbeat accepted after expiry.
        assert sock.close_code == 1011
        assert state.queues[0].pending_projection is not None
        assert len(state.owners) == 1 and finish_module._closed_record_drains
        assert state.drain_active[0], 'drain observation follows a worker already stuck before socket close'
        state.finish.assert_not_awaited()
        assert state.client.rows[state.path]['record_upload_sessions']
        assert metrics.SOCKET_CLOSED.labels('queue_wait_timeout', '<5m', 'audio')._value.get() == before + 1
        # The same retained worker, not a restarted projection, owns all three.
        state.release.set()
        await asyncio.wait_for(state.owners[0], 5)
        assert not state.drain_active[0]
        assert len(state.projected) == 3
        assert state.queues[0].pending_projection is None and state.queues[0].empty()
        assert state.client.rows[state.path]['record_upload_sessions'] == {}
        assert state.client.rows[state.path]['record_audio_closed']
        assert len(remote.list_blobs('audio-outbox/')) == 3
    finally:
        await collect(state, handler)


@pytest.mark.asyncio
async def test_closed_owner_admission_failure_keeps_fence_and_durable_slot(saturated, monkeypatch, remote):
    state = saturated
    monkeypatch.setattr(pusher, 'retain_closed_record_drain', lambda _: False)
    handler = asyncio.create_task(pusher._websocket_util_trigger(state.socket(), 'owner', 16000, audio_custody=1))
    try:
        await at_capacity(state)
        state.timeouts[-1].reschedule(asyncio.get_running_loop().time() - 1)
        await asyncio.wait_for(handler, 5)
        assert not state.owners
        assert state.queues[0].pending_projection is not None
        assert state.client.rows[state.path]['record_upload_sessions']
        assert not state.client.rows[state.path]['record_audio_closed']
        state.finish.assert_not_awaited()
        assert len(remote.list_blobs('audio-outbox/')) == 3
        assert len(remote.list_blobs('raw-live/')) == 3
    finally:
        await collect(state, handler)


@pytest.mark.asyncio
async def test_handler_cancellation_during_capacity_wait_keeps_same_drain_owner(saturated):
    state = saturated
    sock = state.socket()
    before = metrics.SOCKET_CLOSED.labels('cancelled', '<5m', 'audio')._value.get()
    handler = asyncio.create_task(pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1))
    try:
        await at_capacity(state)
        handler.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(handler, 5)
        assert state.queues[0].pending_projection is not None
        assert state.client.rows[state.path]['record_upload_sessions']
        assert sock.reads == 4 and len(state.owners) == 1
        assert metrics.SOCKET_CLOSED.labels('cancelled', '<5m', 'audio')._value.get() == before + 1
        state.release.set()
        await asyncio.wait_for(state.owners[0], 5)
        assert len(state.projected) == 3 and not state.barrier.upload_sessions
    finally:
        await collect(state, handler)


@pytest.mark.asyncio
@pytest.mark.parametrize('audio_custody', [None, 1])
@pytest.mark.parametrize('audio_timeline', [None, 2])
@pytest.mark.parametrize('enabled', [True, False])
async def test_kill_switch_and_mixed_listener_capabilities_keep_all_projections(
    saturated, monkeypatch, audio_custody, audio_timeline, enabled
):
    state = saturated
    monkeypatch.setenv('PUSHER_PROJECTION_QUEUE_WAIT_BOUND_ENABLED', str(enabled).lower())
    sock = state.socket()
    handler = asyncio.create_task(
        pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=audio_custody, audio_timeline=audio_timeline)
    )
    try:
        await at_capacity(state)
        assert (state.timeouts[-1].when() is not None) is enabled
        assert not handler.done() and sock.reads == 4
        state.release.set()
        await asyncio.wait_for(handler, 5)
        assert len(state.projected) == 3
        assert sock.reads == 6  # Remaining heartbeat then peer close.
        assert sock.close_code == 1000 and not state.barrier.upload_sessions
    finally:
        await collect(state, handler)


@pytest.mark.asyncio
async def test_custody_commit_remains_unbounded_by_receive_liveness(inline_session, monkeypatch):
    # The first ghostreclaim diagnostic, with a legal real-clock budget.
    _, _, _, projected = inline_session
    monkeypatch.setattr(pusher, 'WS_RECEIVE_TIMEOUT', 0.5)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    entered, release = asyncio.Event(), asyncio.Event()
    real_run = pusher.run_blocking
    dispatches = 0

    async def run(executor, fn, *args, **kwargs):
        nonlocal dispatches
        if fn is pusher.commit_pcm_window:
            dispatches += 1
            entered.set()
            await release.wait()
        return await real_run(executor, fn, *args, **kwargs)

    monkeypatch.setattr(pusher, 'run_blocking', run)
    sock = Socket(_audio_frames('conversation', [b'\x01\x00' * 160]))
    before = pusher.PUSHER_ACTIVE_WS_CONNECTIONS._value.get()
    handler = asyncio.create_task(pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        await asyncio.sleep(0.6)
        assert not handler.done() and not sock.frames and not sock.sent
        assert pusher.PUSHER_ACTIVE_WS_CONNECTIONS._value.get() == before + 1
        release.set()
        await asyncio.wait_for(handler, 5)
        assert dispatches == 1 and projected and sock.close_code == 1000
    finally:
        release.set()
        await asyncio.gather(handler, return_exceptions=True)


@pytest.mark.asyncio
async def test_unknown_midstream_commit_is_never_rerun_at_shutdown(inline_session, monkeypatch):
    client, path, barrier, _ = inline_session
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    commit = pusher.commit_pcm_window
    dispatches = 0

    def committed_then_failed(*args, **kwargs):
        nonlocal dispatches
        dispatches += 1
        commit(*args, **kwargs)
        raise OSError('synthetic lost commit result')

    monkeypatch.setattr(pusher, 'commit_pcm_window', committed_then_failed)
    sock = Socket(_audio_frames('conversation', [b'\x01\x00' * 160]))
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1)
    assert dispatches == 1 and not sock.sent
    assert client.rows[path]['record_upload_sessions'] and barrier.failed_recordings
    assert not client.rows[path]['record_audio_closed']


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['disconnect', 'send_closed', 'oserror', 'application'])
async def test_ack_failure_keeps_committed_projection_delivery(inline_session, monkeypatch, failure):
    client, path, barrier, projected = inline_session
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    errors = {
        'disconnect': WebSocketDisconnect(1006),
        'send_closed': RuntimeError('Cannot call "send" once a close message has been sent.'),
        'oserror': OSError('synthetic departed peer'),
        'application': RuntimeError('synthetic programming failure'),
    }
    sock = Socket(_audio_frames('conversation', [b'\x01\x00' * 160]))
    sock.send_bytes = AsyncMock(side_effect=errors[failure])
    reason = 'application_error' if failure == 'application' else 'peer'
    before = metrics.SOCKET_CLOSED.labels(reason, '<5m', 'audio')._value.get()
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1)
    assert len(projected) == 1 and not barrier.upload_sessions
    assert client.rows[path]['record_audio_closed']
    assert sock.close_code == (1011 if failure == 'application' else 1006)
    assert metrics.SOCKET_CLOSED.labels(reason, '<5m', 'audio')._value.get() == before + 1


def test_deadline_kill_switch_is_on_unless_explicitly_off(monkeypatch):
    monkeypatch.delenv('PUSHER_PROJECTION_QUEUE_WAIT_BOUND_ENABLED', raising=False)
    assert pusher._projection_wait_bound_enabled()
    for value in ('', 'garbage', '0', 'true'):
        monkeypatch.setenv('PUSHER_PROJECTION_QUEUE_WAIT_BOUND_ENABLED', value)
        assert pusher._projection_wait_bound_enabled()
    monkeypatch.setenv('PUSHER_PROJECTION_QUEUE_WAIT_BOUND_ENABLED', 'false')
    assert not pusher._projection_wait_bound_enabled()


@pytest.mark.asyncio
async def test_slot_is_part_of_each_conversations_drain_proof(remote):
    first = commit_pcm('owner', b'\x01\x00', 'earlier', 1000, 16000, 'root', 0)
    later = commit_pcm('owner', b'\x01\x00', 'later', 1000, 16000, 'root', 1)
    queue = finish_module.RecordProjectionQueue(maxsize=1)
    a = pusher.AudioProjection(first, 1000, 0, 1)
    b = pusher.AudioProjection(later, 1000, 0, 1)
    queue.put_nowait(a)
    queue.stage_committed(b)
    assert queue.has_conversation('earlier') and queue.has_conversation('later')
    with pytest.raises(RuntimeError):
        queue.stage_committed(a)
    assert queue.get_nowait() is a
    assert not queue.has_conversation('earlier') and queue.has_conversation('later')
    queue.task_done()
    assert queue.get_nowait() is b
    queue.task_done()
    assert not queue.has_conversation('later') and queue.pending_projection is None
    await queue.deliver_pending(timeout=None)
    await asyncio.wait_for(queue.join(), 5)


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', [True, False])
async def test_quiet_control_session_never_enters_capacity_wait(inline_session, monkeypatch, enabled):
    _, _, barrier, _ = inline_session
    monkeypatch.setenv('PUSHER_PROJECTION_QUEUE_WAIT_BOUND_ENABLED', str(enabled).lower())
    entered, release = asyncio.Event(), asyncio.Event()
    sock = Socket([struct.pack('<I', 100)] * 3)
    receive = sock.receive_bytes

    async def quiet():
        if not sock.frames:
            entered.set()
            await release.wait()
        return await receive()

    sock.receive_bytes = quiet
    before = metrics.WORK_DURATION.labels('projection_enqueue')._sum.get()
    handler = asyncio.create_task(pusher._websocket_util_trigger(sock, 'owner', 16000))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        assert not handler.done() and not barrier.upload_sessions
        assert metrics.WORK_DURATION.labels('projection_enqueue')._sum.get() == before
    finally:
        release.set()
        await asyncio.wait_for(handler, 5)
    assert sock.close_code == 1000


@pytest.mark.parametrize('abandon_first', [True, False])
def test_abandoned_close_gauge_follows_both_completion_race_orders(monkeypatch, abandon_first):
    active, outstanding = MagicMock(), MagicMock()
    monkeypatch.setattr(barrier_module, '_close_retry_slots', active)
    monkeypatch.setattr(barrier_module, '_close_outstanding_slots', outstanding)
    gauge = barrier_module.RECORD_CLOSE_ABANDONED_OUTSTANDING
    before = gauge._value.get()
    admission = barrier_module._CloseAdmission()
    if abandon_first:
        admission.abandon()
        admission.abandon()  # A second deadline observation cannot double-count.
        assert gauge._value.get() == before + 1
        admission.completed(None)
    else:
        admission.completed(None)
        admission.abandon()  # An overdue timer after completion cannot count it.
    assert gauge._value.get() == before
    active.release.assert_called_once()
    outstanding.release.assert_called_once()


@pytest.mark.asyncio
async def test_active_close_admission_refusal_is_not_counted_as_outstanding_cap(inline_session, monkeypatch):
    _, _, barrier, _ = inline_session
    barrier.keep_close_pending = True
    occupied = threading.BoundedSemaphore(1)
    occupied.acquire()
    monkeypatch.setattr(barrier_module, '_close_retry_slots', occupied)
    before = barrier_module.RECORD_CLOSE_OUTSTANDING_REFUSALS._value.get()
    with pytest.raises(barrier_module.ExecutorSaturatedError):
        await barrier._close_metadata('conversation', lambda: None)
    assert barrier_module.RECORD_CLOSE_OUTSTANDING_REFUSALS._value.get() == before


def test_close_cap_metrics_have_no_labels_and_are_exposed_by_metrics_router(monkeypatch):
    from routers import metrics as metrics_router

    monkeypatch.setenv('METRICS_SECRET', 'synthetic-scrape-token')
    response = metrics_router.metrics(SimpleNamespace(credentials='synthetic-scrape-token'))
    body = response.body.decode()
    for collector, name in (
        (barrier_module.RECORD_CLOSE_ABANDONED_OUTSTANDING, 'omi_pusher_record_close_abandoned_outstanding'),
        (barrier_module.RECORD_CLOSE_OUTSTANDING_REFUSALS, 'omi_pusher_record_close_outstanding_refusals_total'),
    ):
        assert name in body
        for family in collector.collect():
            assert all(sample.labels == {} for sample in family.samples)


@pytest.mark.asyncio
async def test_background_failure_keeps_application_classification_when_receiver_is_cancelled(
    inline_session, monkeypatch
):
    entered, never = asyncio.Event(), asyncio.Event()
    monkeypatch.setattr(pusher, 'SPEAKER_SAMPLE_PROCESS_INTERVAL', 17.0)
    real_wait = pusher.wait_for_event

    async def fail_speaker_worker(event, seconds):
        if seconds == 17.0:
            await entered.wait()
            raise RuntimeError('synthetic background failure')
        return await real_wait(event, seconds)

    monkeypatch.setattr(pusher, 'wait_for_event', fail_speaker_worker)
    sock = Socket([struct.pack('<I', 100)])
    real_receive = sock.receive_bytes

    async def receive():
        if not sock.frames:
            entered.set()
            await never.wait()
        return await real_receive()

    sock.receive_bytes = receive
    counter = metrics.SOCKET_CLOSED.labels('application_error', '<5m', 'control_only')
    before = counter._value.get()
    active_before = pusher.PUSHER_ACTIVE_WS_CONNECTIONS._value.get()
    handler = asyncio.create_task(pusher._websocket_util_trigger(sock, 'owner', 16000))
    try:
        await asyncio.wait_for(handler, 5)
        assert sock.close_code == 1011
        assert counter._value.get() == before + 1
        assert pusher.PUSHER_ACTIVE_WS_CONNECTIONS._value.get() == active_before
    finally:
        never.set()
        if not handler.done():
            handler.cancel()
        await asyncio.gather(handler, return_exceptions=True)
