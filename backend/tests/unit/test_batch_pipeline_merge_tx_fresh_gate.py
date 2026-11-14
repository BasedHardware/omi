"""Transactional fresh selection; synthetic snapshots only."""

import logging
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import FailedPrecondition

from tests.unit.test_batch_pipeline_merge_fresh_first import (
    CATCH_UP,
    FRESH,
    NOW,
    OWNER,
    admitted,
    complete,
    merge_for,
)
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, MemoryTransaction
from utils.batch_pipeline.merge import HEAD_WAIT_UNAVAILABLE_RETRY_SECONDS
from testing.pipeline_sim.store import CustomerData, SimStore


@pytest.mark.parametrize('state', ['leased', 'dead'])
def test_stale_probe_cannot_pass_a_row_that_settles_before_transaction(state):
    store, queue, leases = admitted({'c': (1000, CATCH_UP), 'f1': (90000, FRESH), 'f2': (90010, FRESH)})
    complete(queue, leases, 'f2')
    store.rows['jobs', 'f1']['state'] = state
    stale = [store.rows['jobs', 'f2'].copy()]
    store.fresh_pending = Mock(return_value=stale)
    # The row omitted by the old probe settles/redrives before the commit snapshot.
    (
        complete(queue, leases, 'f1')
        if state == 'leased'
        else store.rows['jobs', 'f1'].update(
            state='result_ready', ready_at=NOW, result=store.rows['jobs', 'f2']['result']
        )
    )
    assert merge_for(store, wait=60).commit_next('heavy', NOW)['segment_id'] == 'f1'
    store.fresh_pending.assert_not_called()


def large_owner(count, sim=False):
    store = None
    if sim:
        customer = CustomerData()
        customer.add_user('heavy')
        store = SimStore(customer)
    store, queue, leases = admitted(
        {'c': (1000, CATCH_UP), 'f0': (90000, FRESH), f'f{count}': (90000 + count, FRESH)}, store
    )
    complete(queue, leases, f'f{count}')
    template = store.rows['jobs', 'f0']
    store.run(
        lambda tx: [
            tx.put('jobs', f'f{i}', {**template, 'segment_id': f'f{i}', 'capture_at': 90000 + i})
            for i in range(1, count)
        ]
    )
    return store


@pytest.mark.parametrize('sim', [False, True])
@pytest.mark.parametrize('count', [33, 40])
@pytest.mark.parametrize('elapsed', [59, 60])
def test_ready_fresh_beyond_probe_page_obeys_its_own_wait(count, elapsed, sim, caplog):
    store = large_owner(count, sim)
    with caplog.at_level(logging.WARNING):
        entry = merge_for(store, wait=60).commit_next('heavy', NOW + elapsed)
    assert (entry['segment_id'] if entry else None) == (f'f{count}' if elapsed == 60 else None)
    assert 'fresh_probe_full_no_ready' not in caplog.text


@pytest.mark.parametrize('method', ['fresh_first_pending', 'fresh_first_ready_pending'])
def test_missing_tx_index_falls_back_once_and_backs_off(method, monkeypatch, caplog):
    store, queue, leases = admitted({'c': (1000, CATCH_UP), 'f': (90000, FRESH)})
    complete(queue, leases, 'f')
    query = Mock(side_effect=FailedPrecondition('missing index'))
    monkeypatch.setattr(MemoryTransaction, method, query)
    clock = [1000.0]
    monkeypatch.setattr('utils.batch_pipeline.merge.time.monotonic', lambda: clock[0])
    fallback = Mock()
    monkeypatch.setattr('utils.batch_pipeline.merge.record_fallback', fallback)
    merge = merge_for(store)
    with caplog.at_level(logging.WARNING):
        assert merge.commit_next('heavy', NOW)['segment_id'] == 'f'
        assert merge.commit_next('heavy', NOW) is None
    assert query.call_count == 1
    assert caplog.text.count('outcome=fresh_tx_gate_unavailable') == 1
    fallback.assert_called_once()
    assert merge._fresh_tx_retry_at == 1000 + HEAD_WAIT_UNAVAILABLE_RETRY_SECONDS
    clock[0] += HEAD_WAIT_UNAVAILABLE_RETRY_SECONDS
    merge.commit_next('heavy', NOW)
    assert query.call_count == 2


def test_off_restores_the_probe_page_and_its_log(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_TX_FRESH_GATE_ENABLED', 'false')
    store = large_owner(33)
    monkeypatch.setattr(MemoryTransaction, 'fresh_first_pending', Mock(side_effect=AssertionError('gate off')))
    with caplog.at_level(logging.WARNING):
        assert merge_for(store, wait=0).commit_next('heavy', NOW + 60) is None
    assert caplog.text.count('outcome=fresh_probe_full_no_ready') == 1


def test_memory_transaction_finds_first_and_ready_past_terminal_rows():
    store = MemoryStore()
    for i in range(41):
        store.rows['jobs', str(i)] = dict(
            segment_id=str(i),
            owner_key=OWNER,
            merge_pending=True,
            fresh_capture=True,
            capture_at=i,
            state='result_ready' if i == 40 else 'leased',
        )
    for state in ['leased', 'dead', 'quarantined', 'committed']:
        store.rows['jobs', '0']['state'] = state
        first, ready = store.run(lambda tx: (tx.fresh_first_pending(OWNER), tx.fresh_first_ready_pending(OWNER)))
        assert first['segment_id'] == '0' and ready['segment_id'] == '40'
