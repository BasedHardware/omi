"""Deterministic paid-transport lifecycle using real gate and Soniox loops."""

import asyncio
import json
from collections import deque
from types import SimpleNamespace

import pytest
from prometheus_client import REGISTRY

from config import soniox_idle as idle_config
from config.soniox_idle import idle_close_seconds, idle_max_closes_per_hour, idle_rearm_seconds
from utils.stt import soniox, soniox_idle, vad_gate, live_metrics, live_session, replay_delivery
from utils.stt.streaming import STTService
from utils.stt.soniox import SafeSonioxSocket
from utils.stt.soniox_idle import IdleSonioxSocket, SonioxIdleBudget
from utils.stt.vad_gate import GatedSTTSocket, VADStreamingGate
from utils.stt.live_failure import send_live_stt_audio


class Peer:
    def __init__(self):
        self.sent = []
        self.frames = asyncio.Queue()
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        frame = await self.frames.get()
        if frame is None:
            raise StopAsyncIteration
        return json.dumps(frame)

    async def send(self, data):
        self.sent.append(data)
        if data == '':
            self.frames.put_nowait({'finished': True})
        elif data == '{"type": "finalize"}':
            self.frames.put_nowait({'tokens': [{'text': '<fin>', 'is_final': True}]})

    async def close(self):
        self.closed = True
        self.frames.put_nowait(None)


def build(monkeypatch, seconds=2, fail=False):
    tick = [100.0]
    monkeypatch.setattr(soniox_idle.time, 'monotonic', lambda: tick[0])
    monkeypatch.setattr(vad_gate, '_get_ort_session', lambda: None)
    monkeypatch.setattr(VADStreamingGate, '_run_vad', lambda self, data: data[0] == 1)
    peers = [Peer()]
    seen = []
    raw = SafeSonioxSocket(peers[0], seen.extend, asyncio.get_running_loop())

    async def connect(callback):
        if fail:
            raise RuntimeError('dial failed')
        peer = Peer()
        peers.append(peer)
        return SafeSonioxSocket(peer, callback, asyncio.get_running_loop())

    idle = IdleSonioxSocket(raw, connect, seen.extend, 16000, seconds)
    gate = VADStreamingGate(sample_rate=16000, mode='active', hangover_ms=0)
    return GatedSTTSocket(idle, gate), idle, gate, peers, seen, tick


async def settle():
    # No wall sleeps or ONNX work: deterministic event-loop scheduling only.
    for _ in range(12):
        await asyncio.sleep(0)


@pytest.mark.parametrize('value', [None, '0'])
@pytest.mark.parametrize('warm', [False, True])
def test_off_returns_original_adapter_and_no_idle_series(monkeypatch, value, warm):
    monkeypatch.setenv('SONIOX_API_KEY', 'fake')
    if value is None:
        monkeypatch.delenv('SONIOX_IDLE_CLOSE_SECONDS', raising=False)
    else:
        monkeypatch.setenv('SONIOX_IDLE_CLOSE_SECONDS', value)
    if warm:
        live_metrics.soniox_idle_metrics()

    # Prior enabled tests may have registered idle collectors already. Compare
    # the actual global registry, including their values, without replacing it.
    def snapshot():
        return {
            (sample.name, tuple(sorted(sample.labels.items()))): sample.value
            for family in REGISTRY.collect()
            for sample in family.samples
        }

    before = snapshot()
    monkeypatch.setattr(live_metrics, 'Counter', lambda *a, **kw: pytest.fail('off registered metric'))
    monkeypatch.setattr(live_metrics, 'Histogram', lambda *a, **kw: pytest.fail('off registered histogram'))
    monkeypatch.setattr(soniox_idle, 'soniox_idle_metrics', lambda: pytest.fail('off requested idle metrics'))
    peers = []

    async def dial(*args, **kwargs):
        peer = Peer()
        peers.append(peer)
        return peer

    monkeypatch.setattr(soniox.websockets, 'connect', dial)

    async def run():
        socket = await soniox.process_audio_soniox(lambda _: None, 16000, 'en')
        assert type(socket) is SafeSonioxSocket
        socket.send(b'\x01\x00')
        socket.finalize()
        await socket.drain_and_close()
        assert peers[0].sent[1:] == [b'\x01\x00', '{"type": "finalize"}', '']

    asyncio.run(run())
    after = snapshot()
    assert after.keys() == before.keys()
    assert {key: value for key, value in after.items() if key[0].startswith('omi_soniox_idle')} == {
        key: value for key, value in before.items() if key[0].startswith('omi_soniox_idle')
    }


