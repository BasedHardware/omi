from prometheus_client import CollectorRegistry
import pytest

from utils.batch_pipeline.metrics import QueueMetrics
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline.scheduler import Scheduler


def test_queue_age_and_stale_refresh_retains_previous_sample(monkeypatch):
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    metrics.refresh(store, 100)
    assert registry.get_sample_value('omi_batch_pipeline_oldest_age_seconds', {'priority': 'deep'}) == 100
    lease = queue.pull(101)[0]
    metrics.refresh(store, 102)
    assert registry.get_sample_value('omi_batch_pipeline_ready_age_seconds', {'priority': 'deep'}) == 0
    assert registry.get_sample_value('omi_batch_pipeline_oldest_age_seconds', {'priority': 'deep'}) == 102

    def unavailable(*args, **kwargs):
        raise RuntimeError('store unavailable')

    monkeypatch.setattr(store, 'oldest', unavailable)
    with pytest.raises(RuntimeError):
        metrics.refresh(store, 200)
    assert registry.get_sample_value('omi_batch_pipeline_metrics_refreshed_at_seconds') == 102
    assert lease.item.segment_id == 'a'
    metrics.record('leased', wait_seconds=101)
    metrics.record('completed')
    assert registry.get_sample_value('omi_batch_pipeline_events_total', {'event': 'completed'}) == 1
    with pytest.raises(ValueError):
        metrics.record('user-id')


def test_scheduler_records_new_transitions_without_duplicate_completion_count():
    from utils.batch_pipeline.contracts import WorkResult
    from utils.batch_pipeline.merge import OrderedMerge

    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    store = MemoryStore()
    queue = Scheduler(store, metrics=metrics)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(10)[0]
    result = WorkResult('a', 'gs://results/a')
    assert queue.complete(result, lease.token, 11)
    assert queue.complete(result, lease.token, 12)
    assert registry.get_sample_value('omi_batch_pipeline_events_total', {'event': 'completed'}) == 1
    assert registry.get_sample_value('omi_batch_pipeline_owner_wait_seconds_sum') == 10
    merge = OrderedMerge(store, metrics=metrics)
    merge.commit_next('heavy', 13)
    merge.commit_next('heavy', 14)
    assert registry.get_sample_value('omi_batch_pipeline_events_total', {'event': 'committed'}) == 1
