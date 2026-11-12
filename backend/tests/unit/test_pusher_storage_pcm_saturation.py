"""Hermetic slow-GCS saturation, written before byte admission.

Events model a 30-120s outage without wall-clock sleeps. The storage callable
is replaced, but submission, the custody commit, receipt and ACK path are real.
This measures Python allocations and process RSS, not GCS SDK buffering or
deployed socket counts. Run in the normal isolated unit-file lane.
"""

import asyncio
import hashlib
from collections import Counter
import os
from pathlib import Path
import resource
import struct
import subprocess
import threading
import tracemalloc
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from routers import pusher
from utils.pusher_protocol import BUFFERED_AUDIO_MAX_BYTES, ByteBudget
from tests.unit.test_audio_durable_outbox import Socket, _audio_frames, inline_session, remote
from utils.other.audio_outbox import read_pcm
from utils.pusher_storage_budget import MIN_STORAGE_PCM_BUDGET_MB, StoragePcmBudget, storage_pcm_budget_bytes

MIB = 1024 * 1024
LIMIT = 8 * MIB
PCM_SIZE = 512 * 1024


def current_rss_bytes():
    status = Path('/proc/self/status')
    if status.exists():
        return next(
            int(line.split()[1]) * 1024 for line in status.read_text().splitlines() if line.startswith('VmRSS:')
        )
    # macOS has no /proc; ps reports resident KiB for this exact test process.
    return int(subprocess.check_output(['/bin/ps', '-o', 'rss=', '-p', str(os.getpid())], text=True)) * 1024