@pytest.mark.parametrize('recovery', ['false', 'true'])
def test_silence_close_onset_exact_and_timestamp_continuity(monkeypatch, recovery):
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', recovery)

    async def run():
        socket, idle, gate, peers, seen, tick = build(monkeypatch)
        speech = b'\x01\x00' * 1600
        silence = b'\x00\x00' * 1600
        assert socket.send(speech, wall_time=100, start_sample=0)
        idle._transport._handle_tokens([{'text': 'first ', 'is_final': True, 'start_ms': 0, 'end_ms': 100}])
        socket.send(silence, wall_time=100.1, start_sample=1600)
        tick[0] += 3
        socket.send(silence, wall_time=103.1, start_sample=49600)
        await idle._close_task
        assert peers[0].closed
        assert not socket.is_connection_dead
        assert socket.death_reason is None
        assert socket.typed_death_reason is None
        assert peers[0].sent[-2:] == ['{"type": "finalize"}', '']
        # The gate already holds the last silence PCM. Onset includes it once,
        # before the new speech frame, without decoder/resampler edits.
        pre_roll = b''.join(data for data, _ in gate._pre_roll)
        tick[0] += 20
        assert socket.send(speech, wall_time=123.1, start_sample=369600)
        assert len(peers) == 1
        assert await socket.complete_send()
        await settle()
        assert [x for x in peers[1].sent if isinstance(x, bytes)] == [pre_roll + speech]
        idle._transport._handle_tokens([{'text': 'next ', 'is_final': True, 'start_ms': 0, 'end_ms': 100}])
        gate.remap_segments(seen)
        assert seen[1]['start'] >= seen[0]['end']
        assert seen[1]['start'] > 20
        await idle.drain_and_close()
        assert not socket.is_connection_dead

    asyncio.run(run())


def test_failed_reopen_uses_normal_send_failover_boundary(monkeypatch):
    async def run():
        socket, idle, _, peers, _, tick = build(monkeypatch, fail=True)
        silence = b'\x00\x00' * 1600
        socket.send(silence, wall_time=100)
        tick[0] += 3
        socket.send(silence, wall_time=103)
        await idle._close_task
        fallback = []

        async def failover():
            fallback.append(True)
            return True

        state = SimpleNamespace(active=True, stt_terminal_failure=False)
        sent = await send_live_stt_audio(
            None,
            state,
            stt_socket=socket,
            audio=b'\x01\x00' * 1600,
            provider='soniox',
            platform='desktop',
            attempt_failover=failover,
        )
        assert not sent
        assert fallback == [True]
        assert idle.is_connection_dead
        assert not state.stt_terminal_failure
        assert len(peers) == 1
        await idle.drain_and_close()

    asyncio.run(run())


def test_end_while_idle_closed_never_reopens(monkeypatch):
    async def run():
        socket, idle, _, peers, _, tick = build(monkeypatch)
        socket.send(b'\x00\x00' * 1600, wall_time=100)
        tick[0] += 3
        socket.send(b'\x00\x00' * 1600, wall_time=103)
        await idle._close_task
        socket.finalize()
        socket.finish()
        await idle.drain_and_close()
        assert len(peers) == 1
        assert peers[0].closed
        assert not idle.is_connection_dead

    asyncio.run(run())


@pytest.mark.parametrize('value', ['', '0', '-1', 'nan', 'inf', 'invalid'])
def test_off_values_are_inert(monkeypatch, value):
    monkeypatch.setenv('SONIOX_IDLE_CLOSE_SECONDS', value)
    assert idle_close_seconds() == 0


def test_threshold_floor_logs_once_and_reads_current_env(monkeypatch, caplog):
    idle_config._warn_threshold_floor.cache_clear()
    try:
        for value in ['0.001', '1', '19.99', '1']:
            monkeypatch.setenv('SONIOX_IDLE_CLOSE_SECONDS', value)
            assert idle_close_seconds() == 20
        assert len([record for record in caplog.records if 'below safety floor' in record.message]) == 1
        for value in ['20', '45', '90']:
            monkeypatch.setenv('SONIOX_IDLE_CLOSE_SECONDS', value)
            assert idle_close_seconds() == float(value)
    finally:
        idle_config._warn_threshold_floor.cache_clear()


