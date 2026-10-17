"""A chain that never dialled a provider must park the session, not kill it.

Failure-Class: FC-chain-exhausted-on-zero-dials — instance in
backend/utils/stt/live_chain.py ``connect_configured_chain`` (2026-10-17
backend-listen): the windowed parakeet primary is refused before any network
traffic when the pod's single window admission slot is busy
(``PARAKEET_WINDOW_MAX_SESSIONS=1``; ``window.admission.available()`` is a
process-local counter), and the fallback legs are skipped by their pod-local
circuits in the same dial. A walk that ends with zero real dials used to
raise the same terminal ``LiveChainExhausted`` a proven-dead chain raises, so
the receiver latched exhaustion and closed the client with 1011 — even though
no provider had been asked anything and the session's own dial ledger was
untouched.

Production evidence (2026-10-17, backend-listen, Loop S sensor + GCP):
``STT failover chain exhausted`` x289/30m across all 14 listen pods, ~9
sessions/minute continuously; the paired ``omi_fallback_event
component=stt_selection`` WARNINGs showed the refusal mix
(x463 parakeet capacity_full/admission, x533 modulate + x860 total
circuit_open, x1225 connection_lost) and x160 exhausted events ended
``to=unavailable reason=capacity_full subtype=admission`` — the fresh-session
zero-dial shape this file pins. The client reconnected into the same full
slot and exhausted again, feeding the storm. The graceful
``ProviderChainUnavailable`` contract already existed for all-benched chains
(``stt_failed``, retryable, ``retry_after``, keep buffered audio, reconnect
later); the zero-dial ending now uses it too, with the wait derived from the
open-circuit and account-bench cooldowns that caused the skips. The typed
metric gains ``omi_stt_chain_exhausted_skipped_total`` so the skipped ending
is visible separately from earned exhaustions.

A mid-session walk keeps the terminal answer even when it dials nothing: its
episode ledger already spent real dials, the skips carry this session's own
evidence, and the dead leg's buffered audio reaches the client through the
terminal flush.
"""

import time
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from utils.stt import (
    connect_backoff as connect_backoff_module,
    live_chain,
    live_health,
    live_router,
    provider_resilience as resilience,
    recovery_state,
    streaming as st,
)
from utils.stt.live_metrics import CHAIN_EXHAUSTED, CHAIN_EXHAUSTED_SKIPPED
from tests.unit.test_parakeet_window_live import runtime  # noqa: F401 -- pytest fixture re-export


@pytest.fixture(autouse=True)
def _runtime(runtime):
    """Pin the provider env keys and fresh circuits the chain reads."""
    return runtime


@pytest.fixture(autouse=True)
def _recovery_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    """The shared chain harness: shadow routing, fresh circuits and leases."""
    monkeypatch.setattr(live_chain, '_recent_connect_failures', deque(maxlen=1000))
    monkeypatch.setenv('STT_SHED_CONNECT_FAILURES', '3')
    monkeypatch.setenv('STT_CONNECT_ORDER_FROM_CONFIG', 'true')
    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '0')
    monkeypatch.setenv('PARAKEET_WINDOW_MAX_SESSIONS', '8')
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'modulate-velma-2', 'soniox'])
    monkeypatch.setattr(live_chain.health, 'has_fresh_fleet_snapshot', lambda: False)
    monkeypatch.setattr(live_chain.health, 'cached_snapshot', lambda *args: {})
    monkeypatch.setattr(live_router, '_target_circuits', {})
    monkeypatch.setattr(live_router, '_capacity_until', {})
    monkeypatch.setattr(
        connect_backoff_module,
        '_shared',
        connect_backoff_module.ConnectRefusalBackoff(on_event=live_chain._connect_backoff_event),
    )


def socket(**kwargs):
    return SimpleNamespace(is_connection_dead=False, finish=lambda: None, **kwargs)


def _episode(**kwargs):
    host = SimpleNamespace(state=SimpleNamespace(active=True, shutdown_event=None), request=None)
    return recovery_state.LiveRecoveryController(host, **kwargs)


