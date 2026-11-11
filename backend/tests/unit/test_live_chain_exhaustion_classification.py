"""Mid-session failover must classify the managed chain's typed exhaustion.

Failure-Class: FC-typed-failure-collapsed-to-generic — instance in
backend/routers/listen/receiver.py ``_rebuild_stt_socket_locked`` (2026-10-09
backend-listen): the managed dial's typed terminal answer
(``LiveChainExhausted`` — every configured provider refused inside one dial)
was handled correctly as terminal exhaustion but reported through the shared
``except Exception`` arm, so ``logger.exception`` re-printed the chain's own
frames as an unexpected crash once per session. The generic arm is for
untyped dial faults (provider adapters raising unexpectedly); a typed
terminal exception is classified evidence, not a crash.

Production evidence (2026-10-09, backend-listen): the
``Traceback ... in _rebuild_stt_socket_locked`` and
``ERROR:...:STT failover connect raised`` entries (each x101/30m in the
sensor window, ~1600/day) mirrored the
``omi_fallback_event ... outcome=exhausted`` WARNINGs 1:1 — every traceback
ended in ``utils.stt.live_chain.LiveChainExhausted: Configured STT chain
exhausted`` raised at live_chain.py:1078. The user-visible behavior was
already correct (buffered audio ends in the typed ``stt_failed`` terminal
status and the client is closed with 1011 by the death monitor); the crash
tracebacks were pure log noise that buried genuinely unexpected dial
failures sharing the message shape.
"""

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.unit.test_modulate_capacity_failover import dead_receiver
from tests.unit.test_parakeet_window_live import runtime  # noqa: F401 -- pytest fixture
from utils.stt import live_chain, live_router, streaming as st
from utils.stt.live_failure import live_stt_upstream_failure, terminate_live_stt_session


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture(autouse=True)
def _stt_failover_recovery_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')


@pytest.fixture(autouse=True)
def serving(monkeypatch, runtime):
    """Mirror the test_modulate_capacity_failover harness: routing in shadow,
    no fleet snapshot, no capacity state — so provider selection yields a
    candidate and the rebuild reaches the (mocked) connect. ``runtime``
    (imported fixture) pins the provider env keys and fresh circuits."""
    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '0')
    monkeypatch.setenv('PARAKEET_WINDOW_MAX_SESSIONS', '8')
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'modulate-velma-2', 'soniox'])
    monkeypatch.setattr(live_chain.health, 'has_fresh_fleet_snapshot', lambda: False)
    monkeypatch.setattr(live_chain.health, 'cached_snapshot', lambda *args: {})
    monkeypatch.setattr(live_router, '_capacity_until', {})


def _chain_exhausted_receiver(error: Exception):
    receiver = dead_receiver()

    async def raise_from_chain(*_args, **_kwargs):
        raise error

    receiver._create_stt_socket = AsyncMock(side_effect=raise_from_chain)
    return receiver


@pytest.mark.anyio
async def test_typed_chain_exhaustion_is_classified_not_crash_logged(caplog):
    """LiveChainExhausted settles, exhausts, logs one classified line, and
    never re-prints the chain's frames."""
    receiver = _chain_exhausted_receiver(live_chain.LiveChainExhausted('Configured STT chain exhausted'))
    with caplog.at_level(logging.INFO, logger='routers.listen.receiver'):
        assert await receiver._failover_stt_socket() is False

    records = [r for r in caplog.records if r.name == 'routers.listen.receiver']
    assert [r.levelno for r in records] == [logging.ERROR]
    assert records[0].exc_info is None
    assert records[0].getMessage() == 'STT failover chain exhausted (Configured STT chain exhausted)'
    # Terminal exhaustion latch: the death monitor owns the client teardown
    # (typed stt_failed status + close 1011), exactly as before.
    assert receiver.recovery.exhausted
    assert receiver._create_stt_socket.await_count == 1


