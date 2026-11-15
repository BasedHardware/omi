"""Bounded serving discovery and supervisor cadence, exercised at runtime seams."""

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from config import batch_pipeline as config
from database.batch_pipeline_store import projection_page
from tests.unit.test_batch_pipeline_followup_desync import ResultQuery
from utils.batch_pipeline import projection, serving


@pytest.mark.parametrize(
    'name,reader,default,minimum,maximum',
    [
        ('BATCH_PIPELINE_SERVING_SWEEP_PAGE_ROWS', config.serving_sweep_page_rows, 100, 50, 200),
        ('BATCH_PIPELINE_SERVING_TICK_SECONDS', config.serving_tick_seconds, 20, 10, 60),
        ('BATCH_PIPELINE_READY_DISCOVERY_TICK_SECONDS', config.ready_discovery_tick_seconds, 10, 1, 60),
        ('BATCH_PIPELINE_READY_DISCOVERY_OWNERS_PER_TICK', config.ready_discovery_owners_per_tick, 20, 1, 100),
    ],
)
@pytest.mark.parametrize(
    'raw', [None, '', 'bad', '2.5', 'nan', 'inf', '-1', '0', '5', '50', '200', '300', '999', '1000']
)
def test_serving_numeric_bounds(monkeypatch, name, reader, default, minimum, maximum, raw):
    monkeypatch.delenv('BATCH_PIPELINE_SERVING_SWEEP_PAGE_ROWS', raising=False)
    if raw is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, raw)
    expected = default if raw in (None, '', 'bad', '2.5', 'nan', 'inf') else max(minimum, min(int(raw), maximum))
    assert reader() == expected


@pytest.mark.parametrize(
    'page,tick,effective', [('100', '20', 20), ('200', '20', 20), ('200', '10', 10), ('200', '5', 10), ('999', '0', 10)]
)
def test_serving_combined_budget_preserves_page_and_warns_once(monkeypatch, caplog, page, tick, effective):
    monkeypatch.setenv('BATCH_PIPELINE_SERVING_SWEEP_PAGE_ROWS', page)
    monkeypatch.setenv('BATCH_PIPELINE_SERVING_TICK_SECONDS', tick)
    monkeypatch.setattr(config, '_serving_budget_warned', False)
    rows = config.serving_sweep_page_rows()
    with caplog.at_level(logging.WARNING, logger=config.__name__):
        assert config.serving_tick_seconds() == config.serving_tick_seconds() == effective
    assert config.serving_sweep_page_rows() == rows
    assert rows / effective <= 20
    warnings = [record for record in caplog.records if 'action=read_budget' in record.message]
    assert len(warnings) == int(int(tick) < rows / 20)
    if warnings:
        assert f'effective_page_rows={rows} effective_tick_seconds={effective}' in warnings[0].message


def test_combined_budget_raises_tick_instead_of_reducing_page(monkeypatch, caplog):
    # Exercise the budget independently of today's tighter individual clamps.
    monkeypatch.setattr(config, 'serving_sweep_page_rows', lambda: 250)
    monkeypatch.setenv('BATCH_PIPELINE_SERVING_TICK_SECONDS', '10')
    monkeypatch.setattr(config, '_serving_budget_warned', False)
    with caplog.at_level(logging.WARNING, logger=config.__name__):
        assert config.serving_tick_seconds() == 12.5
    assert 'effective_page_rows=250 effective_tick_seconds=12.5' in caplog.text


