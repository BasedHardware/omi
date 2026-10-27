"""Idle onset through real managed selection, ordered delivery and fake transports."""

import asyncio

import pytest

from tests.unit.test_parakeet_window_live import runtime, Client  # noqa: F401
from tests.unit.test_live_cost_router import controls  # noqa: F401
from tests.unit.test_live_replay_provider_pairs import setup_receiver, stop, until
from utils.observability import demand_cohort as telemetry
from utils.stt import live_chain, live_session, parakeet_window as window, replay_delivery, streaming as st
from utils.stt.live_gate import GateState
from utils.stt.live_metrics import soniox_idle_metrics
from utils.stt.soniox_idle import IdleSonioxSocket
from utils.stt.recovery_state import MAX_RECOVERY_EPISODES
from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401
from routers.listen.receiver import ListenReceiver
from tests.unit.test_live_replay_provider_pairs import Transport
from utils.stt.soniox import SafeSonioxSocket


async def idle_receiver(monkeypatch, *, language='en', enabled=True, benched=False, modulate=False):
    monkeypatch.setenv('STT_IDLE_REOPEN_COST_RESELECT_ENABLED', str(enabled).lower())
    monkeypatch.setenv('SONIOX_IDLE_NO_FRAMES_SECONDS', '0')
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    states = {
        'parakeet-window': GateState(stage=0, until=1e20),
        'modulate-velma-2': GateState(stage=0, until=1e20),
    }
    monkeypatch.setattr(
        live_chain.health,
        'cost_snapshot',
        lambda targets, _language: {target.id: states.get(target.id, GateState()) for target in targets},
    )
    models = ['soniox', 'parakeet-window'] + (['modulate-velma-2'] if modulate else [])
    actual, base, raws, legs, observations = await setup_receiver(monkeypatch, models, source='soniox')
    actual._window_replay_audio = None
    actual._resilient_audio = None
    old = actual.stt_socket
    old.gate = None
    actual.host.language = language
    actual.host.stt_language = language
    factory = st.process_audio_soniox

    async def wrap(callback, *args, **kwargs):
        raw = await factory(callback, *args, **kwargs)
        return IdleSonioxSocket(raw, lambda cb: factory(cb, *args, **kwargs), callback, 16000, 20)

    monkeypatch.setattr(st, 'process_audio_soniox', wrap)
    idle = IdleSonioxSocket(old.raw, lambda cb: factory(cb), old.raw._stream_transcript, 16000, 20)
    if old._soniox_wire_ledger:
        idle.set_wire_ledger(old._send_tracker)
    old.raw = idle
    states['parakeet-window'] = GateState(stage=0, until=1e20) if benched else GateState()
    states['modulate-velma-2'] = GateState()
    monkeypatch.setattr(actual, '_capture', lambda *args, **kwargs: None)
    return actual, base, raws, legs, observations, old, idle, states


async def close_idle(idle):
    idle._begin_idle_close(1.0, 'vad')
    await idle._close_task


async def onset(actual, data, start=2160000):
    actual._stt_buffer_start_sample = start
    buffer = bytearray(data)
    await actual._flush_stt_buffer(buffer, force=True)
    assert not buffer


def reopen_observations() -> float:
    return sum(
        sample.value for sample in soniox_idle_metrics().latency.collect()[0].samples if sample.name.endswith('_count')
    )


