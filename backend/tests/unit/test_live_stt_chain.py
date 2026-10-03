"""Behavioral contracts for the September 2026 live provider-chain outage."""

import asyncio
import time
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config.stt_provider_policy import STTServingSurface, model_is_enabled, provider_for_service
from utils.stt import (
    connect_backoff as connect_backoff_module,
    live_failure,
    connect_metrics,
    live_chain,
    live_health,
    live_router,
    provider_resilience as resilience,
    recovery_state,
    streaming as st,
)
from utils.stt.live_rollout import managed_chain_enabled, window_allocation
from utils.stt.soniox import SonioxRateLimitError, soniox_death_reason
from utils.stt.stream_close import PROVIDER_AUTH_REJECTED, PROVIDER_BUDGET_EXHAUSTED


@pytest.fixture(autouse=True)
def _stt_failover_recovery_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(live_chain, '_recent_connect_failures', deque(maxlen=1000))
    monkeypatch.setenv('STT_SHED_CONNECT_FAILURES', '3')
    monkeypatch.setenv('STT_CONNECT_ORDER_FROM_CONFIG', 'true')
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '100')
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://tdt.invalid')
    monkeypatch.setenv('SONIOX_API_KEY', 'test')
    monkeypatch.setenv('MODULATE_API_KEY', 'test')
    monkeypatch.setattr(st, '_deepgram_is_available', lambda: True)
    monkeypatch.setattr(resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0)
    for name in ('parakeet', 'modulate', 'deepgram', 'soniox'):
        monkeypatch.setattr(
            st, f'_{name}_circuit', resilience.ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=30)
        )
    monkeypatch.setattr(live_router, '_target_circuits', {})
    monkeypatch.setattr(live_router, '_capacity_until', {})
    monkeypatch.setattr(
        connect_backoff_module,
        '_shared',
        connect_backoff_module.ConnectRefusalBackoff(on_event=live_chain._connect_backoff_event),
    )


def socket(**kwargs):
    return SimpleNamespace(is_connection_dead=False, finish=lambda: None, **kwargs)


@pytest.mark.parametrize(
    'language,expected',
    [
        ('en', 'parakeet'),
        ('en-US', 'parakeet'),
        ('fr', 'parakeet'),
        ('ja', 'soniox'),
        ('ko', 'soniox'),
        ('zh', 'soniox'),
        ('vi', 'soniox'),
        ('auto', 'soniox'),
        ('multi', 'soniox'),
    ],
)
def test_requested_language_governs_tdt_eligibility(monkeypatch, language, expected):
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'soniox'])
    service, _, model = st.get_stt_service_for_language(language, window_uid='user')
    assert service.value == expected
    if expected == 'parakeet':
        assert model == 'parakeet-window'


def test_window_policy_cannot_leak_to_ptt_or_batch():
    assert model_is_enabled('parakeet-window', STTServingSurface.STREAMING)
    for surface in (STTServingSurface.PTT, STTServingSurface.PRERECORDED):
        assert not model_is_enabled('parakeet-window', surface)


def test_allocation_is_stable_bounded_and_default_dark(monkeypatch):
    monkeypatch.delenv('PARAKEET_WINDOW_ALLOCATION_PERCENT')
    assert not window_allocation('user')
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '25')
    first = [window_allocation(str(i)) for i in range(1000)]
    assert first == [window_allocation(str(i)) for i in range(1000)]
    assert 200 < sum(first) < 300
    assert not window_allocation(None)
    monkeypatch.setenv('STT_CONNECT_ORDER_FROM_CONFIG', 'false')
    assert not window_allocation('user')


def test_one_percent_canary_leads_without_reordering_vendor_control(monkeypatch):
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '1')
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'modulate-velma-2', 'soniox', 'dg-nova-3'])
    allocated = next(str(i) for i in range(10000) if window_allocation(str(i)))
    control = next(str(i) for i in range(10000) if not window_allocation(str(i)))
    assert st.get_stt_service_for_language('en', window_uid=allocated)[0] == st.STTService.parakeet
    assert st.get_stt_service_for_language('en', window_uid=control)[0] == st.STTService.modulate


@pytest.mark.parametrize('primary', list(st.STTService))
@pytest.mark.asyncio
async def test_every_primary_walks_config_order_and_feeds_each_leg(monkeypatch, primary):
    monkeypatch.setattr(st, 'stt_service_models', ['soniox', 'parakeet-window', 'dg-nova-3', 'modulate-velma-2'])
    calls = []
    ordered = [st.STTService.soniox, st.STTService.parakeet, st.STTService.deepgram, st.STTService.modulate]
    candidates = [s for s in ordered if s != primary]

    async def connect(service):
        calls.append(service)
        if service == candidates[-1]:
            return socket()
        raise RuntimeError('unavailable')

    failed = set()
    _, actual = await st.connect_stt_socket_with_fallback(
        primary_service=primary,
        connect_primary=lambda: connect(primary),
        connect_soniox=lambda: connect(st.STTService.soniox),
        connect_parakeet=lambda: connect(st.STTService.parakeet),
        connect_deepgram=lambda: connect(st.STTService.deepgram),
        connect_modulate=lambda: connect(st.STTService.modulate),
        failed=failed,
    )
    assert calls == [primary, *candidates]
    assert actual == candidates[-1]
    assert failed == {provider_for_service(s) for s in calls[:-1]}
    for service in calls[:-1]:
        assert st._circuit_for_primary(service).state == 'open'


