"""Dedicated pump selection, bounded capacity, failure containment and loop handoff."""

import asyncio
import importlib
import logging
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from prometheus_client import CollectorRegistry

from config import batch_pipeline as config
from config.policy import resolve_stage_policy
from utils.batch_pipeline.metrics import QueueMetrics
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline import projection_drain, serving


async def isolated_pump(pump, holds):
    # These tests control only projection ticks. Coalescing's independent loop
    # has a separate real-gather supervision test in test_batch_upload_coalescing.
    holds.close()
    return await pump


@pytest.mark.parametrize('mode', ['shadow', 'serve'])
@pytest.mark.parametrize(
    'raw,enabled',
    [
        (None, True),
        ('off', False),
        (' OFF ', False),
        ('false', True),
        ('0', True),
        ('', True),
        ('bad', True),
        ('on', True),
    ],
)
def test_serving_sweep_only_off_disables(monkeypatch, mode, raw, enabled):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', mode)
    name = 'BATCH_PIPELINE_SERVING_PROJECTION_SWEEP'
    if raw is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, raw)
    assert config.serving_projection_sweep_enabled() is enabled


@pytest.mark.parametrize('mode', ['shadow', 'serve'])
@pytest.mark.parametrize(
    'raw,enabled',
    [
        (None, False),
        ('true', True),
        (' TRUE ', True),
        ('off', False),
        ('false', False),
        ('0', False),
        ('', False),
        ('bad', False),
        ('1', False),
    ],
)
def test_projection_pump_policy_opt_in(monkeypatch, mode, raw, enabled):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', mode)
    if raw is None:
        monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_PUMP_ENABLED', raising=False)
    else:
        monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_PUMP_ENABLED', raw)
    assert config.projection_pump_enabled() is enabled


@pytest.mark.parametrize('raw,default', [(None, True), ('off', False)])
def test_serving_sweep_gate_preserves_other_reconcile_work(monkeypatch, raw, default):
    if raw is None:
        monkeypatch.delenv('BATCH_PIPELINE_SERVING_PROJECTION_SWEEP', raising=False)
    else:
        monkeypatch.setenv('BATCH_PIPELINE_SERVING_PROJECTION_SWEEP', raw)
    service = serving.Serving(MemoryStore(), projector=Mock(), metrics=Mock())
    service._maintain = Mock()
    service._reconcile_owner = Mock(return_value=['followup'])
    service.merge.held_owners.add('held')
    service.drain_owner = Mock()
    monkeypatch.setattr(serving, 'owner_chain_projection_enabled', lambda: True)
    assert service.reconcile(periodic=True, owner_id='wake', recovered='unit') == ['followup']
    assert service.projector.sweep.call_count == int(default)
    service._maintain.assert_called_once_with(recover_quarantine=False)
    service._reconcile_owner.assert_called_once_with('wake', 'unit')
    service.drain_owner.assert_called_once_with('held')
    service.metrics.refresh.assert_called_once()


@pytest.mark.parametrize(
    'name,reader,default,minimum,maximum',
    [
        ('BATCH_PIPELINE_PUMP_SWEEP_PAGES', config.projection_pump_sweep_pages, 1, 1, 4),
        ('BATCH_PIPELINE_PUMP_TICK_SECONDS', config.projection_pump_tick_seconds, 20, 2, 60),
        ('BATCH_PIPELINE_MAX_OWNER_DRAINS', config.max_owner_drains, 8, 1, 16),
    ],
)
@pytest.mark.parametrize('raw', [None, '', 'bad', '2.5', '-10', '0', '1', '3', '999'])
def test_pump_numeric_env_bounds(monkeypatch, name, reader, default, minimum, maximum, raw):
    if raw is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, raw)
    expected = default if raw in (None, '', 'bad', '2.5') else max(minimum, min(int(raw), maximum))
    assert reader() == expected