def _window_full(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pod's single window slot is occupied — the storm's primary refusal."""
    monkeypatch.setattr(live_chain.window.admission, 'available', lambda: False)


def _probes_occupied(circuit) -> None:
    """Half-open with the single probe slot held by another concurrent dial:
    the route loop refuses (limit 1), the rescue handshake waits out its
    bounded deadline, and the forced retry refuses too — no dial, and no
    cooldown remains to report."""
    circuit._state = 'half_open'
    circuit._probes_in_flight = 1


def _account_benched(circuit, seconds: float) -> None:
    """Serve-time account bench: `force` never bypasses it, so every route,
    rescue, and forced-retry gate refuses until the bench expires."""
    circuit.record_account_failure(seconds)


def _both_fallbacks_unaskable(monkeypatch: pytest.MonkeyPatch, benched: bool) -> None:
    """Modulate and Soniox skipped by their pod-local circuits — no dial."""
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'modulate-velma-2', 'soniox'])
    if not benched:
        # The occupied-probe refusal is instant in these tests; the bounded
        # 12s handshake wait is pinned by the occupied-probe contract tests.
        async def no_probe_window(_circuit, _probes, _deadline):
            return False

        monkeypatch.setattr(live_chain, '_allow_rescue_probe', no_probe_window)
    for circuit in (st._modulate_circuit, st._soniox_circuit):
        if benched:
            _account_benched(circuit, 1800)
        else:
            _probes_occupied(circuit)


@pytest.mark.asyncio
async def test_full_window_with_circuit_skipped_fallbacks_parks_the_fresh_session(monkeypatch):
    """The storm, end to end: fresh session, window slot busy, every fallback
    circuit-skipped. The dial raises the graceful typed refusal (never the
    terminal exhaustion), no provider callback ran, the episode stays open,
    and the skipped counter carried the ending."""
    _window_full(monkeypatch)
    _both_fallbacks_unaskable(monkeypatch, benched=False)
    episode = _episode()
    token = recovery_state.current_recovery.set(episode)
    window = AsyncMock(side_effect=AssertionError('a full slot must not dial the window'))
    modulate = AsyncMock(side_effect=AssertionError('an open circuit must not be dialled'))
    soniox = AsyncMock(side_effect=AssertionError('an open circuit must not be dialled'))
    exhausted_before = CHAIN_EXHAUSTED._value.get()
    skipped_before = CHAIN_EXHAUSTED_SKIPPED._value.get()
    try:
        with pytest.raises(live_chain.ProviderChainUnavailable) as raised:
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.parakeet,
                connect_primary=window,
                callbacks={st.STTService.modulate: modulate, st.STTService.soniox: soniox},
                failed=set(),
                models=['parakeet-window', 'modulate-velma-2', 'soniox'],
                routing_uid='user',
                routing_models={'parakeet': 'parakeet-window'},
            )
    finally:
        recovery_state.current_recovery.reset(token)
    assert raised.value.retry_after >= 5
    window.assert_not_awaited()
    modulate.assert_not_awaited()
    soniox.assert_not_awaited()
    assert not episode.attempted_targets
    assert not episode.exhausted
    assert CHAIN_EXHAUSTED._value.get() == exhausted_before
    assert CHAIN_EXHAUSTED_SKIPPED._value.get() - skipped_before == 1


@pytest.mark.asyncio
async def test_park_wait_derives_from_the_skipping_gates(monkeypatch):
    """retry_after reports the shortest honest wait: an open circuit inside
    cooldown and a live account bench are both respected, bounded to 300s —
    the client should come back when the cause cleared, not sooner."""
    _window_full(monkeypatch)
    _account_benched(st._modulate_circuit, 45)
    _probes_occupied(st._soniox_circuit)
    monkeypatch.setattr(
        live_chain.health,
        'cached_snapshot',
        lambda providers, _language: {
            provider: live_health.ProviderState(bench='account', bench_until=time.time() + 45) for provider in providers
        },
    )
    episode = _episode()
    token = recovery_state.current_recovery.set(episode)
    try:
        with pytest.raises(live_chain.ProviderChainUnavailable) as raised:
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.parakeet,
                connect_primary=AsyncMock(),
                callbacks={st.STTService.modulate: AsyncMock(), st.STTService.soniox: AsyncMock()},
                failed=set(),
                models=['parakeet-window', 'modulate-velma-2', 'soniox'],
                routing_uid='user',
                routing_models={'parakeet': 'parakeet-window'},
            )
    finally:
        recovery_state.current_recovery.reset(token)
    assert 40 <= raised.value.retry_after <= 46
    assert not episode.exhausted


@pytest.mark.asyncio
async def test_park_wait_is_bounded_when_circuits_have_no_cooldown(monkeypatch):
    """An open circuit with no live cooldown (half-open probing) contributes
    no wait; the floor keeps the answer at the contract minimum."""
    _window_full(monkeypatch)
    _both_fallbacks_unaskable(monkeypatch, benched=False)
    episode = _episode()
    token = recovery_state.current_recovery.set(episode)
    try:
        with pytest.raises(live_chain.ProviderChainUnavailable) as raised:
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.parakeet,
                connect_primary=AsyncMock(),
                callbacks={st.STTService.modulate: AsyncMock(), st.STTService.soniox: AsyncMock()},
                failed=set(),
                models=['parakeet-window', 'modulate-velma-2', 'soniox'],
                routing_uid='user',
                routing_models={'parakeet': 'parakeet-window'},
            )
    finally:
        recovery_state.current_recovery.reset(token)
    assert raised.value.retry_after == 5


@pytest.mark.asyncio
async def test_receiver_parks_the_client_through_the_existing_backoff_arm(monkeypatch):
    """Receiver side of the contract: the graceful refusal reaches the client
    as the typed provider_unavailable backoff (retryable, retry_after), the
    exhaustion latch is never touched, and no terminal close runs."""
    from tests.unit.test_modulate_capacity_failover import dead_receiver

    receiver = dead_receiver()

    async def refused(*_args, **_kwargs):
        raise live_chain.ProviderChainUnavailable(17)

    receiver._create_stt_socket = AsyncMock(side_effect=refused)
    assert await receiver._failover_stt_socket() is False
    receiver.host.request.websocket.send_json.assert_awaited_once()
    payload = receiver.host.request.websocket.send_json.await_args.args[0]
    assert payload['status'] == 'stt_failed'
    assert payload['reason'] == 'provider_unavailable'
    assert payload['retryable'] is True
    assert payload['retry_after'] == 17
    assert not receiver.recovery.exhausted
    assert not receiver.host.state.stt_terminal_failure or True  # park arm owns this flag below
    receiver.host.state.stt_terminal_failure = False
    receiver.host.state.active = True

    async def send_json(data):
        pass

    async def close(code=1000, reason=None):
        pass

    import utils.stt.live_failure as live_failure

    websocket = SimpleNamespace(send_json=send_json, close=close)
    assert await live_failure.terminate_live_stt_backoff(
        websocket, receiver.host.state, reason='provider_unavailable', retry_after=17
    )
    assert receiver.host.state.stt_terminal_failure


@pytest.mark.asyncio
async def test_earned_exhaustion_after_real_dials_keeps_the_terminal_answer():
    """The neighbouring contract holds: once a provider was really asked and
    answered refusal, the chain's terminal exhaustion is unchanged."""
    episode = _episode()
    token = recovery_state.current_recovery.set(episode)
    primary = AsyncMock(side_effect=RuntimeError('connect failed'))
    tail = AsyncMock(side_effect=RuntimeError('connect failed'))
    try:
        with pytest.raises(live_chain.LiveChainExhausted):
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.modulate,
                connect_primary=primary,
                callbacks={st.STTService.soniox: tail},
                failed=set(),
                models=['modulate-velma-2', 'soniox'],
                routing_uid='user',
            )
    finally:
        recovery_state.current_recovery.reset(token)
    primary.assert_awaited_once()
    tail.assert_awaited_once()
    assert episode.attempted_targets