@pytest.mark.asyncio
async def test_failed_session_provider_is_never_revisited(monkeypatch):
    monkeypatch.setattr(st, 'stt_service_models', ['modulate-velma-2', 'soniox'])
    modulate, soniox = AsyncMock(), AsyncMock(return_value=socket())
    _, actual = await st.connect_stt_socket_with_fallback(
        primary_service=st.STTService.modulate, connect_primary=modulate, connect_soniox=soniox, failed={'modulate'}
    )
    assert actual == st.STTService.soniox
    modulate.assert_not_called()


@pytest.mark.asyncio
async def test_three_failed_connects_shed_all_open_breakers_with_retry_after(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    monkeypatch.setattr(
        live_chain.health,
        'cached_snapshot',
        lambda providers, _language: {
            provider: live_health.ProviderState(bench='selection', bench_until=9999999999) for provider in providers
        },
    )
    callbacks = {service: AsyncMock(return_value=socket()) for service in st.STTService}
    for service in (st.STTService.modulate, st.STTService.soniox, st.STTService.parakeet):
        callbacks[service].side_effect = RuntimeError('connect failed')
    with pytest.raises(RuntimeError, match='exhausted'):
        await live_chain.connect_configured_chain(
            primary_service=st.STTService.modulate,
            connect_primary=callbacks[st.STTService.modulate],
            callbacks=callbacks,
            failed=set(),
            models=['modulate-velma-2', 'soniox', 'parakeet'],
            routing_uid='test',
        )
    assert len(live_chain._recent_connect_failures) == 3
    for callback in callbacks.values():
        callback.reset_mock()
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')

    with pytest.raises(live_chain.ProviderChainUnavailable) as raised:
        await live_chain.connect_configured_chain(
            primary_service=st.STTService.modulate,
            connect_primary=callbacks[st.STTService.modulate],
            callbacks=callbacks,
            failed=set(),
            models=['modulate-velma-2', 'soniox', 'parakeet'],
            routing_uid='test',
        )

    assert raised.value.retry_after >= 5
    for callback in callbacks.values():
        callback.assert_not_called()


@pytest.mark.asyncio
async def test_all_local_benches_with_fleet_healthy_do_not_shed(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    monkeypatch.setattr(live_chain.health, 'has_fresh_fleet_snapshot', lambda: True)
    monkeypatch.setattr(
        live_chain.health,
        'cached_snapshot',
        lambda _providers, _language: {'soniox': live_health.ProviderState(score=0.9, samples=20)},
    )
    live_chain._recent_connect_failures.extend((time.monotonic(), 'modulate') for _ in range(3))
    st._modulate_circuit.record_account_failure(600)
    st._soniox_circuit.record_serve_failure()
    primary, tail = AsyncMock(return_value=socket()), AsyncMock(return_value=socket())
    _, selected = await live_chain.connect_configured_chain(
        primary_service=st.STTService.modulate,
        connect_primary=primary,
        callbacks={st.STTService.soniox: tail},
        failed=set(),
        models=['modulate-velma-2', 'soniox'],
        routing_uid='test',
    )
    assert selected == st.STTService.soniox
    primary.assert_not_awaited()
    tail.assert_awaited_once()
    assert not live_chain._recent_connect_failures


@pytest.mark.asyncio
async def test_all_local_benches_with_fresh_fleet_outage_shed_without_connect_evidence(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    monkeypatch.setattr(live_chain.health, 'has_fresh_fleet_snapshot', lambda: True)
    monkeypatch.setattr(
        live_chain.health,
        'cached_snapshot',
        lambda providers, _language: {
            provider: live_health.ProviderState(bench='selection', bench_until=time.time() + 120)
            for provider in providers
        },
    )
    st._modulate_circuit.record_serve_failure()
    st._soniox_circuit.record_serve_failure()
    primary, tail = AsyncMock(return_value=socket()), AsyncMock(return_value=socket())

    with pytest.raises(live_chain.ProviderChainUnavailable) as raised:
        await live_chain.connect_configured_chain(
            primary_service=st.STTService.modulate,
            connect_primary=primary,
            callbacks={st.STTService.soniox: tail},
            failed=set(),
            models=['modulate-velma-2', 'soniox'],
            routing_uid='test',
        )

    assert raised.value.retry_after >= 120
    primary.assert_not_awaited()
    tail.assert_not_awaited()
    assert not live_chain._recent_connect_failures


@pytest.mark.asyncio
async def test_unknown_fleet_requires_configured_number_of_real_connect_failures(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    monkeypatch.setenv('STT_SHED_CONNECT_FAILURES', '2')
    monkeypatch.setattr(live_chain.health, 'cached_snapshot', lambda _providers, _language: {})
    st._modulate_circuit.record_serve_failure()
    st._soniox_circuit.record_account_failure(600)
    primary = AsyncMock(side_effect=RuntimeError('connect failed'))
    kwargs = dict(
        primary_service=st.STTService.modulate,
        connect_primary=primary,
        callbacks={st.STTService.soniox: AsyncMock(return_value=socket())},
        failed=set(),
        models=['modulate-velma-2', 'soniox'],
        routing_uid='test',
    )
    with pytest.raises(RuntimeError, match='exhausted'):
        await live_chain.connect_configured_chain(**kwargs)
    assert [provider for _, provider in live_chain._recent_connect_failures] == ['modulate']
    with pytest.raises(RuntimeError, match='exhausted'):
        await live_chain.connect_configured_chain(**kwargs)
    assert [provider for _, provider in live_chain._recent_connect_failures] == ['modulate']
    primary.assert_awaited_once()


@pytest.mark.asyncio
async def test_success_resets_failed_connect_shed_gate(monkeypatch):
    failing = AsyncMock(side_effect=RuntimeError('connect failed'))
    healthy = AsyncMock(return_value=socket())
    kwargs = dict(
        primary_service=st.STTService.modulate,
        connect_primary=failing,
        callbacks={st.STTService.soniox: healthy},
        failed=set(),
        models=['modulate-velma-2', 'soniox'],
    )
    _, selected = await live_chain.connect_configured_chain(**kwargs)
    assert selected == st.STTService.soniox
    failing.assert_awaited_once()
    assert not live_chain._recent_connect_failures
    st._soniox_circuit.record_account_failure(600)
    with pytest.raises(RuntimeError, match='exhausted'):
        await live_chain.connect_configured_chain(**kwargs)
    assert not live_chain._recent_connect_failures
    failing.assert_awaited_once()


@pytest.mark.asyncio
async def test_old_connect_failures_cannot_confirm_a_new_outage():
    expired = time.monotonic() - live_chain._FAILURE_EVIDENCE_SECONDS - 1
    live_chain._recent_connect_failures.extend((expired, 'soniox') for _ in range(3))
    st._modulate_circuit.record_account_failure(600)
    st._soniox_circuit.record_account_failure(600)
    with pytest.raises(RuntimeError, match='exhausted'):
        await live_chain.connect_configured_chain(
            primary_service=st.STTService.modulate,
            connect_primary=AsyncMock(return_value=socket()),
            callbacks={st.STTService.soniox: AsyncMock(return_value=socket())},
            failed=set(),
            models=['modulate-velma-2', 'soniox'],
        )
    assert not live_chain._recent_connect_failures


@pytest.mark.asyncio
async def test_expired_breaker_still_admits_its_half_open_probe(monkeypatch):
    monkeypatch.setattr(st, 'stt_service_models', ['soniox', 'modulate-velma-2', 'parakeet'])
    now = [0.0]
    probe_circuit = resilience.ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=30, clock=lambda: now[0])
    probe_circuit.record_failure()
    monkeypatch.setattr(st, '_soniox_circuit', probe_circuit)
    for service in (st.STTService.modulate, st.STTService.parakeet, st.STTService.deepgram):
        st._circuit_for_primary(service).record_account_failure(600)
    now[0] = 31

    soniox = AsyncMock(return_value=socket())
    unused = {service: AsyncMock(return_value=socket()) for service in st.STTService}
    _, selected = await live_chain.connect_configured_chain(
        primary_service=st.STTService.soniox,
        connect_primary=soniox,
        callbacks=unused,
        failed=set(),
        models=['soniox', 'modulate-velma-2', 'parakeet'],
    )

    assert selected == st.STTService.soniox
    soniox.assert_awaited_once()
    for callback in unused.values():
        callback.assert_not_called()


@pytest.mark.asyncio
async def test_idle_half_open_recovery_probe_is_not_shed(monkeypatch):
    monkeypatch.setattr(st, 'stt_service_models', ['soniox', 'modulate-velma-2', 'parakeet'])
    now = [0.0]
    probe_circuit = resilience.ProviderCircuitBreaker(
        failure_threshold=1, cooldown_seconds=30, serve_error_cooldown_seconds=30, clock=lambda: now[0]
    )
    probe_circuit.record_serve_failure()
    now[0] = 31
    assert probe_circuit.allow_request()
    probe_circuit.record_success()  # Grace success leaves a serve-error bench half-open.
    assert probe_circuit.state == 'half_open'
    monkeypatch.setattr(st, '_soniox_circuit', probe_circuit)
    st._modulate_circuit.record_account_failure(600)
    st._parakeet_circuit.record_account_failure(600)

    recovering = AsyncMock(return_value=socket())
    callbacks = {service: AsyncMock(return_value=socket()) for service in st.STTService}
    _, selected = await live_chain.connect_configured_chain(
        primary_service=st.STTService.soniox,
        connect_primary=recovering,
        callbacks=callbacks,
        failed=set(),
        models=['soniox', 'modulate-velma-2', 'parakeet'],
    )

    assert selected == st.STTService.soniox
    recovering.assert_awaited_once()
    callbacks[st.STTService.modulate].assert_not_awaited()
    callbacks[st.STTService.parakeet].assert_not_awaited()


@pytest.mark.asyncio
async def test_open_primary_skips_to_healthy_tail_then_serve_error_last_resort(monkeypatch):
    monkeypatch.setattr(st, 'stt_service_models', ['modulate-velma-2', 'soniox'])
    st._modulate_circuit.record_serve_failure()
    primary, tail = AsyncMock(return_value=socket()), AsyncMock(return_value=socket())
    await st.connect_stt_socket_with_fallback(
        primary_service=st.STTService.modulate, connect_primary=primary, connect_soniox=tail
    )
    primary.assert_not_called()
    tail.assert_awaited_once()
    st._soniox_circuit.record_serve_failure()
    _, selected = await st.connect_stt_socket_with_fallback(
        primary_service=st.STTService.modulate, connect_primary=primary, connect_soniox=tail
    )
    assert selected == st.STTService.modulate
    primary.assert_awaited_once()
    tail.assert_awaited_once()


@pytest.mark.asyncio
async def test_last_resort_never_bypasses_account_cooldown(monkeypatch):
    monkeypatch.setattr(st, 'stt_service_models', ['modulate-velma-2', 'soniox'])
    st._modulate_circuit.record_account_failure(1800)
    st._soniox_circuit.record_account_failure(1800)
    primary = AsyncMock(return_value=socket())
    for _ in range(2):
        with pytest.raises(RuntimeError, match='exhausted'):
            await st.connect_stt_socket_with_fallback(
                primary_service=st.STTService.modulate,
                connect_primary=primary,
                connect_soniox=AsyncMock(return_value=socket()),
            )
    primary.assert_not_called()


@pytest.mark.asyncio
async def test_last_resort_never_force_dials_open_tdt(monkeypatch):
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'soniox'])
    st._parakeet_circuit.record_serve_failure()
    st._soniox_circuit.record_serve_failure()
    primary, tail = AsyncMock(return_value=socket()), AsyncMock(return_value=socket())
    _, selected = await st.connect_stt_socket_with_fallback(
        primary_service=st.STTService.parakeet, connect_primary=primary, connect_soniox=tail
    )
    assert selected == st.STTService.soniox
    primary.assert_not_called()
    tail.assert_awaited_once()


@pytest.mark.asyncio
async def test_configured_chain_emits_exhausted_only_when_terminal(monkeypatch):
    from utils.stt import live_chain

    monkeypatch.setattr(st, 'stt_service_models', ['modulate-velma-2', 'soniox'])
    events = []
    monkeypatch.setattr(live_failure, 'record_fallback', lambda **kw: events.append(kw))
    with pytest.raises(RuntimeError, match='exhausted'):
        await st.connect_stt_socket_with_fallback(
            primary_service=st.STTService.modulate,
            connect_primary=AsyncMock(side_effect=RuntimeError('down')),
            connect_soniox=AsyncMock(side_effect=RuntimeError('down')),
        )
    exhausted = [event for event in events if event['outcome'] == 'exhausted']
    assert len(exhausted) == 1
    assert exhausted[0]['to_mode'] == 'unavailable'
    assert all(event['outcome'] == 'degraded' for event in events if event is not exhausted[0])


@pytest.mark.asyncio
async def test_cancelled_probe_is_released_and_socket_closed(monkeypatch):
    monkeypatch.setattr(st, 'stt_service_models', ['modulate-velma-2'])
    now = [0.0]
    circuit = resilience.ProviderCircuitBreaker(
        failure_threshold=1,
        cooldown_seconds=30,
        serve_error_cooldown_seconds=30,
        clock=lambda: now[0],
    )
    circuit.record_serve_failure()
    now[0] = 31
    monkeypatch.setattr(st, '_modulate_circuit', circuit)
    started = asyncio.Event()

    async def connect():
        started.set()
        await asyncio.Future()

    task = asyncio.create_task(
        st.connect_stt_socket_with_fallback(primary_service=st.STTService.modulate, connect_primary=connect)
    )
    await started.wait()
    assert not st._modulate_circuit.allow_request(force=True)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert st._modulate_circuit.allow_request(force=True)


@pytest.mark.parametrize('status', [401, 402, 403])
@pytest.mark.asyncio
async def test_account_refusal_has_long_cooldown_and_auth_reason(monkeypatch, status):
    monkeypatch.setattr(st, 'stt_service_models', ['dg-nova-3', 'soniox'])
    now = [0.0]
    circuit = resilience.ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30, clock=lambda: now[0])
    monkeypatch.setattr(st, '_deepgram_circuit', circuit)
    from utils.stt import live_chain

    events = []
    monkeypatch.setattr(live_failure, 'record_fallback', lambda **kw: events.append(kw))
    await st.connect_stt_socket_with_fallback(
        primary_service=st.STTService.deepgram,
        connect_primary=AsyncMock(side_effect=st.DeepgramConnectionRejection('account', status)),
        connect_soniox=AsyncMock(return_value=socket()),
    )
    assert events[0]['reason'] == 'auth'
    now[0] = 1799
    assert not circuit.allow_request(max_probes=4)
    now[0] = 1800
    assert circuit.allow_request(max_probes=4)
    assert not circuit.allow_request(max_probes=4)