@pytest.mark.asyncio
async def test_unset_flag_keeps_inplace_reopen_for_first_text(monkeypatch):
    """The shipped default must not delay first text with idle handling.

    Default-on reselect retired the serving leg at every idle onset and rebuilt
    through the full chain; at fleet scale that churn exhausted chains and
    terminated sessions, and first text waited for the user's next utterance
    (2026-10-27 listen bb5f6e7 regression, listenlat RCA). With the flag unset
    the waking speech is served by the in-place reopen instead: same logical
    leg, no teardown, and a reopen latency observation is recorded.
    """
    monkeypatch.delenv('STT_IDLE_REOPEN_COST_RESELECT_ENABLED', raising=False)
    actual, _, raws, _, _, old, idle, _ = await idle_receiver(monkeypatch, enabled=True, benched=True)
    monkeypatch.delenv('STT_IDLE_REOPEN_COST_RESELECT_ENABLED', raising=False)  # ship-shape: flag unset
    data = b'\x31\x01' * 1600
    try:
        await close_idle(idle)
        before = reopen_observations()
        await onset(actual, data)
        await until(lambda: idle.idle_cost_reselect_requested or idle._idle_since is None)
        assert idle.idle_cost_reselect_requested is False
        assert idle._idle_since is None
        serving = getattr(actual.stt_socket, 'connection', actual.stt_socket)
        assert serving is old  # same logical leg behind any tail wrapper; no teardown
        assert old.leg_outcome.reason != 'normal_close'
        await until(lambda: raws[-1]._ws.byte_count >= len(data))
        assert reopen_observations() == before + 1
    finally:
        await actual._drain_stt_sockets()
        await stop(raws)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'language,benched,enabled,modulate,expected',
    [
        ('en', False, True, False, 'parakeet'),
        ('en', True, True, False, 'soniox'),
        ('vi', False, True, False, 'soniox'),
        ('en', False, False, False, 'soniox'),
        ('en', True, True, True, 'modulate'),
    ],
)
async def test_idle_reopen_rechecks_cost_stage_language_and_kill_switch(
    monkeypatch, language, benched, enabled, modulate, expected
):
    actual, _, raws, legs, observations, old, idle, _ = await idle_receiver(
        monkeypatch, language=language, enabled=enabled, benched=benched, modulate=modulate
    )
    data = b'\x31\x01' * 1600
    try:
        # A former session failure cannot keep a now recovered target excluded.
        actual._stt_failed_providers.add('parakeet')
        actual._stt_failed_targets.add('parakeet-window')
        actual.recovery.episode_count = MAX_RECOVERY_EPISODES
        await close_idle(idle)
        await onset(actual, data)
        await until(lambda: idle.idle_cost_reselect_requested or len(raws) == 2)
        if enabled:
            assert await actual._failover_stt_socket()
        assert actual.host.stt_service.value == expected
        assert actual.recovery.episode_count == MAX_RECOVERY_EPISODES
        assert st._soniox_circuit.state == 'closed'
        if expected != 'parakeet':
            await until(lambda: raws[-1]._ws.byte_count == len(data))
            assert raws[-1]._ws.pcm == data
            assert raws[-1]._demand_wire.origin == 'idle_reopened'
        else:
            assert actual.stt_socket.window
        if enabled:
            assert old.retired_for_replay or old.leg_outcome.settled
            assert old.leg_outcome.reason == 'normal_close'
            assert all(item[5] != 'connection_lost' for item in observations)
    finally:
        await actual._drain_stt_sockets()
        for leg in legs:
            leg.finish()
        await stop(raws)


@pytest.mark.asyncio
@pytest.mark.parametrize('ring_enabled', [False, True])
async def test_idle_handoff_preserves_preroll_once_and_fences_old_text(monkeypatch, ring_enabled):
    from types import SimpleNamespace
    from utils.stt.resilient_stream import ResilientAudio

    actual, base, raws, _, _, old, idle, _ = await idle_receiver(monkeypatch, benched=True)
    prefix = b'\x21\x01' * 800
    frame = b'\x31\x01' * 1600
    start = 2160000
    if ring_enabled:
        actual._window_replay_audio = ResilientAudio(16000, strict_replay=True, recovery_enabled=True)
        actual._window_replay_started = True
        actual._window_replay_audio.append(prefix, start - 800)
    # Model the real VAD's admitted onset, including an earlier pre-roll span.
    output = SimpleNamespace(
        audio_to_send=prefix + frame,
        send_spans=((start - 800, 2400),),
        is_speech=True,
        should_finalize=False,
    )
    old.gate = SimpleNamespace(
        process_audio=lambda *args, **kwargs: output,
        mode='active',
        consume_speech_ms_delta=lambda: 100,
        remap_segments=lambda segments: None,
    )
    try:
        await close_idle(idle)
        await onset(actual, frame, start)
        await until(lambda: idle.idle_cost_reselect_requested)
        assert await actual._failover_stt_socket()
        await until(lambda: raws[-1]._ws.byte_count == len(prefix + frame))
        assert raws[-1]._ws.pcm == prefix + frame
        before = len(base.emitted)
        raws[0]._stream_transcript([{'text': 'stale', 'start': 0, 'end': 0.1, 'speaker': '0'}])
        assert len(base.emitted) == before
        raws[-1]._stream_transcript([{'text': 'continued', 'start': 0, 'end': 0.15, 'speaker': '0'}])
        assert [item['text'] for item in base.emitted] == ['continued']
    finally:
        await actual._drain_stt_sockets()
        await stop(raws)