def configure(monkeypatch, limit):
    monkeypatch.setenv('PUSHER_STORAGE_PCM_BUDGET_MB', str(limit // MIB))
    from utils.pusher_storage_budget import StoragePcmBudget

    budget = StoragePcmBudget(limit)
    monkeypatch.setattr(pusher, 'storage_pcm_budget', budget)
    return budget


class BufferedSocket:
    """One serial producer; only the real commit callback can trim its WAL copy."""

    def __init__(self, index):
        self.uid = f'synthetic-{index}'
        self.original = bytes([index + 1, 0]) * (PCM_SIZE // 2)
        self.buffer = bytearray(self.original)
        self.frames = [{'sequence': index, 'samples': PCM_SIZE // 2, 'start': 1000.0}]
        self.checkpoints = [dict(frame) for frame in self.frames]
        self.websocket = SimpleNamespace(send_bytes=AsyncMock(), close=AsyncMock())
        self.queue = MagicMock()
        self.budget = ByteBudget(20 * MIB)
        self.budget.reserve(len(self.buffer))
        self.commits = 0

    def committed(self):
        self.commits += 1
        self.buffer.clear()
        self.frames.clear()

    async def flush(self, *, tail=False):
        kwargs = {'tail': True} if tail else {}
        return await pusher._commit_durable_audio_window(
            uid=self.uid,
            payload=bytes(self.buffer),
            frames=list(self.frames),
            conversation_id=None,
            start=1000.0,
            sample_rate=16000,
            custody_root='synthetic-root',
            protection_level=None,
            audio_custody=1,
            timeline_v2=False,
            websocket=self.websocket,
            durable_queue=self.queue,
            budget=self.budget,
            queue_wait_timeout=None,
            on_committed=self.committed,
            **kwargs,
        )


class SlowGCS:
    def __init__(self):
        self.release = threading.Event()
        self.lock = threading.Lock()
        self.active = Counter()
        self.max_per_socket = Counter()
        self.bytes = 0
        self.peak = 0
        self.calls = []
        self.fail = False

    def __call__(self, uid, payload, *args, **kwargs):
        with self.lock:
            self.active[uid] += 1
            self.max_per_socket[uid] = max(self.max_per_socket[uid], self.active[uid])
            self.bytes += len(payload)
            self.peak = max(self.peak, self.bytes)
            self.calls.append((uid, hashlib.sha256(payload).digest()))
        try:
            assert self.release.wait(10), 'test must release every owned storage thread'
            if self.fail:
                raise OSError('synthetic failure wave')
            return SimpleNamespace(conversation_id=None, samples=len(payload) // 2, to_dict=lambda: {'committed': True})
        finally:
            with self.lock:
                self.bytes -= len(payload)
                self.active[uid] -= 1


async def settled_admissions(tasks):
    # Scheduler turns, not a simulated storage delay; bounded failure deadline.
    for _ in range(1000):
        await asyncio.sleep(0.001)
        if all(task.done() for task in tasks):
            return
        # Refused tasks settle immediately; admitted work remains in the stub.
        if sum(task.done() for task in tasks) >= 38:
            return
    # The test-first unbounded implementation holds all 50 in GCS.


@pytest.mark.slow
@pytest.mark.asyncio
async def test_50_sockets_plateau_refuse_without_ack_then_retry_once(monkeypatch):
    budget = configure(monkeypatch, LIMIT)
    gcs = SlowGCS()
    monkeypatch.setattr(pusher, 'commit_pcm_window', gcs)
    sockets = [BufferedSocket(index) for index in range(50)]
    tracemalloc.start()
    baseline, _ = tracemalloc.get_traced_memory()
    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    resident_before = current_rss_bytes()
    tasks = [asyncio.create_task(sock.flush()) for sock in sockets]
    try:
        await settled_admissions(tasks)
        inflight = pusher.PUSHER_STORAGE_PCM_INFLIGHT_BYTES._value.get()
        assert inflight <= LIMIT * 3 // 4, f'unbounded PCM: {inflight} bytes for {LIMIT}-byte budget'
        assert gcs.peak <= LIMIT * 3 // 4
        refused = [sock for sock, task in zip(sockets, tasks) if task.done()]
        assert len(refused) == 38
        for sock in refused:
            assert sock.buffer == sock.original and sock.frames == sock.checkpoints
            assert sock.commits == 0 and sock.budget.used == PCM_SIZE
            sock.websocket.send_bytes.assert_not_awaited()
            sock.queue.stage_committed.assert_not_called()
        for _ in range(30):
            # Repeated data-driven boundaries during the same GCS outage do
            # not grow submissions, allocate waiting tasks or trim input.
            for sock in refused:
                assert await sock.flush() is None
                assert sock.buffer == sock.original and sock.frames == sock.checkpoints
            assert pusher.PUSHER_STORAGE_PCM_INFLIGHT_BYTES._value.get() == inflight
            assert gcs.peak <= LIMIT * 3 // 4
        for sock in sockets:
            sock.websocket.close.assert_not_awaited()
            assert len(sock.buffer) < 20 * MIB
        allocated, peak = tracemalloc.get_traced_memory()
        assert peak - baseline < LIMIT + sum(len(sock.buffer) for sock in sockets) + 4 * MIB
        # ru_maxrss is a high-water mark; it cannot prove RSS drains. Bound its
        # growth separately from live byte accounting (macOS bytes/Linux KiB).
        import sys

        rss_scale = 1 if sys.platform == 'darwin' else 1024
        assert (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - rss_before) * rss_scale < 32 * MIB
        assert allocated >= 0
        resident_saturated = current_rss_bytes()
        assert resident_saturated <= resident_before + LIMIT + 50 * PCM_SIZE + 16 * MIB
        gcs.release.set()
        await asyncio.gather(*tasks)
        for sock in refused:  # The next per-socket flush boundary, after recovery.
            assert await sock.flush() is not None
        assert all(sock.commits == 1 and not sock.buffer and not sock.frames for sock in sockets)
        assert all(sock.websocket.send_bytes.await_count == 1 for sock in sockets)
        assert len(gcs.calls) == 50 and max(gcs.max_per_socket.values()) == 1
        assert gcs.bytes == 0 and budget.used == 0
        assert pusher.PUSHER_STORAGE_PCM_INFLIGHT_BYTES._value.get() == 0
        gcs.calls.clear()  # Drop recorder metadata; it never retains settled PCM.
        import gc

        gc.collect()
        drained, _ = tracemalloc.get_traced_memory()
        assert drained < peak
        # Resident allocator pages need not immediately return to the OS. The
        # live RSS must stay on its plateau after all copies/buffers drain;
        # exact submitted bytes and Python live allocations are checked above.
        assert current_rss_bytes() <= resident_saturated + 4 * MIB
    finally:
        gcs.release.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        tracemalloc.stop()


@pytest.mark.asyncio
async def test_mass_tail_uses_reserved_quarter_while_live_is_full(monkeypatch):
    budget = configure(monkeypatch, LIMIT)
    gcs = SlowGCS()
    monkeypatch.setattr(pusher, 'commit_pcm_window', gcs)
    live = [BufferedSocket(index) for index in range(12)]
    tasks = [asyncio.create_task(sock.flush()) for sock in live]
    tails = [BufferedSocket(index) for index in range(50)]
    # 50 small disconnect tails fit in the reserved lane; sizing larger tails
    # requires a measured production distribution, which this test cannot supply.
    for sock in tails:
        sock.buffer = bytearray(sock.original[:4096])
        sock.original = bytes(sock.buffer)
    try:
        for _ in range(1000):
            if gcs.bytes == LIMIT * 3 // 4:
                break
            await asyncio.sleep(0.001)
        refused = BufferedSocket(49)
        assert await refused.flush() is None
        tail_tasks = [asyncio.create_task(sock.flush(tail=True)) for sock in tails]
        tasks.extend(tail_tasks)
        for _ in range(1000):
            if len(gcs.calls) == 62:
                break
            await asyncio.sleep(0.001)
        assert len(gcs.calls) == 62 and not any(task.done() for task in tail_tasks)
        assert budget.used <= LIMIT
        # Barrier markers/close/abandon use their actual separate executor even
        # when PCM is held. No budget fixture may stub their admission.
        from utils.pusher_record_barrier import PusherRecordBarrier

        barrier = PusherRecordBarrier('synthetic')
        barrier.keep_close_pending = True
        calls = []
        for stage in ('close', 'abandon', 'marker'):
            assert (
                await asyncio.wait_for(barrier._close_metadata('synthetic', lambda: calls.append(stage) or stage), 1)
                == stage
            )
        assert calls == ['close', 'abandon', 'marker']
        gcs.release.set()
        await asyncio.gather(*tasks)
        assert all(sock.commits == 1 for sock in tails) and budget.used == 0
    finally:
        gcs.release.set()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('boundary', ['size', 'conversation', 'process', 'gap', 'framed'])
async def test_real_router_retains_refused_window_across_flush_boundaries(inline_session, monkeypatch, boundary):
    client, path, barrier, projected = inline_session
    configure(monkeypatch, 0)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    first, second = b'\x01\x00' * 160, b'\x02\x00' * 160
    commit = pusher._commit_durable_audio_window
    refused = []

    async def refuse_once(**kwargs):
        if not refused:
            refused.append((kwargs['payload'], kwargs['frames']))
            return None
        return await commit(**kwargs)

    monkeypatch.setattr(pusher, '_commit_durable_audio_window', refuse_once)
    frames = _audio_frames('conversation', [first])
    next_conversation = 'conversation'
    if boundary == 'conversation':
        next_conversation = 'next'
        client.rows[('users', 'owner', 'conversations', 'next')] = {'record_lane_owner': 'batch_live_v1'}
        frames.append(struct.pack('<I', 103) + b'next')
    elif boundary == 'process':
        import json

        frames.append(struct.pack('<I', 104) + json.dumps({'conversation_id': 'conversation'}).encode())
        monkeypatch.setattr(pusher, 'process_conversation_task', AsyncMock())
    if boundary == 'framed':
        monkeypatch.setattr(pusher, 'framed_pack', lambda uid: True)
    frames.append(struct.pack('<Id', 101, 1010.0 if boundary == 'gap' else 1000.01) + second)
    sock = Socket(frames)
    await asyncio.wait_for(
        pusher._websocket_util_trigger(
            sock, 'owner', 16000, audio_custody=1, audio_timeline=2 if boundary in ('gap', 'framed') else None
        ),
        5,
    )
    from utils.other.audio_outbox import AudioReceipt
    import json

    receipts = [
        AudioReceipt(**json.loads(frame[4:])['receipt'])
        for frame in sock.sent
        if struct.unpack('<I', frame[:4])[0] == 203
    ]
    assert refused and refused[0][0] == first
    assert receipts and read_pcm('owner', receipts[0]) == first
    assert receipts[0].conversation_id == 'conversation'
    assert read_pcm('owner', receipts[-1]) == second
    assert receipts[-1].conversation_id == next_conversation
    assert sock.close_code == 1000


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [False, True])
async def test_flag_zero_preserves_exact_pcm_ack_and_failure_characterization(monkeypatch, failure):
    configure(monkeypatch, 0)
    gcs = SlowGCS()
    gcs.fail = failure
    monkeypatch.setattr(pusher, 'commit_pcm_window', gcs)
    sockets = [BufferedSocket(index) for index in range(50)]
    tasks = [asyncio.create_task(sock.flush()) for sock in sockets]
    try:
        for _ in range(1000):
            if len(gcs.calls) == 50:
                break
            await asyncio.sleep(0.001)
        assert len(gcs.calls) == 50 and gcs.bytes == 50 * PCM_SIZE
        gcs.release.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for sock, result in zip(sockets, results):
            assert (sock.uid, hashlib.sha256(sock.original).digest()) in gcs.calls
            if failure:
                assert isinstance(result, OSError)
                assert sock.buffer == sock.original and sock.frames == sock.checkpoints
                assert sock.commits == 0
                sock.websocket.send_bytes.assert_not_awaited()
            else:
                assert result is not None and sock.commits == 1
                sock.websocket.send_bytes.assert_awaited_once_with(pusher.audio_custody_ack_frame({'committed': True}))
            sock.websocket.close.assert_not_awaited()
        assert max(gcs.max_per_socket.values()) == 1 and gcs.bytes == 0
    finally:
        gcs.release.set()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [False, True])
async def test_cancelled_caller_holds_admission_until_real_thread_settles(monkeypatch, caplog, failure):
    budget = configure(monkeypatch, LIMIT)
    settle = MagicMock(wraps=budget.settle)
    monkeypatch.setattr(budget, 'settle', settle)
    gcs = SlowGCS()
    gcs.fail = failure
    monkeypatch.setattr(pusher, '_pcm_error_logged_at', {})
    errors = pusher.PUSHER_STORAGE_PCM_ERRORS_TOTAL.labels(reason='late_storage')
    errors_before = errors._value.get()
    monkeypatch.setattr(pusher, 'commit_pcm_window', gcs)
    sock = BufferedSocket(0)
    task = asyncio.create_task(sock.flush())
    try:
        for _ in range(1000):
            if gcs.bytes:
                break
            await asyncio.sleep(0.001)
        assert gcs.bytes == PCM_SIZE
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        settle.assert_not_called()
        assert budget.used == PCM_SIZE
        assert pusher.PUSHER_STORAGE_PCM_INFLIGHT_BYTES._value.get() == PCM_SIZE
        assert sock.buffer == sock.original and sock.frames == sock.checkpoints
        sock.websocket.send_bytes.assert_not_awaited()
        gcs.release.set()
        for _ in range(1000):
            if not budget.used:
                break
            await asyncio.sleep(0.001)
        assert budget.used == 0 and not pusher._pcm_commits
        settle.assert_called_once_with(PCM_SIZE)
        assert errors._value.get() == errors_before + int(failure)
        logs = [r for r in caplog.records if 'reason=late_storage' in r.message]
        assert len(logs) == int(failure)
        assert pusher.PUSHER_STORAGE_PCM_INFLIGHT_BYTES._value.get() == 0
        sock.websocket.send_bytes.assert_not_awaited()
    finally:
        gcs.release.set()
        await asyncio.gather(task, *pusher._pcm_commits, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('peer_gone', [False, True], ids=['stalled-storage', 'peer-disconnected'])
async def test_admission_pause_cancellation_keeps_wal_without_tail_storage(inline_session, monkeypatch, peer_gone):
    from fastapi.websockets import WebSocketState

    client, path, barrier, projected = inline_session
    budget = configure(monkeypatch, LIMIT)
    held = budget.live_limit
    assert budget.acquire(held)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    monkeypatch.setattr(pusher, 'RECORD_INLINE_FINISH_TIMEOUT', 1.0)
    gcs = SlowGCS()
    monkeypatch.setattr(pusher, 'commit_pcm_window', gcs)
    paused = asyncio.Event()
    windows = []
    commit, retain = pusher._commit_durable_audio_window, pusher.RetainedPcmWindow

    async def committing(**kwargs):
        result = await commit(**kwargs)
        if result is None:
            paused.set()
        return result

    def retaining(*args):
        window = retain(*args)
        windows.append(window)
        return window

    monkeypatch.setattr(pusher, '_commit_durable_audio_window', committing)
    monkeypatch.setattr(pusher, 'RetainedPcmWindow', retaining)
    pcm = b'\x01\x00' * 160
    client_wal = _audio_frames('conversation', [pcm, pcm])
    sock = Socket(client_wal)
    handler = asyncio.create_task(pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1))
    try:
        await asyncio.wait_for(paused.wait(), 5)
        checkpoints = [dict(frame) for frame in windows[0].frames]
        if peer_gone:
            sock.client_state = WebSocketState.DISCONNECTED
            gcs.release.set()  # A faulty cancellation flush would commit and ACK the gone peer.
        handler.cancel()
        done, _ = await asyncio.wait({handler}, timeout=1.0)
        assert handler in done, 'cancellation cleanup must not wait for storage or its retries'
        with pytest.raises(asyncio.CancelledError):
            await handler
        assert not gcs.calls and not projected and not sock.sent
        assert windows[0].payload == pcm and windows[0].frames == checkpoints
        assert len(sock.frames) == 1 and len(client_wal) == 3
        assert budget.used == held and not pusher._pcm_commits
        assert client.rows[path]['record_upload_sessions']
        assert not client.rows[path]['record_audio_closed']
        assert 'conversation' in barrier.failed_recordings
        assert sock.close_code == (None if peer_gone else 1006)
    finally:
        gcs.release.set()
        await asyncio.wait_for(asyncio.gather(handler, return_exceptions=True), 5)
        budget.release(held)


@pytest.mark.asyncio
async def test_refusal_telemetry_failure_is_still_non_ack_and_non_exception(monkeypatch):
    budget = configure(monkeypatch, LIMIT)
    assert budget.acquire(budget.live_limit)
    counter = MagicMock()
    counter.labels.side_effect = RuntimeError('synthetic telemetry fault')
    monkeypatch.setattr(pusher, 'PUSHER_STORAGE_PCM_REFUSALS_TOTAL', counter)
    storage = MagicMock()
    monkeypatch.setattr(pusher, 'commit_pcm_window', storage)
    sock = BufferedSocket(0)
    try:
        assert await sock.flush() is None
        assert sock.buffer == sock.original and sock.frames == sock.checkpoints
        storage.assert_not_called()
        sock.websocket.send_bytes.assert_not_awaited()
        sock.websocket.close.assert_not_awaited()
    finally:
        budget.release(budget.live_limit)


@pytest.mark.asyncio
async def test_real_socket_full_budget_tail_retains_producer_without_error_close(inline_session, monkeypatch):
    client, path, barrier, projected = inline_session
    budget = configure(monkeypatch, LIMIT)
    assert budget.acquire(LIMIT, tail=True)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    refused, tasks = asyncio.Event(), []
    commit, create = pusher._commit_durable_audio_window, pusher.create_named_task

    async def observe(**kwargs):
        result = await commit(**kwargs)
        if result is None:
            refused.set()
        return result

    def creating(*args, **kwargs):
        task = create(*args, **kwargs)
        if kwargs.get('name', '').endswith(':receive'):
            tasks.append(task)
        return task

    monkeypatch.setattr(pusher, '_commit_durable_audio_window', observe)
    monkeypatch.setattr(pusher, 'create_named_task', creating)
    sock = Socket(_audio_frames('conversation', [b'\x01\x00' * 160] * 3))
    handler = asyncio.create_task(pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1))
    try:
        await asyncio.wait_for(refused.wait(), 5)
        tasks[0].cancel()  # Cancellable intake pause; even a full tail cannot select 1011.
        await asyncio.wait_for(handler, 5)
        assert sock.close_code == 1000 and not sock.sent and not projected
        assert len(sock.frames) == 2
        assert client.rows[path]['record_upload_sessions']
        assert not client.rows[path]['record_audio_closed']
        assert 'conversation' in barrier.failed_recordings
    finally:
        budget.release(LIMIT)
        await asyncio.wait_for(handler, 5)


@pytest.mark.asyncio
async def test_real_barrier_begin_failure_close_and_abandon_during_pcm_saturation(inline_session, monkeypatch):
    client, path, barrier, _ = inline_session
    budget = configure(monkeypatch, LIMIT)
    assert budget.acquire(LIMIT, tail=True)
    from utils import pusher_record_barrier as module

    calls = []
    for name in (
        'set_record_upload_pending',
        'seal_record_audio',
        'mark_record_upload_failed',
        'abandon_record_upload_session',
    ):
        original = getattr(module.record_audio_db, name)

        def record(*args, _name=name, _fn=original, **kwargs):
            calls.append((_name, threading.current_thread().name))
            return _fn(*args, **kwargs)

        monkeypatch.setattr(module.record_audio_db, name, record)
    try:
        await asyncio.wait_for(barrier.begin_recording('conversation'), 1)
        assert await asyncio.wait_for(barrier.finish_recording('conversation'), 1)
        await asyncio.wait_for(barrier.fail_recording('conversation'), 1)
        # Fresh begin owns the exact token needed by the real abandonment path.
        other = module.PusherRecordBarrier('owner')
        await asyncio.wait_for(other.begin_recording('conversation'), 1)
        await asyncio.wait_for(other.abandon_recordings(), 1)
        assert {
            'set_record_upload_pending',
            'seal_record_audio',
            'mark_record_upload_failed',
            'abandon_record_upload_session',
        } <= {name for name, _ in calls}
        assert all(thread.startswith('record-barrier') for _, thread in calls)
        assert budget.used == LIMIT
    finally:
        budget.release(LIMIT)


@pytest.mark.asyncio
async def test_enabled_failure_wave_releases_capacity_and_retains_unacked_input(monkeypatch):
    budget = configure(monkeypatch, LIMIT)
    gcs = SlowGCS()
    gcs.fail = True
    monkeypatch.setattr(pusher, 'commit_pcm_window', gcs)
    sockets = [BufferedSocket(index) for index in range(50)]
    tasks = [asyncio.create_task(sock.flush()) for sock in sockets]
    try:
        await settled_admissions(tasks)
        assert budget.used == LIMIT * 3 // 4
        gcs.release.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert sum(isinstance(result, OSError) for result in results) == 12
        assert sum(result is None for result in results) == 38
        assert budget.used == 0
        assert all(sock.buffer == sock.original and sock.frames == sock.checkpoints for sock in sockets)
        assert all(not sock.websocket.send_bytes.await_count for sock in sockets)
        # Model subsequent source-WAL replay after the failed storage wave.
        gcs.fail = False
        for sock in sockets:
            assert await sock.flush() is not None
        assert all(sock.commits == 1 for sock in sockets) and budget.used == 0
    finally:
        gcs.release.set()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.parametrize(
    'value, expected',
    [(None, 0), ('0', 0), ('1', 0), ('26', 0), ('27', 27 * MIB), ('512', 512 * MIB), ('bad', 0), ('-1', 0)],
)
def test_startup_configuration_default_and_kill_switch(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv('PUSHER_STORAGE_PCM_BUDGET_MB', raising=False)
    else:
        monkeypatch.setenv('PUSHER_STORAGE_PCM_BUDGET_MB', value)
    assert storage_pcm_budget_bytes() == expected


def test_tail_refusal_and_exact_release():
    budget = StoragePcmBudget(LIMIT)
    assert not budget.acquire(LIMIT + 1, tail=True) and budget.used == 0
    assert budget.acquire(budget.live_limit)
    assert not budget.acquire(1)
    assert budget.acquire(LIMIT // 4, tail=True)
    assert not budget.acquire(1, tail=True)
    budget.release(budget.live_limit)
    budget.release(LIMIT // 4)
    assert budget.used == 0


def test_minimum_enabled_budget_can_admit_the_largest_socket_window():
    budget = StoragePcmBudget(MIN_STORAGE_PCM_BUDGET_MB * MIB)
    assert budget.acquire(BUFFERED_AUDIO_MAX_BYTES)
    budget.release(BUFFERED_AUDIO_MAX_BYTES)
    assert budget.acquire(BUFFERED_AUDIO_MAX_BYTES, tail=True)
    budget.release(BUFFERED_AUDIO_MAX_BYTES)
    assert budget.used == 0
    # The next smaller integer MiB cannot satisfy the live-lane contract.
    assert StoragePcmBudget((MIN_STORAGE_PCM_BUDGET_MB - 1) * MIB).live_limit < BUFFERED_AUDIO_MAX_BYTES


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['recover', 'cancel_to_replay', 'cancel_handler'])
async def test_first_refusal_stops_30_minute_windows_before_socket_budget_can_fill(
    inline_session, monkeypatch, outcome
):
    from fastapi.websockets import WebSocketDisconnect
    from tests.unit.test_audio_durable_outbox import _sent_receipts

    _, _, barrier, _ = inline_session
    budget = configure(monkeypatch, LIMIT)
    monkeypatch.setattr(pusher, 'RECORD_INLINE_FINISH_TIMEOUT', 1.0)
    held = budget.live_limit
    assert budget.acquire(held)
    pcm = b'\x01\x00' * (16000 * 60)
    client_wal = [pcm] * 30
    sock = Socket([struct.pack('<I', 103) + b'conversation'] + [struct.pack('<Id', 101, 1000.0) + pcm] * 30)
    attempts, windows, tasks = [], [], []
    saturated, stop_source = asyncio.Event(), asyncio.Event()
    commit, retain, create = pusher._commit_durable_audio_window, pusher.RetainedPcmWindow, pusher.create_named_task
    receive = sock.receive_bytes
    reads = 0

    def retaining(*args):
        window = retain(*args)
        windows.append(window)
        return window

    def creating(*args, **kwargs):
        task = create(*args, **kwargs)
        if kwargs.get('name', '').endswith(':receive'):
            tasks.append(task)
        return task

    async def receiving():
        nonlocal reads
        if stop_source.is_set():
            raise WebSocketDisconnect(1000)
        reads += 1
        return await receive()

    async def committing(**kwargs):
        result = await commit(**kwargs)
        attempts.append((kwargs['tail'], kwargs['budget'], result))
        if len(attempts) >= 30:
            saturated.set()
        return result

    monkeypatch.setattr(pusher, 'RetainedPcmWindow', retaining)
    monkeypatch.setattr(pusher, 'create_named_task', creating)
    monkeypatch.setattr(pusher, '_commit_durable_audio_window', committing)
    monkeypatch.setattr(sock, 'receive_bytes', receiving)
    handler = asyncio.create_task(pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1))
    released = False
    try:
        await asyncio.wait_for(saturated.wait(), 5)
        # Thirty full-minute windows are offered; after thirty capacity probes
        # only the FIRST has entered this socket. Unread source WAL stays owned
        # by the producer, rather than charging another 29 windows server-side.
        assert reads == 2 and len(sock.frames) == 29 and len(windows) == 1
        assert windows[0].payload == pcm and len(windows[0].frames) == 1
        assert all(result is None and not tail for tail, _, result in attempts)
        assert attempts[-1][1].used == len(pcm) < BUFFERED_AUDIO_MAX_BYTES // 2
        assert not sock.sent and sock.close_code is None and not handler.done()
        for stage in ('close', 'abandon', 'marker'):
            assert await asyncio.wait_for(barrier._close_metadata('other', lambda: stage), 1) == stage
        stop_source.set()
        if outcome == 'recover':
            budget.release(held)
            released = True
        elif outcome == 'cancel_to_replay':
            # Cancellation keeps the refused window unacknowledged for WAL
            # replay, without starting a reserved-lane commit during cleanup.
            tasks[0].cancel()
        else:
            handler.cancel()  # SIGTERM cancels the endpoint, not its private receive task.
        if outcome == 'cancel_handler':
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(handler, 5)
        else:
            await asyncio.wait_for(handler, 5)
        receipts = _sent_receipts(sock)
        if outcome == 'recover':
            assert len(receipts) == 1 and read_pcm('owner', receipts[0]) == pcm
        else:
            assert not receipts
            assert windows[0].payload == pcm and len(windows[0].frames) == 1
            assert 'conversation' in barrier.failed_recordings
        assert len(sock.frames) == 29 and client_wal == [pcm] * 30
        assert sock.close_code == (1006 if outcome == 'cancel_handler' else 1000)
        assert budget.used == (0 if released else held)
        assert not attempts[-1][0]
    finally:
        if not released:
            budget.release(held)
        if not handler.done():
            stop_source.set()
        else:
            for task in tasks:
                if not task.done():
                    task.cancel()
        await asyncio.wait_for(asyncio.gather(handler, *tasks, return_exceptions=True), 5)


@pytest.mark.asyncio
async def test_enabled_legacy_window_checkpoint_count_is_bounded(inline_session, monkeypatch):
    configure(monkeypatch, LIMIT)
    monkeypatch.setattr(pusher, 'MAX_PCM_WINDOW_FRAMES', 2)
    windows = []
    commit = pusher._commit_durable_audio_window

    async def record(**kwargs):
        windows.append(list(kwargs['frames']))
        return await commit(**kwargs)

    monkeypatch.setattr(pusher, '_commit_durable_audio_window', record)
    sock = Socket(_audio_frames('conversation', [b'\x01\x00'] * 5))
    await asyncio.wait_for(pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1), 5)
    assert [len(frames) for frames in windows] == [2, 2, 1]
    assert sock.close_code == 1000


@pytest.mark.asyncio
async def test_retained_deleted_owner_is_not_retried_into_new_conversation(inline_session, monkeypatch):
    client, path, _, _ = inline_session
    configure(monkeypatch, LIMIT)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    client.rows[('users', 'owner', 'conversations', 'next')] = {'record_lane_owner': 'batch_live_v1'}
    projected, refused = asyncio.Event(), asyncio.Event()
    project = pusher.PusherAudioProjection.refresh
    commit = pusher._commit_durable_audio_window
    calls = []

    def delete_on_projection(self, cid, *args, **kwargs):
        if cid == 'conversation':
            return False  # Production's gone-owner result populates the socket set.
        return project(self, cid, *args, **kwargs)

    async def refuse_second(**kwargs):
        calls.append(kwargs['conversation_id'])
        if len(calls) >= 2 and kwargs['conversation_id'] == 'conversation':
            refused.set()
            return None
        return await commit(**kwargs)

    real_run = pusher.run_blocking

    async def run(executor, fn, *args, **kwargs):
        deleting = getattr(fn, '__func__', None) is delete_on_projection
        if deleting:
            await refused.wait()
        result = await real_run(executor, fn, *args, **kwargs)
        if deleting:
            # This runs after the caller installs the returned gone-owner result.
            asyncio.get_running_loop().call_soon(projected.set)
        return result

    monkeypatch.setattr(pusher, 'run_blocking', run)
    monkeypatch.setattr(pusher.PusherAudioProjection, 'refresh', delete_on_projection)
    monkeypatch.setattr(pusher, '_commit_durable_audio_window', refuse_second)
    frames = _audio_frames('conversation', [b'\x01\x00', b'\x02\x00'])
    frames += _audio_frames('next', [b'\x03\x00'])
    sock = Socket(frames)
    receive = sock.receive_bytes
    reads = 0

    async def sequenced():
        nonlocal reads
        if reads == 3:
            await asyncio.wait_for(refused.wait(), 5)
            await asyncio.wait_for(projected.wait(), 5)
        reads += 1
        return await receive()

    monkeypatch.setattr(sock, 'receive_bytes', sequenced)
    await asyncio.wait_for(pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1), 5)
    assert calls[:2] == ['conversation', 'conversation'] and calls[-1] == 'next'
    assert sock.close_code == 1000


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['storage', 'ack_departure'])
async def test_failed_first_retry_never_reads_or_certifies_a_later_owner(inline_session, monkeypatch, failure):
    from fastapi.websockets import WebSocketDisconnect

    client, path, barrier, _ = inline_session
    next_path = ('users', 'owner', 'conversations', 'next')
    client.rows[next_path] = {'record_lane_owner': 'batch_live_v1'}
    budget = configure(monkeypatch, LIMIT)
    assert budget.acquire(LIMIT, tail=True)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    frames = _audio_frames('conversation', [b'\x01\x00']) + _audio_frames('next', [b'\x02\x00'])
    sock = Socket(frames)
    refused = asyncio.Event()
    commit = pusher._commit_durable_audio_window

    async def observe(**kwargs):
        result = await commit(**kwargs)
        if result is None:
            refused.set()
        return result

    monkeypatch.setattr(pusher, '_commit_durable_audio_window', observe)
    if failure == 'storage':
        monkeypatch.setattr(pusher, 'commit_pcm_window', MagicMock(side_effect=OSError('synthetic storage failure')))
    else:
        monkeypatch.setattr(sock, 'send_bytes', AsyncMock(side_effect=WebSocketDisconnect(1006)))
    handler = asyncio.create_task(pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1))
    try:
        await asyncio.wait_for(refused.wait(), 5)
    finally:
        budget.release(LIMIT)
    await asyncio.wait_for(handler, 5)
    assert len(sock.frames) == 2  # B's ID and PCM never entered the receive task.
    assert not client.rows[next_path].get('record_upload_sessions')
    assert 'next' not in barrier.failed_recordings
    if failure == 'storage':
        assert client.rows[path]['record_upload_sessions']
        assert not client.rows[path]['record_audio_closed']
        assert 'conversation' in barrier.failed_recordings
        assert sock.close_code == 1011  # Existing genuine storage-error policy.
    else:
        assert sock.close_code == 1006 and client.rows[path]['record_audio_closed']
    assert budget.used == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['acquire', 'release'])