@pytest.mark.parametrize(
    'error', ['organization_monthly_budget_exhausted', 'organization_balance_exhausted', 'invalid_api_key']
)
def test_soniox_account_codes_are_typed(error):
    assert soniox_death_reason(None, error) == (
        PROVIDER_AUTH_REJECTED if error == 'invalid_api_key' else PROVIDER_BUDGET_EXHAUSTED
    )


def test_parallel_half_open_and_late_success_cannot_erase_a_failure():
    now = [0.0]
    cb = resilience.ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=30, clock=lambda: now[0])
    cb.record_failure()
    now[0] = 30
    assert cb.allow_request(max_probes=2)
    assert cb.allow_request(max_probes=2)
    assert not cb.allow_request(max_probes=2)
    cb.record_failure()
    cb.record_success(respect_open=True)
    assert cb.state == 'open'


@pytest.mark.asyncio
async def test_default_darkness_preserves_fixed_order_and_ignores_fallback_breaker(monkeypatch):
    monkeypatch.delenv('STT_CONNECT_ORDER_FROM_CONFIG')
    monkeypatch.setattr(st, 'stt_service_models', ['modulate-velma-2', 'soniox', 'dg-nova-3', 'parakeet'])
    assert st.get_stt_service_for_language('en', window_uid='user') == (st.STTService.modulate, 'multi', 'velma-2')
    st._deepgram_circuit.record_serve_failure()
    soniox = AsyncMock(return_value=socket())
    dg = AsyncMock(return_value=socket())
    _, actual = await st.connect_stt_socket_with_fallback(
        primary_service=st.STTService.modulate,
        connect_primary=AsyncMock(side_effect=RuntimeError()),
        connect_soniox=soniox,
        connect_deepgram=dg,
    )
    assert actual == st.STTService.deepgram
    soniox.assert_not_called()
    assert st._deepgram_circuit.state == 'open'
    # Existing open-primary behavior is preserved, even though it strands a start.
    st._modulate_circuit.record_serve_failure()
    primary = AsyncMock(return_value=socket())
    with pytest.raises(RuntimeError):
        await st.connect_stt_socket_with_fallback(primary_service=st.STTService.modulate, connect_primary=primary)
    primary.assert_not_called()