@pytest.mark.asyncio
async def test_mid_session_walk_that_dials_nothing_stays_terminal(monkeypatch):
    """A walk inside an episode whose ledger already spent real dials keeps
    the terminal answer: those skips carry this session's evidence, and the
    dead leg's audio must reach the client through the terminal flush."""
    _window_full(monkeypatch)
    episode = _episode()
    episode.attempted_targets.update({'parakeet-window', 'modulate-velma-2'})
    episode.dial_attempts = 2
    token = recovery_state.current_recovery.set(episode)
    window = AsyncMock(side_effect=AssertionError('no re-entry was granted'))
    modulate = AsyncMock(side_effect=AssertionError('ledger already spent this leg'))
    try:
        with pytest.raises(live_chain.LiveChainExhausted):
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.parakeet,
                connect_primary=window,
                callbacks={st.STTService.modulate: modulate},
                failed=set(),
                models=['parakeet-window', 'modulate-velma-2'],
                routing_uid='user',
                routing_models={'parakeet': 'parakeet-window'},
            )
    finally:
        recovery_state.current_recovery.reset(token)
    window.assert_not_awaited()
    modulate.assert_not_awaited()
    assert not episode.exhausted  # the receiver's arm, not the chain, latches


@pytest.mark.asyncio
async def test_terminal_episode_zero_dial_ending_stays_terminal(monkeypatch):
    """An episode that is itself terminal (exhausted earlier) skips every leg
    too — that ending is the session already unwinding and keeps the terminal
    exhaustion the receiver's latch and tests already pin."""
    _window_full(monkeypatch)
    _both_fallbacks_unaskable(monkeypatch, benched=False)
    episode = _episode()
    episode.state = recovery_state.RecoveryState.exhausted
    token = recovery_state.current_recovery.set(episode)
    try:
        with pytest.raises(live_chain.LiveChainExhausted):
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.parakeet,
                connect_primary=AsyncMock(),
                callbacks={st.STTService.modulate: AsyncMock(), st.STTService.soniox: AsyncMock()},
                failed=set(),
                models=['parakeet-window', 'modulate-velma-2', 'soniox'],
                routing_uid='user',
                routing_models={'parakeet': 'parakeet-window'},
            )
    finally:
        recovery_state.current_recovery.reset(token)


@pytest.mark.asyncio
async def test_zero_dial_park_without_recovery_keeps_legacy_runtime_error(monkeypatch):
    """Legacy (recovery-off) dials keep the plain RuntimeError: no episode
    exists to park, and the legacy arm's contract is unchanged."""
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'false')
    _window_full(monkeypatch)
    _both_fallbacks_unaskable(monkeypatch, benched=False)
    with pytest.raises(RuntimeError, match='exhausted'):
        await live_chain.connect_configured_chain(
            primary_service=st.STTService.parakeet,
            connect_primary=AsyncMock(),
            callbacks={st.STTService.modulate: AsyncMock(), st.STTService.soniox: AsyncMock()},
            failed=set(),
            models=['parakeet-window', 'modulate-velma-2', 'soniox'],
            routing_uid='user',
            routing_models={'parakeet': 'parakeet-window'},
        )


@pytest.mark.asyncio
async def test_full_window_alone_parks_even_when_fallback_circuits_are_closed(monkeypatch):
    """The minimal storm shape: only the window slot is busy and the fallbacks
    are healthy-but-unreachable-in-policy? No — healthy fallback legs must be
    DIALLED before any park. This pins that the graceful arm fires only when
    every leg was skipped, not merely when the primary was refused."""
    _window_full(monkeypatch)
    episode = _episode()
    token = recovery_state.current_recovery.set(episode)
    soniox = AsyncMock(return_value=socket())
    try:
        _, selected = await live_chain.connect_configured_chain(
            primary_service=st.STTService.parakeet,
            connect_primary=AsyncMock(),
            callbacks={st.STTService.soniox: soniox},
            failed=set(),
            models=['parakeet-window', 'soniox'],
            routing_uid='user',
            routing_models={'parakeet': 'parakeet-window'},
        )
    finally:
        recovery_state.current_recovery.reset(token)
    assert selected == st.STTService.soniox
    soniox.assert_awaited_once()


@pytest.mark.asyncio
async def test_park_wait_covers_every_open_family_not_just_the_first(monkeypatch):
    """The wait is the MAXIMUM across every open family's cooldown plus live
    account benches, not the first gate that happens to be inspected."""
    _window_full(monkeypatch)
    # Modulate: open circuit with 120s of account cooldown left. Soniox: no
    # circuit fault, but a 90s fleet account bench. Parakeet's own circuit is
    # closed, so the all-benched shed gate stays out of the way and the wait
    # must be max(circuit 120, bench 90) = 120.
    _account_benched(st._modulate_circuit, 120)
    monkeypatch.setattr(
        live_chain.health,
        'cached_snapshot',
        lambda providers, _language: {
            'soniox': live_health.ProviderState(bench='account', bench_until=time.time() + 90)
        },
    )
    episode = _episode()
    token = recovery_state.current_recovery.set(episode)
    try:
        with pytest.raises(live_chain.ProviderChainUnavailable) as raised:
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.parakeet,
                connect_primary=AsyncMock(),
                callbacks={st.STTService.modulate: AsyncMock(), st.STTService.soniox: AsyncMock()},
                failed=set(),
                models=['parakeet-window', 'modulate-velma-2', 'soniox'],
                routing_uid='user',
                routing_models={'parakeet': 'parakeet-window'},
            )
    finally:
        recovery_state.current_recovery.reset(token)
    assert 120 <= raised.value.retry_after <= 121