@pytest.mark.parametrize('raw,expected', [(None, 8), ('bad', 8), ('', 8), ('0', 1), ('999', 16), ('16', 16)])
def test_owner_drain_module_capacity_from_env(monkeypatch, raw, expected):
    try:
        with monkeypatch.context() as patch:
            if raw is None:
                patch.delenv('BATCH_PIPELINE_MAX_OWNER_DRAINS', raising=False)
            else:
                patch.setenv('BATCH_PIPELINE_MAX_OWNER_DRAINS', raw)
            importlib.reload(projection_drain)
            assert projection_drain.MAX_OWNER_DRAINS == expected
    finally:
        importlib.reload(projection_drain)


@pytest.mark.asyncio
@pytest.mark.parametrize('serving_enabled', ['false', 'true'])
@pytest.mark.parametrize(
    'pages,tick,expected_pages,expected_tick',
    [(None, None, 1, 20), ('3', '4', 3, 4), ('999', '999', 4, 60), ('0', '0', 1, 2), ('bad', 'bad', 1, 20)],
)
async def test_pump_only_sweeps_and_hands_drains_to_loop(
    monkeypatch, caplog, serving_enabled, pages, tick, expected_pages, expected_tick
):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_PUMP_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_SERVING_ENABLED', serving_enabled)
    # Pump discovery is independent of the serving-instance sweep kill switch.
    monkeypatch.setenv('BATCH_PIPELINE_SERVING_PROJECTION_SWEEP', 'off')
    for name, raw in [('BATCH_PIPELINE_PUMP_SWEEP_PAGES', pages), ('BATCH_PIPELINE_PUMP_TICK_SECONDS', tick)]:
        if raw is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, raw)
    loop_thread = threading.get_ident()
    projector = SimpleNamespace(
        handoff=threading.Lock(),
        drain_requests={},
        owes_drains=False,
        has_async_followups=False,
        owes_followups=False,
        start_followups=AsyncMock(),
    )
    sweep_calls = []

    def sweep():
        assert threading.get_ident() != loop_thread
        sweep_calls.append(1)
        projector.drain_requests['owner'] = None
        projector.owes_drains = True

    def start_drains():
        assert threading.get_ident() == loop_thread
        assert len(sweep_calls) == expected_pages
        projector.drain_requests.clear()
        projector.owes_drains = False

    projector.sweep = Mock(side_effect=sweep)
    projector.start_drains = Mock(side_effect=start_drains)
    service = SimpleNamespace(
        projector=projector, reconcile=Mock(), reconcile_async=Mock(), _maintain=Mock(), dispatch_recovery=Mock()
    )
    monkeypatch.setattr(serving, 'current_stage', lambda: 'dev')
    factory = Mock(return_value=service)
    monkeypatch.setattr(serving, 'serving_for_stage', factory)
    record_drain = Mock()
    monkeypatch.setattr(serving, 'drain_recordings', record_drain)
    timeouts = []

    async def wait_for(awaitable, *, timeout):
        timeouts.append(timeout)
        runtime[0].set()
        return await awaitable

    monkeypatch.setattr(
        serving,
        'asyncio',
        SimpleNamespace(
            Event=asyncio.Event, wait_for=wait_for, TimeoutError=asyncio.TimeoutError, gather=isolated_pump
        ),
    )
    caplog.set_level(logging.INFO, logger=serving.__name__)
    runtime = serving.start_serving_from_env()
    await asyncio.wait_for(runtime[1], timeout=5)
    assert timeouts == [expected_tick]
    factory.assert_called_once_with('dev')
    assert projector.sweep.call_count == expected_pages
    projector.start_drains.assert_called_once()
    projector.start_followups.assert_not_awaited()
    for forbidden in (
        service.reconcile,
        service.reconcile_async,
        service._maintain,
        service.dispatch_recovery,
        record_drain,
    ):
        forbidden.assert_not_called()
    assert f'outcome=tick sweeps={expected_pages} owners_requested=1 elapsed_seconds=' in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['build', 'projector', 'sweep', 'followups', 'index', 'drains'])