@pytest.mark.parametrize(
    'multi,custom,byok', [(True, False, {}), (False, True, {}), (False, False, {'deepgram': 'test'})]
)
def test_excluded_session_shapes_do_not_enter_new_chain(monkeypatch, multi, custom, byok):
    from utils import byok as byok_module

    monkeypatch.setattr(byok_module, 'get_byok_keys', lambda: byok)
    host = SimpleNamespace(is_multi_channel=multi, use_custom_stt=custom)
    assert not managed_chain_enabled(host)
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'soniox'])
    service, _, model = st.get_stt_service_for_language('en')
    assert service == st.STTService.soniox
    assert model == 'soniox'


def test_preflight_does_not_strand_a_start_with_an_open_primary(monkeypatch):
    monkeypatch.setattr(st, 'stt_service_models', ['modulate-velma-2', 'soniox'])
    st._modulate_circuit.record_serve_failure()
    assert st.is_stt_available()
    monkeypatch.delenv('STT_CONNECT_ORDER_FROM_CONFIG')
    assert not st.is_stt_available()


@pytest.mark.asyncio
async def test_soniox_accepted_upgrade_account_refusal_feeds_breaker(monkeypatch):
    monkeypatch.setattr(st, 'stt_service_models', ['soniox', 'modulate-velma-2'])
    closed = []
    dead = SimpleNamespace(
        is_connection_dead=True, typed_death_reason=PROVIDER_BUDGET_EXHAUSTED, finish=lambda: closed.append(1)
    )
    _, service = await st.connect_stt_socket_with_fallback(
        primary_service=st.STTService.soniox,
        connect_primary=AsyncMock(return_value=dead),
        connect_modulate=AsyncMock(return_value=socket()),
    )
    assert service == st.STTService.modulate
    assert st._soniox_circuit.state == 'open'
    assert closed == [1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'typed_reason,error_class',
    [(PROVIDER_BUDGET_EXHAUSTED, 'budget'), (PROVIDER_AUTH_REJECTED, 'auth')],
)
async def test_chain_account_death_labels_error_class_by_typed_reason(monkeypatch, typed_reason, error_class):
    # The connect counter must carry the typed token so a 402 reads
    # error_class=budget on the dashboard and leg-error alert; 'auth' is
    # reserved for actual authentication refusals. The account bench still
    # arms either way, while omi_fallback_total retains its legacy quota/auth labels.
    from utils.stt import live_chain

    monkeypatch.setattr(st, 'stt_service_models', ['soniox', 'modulate-velma-2'])
    connects, fallbacks = [], []
    monkeypatch.setattr(live_chain, 'record_stt_provider_connect', lambda **kw: connects.append(kw))
    monkeypatch.setattr(live_failure, 'record_fallback', lambda **kw: fallbacks.append(kw))
    dead = SimpleNamespace(is_connection_dead=True, typed_death_reason=typed_reason, finish=lambda: None)
    _, service = await st.connect_stt_socket_with_fallback(
        primary_service=st.STTService.soniox,
        connect_primary=AsyncMock(return_value=dead),
        connect_modulate=AsyncMock(return_value=socket()),
    )
    assert service == st.STTService.modulate
    failures = [call for call in connects if call['outcome'] == 'failure']
    assert len(failures) == 1
    assert failures[0]['provider'] == 'soniox'
    assert failures[0]['reason'] == typed_reason
    assert connect_metrics.connect_error_class(failures[0]['reason']) == error_class
    assert st._soniox_circuit.state == 'open'  # account bench armed, unchanged
    assert fallbacks, 'the bounded fallback vocabulary is still recorded'
    fallback_reason = 'quota' if error_class == 'budget' else 'auth'
    assert all(event['reason'] == fallback_reason for event in fallbacks)


