"""Fresh delivery guard runs production queries and collector without customer data."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from prometheus_client import CollectorRegistry

from database.batch_pipeline_fresh_guard import fresh_committed_counts
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline import fresh_guard as module
from utils.batch_pipeline.serving import Serving


class CountClient:
    def __init__(self, rows=(), fail_at=None):
        self.rows = rows
        self.calls = []
        self.fail_at = fail_at

    def collection(self, name):
        assert name == 'batch_pipeline_dev_results'
        return CountQuery(self, ())


class CountQuery:
    def __init__(self, client, filters):
        self.client, self.filters = client, filters

    def where(self, key, op, value):
        return CountQuery(self.client, self.filters + ((key, op, value),))

    def count(self):
        return self

    def get(self, *, timeout, retry):
        assert timeout == 10 and retry is None
        self.client.calls.append(self.filters)
        if len(self.client.calls) == self.client.fail_at:
            raise RuntimeError('synthetic query failure')

        def matches(row):
            for key, op, value in self.filters:
                if key not in row:
                    return False
                actual = row[key]
                if op == '==' and actual != value:
                    return False
                if op == '>=' and actual < value:
                    return False
                if op == '<=' and actual > value:
                    return False
            return True

        return [[SimpleNamespace(value=sum(matches(row) for row in self.client.rows))]]


@pytest.fixture
def guard(monkeypatch):
    clock = [2000.0]
    monkeypatch.delenv('BATCH_PIPELINE_FRESH_GUARD_ENABLED', raising=False)
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(module.time, 'time', lambda: clock[0])
    registry = CollectorRegistry()
    return module.FreshGuard(registry), registry, clock


def samples(registry):
    return {s.name.removeprefix(module.PREFIX): s.value for m in registry.collect() for s in m.samples}


def store(client):
    return SimpleNamespace(client=client, namespace='batch_pipeline_dev')


def test_counts_use_exact_window_and_pending_state():
    rows = [
        {'fresh_capture': True, 'committed_at': at, 'projection_state': state}
        for at, state in [
            (800, 'pending'),
            (1400, 'projected'),
            (1000, 'quarantine_held'),
            (799, 'pending'),
            (1401, 'pending'),
        ]
    ]
    rows += [
        {'fresh_capture': False, 'committed_at': 1000, 'projection_state': 'pending'},
        {'committed_at': 1000, 'projection_state': 'pending'},
    ]
    client = CountClient(rows)
    assert fresh_committed_counts(client, 'batch_pipeline_dev', 2000) == (3, 1)
    assert client.calls == [
        (('fresh_capture', '==', True), ('committed_at', '>=', 800), ('committed_at', '<=', 1400)),
        (
            ('fresh_capture', '==', True),
            ('committed_at', '>=', 800),
            ('committed_at', '<=', 1400),
            ('projection_state', '==', 'pending'),
        ),
    ]


def test_empty_window_has_counts_but_no_ratio(guard):
    sampler, registry, _ = guard
    sampler.refresh(store(CountClient()))
    assert samples(registry) == {
        'committed_window_total': 0,
        'unprojected_window_total': 0,
        'guard_sample_age_seconds': 0,
    }


@pytest.mark.parametrize('fail_at', [1, 2])
def test_failure_removes_previous_ratio_and_counts_but_age_continues(guard, fail_at):
    sampler, registry, clock = guard
    client = CountClient([{'fresh_capture': True, 'committed_at': 1000, 'projection_state': 'pending'}])
    sampler.refresh(store(client))
    assert samples(registry)['unprojected_ratio'] == 1
    clock[0] += 60
    sampler.refresh(store(CountClient(fail_at=fail_at)))
    assert samples(registry) == {'guard_sample_age_seconds': 60}


def test_first_query_failure_exposes_no_ratio(guard):
    sampler, registry, _ = guard
    sampler.refresh(store(CountClient(fail_at=1)))
    assert samples(registry) == {}


def test_cadence_and_scrapes_issue_no_extra_queries_and_expire_stale_ratio(guard):
    sampler, registry, clock = guard
    client = CountClient([{'fresh_capture': True, 'committed_at': 1000, 'projection_state': 'pending'}])
    sampler.refresh(store(client))
    clock[0] += 59
    sampler.refresh(store(client))
    assert samples(registry)['guard_sample_age_seconds'] == 59
    assert len(client.calls) == 2
    clock[0] += 1
    sampler.refresh(store(client))
    assert len(client.calls) == 4
    clock[0] += 120
    assert samples(registry) == {'guard_sample_age_seconds': 120}


def test_off_removes_all_gauges_and_stops_queries(guard, monkeypatch):
    sampler, registry, clock = guard
    client = CountClient()
    sampler.refresh(store(client))
    monkeypatch.setenv('BATCH_PIPELINE_FRESH_GUARD_ENABLED', 'off')
    assert samples(registry) == {}
    clock[0] += 60
    sampler.refresh(store(client))
    assert len(client.calls) == 2
    assert samples(registry) == {}


@pytest.mark.parametrize('periodic', [False, True])
def test_only_maintenance_leader_samples_even_for_explicit_reconcile(guard, periodic):
    sampler, registry, clock = guard
    client = CountClient()
    memory = MemoryStore()
    memory.client, memory.namespace = client, 'batch_pipeline_dev'
    leader = Mock()
    leader.acquire.return_value = False
    metrics = SimpleNamespace(fresh_guard=sampler, delivered_share=Mock(), refresh=Mock())
    service = Serving(memory, leader=leader, metrics=metrics)
    service.reconcile(periodic=periodic)
    assert client.calls == [] and samples(registry) == {}
    leader.acquire.return_value = True
    service.reconcile(periodic=periodic)
    assert len(client.calls) == 2
    clock[0] += 60
    leader.acquire.return_value = False
    service.reconcile(periodic=periodic)
    assert len(client.calls) == 2 and samples(registry) == {}


def test_scrape_does_not_wait_for_count_rpc_and_overlapping_refresh_is_coalesced(guard, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    sampler, registry, _ = guard
    entered, release = threading.Event(), threading.Event()

    def slow_count(*args):
        entered.set()
        assert release.wait(5)
        return 4, 1

    count = Mock(side_effect=slow_count)
    monkeypatch.setattr(module, 'fresh_committed_counts', count)
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(sampler.refresh, store(CountClient()))
        try:
            assert entered.wait(2)
            assert pool.submit(samples, registry).result(timeout=1) == {}
            pool.submit(sampler.refresh, store(CountClient())).result(timeout=1)
            assert count.call_count == 1
        finally:
            release.set()
        future.result(timeout=2)
    assert samples(registry)['unprojected_ratio'] == 0.25


@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve'])
@pytest.mark.parametrize('value', ['off', 'false', '0', 'no', ' OFF '])
def test_registered_kill_switch_stops_queries_in_every_parser_mode(guard, monkeypatch, mode, value):
    sampler, registry, _ = guard
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', mode)
    monkeypatch.setenv('BATCH_PIPELINE_FRESH_GUARD_ENABLED', value)
    client = CountClient()
    sampler.refresh(store(client))
    assert client.calls == []
    assert samples(registry) == {}


@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve'])
@pytest.mark.parametrize('value', [None, '', 'true', 'unexpected'])
def test_registered_kill_switch_defaults_on_in_every_parser_mode(monkeypatch, mode, value):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', mode)
    if value is None:
        monkeypatch.delenv('BATCH_PIPELINE_FRESH_GUARD_ENABLED', raising=False)
    else:
        monkeypatch.setenv('BATCH_PIPELINE_FRESH_GUARD_ENABLED', value)
    assert module.enabled()