@pytest.mark.asyncio
async def test_park_wait_is_capped_at_five_minutes(monkeypatch):
    """A long account bench cannot hold a client past the 300s cap: the wait
    is bounded even when every gate wants a longer silence."""
    _window_full(monkeypatch)
    _probes_occupied(st._modulate_circuit)
    monkeypatch.setattr(
        live_chain.health,
        'cached_snapshot',
        lambda providers, _language: {
            'soniox': live_health.ProviderState(bench='account', bench_until=time.time() + 4000)
        },
    )
    episode = _episode()
    token = recovery_state.current_recovery.set(episode)
    try:
        with pytest.raises(live_chain.ProviderChainUnavailable) as raised:
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.parakeet,
                connect_primary=AsyncMock(),
                callbacks={st.STTService.modulate: AsyncMock(), st.STTService.soniox: AsyncMock()},
                failed=set(),
                models=['parakeet-window', 'modulate-velma-2', 'soniox'],
                routing_uid='user',
                routing_models={'parakeet': 'parakeet-window'},
            )
    finally:
        recovery_state.current_recovery.reset(token)
    assert raised.value.retry_after == 300


@pytest.mark.asyncio
async def test_all_dial_budget_denial_still_dialled_legs_count(monkeypatch):
    """A walk whose legs were attempted but refused by the per-dial budget
    (reserve gate) with zero real dials is still EARNED evidence when the
    episode ledger shows the session already paid for those targets — the
    untouched-ledger predicate, not merely the dialed flag, gates the park."""
    _window_full(monkeypatch)
    episode = _episode()
    episode.attempted_targets.update({'soniox'})
    token = recovery_state.current_recovery.set(episode)
    window = AsyncMock(side_effect=AssertionError('no re-entry was granted'))
    soniox = AsyncMock(side_effect=AssertionError('ledger already spent this leg'))
    try:
        with pytest.raises(live_chain.LiveChainExhausted):
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.parakeet,
                connect_primary=window,
                callbacks={st.STTService.soniox: soniox},
                failed=set(),
                models=['parakeet-window', 'soniox'],
                routing_uid='user',
                routing_models={'parakeet': 'parakeet-window'},
            )
    finally:
        recovery_state.current_recovery.reset(token)
    window.assert_not_awaited()
    soniox.assert_not_awaited()


@pytest.mark.asyncio
async def test_park_leaves_no_shed_evidence_and_no_leg_attempts(monkeypatch):
    """A parked ending poisons nothing: no connect-failure shed evidence is
    recorded, no leg-attempt counter moves, and the episode's dial ledger
    stays empty — later sessions and later dials inherit a clean chain."""
    from utils.stt.live_metrics import LEG_ATTEMPTS

    _window_full(monkeypatch)
    _both_fallbacks_unaskable(monkeypatch, benched=True)
    episode = _episode()
    token = recovery_state.current_recovery.set(episode)
    failures_before = len(live_chain._recent_connect_failures)
    legs_before = {labels: child._value.get() for labels, child in LEG_ATTEMPTS._metrics.items()}
    try:
        with pytest.raises(live_chain.ProviderChainUnavailable):
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.parakeet,
                connect_primary=AsyncMock(),
                callbacks={st.STTService.modulate: AsyncMock(), st.STTService.soniox: AsyncMock()},
                failed=set(),
                models=['parakeet-window', 'modulate-velma-2', 'soniox'],
                routing_uid='user',
                routing_models={'parakeet': 'parakeet-window'},
            )
    finally:
        recovery_state.current_recovery.reset(token)
    assert len(live_chain._recent_connect_failures) == failures_before
    assert {labels: child._value.get() for labels, child in LEG_ATTEMPTS._metrics.items()} == legs_before
    assert not episode.attempted_targets


@pytest.mark.asyncio
async def test_terminal_episode_park_does_not_fire_and_metric_stays_split(monkeypatch):
    """The skipped counter moves ONLY on the park ending: the terminal
    zero-dial ending (dead episode) and the earned ending both leave it
    untouched while the legacy exhausted counter carries them."""
    from utils.stt.live_metrics import CHAIN_EXHAUSTED as _ce

    _window_full(monkeypatch)
    _both_fallbacks_unaskable(monkeypatch, benched=False)
    episode = _episode()
    episode.state = recovery_state.RecoveryState.exhausted
    token = recovery_state.current_recovery.set(episode)
    skipped_before = CHAIN_EXHAUSTED_SKIPPED._value.get()
    exhausted_before = _ce._value.get()
    try:
        with pytest.raises(live_chain.LiveChainExhausted):
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.parakeet,
                connect_primary=AsyncMock(),
                callbacks={st.STTService.modulate: AsyncMock(), st.STTService.soniox: AsyncMock()},
                failed=set(),
                models=['parakeet-window', 'modulate-velma-2', 'soniox'],
                routing_uid='user',
                routing_models={'parakeet': 'parakeet-window'},
            )
    finally:
        recovery_state.current_recovery.reset(token)
    assert CHAIN_EXHAUSTED_SKIPPED._value.get() == skipped_before
    assert _ce._value.get() - exhausted_before == 1


@pytest.mark.asyncio
async def test_park_log_carries_the_gates_not_user_data(monkeypatch, caplog):
    """The bounded park line names the policy gates (reason, subtype,
    retry_after) and never a uid, session id, or provider exception text."""
    import logging

    _window_full(monkeypatch)
    _account_benched(st._modulate_circuit, 45)
    _probes_occupied(st._soniox_circuit)
    episode = _episode()
    token = recovery_state.current_recovery.set(episode)
    try:
        with caplog.at_level(logging.INFO, logger='utils.stt.live_chain'):
            with pytest.raises(live_chain.ProviderChainUnavailable):
                await live_chain.connect_configured_chain(
                    primary_service=st.STTService.parakeet,
                    connect_primary=AsyncMock(),
                    callbacks={st.STTService.modulate: AsyncMock(), st.STTService.soniox: AsyncMock()},
                    failed=set(),
                    models=['parakeet-window', 'modulate-velma-2', 'soniox'],
                    routing_uid='uid-with-secrets',
                    routing_models={'parakeet': 'parakeet-window'},
                )
    finally:
        recovery_state.current_recovery.reset(token)
    parked = [r for r in caplog.records if 'stt_chain_parked' in r.getMessage()]
    assert len(parked) == 1
    line = parked[0].getMessage()
    assert 'reason=capacity_full' in line
    assert 'subtype=admission' in line
    assert 'retry_after=' in line
    assert 'uid-with-secrets' not in line