@pytest.mark.parametrize(
    'value,expected', [('1', 60), ('0', 60), ('-1', 60), ('120', 120), ('nan', 60), ('inf', 60), ('bad', 60)]
)
def test_rearm_config_has_a_safe_floor(monkeypatch, value, expected):
    monkeypatch.setenv('SONIOX_IDLE_REARM_SECONDS', value)
    assert idle_rearm_seconds() == expected


@pytest.mark.parametrize('value,expected', [('3', 3), ('0', 12), ('-1', 12), ('1.5', 12), ('nan', 12), ('bad', 12)])
def test_hourly_close_cap_config(monkeypatch, value, expected):
    monkeypatch.setenv('SONIOX_IDLE_MAX_CLOSES_PER_HOUR', value)
    assert idle_max_closes_per_hour() == expected


@pytest.mark.parametrize('recovery', ['false', 'true'])
@pytest.mark.parametrize('cap', [None, 3])
def test_threshold_flapping_bounds_paid_dials(monkeypatch, recovery, cap):
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', recovery)
    monkeypatch.setenv('SONIOX_IDLE_CLOSE_SECONDS', '20')
    monkeypatch.delenv('SONIOX_IDLE_REARM_SECONDS', raising=False)
    if cap is None:
        monkeypatch.delenv('SONIOX_IDLE_MAX_CLOSES_PER_HOUR', raising=False)
    else:
        monkeypatch.setenv('SONIOX_IDLE_MAX_CLOSES_PER_HOUR', str(cap))
    limit = cap or 12

    async def run():
        socket, idle, _, peers, _, tick = build(monkeypatch, seconds=idle_close_seconds())
        silence = b'\x00\x00' * 1600
        onset = b'\x01\x00' * 1600
        closed_at = []
        reopened_at = []

        def send(data):
            assert socket.send(data, wall_time=tick[0], start_sample=round((tick[0] - 100) * 16000))

        # 120 opportunities over 40 minutes, with onset immediately after each
        # threshold. The original implementation dials on every iteration.
        for _ in range(120):
            send(silence)
            tick[0] += 20
            send(silence)
            if idle._idle_since is not None:
                closed_at.append(tick[0])
                await idle._close_task
            tick[0] += 0.01
            send(onset)
            previous = len(peers)
            assert await socket.complete_send()
            if len(peers) > previous:
                reopened_at.append(tick[0])
                await settle()
                assert b''.join(data for data in peers[-1].sent if isinstance(data, bytes)).endswith(onset)
            socket.commit_send()

        assert len(peers) == limit + 1  # initial dial plus capped idle reopens
        assert len(closed_at) == len(reopened_at) == limit
        assert all(close - reopen >= 60 for close, reopen in zip(closed_at[1:], reopened_at))
        assert not peers[-1].closed
        assert not socket.is_connection_dead
        await idle.drain_and_close()

    asyncio.run(run())


def test_cooldown_and_rolling_hour_expire_at_exact_boundaries(monkeypatch):
    monkeypatch.setenv('SONIOX_IDLE_REARM_SECONDS', '120')
    monkeypatch.setenv('SONIOX_IDLE_MAX_CLOSES_PER_HOUR', '2')

    async def run():
        socket, idle, _, peers, _, tick = build(monkeypatch, seconds=20)
        silence = SimpleNamespace(is_speech=False, audio_to_send=b'')
        idle.observe_vad(silence, 'active')
        tick[0] += 20
        idle.observe_vad(silence, 'active')
        first_close = tick[0]
        await idle._close_task
        assert socket.send(b'\x01\x00' * 1600, wall_time=tick[0])
        assert await socket.complete_send()
        idle.observe_vad(silence, 'active')
        tick[0] += 119.999
        idle.observe_vad(silence, 'active')
        assert idle._idle_since is None
        tick[0] = first_close + 120
        idle.observe_vad(silence, 'active')
        assert idle._idle_since == tick[0]
        await idle._close_task
        assert socket.send(b'\x01\x00' * 1600, wall_time=tick[0])
        assert await socket.complete_send()
        idle.observe_vad(silence, 'active')
        tick[0] = first_close + 3599.999
        idle.observe_vad(silence, 'active')
        assert idle._idle_since is None
        tick[0] = first_close + 3600
        idle.observe_vad(silence, 'active')
        assert idle._idle_since == tick[0]
        assert len(idle._idle_budget.close_times) == 2
        await idle._close_task
        assert len(peers) == 3
        await idle.drain_and_close()

    asyncio.run(run())


