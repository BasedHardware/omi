"""Provider-pair acceptance: real managed legs/receiver/send loops, synthetic PCM."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.unit.test_parakeet_window_live import runtime, receiver, Client  # noqa: F401
from tests.unit.test_live_cost_router import controls  # noqa: F401
from config.live_stt_replay import ReplayLimits
from routers.listen.receiver import ListenReceiver
from utils.stt import (
    parakeet_window as window,
    streaming as st,
    live_session,
    live_chain,
    recovery_state,
    replay_delivery,
)
from utils.metrics import OMI_FALLBACK_TOTAL
from utils.stt.live_failure import PendingLiveFailover, live_stt_terminal_reason, settle_terminal_socket
from utils.stt.live_gate import GateState
from utils.stt.live_metrics import REPLAY_AUDIO, REPLAY_CLOSED, REPLAY_SKIPPED
from utils.stt.live_signal import provider_observation
from utils.stt.replay_delivery import ReplayTailSocket, replay_packets
from utils.stt.resilient_stream import ResilientAudio, replay_chunks, socket_is_finishing
from utils.stt.send_queue import AudioSendQueue
from utils.stt.soniox import SafeSonioxSocket
from utils.stt.streaming import SafeModulateSocket


from tests.unit.fixtures.replay_clock import virtual_clock  # noqa: F401


@pytest.fixture(autouse=True)
def _stt_failover_recovery_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')


class Transport:
    def __init__(self, fail_after=None):
        self.sent = []
        self.byte_count = 0
        self.inbound = asyncio.Queue()
        self.fail_after = fail_after
        self.on_send = lambda: None
        self.closed = False
        self.timer = None
        self.sent_at = []
        self.gate = asyncio.Event()
        self.gate.set()

    async def send(self, data):
        await self.gate.wait()
        if self.fail_after is not None and len(self.sent) >= self.fail_after:
            raise OSError('synthetic transport failure')
        if self.timer is not None and isinstance(data, bytes):
            await self.timer.sleep(0.020)
        self.sent.append(data)
        self.sent_at.append(self.timer.now if self.timer is not None else 0.0)
        if isinstance(data, bytes):
            self.byte_count += len(data)
        self.on_send()
        if data == '':
            self.inbound.put_nowait('{"finished":true,"type":"done"}')

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.inbound.get()

    async def close(self):
        self.closed = True

    @property
    def pcm(self):
        return b''.join(frame for frame in self.sent if isinstance(frame, bytes))


async def stop(raws):
    tasks = []
    for raw in raws:
        for task in (raw._send_task, raw._recv_task):
            task.cancel()
            tasks.append(task)
    await asyncio.gather(*tasks, return_exceptions=True)


async def until(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(0)


def full_ring():
    ring = ResilientAudio(16000, ring_seconds=135, strict_replay=True)
    for n in range(4500):
        ring.append((n + 1).to_bytes(2, 'little') * 480, n * 480)
    return ring


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', [SafeSonioxSocket, SafeModulateSocket])
async def test_old_unyielding_replay_overflows_both_real_provider_queues(kind):
    raw = kind(Transport(), lambda _: None, asyncio.get_running_loop())
    try:
        accepted = 0
        for _, chunk in full_ring().snapshot():
            if not raw.send(chunk):
                break
            accepted += 1
        assert accepted == 2000
        assert raw.is_connection_dead and raw.typed_death_reason == 'capacity_full'
    finally:
        await stop([raw])


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', [SafeSonioxSocket, SafeModulateSocket])
async def test_full_replay_backpressures_small_real_queue_without_drop(kind):
    transport = Transport()
    raw = kind(transport, lambda _: None, asyncio.get_running_loop())
    raw._send_queue = AudioSendQueue(maxsize=2)
    raw.replay_send = lambda data, start: raw.send(data)
    transport.gate.clear()
    ring = full_ring()
    expected = b''.join(data for _, data in ring.snapshot())
    task = asyncio.create_task(replay_chunks(raw, ring.snapshot(), source=ring, provider='parakeet', soniox=None))
    try:
        await until(lambda: raw._send_queue.qsize() + raw._send_queue.inflight >= raw._send_queue.maxsize)
        assert not task.done() and not raw.is_connection_dead
        transport.gate.set()
        assert await task is None
        await until(lambda: transport.byte_count == len(expected))
        assert transport.pcm == expected
        assert not raw.is_connection_dead
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await stop([raw])


def fallback_count():
    return sum(
        sample.value
        for metric in OMI_FALLBACK_TOTAL.collect()
        for sample in metric.samples
        if sample.name.endswith('_total') and sample.labels.get('component') == 'stt_live_session'
    )


async def setup_receiver(monkeypatch, order, *, fail_first=False, router_on=False, source=None):
    if router_on:
        monkeypatch.setenv('STT_ROUTING_MODE', 'on')
        monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
        live_session.health._cost_local[('modulate-velma-2', 'all')] = GateState(
            stage=0, until=live_session.health._clock() + 300, generation=1
        )

    monkeypatch.setattr(st, 'stt_service_models', order)
    monkeypatch.setattr(window, 'get_stt_client', lambda: Client())
    base = receiver()
    base.fallback_before = fallback_count()
    host = base.host
    if source is not None and source != 'parakeet-window':
        host.stt_model = source
        host.stt_service = st.STTService.soniox if source == 'soniox' else st.STTService.modulate
    host.request.sample_rate = 16000
    host.request.websocket = SimpleNamespace(send_json=AsyncMock(), close=AsyncMock())
    host.state.stt_terminal_failure = False
    host.state.fair_use_dg_budget_exhausted = False
    host.state.fair_use_track_dg_usage = False
    host.state.dg_usage_ms_pending = 0
    host.client_device_context = SimpleNamespace(platform='ios')
    host.transcripts = SimpleNamespace(enqueue=base.emitted.extend)
    host.spawn = lambda coro, **kw: (
        coro.close() if kw.get('name') == 'stt_death_monitor' else asyncio.create_task(coro, name=kw.get('name'))
    )
    raws = []
    legs = []
    observations = []
    monkeypatch.setattr(
        live_session.health, 'record_session', lambda *args, **kwargs: observations.append(args) or True
    )

    def factory(kind):
        async def connect(callback, *args, **kwargs):
            raw = kind(
                Transport(fail_after=2 if fail_first and not raws else None), callback, asyncio.get_running_loop()
            )
            raws.append(raw)
            return raw

        return connect

    monkeypatch.setattr(st, 'process_audio_soniox', factory(SafeSonioxSocket))
    monkeypatch.setattr(st, 'process_audio_modulate', factory(SafeModulateSocket))
    actual = ListenReceiver(host, [], {})
    monkeypatch.setattr(actual, '_run_on_listen_loop', lambda callback, segments: callback(segments))
    original_create = actual._create_stt_socket

    async def create(*args, **kwargs):
        leg = await original_create(*args, **kwargs)
        if leg is not None:
            legs.append(leg)
        return leg

    monkeypatch.setattr(actual, '_create_stt_socket', create)
    assert await actual.initialize_stt()
    ring = full_ring()
    # Populate capture, not provider input: a full retained backlog before failover.
    actual._window_replay_audio = ring
    ring._base_ring_seconds = 90
    actual.capture_timeline.accept(b''.join(data for _, data in ring.snapshot()), 1000, 1)
    return actual, base, raws, legs, observations


@pytest.mark.asyncio
@pytest.mark.parametrize('successor,router_on', [('soniox', False), ('modulate-velma-2', False), ('soniox', True)])
async def test_parakeet_full_135s_replay_then_live_audio_order_and_settlement(monkeypatch, successor, router_on):

    monkeypatch.setattr(replay_delivery, 'REPLAY_PREFIX_SECONDS', 150.0)
    monkeypatch.setattr(replay_delivery, 'TAIL_RESIDENCE_SECONDS', 200.0)
    monkeypatch.setattr(recovery_state, 'RECOVERY_EPISODE_SECONDS', 200.0)
    order = ['parakeet-window', 'modulate-velma-2', 'soniox'] if router_on else ['parakeet-window', successor]
    actual, base, raws, legs, observations = await setup_receiver(monkeypatch, order, router_on=router_on)
    source = actual.stt_socket
    source.raw.fail('first_text_deadline')
    expected = b''.join(data for _, data in actual._window_ring().snapshot())
    try:
        failover = asyncio.create_task(actual._failover_stt_socket())
        await until(lambda: bool(raws))
        assert not failover.done()
        # Newly captured audio must remain after the replay prefix, including at capacity.
        tail = b'\x23\x01' * 480
        start = len(expected) // 2
        actual.capture_timeline.accept(tail, 1135, 136)
        actual._stt_buffer_start_sample = start
        monkeypatch.setattr(actual, '_capture', lambda *args, **kwargs: None)
        buffer = bytearray(tail)
        await actual._flush_stt_buffer(buffer, force=True)
        assert buffer == b''
        assert await failover
        successor_leg = actual.stt_socket
        assert source.leg_outcome.claimed and not successor_leg.is_connection_dead
        assert isinstance(raws[-1], SafeSonioxSocket if successor == 'soniox' else SafeModulateSocket)
        await until(lambda: raws[-1]._ws.byte_count == len(expected) + len(tail))
        assert raws[-1]._ws.pcm == expected + tail
        raws[-1]._stream_transcript([{'text': 'synthetic', 'start': 0, 'end': 135.03, 'speaker': 'speaker_0'}])
        assert len(base.emitted) == 1
        assert source.leg_outcome.settled
        assert source.retired_for_replay
        successor_leg.finish()
        successor_leg.finish()
        assert all(leg.leg_outcome.settled for leg in legs), [
            (
                leg.service.value,
                leg.leg_outcome.claimed,
                leg.leg_outcome.settled,
                leg.leg_outcome.reason,
                leg.leg_outcome.owner_closing,
            )
            for leg in legs
        ]
        assert len(observations) == len(legs) == 2
        assert fallback_count() - base.fallback_before == 1
        assert actual._window_ring().ring_seconds <= 150
    finally:
        actual.stt_socket.finish()
        await stop(raws)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'order',
    [
        ['parakeet-window', 'soniox', 'modulate-velma-2'],
        ['parakeet-window', 'modulate-velma-2', 'soniox'],
    ],
)
async def test_successor_dies_mid_replay_walks_to_next_provider(monkeypatch, order):

    monkeypatch.setattr(replay_delivery, 'REPLAY_PREFIX_SECONDS', 150.0)
    monkeypatch.setattr(recovery_state, 'RECOVERY_EPISODE_SECONDS', 200.0)

    first_family = 'soniox' if order[1] == 'soniox' else 'modulate'
    closed_before = REPLAY_CLOSED.labels(source='parakeet', successor=first_family)._value.get()
    actual, base, raws, legs, observations = await setup_receiver(monkeypatch, order, fail_first=True)
    actual.stt_socket.raw.fail('first_text_deadline')
    expected = b''.join(data for _, data in actual._window_ring().snapshot())
    try:
        assert await actual._failover_stt_socket()
        assert len(raws) == 2 and len(legs) == 3
        assert not actual.stt_socket.is_connection_dead
        await until(lambda: raws[-1]._ws.byte_count == len(expected))
        assert raws[-1]._ws.pcm == expected
        raws[-1]._stream_transcript([{'text': 'synthetic', 'start': 0, 'end': 135, 'speaker': 'speaker_0'}])
        # A late callback from the failed replay leg cannot duplicate text.
        raws[0]._stream_transcript([{'text': 'synthetic', 'start': 0, 'end': 1, 'speaker': 'speaker_0'}])
        assert len(base.emitted) == 1
        assert len(actual._stt_failed_providers) == 2
        assert not actual.host.state.stt_terminal_failure
        assert REPLAY_CLOSED.labels(source='parakeet', successor=first_family)._value.get() == closed_before + 1
        assert raws[0]._ws.closed and raws[0]._send_task.done() and raws[0]._recv_task.done()
        actual.stt_socket.finish()
        for leg in legs:
            leg.finish()
            assert leg.leg_outcome.settled
        assert len(observations) == len(legs)
        assert fallback_count() - base.fallback_before == 2
    finally:
        actual.stt_socket.finish()
        await stop(raws)


@pytest.mark.asyncio
async def test_managed_soniox_internal_finish_still_fails_over(monkeypatch):

    monkeypatch.setattr(recovery_state, 'RECOVERY_EPISODE_SECONDS', 300.0)
    actual, _, raws, legs, _ = await setup_receiver(monkeypatch, ['parakeet-window', 'soniox', 'modulate-velma-2'])
    actual.stt_socket.raw.fail('first_text_deadline')
    try:
        assert await actual._failover_stt_socket()
        soniox = actual.stt_socket
        while not soniox.raw._send_queue.full():
            soniox.raw._send_queue.put_nowait(b'\x01\x00')
        assert not soniox.send(b'\x01\x00' * 480)
        assert soniox.normalized_death_reason == 'capacity_full'
        assert soniox.raw._finishing
        assert not socket_is_finishing(soniox)
        assert await actual._failover_stt_socket()
        assert actual.host.stt_service == st.STTService.modulate
        assert raws[0]._ws.closed and raws[0]._send_task.done() and raws[0]._recv_task.done()
        actual.stt_socket.mark_owner_teardown()
        assert socket_is_finishing(actual.stt_socket)
        assert not await actual._failover_stt_socket()
    finally:
        for leg in legs:
            leg.finish()
        await stop(raws)


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel', [False, True])
async def test_replay_teardown_closes_unadopted_leg_once(monkeypatch, cancel):
    actual, _, raws, legs, observations = await setup_receiver(monkeypatch, ['parakeet-window', 'soniox'])
    actual.stt_socket.raw.fail('first_text_deadline')
    entered = asyncio.Event()
    released = asyncio.Event()
    original = live_session.LiveLegSocket.wait_send_capacity

    async def wait(leg):
        entered.set()
        await released.wait()
        return await original(leg)

    monkeypatch.setattr(live_session.LiveLegSocket, 'wait_send_capacity', wait)
    task = asyncio.create_task(actual._failover_stt_socket())
    try:
        await entered.wait()
        if cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            actual.host.state.active = False
            actual.stt_socket.mark_owner_teardown()
            released.set()
            assert not await task
        assert len(legs) == 2
        assert all(leg.leg_outcome.settled for leg in legs), [
            (
                leg.service.value,
                leg.leg_outcome.claimed,
                leg.leg_outcome.settled,
                leg.leg_outcome.reason,
                leg.leg_outcome.owner_closing,
            )
            for leg in legs
        ]
        assert legs[-1].leg_outcome.owner_closing
        assert len(observations) == 2
        assert raws[-1]._send_task.done() and raws[-1]._recv_task.done()
        assert raws[-1]._ws.closed
    finally:
        released.set()
        for leg in legs:
            leg.finish()
        await stop(raws)


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', [SafeSonioxSocket, SafeModulateSocket])
async def test_stalled_replay_queue_rejects_with_bounded_capacity_cause(monkeypatch, kind):
    raw = kind(Transport(), lambda _: None, asyncio.get_running_loop())
    assert raw.replay_limits.queue_wait_seconds == 2.0 and raw.replay_limits.queue_packets == 2
    monkeypatch.setattr(raw, 'replay_limits', ReplayLimits(queue_wait_seconds=0.001))
    raw._send_queue = AudioSendQueue(maxsize=1)
    raw._send_task.cancel()
    await asyncio.gather(raw._send_task, return_exceptions=True)
    raw.send(b'\x01\x00')
    try:
        assert not await raw.wait_send_capacity()
        assert raw.is_connection_dead and raw.typed_death_reason == 'capacity_full'
    finally:
        await stop([raw])


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', [SafeSonioxSocket, SafeModulateSocket])
async def test_stalled_default_queue_replay_never_hides_behind_2000_slots(monkeypatch, kind):
    transport = Transport()
    transport.gate.clear()
    raw = kind(transport, lambda _: None, asyncio.get_running_loop())
    assert raw.replay_limits.queue_wait_seconds == 2.0 and raw.replay_limits.queue_packets == 2
    monkeypatch.setattr(raw, 'replay_limits', ReplayLimits(queue_wait_seconds=0.001))
    raw.replay_send = lambda data, start: raw.send(data)
    ring = full_ring()
    try:
        rejected = await replay_chunks(raw, ring.snapshot(), source=ring, provider='parakeet', soniox=None)
        assert rejected is not None
        assert raw._send_queue.maxsize == 2000 and raw._send_queue.high_water == 2
        assert raw.typed_death_reason == 'capacity_full'
    finally:
        await stop([raw])


@pytest.mark.asyncio
@pytest.mark.parametrize('successor', ['soniox', 'modulate-velma-2'])
async def test_adopted_tail_capacity_full_is_censored_not_provider_death(monkeypatch, successor):
    actual, _, raws, legs, observations = await setup_receiver(monkeypatch, ['parakeet-window', successor])
    actual.stt_socket.raw.fail('first_text_deadline')
    try:
        assert await actual._failover_stt_socket()
        tail = actual.stt_socket
        assert isinstance(tail, ReplayTailSocket)
        assert not tail.connection.is_connection_dead
        assert not tail.send(b'\x01\x00' * (27 * 16000), 135 * 16000)
        assert tail.typed_death_reason == 'capacity_full'
        assert not raws[-1].is_connection_dead
        assert live_stt_terminal_reason(tail, 'send_failed') == 'capacity_full'
        hop = PendingLiveFailover.from_socket(tail, actual.host.stt_service.value, 'unavailable')
        assert hop.reason == 'capacity_full'
        before = fallback_count()
        hop.note_failure(None)
        hop.note_failure(None)
        assert legs[-1].leg_outcome.settled
        assert fallback_count() - before == 1
        assert provider_observation('failover', 'capacity_full') is None
        recorded = [entry for entry in observations if entry[0] == legs[-1].routing_target]
        assert recorded and recorded[-1][5] == 'capacity_full'
        assert recorded[-1][5] != 'connection_lost'
    finally:
        await actual._drain_stt_sockets()
        await stop(raws)


@pytest.mark.asyncio
async def test_disconnect_during_successor_setup_closes_constructed_leg(monkeypatch):
    actual, _, raws, legs, observations = await setup_receiver(monkeypatch, ['parakeet-window', 'soniox'])
    actual.stt_socket.raw.fail('first_text_deadline')
    entered = asyncio.Event()
    held = []

    async def handshake(*args):
        leg = args[-1]
        held.append(leg)
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(st, '_primary_is_serving', handshake)
    monkeypatch.setattr(st, 'fallback_socket_is_serving', handshake)
    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', handshake)
    task = asyncio.create_task(actual._failover_stt_socket())
    try:
        await entered.wait()
        actual.host.state.active = False
        actual.stt_socket.mark_owner_teardown()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert held[0].leg_outcome.settled and held[0].leg_outcome.owner_closing
        assert raws[0]._send_task.done() and raws[0]._recv_task.done() and raws[0]._ws.closed
        assert legs[0].leg_outcome.settled
        assert len(observations) == 2
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        for leg in legs + held:
            leg.finish()
        await stop(raws)


def test_replay_coalescing_preserves_capture_gaps_and_packet_bound(monkeypatch):

    monkeypatch.setattr('utils.stt.replay_delivery.REPLAY_PACKET_BYTES', 4)
    assert list(replay_packets(((0, b'AA'), (1, b'BBBB'), (8, b'CCCCCC')))) == [
        (0, b'AABB'),
        (2, b'BB'),
        (8, b'CCCC'),
        (10, b'CC'),
    ]
    ring = full_ring()
    for _ in range(10):
        ring.reserve_replacement_headroom()
    assert ring.ring_seconds == 150


@pytest.mark.asyncio
async def test_text_during_failed_replay_is_not_replayed_or_emitted_twice(monkeypatch):

    monkeypatch.setattr(replay_delivery, 'REPLAY_PREFIX_SECONDS', 150.0)
    monkeypatch.setattr(recovery_state, 'RECOVERY_EPISODE_SECONDS', 200.0)
    actual, base, raws, legs, _ = await setup_receiver(
        monkeypatch, ['parakeet-window', 'soniox', 'modulate-velma-2'], fail_first=True
    )
    actual.stt_socket.raw.fail('first_text_deadline')
    original_pcm = b''.join(data for _, data in actual._window_ring().snapshot())
    original_create = actual._create_stt_socket

    async def create(*args, **kwargs):
        leg = await original_create(*args, **kwargs)
        if isinstance(leg.raw, SafeSonioxSocket):

            def first_text():
                leg.raw._ws.on_send = lambda: None
                leg.raw._stream_transcript([{'text': 'first', 'start': 0, 'end': 0.5, 'speaker': 'speaker_0'}])

            leg.raw._ws.on_send = first_text
        return leg

    monkeypatch.setattr(actual, '_create_stt_socket', create)
    try:
        assert await actual._failover_stt_socket()
        expected = original_pcm[16000:]  # First half-second was already emitted.
        await until(lambda: raws[-1]._ws.byte_count == len(expected))
        assert raws[-1]._ws.pcm == expected
        raws[-1]._stream_transcript([{'text': 'rest', 'start': 0, 'end': 134.5, 'speaker': 'speaker_0'}])
        assert [segment['text'] for segment in base.emitted] == ['first', 'rest']
        assert [(segment['start'], segment['end']) for segment in base.emitted] == [(0, 0.5), (0.5, 135)]
    finally:
        for leg in legs:
            leg.finish()
        await stop(raws)


@pytest.mark.asyncio
@pytest.mark.parametrize('successor', ['soniox', 'modulate-velma-2'])
async def test_slow_consumer_full_ring_paced_budget_and_realtime_live_order(monkeypatch, virtual_clock, successor):

    monkeypatch.setattr(replay_delivery, 'REPLAY_PREFIX_SECONDS', 20.0)
    actual, _, raws, legs, _ = await setup_receiver(monkeypatch, ['parakeet-window', successor])
    actual.stt_socket.raw.fail('first_text_deadline')
    original = b''.join(data for _, data in actual._window_ring().snapshot())
    family = 'soniox' if successor == 'soniox' else 'modulate'
    labels = dict(source='parakeet', successor=family)
    skipped_before = REPLAY_SKIPPED.labels(**labels)._value.get()
    audio_before = REPLAY_AUDIO.labels(**labels)._value.get()
    closed_before = REPLAY_CLOSED.labels(**labels)._value.get()
    original_create = actual._create_stt_socket

    async def create(*args, **kwargs):
        leg = await original_create(*args, **kwargs)
        leg.raw._ws.timer = virtual_clock
        return leg

    monkeypatch.setattr(actual, '_create_stt_socket', create)
    monkeypatch.setattr(actual, '_capture', lambda *args, **kwargs: None)
    tail = []
    captured = []

    async def ingest():
        for n in range(70):  # 21s of real-time capture; continues past adoption.
            await virtual_clock.sleep(0.3)
            data = (6000 + n).to_bytes(2, 'little') * 4800
            tail.append(data)
            captured.append(virtual_clock.now)
            actual._stt_buffer_start_sample = 135 * 16000 + n * 4800
            buffer = bytearray(data)
            await actual._flush_stt_buffer(buffer, force=True)
            assert not buffer  # Ingestion never waits for the recovery lock.

    task = asyncio.create_task(actual._failover_stt_socket())
    ingestion = asyncio.create_task(ingest())
    try:
        assert await task
        replay_wall = virtual_clock.now
        assert 19 <= replay_wall <= 20 + 3 * 0.512 + 0.001
        await ingestion
        expected = original[115 * 32000 :] + b''.join(tail)
        await until(lambda: raws[-1]._ws.byte_count == len(expected))
        transport = raws[-1]._ws
        assert transport.pcm == expected
        assert raws[-1]._send_queue.high_water <= 2
        assert not raws[-1].is_connection_dead
        assert REPLAY_SKIPPED.labels(**labels)._value.get() - skipped_before == 115
        assert REPLAY_AUDIO.labels(**labels)._value.get() - audio_before == pytest.approx(20)
        assert REPLAY_CLOSED.labels(**labels)._value.get() == closed_before
        # For every replay admission interval: <=1x audio plus one bounded packet.
        packets = [(data, at) for data, at in zip(transport.sent, transport.sent_at) if isinstance(data, bytes)]
        delivered = 0.0
        for data, at in packets:
            delivered += len(data) / 32000
            assert delivered <= at + 0.512 + 0.001
        live_times = [at for _, at in packets[40:]]  # ceil(640000 / 16384) replay packets
        assert len(live_times) == len(captured)
        assert max(at - born for at, born in zip(live_times, captured)) <= 20.532 + 3 * 0.512
        assert sum(len(packet.data) for packet in actual.stt_socket.tail) <= 21 * 32000
    finally:
        task.cancel()
        ingestion.cancel()
        await asyncio.gather(task, ingestion, return_exceptions=True)
        for leg in legs:
            leg.finish()
        actual.stt_socket.finish()
        await stop(raws)


@pytest.mark.asyncio
@pytest.mark.parametrize('successor', ['soniox', 'modulate-velma-2'])
async def test_send_queue_full_during_owner_departure_is_not_exhaustion(monkeypatch, successor):

    actual, _, raws, legs, _ = await setup_receiver(monkeypatch, ['parakeet-window', successor])
    actual.stt_socket.raw.fail('first_text_deadline')
    try:
        assert await actual._failover_stt_socket()
        leg = actual.stt_socket
        # Healthy socket, stalled sender outside replay: finalize also needs a slot.
        raw = raws[-1]
        raw._send_task.cancel()
        await asyncio.sleep(0)
        raw._send_task.cancel()
        await asyncio.gather(raw._send_task, return_exceptions=True)
        while not raw._send_queue.full():
            raw._send_queue.put_nowait(b'\x01\x00')
        actual.host.state.active = False
        before = fallback_count()
        raw.finalize() if successor == 'soniox' else raw.send(b'\x01\x00')
        assert raw.is_connection_dead
        assert raw.death_reason == 'send queue full'
        settle_terminal_socket(leg, actual.host.stt_service.value, 'capacity_full')
        settle_terminal_socket(leg, actual.host.stt_service.value, 'capacity_full')
        assert leg.leg_outcome.settled and leg.leg_outcome.excluded_death
        assert fallback_count() == before
        assert not actual.host.state.stt_terminal_failure
        while not raw._send_queue.empty():
            raw._send_queue.get_nowait()
    finally:
        for leg in legs:
            leg.finish()
        await stop(raws)


@pytest.mark.asyncio
@pytest.mark.parametrize('successor', ['soniox', 'modulate-velma-2'])
async def test_adopted_live_tail_drains_before_eos_after_client_departure(monkeypatch, virtual_clock, successor):

    monkeypatch.setattr(replay_delivery, 'REPLAY_PREFIX_SECONDS', 20.0)
    actual, _, raws, legs, observations = await setup_receiver(monkeypatch, ['parakeet-window', successor])
    actual.stt_socket.raw.fail('first_text_deadline')
    original = b''.join(data for _, data in actual._window_ring().snapshot())[-640000:]
    monkeypatch.setattr(actual, '_capture', lambda *args, **kwargs: None)
    task = asyncio.create_task(actual._failover_stt_socket())
    try:
        await until(lambda: bool(raws))
        await virtual_clock.sleep(0.03)
        tail = b'\x23\x01' * 480
        actual._stt_buffer_start_sample = 135 * 16000
        await actual._flush_stt_buffer(bytearray(tail), force=True)
        assert await task
        actual.stt_socket.mark_owner_teardown()
        actual.host.state.active = False
        await actual.stt_socket.drain_and_close()
        actual._settle_pending_live_failover_failure()
        assert raws[-1]._ws.pcm == original + tail
        assert raws[-1]._ws.sent[-1] == ''
        assert raws[-1]._ws.closed and raws[-1]._send_task.done() and raws[-1]._recv_task.done()
        assert actual.stt_socket._task.done()
        assert all(leg.leg_outcome.settled for leg in legs)
        assert len(observations) == len(legs) == 2
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        actual.stt_socket.finish()
        await stop(raws)
