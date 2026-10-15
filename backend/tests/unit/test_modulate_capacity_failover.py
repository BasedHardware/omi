"""A local window refusal must not strand live sessions behind a serving bench."""

import asyncio
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from prometheus_client import CollectorRegistry, Counter, generate_latest

import routers.listen.receiver as receiver_module
from routers.listen.receiver import ListenReceiver
from tests.unit.test_parakeet_window_live import runtime, _flush_capture
from tests.unit.test_parakeet_failover_exhausted import Replacement, setup_chain
from utils.observability import fallback
from utils.stt import live_chain, live_router, parakeet_window as window, streaming as st
from utils.stt.live_metrics import CHAIN_EXHAUSTED, WINDOW_ADMISSION


@pytest.fixture(autouse=True)
def _stt_failover_recovery_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')


@pytest.fixture(autouse=True)
def serving(monkeypatch, runtime):
    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '0')
    monkeypatch.setenv('PARAKEET_WINDOW_MAX_SESSIONS', '8')
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'modulate-velma-2', 'soniox'])
    monkeypatch.setattr(live_chain.health, 'has_fresh_fleet_snapshot', lambda: False)
    monkeypatch.setattr(live_chain.health, 'cached_snapshot', lambda *args: {})
    monkeypatch.setattr(live_router, '_capacity_until', {})


def host():
    return SimpleNamespace(
        stt_service=st.STTService.modulate,
        stt_language='en',
        stt_model='velma-2',
        language='en',
        language_profile=None,
        multi_lang_enabled=True,
        vocabulary=[],
        is_multi_channel=False,
        use_custom_stt=False,
        session_id='synthetic',
        request=SimpleNamespace(uid='synthetic', vad_gate_override=False, websocket=AsyncMock()),
        state=SimpleNamespace(active=True, stt_terminal_failure=False),
        client_device_context=SimpleNamespace(platform='ios'),
    )


def dead_receiver():
    actual = ListenReceiver(host(), [], {})
    previous = Replacement(lambda _: None)
    previous.is_connection_dead = True
    previous.typed_death_reason = 'modulate_serve_error'
    actual.stt_socket = previous
    actual._stt_rebuild = (lambda: (lambda _: None, lambda _: None, None), 16000)
    return actual


@pytest.mark.asyncio
async def test_capacity_refusal_reaches_serving_benched_soniox(monkeypatch):
    st._soniox_circuit.record_serve_failure()
    para = AsyncMock(side_effect=st.ParakeetConnectionError('capacity_full', capacity_subtype='admission'))
    son = AsyncMock(return_value=Replacement(lambda _: None))
    _, actual = await live_chain.connect_configured_chain(
        primary_service=st.STTService.parakeet,
        connect_primary=para,
        callbacks={st.STTService.modulate: AsyncMock(), st.STTService.soniox: son},
        failed={'modulate'},
        models=st.stt_service_models,
    )
    assert actual == st.STTService.soniox
    para.assert_awaited_once()
    son.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('revision', ['6a26acc', 'afa7800', '0ba6edb'])
