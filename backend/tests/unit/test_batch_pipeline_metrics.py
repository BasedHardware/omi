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
    assert (
        registry.get_sample_value(
            'omi_batch_pipeline_oldest_age_seconds',
            {'priority': 'deep', 'worker_release': 'unscoped', 'namespace': 'unscoped'},
        )
        == 100
    )
    lease = queue.pull(101)[0]
    metrics.refresh(store, 102)
    assert (
        registry.get_sample_value(
            'omi_batch_pipeline_ready_age_seconds',
            {'priority': 'deep', 'worker_release': 'unscoped', 'namespace': 'unscoped'},
        )
        == 0
    )
    assert (
        registry.get_sample_value(
            'omi_batch_pipeline_oldest_age_seconds',
            {'priority': 'deep', 'worker_release': 'unscoped', 'namespace': 'unscoped'},
        )
        == 102
    )

    def unavailable(*args, **kwargs):
        raise RuntimeError('store unavailable')

    monkeypatch.setattr(store, 'oldest', unavailable)
    with pytest.raises(RuntimeError):
        metrics.refresh(store, 200)
    assert (
        registry.get_sample_value(
            'omi_batch_pipeline_metrics_refreshed_at_seconds', {'worker_release': 'unscoped', 'namespace': 'unscoped'}
        )
        == 102
    )
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


def test_exported_age_and_freshness_have_the_hpa_release_namespace_scope():
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry, worker_release='synthetic-worker', namespace='synthetic')
    store = MemoryStore()
    Scheduler(store).enqueue(item('scoped'), 0)
    metrics.refresh(store, 100)
    scope = {'worker_release': 'synthetic-worker', 'namespace': 'synthetic'}
    assert registry.get_sample_value('omi_batch_pipeline_ready_age_seconds', {**scope, 'priority': 'deep'}) == 100
    assert registry.get_sample_value('omi_batch_pipeline_metrics_refreshed_at_seconds', scope) == 100


def test_retry_age_survives_requeue_and_clears_only_after_success():
    from utils.batch_pipeline.contracts import WorkResult

    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('retry-head'), 0)
    lease = queue.pull(1)[0]
    queue.fail('retry-head', lease.token, 2)
    queue.recover(7)
    metrics.refresh(store, 1000)
    labels = {'priority': 'deep', 'worker_release': 'unscoped', 'namespace': 'unscoped'}
    assert registry.get_sample_value('omi_batch_pipeline_retry_age_seconds', labels) == 998
    lease = queue.pull(1000)[0]
    queue.complete(WorkResult('retry-head', 'gs://results/retry'), lease.token, 1001)
    metrics.refresh(store, 1002)
    assert registry.get_sample_value('omi_batch_pipeline_retry_age_seconds', labels) == 0