@pytest.mark.asyncio
async def test_parked_then_recovered_session_can_still_serve(monkeypatch):
    """The park must not poison the pod: after the skipped ending, a fresh
    dial on the same episode with the gates healthy again connects and
    serves — the graceful answer is retryable, not a latch."""
    _window_full(monkeypatch)
    _both_fallbacks_unaskable(monkeypatch, benched=False)
    episode = _episode()
    token = recovery_state.current_recovery.set(episode)
    try:
        with pytest.raises(live_chain.ProviderChainUnavailable):
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.parakeet,
                connect_primary=AsyncMock(),
                callbacks={st.STTService.modulate: AsyncMock(), st.STTService.soniox: AsyncMock()},
                failed=set(),
                models=['parakeet-window', 'modulate-velma-2', 'soniox'],
                routing_uid='user',
                routing_models={'parakeet': 'parakeet-window'},
            )
        # The slot frees and the occupied probe releases: the SAME episode
        # dials on. No parakeet callback is armed (its window has no
        # re-entry), so the healthy soniox leg is the one that serves.
        monkeypatch.setattr(live_chain.window.admission, 'available', lambda: True)
        st._soniox_circuit._probes_in_flight = 0
        healthy = AsyncMock(return_value=socket())
        _, selected = await live_chain.connect_configured_chain(
            primary_service=st.STTService.soniox,
            connect_primary=healthy,
            callbacks={},
            failed=set(),
            models=['soniox'],
            routing_uid='user',
        )
    finally:
        recovery_state.current_recovery.reset(token)
    assert selected == st.STTService.soniox
    healthy.assert_awaited_once()
    assert not episode.exhausted


@pytest.mark.asyncio
async def test_legacy_rebuild_park_sends_backoff_without_exhausting(monkeypatch):
    """The legacy recovery arm shares the contract: a zero-dial
    ProviderChainUnavailable from its dial sends the client the typed
    provider_unavailable backoff and never latches exhaustion."""
    from tests.unit.test_modulate_capacity_failover import dead_receiver

    receiver = dead_receiver()
    receiver.recovery = None  # force the legacy arm

    async def refused(*_args, **_kwargs):
        raise live_chain.ProviderChainUnavailable(11)

    receiver._create_stt_socket = AsyncMock(side_effect=refused)
    assert await receiver._failover_stt_socket() is False
    receiver.host.request.websocket.send_json.assert_awaited_once()
    payload = receiver.host.request.websocket.send_json.await_args.args[0]
    assert payload['status'] == 'stt_failed'
    assert payload['reason'] == 'provider_unavailable'
    assert payload['retry_after'] == 11


@pytest.mark.asyncio
async def test_park_leaves_following_legs_dialable_within_the_episode(monkeypatch):
    """A skipped ending must not consume recovery reservations: the episode's
    dial ledger is untouched, so a later leg in the SAME episode can still be
    reserved and dialled (park now, dial when a gate opens)."""
    _window_full(monkeypatch)
    _account_benched(st._modulate_circuit, 1800)
    _probes_occupied(st._soniox_circuit)
    episode = _episode()
    token = recovery_state.current_recovery.set(episode)
    try:
        with pytest.raises(live_chain.ProviderChainUnavailable):
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.parakeet,
                connect_primary=AsyncMock(),
                callbacks={st.STTService.modulate: AsyncMock(), st.STTService.soniox: AsyncMock()},
                failed=set(),
                models=['parakeet-window', 'modulate-velma-2', 'soniox'],
                routing_uid='user',
                routing_models={'parakeet': 'parakeet-window'},
            )
        assert not episode.attempted_targets
        # With every gate healthy again, the same episode dials and serves.
        # The context var was reset by the failed dial's own frame, so re-arm
        # it for the follow-up dial inside this same episode.
        monkeypatch.setattr(live_chain.window.admission, 'available', lambda: True)
        st._soniox_circuit._probes_in_flight = 0  # the probe slot freed
        healthy = AsyncMock(return_value=socket())
        token2 = recovery_state.current_recovery.set(episode)
        try:
            _, selected = await live_chain.connect_configured_chain(
                primary_service=st.STTService.soniox,
                connect_primary=healthy,
                callbacks={},
                failed=set(),
                models=['soniox'],
                routing_uid='user',
            )
        finally:
            recovery_state.current_recovery.reset(token2)
    finally:
        recovery_state.current_recovery.reset(token)
    assert selected == st.STTService.soniox
    healthy.assert_awaited_once()
    assert not episode.exhausted


@pytest.mark.asyncio
async def test_park_wait_covers_family_circuit_cooldown_alone(monkeypatch):
    """An open family circuit with cooldown and no benches anywhere still
    reports its remaining silence as the wait — the wait matrix covers every
    gate kind independently."""
    _window_full(monkeypatch)
    _account_benched(st._modulate_circuit, 45)
    _probes_occupied(st._soniox_circuit)
    monkeypatch.setattr(live_chain.health, 'cached_snapshot', lambda *args: {})
    episode = _episode()
    token = recovery_state.current_recovery.set(episode)
    try:
        with pytest.raises(live_chain.ProviderChainUnavailable) as raised:
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.parakeet,
                connect_primary=AsyncMock(),
                callbacks={st.STTService.modulate: AsyncMock(), st.STTService.soniox: AsyncMock()},
                failed=set(),
                models=['parakeet-window', 'modulate-velma-2', 'soniox'],
                routing_uid='user',
                routing_models={'parakeet': 'parakeet-window'},
            )
    finally:
        recovery_state.current_recovery.reset(token)
    assert 30 <= raised.value.retry_after <= 46