@pytest.mark.parametrize('previous_soniox', [False, True])
async def test_historical_open_window_and_soniox_exhaust_with_failed_modulate(revision, previous_soniox):
    source = subprocess.run(
        ['git', 'show', f'{revision}:backend/utils/stt/live_chain.py'],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    source = source.replace('fallback_reason_for_typed_death', 'fallback_metric_reason')
    namespace = {'__name__': f'historical_chain_{revision}'}
    exec(compile(source, f'{revision}/live_chain.py', 'exec'), namespace)
    st._parakeet_circuit.record_serve_failure()
    if not previous_soniox:
        st._soniox_circuit.record_serve_failure()
    failed = {'modulate', 'soniox'} if previous_soniox else {'modulate'}
    para, son = AsyncMock(), AsyncMock(return_value=Replacement(lambda _: None))
    with pytest.raises(RuntimeError, match='Configured STT chain exhausted'):
        await namespace['connect_configured_chain'](
            primary_service=st.STTService.parakeet,
            connect_primary=para,
            callbacks={st.STTService.modulate: AsyncMock(), st.STTService.soniox: son},
            failed=failed,
            models=st.stt_service_models,
        )
    para.assert_not_awaited()
    son.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('previous_soniox', [False, True])
async def test_concurrent_modulate_deaths_at_window_capacity_continue_on_soniox(monkeypatch, previous_soniox):
    admission = window.WindowAdmission()
    monkeypatch.setattr(window, 'admission', admission)
    releases = [admission.acquire() for _ in range(8)]
    window_connect = AsyncMock(side_effect=AssertionError('full window must be skipped'))
    monkeypatch.setattr(window, 'connect_window', window_connect)
    if not previous_soniox:
        st._soniox_circuit.record_serve_failure()
    replacements = []
    started, release_probe = asyncio.Event(), asyncio.Event()

    async def soniox(callback, *args, **kwargs):
        started.set()
        await release_probe.wait()
        leg = Replacement(callback)
        replacements.append(leg)
        return leg

    monkeypatch.setattr(st, 'process_audio_soniox', soniox)
    actuals = [dead_receiver() for _ in range(35)]
    if previous_soniox:
        for actual in actuals:
            actual._stt_failed_providers.add('soniox')
            actual._stt_failed_reasons['soniox'] = 'connection_lost'
    before = CHAIN_EXHAUSTED._value.get()
    overflow_before = WINDOW_ADMISSION.labels(outcome='overflow')._value.get()
    try:
        tasks = [asyncio.create_task(actual._failover_stt_socket()) for actual in actuals]
        await started.wait()
        await asyncio.sleep(0)
        release_probe.set()
        assert await asyncio.gather(*tasks) == [True] * 35
        assert len(replacements) == 35
        window_connect.assert_not_called()
        assert WINDOW_ADMISSION.labels(outcome='overflow')._value.get() - overflow_before == 35
        assert CHAIN_EXHAUSTED._value.get() == before
        for actual in actuals:
            assert actual.host.stt_service == st.STTService.soniox
            assert actual._stt_failed_providers == {'modulate'}
            assert not actual.host.state.stt_terminal_failure
            assert actual.stt_socket.send(b'\x01\x00' * 512)
        assert [len(leg.sent) for leg in replacements] == [1] * 35
    finally:
        for actual in actuals:
            actual.stt_socket.finish()
        for release in releases:
            release()


@pytest.mark.asyncio
async def test_failed_rebuild_is_latched_across_35_send_monitor_races(monkeypatch):
    actual = dead_receiver()
    actual._create_stt_socket = AsyncMock(side_effect=live_chain.LiveChainExhausted('Configured STT chain exhausted'))
    assert await asyncio.gather(*(actual._failover_stt_socket() for _ in range(35))) == [False] * 35
    actual._create_stt_socket.assert_awaited_once()
    assert actual._stt_failed_providers == {'modulate'}


def test_fallback_log_and_counter_match_and_first_burst_needs_zero_sample(monkeypatch, caplog):
    registry = CollectorRegistry()
    counter = Counter(
        'omi_fallback_total', 'test', ['component', 'from_mode', 'to_mode', 'reason', 'outcome'], registry=registry
    )
    monkeypatch.setattr(fallback, 'OMI_FALLBACK_TOTAL', counter)
    labels = dict(
        component='stt_live_session',
        from_mode='modulate',
        to_mode='parakeet',
        reason='capacity_full',
        outcome='exhausted',
    )
    assert b'omi_fallback_total{' not in generate_latest(registry)
    for _ in range(35):
        fallback.record_fallback(**labels)
    assert counter.labels(**labels)._value.get() == 35
    assert len([record for record in caplog.records if 'omi_fallback_event' in record.message]) == 35
    assert counter.labels(**labels)._value.get() - 35 == 0  # flat subsequent scrape: increase misses the first burst


@pytest.mark.parametrize('to_mode', ['parakeet', 'unavailable'])
def test_exhausted_children_have_a_zero_baseline_before_the_first_burst(monkeypatch, to_mode):
    registry = CollectorRegistry()
    counter = Counter(
        'omi_fallback_total', 'test', ['component', 'from_mode', 'to_mode', 'reason', 'outcome'], registry=registry
    )
    monkeypatch.setattr(fallback, 'OMI_FALLBACK_TOTAL', counter)
    fallback.initialize_live_stt_exhausted_children()
    labels = dict(
        component='stt_live_session',
        from_mode='modulate',
        to_mode=to_mode,
        reason='capacity_full',
        outcome='exhausted',
    )
    before = counter.labels(**labels)._value.get()
    assert before == 0
    for _ in range(35):
        fallback.record_fallback(**labels)
    assert counter.labels(**labels)._value.get() - before == 35


@pytest.mark.asyncio
@pytest.mark.parametrize('previous_soniox', [False, True])
async def test_window_origin_modulate_ring_pressure_replays_exactly_once_on_soniox(monkeypatch, previous_soniox):
    actual, _, _, legs, capture = await setup_chain(monkeypatch)
    try:
        assert await actual._failover_stt_socket()
        assert actual.host.stt_service == st.STTService.modulate
        if previous_soniox:
            actual._stt_failed_providers.add('soniox')
            actual._stt_failed_reasons['soniox'] = 'connection_lost'
        else:
            st._soniox_circuit.record_serve_failure()
        ring = actual._window_ring()
        ring.ring_seconds = len(capture) / (2 * 16000)
        next_audio = b'\x01\x00' * 640
        await _flush_capture(actual, next_audio, len(capture) // 2)
        assert actual.host.stt_service == st.STTService.soniox
        assert b''.join(legs['soniox'][0].sent) == capture + next_audio
        assert len(legs['soniox']) == 1
        assert not actual.host.state.stt_terminal_failure
    finally:
        await actual._drain_stt_sockets()


@pytest.mark.asyncio
async def test_unrecoverable_ring_pressure_terminates_once_without_rebuild_loop(monkeypatch):
    actual, _, _, _, capture = await setup_chain(monkeypatch)
    try:
        assert await actual._failover_stt_socket()
        st._soniox_circuit.record_account_failure(1800)
        ring = actual._window_ring()
        ring.ring_seconds = len(capture) / (2 * 16000)
        before = CHAIN_EXHAUSTED._value.get()
        await _flush_capture(actual, b'\x01\x00' * 640, len(capture) // 2)
        assert actual.host.state.stt_terminal_failure
        assert actual.recovery.exhausted
        assert CHAIN_EXHAUSTED._value.get() - before == 1
        assert await asyncio.gather(*(actual._failover_stt_socket() for _ in range(35))) == [False] * 35
        assert CHAIN_EXHAUSTED._value.get() - before == 1
        actual.host.request.websocket.close.assert_awaited_once()
    finally:
        await actual._drain_stt_sockets()


@pytest.mark.asyncio
async def test_capacity_cooldown_is_honoured_by_shadow_serving(monkeypatch):
    para = AsyncMock(side_effect=st.ParakeetConnectionError('capacity_full', capacity_subtype='admission'))
    son = AsyncMock(return_value=Replacement(lambda _: None))
    kwargs = dict(
        primary_service=st.STTService.parakeet,
        connect_primary=para,
        callbacks={st.STTService.soniox: son},
        models=['parakeet-window', 'soniox'],
        routing_uid='synthetic',
        routing_models={'parakeet': 'parakeet-window', 'soniox': 'soniox'},
    )
    assert (await live_chain.connect_configured_chain(**kwargs, failed=set()))[1] == st.STTService.soniox
    assert (await live_chain.connect_configured_chain(**kwargs, failed=set()))[1] == st.STTService.soniox
    para.assert_awaited_once()
    assert son.await_count == 2


@pytest.mark.asyncio
async def test_occupied_probe_wait_is_bounded_without_bypassing_account():
    circuit = st._soniox_circuit
    circuit.record_serve_failure()
    assert circuit.allow_request(force=True)
    assert not await live_chain._allow_rescue_probe(circuit, 1, asyncio.get_running_loop().time())
    circuit.record_account_failure(1800)
    assert not await live_chain._allow_rescue_probe(circuit, 1, asyncio.get_running_loop().time() + 12)


@pytest.mark.asyncio
async def test_previously_used_soniox_transport_loss_gets_one_healthy_rescue(monkeypatch):
    actual = dead_receiver()
    actual._stt_failed_providers.add('soniox')
    actual._stt_failed_reasons['soniox'] = 'connection_lost'
    st._parakeet_circuit.record_serve_failure()
    replacements = []

    async def connect(callback, *args, **kwargs):
        leg = Replacement(callback)
        replacements.append(leg)
        return leg

    monkeypatch.setattr(st, 'process_audio_soniox', connect)
    assert await actual._failover_stt_socket()
    assert actual.host.stt_service == st.STTService.soniox
    assert actual._stt_rescue_retries == {'soniox'}
    assert actual._stt_rebuild_attempts == 1
    replacements[0].is_connection_dead = True
    replacements[0].typed_death_reason = 'connection_lost'
    assert not await actual._failover_stt_socket()
    assert actual.recovery.exhausted
    assert len(replacements) == 1
    assert not await actual._failover_stt_socket()
    assert actual._stt_rebuild_attempts == 2


@pytest.mark.parametrize('reason', ['provider_budget_exhausted', 'provider_auth_rejected', 'provider_5xx'])
@pytest.mark.asyncio
async def test_previous_account_or_connect_failure_is_not_retried(monkeypatch, reason):
    actual = dead_receiver()
    actual._stt_failed_providers.add('soniox')
    actual._stt_failed_reasons['soniox'] = reason
    st._parakeet_circuit.record_serve_failure()
    connect = AsyncMock()
    monkeypatch.setattr(st, 'process_audio_soniox', connect)
    assert not await actual._failover_stt_socket()
    assert actual._stt_rescue_retries == set()
    connect.assert_not_awaited()