@pytest.mark.parametrize('prior_success', [False, True])
async def test_pump_logs_failure_and_runs_next_tick(monkeypatch, caplog, failure, prior_success):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_PUMP_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PUMP_SWEEP_PAGES', '1')
    projector = SimpleNamespace(
        handoff=threading.Lock(),
        drain_requests={},
        owes_drains=True,
        sweep=Mock(),
        start_drains=Mock(),
        has_async_followups=False,
        owes_followups=failure == 'followups',
        owes_index=failure == 'index',
        schedule_index_flush=Mock(),
        start_followups=AsyncMock(),
    )
    service = SimpleNamespace(projector=projector)
    factory = Mock(return_value=service)
    target = {
        'build': factory,
        'projector': factory,
        'sweep': projector.sweep,
        'followups': projector.start_followups,
        'index': projector.schedule_index_flush,
        'drains': projector.start_drains,
    }[failure]
    success = service if target is factory else None
    failed = SimpleNamespace(projector=None) if failure == 'projector' else RuntimeError('synthetic')
    target.side_effect = ([success] if prior_success else []) + [failed, success]
    monkeypatch.setattr(serving, 'serving_for_stage', factory)
    monkeypatch.setattr(serving, 'current_stage', lambda: 'dev')
    ticks = []
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    monkeypatch.setattr(serving, '_metrics', lambda: metrics)
    tick_metric = 'omi_batch_projection_pump_last_tick_seconds'
    success_metric = 'omi_batch_projection_pump_last_success_seconds'
    assert registry.get_sample_value(tick_metric) == registry.get_sample_value(success_metric) == 0
    clock = iter([100.0, 200.0, 300.0] if prior_success else [200.0, 300.0])
    now = [0.0]

    def wall_clock():
        return now[0]

    # Both gauges see the same wall-clock time within a tick. No real sleeping.
    now[0] = next(clock)
    monkeypatch.setattr(serving, 'time', SimpleNamespace(time=wall_clock, monotonic=time.monotonic))

    async def wait_for(awaitable, *, timeout):
        ticks.append(timeout)
        assert registry.get_sample_value(tick_metric) == now[0]
        expected_success = 300.0 if now[0] == 300.0 else (100.0 if prior_success else 0.0)
        assert registry.get_sample_value(success_metric) == expected_success
        if now[0] == 300.0:
            runtime[0].set()
            return await awaitable
        now[0] = next(clock)
        awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(
        serving,
        'asyncio',
        SimpleNamespace(
            Event=asyncio.Event, wait_for=wait_for, TimeoutError=asyncio.TimeoutError, gather=isolated_pump
        ),
    )
    caplog.set_level(logging.INFO, logger=serving.__name__)
    runtime = serving.start_serving_from_env()
    await asyncio.wait_for(runtime[1], timeout=5)
    assert len(ticks) == 2 + int(prior_success)
    assert factory.call_count == len(ticks)
    assert 'event=batch_projection_pump outcome=retry exception_type=RuntimeError' in caplog.text
    assert caplog.text.count('event=batch_projection_pump outcome=tick') == len(ticks)
    assert projector.start_drains.call_count >= 1