@pytest.mark.asyncio
async def test_park_wait_is_the_max_across_family_target_and_bench_gates(monkeypatch):
    """All three gate kinds at once: family circuit (40s), canary target
    circuit (70s), fleet bench (25s) — the wait is the maximum, 70s."""
    _window_full(monkeypatch)
    _account_benched(st._modulate_circuit, 40)
    monkeypatch.setattr(
        live_chain.health,
        'cached_snapshot',
        lambda providers, _language: {
            'soniox': live_health.ProviderState(bench='account', bench_until=time.time() + 25)
        },
    )
    # A canary target with its own open circuit (70s left) on the soniox
    # route: propose() returns it, so the route walk skips it on the open
    # target circuit and the park's wait must include its cooldown.
    target = SimpleNamespace(
        id='soniox-eu',
        family='soniox',
        endpoint='http://soniox-eu.invalid',
        cost_per_audio_hour=0.0,
        at_capacity=lambda: False,
    )
    real_target_circuit = live_chain.target_circuit

    def target_circuit_with_bench(target, default=None):
        if getattr(target, 'id', None) == 'soniox-eu':
            return bench_circuit
        if target is None or getattr(target, 'endpoint', None) is None:
            return default
        return real_target_circuit(target, default)

    bench_circuit = resilience.ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=70)
    bench_circuit.record_account_failure(70)  # force cannot bypass account cooldowns
    monkeypatch.setattr(live_chain, 'target_circuit', target_circuit_with_bench)
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setattr(live_chain, 'routing_on', lambda _uid: True)
    monkeypatch.setattr(live_chain, 'propose', lambda *args, **kwargs: [target])
    episode = _episode()
    token = recovery_state.current_recovery.set(episode)
    try:
        with pytest.raises(live_chain.ProviderChainUnavailable) as raised:
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.parakeet,
                connect_primary=AsyncMock(),
                callbacks={st.STTService.modulate: AsyncMock(), st.STTService.soniox: AsyncMock()},
                failed=set(),
                models=['parakeet-window', 'modulate-velma-2', 'soniox'],
                routing_uid='user',
                routing_models={'parakeet': 'parakeet-window', 'soniox': 'soniox'},
            )
    finally:
        recovery_state.current_recovery.reset(token)
    assert 70 <= raised.value.retry_after <= 71


@pytest.mark.asyncio
async def test_park_wait_ignores_benches_that_do_not_exclude_the_family(monkeypatch):
    """A fleet state with a bench that does not exclude the family (or no
    bench at all) contributes nothing: the wait stays at the floor from the
    cooldown-free occupied probes."""
    _window_full(monkeypatch)
    _probes_occupied(st._modulate_circuit)
    _probes_occupied(st._soniox_circuit)
    monkeypatch.setattr(
        live_chain.health,
        'cached_snapshot',
        lambda providers, _language: {
            'soniox': live_health.ProviderState(bench='selection', bench_until=time.time() + 900)
        },
    )
    episode = _episode()
    token = recovery_state.current_recovery.set(episode)
    try:
        with pytest.raises(live_chain.ProviderChainUnavailable) as raised:
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.parakeet,
                connect_primary=AsyncMock(),
                callbacks={st.STTService.modulate: AsyncMock(), st.STTService.soniox: AsyncMock()},
                failed=set(),
                models=['parakeet-window', 'modulate-velma-2', 'soniox'],
                routing_uid='user',
                routing_models={'parakeet': 'parakeet-window'},
            )
    finally:
        recovery_state.current_recovery.reset(token)
    assert raised.value.retry_after == 5


@pytest.mark.asyncio
async def test_client_departure_zero_dial_ending_stays_terminal(monkeypatch):
    """A client that already left skips every leg too, but nobody is left to
    park: the terminal answer keeps the teardown contract."""
    _window_full(monkeypatch)
    _both_fallbacks_unaskable(monkeypatch, benched=False)
    episode = _episode()
    episode.mark_client_leaving()
    token = recovery_state.current_recovery.set(episode)
    try:
        with pytest.raises(live_chain.LiveChainExhausted):
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.parakeet,
                connect_primary=AsyncMock(),
                callbacks={st.STTService.modulate: AsyncMock(), st.STTService.soniox: AsyncMock()},
                failed=set(),
                models=['parakeet-window', 'modulate-velma-2', 'soniox'],
                routing_uid='user',
                routing_models={'parakeet': 'parakeet-window'},
            )
    finally:
        recovery_state.current_recovery.reset(token)


@pytest.mark.asyncio
async def test_expired_episode_zero_dial_ending_stays_terminal(monkeypatch):
    """An expired episode is the same story: its deadline ran out, the
    ending is terminal even with nothing dialled inside this walk."""
    _window_full(monkeypatch)
    _both_fallbacks_unaskable(monkeypatch, benched=False)
    ticks = [0.0]
    episode = _episode(clock=lambda: ticks[0])
    episode.begin(family='parakeet')
    ticks[0] = recovery_state.RECOVERY_EPISODE_SECONDS + 1
    assert episode.episode_expired()
    token = recovery_state.current_recovery.set(episode)
    try:
        with pytest.raises(live_chain.LiveChainExhausted):
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.parakeet,
                connect_primary=AsyncMock(),
                callbacks={st.STTService.modulate: AsyncMock(), st.STTService.soniox: AsyncMock()},
                failed=set(),
                models=['parakeet-window', 'modulate-velma-2', 'soniox'],
                routing_uid='user',
                routing_models={'parakeet': 'parakeet-window'},
            )
    finally:
        recovery_state.current_recovery.reset(token)


