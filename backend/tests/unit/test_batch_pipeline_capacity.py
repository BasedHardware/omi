"""Capacity follows attempt eligibility, not parked queue age or replica count."""

from prometheus_client import CollectorRegistry
import pytest

from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline.metrics import QueueMetrics
from utils.batch_pipeline.scheduler import Scheduler


@pytest.mark.parametrize('reason', ['allowance_exhausted', 'privacy_blocked', None])
def test_old_worker_refusal_cannot_turn_parked_requeue_into_capacity(reason):
    store = MemoryStore()
    scheduler = Scheduler(store)
    scheduler.enqueue(item('held'), 100)
    assert store.rows['jobs', 'held']['compute_decision'] == {'outcome': 'unattempted'}
    lease = scheduler.pull(101)[0]
    assert scheduler.defer('held', lease.token, 102, 30, held_reason=reason, admission_refused=True)
    scheduler.recover(1000)
    job = store.rows['jobs', 'held']
    assert job['state'] == 'ready' and job['merge_pending']
    # Existing workers already implement these transitions. No new boolean
    # eligibility bit can be left true by a mixed-version worker.
    assert (job.get('compute_decision') or {}).get('outcome') not in {'unattempted', 'allowed'}


def test_repeated_enqueue_does_not_reclassify_legacy_debt():
    store = MemoryStore()
    scheduler = Scheduler(store)
    work = item('legacy')
    assert scheduler.enqueue(work, 100)
    store.rows['jobs', 'legacy'].pop('compute_decision')
    assert not scheduler.enqueue(work, 101)
    assert 'compute_decision' not in store.rows['jobs', 'legacy']


def test_shutdown_refund_preserves_first_attempt_capacity_without_allowing_compute():
    store = MemoryStore()
    scheduler = Scheduler(store)
    scheduler.enqueue(item('refund'), 100)
    lease = scheduler.pull(101)[0]
    assert scheduler.defer('refund', lease.token, 102, 1)
    scheduler.recover(1000)
    assert store.rows['jobs', 'refund']['compute_decision'] == {'outcome': 'unattempted'}
    assert not store.rows['jobs', 'refund'].get('compute_admission_token')


class CapacityStore(MemoryStore):
    def __init__(self):
        super().__init__()
        self.counts = [4, 2, 0]
        self.fail_priority = None

    def ready_for_capacity(self, priority, now):
        if priority == self.fail_priority:
            raise RuntimeError('capacity sample unavailable')
        return self.counts[priority]


def test_three_priority_capacity_sample_is_atomic_and_never_missing_as_zero():
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry, worker_release='synthetic', namespace='synthetic')
    store = CapacityStore()
    scope = {'worker_release': 'synthetic', 'namespace': 'synthetic'}
    metrics.refresh(store, 100)
    assert registry.get_sample_value('omi_batch_pipeline_capacity_refreshed_at_seconds', scope) == 100
    for priority, count in zip(('fresh', 'recent', 'deep'), (4, 2, 0)):
        assert (
            registry.get_sample_value('omi_batch_pipeline_admissible_ready_units', {**scope, 'priority': priority})
            == count
        )
    store.counts = [0, 0, 0]
    store.fail_priority = 1
    with pytest.raises(RuntimeError):
        metrics.refresh(store, 200)
    assert registry.get_sample_value('omi_batch_pipeline_capacity_refreshed_at_seconds', scope) == 100
    assert registry.get_sample_value('omi_batch_pipeline_admissible_ready_units', {**scope, 'priority': 'fresh'}) == 4


def test_never_observed_capacity_has_no_fresh_clock():
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    store = CapacityStore()
    store.fail_priority = 0
    with pytest.raises(RuntimeError):
        metrics.refresh(store, 100)
    assert registry.get_sample_value(
        'omi_batch_pipeline_capacity_refreshed_at_seconds', {'worker_release': 'unscoped', 'namespace': 'unscoped'}
    ) in (None, 0)
