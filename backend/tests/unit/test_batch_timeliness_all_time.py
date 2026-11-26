"""Dark all-time stock: exact COUNT aggregations, no document scans or epoch cutoff."""

import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from prometheus_client import CollectorRegistry, generate_latest

from database.batch_pipeline_store import timeliness_all_time_counts, timeliness_sample
from tests.unit.test_batch_pipeline_timeliness import _Client, _Query, EPOCH, NOW, SLA
from utils.batch_pipeline import metrics as metrics_module
from utils.batch_pipeline.metrics import QueueMetrics

FLAG = 'BATCH_TIMELINESS_ALL_TIME_COUNTS_ENABLED'
METRIC = 'omi_batch_timeliness_all_time_units'
LEGS = {'quarantine_held_rows': 3, 'assignment_held': 2, 'projection': 3}


def client():
    return _Client(
        jobs=[
            {'state': 'committed', 'recovery_state': 'held', 'enqueued_at': EPOCH - 10},
            {'state': 'committed', 'recovery_state': 'held', 'enqueued_at': NOW - 1},
            {'state': 'committed', 'recovery_state': 'recovered', 'enqueued_at': EPOCH - 10},
        ],
        results=[
            *[{'projection_state': 'quarantine_held', 'committed_at': t} for t in (EPOCH - 10, EPOCH + 1, NOW - 1)],
            {'projection_state': 'pending', 'committed_at': EPOCH - 1},
            {'projection_state': 'persisted', 'committed_at': NOW - 1},
            {'projection_state': 'ready', 'committed_at': EPOCH - 1},
        ],
    )


class _Lease:
    """Stands in for LeaderLease: ``held`` decides whether this replica wins the lease."""

    held = True

    def __init__(self, store, name, ttl_seconds):
        self.ttl_seconds = ttl_seconds

    def acquire(self):
        return _Lease.held


def _leader(monkeypatch, *, lever=True, held=True):
    monkeypatch.setattr(metrics_module, 'lever_enabled', lambda name: lever and name == 'batch_timeliness_leader')
    monkeypatch.setattr(metrics_module, 'LeaderLease', _Lease)
    monkeypatch.setattr(_Lease, 'held', held)


def test_all_time_counts_are_three_unbounded_count_aggregations(monkeypatch):
    calls, streams = [], []
    count, stream = _Query.count, _Query.stream

    def counted(query):
        calls.append((query.filters, query._limit))
        return count(query)

    def streamed(query):
        streams.append((query.filters, query.order, query._limit))
        return stream(query)

    monkeypatch.setattr(_Query, 'count', counted)
    monkeypatch.setattr(_Query, 'stream', streamed)
    assert timeliness_all_time_counts(client(), 'ns') == LEGS
    # No epoch cutoff, no document walk: only three COUNT aggregations.
    assert streams == []
    assert len(calls) == 3
    assert all(limit is None for _, limit in calls)
    assert {field for filters, _ in calls for field, _, _ in filters} == {'state', 'recovery_state', 'projection_state'}


@pytest.mark.parametrize('value', [None, 'false', 'true'])
def test_off_has_no_new_series_and_on_exports_fake_store_counts(monkeypatch, value):
    monkeypatch.delenv(FLAG, raising=False)
    if value is not None:
        monkeypatch.setenv(FLAG, value)
    monkeypatch.setattr(metrics_module, 'timeliness_epoch', lambda: EPOCH)
    _leader(monkeypatch)
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    store = SimpleNamespace(client=client(), namespace='ns')
    metrics.refresh_timeliness(store, NOW)
    for leg, units in LEGS.items():
        assert registry.get_sample_value(METRIC, {'leg': leg}) == (units if value == 'true' else None)
    assert (METRIC.encode() in generate_latest(registry)) is (value == 'true')
    assert registry.get_sample_value('omi_batch_timeliness_new_over_sla_units', {'leg': 'quarantine_held_rows'}) == 1
    if value == 'true':
        monkeypatch.setenv(FLAG, 'false')
        assert METRIC.encode() not in generate_latest(registry)
        metrics.refresh_timeliness(store, NOW + 601)
        monkeypatch.setenv(FLAG, 'true')
        # An OFF refresh cannot revive the previous all-time sample on re-enable.
        assert METRIC.encode() not in generate_latest(registry)
        metrics.refresh_timeliness(store, NOW + 1202)
        assert registry.get_sample_value(METRIC, {'leg': 'quarantine_held_rows'}) == 3


def _companion_count(query):
    # The hourly policy-held gauge is independent of this default-off companion family.
    return (
        ('state', '==', 'allowance_held') not in query.filters
        and query._limit is None
        and not any(field in {'enqueued_at', 'committed_at'} for field, _, _ in query.filters)
    )


