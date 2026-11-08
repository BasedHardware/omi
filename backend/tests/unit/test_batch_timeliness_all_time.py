"""Dark all-time stock: exact COUNT aggregations, no document scans or epoch cutoff."""

from types import SimpleNamespace

import pytest
from prometheus_client import CollectorRegistry, generate_latest

from database.batch_pipeline_store import timeliness_sample
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


def test_companion_adds_only_three_unbounded_count_aggregations(monkeypatch):
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
    baseline = timeliness_sample(client(), 'ns', EPOCH, NOW, SLA)
    base_calls, base_streams = list(calls), list(streams)
    calls.clear()
    streams.clear()
    enabled = timeliness_sample(client(), 'ns', EPOCH, NOW, SLA, all_time_counts=True)
    assert enabled.pop('all_time') == LEGS
    assert enabled == baseline
    assert streams == base_streams
    extra = list(calls)
    for call in base_calls:
        extra.remove(call)
    assert len(extra) == 3
    assert all(limit is None for _, limit in extra)
    assert {field for filters, _ in extra for field, _, _ in filters} == {'state', 'recovery_state', 'projection_state'}


@pytest.mark.parametrize('value', [None, 'false', 'true'])
def test_off_has_no_new_series_and_on_exports_fake_store_counts(monkeypatch, value):
    monkeypatch.delenv(FLAG, raising=False)
    if value is not None:
        monkeypatch.setenv(FLAG, value)
    monkeypatch.setattr(metrics_module, 'timeliness_epoch', lambda: EPOCH)
    monkeypatch.setattr(metrics_module, 'lever_enabled', lambda _: False)
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
