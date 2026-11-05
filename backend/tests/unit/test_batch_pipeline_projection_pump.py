"""Dedicated pump selection, bounded capacity, failure containment and loop handoff."""

import asyncio
import importlib
import logging
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config import batch_pipeline as config
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline import projection_drain, serving


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
    'name,reader,default,maximum',
    [
        ('BATCH_PIPELINE_PUMP_SWEEP_PAGES', config.projection_pump_sweep_pages, 1, 10),
        ('BATCH_PIPELINE_PUMP_TICK_SECONDS', config.projection_pump_tick_seconds, 20, 60),
        ('BATCH_PIPELINE_MAX_OWNER_DRAINS', config.max_owner_drains, 8, 32),
    ],
)
@pytest.mark.parametrize('raw', [None, '', 'bad', '2.5', '-10', '0', '3', '999'])
def test_pump_numeric_env_bounds(monkeypatch, name, reader, default, maximum, raw):
    if raw is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, raw)
    expected = default if raw in (None, '', 'bad', '2.5') else max(1, min(int(raw), maximum))
    assert reader() == expected


@pytest.mark.parametrize('raw,expected', [(None, 8), ('bad', 8), ('', 8), ('0', 1), ('999', 32), ('16', 16)])
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
    [(None, None, 1, 20), ('3', '4', 3, 4), ('999', '999', 10, 60), ('0', '0', 1, 1), ('bad', 'bad', 1, 20)],
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
    projector = SimpleNamespace(handoff=threading.Lock(), drain_requests={}, owes_drains=False)
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
        serving, 'asyncio', SimpleNamespace(Event=asyncio.Event, wait_for=wait_for, TimeoutError=asyncio.TimeoutError)
    )
    caplog.set_level(logging.INFO, logger=serving.__name__)
    runtime = serving.start_serving_from_env()
    await asyncio.wait_for(runtime[1], timeout=5)
    assert timeouts == [expected_tick]
    factory.assert_called_once_with('dev')
    assert projector.sweep.call_count == expected_pages
    projector.start_drains.assert_called_once()
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
@pytest.mark.parametrize('failure', ['build', 'sweep', 'drains'])
async def test_pump_logs_failure_and_runs_next_tick(monkeypatch, caplog, failure):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_PUMP_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PUMP_SWEEP_PAGES', '1')
    projector = SimpleNamespace(
        handoff=threading.Lock(), drain_requests={}, owes_drains=True, sweep=Mock(), start_drains=Mock()
    )
    service = SimpleNamespace(projector=projector)
    factory = Mock(return_value=service)
    target = {'build': factory, 'sweep': projector.sweep, 'drains': projector.start_drains}[failure]
    target.side_effect = [RuntimeError('synthetic'), None if failure != 'build' else service]
    monkeypatch.setattr(serving, 'serving_for_stage', factory)
    monkeypatch.setattr(serving, 'current_stage', lambda: 'dev')
    ticks = []

    async def wait_for(awaitable, *, timeout):
        ticks.append(timeout)
        if len(ticks) == 2:
            runtime[0].set()
            return await awaitable
        awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(
        serving, 'asyncio', SimpleNamespace(Event=asyncio.Event, wait_for=wait_for, TimeoutError=asyncio.TimeoutError)
    )
    caplog.set_level(logging.INFO, logger=serving.__name__)
    runtime = serving.start_serving_from_env()
    await asyncio.wait_for(runtime[1], timeout=5)
    assert len(ticks) == 2
    assert factory.call_count == 2
    assert 'event=batch_projection_pump outcome=retry exception_type=RuntimeError' in caplog.text
    assert caplog.text.count('event=batch_projection_pump outcome=tick') == 2
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
    projector = SimpleNamespace(sweep=Mock(side_effect=swept.set), owes_drains=False, start_drains=Mock())
    monkeypatch.setattr(serving, 'serving_for_stage', lambda stage: SimpleNamespace(projector=projector))
    monkeypatch.setattr(serving, 'current_stage', lambda: 'dev')

    async def run_blocking(executor, fn, *args):
        return fn(*args)

    monkeypatch.setattr(serving, 'run_blocking', run_blocking)
    runtime = serving.start_serving_from_env()
    try:
        await asyncio.wait_for(swept.wait(), timeout=5)
    finally:
        await serving.stop_serving(runtime)
    projector.sweep.assert_called_once()
    projector.start_drains.assert_not_called()
    assert runtime[1].done()
