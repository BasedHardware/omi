"""Refused admission waits durably without spending provider retries or hiding BLIND."""

from prometheus_client import CollectorRegistry
import pytest

from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline.contracts import WorkResult
from utils.batch_pipeline.metrics import QueueMetrics
from utils.batch_pipeline.scheduler import Scheduler


def setup():
    store = MemoryStore()
    registry = CollectorRegistry()
    queue = Scheduler(store, metrics=QueueMetrics(registry))
    queue.enqueue(item('held'), 0)
    return store, queue, registry


def test_repeated_refusal_backs_off_without_attempt_charge_and_completion_resets():
    store, queue, registry = setup()
    now = 0
    for expected in (30, 60, 120, 240, 300, 300):
        lease = queue.pull(now)[0]
        # An earlier admission allow must neither reset the streak nor remain
        # a misleading latest decision when the dispatch recheck is BLIND.
        store.rows['jobs', 'held']['compute_decision'] = {'outcome': 'allowed', 'at': now}
        assert queue.defer('held', lease.token, now, admission_refused=True)
        job = store.rows['jobs', 'held']
        assert job['available_at'] == now + expected
        assert job['attempt'] == 0 and job['state'] == 'retry'
        assert 'compute_decision' not in job
        assert 'retry_started_at' not in job
        now += expected
        queue.recover(now)
    assert (
        registry.get_sample_value('omi_batch_pipeline_events_total', {'event': 'admission_unevaluated_deferred'}) == 6
    )
    lease = queue.pull(now)[0]
    assert queue.complete(WorkResult('held', 'gs://synthetic/result'), lease.token, now)
    assert 'admission_refusals' not in store.rows['jobs', 'held']


@pytest.mark.parametrize(
    'delay,expected',
    [
        (600, 600),
        (3600, 3600),
        (86400, 86400),
        (100000, 86400),
        (float('nan'), 30),
        (float('inf'), 30),
        (True, 30),
        ('60', 30),
    ],
)
def test_policy_delay_preserved_and_invalid_delay_never_grants_compute(delay, expected):
    store, queue, registry = setup()
    lease = queue.pull(0)[0]
    assert queue.defer('held', lease.token, 0, delay, held_reason='allowance_exhausted', admission_refused=True)
    job = store.rows['jobs', 'held']
    assert job['available_at'] == expected and job['attempt'] == 0
    assert job['compute_decision']['reason'] == 'allowance_exhausted'
    assert registry.get_sample_value('omi_batch_pipeline_events_total', {'event': 'admission_policy_deferred'}) == 1


def test_stale_token_and_refunds_do_not_increment_refusal_or_emit_metric():
    store, queue, registry = setup()
    lease = queue.pull(0)[0]
    assert not queue.defer('held', 'stale', 0, admission_refused=True)
    assert queue.defer('held', lease.token, 0, 1)
    assert 'admission_refusals' not in store.rows['jobs', 'held']
    assert (
        registry.get_sample_value('omi_batch_pipeline_events_total', {'event': 'admission_unevaluated_deferred'})
        is None
    )


def test_waiting_refusal_does_not_block_same_owner_ready_sibling():
    store, queue, _ = setup()
    lease = queue.pull(0)[0]
    queue.enqueue(item('sibling'), 0)
    assert queue.defer('held', lease.token, 0, admission_refused=True)
    assert queue.pull(1)[0].item.segment_id == 'sibling'
    queue.recover(30)
    assert queue.pull(30)[0].item.segment_id == 'held'