def _epoch_series(registry):
    return {
        (sample.name, tuple(sorted(sample.labels.items()))): sample.value
        for family in registry.collect()
        for sample in family.samples
        if (
            sample.name.startswith('omi_batch_timeliness_')
            or sample.name in {'omi_batch_held_oldest_age_seconds', 'omi_batch_projection_drain_oldest_age_seconds'}
        )
        and sample.name != METRIC
        and not sample.name.endswith('_created')
    }


@pytest.mark.parametrize('failed_legs', [*(frozenset({leg}) for leg in LEGS), frozenset(LEGS)])
def test_companion_count_failures_refresh_epoch_and_remove_failed_series(monkeypatch, caplog, failed_legs):
    monkeypatch.setattr(metrics_module, 'timeliness_epoch', lambda: EPOCH)
    _leader(monkeypatch)
    store = SimpleNamespace(client=client(), namespace='ns')
    baseline_registry, registry = CollectorRegistry(), CollectorRegistry()
    baseline, metrics = QueueMetrics(baseline_registry), QueueMetrics(registry)
    monkeypatch.setenv(FLAG, 'false')
    baseline.refresh_timeliness(store, NOW)
    monkeypatch.setenv(FLAG, 'true')
    metrics.refresh_timeliness(store, NOW)
    # A previously exported value must disappear if the next observation fails.
    assert all(registry.get_sample_value(METRIC, {'leg': leg}) == units for leg, units in LEGS.items())
    store.client.tables['ns_results'].append(
        {'id': 'new-held', 'projection_state': 'quarantine_held', 'committed_at': EPOCH + 2}
    )
    monkeypatch.setenv(FLAG, 'false')
    baseline.refresh_timeliness(store, NOW + 601)
    monkeypatch.setenv(FLAG, 'true')
    count = _Query.count
    attempted = []

    def counted(query):
        if _companion_count(query):
            fields = {field for field, _, _ in query.filters}
            leg = (
                'assignment_held'
                if 'state' in fields
                else 'quarantine_held_rows' if len(query.filters) == 1 and query.filters[0][1] == '==' else 'projection'
            )
            attempted.append(leg)
            if leg in failed_legs:
                # Raise at aggregation RPC execution, after the builder succeeds.
                return Mock(get=Mock(side_effect=RuntimeError('private payload')))
        return count(query)

    monkeypatch.setattr(_Query, 'count', counted)
    caplog.set_level(logging.WARNING)
    metrics.refresh_timeliness(store, NOW + 601)
    assert _epoch_series(registry) == _epoch_series(baseline_registry)
    assert registry.get_sample_value('omi_batch_timeliness_observed_at_seconds') == NOW + 601
    assert registry.get_sample_value('omi_batch_timeliness_new_over_sla_units', {'leg': 'quarantine_held_rows'}) == 2
    assert registry.get_sample_value('omi_batch_timeliness_samples_total', {'outcome': 'ok'}) == 2
    assert registry.get_sample_value('omi_batch_timeliness_samples_total', {'outcome': 'error'}) is None
    assert attempted == list(LEGS)
    for leg, units in LEGS.items():
        expected = None if leg in failed_legs else units + int(leg == 'quarantine_held_rows')
        assert registry.get_sample_value(METRIC, {'leg': leg}) == expected
    assert sorted(record.getMessage() for record in caplog.records) == sorted(
        f'event=batch_timeliness_all_time_sample outcome=unavailable leg={leg} exception_type=RuntimeError'
        for leg in failed_legs
    )


@pytest.mark.parametrize(
    ('lever', 'held'),
    [(False, True), (True, False)],
    ids=['election-off-no-companion', 'leader-without-lease-no-companion'],
)
def test_companion_counts_need_leader_mode_and_the_lease(monkeypatch, caplog, lever, held):
    monkeypatch.setenv(FLAG, 'true')
    monkeypatch.setattr(metrics_module, 'timeliness_epoch', lambda: EPOCH)
    _leader(monkeypatch, lever=lever, held=held)
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    clear = Mock(wraps=metrics.timeliness_all_time.clear)
    monkeypatch.setattr(metrics.timeliness_all_time, 'clear', clear)
    companion = Mock()
    count = _Query.count

    def counted(query):
        if _companion_count(query):
            companion()
            raise AssertionError('a replica without leader mode and the lease ran a companion count')
        return count(query)

    monkeypatch.setattr(_Query, 'count', counted)
    metrics.refresh_timeliness(SimpleNamespace(client=client(), namespace='ns'), NOW)
    companion.assert_not_called()
    clear.assert_not_called()
    assert METRIC.encode() not in generate_latest(registry)
    observed = registry.get_sample_value('omi_batch_timeliness_observed_at_seconds')
    assert (observed == NOW) if held else (observed != NOW)