def test_mid_session_metrics_retain_their_bounded_vocabulary():
    from utils.observability.fallback import bucket_component, bucket_reason

    assert bucket_component('stt_live_session') == 'stt_live_session'
    assert bucket_reason('connection_lost') == 'connection_lost'


def test_soniox_circuit_owns_its_env_only_after_enablement(monkeypatch):
    monkeypatch.setenv('SONIOX_CIRCUIT_FAILURE_THRESHOLD', '1')
    monkeypatch.setenv('MODULATE_CIRCUIT_FAILURE_THRESHOLD', '2')
    enabled = resilience.soniox_circuit_from_env()
    enabled.record_failure()
    assert enabled.state == 'open'
    monkeypatch.delenv('STT_CONNECT_ORDER_FROM_CONFIG')
    legacy = resilience.soniox_circuit_from_env()
    legacy.record_failure()
    assert legacy.state == 'closed'
    legacy.record_failure()
    assert legacy.state == 'open'


def test_late_probe_callbacks_cannot_consume_a_new_generation_probe():
    now = [0.0]
    cb = resilience.ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=1, clock=lambda: now[0])
    cb.record_failure()
    now[0] = 1
    assert cb.allow_request()
    success, cancel = cb.deferred_result_callbacks()
    cb.record_failure()
    now[0] = 2
    assert cb.allow_request()
    success()
    cancel()
    assert cb.state == 'half_open'
    assert not cb.allow_request()