def test_session_budget_survives_socket_replacement(monkeypatch):
    monkeypatch.setenv('SONIOX_API_KEY', 'fake')
    monkeypatch.setenv('SONIOX_IDLE_CLOSE_SECONDS', '20')
    monkeypatch.setenv('SONIOX_IDLE_REARM_SECONDS', '120')
    monkeypatch.setenv('SONIOX_IDLE_MAX_CLOSES_PER_HOUR', '1')
    tick = [100.0]
    monkeypatch.setattr(soniox_idle.time, 'monotonic', lambda: tick[0])

    async def dial(*args, **kwargs):
        return Peer()

    monkeypatch.setattr(soniox.websockets, 'connect', dial)

    async def run():
        budget = SonioxIdleBudget()
        first = await soniox.process_audio_soniox(lambda _: None, 16000, 'en', idle_budget=budget)
        silence = SimpleNamespace(is_speech=False, audio_to_send=b'')
        first.observe_vad(silence, 'active')
        tick[0] += 20
        first.observe_vad(silence, 'active')
        await first._close_task
        assert first.send(b'\x01\x00' * 1600)
        assert await first.complete_send()
        await first.drain_and_close()
        # Both legacy and managed connectors pass the receiver's same budget
        # through this serving constructor when replacing a provider leg.
        replacement = await soniox.process_audio_soniox(lambda _: None, 16000, 'en', idle_budget=budget)
        assert replacement._idle_budget is first._idle_budget
        replacement.observe_vad(silence, 'active')
        tick[0] += 120
        replacement.observe_vad(silence, 'active')
        assert replacement._close_task is None  # cooldown elapsed, hourly cap persists
        tick[0] = 3720
        replacement.observe_vad(silence, 'active')
        await replacement._close_task
        await replacement.drain_and_close()

    asyncio.run(run())


def test_shutdown_during_dial_cancels_and_reaps_owned_task(monkeypatch):
    async def run():
        socket, idle, _, peers, _, tick = build(monkeypatch)
        socket.send(b'\x00\x00' * 1600, wall_time=100)
        tick[0] += 3
        socket.send(b'\x00\x00' * 1600, wall_time=103)
        await idle._close_task
        entered = asyncio.Event()
        cancelled = asyncio.Event()

        async def connect(callback):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        idle._connect = connect
        assert socket.send(b'\x01\x00' * 1600, wall_time=104)
        completion = asyncio.create_task(socket.complete_send())
        await entered.wait()
        await idle.drain_and_close()
        await asyncio.gather(completion, return_exceptions=True)
        assert cancelled.is_set()
        assert len(peers) == 1
        assert idle._reopen_task.done()
        assert not [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]

    asyncio.run(run())


def test_failed_dial_preserves_preroll_through_actual_buffer_retry(monkeypatch):
    async def run():
        socket, idle, gate, _, _, tick = build(monkeypatch, fail=True)
        silence = b'\x00\x00' * 1600
        socket.send(silence, wall_time=100, start_sample=0)
        tick[0] += 3
        socket.send(silence, wall_time=103, start_sample=48000)
        await idle._close_task
        prefix = b''.join(data for data, _ in gate._pre_roll)
        delivered = []
        replacement = SimpleNamespace(
            is_connection_dead=False,
            send_admitted_audio=lambda data, spans: delivered.append((data, spans)) or True,
        )

        class Receiver:
            stt_socket = socket

            async def failover(self):
                self.stt_socket = replacement
                return True

        owner = Receiver()
        state = SimpleNamespace(active=True, stt_terminal_failure=False)
        onset = b'\x01\x00' * 1600
        assert not await send_live_stt_audio(
            None,
            state,
            stt_socket=owner.stt_socket,
            audio=onset,
            start_sample=49600,
            provider='soniox',
            platform='desktop',
            attempt_failover=owner.failover,
        )
        assert await send_live_stt_audio(
            None,
            state,
            stt_socket=owner.stt_socket,
            audio=onset,
            start_sample=49600,
            provider='soniox',
            platform='desktop',
            attempt_failover=owner.failover,
        )
        assert delivered[0][0] == prefix + onset
        assert len(delivered) == 1
        assert owner._idle_onset_retry is None
        await idle.drain_and_close()

    asyncio.run(run())