@pytest.mark.parametrize('pending_page', [False, True])
@pytest.mark.parametrize(
    'raw,limit,expected',
    [
        (None, None, 100),
        ('200', None, 200),
        ('999', None, 200),
        ('0', None, 50),
        ('bad', None, 100),
        (None, 200, 100),
        ('200', 25, 25),
        ('200', 999, 200),
        ('200', 0, 1),
    ],
)
def test_sweep_uses_configured_cap_for_assignment_and_finish(monkeypatch, pending_page, raw, limit, expected):
    if raw is None:
        monkeypatch.delenv('BATCH_PIPELINE_SERVING_SWEEP_PAGE_ROWS', raising=False)
    else:
        monkeypatch.setenv('BATCH_PIPELINE_SERVING_SWEEP_PAGE_ROWS', raw)
    monkeypatch.setattr(projection, 'projection_pending_page_enabled', lambda: pending_page)
    monkeypatch.setattr(projection, 'sweep_owner_chain_enabled', lambda: False)
    projector = projection.Projector(Mock(), Mock())
    for discovery in (projector.discovery, projector.assignment_discovery, projector.finish_discovery):
        discovery.next = Mock(return_value=[])
    result = projector.sweep() if limit is None else projector.sweep(limit=limit)
    selected = projector.assignment_discovery if pending_page else projector.discovery
    selected.next.assert_called_once_with(limit=expected)
    if pending_page:
        projector.finish_discovery.next.assert_called_once_with(limit=expected)
    else:
        projector.finish_discovery.next.assert_not_called()
    assert result == {'completed': 0, 'waiting': 0, 'blocked': 0, 'error': 0}


@pytest.mark.parametrize('raw,expected', [(None, 100), ('200', 200), ('300', 200)])
def test_sweep_page_size_reaches_database_query(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv('BATCH_PIPELINE_SERVING_SWEEP_PAGE_ROWS', raising=False)
    else:
        monkeypatch.setenv('BATCH_PIPELINE_SERVING_SWEEP_PAGE_ROWS', raw)
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED', 'off')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED', 'on')
    monkeypatch.setattr(projection, 'projection_pending_page_enabled', lambda: True)
    monkeypatch.setattr(projection, 'sweep_owner_chain_enabled', lambda: False)
    query = ResultQuery({f'r{i:03d}': {'committed_at': i, 'projection_state': 'pending'} for i in range(350)})
    store = Mock()
    store.projection_page.side_effect = lambda **kwargs: projection_page(query, 'synthetic', **kwargs)
    projector = projection.Projector(store, Mock())
    projector.store.read = Mock(side_effect=projection.ProjectionBlocked('synthetic'))
    assert projector.sweep()['blocked'] == expected
    assert query.calls == [(None, expected), (None, expected)]
    # The database ceiling stays bounded even for callers bypassing config.
    projection_page(query, 'synthetic', limit=999)
    assert query.calls[-1] == (None, 200)


@pytest.mark.asyncio
@pytest.mark.parametrize('raw,expected', [(None, 20), ('10', 10), ('5', 10), ('0', 10), ('999', 60), ('bad', 20)])
async def test_supervisor_uses_configured_tick(monkeypatch, raw, expected):
    monkeypatch.setenv('BATCH_PIPELINE_SERVING_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_PUMP_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_DISPATCH_INTERVAL_SECONDS', 'off')
    if raw is None:
        monkeypatch.delenv('BATCH_PIPELINE_SERVING_TICK_SECONDS', raising=False)
    else:
        monkeypatch.setenv('BATCH_PIPELINE_SERVING_TICK_SECONDS', raw)
    service = SimpleNamespace(store=Mock(), reconcile_async=AsyncMock())
    monkeypatch.setattr(serving, 'current_stage', lambda: 'dev')
    monkeypatch.setattr(serving, 'serving_for_stage', lambda stage: service)
    monkeypatch.setattr(serving, 'drain_recordings', AsyncMock(return_value=None))
    ticks = []

    async def wait_for(awaitable, *, timeout):
        if service.reconcile_async.await_count and not ticks:
            ticks.append(timeout)
            runtime[0].set()
        return await awaitable

    monkeypatch.setattr(
        serving,
        'asyncio',
        SimpleNamespace(
            Event=asyncio.Event,
            wait_for=wait_for,
            TimeoutError=asyncio.TimeoutError,
            gather=asyncio.gather,
            sleep=asyncio.sleep,
        ),
    )
    runtime = serving.start_serving_from_env()
    try:
        await asyncio.wait_for(runtime[1], timeout=5)
    finally:
        runtime[0].set()
        await asyncio.gather(runtime[1], return_exceptions=True)
    assert ticks == [expected]
    service.reconcile_async.assert_awaited_once_with(recover_quarantine=True, periodic=True)