@pytest.mark.parametrize('provider', ['soniox', 'modulate'])
@pytest.mark.parametrize('reason', [PROVIDER_BUDGET_EXHAUSTED, PROVIDER_AUTH_REJECTED])
def test_shared_typed_account_death_uses_long_cooldown_and_one_probe(monkeypatch, provider, reason):
    from utils.stt.live_failure import note_typed_provider_death
    from utils.stt.live_reason import normalize_live_stt_reason

    now = [0.0]
    cb = resilience.ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30, clock=lambda: now[0])
    monkeypatch.setattr(st, f'_{provider}_circuit', cb)
    assert note_typed_provider_death(socket(typed_death_reason=reason), provider)
    now[0] = 1799
    assert not cb.allow_request(max_probes=4)
    now[0] = 1800
    assert cb.allow_request(max_probes=4)
    assert not cb.allow_request(max_probes=4)
    assert normalize_live_stt_reason(reason) == reason


@pytest.mark.parametrize('code', [401, 403])
def test_soniox_auth_uses_shared_type_only_when_enabled(monkeypatch, code):
    assert soniox_death_reason(code, 'unknown') == PROVIDER_AUTH_REJECTED
    monkeypatch.delenv('STT_CONNECT_ORDER_FROM_CONFIG')
    assert soniox_death_reason(code, 'unknown') == 'connection_lost'
    # The upstream budget fix is unconditional, including project budgets.
    assert soniox_death_reason(402, 'project_monthly_budget_exhausted') == PROVIDER_BUDGET_EXHAUSTED


@pytest.fixture
def connect_backoff(monkeypatch):
    now = [0.0]
    instance = connect_backoff_module.ConnectRefusalBackoff(clock=lambda: now[0])
    monkeypatch.setattr(live_chain, 'connect_backoff', lambda: instance)
    instance.now = now
    return instance


def _soniox_then_modulate(**overrides):
    return dict(
        primary_service=st.STTService.soniox,
        connect_primary=overrides.get('soniox'),
        callbacks={st.STTService.modulate: overrides.get('modulate', AsyncMock(return_value=socket()))},
        failed=overrides.get('failed', set()),
        models=['soniox', 'modulate-velma-2'],
    )


@pytest.mark.asyncio
async def test_isolated_429_leaves_fresh_sessions_dialing_soniox(connect_backoff):
    soniox = AsyncMock(side_effect=SonioxRateLimitError('transient'))
    _, service = await live_chain.connect_configured_chain(**_soniox_then_modulate(soniox=soniox))
    assert service == st.STTService.modulate
    serving = AsyncMock(return_value=socket())
    _, service = await live_chain.connect_configured_chain(**_soniox_then_modulate(soniox=serving))
    assert service == st.STTService.soniox
    serving.assert_awaited_once()


@pytest.mark.asyncio
async def test_three_429s_skip_fresh_soniox_dials_without_a_bench(connect_backoff, monkeypatch):
    soniox = AsyncMock(side_effect=SonioxRateLimitError('transient'))
    modulate = AsyncMock(return_value=socket())
    for _ in range(3):
        _, service = await live_chain.connect_configured_chain(
            **_soniox_then_modulate(soniox=soniox, modulate=modulate)
        )
        assert service == st.STTService.modulate
    assert soniox.await_count == 3
    events = []
    monkeypatch.setattr(live_chain, 'record_fallback', lambda **kw: events.append(kw))
    _, service = await live_chain.connect_configured_chain(**_soniox_then_modulate(soniox=soniox, modulate=modulate))
    assert service == st.STTService.modulate
    assert soniox.await_count == 3
    assert modulate.await_count == 4
    assert any(
        event['reason'] == 'circuit_open' and event['to_mode'] == 'soniox' and event['outcome'] == 'degraded'
        for event in events
    )
    assert st._soniox_circuit.state == 'closed'


@pytest.mark.asyncio
async def test_refusals_older_than_the_window_do_not_open(connect_backoff):
    soniox = AsyncMock(side_effect=SonioxRateLimitError('transient'))
    for _ in range(3):
        await live_chain.connect_configured_chain(**_soniox_then_modulate(soniox=soniox))
        connect_backoff.now[0] += 10.5
    serving = AsyncMock(return_value=socket())
    _, service = await live_chain.connect_configured_chain(**_soniox_then_modulate(soniox=serving))
    assert service == st.STTService.soniox
    serving.assert_awaited_once()