@pytest.mark.parametrize('after_mutation', [False, True])
async def test_accounting_fault_fails_open_without_socket_close_or_counter_corruption(
    inline_session, monkeypatch, caplog, operation, after_mutation
):
    from tests.unit.test_audio_durable_outbox import _sent_receipts

    _, _, _, _ = inline_session
    budget = configure(monkeypatch, LIMIT)
    assert budget.acquire(128)  # Another socket's reservation must remain intact.
    release = budget.release
    original = getattr(budget, operation)

    def broken(*args, **kwargs):
        if after_mutation:
            original(*args, **kwargs)
        raise RuntimeError('injected accounting failure')

    monkeypatch.setattr(budget, operation, broken)
    fallback = MagicMock(wraps=pusher.record_fallback)
    monkeypatch.setattr(pusher, 'record_fallback', fallback)
    monkeypatch.setattr(pusher, '_pcm_error_logged_at', {})
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    metric = pusher.PUSHER_STORAGE_PCM_ERRORS_TOTAL.labels(reason=operation)
    before = metric._value.get()
    sock = Socket(_audio_frames('conversation', [b'\x01\x00', b'\x02\x00']))
    try:
        await asyncio.wait_for(pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1), 5)
        assert sock.close_code == 1000 and len(_sent_receipts(sock)) == 2
        assert budget.used == 128 and metric._value.get() == before + 2
        fail_open = [call for call in fallback.call_args_list if call.kwargs['from_mode'] == 'storage_pcm_budget']
        assert len(fail_open) == (2 if operation == 'acquire' else 0)
        assert all(call.kwargs['outcome'] == 'degraded' for call in fail_open)
        logs = [r for r in caplog.records if 'event=pusher_pcm_error' in r.message]
        assert len(logs) == 1 and f'reason={operation}' in logs[0].message
    finally:
        release(128)
