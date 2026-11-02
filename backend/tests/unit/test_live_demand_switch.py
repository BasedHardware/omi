"""Healthy switch acceptance through real managed legs and capture replay."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.unit.test_parakeet_window_live import runtime, Client  # noqa: F401
from tests.unit.test_live_replay_provider_pairs import setup_receiver, stop, until
from tests.unit.test_live_cost_router import controls  # noqa: F401
from routers.listen.demand_routing import LiveDemandRouting
from routers.listen import demand_routing
from config.live_demand import resolve_live_demand
from config.live_stt_replay import DEFAULT_REPLAY_PREFIX_MARGIN_SECONDS, REPLAY_PREFIX_MARGIN_ENV
from tests.unit.fixtures.replay_clock import VirtualClock
from utils.audio_timeline import CaptureTimeline
from utils.stt import recovery_state, replay_delivery, resilient_stream
from utils.stt import streaming as st, parakeet_window as window, live_session
from utils.stt.recovery_state import RecoveryState
from utils.stt.resilient_stream import ResilientAudio


async def demand_receiver(monkeypatch):
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')
    monkeypatch.setenv('STT_LIVE_DEMAND_ENABLED', 'false')
    actual, base, raws, legs, observations = await setup_receiver(
        monkeypatch, ['soniox', 'parakeet-window'], source='soniox'
    )
    actual._window_replay_audio = ResilientAudio(16000, strict_replay=True, recovery_enabled=True)
    actual._window_replay_started = True
    demand = LiveDemandRouting(actual, eligible=True)
    actual.live_demand = demand
    monkeypatch.setattr(demand, 'publish', AsyncMock(return_value=False))
    monkeypatch.setattr(demand_routing, 'realtime_consumer_active', AsyncMock(return_value=False))
    monkeypatch.setenv('STT_LIVE_DEMAND_ENABLED', 'true')
    monkeypatch.setenv('STT_LIVE_DEMAND_PERCENT', '100')
    demand.policy.observe({'foreground': False, 'transcript_visible': False})
    demand.policy.decide(enabled=True, visible=False, consumer=False)
    return actual, base, raws, legs, observations


@pytest.mark.asyncio
async def test_vendor_window_vendor_reentry_and_old_callback_fence(monkeypatch):
    actual, base, raws, legs, _ = await demand_receiver(monkeypatch)
    initial = actual.stt_socket
    client = Client()
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    try:
        assert await actual._switch_live_demand('parakeet')
        cheap = actual.stt_socket
        assert actual.host.stt_model == 'parakeet-window'
        assert initial.retired_for_replay
        # Healthy policy handovers leave the failure episode budget unchanged.
        assert actual.recovery.episode_count == 0
        actual.recovery.note_healthy_connection(cheap)
        actual.recovery.state = RecoveryState.recovered
        actual.live_demand.policy.observe({'foreground': True, 'transcript_visible': True})
        actual.live_demand.policy.decide(enabled=True, visible=True, consumer=False)
        assert await actual._switch_live_demand('vendor')
        assert actual.host.stt_service == st.STTService.soniox
        assert cheap.retired_for_replay
        raws[0]._stream_transcript([{'text': 'retired', 'start': 0, 'end': 1, 'speaker': 'speaker_0'}])
        assert not base.emitted
        # Another hidden interval can re-enter the same healthy cheap target.
        actual.recovery.state = RecoveryState.recovered
        actual.live_demand.policy.observe({'foreground': False, 'transcript_visible': False})
        actual.live_demand.policy.decide(enabled=True, visible=False, consumer=False)
        assert await actual._switch_live_demand('parakeet')
        assert actual.recovery.episode_count == 0
    finally:
        actual.stt_socket.finish()
        await stop(raws)


@pytest.mark.asyncio
@pytest.mark.parametrize('refusal', ['capacity', 'pressure'])
async def test_refused_window_keeps_vendor_serving(monkeypatch, refusal):
    actual, _, raws, _, _ = await demand_receiver(monkeypatch)
    initial = actual.stt_socket
    if refusal == 'capacity':
        monkeypatch.setattr(window.admission, 'available', lambda: False)
    else:
        monkeypatch.setattr(window.batch_pressure, 'allows', lambda *_: False)
    try:
        assert not await actual._switch_live_demand('parakeet')
        assert actual.stt_socket is initial
        assert actual.host.stt_service == st.STTService.soniox
        assert not initial.retired_for_replay and not initial.is_connection_dead
        assert actual.live_demand.policy.fallback
        assert not actual.live_demand.window_permitted
    finally:
        actual.stt_socket.finish()
        await stop(raws)


@pytest.mark.asyncio
async def test_window_to_vendor_replays_exact_capture_and_fences_duplicates(monkeypatch):
    actual, base, raws, _, _ = await demand_receiver(monkeypatch)
    try:
        assert await actual._switch_live_demand('parakeet')
        cheap = actual.stt_socket
        # Unanswered sample markers must reach the vendor once and in order.
        pcm = b'\x12\x01' * 1600 + b'\x13\x01' * 1600
        actual._window_replay_audio.append(pcm, 0)
        actual.live_demand.policy.observe({'foreground': True, 'transcript_visible': True})
        actual.live_demand.policy.decide(enabled=True, visible=True, consumer=False)
        actual.recovery.state = RecoveryState.recovered
        assert await actual._switch_live_demand('vendor')
        await until(lambda: raws[-1]._ws.byte_count == len(pcm))
        assert raws[-1]._ws.pcm == pcm
        assert cheap.retired_for_replay
        raws[-1]._stream_transcript([{'text': 'new', 'start': 0, 'end': 0.2, 'speaker': 'speaker_0'}])
        assert [segment['text'] for segment in base.emitted] == ['new']
    finally:
        actual.stt_socket.finish()
        await stop(raws)


@pytest.mark.asyncio
async def test_window_degradation_recovers_vendor_with_capture_preserved(monkeypatch):
    actual, base, raws, _, _ = await demand_receiver(monkeypatch)
    try:
        assert await actual._switch_live_demand('parakeet')
        cheap = actual.stt_socket
        pcm = b'\x31\x01' * 3200
        actual._window_replay_audio.append(pcm, 0)
        cheap.raw.fail('first_text_deadline')
        actual.live_demand.policy.fallback = True
        actual.live_demand.policy.window_permitted = False
        assert await actual._failover_stt_socket()
        assert actual.host.stt_service == st.STTService.soniox
        await until(lambda: raws[-1]._ws.byte_count == len(pcm))
        assert raws[-1]._ws.pcm == pcm
    finally:
        actual.stt_socket.finish()
        await stop(raws)


@pytest.mark.asyncio
async def test_visible_report_during_dial_keeps_vendor(monkeypatch):
    actual, _, raws, _, _ = await demand_receiver(monkeypatch)
    old = actual.stt_socket
    session = actual._managed_live_chain
    connect = session.connect

    async def changed(*args, **kwargs):
        candidate = await connect(*args, **kwargs)
        actual.live_demand.policy.observe({'foreground': True, 'transcript_visible': True})
        actual.live_demand.policy.window_permitted = False
        return candidate

    monkeypatch.setattr(session, 'connect', changed)
    try:
        assert not await actual._switch_live_demand('parakeet')
        assert actual.stt_socket is old and not old.retired_for_replay
        assert actual.host.stt_service == st.STTService.soniox
    finally:
        actual.stt_socket.finish()
        await stop(raws)


@pytest.mark.asyncio
async def test_vendor_candidate_failure_keeps_window_and_audio(monkeypatch):
    actual, _, raws, _, _ = await demand_receiver(monkeypatch)
    try:
        assert await actual._switch_live_demand('parakeet')
        cheap = actual.stt_socket
        actual.live_demand.policy.window_permitted = False
        actual.recovery.state = RecoveryState.recovered
        monkeypatch.setattr(actual._managed_live_chain, 'connect', AsyncMock(side_effect=OSError('dial failed')))
        assert not await actual._switch_live_demand('vendor')
        assert actual.stt_socket is cheap and not cheap.retired_for_replay
        assert actual.host.stt_model == 'parakeet-window'
    finally:
        actual.stt_socket.finish()
        await stop(raws)


@pytest.mark.asyncio
@pytest.mark.parametrize('late_demand', ['other_client', 'consumer', 'rollback'])
async def test_demand_rechecked_before_retiring_vendor(monkeypatch, late_demand):
    actual, _, raws, _, _ = await demand_receiver(monkeypatch)
    old = actual.stt_socket
    if late_demand == 'other_client':
        monkeypatch.setattr(actual.live_demand, 'publish', AsyncMock(return_value=True))
    elif late_demand == 'consumer':
        monkeypatch.setattr(demand_routing, 'realtime_consumer_active', AsyncMock(return_value=True))
    else:
        monkeypatch.setenv('STT_LIVE_DEMAND_ENABLED', 'false')
    try:
        assert not await actual._switch_live_demand('parakeet')
        assert actual.stt_socket is old and not old.retired_for_replay
        assert actual.host.stt_service == st.STTService.soniox
    finally:
        actual.stt_socket.finish()
        await stop(raws)


@pytest.mark.asyncio
async def test_window_allocation_kill_retains_vendor(monkeypatch):
    actual, _, raws, _, _ = await demand_receiver(monkeypatch)
    old = actual.stt_socket
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '0')
    try:
        assert not await actual._switch_live_demand('parakeet')
        assert actual.stt_socket is old and not old.retired_for_replay
    finally:
        actual.stt_socket.finish()
        await stop(raws)


@pytest.mark.asyncio
async def test_replay_failure_after_fence_recovers_vendor_without_losing_prefix(monkeypatch):
    actual, _, raws, _, _ = await demand_receiver(monkeypatch)
    pcm = b'\x41\x01' * 3200
    actual._window_replay_audio.append(pcm, 0)
    pump = actual._pump_replacement

    async def fail_cheap(raw, epoch, hop, replay, ring, previous, **kwargs):
        if actual.host.stt_service == st.STTService.parakeet:
            raw.raw.fail('send_failed')
            await actual._reject_candidate(raw, epoch, hop, previous)
            return False
        return await pump(raw, epoch, hop, replay, ring, previous, **kwargs)

    monkeypatch.setattr(actual, '_pump_replacement', fail_cheap)
    try:
        assert not await actual._switch_live_demand('parakeet')
        assert actual.host.stt_service == st.STTService.soniox
        assert actual.live_demand.policy.fallback
        await until(lambda: raws[-1]._ws.byte_count == len(pcm))
        assert raws[-1]._ws.pcm == pcm
    finally:
        actual.stt_socket.finish()
        await stop(raws)


@pytest.mark.asyncio
async def test_disconnect_during_fresh_demand_check_releases_candidate(monkeypatch):
    actual, _, raws, _, _ = await demand_receiver(monkeypatch)
    old = actual.stt_socket
    monkeypatch.setattr(actual.live_demand, 'can_admit_window', AsyncMock(side_effect=asyncio.CancelledError))
    try:
        with pytest.raises(asyncio.CancelledError):
            await actual._switch_live_demand('parakeet')
        assert window.admission.active == 0
        assert actual.stt_socket is old and not old.retired_for_replay
        assert actual.host.stt_service == st.STTService.soniox
    finally:
        actual.stt_socket.finish()
        await stop(raws)


@pytest.mark.asyncio
async def test_live_capture_during_healthy_switch_does_not_wait_on_prefix(monkeypatch):
    actual, _, raws, _, _ = await demand_receiver(monkeypatch)
    prefix = b'\x51\x01' * 3200
    tail = b'\x52\x01' * 480
    actual.capture_timeline = CaptureTimeline(sample_rate=16000)
    actual.capture_timeline.accept(prefix, 1000, 1)
    actual._window_replay_audio.append(prefix, 0)
    entered, resume = asyncio.Event(), asyncio.Event()
    pump = actual._pump_replacement

    async def held(raw, *args, **kwargs):
        if actual.host.stt_service == st.STTService.parakeet:
            entered.set()
            await resume.wait()
        return await pump(raw, *args, **kwargs)

    monkeypatch.setattr(actual, '_pump_replacement', held)
    switching = asyncio.create_task(actual._switch_live_demand('parakeet'))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        actual.capture_timeline.accept(tail, 1000.2, 1.2)
        actual._stt_buffer_start_sample = len(prefix) // 2
        buffer = bytearray(tail)
        await asyncio.wait_for(actual._flush_stt_buffer(buffer, force=True), 0.5)
        assert not buffer and not switching.done()
        resume.set()
        assert await switching
        actual.recovery.state = RecoveryState.recovered
        actual.live_demand.policy.window_permitted = False
        assert await actual._switch_live_demand('vendor')
        await until(lambda: raws[-1]._ws.byte_count == len(prefix + tail))
        assert raws[-1]._ws.pcm == prefix + tail
    finally:
        resume.set()
        switching.cancel()
        await asyncio.gather(switching, return_exceptions=True)
        actual.stt_socket.finish()
        await stop(raws)


@pytest.mark.asyncio
async def test_default_hidden_dwell_fits_quiet_capture_replay_budget(monkeypatch):
    actual, _, raws, _, _ = await demand_receiver(monkeypatch)
    timer = VirtualClock()
    monkeypatch.setattr(replay_delivery, 'clock', lambda: timer.now)
    monkeypatch.setattr(replay_delivery, 'sleep', timer.sleep)
    monkeypatch.setattr(recovery_state, 'clock', lambda: timer.now)
    monkeypatch.setattr(resilient_stream, 'clock', lambda: timer.now)
    monkeypatch.setattr(replay_delivery, 'REPLAY_PREFIX_SECONDS', 20.0)
    monkeypatch.delenv('STT_LIVE_DEMAND_MIN_DWELL_SECONDS', raising=False)
    monkeypatch.delenv(REPLAY_PREFIX_MARGIN_ENV, raising=False)
    dwell = resolve_live_demand().dwell_seconds
    assert dwell < replay_delivery.REPLAY_PREFIX_SECONDS - DEFAULT_REPLAY_PREFIX_MARGIN_SECONDS
    # No emitted vendor anchor: all pre-dwell capture remains replay-owned.
    actual._window_replay_audio.append(b'\x00\x00' * int(dwell * 16000), 0)
    old = actual.stt_socket
    try:
        assert await actual._switch_live_demand('parakeet')
        assert old.retired_for_replay
        assert actual.host.stt_model == 'parakeet-window'
        assert not actual.live_demand.policy.fallback
    finally:
        actual.stt_socket.finish()
        await stop(raws)


@pytest.mark.asyncio
@pytest.mark.parametrize('unanswered_seconds, admitted', [(19.0, True), (19.5, False), (20.0, False)])
async def test_handover_refuses_unanswered_capture_past_the_margined_budget(monkeypatch, unanswered_seconds, admitted):
    # A handover replays the whole unanswered ring uncut, so it refuses — and
    # keeps the healthy source — past the same wall-minus-margin the failure
    # path holds back; exactly-the-wall capture would miss the wall at 1x.
    actual, _, raws, _, _ = await demand_receiver(monkeypatch)
    timer = VirtualClock()
    monkeypatch.setattr(replay_delivery, 'clock', lambda: timer.now)
    monkeypatch.setattr(replay_delivery, 'sleep', timer.sleep)
    monkeypatch.setattr(recovery_state, 'clock', lambda: timer.now)
    monkeypatch.setattr(resilient_stream, 'clock', lambda: timer.now)
    monkeypatch.setattr(replay_delivery, 'REPLAY_PREFIX_SECONDS', 20.0)
    monkeypatch.delenv(REPLAY_PREFIX_MARGIN_ENV, raising=False)
    actual._window_replay_audio.append(b'\x00\x00' * int(unanswered_seconds * 16000), 0)
    old = actual.stt_socket
    try:
        assert await actual._switch_live_demand('parakeet') is admitted
        if admitted:
            assert old.retired_for_replay
            assert actual.host.stt_model == 'parakeet-window'
            assert not actual.live_demand.policy.fallback
        else:
            assert actual.stt_socket is old
            assert actual.host.stt_service == st.STTService.soniox
            assert not old.retired_for_replay and not old.is_connection_dead
            assert actual.live_demand.policy.fallback
    finally:
        actual.stt_socket.finish()
        await stop(raws)


@pytest.mark.asyncio
async def test_dead_cheap_candidate_during_fresh_check_pins_healthy_vendor(monkeypatch):
    actual, _, raws, _, _ = await demand_receiver(monkeypatch)
    old = actual.stt_socket
    opened = []
    connect = actual._managed_live_chain.connect

    async def tracked(*args, **kwargs):
        candidate = await connect(*args, **kwargs)
        opened.append(candidate)
        return candidate

    async def degraded():
        opened[-1].raw.fail('provider_5xx')
        return True

    monkeypatch.setattr(actual._managed_live_chain, 'connect', tracked)
    monkeypatch.setattr(actual.live_demand, 'can_admit_window', degraded)
    try:
        assert not await actual._switch_live_demand('parakeet')
        assert actual.stt_socket is old and not old.is_connection_dead
        assert actual.live_demand.policy.fallback and not actual.live_demand.window_permitted
        assert not await actual._switch_live_demand('parakeet')
        assert len(opened) == 1
    finally:
        actual.stt_socket.finish()
        await stop(raws)


@pytest.mark.asyncio
async def test_previous_vendor_death_does_not_condemn_healthy_cheap_candidate(monkeypatch):
    actual, _, raws, _, _ = await demand_receiver(monkeypatch)
    old = actual.stt_socket

    async def previous_died():
        old.fail('send_failed')
        return True

    monkeypatch.setattr(actual.live_demand, 'can_admit_window', previous_died)
    try:
        assert not await actual._switch_live_demand('parakeet')
        assert actual.stt_socket is old and old.is_connection_dead
        assert not actual.live_demand.policy.fallback
        assert window.admission.active == 0
    finally:
        actual.stt_socket.finish()
        await stop(raws)