@pytest.mark.asyncio
async def test_probe_is_exclusive_and_sessions_do_not_wait(connect_backoff):
    soniox = AsyncMock(side_effect=SonioxRateLimitError('transient'))
    for _ in range(3):
        await live_chain.connect_configured_chain(**_soniox_then_modulate(soniox=soniox))
    connect_backoff.now[0] += 2.0
    started, release = asyncio.Event(), asyncio.Event()

    async def probe():
        started.set()
        await release.wait()
        return socket()

    task = asyncio.create_task(live_chain.connect_configured_chain(**_soniox_then_modulate(soniox=probe)))
    await started.wait()
    blocked = AsyncMock(side_effect=AssertionError('held probe must gate every other session'))
    for _ in range(39):
        _, service = await live_chain.connect_configured_chain(**_soniox_then_modulate(soniox=blocked))
        assert service == st.STTService.modulate
    blocked.assert_not_called()
    release.set()
    _, service = await task
    assert service == st.STTService.soniox


@pytest.mark.asyncio
async def test_refused_probe_escalates_and_successful_probe_resets(connect_backoff):
    soniox = AsyncMock(side_effect=SonioxRateLimitError('transient'))
    for _ in range(3):
        await live_chain.connect_configured_chain(**_soniox_then_modulate(soniox=soniox))
    for cooldown in (2.0, 4.0):
        connect_backoff.now[0] += cooldown - 0.1
        await live_chain.connect_configured_chain(
            **_soniox_then_modulate(soniox=AsyncMock(side_effect=AssertionError('still cooling')))
        )
        connect_backoff.now[0] += 0.1
        await live_chain.connect_configured_chain(**_soniox_then_modulate(soniox=soniox))
    connect_backoff.now[0] += 8.0
    serving = AsyncMock(return_value=socket())
    _, service = await live_chain.connect_configured_chain(**_soniox_then_modulate(soniox=serving))
    assert service == st.STTService.soniox
    _, service = await live_chain.connect_configured_chain(
        **_soniox_then_modulate(soniox=AsyncMock(side_effect=SonioxRateLimitError('transient')))
    )
    assert service == st.STTService.modulate
    retry = AsyncMock(return_value=socket())
    _, service = await live_chain.connect_configured_chain(**_soniox_then_modulate(soniox=retry))
    assert service == st.STTService.soniox
    retry.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancelled_probe_releases_without_immediate_second_probe(connect_backoff):
    soniox = AsyncMock(side_effect=SonioxRateLimitError('transient'))
    for _ in range(3):
        await live_chain.connect_configured_chain(**_soniox_then_modulate(soniox=soniox))
    connect_backoff.now[0] += 2.0
    started = asyncio.Event()

    async def probe():
        started.set()
        await asyncio.Future()

    task = asyncio.create_task(live_chain.connect_configured_chain(**_soniox_then_modulate(soniox=probe)))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    blocked = AsyncMock(side_effect=AssertionError('cancel re-cools the probe slot'))
    _, service = await live_chain.connect_configured_chain(**_soniox_then_modulate(soniox=blocked))
    assert service == st.STTService.modulate
    blocked.assert_not_called()
    connect_backoff.now[0] += 2.0
    serving = AsyncMock(return_value=socket())
    _, service = await live_chain.connect_configured_chain(**_soniox_then_modulate(soniox=serving))
    assert service == st.STTService.soniox


@pytest.mark.asyncio
async def test_connect_refused_errors_count_toward_the_gate(connect_backoff, monkeypatch):
    monkeypatch.setattr(
        st, '_soniox_circuit', resilience.ProviderCircuitBreaker(failure_threshold=10, cooldown_seconds=30)
    )
    soniox = AsyncMock(side_effect=ConnectionRefusedError())
    for _ in range(3):
        _, service = await live_chain.connect_configured_chain(**_soniox_then_modulate(soniox=soniox))
        assert service == st.STTService.modulate
    await live_chain.connect_configured_chain(**_soniox_then_modulate(soniox=soniox))
    assert soniox.await_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'reason,expected_dials',
    [
        ('auth', 1),
        ('provider_budget_exhausted', 1),
        ('provider_auth_rejected', 1),
        ('capacity_full', 3),
        ('config_incomplete', 3),
        ('vad_failed', 3),
    ],
)
async def test_non_refusal_outcomes_do_not_count_toward_the_gate(connect_backoff, monkeypatch, reason, expected_dials):
    monkeypatch.setattr(live_chain, 'note_capacity_full', lambda *args: None)
    soniox = AsyncMock(side_effect=live_chain.RejectedStream(reason))
    for _ in range(3):
        monkeypatch.setattr(
            st, '_soniox_circuit', resilience.ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30)
        )
        _, service = await live_chain.connect_configured_chain(**_soniox_then_modulate(soniox=soniox))
        assert service == st.STTService.modulate
    assert soniox.await_count == expected_dials
    state = connect_backoff._states.get('soniox')
    assert state is None or not state.refusals