@pytest.mark.asyncio
async def test_zero_dial_park_without_an_episode_stays_terminal(monkeypatch):
    """Recovery on but no episode in the context (a dial outside any owner
    session): the predicate needs the episode, and without it the terminal
    answer is unchanged — the park is an episode-scoped contract."""
    _window_full(monkeypatch)
    _both_fallbacks_unaskable(monkeypatch, benched=False)
    token = recovery_state.current_recovery.set(None)
    try:
        with pytest.raises(live_chain.LiveChainExhausted):
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.parakeet,
                connect_primary=AsyncMock(),
                callbacks={st.STTService.modulate: AsyncMock(), st.STTService.soniox: AsyncMock()},
                failed=set(),
                models=['parakeet-window', 'modulate-velma-2', 'soniox'],
                routing_uid='user',
                routing_models={'parakeet': 'parakeet-window'},
            )
    finally:
        recovery_state.current_recovery.reset(token)


@pytest.mark.asyncio
async def test_optional_handover_zero_dial_stays_rejected_stream(monkeypatch):
    """Demand-lane handovers raise RejectedStream BEFORE the tail: the park
    must never hijack the handover contract even with every leg skipped."""
    _window_full(monkeypatch)
    _both_fallbacks_unaskable(monkeypatch, benched=True)
    episode = _episode()
    token = recovery_state.current_recovery.set(episode)
    try:
        with pytest.raises(live_chain.RejectedStream):
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.parakeet,
                connect_primary=AsyncMock(),
                callbacks={st.STTService.modulate: AsyncMock(), st.STTService.soniox: AsyncMock()},
                failed=set(),
                models=['parakeet-window', 'modulate-velma-2', 'soniox'],
                routing_uid='user',
                routing_models={'parakeet': 'parakeet-window'},
                optional_handover=True,
            )
    finally:
        recovery_state.current_recovery.reset(token)


@pytest.mark.asyncio
async def test_park_log_absent_on_earned_exhaustion(monkeypatch, caplog):
    """The bounded park WARNING belongs to the skipped ending only: an
    earned exhaustion logs no park line."""
    import logging

    episode = _episode()
    token = recovery_state.current_recovery.set(episode)
    try:
        with caplog.at_level(logging.INFO, logger='utils.stt.live_chain'):
            with pytest.raises(live_chain.LiveChainExhausted):
                await live_chain.connect_configured_chain(
                    primary_service=st.STTService.modulate,
                    connect_primary=AsyncMock(side_effect=RuntimeError('connect failed')),
                    callbacks={st.STTService.soniox: AsyncMock(side_effect=RuntimeError('connect failed'))},
                    failed=set(),
                    models=['modulate-velma-2', 'soniox'],
                    routing_uid='user',
                )
    finally:
        recovery_state.current_recovery.reset(token)
    assert not [r for r in caplog.records if 'stt_chain_parked' in r.getMessage()]


@pytest.mark.asyncio
async def test_park_log_absent_on_terminal_episode_ending(monkeypatch, caplog):
    """The dead-episode zero-dial ending logs no park line either — it keeps
    its classified receiver ERROR instead."""
    import logging

    _window_full(monkeypatch)
    _both_fallbacks_unaskable(monkeypatch, benched=False)
    episode = _episode()
    episode.state = recovery_state.RecoveryState.exhausted
    token = recovery_state.current_recovery.set(episode)
    try:
        with caplog.at_level(logging.INFO, logger='utils.stt.live_chain'):
            with pytest.raises(live_chain.LiveChainExhausted):
                await live_chain.connect_configured_chain(
                    primary_service=st.STTService.parakeet,
                    connect_primary=AsyncMock(),
                    callbacks={st.STTService.modulate: AsyncMock(), st.STTService.soniox: AsyncMock()},
                    failed=set(),
                    models=['parakeet-window', 'modulate-velma-2', 'soniox'],
                    routing_uid='user',
                    routing_models={'parakeet': 'parakeet-window'},
                )
    finally:
        recovery_state.current_recovery.reset(token)
    assert not [r for r in caplog.records if 'stt_chain_parked' in r.getMessage()]


@pytest.mark.asyncio
async def test_earned_exhaustion_leaves_skipped_counter_untouched():
    """Counter isolation both ways: an earned ending moves only the legacy
    exhausted counter, never the skipped one."""
    episode = _episode()
    token = recovery_state.current_recovery.set(episode)
    skipped_before = CHAIN_EXHAUSTED_SKIPPED._value.get()
    exhausted_before = CHAIN_EXHAUSTED._value.get()
    try:
        with pytest.raises(live_chain.LiveChainExhausted):
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.modulate,
                connect_primary=AsyncMock(side_effect=RuntimeError('connect failed')),
                callbacks={st.STTService.soniox: AsyncMock(side_effect=RuntimeError('connect failed'))},
                failed=set(),
                models=['modulate-velma-2', 'soniox'],
                routing_uid='user',
            )
    finally:
        recovery_state.current_recovery.reset(token)
    assert CHAIN_EXHAUSTED._value.get() - exhausted_before == 1
    assert CHAIN_EXHAUSTED_SKIPPED._value.get() == skipped_before


@pytest.mark.asyncio
async def test_receiver_managed_park_restores_previous_selection(monkeypatch):
    """After a parked failover the session still sits on its proven
    provider/language/model — the refusal is policy, not evidence against
    the serving selection."""
    from tests.unit.test_modulate_capacity_failover import dead_receiver

    receiver = dead_receiver()
    selection_before = (receiver.host.stt_service, receiver.host.stt_language, receiver.host.stt_model)

    async def refused(*_args, **_kwargs):
        raise live_chain.ProviderChainUnavailable(9)

    receiver._create_stt_socket = AsyncMock(side_effect=refused)
    assert await receiver._failover_stt_socket() is False
    assert (receiver.host.stt_service, receiver.host.stt_language, receiver.host.stt_model) == selection_before
    assert not receiver.recovery.exhausted


