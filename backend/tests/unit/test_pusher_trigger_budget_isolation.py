"""Audio trigger lanes degrade their own bytes instead of the custody session.

Failure-Class: FC-enrichment-backpressure-terminates-custody-session — the
per-socket ``ByteBudget`` (``BUFFERED_AUDIO_MAX_BYTES``, 20 MiB) priced three
different consumers on every listen socket: the custody capture lane (the
durable window buffer and the private-cloud chunk queue, whose bytes the
client is owed an ACK for), the audio-app trigger lane and the developer
audio-webhook lane (both fire-and-forget enrichment). When an enrichment
consumer stalled long enough, its queued bytes held the shared reservation and
the next trigger-lane flush hit the shared budget's fail-closed edge:
``extend_bounded`` / ``append_bounded`` raised ``AudioBackpressure`` and the
receive loop booked it as ``Could not process audio`` + close 1011 +
``application_failed`` — a live recording killed mid-stream because an
enrichment lane was busy, forcing the client to reconnect and replay. This is
the pressure behind the Loop S sensor's largest pusher signature (about 1,000
tracebacks per 30 minutes at ``finish_receive`` in the 2026-11-05 window).

The fix separates the accounting and the degradation:

1. The trigger/webhook lanes get their own ``trigger_budget``, so their
   reservations can never starve the capture lane's reserve.
2. Both trigger-lane call sites (buffer reserve, queue append) pass
   ``drop_on_full=True`` — drop this input / evict the oldest queued item,
   release its reservation, count the drop, log a WARNING with the uid —
   instead of the custody raise.
3. The custody lane keeps its exact fail-closed semantics: capture reserves,
   the private-cloud queue and ``bound_private_pending`` still raise
   ``AudioBackpressure`` when exhausted, so a genuinely out-of-custody-budget
   session still ends 1011 with nothing acknowledged and the producer replays.

The suite pins all three surfaces: the protocol-level degradation and the
unchanged custody escalation, the handler-level saturation choreography on the
durable custody harness (a stalled trigger consumer while frames keep
streaming — every frame still commits custody and the session ends clean,
where the previous code killed the session at the overflow frame), and the
budget-isolation/accounting guards.
"""

import asyncio
import inspect
import json
import logging
import struct
from collections import deque
from unittest.mock import MagicMock

import pytest

import routers.pusher as pusher
import utils.pusher_protocol as pusher_protocol
from tests.unit.test_audio_durable_outbox import Socket, _audio_frames, remote
from utils import pusher_audio_projection
from utils.other.audio_outbox import AudioReceipt, read_pcm
from utils.pusher_protocol import (
    BUFFERED_AUDIO_MAX_BYTES,
    PUSHER_AUDIO_CUSTODY_ACK_OPCODE,
    AudioBackpressure,
    ByteBudget,
    append_bounded,
    bound_private_pending,
    extend_bounded,
    pusher_session_outcome,
    record_queue_drop,
)

logger = logging.getLogger(__name__)

# One audio frame of 130000 B: above the 4-second trigger flush threshold at
# 16 kHz (16000 * 4 * 2 = 128000 B), so every frame flushes exactly one queue
# item per enabled lane. The trigger queue's maxlen is AUDIO_BYTES_QUEUE_WARN_SIZE
# (20), so payload 21 is the first deterministic eviction.
FRAME_BYTES = 130000


def _payload(index):
    return bytes([65 + index]) * FRAME_BYTES


def _outbox(monkeypatch, enabled=True):
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'true' if enabled else 'false')


def _counted_drops(monkeypatch):
    drops = MagicMock()
    dropped_bytes = MagicMock()
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPS', drops)
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPPED_BYTES', dropped_bytes)
    return drops, dropped_bytes


def _drop_calls(counter, queue_name):
    return [call for call in counter.labels.call_args_list if call.kwargs.get('queue') == queue_name]


def _full_queue(maxlen, sizes, budget=None):
    queue = deque(maxlen=maxlen)
    for index, size in enumerate(sizes):
        if budget is not None:
            assert budget.reserve(size)
        queue.append({'data': b'x' * size, 'index': index})
    return queue


def _admit(monkeypatch, *, app=False, webhook=None, sync=True):
    monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda uid: webhook)
    monkeypatch.setattr(pusher, 'is_audio_bytes_app_enabled', lambda uid: app)
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: sync)
    if sync:
        monkeypatch.setattr(pusher.users_db, 'get_data_protection_level', lambda uid: 'standard')
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL', 0.001)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0)
    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', MagicMock(return_value=['projected']))
    monkeypatch.setattr(pusher_audio_projection.conversations_db, 'create_audio_files_from_chunks', lambda *a: [])


def _journeys(monkeypatch):
    journeys = []

    def factory(name):
        attempt = MagicMock()
        attempt.name = name
        journeys.append(attempt)
        return attempt

    monkeypatch.setattr(pusher, 'JourneyAttempt', factory)
    return journeys


def _custody_receipts(sock):
    return [
        AudioReceipt(**json.loads(frame[4:])['receipt'])
        for frame in sock.sent
        if struct.unpack('<I', frame[:4])[0] == PUSHER_AUDIO_CUSTODY_ACK_OPCODE
    ]


def _noop_consumer(recorder=None):
    async def consumer(uid, sample_rate, data):
        if recorder is not None:
            recorder.append(len(data))

    return consumer


async def _stalled_lane_session(
    monkeypatch,
    *,
    payloads,
    app_enabled=True,
    webhook_delay=None,
    sync_enabled=True,
    extra_payloads=(),
    release_after=None,
    release_drain_to=None,
    expected_processed=None,
    trigger_budget_limit=None,
    outbox=True,
):
    """Stream payloads against a consumer that stalls inside its first trigger call.

    Deterministic choreography: the first two frames (conversation binding +
    first PCM) are delivered ungated; the first flush wakes the consumer,
    which takes the first queue item and blocks inside the stub. Every later
    frame is delivered only on the test's advance handshake while the consumer
    is provably stuck, so the trigger queue deterministically overflows
    mid-stream. The session's clean disconnect is held open until the consumer
    has been released and drained, so assertions run against the fully
    settled session.
    """
    _outbox(monkeypatch, outbox)
    _admit(monkeypatch, app=app_enabled, webhook=webhook_delay, sync=sync_enabled)
    if trigger_budget_limit is not None:
        monkeypatch.setattr(pusher, 'BUFFERED_AUDIO_MAX_BYTES', trigger_budget_limit)
    journeys = _journeys(monkeypatch)
    drops, dropped_bytes = _counted_drops(monkeypatch)
    frames = _audio_frames('conversation', list(payloads) + list(extra_payloads))
    total = len(frames)
    sock = Socket(frames)
    processed = []
    armed = asyncio.Event()
    advance = asyncio.Event()
    tail_gate = asyncio.Event()
    release = asyncio.Event()
    state = {'delivered': 0}

    async def stalled_consumer(uid, sample_rate, data):
        processed.append(len(data))
        armed.set()
        await asyncio.wait_for(release.wait(), timeout=10)

    monkeypatch.setattr(pusher, 'trigger_realtime_audio_bytes', stalled_consumer)
    monkeypatch.setattr(pusher, 'send_audio_bytes_developer_webhook', stalled_consumer)

    real_receive = sock.receive_bytes

    async def paced_receive():
        if 2 <= state['delivered'] < total:
            await asyncio.wait_for(advance.wait(), timeout=10)
            advance.clear()
        if state['delivered'] >= total:
            await asyncio.wait_for(tail_gate.wait(), timeout=10)
        frame = await real_receive()
        state['delivered'] += 1
        return frame

    monkeypatch.setattr(sock, 'receive_bytes', paced_receive)

    task = asyncio.create_task(pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1))
    await asyncio.wait_for(armed.wait(), timeout=10)
    delivered = state['delivered']
    for _ in range(total - 2):
        advance.set()
        while state['delivered'] == delivered and not task.done():
            await asyncio.sleep(0)
        delivered = state['delivered']
        assert not task.done(), 'session ended before every frame was delivered'
        if sync_enabled and outbox:
            # The fetch handshake alone does not cover this frame's flush: wait
            # until its custody receipt has landed so the trigger queue state
            # is frozen at every gate and the phases below are deterministic.
            while len(_custody_receipts(sock)) < delivered - 1 and not task.done():
                await asyncio.sleep(0)
        if release_after is not None and delivered - 1 >= release_after:
            # Mid-stream recovery: the consumer has provably stalled through
            # `release_after` flushed frames; let it drain everything so far,
            # so the remaining frames land in an emptying queue.
            release.set()
            target = release_drain_to if release_drain_to is not None else delivered - 1
            for _ in range(500000):
                if len(processed) >= target or task.done():
                    break
                await asyncio.sleep(0)
    release.set()
    if expected_processed is not None:
        for _ in range(500000):
            if len(processed) >= expected_processed or task.done():
                break
            await asyncio.sleep(0)
    tail_gate.set()
    await asyncio.wait_for(task, timeout=30)
    return sock, processed, journeys, drops, dropped_bytes


class _SpyBudget(ByteBudget):
    """ByteBudget subclass recording every handler-created instance, in order."""

    instances = []

    def __init__(self, limit):
        super().__init__(limit)
        _SpyBudget.instances.append(self)


def _spy_budgets(monkeypatch):
    _SpyBudget.instances = []
    monkeypatch.setattr(pusher, 'ByteBudget', _SpyBudget)
    return _SpyBudget.instances


# ---------------------------------------------------------------------------
# Part A — ByteBudget accounting primitives (the base every drop path
# releases against) and the buffer -> queue -> consume lifecycle the handler
# runs on the trigger lane.
# ---------------------------------------------------------------------------