def test_companion_counts_run_only_after_epoch_gauges_publish(monkeypatch):
    monkeypatch.setenv(FLAG, 'true')
    monkeypatch.setattr(metrics_module, 'timeliness_epoch', lambda: EPOCH)
    _leader(monkeypatch)
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    seen = []
    count = _Query.count

    def counted(query):
        if _companion_count(query):
            # A slow or failed companion COUNT must find the epoch series already published.
            seen.append(registry.get_sample_value('omi_batch_timeliness_observed_at_seconds'))
        return count(query)

    monkeypatch.setattr(_Query, 'count', counted)
    metrics.refresh_timeliness(SimpleNamespace(client=client(), namespace='ns'), NOW + 601)
    assert seen == [NOW + 601] * 3
    assert registry.get_sample_value(METRIC, {'leg': 'projection'}) == LEGS['projection']


def test_companion_leg_failure_does_not_block_the_next_epoch_refresh(monkeypatch):
    monkeypatch.setenv(FLAG, 'true')
    monkeypatch.setattr(metrics_module, 'timeliness_epoch', lambda: EPOCH)
    _leader(monkeypatch)
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    store = SimpleNamespace(client=client(), namespace='ns')
    count = _Query.count

    def failing(query):
        if _companion_count(query):
            return Mock(get=Mock(side_effect=RuntimeError('private payload')))
        return count(query)

    monkeypatch.setattr(_Query, 'count', failing)
    metrics.refresh_timeliness(store, NOW)
    metrics.refresh_timeliness(store, NOW + 601)
    assert registry.get_sample_value('omi_batch_timeliness_observed_at_seconds') == NOW + 601
    assert registry.get_sample_value('omi_batch_timeliness_samples_total', {'outcome': 'ok'}) == 2
    assert not any(sample.name == METRIC for family in registry.collect() for sample in family.samples)


@pytest.mark.parametrize('value', [None, 'false'])
def test_off_runs_no_companion_counts_or_series_updates(monkeypatch, caplog, value):
    monkeypatch.delenv(FLAG, raising=False)
    if value is not None:
        monkeypatch.setenv(FLAG, value)
    monkeypatch.setattr(metrics_module, 'timeliness_epoch', lambda: EPOCH)
    _leader(monkeypatch)
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    clear = Mock(wraps=metrics.timeliness_all_time.clear)
    monkeypatch.setattr(metrics.timeliness_all_time, 'clear', clear)
    sampler = Mock(wraps=timeliness_sample)
    monkeypatch.setattr(metrics_module, 'timeliness_sample', sampler)
    count = _Query.count
    companion = Mock()

    def counted(query):
        if _companion_count(query):
            companion()
            raise AssertionError('disabled companion count ran')
        return count(query)

    monkeypatch.setattr(_Query, 'count', counted)
    metrics.refresh_timeliness(SimpleNamespace(client=client(), namespace='ns'), NOW)
    companion.assert_not_called()
    clear.assert_not_called()
    assert 'all_time_counts' not in sampler.call_args.kwargs
    assert METRIC.encode() not in generate_latest(registry)
    assert registry.get_sample_value('omi_batch_timeliness_observed_at_seconds') == NOW
    assert not any('event=batch_timeliness_all_time_sample' in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize('enabled', [False, True])
def test_epoch_failure_keeps_legacy_values_and_never_runs_companion_counts(monkeypatch, caplog, enabled):
    monkeypatch.setenv(FLAG, str(enabled).lower())
    monkeypatch.setattr(metrics_module, 'timeliness_epoch', lambda: EPOCH)
    _leader(monkeypatch)
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    store = SimpleNamespace(client=client(), namespace='ns')
    metrics.refresh_timeliness(store, NOW)
    before = _epoch_series(registry)
    count = _Query.count
    companion = Mock()

    def counted(query):
        if _companion_count(query):
            companion()
        if ('enqueued_at', '<', EPOCH) in query.filters:
            # Fail a legacy backlog COUNT, after the epoch over-SLA counts succeeded.
            raise RuntimeError('legacy aggregation failed')
        return count(query)

    monkeypatch.setattr(_Query, 'count', counted)
    caplog.set_level(logging.WARNING)
    metrics.refresh_timeliness(store, NOW + 601)
    after = _epoch_series(registry)
    assert after.pop(('omi_batch_timeliness_samples_total', (('outcome', 'error'),))) == 1
    assert after == before
    assert registry.get_sample_value('omi_batch_timeliness_observed_at_seconds') == NOW
    companion.assert_not_called()
    assert [record.getMessage() for record in caplog.records] == [
        'event=batch_timeliness_sample outcome=unavailable exception_type=RuntimeError'
    ]
