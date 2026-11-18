"""Allowlisted owners skip the head wait behind a stale (starved) head; everyone else is unchanged."""

from dataclasses import asdict
import logging

import pytest

from config.batch_pipeline import MERGE_STALE_HEAD_SECONDS, merge_stale_head_skip
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline.contracts import ProjectionBinding, WorkResult
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.scheduler import Scheduler

ENV = 'BATCH_PIPELINE_MERGE_STALE_HEAD_UID_ALLOWLIST'
NOW = 1_000_000.0
W = 60


def world(*, head_age=7200.0, units=('first',), native=True, head_state='retry'):
    """A days-old fresh-class head, then one sealed recording's units admitted just now."""
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('stale', owner='owner', capture=1), NOW - head_age)
    store.rows['jobs', 'stale'].update(state=head_state, fresh_capture=True)
    binding = ProjectionBinding('owner', 'record-job', 'record-content', tuple(units), native_record=native)
    for i, sid in enumerate(units):
        queue.enqueue(item(sid, owner='owner', capture=NOW - 300 + i), NOW)
        store.rows['jobs', sid].update(projection_binding=asdict(binding), fresh_capture=True)
    return store, OrderedMerge(store, head_wait_seconds=W)


def ready(store, sid, at):
    store.rows['jobs', sid].update(
        state='result_ready', result=WorkResult(sid, 'gs://synthetic/result').to_dict(), ready_at=at
    )


@pytest.fixture
def listed(monkeypatch):
    monkeypatch.setenv(ENV, ' other , owner ')


def test_listed_owner_commits_at_once_behind_a_stale_head(listed, caplog):
    store, merge = world()
    ready(store, 'first', NOW)
    with caplog.at_level(logging.INFO):
        entry = merge.commit_next('owner', NOW + 1)
    assert entry['segment_id'] == 'first' and entry['head_wait_bypass'] is True
    assert store.rows['jobs', 'first']['state'] == 'committed'
    assert store.rows['jobs', 'stale']['merge_pending'] is True  # Appends later as late_capture.
    assert 'outcome=stale_head_skip' in caplog.text


@pytest.mark.parametrize('raw', [None, '', ' , ', 'someone-else'])
def test_unlisted_owner_keeps_the_head_wait(monkeypatch, raw):
    if raw is None:
        monkeypatch.delenv(ENV, raising=False)
    else:
        monkeypatch.setenv(ENV, raw)
    store, merge = world()
    ready(store, 'first', NOW)
    assert merge.commit_next('owner', NOW + W - 1) is None
    assert merge.commit_next('owner', NOW + W)['segment_id'] == 'first'


def test_recent_head_keeps_the_head_wait(listed):
    store, merge = world(head_age=MERGE_STALE_HEAD_SECONDS - W - 1)  # Still recent at NOW + W - 1.
    ready(store, 'first', NOW)
    assert merge.commit_next('owner', NOW + W - 1) is None
    assert merge.commit_next('owner', NOW + W)['segment_id'] == 'first'


def test_head_wait_off_keeps_strict_order(listed):
    store, _ = world()
    merge = OrderedMerge(store, head_wait_seconds=0)
    ready(store, 'first', NOW)
    assert merge.commit_next('owner', NOW + 10**6) is None


def test_an_unready_earlier_unit_of_the_recording_still_waits(listed):
    store, merge = world(units=('first', 'last'))
    ready(store, 'last', NOW)
    assert merge.commit_next('owner', NOW + W - 1) is None
    assert store.rows['jobs', 'last']['state'] == 'result_ready'
    ready(store, 'first', NOW + 5)
    assert merge.commit_next('owner', NOW + 6)['segment_id'] == 'first'
    assert merge.commit_next('owner', NOW + 6)['segment_id'] == 'last'


def test_non_record_work_keeps_the_head_wait(listed):
    store, merge = world(native=False)
    ready(store, 'first', NOW)
    assert merge.commit_next('owner', NOW + W - 1) is None
    assert merge.commit_next('owner', NOW + W)['segment_id'] == 'first'


def test_head_readmitted_after_the_probe_keeps_the_wait(listed, monkeypatch):
    store, merge = world()
    ready(store, 'first', NOW)
    probe = store.longest_ready_pending

    def readmit_then_probe(key):
        # The stale head is re-admitted between the probe and the transaction.
        store.rows['jobs', 'stale']['enqueued_at'] = NOW
        return probe(key)

    monkeypatch.setattr(store, 'longest_ready_pending', readmit_then_probe)
    assert merge.commit_next('owner', NOW + 1) is None
    assert store.rows['jobs', 'first']['state'] == 'result_ready'


@pytest.mark.parametrize(
    'raw,uid,expected',
    [
        (None, 'owner', False),
        ('', 'owner', False),
        ('owner', '', False),
        ('owner', 'owner', True),
        ('a, owner ,b', 'owner', True),
        ('owners', 'owner', False),
    ],
)
def test_allowlist_parses_exact_members(monkeypatch, raw, uid, expected):
    if raw is None:
        monkeypatch.delenv(ENV, raising=False)
    else:
        monkeypatch.setenv(ENV, raw)
    assert merge_stale_head_skip(uid) is expected


@pytest.mark.parametrize('tx_gate', [False, True])
@pytest.mark.parametrize('listed_owner', [False, True])
def test_catch_up_head_with_older_fresh_stock_behind_it(monkeypatch, tx_gate, listed_owner):
    # Prod shape: a starved catch-up record head, then starved fresh-class
    # non-record stock, then the recording that was just sealed.
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_TX_FRESH_GATE_ENABLED', str(tx_gate).lower())
    monkeypatch.setenv(ENV, 'owner' if listed_owner else '')
    store, merge = world()
    store.rows['jobs', 'stale']['fresh_capture'] = False
    Scheduler(store).enqueue(item('stock', owner='owner', capture=2), NOW - 7200)
    store.rows['jobs', 'stock'].update(state='retry', fresh_capture=True)
    ready(store, 'first', NOW)
    entry = merge.commit_next('owner', NOW + 1)
    if listed_owner:
        assert entry['segment_id'] == 'first'
    else:
        assert entry is None
        assert merge.commit_next('owner', NOW + W)['segment_id'] == 'first'