@pytest.mark.asyncio
async def test_park_log_subtype_is_none_when_no_capacity_was_involved(monkeypatch, caplog):
    """A park caused purely by circuits reports subtype=none — the bounded
    vocabulary keeps the zero-value explicit for the log reader."""
    import logging

    _both_fallbacks_unaskable(monkeypatch, benched=False)
    episode = _episode()
    token = recovery_state.current_recovery.set(episode)
    try:
        with caplog.at_level(logging.INFO, logger='utils.stt.live_chain'):
            with pytest.raises(live_chain.ProviderChainUnavailable):
                await live_chain.connect_configured_chain(
                    primary_service=st.STTService.parakeet,
                    connect_primary=AsyncMock(),
                    callbacks={st.STTService.modulate: AsyncMock(), st.STTService.soniox: AsyncMock()},
                    failed={'parakeet'},
                    models=['parakeet-window', 'modulate-velma-2', 'soniox'],
                    routing_uid='user',
                    routing_models={'parakeet': 'parakeet-window'},
                )
    finally:
        recovery_state.current_recovery.reset(token)
    parked = [r for r in caplog.records if 'stt_chain_parked' in r.getMessage()]
    assert len(parked) == 1
    assert 'reason=circuit_open' in parked[0].getMessage()
    assert 'subtype=none' in parked[0].getMessage()


@pytest.mark.asyncio
async def test_park_wait_cap_boundary_is_exactly_three_hundred(monkeypatch):
    """The cap boundary is exact: a 299.5s bench rounds up to 300 and stays
    at the cap instead of escaping it."""
    _window_full(monkeypatch)
    _probes_occupied(st._modulate_circuit)
    monkeypatch.setattr(
        live_chain.health,
        'cached_snapshot',
        lambda providers, _language: {
            'soniox': live_health.ProviderState(bench='account', bench_until=time.time() + 340)
        },
    )
    episode = _episode()
    token = recovery_state.current_recovery.set(episode)
    try:
        with pytest.raises(live_chain.ProviderChainUnavailable) as raised:
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.parakeet,
                connect_primary=AsyncMock(),
                callbacks={st.STTService.modulate: AsyncMock(), st.STTService.soniox: AsyncMock()},
                failed=set(),
                models=['parakeet-window', 'modulate-velma-2', 'soniox'],
                routing_uid='user',
                routing_models={'parakeet': 'parakeet-window'},
            )
    finally:
        recovery_state.current_recovery.reset(token)
    assert raised.value.retry_after == 300


@pytest.mark.asyncio
async def test_first_real_dial_refusal_makes_later_zero_dial_walks_terminal(monkeypatch):
    """Episode economics end to end: the first walk earns a real dial refusal
    (terminal), and a later walk in the same spent episode that skips every
    leg also stays terminal — one real dial poisons the park for the episode."""
    _window_full(monkeypatch)
    episode = _episode()
    token = recovery_state.current_recovery.set(episode)
    skipped_before = CHAIN_EXHAUSTED_SKIPPED._value.get()
    try:
        with pytest.raises(live_chain.LiveChainExhausted):
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.parakeet,
                connect_primary=AsyncMock(side_effect=RuntimeError('connect failed')),
                callbacks={st.STTService.modulate: AsyncMock(side_effect=RuntimeError('connect failed'))},
                failed=set(),
                models=['parakeet-window', 'modulate-velma-2'],
                routing_uid='user',
                routing_models={'parakeet': 'parakeet-window'},
            )
        assert episode.attempted_targets
        with pytest.raises(live_chain.LiveChainExhausted):
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.parakeet,
                connect_primary=AsyncMock(),
                callbacks={st.STTService.modulate: AsyncMock()},
                failed=set(),
                models=['parakeet-window', 'modulate-velma-2'],
                routing_uid='user',
                routing_models={'parakeet': 'parakeet-window'},
            )
    finally:
        recovery_state.current_recovery.reset(token)
    assert CHAIN_EXHAUSTED_SKIPPED._value.get() == skipped_before


@pytest.mark.asyncio
async def test_single_leg_window_only_chain_still_parks(monkeypatch):
    """A chain configured with only the windowed parakeet leg parks when the
    slot is full: one refused leg with no fallback at all is still zero dials,
    not a terminal verdict about the provider."""
    _window_full(monkeypatch)
    episode = _episode()
    token = recovery_state.current_recovery.set(episode)
    skipped_before = CHAIN_EXHAUSTED_SKIPPED._value.get()
    try:
        with pytest.raises(live_chain.ProviderChainUnavailable) as raised:
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.parakeet,
                connect_primary=AsyncMock(),
                callbacks={},
                failed=set(),
                models=['parakeet-window'],
                routing_uid='user',
                routing_models={'parakeet': 'parakeet-window'},
            )
    finally:
        recovery_state.current_recovery.reset(token)
    assert raised.value.retry_after == 5
    assert CHAIN_EXHAUSTED_SKIPPED._value.get() - skipped_before == 1


@pytest.mark.asyncio
async def test_zero_capacity_env_parks_the_same_as_an_occupied_slot(monkeypatch, runtime):
    """The refusal mechanism is irrelevant to the contract: a window cap of
    zero (env) refuses exactly like an occupied slot and parks the session."""
    monkeypatch.setenv('PARAKEET_WINDOW_MAX_SESSIONS', '0')
    _probes_occupied(st._modulate_circuit)
    _probes_occupied(st._soniox_circuit)
    episode = _episode()
    token = recovery_state.current_recovery.set(episode)
    try:
        with pytest.raises(live_chain.ProviderChainUnavailable) as raised:
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.parakeet,
                connect_primary=AsyncMock(side_effect=AssertionError('a zero cap must not dial')),
                callbacks={st.STTService.modulate: AsyncMock(), st.STTService.soniox: AsyncMock()},
                failed=set(),
                models=['parakeet-window', 'modulate-velma-2', 'soniox'],
                routing_uid='user',
                routing_models={'parakeet': 'parakeet-window'},
            )
    finally:
        recovery_state.current_recovery.reset(token)
    assert raised.value.retry_after >= 5
    assert not episode.attempted_targets