def test_budget_starts_empty():
    budget = ByteBudget(1000)
    assert budget.limit == 1000
    assert budget.used == 0


def test_reserve_within_limit_accepts_and_accounts():
    budget = ByteBudget(1000)
    assert budget.reserve(400) is True
    assert budget.used == 400


def test_reserve_to_exact_limit_accepts():
    budget = ByteBudget(1000)
    assert budget.reserve(1000) is True
    assert budget.used == 1000


def test_reserve_over_limit_rejects_without_accounting():
    budget = ByteBudget(1000)
    assert budget.reserve(1001) is False
    assert budget.used == 0


def test_reserve_negative_size_rejects():
    budget = ByteBudget(1000)
    assert budget.reserve(-1) is False
    assert budget.used == 0


def test_zero_size_reserve_accepts_without_accounting():
    budget = ByteBudget(1000)
    assert budget.reserve(0) is True
    assert budget.used == 0


def test_reserves_accumulate():
    budget = ByteBudget(1000)
    assert budget.reserve(300)
    assert budget.reserve(300)
    assert budget.used == 600


def test_release_shrinks_usage():
    budget = ByteBudget(1000)
    budget.reserve(500)
    budget.release(200)
    assert budget.used == 300


def test_release_floors_at_zero():
    budget = ByteBudget(1000)
    budget.reserve(100)
    budget.release(500)
    assert budget.used == 0


def test_release_restores_reserve_capacity():
    budget = ByteBudget(1000)
    budget.reserve(1000)
    assert budget.reserve(1) is False
    budget.release(1000)
    assert budget.reserve(1000) is True


def test_failed_reservation_leaves_capacity_intact():
    budget = ByteBudget(100)
    assert budget.reserve(200) is False
    assert budget.reserve(100) is True
    assert budget.used == 100


def test_zero_limit_rejects_any_positive_reserve():
    budget = ByteBudget(0)
    assert budget.reserve(1) is False
    assert budget.reserve(0) is True


def test_two_budgets_account_independently():
    first = ByteBudget(100)
    second = ByteBudget(100)
    first.reserve(100)
    assert second.reserve(100) is True
    assert first.used == 100
    assert second.used == 100


def test_reserve_exact_fit_after_release():
    budget = ByteBudget(500)
    budget.reserve(200)
    budget.release(200)
    assert budget.reserve(500) is True


def test_repeated_reserve_release_cycles_stay_consistent():
    budget = ByteBudget(100)
    for _ in range(25):
        assert budget.reserve(100) is True
        budget.release(100)
    assert budget.used == 0


def test_usage_never_exceeds_limit_across_cycles():
    budget = ByteBudget(10)
    for _ in range(20):
        budget.reserve(6)
        budget.release(6)
    assert budget.used <= 10


def test_release_without_prior_reserve_floors_silently():
    budget = ByteBudget(100)
    budget.release(50)
    assert budget.used == 0


