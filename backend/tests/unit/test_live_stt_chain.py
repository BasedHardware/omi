"""Behavioral contracts for the September 2026 live provider-chain outage."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config.stt_provider_policy import STTServingSurface, model_is_enabled, provider_for_service
from utils.stt import provider_resilience as resilience, streaming as st
from utils.stt.live_rollout import managed_chain_enabled, window_allocation
from utils.stt.soniox import soniox_death_reason
from utils.stt.stream_close import PROVIDER_AUTH_REJECTED, PROVIDER_BUDGET_EXHAUSTED


@pytest.fixture(autouse=True)
def configured(monkeypatch):
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
    await st.connect_stt_socket_with_fallback(
        primary_service=st.STTService.modulate, connect_primary=primary, connect_soniox=tail
    )
    primary.assert_awaited_once()
    tail.assert_awaited_once()


@pytest.mark.asyncio
async def test_last_resort_never_bypasses_account_cooldown(monkeypatch):
    monkeypatch.setattr(st, 'stt_service_models', ['modulate-velma-2', 'soniox'])
    st._modulate_circuit.record_account_failure(1800)
    st._soniox_circuit.record_serve_failure()
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
    with pytest.raises(RuntimeError, match='exhausted'):
        await st.connect_stt_socket_with_fallback(
            primary_service=st.STTService.parakeet, connect_primary=primary, connect_soniox=tail
        )
    primary.assert_not_called()
    tail.assert_not_called()


@pytest.mark.asyncio
async def test_configured_chain_emits_exhausted_only_when_terminal(monkeypatch):
    from utils.stt import live_chain

    monkeypatch.setattr(st, 'stt_service_models', ['modulate-velma-2', 'soniox'])
    events = []
    monkeypatch.setattr(live_chain, 'record_fallback', lambda **kw: events.append(kw))
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
    st._modulate_circuit.record_serve_failure()
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
    monkeypatch.setattr(live_chain, 'record_fallback', lambda **kw: events.append(kw))
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
    from utils.stt.live_failure import note_typed_provider_death, fallback_reason_for_typed_death

    now = [0.0]
    cb = resilience.ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30, clock=lambda: now[0])
    monkeypatch.setattr(st, f'_{provider}_circuit', cb)
    assert note_typed_provider_death(socket(typed_death_reason=reason), provider)
    now[0] = 1799
    assert not cb.allow_request(max_probes=4)
    now[0] = 1800
    assert cb.allow_request(max_probes=4)
    assert not cb.allow_request(max_probes=4)
    assert fallback_reason_for_typed_death(reason) == ('quota' if reason == PROVIDER_BUDGET_EXHAUSTED else 'auth')


@pytest.mark.parametrize('code', [401, 403])
def test_soniox_auth_uses_shared_type_only_when_enabled(monkeypatch, code):
    assert soniox_death_reason(code, 'unknown') == PROVIDER_AUTH_REJECTED
    monkeypatch.delenv('STT_CONNECT_ORDER_FROM_CONFIG')
    assert soniox_death_reason(code, 'unknown') == 'connection_lost'
    # The upstream budget fix is unconditional, including project budgets.
    assert soniox_death_reason(402, 'project_monthly_budget_exhausted') == PROVIDER_BUDGET_EXHAUSTED
