"""SCA-2015: an unready head must not hide fresh work behind held provider stock."""

import pytest
from google.api_core.exceptions import FailedPrecondition

from tests.unit.test_batch_pipeline_merge_head_wait import admitted, complete
from utils.batch_pipeline.merge import OrderedMerge


def stalled_owner(head_class):
    store, queue, leases = admitted({'head': 1, 'held': 2, 'fresh': 3})
    head = store.rows['jobs', 'head']
    head['state'] = 'retry'
    if head_class is None:
        head.pop('fresh_capture', None)
    else:
        head['fresh_capture'] = head_class
    complete(queue, leases, 'held', 5)
    store.rows['jobs', 'held'].update(fresh_capture=False, stt_route={'stt_route': 'provider'})
    complete(queue, leases, 'fresh', 10)
    store.rows['jobs', 'fresh']['fresh_capture'] = True
    return store


@pytest.fixture(autouse=True)
def switches(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_PROVIDER_BACKLOG_RELEASE_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_PROVIDER_MERGE_MEMBERSHIP_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_TX_FRESH_GATE_ENABLED', 'true')


@pytest.mark.parametrize('head_class', [True, None, False])
def test_stalled_head_reaches_ready_fresh_past_held_provider_stock(head_class):
    store = stalled_owner(head_class)

    merge = OrderedMerge(store, head_wait_seconds=60, catch_up_depth=1)
    entry = merge.commit_next('heavy', 86400)
    assert entry is not None, 'fresh work is stranded behind the held provider result'
    assert entry['segment_id'] == 'fresh'
    assert store.rows['jobs', 'held']['state'] == 'result_ready'


@pytest.mark.parametrize('wait,now', [(0, 86400), (60, 69)])
def test_stalled_head_preserves_disabled_or_unexpired_head_wait(wait, now):
    store = stalled_owner(True)
    assert OrderedMerge(store, head_wait_seconds=wait, catch_up_depth=1).commit_next('heavy', now) is None


def test_stalled_head_honors_transactional_gate_kill(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_TX_FRESH_GATE_ENABLED', 'false')
    store = stalled_owner(True)
    assert OrderedMerge(store, head_wait_seconds=60, catch_up_depth=1).commit_next('heavy', 86400) is None


def test_stalled_head_missing_index_backs_off_and_keeps_backlog_held(monkeypatch):
    store = stalled_owner(True)
    tx_type = store.run(type)
    calls = []

    def unavailable(tx, key):
        calls.append(key)
        raise FailedPrecondition('synthetic missing index')

    monkeypatch.setattr(tx_type, 'fresh_first_pending', unavailable)
    merge = OrderedMerge(store, head_wait_seconds=60, catch_up_depth=1)
    assert merge.commit_next('heavy', 86400) is None
    assert merge.commit_next('heavy', 86401) is None
    assert len(calls) == 1
    assert store.rows['jobs', 'fresh']['state'] == 'result_ready'
    assert store.rows['jobs', 'held']['state'] == 'result_ready'
