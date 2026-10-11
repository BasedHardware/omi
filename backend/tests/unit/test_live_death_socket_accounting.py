"""Reconcile accepted socket deaths, including selection and client teardown."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.websockets import WebSocketState

from routers.listen import receiver as receiver_module
from tests.unit.test_live_cost_router import controls
from tests.unit.test_live_early_provider_deaths import ProviderWebSocket, managed_leg
from tests.unit.test_live_health_reason_reconciliation import ServingSocket, observed
from tests.unit.test_stt_session_failover import FakeSocket, _receiver_with_dead_socket
from utils.metrics import OMI_FALLBACK_TOTAL, OMI_LIVE_STT_TERMINAL_FAILURES_TOTAL
from utils.observability.transcription import _deployment_environment
from utils.stt import live_chain, live_failure, streaming as st
from utils.stt.live_failure import PendingLiveFailover
from utils.stt.live_metrics import CHAIN_EXHAUSTED, RECONNECT, COST_IGNORED_DEATHS
from utils.stt.live_recovery import select_live_replacement


def listener(monkeypatch, *, family='modulate', language='en'):
    receiver = _receiver_with_dead_socket(monkeypatch, replacement=None)
    receiver.host.language = language
    receiver.host.language_profile = None
    receiver.host.multi_lang_enabled = False
    receiver.host.state.shutdown_event = asyncio.Event()
    receiver.host.client_device_context.platform = 'ios'
    receiver.host.request.websocket = SimpleNamespace(
        client_state=WebSocketState.CONNECTED,
        application_state=WebSocketState.CONNECTED,
        send_json=AsyncMock(),
        close=AsyncMock(),
    )
    raw = ServingSocket()
    receiver.stt_socket = managed_leg(receiver, raw, family=family)
    return receiver, raw


def fallback_count(family, reason):
    return sum(
        sample.value
        for metric in OMI_FALLBACK_TOTAL.collect()
        for sample in metric.samples
        if sample.name == 'omi_fallback_total'
        and sample.labels['component'] in {'stt_selection', 'stt_live_session'}
        and sample.labels['from_mode'] == family
        and sample.labels['reason'] == reason
        and sample.labels['to_mode'] != 'unavailable'
    )


def ignored_count(target, reason):
    return sum(
        COST_IGNORED_DEATHS.labels(target=target, reason=reason, boundary=boundary)._value.get()
        for boundary in ('client_gone', 'owner_teardown')
    )


def terminal_count(family):
    return OMI_LIVE_STT_TERMINAL_FAILURES_TOTAL.labels(
        provider=family,
        outcome='upstream_error',
        client_platform='ios',
        deployment_environment=_deployment_environment(),
        phase='connection',
    )._value.get()


@pytest.mark.parametrize('family,reason', [('modulate', 'modulate_serve_error'), ('soniox', 'connection_lost')])
@pytest.mark.parametrize('ending', ['inactive', 'client_disconnected', 'application_closed', 'shutdown'])
def test_already_dead_socket_after_client_departure_is_not_evidence(monkeypatch, family, reason, ending):
    receiver, raw = listener(monkeypatch, family=family)
    leg = receiver.stt_socket
    before = observed(leg.routing_target, 'provider_failure', reason)
    ignored_before = ignored_count(leg.routing_target, reason)
    raw.die(reason, 'synthetic provider death during client departure')
    if ending == 'inactive':
        receiver.host.state.active = False
    elif ending == 'client_disconnected':
        receiver.host.request.websocket.client_state = WebSocketState.DISCONNECTED
    elif ending == 'application_closed':
        receiver.host.request.websocket.application_state = WebSocketState.DISCONNECTED
    elif ending == 'shutdown':
        receiver.host.state.shutdown_event.set()
    assert leg.is_connection_dead
    leg.send(b'\x01\x00')
    leg.finish()
    leg.finish()
    assert observed(leg.routing_target, 'provider_failure', reason) == before
    assert ignored_count(leg.routing_target, reason) == ignored_before + 1


@pytest.mark.asyncio
async def test_connect_validation_serve_error_has_one_matching_selection_hop(monkeypatch):
    receiver, raw = listener(monkeypatch)
    leg = receiver.stt_socket
    raw.die('modulate_serve_error', 'synthetic serve error')
    before = observed(leg.routing_target, 'provider_failure', 'modulate_serve_error')
    fallback_before = fallback_count('modulate', 'modulate_serve_error')
    generic_before = fallback_count('modulate', 'provider_5xx')
    monkeypatch.setattr(
        live_chain, 'fallback_socket_is_serving', AsyncMock(side_effect=lambda socket: not socket.is_connection_dead)
    )
    await live_chain.connect_configured_chain(
        primary_service=st.STTService.modulate,
        connect_primary=AsyncMock(return_value=leg),
        callbacks={st.STTService.soniox: AsyncMock(return_value=FakeSocket())},
        failed=set(),
        models=['modulate-velma-2', 'soniox'],
        routing_uid=receiver.host.request.uid,
        routing_language='en',
    )
    leg.finish()
    assert observed(leg.routing_target, 'provider_failure', 'modulate_serve_error') == before + 1
    assert fallback_count('modulate', 'modulate_serve_error') == fallback_before + 1
    assert fallback_count('modulate', 'provider_5xx') == generic_before


@pytest.mark.asyncio
@pytest.mark.parametrize('language', ['ko', 'ja', 'zh'])
async def test_connected_terminal_soniox_death_uses_terminal_metric_not_connect_exhaustion(monkeypatch, language):
    monkeypatch.setenv('STT_RESILIENT_RECONNECT', 'false')
    monkeypatch.setenv('STT_SERVICE_MODELS', 'soniox')
    monkeypatch.setattr(st, 'stt_service_models', ['soniox'])
    receiver, raw = listener(monkeypatch, family='soniox', language=language)
    receiver._resilient_audio = None
    reconnect_before = RECONNECT.labels(provider='soniox', reason='connection_lost', outcome='connected')._value.get()
    leg = receiver.stt_socket
    raw.die('connection_lost', 'ws recv closed: synthetic serving transport loss')
    before = observed('soniox', 'provider_failure', 'connection_lost')
    terminal_before = terminal_count('soniox')
    fallback_before = fallback_count('soniox', 'connection_lost')
    exhausted_before = CHAIN_EXHAUSTED._value.get()
    assert receiver.host.request.websocket.client_state == WebSocketState.CONNECTED
    await receiver._monitor_stt_death()
    leg.finish()
    assert observed('soniox', 'provider_failure', 'connection_lost') == before + 1
    assert terminal_count('soniox') == terminal_before + 1
    assert fallback_count('soniox', 'connection_lost') == fallback_before
    assert CHAIN_EXHAUSTED._value.get() == exhausted_before
    # With reconnect disabled, ordinary terminal handling owns this leg.
    assert (
        RECONNECT.labels(provider='soniox', reason='connection_lost', outcome='connected')._value.get()
        == reconnect_before
    )
    receiver.host.request.websocket.close.assert_awaited_once_with(
        code=1011, reason='transcription_service_unavailable'
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('reason', ['modulate_serve_error', 'connection_lost'])
@pytest.mark.parametrize(
    'routes,expected',
    [
        (('selection', 'live', 'terminal', 'departed', 'departed'), (3, 2, 1)),
        (('live', 'departed', 'departed'), (1, 1, 0)),
    ],
)
async def test_distinct_real_modulate_sockets_reconcile_selection_live_terminal_and_departed(
    monkeypatch, reason, routes, expected
):
    before = observed('modulate-velma-2', 'provider_failure', reason)
    ignored_before = ignored_count('modulate-velma-2', reason)
    fallback_before = fallback_count('modulate', reason)
    terminal_before = terminal_count('modulate')
    legs = []
    monkeypatch.setattr(
        receiver_module, 'get_stt_service_for_language', lambda *_a, **_k: (st.STTService.soniox, 'en', 'soniox')
    )
    monkeypatch.setattr(receiver_module, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    monkeypatch.setattr(
        live_chain, 'fallback_socket_is_serving', AsyncMock(side_effect=lambda socket: not socket.is_connection_dead)
    )
    for route in routes:
        receiver, _ = listener(monkeypatch)
        ws = ProviderWebSocket()
        raw = st.SafeModulateSocket(ws, lambda _s: None, asyncio.get_running_loop())
        leg = managed_leg(receiver, raw)
        receiver.stt_socket = leg
        legs.append(leg)
        try:
            if route == 'departed':
                receiver.host.request.websocket.client_state = WebSocketState.DISCONNECTED
            # Multiple Velma frames and multiple observers still belong to one
            # physical socket; the actual parser terminates on the first error.
            for _ in range(3):
                await ws.inbound.put(
                    {'type': 'error', 'error': 'Internal server error'} if reason == 'modulate_serve_error' else None
                )
            await raw._recv_task
            if route == 'departed':
                receiver.host.request.websocket.client_state = WebSocketState.DISCONNECTED
                leg.mark_owner_teardown()
            elif route == 'selection':
                await live_chain.connect_configured_chain(
                    primary_service=st.STTService.modulate,
                    connect_primary=AsyncMock(return_value=leg),
                    callbacks={st.STTService.soniox: AsyncMock(return_value=FakeSocket())},
                    failed=set(),
                    models=['modulate-velma-2', 'soniox'],
                    routing_uid=receiver.host.request.uid,
                    routing_language='en',
                )
            elif route == 'live':
                receiver._create_stt_socket = AsyncMock(return_value=FakeSocket())
                assert await receiver._failover_stt_socket()
                receiver._enqueue_stt_segments([{'text': 'synthetic', 'start': 0, 'end': 1}], provider='soniox')
            else:
                monkeypatch.setattr(
                    receiver_module, 'get_stt_service_for_language', lambda *_a, **_k: (None, 'en', None)
                )
                await receiver._monitor_stt_death()
            assert leg.is_connection_dead
            leg.send(b'\x01\x00')
            leg.finish()
            leg.finish()
        finally:
            raw.finish()
            await asyncio.gather(raw._recv_task, raw._send_task, return_exceptions=True)
    assert len({id(leg.raw) for leg in legs}) == len(routes)
    failures = observed('modulate-velma-2', 'provider_failure', reason) - before
    hops = fallback_count('modulate', reason) - fallback_before
    terminals = terminal_count('modulate') - terminal_before
    assert (failures, hops, terminals) == expected
    assert failures == hops + terminals
    assert ignored_count('modulate-velma-2', reason) - ignored_before == routes.count('departed')


@pytest.mark.asyncio
async def test_failed_selection_successor_keeps_each_source_socket_reason(monkeypatch):
    receiver, modulate_raw = listener(monkeypatch)
    modulate = receiver.stt_socket
    soniox = managed_leg(receiver, ServingSocket(), family='soniox')
    modulate_raw.die('modulate_serve_error', 'synthetic modulate error')
    soniox.raw.die('connection_lost', 'ws synthetic soniox loss')
    before = {
        family: fallback_count(family, reason)
        for family, reason in [('modulate', 'modulate_serve_error'), ('soniox', 'connection_lost')]
    }
    wrong = fallback_count('modulate', 'connection_lost')
    counts = {
        leg.routing_target: observed(leg.routing_target, 'provider_failure', leg.raw.typed_death_reason)
        for leg in (modulate, soniox)
    }
    monkeypatch.setattr(
        live_chain, 'fallback_socket_is_serving', AsyncMock(side_effect=lambda socket: not socket.is_connection_dead)
    )
    _, service = await live_chain.connect_configured_chain(
        primary_service=st.STTService.modulate,
        connect_primary=AsyncMock(return_value=modulate),
        callbacks={
            st.STTService.soniox: AsyncMock(return_value=soniox),
            st.STTService.parakeet: AsyncMock(return_value=FakeSocket()),
        },
        failed=set(),
        models=['modulate-velma-2', 'soniox', 'parakeet-window'],
        routing_uid=receiver.host.request.uid,
        routing_language='en',
    )
    assert service == st.STTService.parakeet
    assert modulate.raw is not soniox.raw
    assert fallback_count('modulate', 'modulate_serve_error') == before['modulate'] + 1
    assert fallback_count('soniox', 'connection_lost') == before['soniox'] + 1
    assert fallback_count('modulate', 'connection_lost') == wrong
    for leg in (modulate, soniox):
        leg.finish()
        assert (
            observed(leg.routing_target, 'provider_failure', leg.normalized_death_reason)
            == counts[leg.routing_target] + 1
        )


@pytest.mark.asyncio
async def test_connect_validation_cannot_restore_a_client_departure_censored_death(monkeypatch):
    receiver, raw = listener(monkeypatch)
    leg = receiver.stt_socket
    receiver.host.request.websocket.client_state = WebSocketState.DISCONNECTED
    raw.die('modulate_serve_error', 'synthetic late serve error')
    before = observed(leg.routing_target, 'provider_failure', 'modulate_serve_error')
    hops_before = fallback_count('modulate', 'modulate_serve_error')
    monkeypatch.setattr(
        live_chain, 'fallback_socket_is_serving', AsyncMock(side_effect=lambda socket: not socket.is_connection_dead)
    )
    await live_chain.connect_configured_chain(
        primary_service=st.STTService.modulate,
        connect_primary=AsyncMock(return_value=leg),
        callbacks={st.STTService.soniox: AsyncMock(return_value=FakeSocket())},
        failed=set(),
        models=['modulate-velma-2', 'soniox'],
        routing_uid=receiver.host.request.uid,
        routing_language='en',
    )
    assert observed(leg.routing_target, 'provider_failure', 'modulate_serve_error') == before
    assert fallback_count('modulate', 'modulate_serve_error') == hops_before
    assert not live_chain.health._cost_local


@pytest.mark.parametrize('family,reason', [('modulate', 'modulate_serve_error'), ('soniox', 'connection_lost')])
def test_death_claimed_with_connected_client_survives_later_teardown(monkeypatch, family, reason):
    receiver, raw = listener(monkeypatch, family=family)
    leg = receiver.stt_socket
    before = observed(leg.routing_target, 'provider_failure', reason)
    ignored_before = ignored_count(leg.routing_target, reason)
    raw.die(reason, 'synthetic serving death')
    assert leg.is_connection_dead
    live_failure.settle_terminal_socket(leg, family, reason)
    receiver.host.request.websocket.client_state = WebSocketState.DISCONNECTED
    receiver.host.state.active = False
    leg.mark_owner_teardown()
    leg.finish()
    leg.finish()
    assert observed(leg.routing_target, 'provider_failure', reason) == before + 1
    assert ignored_count(leg.routing_target, reason) == ignored_before


@pytest.mark.parametrize('family,reason', [('modulate', 'modulate_serve_error'), ('soniox', 'connection_lost')])
def test_death_observed_before_client_departure_remains_provider_failure(monkeypatch, family, reason):
    receiver, raw = listener(monkeypatch, family=family)
    leg = receiver.stt_socket
    before = observed(leg.routing_target, 'provider_failure', reason)
    ignored_before = ignored_count(leg.routing_target, reason)
    raw.die(reason, 'synthetic provider death while client is connected')
    assert leg.is_connection_dead  # First observation snapshots connected eligibility.
    receiver.host.request.websocket.client_state = WebSocketState.DISCONNECTED
    leg.leg_outcome.claim(reason)
    assert leg.leg_outcome.settle()
    assert observed(leg.routing_target, 'provider_failure', reason) == before + 1
    assert ignored_count(leg.routing_target, reason) == ignored_before


@pytest.mark.parametrize('family,reason', [('modulate', 'modulate_serve_error'), ('soniox', 'connection_lost')])
def test_client_departure_before_death_observation_excludes_provider_failure(monkeypatch, family, reason):
    receiver, raw = listener(monkeypatch, family=family)
    leg = receiver.stt_socket
    before = observed(leg.routing_target, 'provider_failure', reason)
    ignored_before = ignored_count(leg.routing_target, reason)
    receiver.host.request.websocket.client_state = WebSocketState.DISCONNECTED
    raw.die(reason, 'synthetic provider death after client departure')
    assert leg.is_connection_dead  # First observation snapshots departed eligibility.
    leg.leg_outcome.claim(reason)
    assert leg.leg_outcome.settle()
    assert observed(leg.routing_target, 'provider_failure', reason) == before
    assert ignored_count(leg.routing_target, reason) == ignored_before + 1


def test_rebuild_exhaustion_settles_observed_leg_once_after_client_departure(monkeypatch):
    receiver, raw = listener(monkeypatch)
    leg = receiver.stt_socket
    before = observed(leg.routing_target, 'provider_failure', 'modulate_serve_error')
    fallback_before = fallback_count('modulate', 'modulate_serve_error')
    raw.die('modulate_serve_error', 'synthetic provider death while client is connected')
    assert leg.is_connection_dead
    receiver.host.request.websocket.client_state = WebSocketState.DISCONNECTED
    receiver._pending_live_failover = PendingLiveFailover(
        from_mode='modulate',
        to_mode='parakeet',
        reason='modulate_serve_error',
        source_outcome=leg.leg_outcome,
    )
    receiver._stt_rebuild_attempts = 3
    select = lambda *_args, **_kwargs: pytest.fail('exhausted rebuild must not select another provider')

    assert select_live_replacement(receiver, 'modulate', select, managed=True) == (None, None, None)
    assert leg.leg_outcome.settled
    assert observed(leg.routing_target, 'provider_failure', 'modulate_serve_error') == before + 1
    assert fallback_count('modulate', 'modulate_serve_error') == fallback_before + 1

    assert select_live_replacement(receiver, 'modulate', select, managed=True) == (None, None, None)
    receiver._settle_pending_live_failover_failure()
    assert observed(leg.routing_target, 'provider_failure', 'modulate_serve_error') == before + 1
    assert fallback_count('modulate', 'modulate_serve_error') == fallback_before + 1


@pytest.mark.parametrize('family,reason', [('modulate', 'modulate_serve_error'), ('soniox', 'connection_lost')])
@pytest.mark.parametrize('owner', [False, True])
def test_ignored_late_death_retains_successful_text_evidence(monkeypatch, family, reason, owner):
    receiver, raw = listener(monkeypatch, family=family)
    leg = receiver.stt_socket
    leg.note_selection_transcript([{'text': 'synthetic'}])
    failures_before = observed(leg.routing_target, 'provider_failure', reason)
    successes_before = observed(leg.routing_target, 'success', 'text')
    ignored_before = ignored_count(leg.routing_target, reason)
    if owner:
        leg.mark_owner_teardown()
    else:
        receiver.host.request.websocket.client_state = WebSocketState.DISCONNECTED
    raw.die(reason, 'synthetic late death after successful transcript')
    assert leg.is_connection_dead
    leg.finish()
    leg.finish()
    leg.leg_outcome.claim(reason, connect=True)
    assert not leg.leg_outcome.settle()
    assert observed(leg.routing_target, 'provider_failure', reason) == failures_before
    assert observed(leg.routing_target, 'success', 'text') == successes_before + 1
    assert ignored_count(leg.routing_target, reason) == ignored_before + int(not owner)
    assert leg.leg_outcome.settled
    state = live_chain.health._cost_local[(leg.routing_target, 'all')]
    assert state.n == 1 and state.failures == 0


@pytest.mark.parametrize('family,reason', [('modulate', 'modulate_serve_error'), ('soniox', 'connection_lost')])
def test_owner_fence_preserves_preexisting_connected_death_but_excludes_later_death(monkeypatch, family, reason):
    receiver, raw = listener(monkeypatch, family=family)
    leg = receiver.stt_socket
    before = observed(leg.routing_target, 'provider_failure', reason)
    ignored_before = ignored_count(leg.routing_target, reason)
    raw.die(reason, 'synthetic provider death before owner close')
    leg.mark_owner_teardown()  # Client still connected: preserve this death.
    leg.finish()
    assert observed(leg.routing_target, 'provider_failure', reason) == before + 1
    assert ignored_count(leg.routing_target, reason) == ignored_before
    receiver2, raw2 = listener(monkeypatch, family=family)
    leg2 = receiver2.stt_socket
    leg2.mark_owner_teardown()  # Alive at the serving boundary.
    raw2.die(reason, 'synthetic late death after owner close')
    leg2.finish()
    assert raw2 is not raw
    assert observed(leg.routing_target, 'provider_failure', reason) == before + 1
    assert ignored_count(leg.routing_target, reason) == ignored_before


@pytest.mark.parametrize('mode', ['off', 'OFF', ' off '])
def test_disabled_routing_does_not_emit_ignored_death_diagnostic(monkeypatch, mode):
    receiver, raw = listener(monkeypatch)
    leg = receiver.stt_socket
    before = ignored_count(leg.routing_target, 'modulate_serve_error')
    monkeypatch.setenv('STT_ROUTING_MODE', mode)
    receiver.host.request.websocket.client_state = WebSocketState.DISCONNECTED
    raw.die('modulate_serve_error', 'synthetic late error')
    leg.finish()
    leg.finish()
    assert leg.leg_outcome.excluded_death and leg.leg_outcome.settled
    assert ignored_count(leg.routing_target, 'modulate_serve_error') == before