@pytest.mark.parametrize('raw', [None, 'false', '', 'bad', '1'])
def test_disabled_pump_does_not_start_without_serving(monkeypatch, raw):
    monkeypatch.delenv('BATCH_PIPELINE_SERVING_ENABLED', raising=False)
    if raw is None:
        monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_PUMP_ENABLED', raising=False)
    else:
        monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_PUMP_ENABLED', raw)
    factory = Mock()
    monkeypatch.setattr(serving, 'serving_for_stage', factory)
    assert serving.start_serving_from_env() is None
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_idle_pump_stops_during_tick_sleep_without_starting_drains(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_PUMP_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PUMP_SWEEP_PAGES', '1')
    swept = asyncio.Event()
    projector = SimpleNamespace(
        sweep=Mock(side_effect=swept.set),
        owes_drains=False,
        start_drains=Mock(),
        has_async_followups=False,
        owes_followups=False,
        start_followups=AsyncMock(),
    )
    monkeypatch.setattr(serving, 'serving_for_stage', lambda stage: SimpleNamespace(projector=projector))
    monkeypatch.setattr(serving, 'current_stage', lambda: 'dev')

    async def run_blocking(executor, fn, *args):
        return fn(*args)

    monkeypatch.setattr(serving, 'run_blocking', run_blocking)
    from utils.batch_pipeline import projection_drain

    monkeypatch.setattr(projection_drain, '_recurring_sweep', None)
    runtime = serving.start_serving_from_env()
    try:
        await asyncio.wait_for(swept.wait(), timeout=5)
        # A live pump marks its recurring sweep, so live-target holds may be passive.
        assert projection_drain.recurring_sweep_active()
    finally:
        await serving.stop_serving(runtime)
    projector.sweep.assert_called_once()
    projector.start_drains.assert_not_called()
    assert runtime[1].done()
    assert not projection_drain.recurring_sweep_active()


@pytest.mark.asyncio
@pytest.mark.parametrize('hint', ['last_page', 'first_page', 'owed'])
async def test_pump_starts_followups_without_serving_sweeps_or_maintenance(monkeypatch, hint):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_PUMP_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_SERVING_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_SERVING_PROJECTION_SWEEP', 'off')
    monkeypatch.setenv('BATCH_PIPELINE_PUMP_SWEEP_PAGES', '2')
    monkeypatch.setenv('BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED', 'true')
    assert resolve_stage_policy('owner', 'projection').async_projection is True
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    monkeypatch.setattr(serving, '_metrics', lambda: metrics)
    assert registry.get_sample_value('omi_batch_projection_pump_last_tick_seconds') == 0
    assert registry.get_sample_value('omi_batch_projection_pump_last_success_seconds') == 0
    loop_thread = threading.get_ident()
    calls = []
    projector = SimpleNamespace(has_async_followups=False, owes_followups=False, owes_drains=False, owes_index=False)
    pages = []

    def sweep():
        assert threading.get_ident() != loop_thread
        calls.append('sweep')
        pages.append(1)
        # The per-page hint is reset just as Projector.sweep resets it.
        projector.has_async_followups = (hint == 'first_page' and len(pages) == 1) or (
            hint == 'last_page' and len(pages) == 2
        )
        projector.owes_followups = hint == 'owed'
        projector.owes_index = True

    async def start_followups(priority):
        assert threading.get_ident() == loop_thread
        assert priority == ()
        assert calls[-1] == 'sweep'
        calls.append('followups')

    def schedule_index_flush():
        assert threading.get_ident() == loop_thread
        calls.append('index')
        projector.owes_index = False

    projector.sweep = Mock(side_effect=sweep)
    projector.schedule_index_flush = Mock(side_effect=schedule_index_flush)
    projector.start_followups = AsyncMock(side_effect=start_followups)
    projector.start_drains = Mock()
    service = SimpleNamespace(
        projector=projector, reconcile=Mock(), reconcile_async=Mock(), _maintain=Mock(), dispatch_recovery=Mock()
    )
    monkeypatch.setattr(serving, 'serving_for_stage', lambda stage: service)
    monkeypatch.setattr(serving, 'current_stage', lambda: 'dev')

    async def wait_for(awaitable, *, timeout):
        runtime[0].set()
        return await awaitable

    monkeypatch.setattr(
        serving,
        'asyncio',
        SimpleNamespace(
            Event=asyncio.Event, wait_for=wait_for, TimeoutError=asyncio.TimeoutError, gather=isolated_pump
        ),
    )
    runtime = serving.start_serving_from_env()
    await asyncio.wait_for(runtime[1], timeout=5)
    assert projector.start_followups.await_count == (2 if hint == 'owed' else 1)
    assert all(call.args == ((),) for call in projector.start_followups.await_args_list)
    assert projector.schedule_index_flush.call_count == 2
    expected = {
        'first_page': ['sweep', 'followups', 'index', 'sweep', 'index'],
        'last_page': ['sweep', 'index', 'sweep', 'followups', 'index'],
        'owed': ['sweep', 'followups', 'index', 'sweep', 'followups', 'index'],
    }
    assert calls == expected[hint]
    assert registry.get_sample_value('omi_batch_projection_pump_last_tick_seconds') > 0
    assert registry.get_sample_value('omi_batch_projection_pump_last_success_seconds') > 0
    projector.start_drains.assert_not_called()
    for forbidden in (service.reconcile, service.reconcile_async, service._maintain, service.dispatch_recovery):
        forbidden.assert_not_called()