@pytest.mark.anyio
async def test_untyped_dial_failure_keeps_crash_traceback(caplog):
    """A genuinely unexpected dial fault keeps the full traceback and the
    walk continues to the next candidate inside the episode."""
    receiver = _chain_exhausted_receiver(RuntimeError('adapter exploded'))
    with caplog.at_level(logging.INFO, logger='routers.listen.receiver'):
        assert await receiver._failover_stt_socket() is False

    records = [r for r in caplog.records if r.name == 'routers.listen.receiver']
    assert {r.getMessage() for r in records} == {'STT failover connect raised'}
    assert records
    assert all(r.levelno == logging.ERROR and r.exc_info is not None for r in records)
    # Untyped faults stay retryable: the first failure excluded only its own
    # leg and the walk dialed the next candidate.
    assert receiver._create_stt_socket.await_count == 2


@pytest.mark.anyio
async def test_typed_exhaustion_restores_previous_selection_once():
    """A failed dial leaves the session on its proven provider/language/model
    exactly once — the restoration runs even though the typed arm never
    retries, so later selection cannot inherit the refused candidate."""
    receiver = _chain_exhausted_receiver(live_chain.LiveChainExhausted('Configured STT chain exhausted'))
    selection_before = (receiver.host.stt_service, receiver.host.stt_language, receiver.host.stt_model)
    assert await receiver._failover_stt_socket() is False

    assert receiver._create_stt_socket.await_count == 1
    assert (receiver.host.stt_service, receiver.host.stt_language, receiver.host.stt_model) == selection_before


@pytest.mark.anyio
async def test_typed_exhaustion_latches_once_and_reruns_fail_fast():
    """The first exhaustion consumes the episode; a later send-path or
    monitor failover that arrives after the latch fails fast with the same
    False result and never dials again (the receiver-lock latching the
    pipeline doc promises)."""
    receiver = _chain_exhausted_receiver(live_chain.LiveChainExhausted('Configured STT chain exhausted'))
    assert await receiver._failover_stt_socket() is False
    assert receiver.recovery.exhausted
    assert receiver._create_stt_socket.await_count == 1

    assert await receiver._failover_stt_socket() is False
    assert await receiver._failover_stt_socket() is False
    assert receiver._create_stt_socket.await_count == 1


@pytest.mark.anyio
async def test_untyped_faults_walk_to_a_serving_success_within_the_episode():
    """The generic arm's walk-continues contract end to end: after an untyped
    failure burns one candidate, a serving replacement is still adopted
    inside the same episode."""
    from tests.unit.test_parakeet_failover_exhausted import Replacement

    receiver = dead_receiver()
    failures = {'remaining': 1}

    async def first_refuses_then_serves(*_args, **_kwargs):
        if failures['remaining'] > 0:
            failures['remaining'] -= 1
            raise RuntimeError('transient adapter crash')
        return Replacement(lambda _: None)

    receiver._create_stt_socket = AsyncMock(side_effect=first_refuses_then_serves)
    assert await receiver._failover_stt_socket() is True


@pytest.mark.anyio
async def test_cancelled_dial_propagates_without_exhaustion_latch():
    """A cancelled dial is session teardown, not exhaustion: CancelledError
    must propagate so the supervisor can finish the shutdown, and the
    episode must stay open."""
    receiver = dead_receiver()

    async def cancelled_dial(*_args, **_kwargs):
        raise asyncio.CancelledError()

    receiver._create_stt_socket = AsyncMock(side_effect=cancelled_dial)
    with pytest.raises(asyncio.CancelledError):
        await receiver._failover_stt_socket()
    assert not receiver.recovery.exhausted