def test_full_buffer_queue_consume_lifecycle_drains_to_zero(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(1000)
    buffer = bytearray()
    queue = deque(maxlen=4)
    assert extend_bounded(buffer, b'x' * 400, 'audio_app_buffer', budget)
    stored = {'data': bytes(buffer)}
    assert append_bounded(queue, stored, 'audio_bytes', byte_budget=budget, size_of=lambda i: len(i['data'])) is False
    budget.release(len(stored['data']))
    assert budget.used == 0


def test_lifecycle_with_mid_cycle_eviction_stays_consistent(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(1000)
    queue = deque(maxlen=1)
    buffer = bytearray()
    assert extend_bounded(buffer, b'x' * 400, 'audio_app_buffer', budget)
    append_bounded(
        queue,
        {'data': bytes(buffer)},
        'audio_bytes',
        byte_budget=budget,
        size_of=lambda i: len(i['data']),
        drop_on_full=True,
    )
    buffer = bytearray()
    assert extend_bounded(buffer, b'y' * 400, 'audio_app_buffer', budget)
    second = {'data': bytes(buffer)}
    evicted = append_bounded(
        queue, second, 'audio_bytes', byte_budget=budget, size_of=lambda i: len(i['data']), drop_on_full=True
    )
    assert evicted is True
    assert budget.used == 400
    budget.release(len(second['data']))
    assert budget.used == 0


def test_two_item_interleaved_lifecycle_drains_to_zero(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(1000)
    queue = deque(maxlen=4)
    for size in (300, 300):
        buffer = bytearray()
        assert extend_bounded(buffer, b'x' * size, 'audio_app_buffer', budget)
        append_bounded(
            queue, {'data': bytes(buffer)}, 'audio_bytes', byte_budget=budget, size_of=lambda i: len(i['data'])
        )
    assert budget.used == 600
    for item in list(queue):
        budget.release(len(item['data']))
    assert budget.used == 0


def test_flush_handoff_keeps_a_single_reservation(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(1000)
    buffer = bytearray()
    assert extend_bounded(buffer, b'x' * 400, 'audio_app_buffer', budget)
    queue = deque(maxlen=4)
    used_before = budget.used
    append_bounded(queue, {'data': bytes(buffer)}, 'audio_bytes', byte_budget=budget, size_of=lambda i: len(i['data']))
    assert budget.used == used_before


# ---------------------------------------------------------------------------
# Part B — drop/backpressure metric contracts.
# ---------------------------------------------------------------------------


def test_queue_drop_counts_per_queue_label(monkeypatch):
    drops, _ = _counted_drops(monkeypatch)
    record_queue_drop('audio_bytes', 10)
    drops.labels.assert_called_once_with(queue='audio_bytes')


def test_queue_drop_counts_dropped_bytes(monkeypatch):
    _, dropped_bytes = _counted_drops(monkeypatch)
    record_queue_drop('audio_bytes', 10)
    dropped_bytes.labels.assert_called_once_with(queue='audio_bytes')
    dropped_bytes.labels.return_value.inc.assert_called_once_with(10)


def test_queue_drop_without_size_counts_no_bytes(monkeypatch):
    _, dropped_bytes = _counted_drops(monkeypatch)
    record_queue_drop('audio_bytes', 0)
    dropped_bytes.labels.assert_not_called()


def test_queue_drop_bytes_accumulate_across_drops(monkeypatch):
    _, dropped_bytes = _counted_drops(monkeypatch)
    record_queue_drop('audio_bytes', 10)
    record_queue_drop('audio_bytes', 15)
    assert dropped_bytes.labels.call_count == 2
    assert dropped_bytes.labels.return_value.inc.call_args_list == [((10,),), ((15,),)]


def test_queue_drop_labels_stay_distinct_per_queue(monkeypatch):
    drops, _ = _counted_drops(monkeypatch)
    record_queue_drop('audio_app_buffer', 5)
    record_queue_drop('audio_webhook_buffer', 5)
    labels = [call.kwargs['queue'] for call in drops.labels.call_args_list]
    assert labels == ['audio_app_buffer', 'audio_webhook_buffer']


def test_backpressure_message_is_the_producer_replay_contract():
    assert str(AudioBackpressure('pusher_queue', {'data': b'x'})) == (
        'audio custody capacity exhausted; input remains unacknowledged'
    )


def test_backpressure_carries_pending_input():
    pending = {'data': b'pending'}
    assert AudioBackpressure('pusher_queue', pending).pending is pending


def test_backpressure_counts_would_drop_stage(monkeypatch):
    would_drop = MagicMock()
    monkeypatch.setattr(pusher_protocol, 'record_would_drop', would_drop)
    AudioBackpressure('pusher_budget', b'data')
    would_drop.assert_called_once_with('pusher_budget')


def test_backpressure_increments_stage_labeled_metric(monkeypatch):
    backpressure = MagicMock()
    monkeypatch.setattr(pusher_protocol, 'BACKPRESSURE', backpressure)
    AudioBackpressure('pusher_pending')
    backpressure.labels.assert_called_once_with(stage='pusher_pending')


def test_backpressure_is_a_runtime_error():
    assert issubclass(AudioBackpressure, RuntimeError)


# ---------------------------------------------------------------------------
# Part C — append_bounded custody defaults: the escalation this fix leaves
# exactly in place for custody queues.
# ---------------------------------------------------------------------------


def test_append_with_space_returns_false_and_appends(monkeypatch):
    _outbox(monkeypatch)
    queue = deque(maxlen=3)
    assert append_bounded(queue, {'data': b'x'}, 'audio_bytes') is False
    assert len(queue) == 1


def test_append_full_budgeted_queue_raises_under_outbox(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(100)
    queue = _full_queue(1, [10], budget)
    with pytest.raises(AudioBackpressure):
        append_bounded(queue, {'data': b'y'}, 'audio_bytes', byte_budget=budget, size_of=lambda i: len(i['data']))


def test_append_full_audio_named_queue_raises_under_outbox(monkeypatch):
    _outbox(monkeypatch)
    queue = _full_queue(1, [10])
    with pytest.raises(AudioBackpressure):
        append_bounded(queue, {'data': b'y'}, 'audio_bytes')


def test_append_full_private_named_queue_raises_under_outbox(monkeypatch):
    _outbox(monkeypatch)
    queue = _full_queue(1, [10])
    with pytest.raises(AudioBackpressure):
        append_bounded(queue, {'data': b'y'}, 'private_cloud')


def test_append_full_budgeted_plain_name_queue_raises_under_outbox(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(100)
    queue = _full_queue(1, [10], budget)
    with pytest.raises(AudioBackpressure):
        append_bounded(queue, {'data': b'y'}, 'plain_queue', byte_budget=budget, size_of=lambda i: len(i['data']))


def test_append_full_plain_unbudgeted_queue_evicts_without_raise(monkeypatch):
    _outbox(monkeypatch)
    queue = _full_queue(1, [10])
    assert append_bounded(queue, {'data': b'y'}, 'plain_queue') is True
    assert [item['data'] for item in queue] == [b'y']


def test_custody_raise_carries_the_item(monkeypatch):
    _outbox(monkeypatch)
    queue = _full_queue(1, [10])
    pending = {'data': b'y'}
    with pytest.raises(AudioBackpressure) as raised:
        append_bounded(queue, pending, 'audio_bytes')
    assert raised.value.pending is pending


def test_custody_raise_does_not_mutate_the_queue(monkeypatch):
    _outbox(monkeypatch)
    queue = _full_queue(2, [10, 20])
    with pytest.raises(AudioBackpressure):
        append_bounded(queue, {'data': b'y'}, 'audio_bytes')
    assert [item['data'] for item in queue] == [b'x' * 10, b'x' * 20]


def test_custody_raise_does_not_consume_budget(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(100)
    queue = _full_queue(1, [10], budget)
    with pytest.raises(AudioBackpressure):
        append_bounded(queue, {'data': b'y'}, 'audio_bytes', byte_budget=budget, size_of=lambda i: len(i['data']))
    assert budget.used == 10


def test_custody_evict_releases_evicted_bytes(monkeypatch):
    _outbox(monkeypatch, False)
    budget = ByteBudget(100)
    queue = _full_queue(1, [40], budget)
    budget.reserve(10)  # the incoming item's buffer reservation, as the caller holds it
    append_bounded(queue, {'data': b'y' * 10}, 'audio_bytes', byte_budget=budget, size_of=lambda i: len(i['data']))
    assert budget.used == 10


def test_custody_evict_counts_the_drop(monkeypatch):
    _outbox(monkeypatch, False)
    drops, _ = _counted_drops(monkeypatch)
    queue = _full_queue(1, [40])
    append_bounded(queue, {'data': b'y'}, 'audio_bytes', size_of=lambda i: len(i['data']))
    assert _drop_calls(drops, 'audio_bytes')


def test_custody_evict_counts_dropped_bytes(monkeypatch):
    _outbox(monkeypatch, False)
    _, dropped_bytes = _counted_drops(monkeypatch)
    queue = _full_queue(1, [40])
    append_bounded(queue, {'data': b'y'}, 'audio_bytes', size_of=lambda i: len(i['data']))
    dropped_bytes.labels.return_value.inc.assert_called_once_with(40)


def test_custody_evict_keeps_fifo_remainder(monkeypatch):
    _outbox(monkeypatch, False)
    queue = _full_queue(3, [10, 20, 30])
    append_bounded(queue, {'data': b'y'}, 'audio_bytes', size_of=lambda i: len(i['data']))
    assert [item['data'] for item in queue] == [b'x' * 20, b'x' * 30, b'y']


def test_append_return_true_exactly_when_evicted(monkeypatch):
    _outbox(monkeypatch, False)
    queue = deque(maxlen=2)
    assert append_bounded(queue, {'data': b'a'}, 'audio_bytes') is False
    assert append_bounded(queue, {'data': b'b'}, 'audio_bytes') is False
    assert append_bounded(queue, {'data': b'c'}, 'audio_bytes') is True


def test_outbox_disabled_audio_named_queue_evicts_instead_of_raise(monkeypatch):
    _outbox(monkeypatch, False)
    queue = _full_queue(1, [10])
    assert append_bounded(queue, {'data': b'y'}, 'audio_bytes') is True
    assert queue[0]['data'] == b'y'


def test_outbox_disabled_budgeted_queue_evicts_and_releases(monkeypatch):
    _outbox(monkeypatch, False)
    budget = ByteBudget(100)
    queue = _full_queue(1, [40], budget)
    budget.reserve(5)
    append_bounded(queue, {'data': b'y' * 5}, 'audio_bytes', byte_budget=budget, size_of=lambda i: len(i['data']))
    assert budget.used == 5


def test_maxlen_respected_after_evict_append(monkeypatch):
    _outbox(monkeypatch, False)
    queue = deque(maxlen=5)
    for index in range(8):
        append_bounded(queue, {'data': bytes([index])}, 'audio_bytes')
    assert len(queue) == 5
    assert [item['data'] for item in queue] == [bytes([index]) for index in range(3, 8)]


def test_evict_without_size_of_releases_nothing_but_counts(monkeypatch):
    _outbox(monkeypatch, False)
    drops, dropped_bytes = _counted_drops(monkeypatch)
    budget = ByteBudget(100)
    queue = _full_queue(1, [40], budget)
    append_bounded(queue, {'data': b'y'}, 'audio_bytes', byte_budget=budget)
    assert budget.used == 40
    assert _drop_calls(drops, 'audio_bytes')
    dropped_bytes.labels.assert_not_called()


def test_repeated_saturated_custody_appends_still_raise(monkeypatch):
    _outbox(monkeypatch)
    queue = _full_queue(2, [10, 20])
    for _ in range(5):
        with pytest.raises(AudioBackpressure):
            append_bounded(queue, {'data': b'y'}, 'audio_bytes')


def test_audio_bytes_queue_name_matches_the_raise_gate(monkeypatch):
    _outbox(monkeypatch)
    queue = _full_queue(1, [10])
    with pytest.raises(AudioBackpressure):
        append_bounded(queue, {'data': b'y'}, 'audio_bytes')


def test_private_cloud_queue_name_matches_the_raise_gate(monkeypatch):
    _outbox(monkeypatch)
    queue = _full_queue(1, [10])
    with pytest.raises(AudioBackpressure):
        append_bounded(queue, {'data': b'y'}, 'private_cloud')


def test_stored_items_keep_identity_through_append(monkeypatch):
    _outbox(monkeypatch, False)
    queue = deque(maxlen=2)
    first = {'data': b'a'}
    second = {'data': b'b'}
    append_bounded(queue, first, 'audio_bytes')
    append_bounded(queue, second, 'audio_bytes')
    assert queue[0] is first
    assert queue[1] is second


def test_custody_evict_releases_exactly_the_size_of_value(monkeypatch):
    _outbox(monkeypatch, False)
    budget = ByteBudget(100)
    queue = deque(maxlen=1)
    budget.reserve(33)
    queue.append({'data': b'a', 'weight': 33})
    append_bounded(queue, {'data': b'b'}, 'audio_bytes', byte_budget=budget, size_of=lambda i: i['weight'])
    assert budget.used == 0


def test_unconfigured_outbox_env_defaults_to_the_custody_raise(monkeypatch):
    monkeypatch.delenv('AUDIO_DURABLE_OUTBOX_ENABLED', raising=False)
    queue = _full_queue(1, [10])
    with pytest.raises(AudioBackpressure):
        append_bounded(queue, {'data': b'y'}, 'audio_bytes')


def test_unconfigured_outbox_env_defaults_budgeted_queues_to_the_raise(monkeypatch):
    monkeypatch.delenv('AUDIO_DURABLE_OUTBOX_ENABLED', raising=False)
    budget = ByteBudget(100)
    queue = _full_queue(1, [10], budget)
    with pytest.raises(AudioBackpressure):
        append_bounded(queue, {'data': b'y'}, 'plain', byte_budget=budget, size_of=lambda i: len(i['data']))


def test_full_boundary_walk_raises_only_at_the_bound(monkeypatch):
    _outbox(monkeypatch)
    queue = deque(maxlen=2)
    append_bounded(queue, {'data': b'a'}, 'audio_bytes')
    append_bounded(queue, {'data': b'b'}, 'audio_bytes')
    with pytest.raises(AudioBackpressure):
        append_bounded(queue, {'data': b'c'}, 'audio_bytes')


def test_outbox_disabled_budgeted_plain_name_queue_evicts(monkeypatch):
    _outbox(monkeypatch, False)
    budget = ByteBudget(100)
    queue = _full_queue(1, [10], budget)
    append = append_bounded(queue, {'data': b'y'}, 'plain', byte_budget=budget, size_of=lambda i: len(i['data']))
    assert append is True


def test_custody_raise_counts_the_would_drop_stage(monkeypatch):
    _outbox(monkeypatch)
    would_drop = MagicMock()
    monkeypatch.setattr(pusher_protocol, 'record_would_drop', would_drop)
    queue = _full_queue(1, [10])
    with pytest.raises(AudioBackpressure):
        append_bounded(queue, {'data': b'y'}, 'audio_bytes')
    would_drop.assert_called_once_with('pusher_queue')


def test_bound_private_pending_raises_under_outbox(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(10**9)
    pending = {f'conv-{index}': {'data': b'x' * 10} for index in range(21)}
    with pytest.raises(AudioBackpressure):
        bound_private_pending(pending, budget)


def test_bound_private_pending_evicts_oldest_without_outbox(monkeypatch):
    _outbox(monkeypatch, False)
    drops, dropped_bytes = _counted_drops(monkeypatch)
    budget = ByteBudget(10**9)
    budget.reserve(210)
    pending = {f'conv-{index}': {'data': b'x' * 10} for index in range(21)}
    bound_private_pending(pending, budget)
    assert 'conv-0' not in pending
    assert len(pending) == 20
    assert budget.used == 200
    assert _drop_calls(drops, 'private_cloud_pending')
    dropped_bytes.labels.return_value.inc.assert_called_once_with(10)


def test_bound_private_pending_under_limit_is_a_noop(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(10**9)
    pending = {f'conv-{index}': {'data': b'x' * 10} for index in range(19)}
    bound_private_pending(pending, budget)
    assert len(pending) == 19


# ---------------------------------------------------------------------------
# Part D — append_bounded drop_on_full policy: the enrichment degradation.
# ---------------------------------------------------------------------------


def test_policy_full_queue_evicts_oldest_without_raising(monkeypatch):
    _outbox(monkeypatch)
    queue = _full_queue(2, [10, 20])
    assert append_bounded(queue, {'data': b'y'}, 'audio_bytes', drop_on_full=True) is True
    assert [item['data'] for item in queue] == [b'x' * 20, b'y']


def test_policy_eviction_releases_the_evicted_reservation(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(100)
    queue = _full_queue(2, [10, 20], budget)
    budget.reserve(5)
    append_bounded(
        queue,
        {'data': b'y' * 5},
        'audio_bytes',
        byte_budget=budget,
        size_of=lambda i: len(i['data']),
        drop_on_full=True,
    )
    assert budget.used == 25


def test_policy_eviction_counts_the_drop(monkeypatch):
    _outbox(monkeypatch)
    drops, _ = _counted_drops(monkeypatch)
    queue = _full_queue(2, [10, 20])
    append_bounded(queue, {'data': b'y'}, 'audio_bytes', drop_on_full=True)
    assert len(_drop_calls(drops, 'audio_bytes')) == 1


def test_policy_eviction_counts_dropped_bytes(monkeypatch):
    _outbox(monkeypatch)
    _, dropped_bytes = _counted_drops(monkeypatch)
    queue = _full_queue(2, [10, 20])
    append_bounded(queue, {'data': b'y'}, 'audio_bytes', size_of=lambda i: len(i['data']), drop_on_full=True)
    dropped_bytes.labels.return_value.inc.assert_called_once_with(10)


def test_policy_keeps_the_newest_item(monkeypatch):
    _outbox(monkeypatch)
    queue = _full_queue(2, [10, 20])
    newest = {'data': b'new'}
    append_bounded(queue, newest, 'audio_bytes', drop_on_full=True)
    assert queue[-1] is newest


def test_policy_preserves_remaining_order(monkeypatch):
    _outbox(monkeypatch)
    queue = _full_queue(3, [10, 20, 30])
    append_bounded(queue, {'data': b'y'}, 'audio_bytes', drop_on_full=True)
    assert [item['data'] for item in queue] == [b'x' * 20, b'x' * 30, b'y']


def test_policy_sustained_saturation_stays_bounded_without_raising(monkeypatch):
    _outbox(monkeypatch)
    queue = deque(maxlen=4)
    for index in range(50):
        append_bounded(queue, {'data': bytes([index])}, 'audio_bytes', drop_on_full=True)
    assert len(queue) == 4
    assert [item['data'] for item in queue] == [bytes([index]) for index in range(46, 50)]


def test_policy_outcome_matches_across_outbox_modes(monkeypatch):
    final_states = []
    for enabled in (True, False):
        _outbox(monkeypatch, enabled)
        drops, _ = _counted_drops(monkeypatch)
        budget = ByteBudget(1000)
        queue = deque(maxlen=2)
        for _ in range(5):
            assert budget.reserve(10)
            append_bounded(
                queue,
                {'data': b'x' * 10},
                'audio_bytes',
                byte_budget=budget,
                size_of=lambda i: len(i['data']),
                drop_on_full=True,
            )
        final_states.append(([item['data'] for item in queue], budget.used, drops.labels.call_count))
    assert final_states[0] == final_states[1]


def test_policy_without_budget_on_audio_named_queue_evicts(monkeypatch):
    _outbox(monkeypatch)
    queue = _full_queue(1, [10])
    assert append_bounded(queue, {'data': b'y'}, 'audio_bytes', drop_on_full=True) is True
    assert queue[0]['data'] == b'y'


def test_policy_without_budget_on_plain_queue_evicts(monkeypatch):
    _outbox(monkeypatch)
    queue = _full_queue(1, [10])
    assert append_bounded(queue, {'data': b'y'}, 'plain', drop_on_full=True) is True


def test_policy_non_full_append_is_a_plain_append(monkeypatch):
    _outbox(monkeypatch)
    drops, _ = _counted_drops(monkeypatch)
    queue = deque(maxlen=4)
    assert append_bounded(queue, {'data': b'y'}, 'audio_bytes', drop_on_full=True) is False
    assert drops.labels.call_count == 0


def test_policy_without_size_of_evicts_and_counts(monkeypatch):
    _outbox(monkeypatch)
    drops, dropped_bytes = _counted_drops(monkeypatch)
    queue = _full_queue(1, [10])
    assert append_bounded(queue, {'data': b'y'}, 'audio_bytes', drop_on_full=True) is True
    assert _drop_calls(drops, 'audio_bytes')
    dropped_bytes.labels.assert_not_called()


def test_policy_return_true_drives_one_warning_per_eviction(monkeypatch, caplog):
    _outbox(monkeypatch)
    budget = ByteBudget(100000)
    queue = deque(maxlen=2)
    with caplog.at_level(logging.WARNING, logger=__name__):
        for index in range(5):
            saturated = append_bounded(
                queue,
                {'data': bytes([index])},
                'audio_bytes',
                byte_budget=budget,
                size_of=lambda i: len(i['data']),
                drop_on_full=True,
            )
            if saturated:
                logger.warning('Dropped oldest audio-app trigger item under queue saturation owner')
    warnings = [record for record in caplog.records if 'Dropped oldest audio-app trigger item' in record.getMessage()]
    assert len(warnings) == 3


def test_policy_maxlen_one_rotates_every_append(monkeypatch):
    _outbox(monkeypatch)
    queue = deque(maxlen=1)
    for index in range(4):
        assert append_bounded(queue, {'data': bytes([index])}, 'audio_bytes', drop_on_full=True) is (index > 0)
    assert queue[0]['data'] == bytes([3])


def test_policy_evicted_item_is_the_previous_head(monkeypatch):
    _outbox(monkeypatch)
    queue = _full_queue(3, [10, 20, 30])
    head = queue[0]
    append_bounded(queue, {'data': b'y'}, 'audio_bytes', drop_on_full=True)
    assert head not in queue


def test_policy_budget_tracks_live_items_only_after_evict_and_append(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(1000)
    queue = deque(maxlen=2)
    for size in (100, 200, 300):
        assert budget.reserve(size)
        append_bounded(
            queue,
            {'data': b'x' * size},
            'audio_bytes',
            byte_budget=budget,
            size_of=lambda i: len(i['data']),
            drop_on_full=True,
        )
    assert budget.used == 500


def test_policy_drop_labels_stay_per_queue_name(monkeypatch):
    _outbox(monkeypatch)
    drops, _ = _counted_drops(monkeypatch)
    first = _full_queue(1, [10])
    second = _full_queue(1, [10])
    append_bounded(first, {'data': b'y'}, 'audio_bytes', drop_on_full=True)
    append_bounded(second, {'data': b'y'}, 'plain', drop_on_full=True)
    assert len(_drop_calls(drops, 'audio_bytes')) == 1
    assert len(_drop_calls(drops, 'plain')) == 1


def test_policy_never_raises_even_without_budget(monkeypatch):
    _outbox(monkeypatch)
    queue = _full_queue(2, [10, 20])
    for index in range(10):
        append_bounded(queue, {'data': bytes([index])}, 'audio_bytes', drop_on_full=True)


def test_policy_zero_size_items_rotate_without_byte_accounting(monkeypatch):
    _outbox(monkeypatch)
    _, dropped_bytes = _counted_drops(monkeypatch)
    queue = deque(maxlen=2)
    for _ in range(4):
        append_bounded(queue, {'data': b''}, 'audio_bytes', size_of=lambda i: 0, drop_on_full=True)
    dropped_bytes.labels.assert_not_called()
    assert len(queue) == 2


def test_policy_eviction_count_equals_overflow_count(monkeypatch):
    _outbox(monkeypatch)
    drops, _ = _counted_drops(monkeypatch)
    queue = deque(maxlen=5)
    for index in range(12):
        append_bounded(queue, {'data': bytes([index])}, 'audio_bytes', drop_on_full=True)
    assert len(_drop_calls(drops, 'audio_bytes')) == 7


def test_policy_leaves_other_queues_untouched(monkeypatch):
    _outbox(monkeypatch)
    other = _full_queue(1, [10])
    custody = _full_queue(1, [10])
    append_bounded(deque(maxlen=1), {'data': b'y'}, 'audio_bytes', drop_on_full=True)
    assert [item['data'] for item in other] == [b'x' * 10]
    with pytest.raises(AudioBackpressure):
        append_bounded(custody, {'data': b'y'}, 'private_cloud')


def test_policy_with_budget_matches_disabled_outbox_behavior(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(100)
    queue = _full_queue(1, [40], budget)
    budget.reserve(5)
    append_bounded(
        queue,
        {'data': b'y' * 5},
        'audio_bytes',
        byte_budget=budget,
        size_of=lambda i: len(i['data']),
        drop_on_full=True,
    )
    assert budget.used == 5
    assert queue[0]['data'] == b'y' * 5


def test_policy_newest_wins_under_continuous_saturation(monkeypatch):
    _outbox(monkeypatch)
    queue = deque(maxlen=3)
    for index in range(9):
        append_bounded(queue, {'data': bytes([index])}, 'audio_bytes', drop_on_full=True)
    assert [item['data'] for item in queue] == [bytes([6]), bytes([7]), bytes([8])]


def test_policy_counter_increments_once_per_eviction(monkeypatch):
    _outbox(monkeypatch)
    drops, _ = _counted_drops(monkeypatch)
    queue = deque(maxlen=2)
    for index in range(6):
        append_bounded(queue, {'data': bytes([index])}, 'audio_bytes', drop_on_full=True)
    assert len(_drop_calls(drops, 'audio_bytes')) == 4


def test_policy_matches_the_legacy_outbox_disabled_eviction_exactly(monkeypatch):
    final_states = []
    for enabled in (True, False):
        _outbox(monkeypatch, enabled)
        queue = deque(maxlen=3)
        for index in range(7):
            append_bounded(queue, {'data': bytes([index])}, 'audio_bytes', drop_on_full=True)
        final_states.append([item['data'] for item in queue])
    assert final_states[0] == final_states[1]


def test_policy_on_unbounded_queue_plain_appends(monkeypatch):
    _outbox(monkeypatch)
    queue = deque()
    for index in range(5):
        assert append_bounded(queue, {'data': bytes([index])}, 'audio_bytes', drop_on_full=True) is False
    assert len(queue) == 5


def test_policy_return_true_exactly_at_overflows_under_mixed_traffic(monkeypatch):
    _outbox(monkeypatch)
    queue = deque(maxlen=2)
    outcomes = [append_bounded(queue, {'data': bytes([index])}, 'audio_bytes', drop_on_full=True) for index in range(6)]
    assert outcomes == [False, False, True, True, True, True]


def test_policy_does_not_touch_the_incoming_reservation(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(1000)
    queue = deque(maxlen=1)
    budget.reserve(50)
    queue.append({'data': b'x' * 50})
    budget.reserve(70)
    append_bounded(
        queue,
        {'data': b'y' * 70},
        'audio_bytes',
        byte_budget=budget,
        size_of=lambda i: len(i['data']),
        drop_on_full=True,
    )
    assert budget.used == 70


def test_policy_eviction_order_independent_of_item_sizes(monkeypatch):
    _outbox(monkeypatch)
    queue = _full_queue(3, [100, 10, 50])
    append_bounded(queue, {'data': b'y'}, 'audio_bytes', drop_on_full=True)
    assert [len(item['data']) for item in queue] == [10, 50, 1]


def test_policy_double_capacity_stream_leaves_the_newest_maxlen(monkeypatch):
    _outbox(monkeypatch)
    queue = deque(maxlen=6)
    for index in range(12):
        append_bounded(queue, {'data': bytes([index])}, 'audio_bytes', drop_on_full=True)
    assert [item['data'] for item in queue] == [bytes([index]) for index in range(6, 12)]


def test_policy_matrix_maxlen1_single_item_stream(monkeypatch):
    _outbox(monkeypatch)
    drops, dropped_bytes = _counted_drops(monkeypatch)
    queue = deque(maxlen=1)
    for _ in range(3):
        append_bounded(queue, {'data': b'x' * 10}, 'audio_bytes', size_of=lambda i: 10, drop_on_full=True)
    assert len(_drop_calls(drops, 'audio_bytes')) == 2
    assert dropped_bytes.labels.return_value.inc.call_count == 2


def test_policy_matrix_maxlen1_three_item_stream(monkeypatch):
    _outbox(monkeypatch)
    queue = deque(maxlen=1)
    for index in range(3):
        append_bounded(queue, {'data': bytes([index])}, 'audio_bytes', drop_on_full=True)
    assert queue[0]['data'] == bytes([2])


def test_policy_matrix_maxlen3_single_item_stream(monkeypatch):
    _outbox(monkeypatch)
    queue = deque(maxlen=3)
    for index in range(5):
        append_bounded(queue, {'data': bytes([index])}, 'audio_bytes', drop_on_full=True)
    assert [item['data'] for item in queue] == [bytes([2]), bytes([3]), bytes([4])]


def test_policy_matrix_maxlen5_two_item_batches(monkeypatch):
    _outbox(monkeypatch)
    queue = deque(maxlen=5)
    for batch in range(4):
        for lane in (0, 1):
            append_bounded(queue, {'data': bytes([batch * 2 + lane])}, 'audio_bytes', drop_on_full=True)
    assert [item['data'] for item in queue] == [bytes([index]) for index in range(3, 8)]


def test_policy_matrix_maxlen2_five_item_stream(monkeypatch):
    _outbox(monkeypatch)
    queue = deque(maxlen=2)
    for index in range(5):
        append_bounded(queue, {'data': bytes([index])}, 'audio_bytes', drop_on_full=True)
    assert [item['data'] for item in queue] == [bytes([3]), bytes([4])]


def test_policy_matrix_maxlen20_three_items_per_burst(monkeypatch):
    _outbox(monkeypatch)
    drops, _ = _counted_drops(monkeypatch)
    queue = deque(maxlen=20)
    for index in range(30):
        append_bounded(queue, {'data': bytes([index])}, 'audio_bytes', drop_on_full=True)
    assert len(queue) == 20
    assert len(_drop_calls(drops, 'audio_bytes')) == 10


# ---------------------------------------------------------------------------
# Part E — extend_bounded custody defaults.
# ---------------------------------------------------------------------------


def test_extend_with_capacity_stores_and_accounts(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(100)
    buffer = bytearray()
    assert extend_bounded(buffer, b'x' * 40, 'audio_app_buffer', budget) is True
    assert bytes(buffer) == b'x' * 40
    assert budget.used == 40


def test_extend_exact_capacity_stores(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(40)
    assert extend_bounded(bytearray(), b'x' * 40, 'audio_app_buffer', budget) is True
    assert budget.used == 40


def test_extend_over_capacity_raises_under_outbox(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(10)
    budget.reserve(10)
    with pytest.raises(AudioBackpressure):
        extend_bounded(bytearray(), b'x' * 5, 'audio_app_buffer', budget)


def test_custody_extend_raise_carries_the_data(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(1)
    data = b'overflow'
    with pytest.raises(AudioBackpressure) as raised:
        extend_bounded(bytearray(), data, 'audio_app_buffer', budget)
    assert raised.value.pending is data


def test_custody_extend_raise_leaves_buffer_untouched(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(1)
    buffer = bytearray()
    with pytest.raises(AudioBackpressure):
        extend_bounded(buffer, b'overflow', 'audio_app_buffer', budget)
    assert buffer == bytearray()


def test_custody_extend_raise_leaves_budget_intact(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(1)
    budget.reserve(1)
    with pytest.raises(AudioBackpressure):
        extend_bounded(bytearray(), b'overflow', 'audio_app_buffer', budget)
    assert budget.used == 1


def test_extend_over_capacity_without_outbox_counts_drop(monkeypatch):
    _outbox(monkeypatch, False)
    drops, _ = _counted_drops(monkeypatch)
    budget = ByteBudget(1)
    budget.reserve(1)
    assert extend_bounded(bytearray(), b'overflow', 'audio_app_buffer', budget) is False
    assert _drop_calls(drops, 'audio_app_buffer')


def test_extend_without_outbox_leaves_buffer_untouched(monkeypatch):
    _outbox(monkeypatch, False)
    budget = ByteBudget(1)
    budget.reserve(1)
    buffer = bytearray()
    assert extend_bounded(buffer, b'overflow', 'audio_app_buffer', budget) is False
    assert buffer == bytearray()


def test_extend_empty_data_stores_trivially(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(1)
    budget.reserve(1)
    assert extend_bounded(bytearray(), b'', 'audio_app_buffer', budget) is True


def test_extend_success_accounts_exactly_the_data(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(100)
    buffer = bytearray()
    extend_bounded(buffer, b'x' * 30, 'audio_app_buffer', budget)
    extend_bounded(buffer, b'y' * 20, 'audio_app_buffer', budget)
    assert budget.used == 50
    assert bytes(buffer) == b'x' * 30 + b'y' * 20


def test_extend_keeps_prior_bytes_on_failed_reserve(monkeypatch):
    _outbox(monkeypatch, False)
    budget = ByteBudget(30)
    buffer = bytearray()
    assert extend_bounded(buffer, b'x' * 30, 'audio_app_buffer', budget)
    assert extend_bounded(buffer, b'y' * 10, 'audio_app_buffer', budget) is False
    assert bytes(buffer) == b'x' * 30


def test_extend_two_buffers_use_their_own_budgets(monkeypatch):
    _outbox(monkeypatch)
    first_budget = ByteBudget(50)
    second_budget = ByteBudget(50)
    assert extend_bounded(bytearray(), b'x' * 50, 'audio_app_buffer', first_budget)
    assert extend_bounded(bytearray(), b'y' * 50, 'audio_webhook_buffer', second_budget)
    assert first_budget.used == 50
    assert second_budget.used == 50


# ---------------------------------------------------------------------------
# Part F — extend_bounded drop_on_full policy.
# ---------------------------------------------------------------------------


def test_policy_extend_overflow_drops_without_raising(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(10)
    budget.reserve(10)
    assert extend_bounded(bytearray(), b'x' * 5, 'audio_app_buffer', budget, drop_on_full=True) is False


def test_policy_extend_drop_counts_the_drop(monkeypatch):
    _outbox(monkeypatch)
    drops, _ = _counted_drops(monkeypatch)
    budget = ByteBudget(1)
    budget.reserve(1)
    extend_bounded(bytearray(), b'overflow', 'audio_app_buffer', budget, drop_on_full=True)
    assert _drop_calls(drops, 'audio_app_buffer')


def test_policy_extend_drop_counts_dropped_bytes(monkeypatch):
    _outbox(monkeypatch)
    _, dropped_bytes = _counted_drops(monkeypatch)
    budget = ByteBudget(1)
    budget.reserve(1)
    extend_bounded(bytearray(), b'overflow', 'audio_app_buffer', budget, drop_on_full=True)
    dropped_bytes.labels.return_value.inc.assert_called_once_with(len(b'overflow'))


def test_policy_extend_drop_leaves_buffer_untouched(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(1)
    budget.reserve(1)
    buffer = bytearray()
    extend_bounded(buffer, b'overflow', 'audio_app_buffer', budget, drop_on_full=True)
    assert buffer == bytearray()


def test_policy_extend_drop_consumes_no_budget(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(1)
    budget.reserve(1)
    extend_bounded(bytearray(), b'overflow', 'audio_app_buffer', budget, drop_on_full=True)
    assert budget.used == 1


def test_policy_extend_smaller_frame_stores_after_a_drop(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(10)
    budget.reserve(10)
    buffer = bytearray()
    assert extend_bounded(buffer, b'x' * 5, 'audio_app_buffer', budget, drop_on_full=True) is False
    budget.release(10)
    assert extend_bounded(buffer, b'y', 'audio_app_buffer', budget, drop_on_full=True) is True
    assert bytes(buffer) == b'y'


def test_policy_extend_success_is_identical_to_default(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(10)
    buffer = bytearray()
    assert extend_bounded(buffer, b'x' * 10, 'audio_app_buffer', budget, drop_on_full=True) is True
    assert bytes(buffer) == b'x' * 10
    assert budget.used == 10


def test_policy_extend_uniform_across_outbox_modes(monkeypatch):
    outcomes = []
    for enabled in (True, False):
        _outbox(monkeypatch, enabled)
        drops, _ = _counted_drops(monkeypatch)
        budget = ByteBudget(1)
        budget.reserve(1)
        buffer = bytearray()
        stored = extend_bounded(buffer, b'overflow', 'audio_app_buffer', budget, drop_on_full=True)
        outcomes.append((stored, bytes(buffer), budget.used, drops.labels.call_count))
    assert outcomes[0] == outcomes[1]


def test_policy_extend_repeated_overflow_never_grows_buffer(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(1)
    budget.reserve(1)
    buffer = bytearray()
    for _ in range(10):
        assert extend_bounded(buffer, b'overflow', 'audio_app_buffer', budget, drop_on_full=True) is False
    assert buffer == bytearray()


def test_policy_extend_exact_fit_stores(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(10)
    assert extend_bounded(bytearray(), b'x' * 10, 'audio_app_buffer', budget, drop_on_full=True) is True


def test_policy_extend_partial_buffer_keeps_its_bytes_on_drop(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(30)
    buffer = bytearray()
    assert extend_bounded(buffer, b'x' * 20, 'audio_app_buffer', budget, drop_on_full=True)
    assert extend_bounded(buffer, b'y' * 20, 'audio_app_buffer', budget, drop_on_full=True) is False
    assert bytes(buffer) == b'x' * 20


def test_policy_extend_zero_size_input_stores(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(1)
    budget.reserve(1)
    assert extend_bounded(bytearray(), b'', 'audio_app_buffer', budget, drop_on_full=True) is True


def test_policy_extend_drop_label_uses_the_buffer_name(monkeypatch):
    _outbox(monkeypatch)
    drops, _ = _counted_drops(monkeypatch)
    budget = ByteBudget(1)
    budget.reserve(1)
    extend_bounded(bytearray(), b'overflow', 'audio_webhook_buffer', budget, drop_on_full=True)
    assert len(_drop_calls(drops, 'audio_webhook_buffer')) == 1


def test_policy_extend_no_raise_for_any_oversize(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(4)
    for _ in range(20):
        extend_bounded(bytearray(), b'x' * 100, 'audio_app_buffer', budget, drop_on_full=True)


def test_policy_extend_recovers_after_consumer_release(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(20)
    budget.reserve(20)
    buffer = bytearray()
    assert extend_bounded(buffer, b'x' * 5, 'audio_app_buffer', budget, drop_on_full=True) is False
    budget.release(20)
    assert extend_bounded(buffer, b'x' * 20, 'audio_app_buffer', budget, drop_on_full=True) is True
    assert budget.used == 20


def test_policy_extend_no_counter_noise_on_success(monkeypatch):
    _outbox(monkeypatch)
    drops, _ = _counted_drops(monkeypatch)
    budget = ByteBudget(10)
    extend_bounded(bytearray(), b'x' * 10, 'audio_app_buffer', budget, drop_on_full=True)
    assert drops.labels.call_count == 0


def test_policy_extend_matrix_partial_then_exact(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(100)
    buffer = bytearray()
    assert extend_bounded(buffer, b'x' * 60, 'audio_app_buffer', budget, drop_on_full=True)
    assert extend_bounded(buffer, b'y' * 60, 'audio_app_buffer', budget, drop_on_full=True) is False
    assert extend_bounded(buffer, b'z' * 40, 'audio_app_buffer', budget, drop_on_full=True) is True
    assert len(buffer) == 100


def test_policy_extend_matrix_tiny_budget_big_input(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(50)
    assert extend_bounded(bytearray(), b'x' * 100, 'audio_app_buffer', budget, drop_on_full=True) is False
    assert budget.used == 0


def test_policy_extend_matrix_zero_budget(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(0)
    assert extend_bounded(bytearray(), b'x', 'audio_app_buffer', budget, drop_on_full=True) is False


def test_policy_extend_matrix_exact_fit(monkeypatch):
    _outbox(monkeypatch)
    budget = ByteBudget(10)
    assert extend_bounded(bytearray(), b'x' * 10, 'audio_app_buffer', budget, drop_on_full=True) is True


# ---------------------------------------------------------------------------
# Part G — session-outcome classification: the terminal semantics the clean
# close rides. Saturation must land in the non-failure outcomes.
# ---------------------------------------------------------------------------


def test_outcome_application_failed_wins():
    assert pusher_session_outcome(1000, application_failed=True) == 'failure'


def test_outcome_plain_1011_is_a_failure():
    assert pusher_session_outcome(1011) == 'failure'


def test_outcome_1011_with_peer_keepalive_is_churn():
    assert pusher_session_outcome(1011, peer_keepalive_timeout=True) == 'cancelled'


def test_outcome_1000_is_success():
    assert pusher_session_outcome(1000) == 'success'


def test_outcome_1001_is_success():
    assert pusher_session_outcome(1001) == 'success'


def test_outcome_1006_is_cancelled():
    assert pusher_session_outcome(1006) == 'cancelled'


def test_outcome_1003_is_cancelled():
    assert pusher_session_outcome(1003) == 'cancelled'


def test_outcome_1013_is_cancelled():
    assert pusher_session_outcome(1013) == 'cancelled'


def test_outcome_unknown_code_is_cancelled():
    assert pusher_session_outcome(1012) == 'cancelled'


def test_outcome_application_failed_overrides_success_code():
    assert pusher_session_outcome(1000, application_failed=True) == 'failure'


def test_outcome_application_failed_overrides_1001():
    assert pusher_session_outcome(1001, application_failed=True) == 'failure'


def test_outcome_application_failed_overrides_1006():
    assert pusher_session_outcome(1006, application_failed=True) == 'failure'


def test_outcome_application_failed_wins_over_keepalive_churn():
    assert pusher_session_outcome(1011, application_failed=True, peer_keepalive_timeout=True) == 'failure'


def test_outcome_keepalive_flag_ignored_on_clean_code():
    assert pusher_session_outcome(1000, peer_keepalive_timeout=True) == 'success'


def test_outcome_keepalive_flag_ignored_on_1006():
    assert pusher_session_outcome(1006, peer_keepalive_timeout=True) == 'cancelled'


def test_outcome_keepalive_flag_ignored_on_1001():
    assert pusher_session_outcome(1001, peer_keepalive_timeout=True) == 'success'


# ---------------------------------------------------------------------------
# Part H — the constants, defaults and isolation primitives the choreography
# and the custody strictness rely on.
# ---------------------------------------------------------------------------


def test_buffered_audio_budget_is_20mib():
    assert BUFFERED_AUDIO_MAX_BYTES == 20 * 1024 * 1024


def test_audio_bytes_queue_bound_is_20():
    assert pusher.AUDIO_BYTES_QUEUE_WARN_SIZE == 20


def test_budget_isolation_exhausted_budget_leaves_the_other_intact():
    trigger = ByteBudget(BUFFERED_AUDIO_MAX_BYTES)
    capture = ByteBudget(BUFFERED_AUDIO_MAX_BYTES)
    assert trigger.reserve(BUFFERED_AUDIO_MAX_BYTES)
    assert capture.reserve(BUFFERED_AUDIO_MAX_BYTES)


def test_budget_isolation_release_on_one_keeps_the_other():
    trigger = ByteBudget(100)
    capture = ByteBudget(100)
    trigger.reserve(100)
    capture.reserve(100)
    trigger.release(100)
    assert capture.used == 100


def test_extend_custody_gate_defaults_on_without_env(monkeypatch):
    monkeypatch.delenv('AUDIO_DURABLE_OUTBOX_ENABLED', raising=False)
    budget = ByteBudget(1)
    budget.reserve(1)
    with pytest.raises(AudioBackpressure):
        extend_bounded(bytearray(), b'overflow', 'audio_app_buffer', budget)


def test_append_policy_flag_defaults_to_custody_semantics():
    assert inspect.signature(append_bounded).parameters['drop_on_full'].default is False


def test_extend_policy_flag_defaults_to_custody_semantics():
    assert inspect.signature(extend_bounded).parameters['drop_on_full'].default is False


def test_handler_budgets_are_sized_from_the_shared_limit_constant():
    assert pusher.BUFFERED_AUDIO_MAX_BYTES is BUFFERED_AUDIO_MAX_BYTES


# ---------------------------------------------------------------------------
# Part I — the two trigger lanes share one budget: interleaved accounting.
# ---------------------------------------------------------------------------


def test_shared_lane_budget_tracks_both_lanes(monkeypatch):
    _outbox(monkeypatch)
    trigger_budget = ByteBudget(1000)
    assert extend_bounded(bytearray(), b'a' * 300, 'audio_app_buffer', trigger_budget, drop_on_full=True)
    assert extend_bounded(bytearray(), b'w' * 200, 'audio_webhook_buffer', trigger_budget, drop_on_full=True)
    assert trigger_budget.used == 500


def test_shared_lane_eviction_releases_whichever_item_is_evicted(monkeypatch):
    _outbox(monkeypatch)
    trigger_budget = ByteBudget(1000)
    queue = deque(maxlen=1)
    assert extend_bounded(bytearray(), b'a' * 300, 'audio_app_buffer', trigger_budget, drop_on_full=True)
    append_bounded(
        queue,
        {'data': b'a' * 300},
        'audio_bytes',
        byte_budget=trigger_budget,
        size_of=lambda i: len(i['data']),
        drop_on_full=True,
    )
    assert extend_bounded(bytearray(), b'w' * 200, 'audio_webhook_buffer', trigger_budget, drop_on_full=True)
    append_bounded(
        queue,
        {'data': b'w' * 200},
        'audio_bytes',
        byte_budget=trigger_budget,
        size_of=lambda i: len(i['data']),
        drop_on_full=True,
    )
    assert trigger_budget.used == 200


def test_shared_lane_release_order_independent():
    trigger_budget = ByteBudget(1000)
    trigger_budget.reserve(300)
    trigger_budget.reserve(200)
    trigger_budget.release(200)
    assert trigger_budget.used == 300
    trigger_budget.release(300)
    assert trigger_budget.used == 0


def test_shared_lane_exhaustion_drops_only_the_newest_input(monkeypatch):
    _outbox(monkeypatch)
    trigger_budget = ByteBudget(500)
    assert extend_bounded(bytearray(), b'a' * 400, 'audio_app_buffer', trigger_budget, drop_on_full=True)
    assert extend_bounded(bytearray(), b'w' * 200, 'audio_webhook_buffer', trigger_budget, drop_on_full=True) is False
    assert trigger_budget.used == 400


def test_shared_queue_mixed_lane_items_evict_in_fifo_order(monkeypatch):
    _outbox(monkeypatch)
    queue = deque(maxlen=2)
    append_bounded(queue, {'data': b'a', 'lane': 'app'}, 'audio_bytes', drop_on_full=True)
    append_bounded(queue, {'data': b'w', 'lane': 'webhook'}, 'audio_bytes', drop_on_full=True)
    append_bounded(queue, {'data': b'a2', 'lane': 'app'}, 'audio_bytes', drop_on_full=True)
    assert [item['lane'] for item in queue] == ['webhook', 'app']


def test_shared_lane_budget_drains_to_zero_after_both_consumers_release(monkeypatch):
    _outbox(monkeypatch)
    trigger_budget = ByteBudget(1000)
    queue = deque(maxlen=4)
    for size in (300, 200):
        assert extend_bounded(bytearray(), b'x' * size, 'audio_app_buffer', trigger_budget, drop_on_full=True)
        append_bounded(
            queue,
            {'data': b'x' * size},
            'audio_bytes',
            byte_budget=trigger_budget,
            size_of=lambda i: len(i['data']),
            drop_on_full=True,
        )
    for item in list(queue):
        trigger_budget.release(len(item['data']))
    assert trigger_budget.used == 0


# ---------------------------------------------------------------------------
# Part J — handler-level saturation choreography on the durable custody
# harness. The saturated-lane tests are the regression: the parent code
# killed the session 1011 at the overflow frame; the fixed code commits every
# frame and ends the session clean.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_saturated_app_trigger_lane_keeps_the_session_and_every_custody_byte(remote, monkeypatch):
    payloads = [_payload(index) for index in range(22)]
    sock, processed, journeys, drops, _ = await _stalled_lane_session(
        monkeypatch, payloads=payloads, app_enabled=True, expected_processed=21
    )

    assert sock.close_code == 1000
    assert 'failure' not in [call.args[0] for call in journeys[0].finish.call_args_list]
    receipts = _custody_receipts(sock)
    assert len(receipts) == 22
    assert [read_pcm('owner', receipt) for receipt in receipts] == payloads
    assert processed == [len(payloads[0])] + [len(payload) for payload in payloads[2:]]
    assert len(_drop_calls(drops, 'audio_bytes')) == 1


@pytest.mark.asyncio
async def test_saturated_webhook_lane_keeps_the_session_and_every_custody_byte(remote, monkeypatch):
    payloads = [_payload(index) for index in range(22)]
    sock, processed, journeys, drops, _ = await _stalled_lane_session(
        monkeypatch, payloads=payloads, app_enabled=False, webhook_delay=4.0, expected_processed=21
    )

    assert sock.close_code == 1000
    assert 'failure' not in [call.args[0] for call in journeys[0].finish.call_args_list]
    receipts = _custody_receipts(sock)
    assert len(receipts) == 22
    assert [read_pcm('owner', receipt) for receipt in receipts] == payloads
    assert processed == [len(payloads[0])] + [len(payload) for payload in payloads[2:]]
    assert len(_drop_calls(drops, 'audio_bytes')) == 1


@pytest.mark.asyncio
async def test_saturated_both_trigger_lanes_keep_the_session_and_every_custody_byte(remote, monkeypatch):
    payloads = [_payload(index) for index in range(22)]
    sock, processed, journeys, drops, _ = await _stalled_lane_session(
        monkeypatch, payloads=payloads, app_enabled=True, webhook_delay=4.0, expected_processed=22
    )

    assert sock.close_code == 1000
    assert 'failure' not in [call.args[0] for call in journeys[0].finish.call_args_list]
    receipts = _custody_receipts(sock)
    assert len(receipts) == 22
    assert [read_pcm('owner', receipt) for receipt in receipts] == payloads
    # Two flushes per frame: 44 appends against a 20-slot queue, two items
    # held by the consumer, so 22 appends evicted their oldest predecessor.
    assert len(processed) == 22
    assert len(_drop_calls(drops, 'audio_bytes')) == 22


@pytest.mark.asyncio
async def test_lane_recovers_after_saturation_and_accepts_new_frames(remote, monkeypatch):
    payloads = [_payload(index) for index in range(22)]
    extra = [_payload(30 + index) for index in range(8)]
    sock, processed, journeys, drops, _ = await _stalled_lane_session(
        monkeypatch,
        payloads=payloads,
        app_enabled=True,
        extra_payloads=extra,
        release_after=22,
        release_drain_to=21,
        expected_processed=29,
    )

    assert sock.close_code == 1000
    assert 'failure' not in [call.args[0] for call in journeys[0].finish.call_args_list]
    receipts = _custody_receipts(sock)
    assert len(receipts) == 30
    # Exactly the one eviction from the stalled phase: after the consumer
    # drained, the lane accepted every following frame without further drops.
    assert len(_drop_calls(drops, 'audio_bytes')) == 1
    assert processed == [len(payloads[0])] + [len(payload) for payload in payloads[2:]] + [len(p) for p in extra]


@pytest.mark.asyncio
async def test_trigger_buffer_exhaustion_drops_the_frame_not_the_session(remote, monkeypatch):
    payloads = [_payload(index) for index in range(3)]
    sock, processed, journeys, drops, _ = await _stalled_lane_session(
        monkeypatch,
        payloads=payloads,
        app_enabled=True,
        sync_enabled=False,
        trigger_budget_limit=300000,
        expected_processed=2,
    )

    assert sock.close_code == 1000
    assert 'failure' not in [call.args[0] for call in journeys[0].finish.call_args_list]
    # Two items fit the 300000 B trigger budget while the consumer holds the
    # first; the third frame's buffer reserve failed and was dropped as the
    # lane's own degradation.
    assert processed == [len(payloads[0]), len(payloads[1])]
    assert len(_drop_calls(drops, 'audio_app_buffer')) == 1
    assert sock.sent == []


@pytest.mark.asyncio
async def test_webhook_buffer_exhaustion_drops_the_frame_not_the_session(remote, monkeypatch):
    payloads = [_payload(index) for index in range(3)]
    sock, processed, journeys, drops, _ = await _stalled_lane_session(
        monkeypatch,
        payloads=payloads,
        app_enabled=False,
        webhook_delay=4.0,
        sync_enabled=False,
        trigger_budget_limit=300000,
        expected_processed=2,
    )

    assert sock.close_code == 1000
    assert 'failure' not in [call.args[0] for call in journeys[0].finish.call_args_list]
    assert processed == [len(payloads[0]), len(payloads[1])]
    assert len(_drop_calls(drops, 'audio_webhook_buffer')) == 1


@pytest.mark.asyncio
async def test_capture_and_trigger_budgets_are_distinct_instances(remote, monkeypatch):
    instances = _spy_budgets(monkeypatch)
    _outbox(monkeypatch)
    _admit(monkeypatch, app=True)
    sock = Socket(_audio_frames('conversation', [_payload(0)]))
    monkeypatch.setattr(pusher, 'trigger_realtime_audio_bytes', _noop_consumer())
    monkeypatch.setattr(pusher, 'send_audio_bytes_developer_webhook', _noop_consumer())
    await asyncio.wait_for(pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1), timeout=30)

    assert len(instances) == 2
    assert instances[0] is not instances[1]


@pytest.mark.asyncio
async def test_both_budgets_drain_after_a_saturated_session(remote, monkeypatch):
    instances = _spy_budgets(monkeypatch)
    payloads = [_payload(index) for index in range(22)]
    _outbox(monkeypatch)
    _admit(monkeypatch, app=True)
    sock = Socket(_audio_frames('conversation', payloads))
    release = asyncio.Event()
    armed = asyncio.Event()

    async def stalled_consumer(uid, sample_rate, data):
        armed.set()
        await asyncio.wait_for(release.wait(), timeout=10)

    monkeypatch.setattr(pusher, 'trigger_realtime_audio_bytes', stalled_consumer)
    task = asyncio.create_task(pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1))
    await asyncio.wait_for(armed.wait(), timeout=10)
    release.set()
    await asyncio.wait_for(task, timeout=30)

    capture, trigger = instances
    assert capture is not trigger
    assert trigger.used == 0
    # Custody bookkeeping may hold at most one in-flight window at this point.
    assert capture.used <= FRAME_BYTES


@pytest.mark.asyncio
async def test_capture_budget_stays_empty_while_the_trigger_lane_is_saturated(remote, monkeypatch):
    instances = _spy_budgets(monkeypatch)
    payloads = [_payload(index) for index in range(22)]
    _outbox(monkeypatch)
    _admit(monkeypatch, app=True)

    frames = _audio_frames('conversation', payloads)
    sock = Socket(frames)
    release = asyncio.Event()
    armed = asyncio.Event()
    advance = asyncio.Event()
    tail_gate = asyncio.Event()
    state = {'delivered': 0}

    async def stalled_consumer(uid, sample_rate, data):
        armed.set()
        await asyncio.wait_for(release.wait(), timeout=10)

    monkeypatch.setattr(pusher, 'trigger_realtime_audio_bytes', stalled_consumer)
    real_receive = sock.receive_bytes

    async def paced_receive():
        if 2 <= state['delivered'] < len(frames):
            await asyncio.wait_for(advance.wait(), timeout=10)
            advance.clear()
        if state['delivered'] >= len(frames):
            await asyncio.wait_for(tail_gate.wait(), timeout=10)
        frame = await real_receive()
        state['delivered'] += 1
        return frame

    monkeypatch.setattr(sock, 'receive_bytes', paced_receive)
    task = asyncio.create_task(pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1))
    await asyncio.wait_for(armed.wait(), timeout=10)
    delivered = state['delivered']
    for _ in range(len(frames) - 2):
        advance.set()
        while state['delivered'] == delivered and not task.done():
            await asyncio.sleep(0)
        delivered = state['delivered']
        # Freeze the queue state at every gate: wait for the frame's custody
        # receipt (its flush) before advancing, so the mid-stream accounting
        # assertion below sees the settled trigger queue.
        while len(_custody_receipts(sock)) < delivered - 1 and not task.done():
            await asyncio.sleep(0)

    capture, trigger = instances
    # Mid-stream: the consumer holds the first item's reservation and the
    # trigger queue holds its 20-slot fill; the capture budget carries at most
    # a few in-flight custody windows — never the trigger bytes.
    assert trigger.used == 21 * FRAME_BYTES
    assert capture.used < trigger.used

    release.set()
    tail_gate.set()
    await asyncio.wait_for(task, timeout=30)
    assert trigger.used == 0


@pytest.mark.asyncio
async def test_trigger_buffer_drop_logs_the_uid(remote, monkeypatch, caplog):
    payloads = [_payload(index) for index in range(3)]
    with caplog.at_level(logging.WARNING, logger='routers.pusher'):
        sock, _, _, _, _ = await _stalled_lane_session(
            monkeypatch,
            payloads=payloads,
            app_enabled=True,
            sync_enabled=False,
            trigger_budget_limit=300000,
            expected_processed=2,
        )
    assert sock.close_code == 1000
    warnings = [record for record in caplog.records if 'Dropped audio-app trigger bytes' in record.getMessage()]
    assert len(warnings) == 1
    assert 'owner' in warnings[0].getMessage()


@pytest.mark.asyncio
async def test_webhook_buffer_drop_logs_the_uid(remote, monkeypatch, caplog):
    payloads = [_payload(index) for index in range(3)]
    with caplog.at_level(logging.WARNING, logger='routers.pusher'):
        sock, _, _, _, _ = await _stalled_lane_session(
            monkeypatch,
            payloads=payloads,
            app_enabled=False,
            webhook_delay=4.0,
            sync_enabled=False,
            trigger_budget_limit=300000,
            expected_processed=2,
        )
    assert sock.close_code == 1000
    warnings = [record for record in caplog.records if 'Dropped webhook trigger bytes' in record.getMessage()]
    assert len(warnings) == 1
    assert 'owner' in warnings[0].getMessage()


@pytest.mark.asyncio
async def test_queue_eviction_logs_the_uid_once_per_eviction(remote, monkeypatch, caplog):
    payloads = [_payload(index) for index in range(22)]
    with caplog.at_level(logging.WARNING, logger='routers.pusher'):
        sock, _, _, _, _ = await _stalled_lane_session(
            monkeypatch, payloads=payloads, app_enabled=True, expected_processed=21
        )
    assert sock.close_code == 1000
    warnings = [record for record in caplog.records if 'Dropped oldest audio-app trigger item' in record.getMessage()]
    assert len(warnings) == 1
    assert 'owner' in warnings[0].getMessage()


@pytest.mark.asyncio
async def test_outbox_disabled_session_saturates_with_the_same_clean_outcome(remote, monkeypatch):
    payloads = [_payload(index) for index in range(22)]
    sock, processed, journeys, drops, _ = await _stalled_lane_session(
        monkeypatch, payloads=payloads, app_enabled=True, outbox=False
    )

    assert sock.close_code == 1000
    assert 'failure' not in [call.args[0] for call in journeys[0].finish.call_args_list]
    # The legacy (outbox-disabled) mode has no custody receipts to freeze the
    # queue state per gate, so the single overflow eviction may land before or
    # after the consumer drains: the lane loses at most that one item.
    assert 21 <= len(processed) <= 22
    assert len(_drop_calls(drops, 'audio_bytes')) <= 1


@pytest.mark.asyncio
async def test_session_without_consumers_books_no_trigger_traffic(remote, monkeypatch):
    instances = _spy_budgets(monkeypatch)
    payloads = [_payload(index) for index in range(5)]
    _outbox(monkeypatch)
    _admit(monkeypatch, app=False, webhook=None)
    drops, _ = _counted_drops(monkeypatch)
    monkeypatch.setattr(pusher, 'trigger_realtime_audio_bytes', _noop_consumer())
    monkeypatch.setattr(pusher, 'send_audio_bytes_developer_webhook', _noop_consumer())
    sock = Socket(_audio_frames('conversation', payloads))
    await asyncio.wait_for(pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1), timeout=30)

    _, trigger = instances
    assert trigger.used == 0
    assert drops.labels.call_count == 0
    assert len(_custody_receipts(sock)) == 5
    assert sock.close_code == 1000


@pytest.mark.asyncio
async def test_below_threshold_frames_stay_buffered_without_queue_items(remote, monkeypatch):
    payloads = [b'\x01\x00' * 30000, b'\x02\x00' * 30000]
    _outbox(monkeypatch)
    _admit(monkeypatch, app=True)
    _journeys(monkeypatch)
    processed = []
    consumer = _noop_consumer(processed)
    monkeypatch.setattr(pusher, 'trigger_realtime_audio_bytes', consumer)
    monkeypatch.setattr(pusher, 'send_audio_bytes_developer_webhook', consumer)
    sock = Socket(_audio_frames('conversation', payloads))
    await asyncio.wait_for(pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1), timeout=30)

    assert processed == []
    assert len(_custody_receipts(sock)) == 2
    assert sock.close_code == 1000


@pytest.mark.asyncio
async def test_threshold_crossing_flushes_one_item_of_exact_buffered_size(remote, monkeypatch):
    payloads = [b'\x01\x00' * 35000, b'\x02\x00' * 35000]
    _outbox(monkeypatch)
    _admit(monkeypatch, app=True)
    _journeys(monkeypatch)
    processed = []
    consumer = _noop_consumer(processed)
    monkeypatch.setattr(pusher, 'trigger_realtime_audio_bytes', consumer)
    monkeypatch.setattr(pusher, 'send_audio_bytes_developer_webhook', consumer)
    sock = Socket(_audio_frames('conversation', payloads))
    await asyncio.wait_for(pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1), timeout=30)

    assert processed == [70000 * 2]
    assert len(_custody_receipts(sock)) == 2
    assert sock.close_code == 1000


@pytest.mark.asyncio
async def test_webhook_only_lane_prices_and_drains_the_shared_trigger_budget(remote, monkeypatch):
    instances = _spy_budgets(monkeypatch)
    payloads = [_payload(index) for index in range(3)]
    _outbox(monkeypatch)
    _admit(monkeypatch, app=False, webhook=4.0)
    app_calls = []
    webhook_calls = []
    monkeypatch.setattr(pusher, 'trigger_realtime_audio_bytes', _noop_consumer(app_calls))
    monkeypatch.setattr(pusher, 'send_audio_bytes_developer_webhook', _noop_consumer(webhook_calls))
    sock = Socket(_audio_frames('conversation', payloads))
    await asyncio.wait_for(pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1), timeout=30)

    _, trigger = instances
    assert app_calls == []
    assert webhook_calls == [FRAME_BYTES] * 3
    assert trigger.used == 0
    assert sock.close_code == 1000
