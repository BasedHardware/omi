"""One idle-onset return to Parakeet for English sessions a transient exit left on Soniox.

2026-11-01 (prod, aggregates): English-primary was 29% of Soniox segments while
parakeet-window sat at stage 100; the session-local exclusion keeps a session on
Soniox for its whole life once a Parakeet exit (circuit_open, a censored death)
moved it. Full reselect at every onset is the 2026-10-27 regression, so the
return is once per session, English only, and only when Parakeet is
window-eligible, admitting, cooled down and at stage 100.
"""

import pytest

from tests.unit.test_parakeet_window_live import runtime, Client  # noqa: F401
from tests.unit.test_live_cost_router import controls  # noqa: F401
from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401
from tests.unit.test_live_replay_provider_pairs import stop, until
from tests.unit.test_soniox_idle_cost_reselect import close_idle, idle_receiver, onset
from utils.stt import parakeet_window as window, streaming as st
from utils.stt.live_gate import GateState

DATA = b'\x31\x01' * 1600


async def failback_receiver(monkeypatch, **kwargs):
    rig = await idle_receiver(monkeypatch, enabled=False, **kwargs)
    monkeypatch.delenv('STT_IDLE_REOPEN_COST_RESELECT_ENABLED', raising=False)  # ship-shape: reselect off
    actual = rig[0]
    # The session left Parakeet earlier: the exclusion that used to pin it on Soniox.
    actual._stt_failed_providers.add('parakeet')
    actual._stt_failed_targets.add('parakeet-window')
    return rig


@pytest.mark.asyncio
async def test_english_session_returns_to_parakeet_once_at_idle_onset(monkeypatch):
    actual, _, raws, legs, observations, old, idle, _ = await failback_receiver(monkeypatch)
    try:
        await close_idle(idle)
        await onset(actual, DATA)
        await until(lambda: idle.idle_cost_reselect_requested or idle._idle_since is None)
        assert idle.idle_cost_reselect_requested is True
        assert await actual._failover_stt_socket()
        assert actual.host.stt_service.value == 'parakeet'
        assert actual.stt_socket.window
        assert old.leg_outcome.reason == 'normal_close'  # planned boundary, not provider evidence
        assert all(item[5] != 'connection_lost' for item in observations)
    finally:
        await actual._drain_stt_sockets()
        for leg in legs:
            leg.finish()
        await stop(raws)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'case',
    ['spent', 'kill_switch', 'non_english', 'benched', 'trial_stage', 'circuit_open', 'admission_full'],
)
async def test_failback_keeps_inplace_reopen_when_not_due(monkeypatch, case):
    language = 'vi' if case == 'non_english' else 'en'
    actual, _, raws, legs, _, old, idle, states = await failback_receiver(monkeypatch, language=language)
    if case == 'spent':
        actual._managed_live_chain.parakeet_failbacks = 1
    elif case == 'kill_switch':
        monkeypatch.setenv('STT_IDLE_PARAKEET_FAILBACK_ENABLED', 'false')
    elif case == 'benched':
        states['parakeet-window'] = GateState(stage=0, until=1e20)
    elif case == 'trial_stage':
        states['parakeet-window'] = GateState(stage=25)
    elif case == 'circuit_open':
        monkeypatch.setattr(st, 'parakeet_family_circuit_state', lambda: 'open')
    elif case == 'admission_full':
        monkeypatch.setattr(window.admission, 'available', lambda: False)
    try:
        await close_idle(idle)
        await onset(actual, DATA)
        await until(lambda: idle.idle_cost_reselect_requested or idle._idle_since is None)
        assert idle.idle_cost_reselect_requested is False
        serving = getattr(actual.stt_socket, 'connection', actual.stt_socket)
        assert serving is old  # same logical leg: the purpose-built in-place reopen
        await until(lambda: raws[-1]._ws.byte_count >= len(DATA))
    finally:
        await actual._drain_stt_sockets()
        for leg in legs:
            leg.finish()
        await stop(raws)
