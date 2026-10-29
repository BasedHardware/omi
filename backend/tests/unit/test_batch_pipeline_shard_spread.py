"""Pull ownership policy; real transaction contention lives in the emulator suite."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config.batch_pipeline import scheduler_control_key, shard_spread_enabled
from database import batch_pipeline_store as store_module
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline.contracts import Priority
from utils.batch_pipeline.scheduler import Scheduler, owner_key


def test_switch_defaults_on_and_reads_changes_at_call_boundary(monkeypatch):
    monkeypatch.delenv('BATCH_SHARD_SPREAD_ENABLED', raising=False)
    assert shard_spread_enabled()
    monkeypatch.setenv('BATCH_SHARD_SPREAD_ENABLED', ' FALSE ')
    assert not shard_spread_enabled()


def test_busy_claim_does_not_write_queue_or_control_and_does_not_bypass_fresh():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('fresh', priority=Priority.FRESH), 0)
    queue.enqueue(item('deep'), 0)
    shard = scheduler_control_key(owner_key('heavy'))
    store.rows['pull_claims', shard] = {'token': 'another-worker', 'expires_at': 100}
    before = deepcopy(store.rows)
    assert queue.pull(1) == []
    assert store.rows == before


def test_same_shard_can_issue_parallel_compute_leases_after_atomic_release():
    store = MemoryStore()
    first, second = Scheduler(store), Scheduler(store)
    first.enqueue(item('a'), 0)
    first.enqueue(item('b'), 0)
    a, b = first.pull(1)[0], second.pull(1)[0]
    assert a.item.segment_id != b.item.segment_id and a.token != b.token
    shard = scheduler_control_key(owner_key('heavy'))
    assert store.rows['pull_claims', shard] == {'token': '', 'expires_at': 0}


def test_failed_pull_keeps_only_expiring_claim_and_never_loses_job(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    shard = scheduler_control_key(owner_key('heavy'))
    before = deepcopy(store.rows)
    run = store.run
    calls = 0

    def fail(body):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError('synthetic failure before commit')
        return run(body)

    monkeypatch.setattr(store, 'run', fail)
    with pytest.raises(ValueError, match='synthetic failure'):
        queue.pull(1)
    assert {key: row for key, row in store.rows.items() if key[0] != 'pull_claims'} == before
    assert 31 <= store.rows['pull_claims', shard]['expires_at'] < 32
    monkeypatch.setattr(store, 'run', run)
    assert Scheduler(store).pull(32)[0].item.segment_id == 'a'


def test_static_contention_operation_scope_restores_after_error():
    assert store_module._pull_operation.get() == 'batch_pipeline_store'
    with pytest.raises(ValueError, match='synthetic'):
        with store_module.pull_operation('pull', 'scheduler_03'):
            assert store_module._pull_operation.get() == 'batch_pull shard=scheduler_03'
            raise ValueError('synthetic')
    assert store_module._pull_operation.get() == 'batch_pipeline_store'
    with pytest.raises(ValueError, match='static'):
        with store_module.pull_operation('pull', 'uid-shaped-key'):
            pass


def test_worker_affinity_spreads_ties_but_never_overrides_service():
    query = Mock()
    for method in ('where', 'order_by', 'limit'):
        getattr(query, method).return_value = query
    docs = [SimpleNamespace(id=f'scheduler_{n:02d}', to_dict=lambda: {'p0_service': 0}) for n in range(8)]
    query.stream.side_effect = lambda: iter(docs)
    client = Mock()
    client.collection.return_value = query
    choices = [
        store_module.control_candidate(client, 'batch_pipeline_dev', 0, 'batch', 1, worker_id=f'worker-{n}')
        for n in range(3)
    ]
    assert len(set(choices)) == 3
    excluded = store_module.control_candidate(
        client, 'batch_pipeline_dev', 0, 'batch', 1, worker_id='worker-0', exclude={choices[0]}
    )
    assert excluded != choices[0]
    docs[:] = [SimpleNamespace(id=f'scheduler_{n:02d}', to_dict=lambda: {'p0_service': 30}) for n in range(8)]
    docs.append(SimpleNamespace(id='scheduler_63', to_dict=lambda: {'p0_service': 0}))
    assert (
        store_module.control_candidate(client, 'batch_pipeline_dev', 0, 'batch', 1, worker_id='worker-0')
        == 'scheduler_63'
    )