@pytest.mark.parametrize('recovery', ['false', 'true'])
def test_managed_idle_close_does_not_claim_health_or_breaker(monkeypatch, recovery):
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', recovery)
    monkeypatch.setenv('STT_ROUTING_MODE', 'off')

    async def run():
        socket, idle, gate, _, _, tick = build(monkeypatch)
        host = SimpleNamespace(
            language='en', request=SimpleNamespace(uid='idle-unit'), state=SimpleNamespace(active=True)
        )
        owner = SimpleNamespace(host=host, recovery=None, _telemetry_platform=lambda: 'desktop')
        session = live_session.LiveChainSession(owner)
        leg = live_session.LiveLegSocket(idle, gate, session, STTService.soniox, 16000, False, False)
        for method in ('record', 'quarantine', 'quarantine_target'):
            monkeypatch.setattr(live_session.health, method, lambda *a, **kw: pytest.fail('idle health side effect'))
        leg.send(b'\x00\x00' * 1600, start_sample=0)
        tick[0] += 3
        leg.send(b'\x00\x00' * 1600, start_sample=48000)
        await idle._close_task
        assert not leg.is_connection_dead
        assert not leg.leg_outcome.claimed
        assert not leg.leg_outcome.death_observed
        assert not leg._target_death_recorded
        assert not leg._open_gauge_released
        await leg.drain_and_close()
        assert not leg.leg_outcome.claimed

    asyncio.run(run())


def test_replay_tail_pump_completes_idle_reopen(monkeypatch):
    async def run():
        socket, idle, _, peers, _, tick = build(monkeypatch)
        socket.send(b'\x00\x00' * 1600, wall_time=100)
        tick[0] += 3
        socket.send(b'\x00\x00' * 1600, wall_time=103)
        await idle._close_task
        host = SimpleNamespace(
            spawn=lambda coro, **kw: asyncio.create_task(coro),
            state=SimpleNamespace(active=True, stt_terminal_failure=False),
        )
        tail = replay_delivery.ReplayTailSocket(
            socket, replay_delivery.ReplayPacer(16000, 'soniox', socket), deque(), host, source='soniox'
        )
        onset = b'\x01\x00' * 1600
        assert tail.send(onset, start_sample=48000)
        tail.start_tail()
        await tail._task
        await settle()
        assert len(peers) == 2
        assert b''.join(x for x in peers[1].sent if isinstance(x, bytes)).endswith(onset)
        assert not tail.is_connection_dead
        await idle.drain_and_close()

    asyncio.run(run())


@pytest.mark.parametrize(
    'code,error,expected',
    [
        (402, 'organization_balance_exhausted', 'provider_budget_exhausted'),
        (401, 'unauthorized', 'provider_auth_rejected'),
    ],
)
def test_planned_close_preserves_real_provider_rejection(monkeypatch, code, error, expected):
    monkeypatch.setenv('STT_CONNECT_ORDER_FROM_CONFIG', 'true')

    async def run():
        socket, idle, _, peers, _, tick = build(monkeypatch)
        peers[0].frames.put_nowait({'error_code': code, 'error_type': error})
        idle._transport._planned_close = True
        idle._idle_since = tick[0]
        await settle()
        assert socket.is_connection_dead
        assert socket.typed_death_reason == expected
        await idle.drain_and_close()
        await idle._transport.drain_and_close()

    asyncio.run(run())