@pytest.mark.asyncio
async def test_recovered_parakeet_still_requires_user_allocation(monkeypatch):
    actual, _, raws, _, _, _, idle, _ = await idle_receiver(monkeypatch)
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '0')
    data = b'\x31\x01' * 1600
    try:
        await close_idle(idle)
        await onset(actual, data)
        await until(lambda: idle.idle_cost_reselect_requested)
        assert await actual._failover_stt_socket()
        assert actual.host.stt_service == st.STTService.soniox
        await until(lambda: raws[-1]._ws.byte_count == len(data))
        assert raws[-1]._ws.pcm == data
    finally:
        await actual._drain_stt_sockets()
        await stop(raws)


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', [True, False])
@pytest.mark.parametrize('unit_budget', [True, False])
async def test_last_funded_idle_onset_is_charged_once_and_reaches_successor(monkeypatch, enabled, unit_budget):
    from utils import stt_cap_dispatch as cap
    from unittest.mock import AsyncMock, Mock

    actual, _, raws, _, _, old, idle, _ = await idle_receiver(monkeypatch, benched=True, enabled=enabled)
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    admission = cap.LiveAdmission('synthetic')
    admission.managed, admission.remaining = True, 0.1
    if unit_budget:
        admission.remaining_units = 0.1 * cap._units_per_second('soniox')
    admission.reason = 'plan_within_allowance'
    recorded = Mock()
    monkeypatch.setattr(cap, 'record_audio', recorded)
    actual.cap_admission = admission
    old.raw = cap.CapSocket(admission, 'soniox', 16000, AsyncMock(), idle)
    monkeypatch.setattr(st, 'process_audio_soniox', cap.live_provider('soniox', 1)(st.process_audio_soniox))
    data = b'\x31\x01' * 1600
    try:
        await close_idle(idle)
        await onset(actual, data)
        await until(lambda: idle.idle_cost_reselect_requested or len(raws) == 2)
        if enabled:
            # The suspended vendor has not received this PCM. Its admission
            # cannot consume the final allowance before the successor opens.
            assert admission.remaining == pytest.approx(0.1)
            assert await actual._failover_stt_socket()
        await until(lambda: raws[-1]._ws.byte_count == len(data))
        assert raws[-1]._ws.pcm == data
        assert admission.remaining == 0
        if unit_budget:
            assert admission.remaining_units == 0
        assert len([call for call in recorded.call_args_list if call.args[:2] == ('live', 'accepted')]) == 1
        assert not actual.host.state.stt_terminal_failure
    finally:
        await actual._drain_stt_sockets()
        await stop(raws)


@pytest.mark.parametrize('origin', telemetry.TRANSPORT_ORIGINS)
def test_wire_and_connected_origin_is_pinned_and_bounded(monkeypatch, origin):
    tick = [100.0]
    monkeypatch.setattr(telemetry, 'monotonic', lambda: tick[0])
    demand_token = telemetry.current_demand.set(telemetry.DemandTelemetry('ineligible'))
    token = telemetry.current_transport_origin.set(origin)
    try:
        wire = telemetry.create_wire_meter('soniox', 16000)
        connected = telemetry.create_connected_meter()
        labels = dict(demand_cohort='ineligible', origin=origin)
        before_wire = telemetry.WIRE_AUDIO.labels(provider='soniox', **labels)._value.get()
        before_connected = telemetry.SONIOX_CONNECTED.labels(**labels)._value.get()
        telemetry.current_transport_origin.set('unbounded-input')
        wire.written(b'\x01\x00' * 16000)
        tick[0] += 6
        connected.flush(close=True)
        connected.flush(close=True)
        assert telemetry.WIRE_AUDIO.labels(provider='soniox', **labels)._value.get() == before_wire + 1
        assert telemetry.SONIOX_CONNECTED.labels(**labels)._value.get() == before_connected + 6
        assert telemetry.create_wire_meter('soniox', 16000).origin == 'initial'
    finally:
        telemetry.current_transport_origin.reset(token)
        telemetry.current_demand.reset(demand_token)


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['success', 'error', 'cancel'])
async def test_legacy_failover_pins_replacement_meters_and_restores_context(outcome):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    raws, wires = [], []

    async def rebuild():
        raw = SafeSonioxSocket(Transport(), lambda _: None, asyncio.get_running_loop())
        raws.append(raw)
        wires.append(telemetry.create_wire_meter('deepgram', 16000))
        if outcome == 'error':
            raise RuntimeError('synthetic dial failure')
        if outcome == 'cancel':
            raise asyncio.CancelledError()
        return True

    receiver = SimpleNamespace(
        recovery=None,
        _stt_failover_lock=asyncio.Lock(),
        _stt_recovery_exhausted=False,
        stt_socket=SimpleNamespace(is_connection_dead=True, _finishing=False),
        _reconnect_stt_socket_locked=AsyncMock(return_value=False),
        _rebuild_stt_socket_locked=rebuild,
    )
    token = telemetry.current_transport_origin.set('initial')
    try:
        if outcome == 'success':
            assert await ListenReceiver._failover_stt_socket(receiver)
        else:
            with pytest.raises(RuntimeError if outcome == 'error' else asyncio.CancelledError):
                await ListenReceiver._failover_stt_socket(receiver)
        assert telemetry.current_transport_origin.get() == 'initial'
        assert wires[0].origin == 'replacement'
        assert raws[0]._demand_wire.origin == 'replacement'
        assert raws[0]._connected_meter.origin == 'replacement'
    finally:
        telemetry.current_transport_origin.reset(token)
        await stop(raws)
