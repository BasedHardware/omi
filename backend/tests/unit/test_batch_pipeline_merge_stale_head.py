"""Allowlisted owners skip the head wait behind a stale (starved) head; everyone else is unchanged."""

from dataclasses import asdict
import logging

import pytest

from config.batch_pipeline import MERGE_STALE_HEAD_SECONDS, merge_stale_head_skip
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline.contracts import ProjectionBinding, WorkResult
from utils.batch_pipeline.merge import STALE_HEAD_PAGE_ROWS, OrderedMerge
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
    assert entry['segment_id'] == 'first' and 'head_wait_bypass' not in entry
    assert store.rows['jobs', 'first']['state'] == 'committed'
    assert store.rows['jobs', 'stale']['merge_pending'] is True  # Appends later as late_capture.
    # The due retry head is promoted (requeued) first, then the skip passes it as a ready head.
    assert 'outcome=stale_head_promoted action=requeued source=ordered_merge count=1' in caplog.text
    assert store.rows['jobs', 'stale']['state'] == 'ready'
    assert 'outcome=stale_head_skip source=ordered_merge head_state=ready wait_bucket=lt60' in caplog.text
    assert 'outcome=head_wait_bypass' not in caplog.text


def test_listed_owner_skip_without_promotion_reports_the_retry_head(listed, monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_STALE_HEAD_PROMOTE_ENABLED', 'false')
    store, merge = world()
    ready(store, 'first', NOW)
    with caplog.at_level(logging.INFO):
        entry = merge.commit_next('owner', NOW + 1)
    assert entry['segment_id'] == 'first' and store.rows['jobs', 'stale']['state'] == 'retry'
    assert 'outcome=stale_head_skip source=ordered_merge head_state=retry wait_bucket=lt60' in caplog.text


def test_an_expired_wait_keeps_the_bypass_marker(monkeypatch, caplog):
    monkeypatch.delenv(ENV, raising=False)
    store, merge = world()
    ready(store, 'first', NOW)
    with caplog.at_level(logging.INFO):
        entry = merge.commit_next('owner', NOW + W)
    assert entry['head_wait_bypass'] is True
    assert 'outcome=head_wait_bypass' in caplog.text and 'outcome=stale_head_skip' not in caplog.text


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


def test_a_young_unready_recording_captured_earlier_blocks_the_skip(listed):
    # Recording A (captured earlier, admitted 5 s ago) is on the GPU; B is ready first.
    store, merge = world(units=('b',))
    queue = Scheduler(store)
    queue.enqueue(item('a', owner='owner', capture=NOW - 600), NOW - 5)
    a = ProjectionBinding('owner', 'record-a', 'content-a', ('a',), native_record=True)
    store.rows['jobs', 'a'].update(
        state='leased', lease_until=NOW + 300, fresh_capture=True, projection_binding=asdict(a)
    )
    ready(store, 'b', NOW)
    assert merge.commit_next('owner', NOW + 1) is None
    ready(store, 'a', NOW + 9)
    assert [merge.commit_next('owner', NOW + 10)['segment_id'] for _ in range(2)] == ['a', 'b']


# Lease-ending paths reset lease_until to 0.0 and stamp available_at; enqueued_at stays old.
@pytest.mark.parametrize(
    'head',
    [
        {'state': 'leased', 'token': 't', 'attempt': 1, 'lease_until': NOW + 300},  # In flight.
        {  # Lease expired seconds ago and due again in 10 s.
            'state': 'retry',
            'attempt': 1,
            'lease_until': 0.0,
            'available_at': NOW + 10,
            'retry_started_at': NOW - 3600,
            'failure': 'lease_expired',
        },
        {  # Failed 10 minutes ago; due, but likely re-leased soon.
            'state': 'retry',
            'attempt': 2,
            'lease_until': 0.0,
            'available_at': NOW - 600,
            'retry_started_at': NOW - 3600,
            'failure': 'worker_failed',
        },
        {'state': 'ready', 'lease_until': 0.0, 'available_at': NOW - 60, 'failure': ''},  # Redriven a minute ago.
        {'state': 'record_pending', 'lease_until': 0.0},  # About to be admitted.
        {'state': 'held', 'lease_until': 0.0},
    ],
    ids=['in_flight', 'due_in_seconds', 'failed_recently', 'redriven', 'record_pending', 'held'],
)
def test_a_head_that_is_not_starved_keeps_the_wait(listed, head):
    store, merge = world()
    store.rows['jobs', 'stale'].update(head)
    ready(store, 'first', NOW)
    assert merge.commit_next('owner', NOW + 1) is None
    assert store.rows['jobs', 'first']['state'] == 'result_ready'


def test_a_requeued_ready_row_ahead_of_the_unit_blocks_the_skip(listed):
    # Admitted hours ago but requeued a minute ago (lease_until reset to 0): due now, not starved.
    store, merge = world()
    Scheduler(store).enqueue(item('requeued', owner='owner', capture=2), NOW - 7200)
    store.rows['jobs', 'requeued'].update(state='ready', available_at=NOW - 60, lease_until=0.0)
    ready(store, 'first', NOW)
    assert merge.commit_next('owner', NOW + 1) is None


def test_a_retry_due_for_hours_without_a_lease_is_starved(listed):
    # Prod shape: failed once, due 10+ hours, never leased again.
    store, merge = world(head_age=40 * 3600)
    store.rows['jobs', 'stale'].update(
        attempt=1,
        lease_until=0.0,
        available_at=NOW - 10 * 3600,
        retry_started_at=NOW - 40 * 3600,
        failure='worker_failed',
    )
    ready(store, 'first', NOW)
    assert merge.commit_next('owner', NOW + 1)['segment_id'] == 'first'


@pytest.mark.parametrize('extra,commits', [(STALE_HEAD_PAGE_ROWS - 1, True), (STALE_HEAD_PAGE_ROWS, False)])
def test_the_page_bound_refuses_the_skip(listed, extra, commits):
    store, merge = world()
    queue = Scheduler(store)
    for i in range(extra):
        queue.enqueue(item(f'stock-{i:03}', owner='owner', capture=2 + i), NOW - 7200)
        store.rows['jobs', f'stock-{i:03}'].update(state='retry')
    ready(store, 'first', NOW)
    entry = merge.commit_next('owner', NOW + 1)
    assert (entry is not None and entry['segment_id'] == 'first') is commits


def test_head_deferred_after_the_probe_keeps_the_wait(listed, monkeypatch):
    store, merge = world()
    ready(store, 'first', NOW)
    probe = store.longest_ready_pending

    def defer_then_probe(key):
        # A lease on the head ends between the probe and the transaction.
        store.rows['jobs', 'stale'].update(attempt=1, lease_until=0.0, available_at=NOW + 5, failure='lease_expired')
        return probe(key)

    monkeypatch.setattr(store, 'longest_ready_pending', defer_then_probe)
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


def test_a_refused_skip_of_a_backlog_held_unit_commits_and_holds_nothing(listed, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_BACKLOG_RELEASE_METER_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_TX_FRESH_GATE_ENABLED', 'true')
    store, merge = world()
    store.rows['jobs', 'first'].update(stt_route={'stt_route': 'provider'}, fresh_capture=False)
    ready(store, 'first', NOW)
    runs = []
    run = store.run
    monkeypatch.setattr(store, 'run', lambda body: runs.append(body) or run(body))
    assert merge.commit_next('owner', NOW + 1) is None
    assert store.rows['jobs', 'first']['state'] == 'result_ready'
    assert merge.held_owners == set()
    assert len(runs) == 2  # Strict order, then the refused skip: no early backlog fallback.
    assert merge.commit_next('owner', NOW + W - 1) is None and merge.held_owners == set()