@pytest.mark.anyio
async def test_provider_chain_unavailable_arm_still_sends_client_backoff():
    """The neighbouring typed arm is untouched: ProviderChainUnavailable
    keeps sending the client the typed provider_unavailable backoff and
    never touches the exhaustion latch."""
    from utils.stt.live_chain import ProviderChainUnavailable

    receiver = dead_receiver()
    retry_after = 42

    async def refused(*_args, **_kwargs):
        raise ProviderChainUnavailable(retry_after)

    receiver._create_stt_socket = AsyncMock(side_effect=refused)
    assert await receiver._failover_stt_socket() is False
    receiver.host.request.websocket.send_json.assert_awaited_once()
    payload = receiver.host.request.websocket.send_json.await_args.args[0]
    assert payload['status'] == 'stt_failed'
    assert payload['reason'] == 'provider_unavailable'
    assert payload['retry_after'] == retry_after
    assert not receiver.recovery.exhausted


@pytest.mark.anyio
async def test_mid_dial_episode_timeout_is_retryable_then_latches(caplog):
    """The episode-timeout arm is distinct from the typed exhaustion arm: the
    timed-out candidate is excluded, the selection is restored, and the walk
    retries the next leg until the episode budget runs out — then it latches
    exhausted. The dial itself never answers here."""
    receiver = dead_receiver()
    receiver.recovery.remaining = lambda: 0.01

    async def slow_dial(*_args, **_kwargs):
        await asyncio.sleep(0.5)
        return None

    receiver._create_stt_socket = AsyncMock(side_effect=slow_dial)
    with caplog.at_level(logging.INFO, logger='routers.listen.receiver'):
        assert await receiver._failover_stt_socket() is False

    assert receiver._create_stt_socket.await_count == 2
    assert receiver.recovery.exhausted
    # Each timed-out leg was excluded by its provider family; the selection
    # restoration ran on every pass.
    assert 'soniox' in receiver._stt_failed_providers
    assert (receiver.host.stt_service, receiver.host.stt_language, receiver.host.stt_model) == (
        st.STTService.modulate,
        'en',
        'velma-2',
    )
    assert all(r.exc_info is None for r in caplog.records if r.name == 'routers.listen.receiver')


@pytest.mark.anyio
async def test_refused_dial_none_excludes_each_leg_then_latches():
    """A dial that answers None (config-incomplete / refused socket) walks
    every remaining leg, excluding each provider, then latches exhausted —
    the untyped arm's retryable contract, exercised without exceptions."""
    receiver = dead_receiver()
    receiver._create_stt_socket = AsyncMock(return_value=None)
    assert await receiver._failover_stt_socket() is False

    assert receiver._create_stt_socket.await_count == 2
    assert receiver.recovery.exhausted
    assert {'modulate', 'soniox'} <= receiver._stt_failed_providers
    assert (receiver.host.stt_service, receiver.host.stt_language, receiver.host.stt_model) == (
        st.STTService.modulate,
        'en',
        'velma-2',
    )


@pytest.mark.anyio
async def test_death_monitor_path_terminates_client_after_typed_exhaustion():
    """The end of the story a client sees after the typed exhaustion: with
    the episode exhausted and no live replacement, the monitor's terminal
    path delivers the bounded stt_failed event and closes with 1011 — the
    user-visible behavior the de-noised log arm must preserve."""
    receiver = _chain_exhausted_receiver(live_chain.LiveChainExhausted('Configured STT chain exhausted'))
    assert await receiver._failover_stt_socket() is False
    assert receiver.recovery.exhausted

    sent: list = []

    async def send_json(data):
        sent.append(data)

    async def close(code=1000, reason=None):
        sent.append(('close', code))

    websocket = SimpleNamespace(send_json=send_json, close=close)
    receiver.host.state.active = True
    receiver.host.state.stt_terminal_failure = False
    await terminate_live_stt_session(
        websocket,
        receiver.host.state,
        failure=live_stt_upstream_failure(receiver._serving_provider()),
        reason='connection_lost',
        platform='ios',
    )
    assert ('close', 1011) in sent
    event = next(item for item in sent if isinstance(item, dict))
    assert event['status'] == 'stt_failed'
    assert event['reason'] == 'connection_lost'
    assert receiver.host.state.stt_terminal_failure is True