def test_planned_no_audio_teardown_emits_no_failure_metric(monkeypatch):
    async def run():
        socket, idle, _, peers, _, _ = build(monkeypatch)
        raw = idle._transport
        raw._planned_close = True
        raw.finish()
        monkeypatch.setattr(soniox, 'record_stt_stream_close', lambda **kw: pytest.fail('planned close evidence'))
        peers[0].frames.put_nowait({'error_code': 400, 'error_message': 'No audio received'})
        await settle()
        assert not socket.is_connection_dead
        await raw.drain_and_close()

    asyncio.run(run())


def test_immediately_dead_reopen_retains_onset_for_failover(monkeypatch):
    async def run():
        socket, idle, gate, _, _, tick = build(monkeypatch)
        socket.send(b'\x00\x00' * 1600, wall_time=100, start_sample=0)
        tick[0] += 3
        socket.send(b'\x00\x00' * 1600, wall_time=103, start_sample=48000)
        await idle._close_task
        prefix = b''.join(data for data, _ in gate._pre_roll)
        complete = socket.complete_send

        async def complete_then_die():
            assert await complete()
            idle._transport._mark_dead('ws recv error: reset', typed_reason='connection_lost')
            idle._transport._done_event.set()
            idle._transport._send_task.cancel()
            return True

        socket.complete_send = complete_then_die

        class Receiver:
            async def failover(self):
                return True

        owner = Receiver()
        onset = b'\x01\x00' * 1600
        state = SimpleNamespace(active=True, stt_terminal_failure=False)
        assert not await send_live_stt_audio(
            None,
            state,
            stt_socket=socket,
            audio=onset,
            start_sample=49600,
            provider='soniox',
            platform='desktop',
            attempt_failover=owner.failover,
        )
        assert owner._idle_onset_retry[0] == prefix + onset
        await idle.drain_and_close()

    asyncio.run(run())


def test_admitted_onset_stays_behind_existing_replay_tail(monkeypatch):
    async def run():
        delivered = []
        connection = SimpleNamespace(
            is_connection_dead=False,
            send=lambda data, **kw: delivered.append(('prior', data, kw)) or True,
            send_admitted_audio=lambda data, spans: delivered.append(('onset', data, spans)) or True,
        )
        host = SimpleNamespace(
            spawn=lambda coro, **kw: asyncio.create_task(coro),
            state=SimpleNamespace(active=True, stt_terminal_failure=False),
        )
        pacer = replay_delivery.ReplayPacer(16000, 'soniox', connection)
        # Pacing is tested elsewhere: keep this queue-order regression CPU-only.
        monkeypatch.setattr(replay_delivery, '_next_audio_slot', lambda *a: 0)
        tail = replay_delivery.ReplayTailSocket(
            connection, pacer, deque([replay_delivery.TailPacket(0, b'old!', replay_delivery.clock())]), host
        )
        assert tail.send_admitted_audio(b'nextword', ((20, 2), (40, 2)))
        assert delivered == []
        tail.start_tail()
        await tail._task
        assert [(kind, data) for kind, data, _ in delivered] == [
            ('prior', b'old!'),
            ('onset', b'next'),
            ('onset', b'word'),
        ]
        assert [item[2] for item in delivered[1:]] == [((20, 2),), ((40, 2),)]

    asyncio.run(run())


def test_replayed_preroll_is_not_delivered_twice(monkeypatch):
    from utils.audio_timeline import CaptureTimeline, ProviderEpochTranslator

    tracker = ProviderEpochTranslator(CaptureTimeline(16000), 16000)
    tracker.note_accepted(20, 2)
    data, spans = soniox_idle.unaccepted_onset(b'pre!word', ((20, 2), (40, 2)), tracker)
    assert data == b'word'
    assert spans == ((40, 2),)