@pytest.mark.asyncio
async def test_all_cooled_targets_get_one_bounded_escape_and_can_recover(connect_backoff):
    soniox = AsyncMock(side_effect=SonioxRateLimitError('transient'))
    modulate = AsyncMock(side_effect=SonioxRateLimitError('transient'))
    for _ in range(3):
        with pytest.raises(RuntimeError, match='exhausted'):
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.soniox,
                connect_primary=soniox,
                callbacks={st.STTService.modulate: modulate},
                failed=set(),
                models=['soniox', 'modulate-velma-2'],
            )
    soniox.reset_mock()
    modulate.reset_mock()
    with pytest.raises(RuntimeError, match='exhausted'):
        await live_chain.connect_configured_chain(
            primary_service=st.STTService.soniox,
            connect_primary=soniox,
            callbacks={st.STTService.modulate: modulate},
            failed=set(),
            models=['soniox', 'modulate-velma-2'],
        )
    assert soniox.await_count == 1
    modulate.assert_not_called()
    recovered = AsyncMock(return_value=socket())
    _, service = await live_chain.connect_configured_chain(
        primary_service=st.STTService.soniox,
        connect_primary=recovered,
        callbacks={st.STTService.modulate: modulate},
        failed=set(),
        models=['soniox', 'modulate-velma-2'],
    )
    assert service == st.STTService.soniox
    recovered.assert_awaited_once()
    modulate.assert_not_called()


@pytest.mark.asyncio
async def test_all_cooling_escape_dials_only_the_earliest_expiry_once(connect_backoff):
    for _ in range(3):
        connect_backoff.acquire('modulate-velma-2', provider='modulate').finish(refused=True)
    connect_backoff.now[0] += 0.5
    for _ in range(3):
        connect_backoff.acquire('soniox', provider='soniox').finish(refused=True)
    host = SimpleNamespace(state=SimpleNamespace(active=True, shutdown_event=None), request=None)
    controller = recovery_state.LiveRecoveryController(host)
    token = recovery_state.current_recovery.set(controller)
    soniox = AsyncMock(side_effect=SonioxRateLimitError('transient'))
    modulate = AsyncMock(side_effect=SonioxRateLimitError('transient'))
    try:
        with pytest.raises(live_chain.LiveChainExhausted):
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.soniox,
                connect_primary=soniox,
                callbacks={st.STTService.modulate: modulate},
                failed=set(),
                models=['soniox', 'modulate-velma-2'],
            )
    finally:
        recovery_state.current_recovery.reset(token)
    modulate.assert_awaited_once()
    soniox.assert_not_called()
    assert connect_backoff.cooldown_until('modulate-velma-2') == 2.0
    assert connect_backoff.cooldown_until('soniox') == 2.5
    assert connect_backoff._states['modulate-velma-2'].cooldown_seconds == 2.0
    assert connect_backoff._states['soniox'].cooldown_seconds == 2.0
    assert controller.attempted_targets == {'modulate-velma-2'}


@pytest.mark.asyncio
@pytest.mark.parametrize('terminal', ['exhausted', 'departed', 'deadline_expired'])
async def test_cooling_escape_cannot_dial_a_terminal_episode(connect_backoff, terminal):
    for identity, provider in (('soniox', 'soniox'), ('modulate-velma-2', 'modulate')):
        for _ in range(3):
            connect_backoff.acquire(identity, provider=provider).finish(refused=True)
    host = SimpleNamespace(state=SimpleNamespace(active=True, shutdown_event=None), request=None)
    ticks = [0.0]
    controller = recovery_state.LiveRecoveryController(host, clock=lambda: ticks[0])
    if terminal == 'departed':
        controller.mark_client_leaving()
    elif terminal == 'deadline_expired':
        controller.begin(family='soniox')
        ticks[0] = recovery_state.RECOVERY_EPISODE_SECONDS + 1
    else:
        controller.state = recovery_state.RecoveryState.exhausted
    token = recovery_state.current_recovery.set(controller)
    soniox = AsyncMock(side_effect=AssertionError('a terminal episode has no escape dial'))
    modulate = AsyncMock(side_effect=AssertionError('a terminal episode has no escape dial'))
    try:
        with pytest.raises(live_chain.LiveChainExhausted):
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.soniox,
                connect_primary=soniox,
                callbacks={st.STTService.modulate: modulate},
                failed=set(),
                models=['soniox', 'modulate-velma-2'],
            )
    finally:
        recovery_state.current_recovery.reset(token)
    soniox.assert_not_called()
    modulate.assert_not_called()
    assert not controller.attempted_targets


@pytest.mark.asyncio
async def test_rescue_probe_auth_records_on_the_probed_circuit(connect_backoff, monkeypatch):
    """The rescue force-probe must charge its own breaker, not the route loop's
    last-bound circuit: Modulate's serve bench is force-probed while Soniox
    stays account-blocked; the probe's auth rejection arms Modulate's account
    bench and leaves Soniox's existing bench untouched."""
    monkeypatch.setattr(st, 'stt_service_models', ['modulate-velma-2', 'soniox'])
    st._modulate_circuit.record_serve_failure()
    st._soniox_circuit.record_account_failure(600)
    soniox_bench = st._soniox_circuit._account_cooldown
    soniox_opened = st._soniox_circuit._opened_at
    modulate = AsyncMock(side_effect=live_chain.RejectedStream('auth'))
    soniox = AsyncMock(side_effect=AssertionError('account bench must not be dialed'))
    with pytest.raises(RuntimeError, match='exhausted'):
        await st.connect_stt_socket_with_fallback(
            primary_service=st.STTService.modulate,
            connect_primary=modulate,
            connect_soniox=soniox,
        )
    modulate.assert_awaited_once()
    soniox.assert_not_called()
    assert st._modulate_circuit._account_cooldown == 1800
    assert st._soniox_circuit._account_cooldown == soniox_bench
    assert st._soniox_circuit._opened_at == soniox_opened