@pytest.mark.parametrize('elapsed', ['off', 'on', 'shadow'])
def test_capture_and_wall_continuity_with_socket_reset(monkeypatch, elapsed):
    from utils.audio_timeline import CaptureTimeline, ProviderEpochTranslator

    monkeypatch.setenv('SONIOX_ELAPSED_AXIS', elapsed)

    async def run():
        socket, idle, gate, _, seen, tick = build(monkeypatch)
        timeline = CaptureTimeline(16000)
        tracker = ProviderEpochTranslator(timeline, 16000)
        tracker.provider_label = 'soniox'
        socket._send_tracker = tracker
        idle._callback = lambda segments: seen.extend(tracker.translate(segments))
        speech = b'\x01\x00' * 1600
        silence = b'\x00\x00' * 1600
        for i in range(42):
            data = speech if i in (0, 41) else silence
            start, _, _ = timeline.accept(data, 100 + (i + 1) / 10, 100 + (i + 1) / 10)
            tick[0] = 100 + i / 10
            assert socket.send(data, wall_time=tick[0], start_sample=start)
            if i == 0:
                idle._transport._handle_tokens([{'text': 'first ', 'is_final': True, 'start_ms': 0, 'end_ms': 100}])
            if idle._close_task is not None:
                await idle._close_task
        assert await socket.complete_send()
        idle._transport._handle_tokens([{'text': 'next ', 'is_final': True, 'start_ms': 100, 'end_ms': 200}])
        assert len(seen) == 2
        assert seen[1]['start'] >= seen[0]['end']
        assert seen[1]['start'] > 3
        assert seen[1]['_capture_start_sample'] >= 39 * 1600
        assert seen[1]['_capture_end_sample'] <= 42 * 1600
        await idle.drain_and_close()

    asyncio.run(run())


@pytest.mark.parametrize('mode', ['shadow', 'on'])
def test_routed_idle_close_keeps_cost_evidence_and_circuits_unchanged(monkeypatch, mode):
    from config.live_stt_registry import Target

    monkeypatch.setenv('STT_ROUTING_MODE', mode)
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')

    async def run():
        _, idle, gate, _, _, tick = build(monkeypatch)
        host = SimpleNamespace(
            language='en', request=SimpleNamespace(uid='idle-unit'), state=SimpleNamespace(active=True)
        )
        owner = SimpleNamespace(host=host, recovery=None, _telemetry_platform=lambda: 'desktop')
        session = live_session.LiveChainSession(owner)
        target = Target('soniox-idle-test', 'soniox', 0.12)
        token = live_session.connecting_target.set(target)
        try:
            leg = live_session.LiveLegSocket(idle, gate, session, STTService.soniox, 16000, False, False)
        finally:
            live_session.connecting_target.reset(token)
        for method in ('record', 'record_session', 'quarantine', 'quarantine_target'):
            monkeypatch.setattr(live_session.health, method, lambda *a, **kw: pytest.fail('idle router evidence'))
        monkeypatch.setattr(live_session, 'target_circuit', lambda *a: pytest.fail('idle circuit lookup'))
        leg.send(b'\x00\x00' * 1600, start_sample=0)
        tick[0] += 3
        leg.send(b'\x00\x00' * 1600, start_sample=48000)
        await idle._close_task
        assert not leg.is_connection_dead
        assert not leg.leg_outcome.claimed
        assert not leg._target_death_recorded
        assert leg._routing_target_entry == target
        await leg.drain_and_close()

    asyncio.run(run())


@pytest.mark.parametrize(
    'error,reason',
    [
        (TimeoutError('dial'), 'timeout'),
        (RuntimeError('dial'), 'provider_5xx'),
        (soniox.SonioxRateLimitError('dial'), 'provider_429'),
    ],
)
def test_failed_reopen_has_normal_connect_reason(monkeypatch, error, reason):
    async def run():
        socket, idle, _, _, _, tick = build(monkeypatch)
        socket.send(b'\x00\x00' * 1600, wall_time=100)
        tick[0] += 3
        socket.send(b'\x00\x00' * 1600, wall_time=103)
        await idle._close_task

        async def connect(callback):
            raise error

        idle._connect = connect
        assert socket.send(b'\x01\x00' * 1600, wall_time=104)
        assert not await socket.complete_send()
        assert idle.typed_death_reason == reason
        assert idle.idle_reopen_failed
        await idle.drain_and_close()

    asyncio.run(run())


def test_tail_rejects_onset_without_capture_spans():
    async def run():
        connection = SimpleNamespace(is_connection_dead=False)
        host = SimpleNamespace(state=SimpleNamespace(active=True, stt_terminal_failure=False))
        tail = replay_delivery.ReplayTailSocket(
            connection, replay_delivery.ReplayPacer(16000, 'soniox', connection), deque(), host
        )
        assert not tail.send_admitted_audio(b'onset!', ())
        assert tail._tail_bytes == 0
        assert not tail.tail

    asyncio.run(run())
