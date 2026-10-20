"""Recovery wake releases the recovered unit past the head wait and depth hold (5% run 18 tail)."""

import logging
import time
from unittest.mock import Mock

from google.api_core.exceptions import FailedPrecondition

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from tests.unit.test_batch_pipeline_merge_head_wait import admitted, complete, drain
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline.merge import RELEASE_SIBLINGS_MAX, OrderedMerge
from utils.batch_pipeline.scheduler import owner_key
from utils.batch_pipeline.serving import Serving

W = 60
OWNER = owner_key('heavy')
SWITCH = 'BATCH_PIPELINE_RECOVERED_MERGE_RELEASE_ENABLED'


def recovered(store, segment, settled, siblings=()):
    """The recovery settle writer: the unit re-enters merge_pending, ready, with ready_at = settle."""
    store.rows['jobs', segment].update(
        state='result_ready', merge_pending=True, recovery_state='recovered', ready_at=settled, result={'r': segment}
    )
    store.rows['jobs', segment]['projection_binding'] = {'segment_ids': [segment, *siblings]}


def test_recovered_row_behind_a_leased_head_commits_at_once_with_release():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    recovered(store, 'b', 500)
    merge = OrderedMerge(store, head_wait_seconds=W)
    assert merge.commit_next('heavy', 501) is None  # Without the wake: the head wait still applies.
    entry = merge.commit_next('heavy', 501, release=merge.release_set('b'))
    assert entry['segment_id'] == 'b' and entry['recovered_release'] is True and entry['recovery_version'] == 1
    assert 'head_wait_bypass' not in entry and entry['late_capture'] is False and entry['log_sequence'] == 1
    assert store.rows['jobs', 'a']['merge_pending'] is True  # The leased head is untouched.
    complete(queue, leases, 'a', 600)
    late = merge.commit_next('heavy', 600)
    assert late['segment_id'] == 'a' and late['late_capture'] is True and late['previous_segment_id'] == 'b'


def test_release_takes_the_contents_ready_siblings_but_never_unready_or_foreign_rows():
    store, queue, leases = admitted({'a': 1, 'b': 2, 'c': 3, 'd': 4, 'e': 5})
    recovered(store, 'b', 500, siblings=('c', 'd'))
    complete(queue, leases, 'c', 400)  # Ready sibling, captured after the recovered unit.
    complete(queue, leases, 'e', 480)  # Ready, another content, under W: it keeps its own head wait.
    merge = OrderedMerge(store, head_wait_seconds=W)
    release = merge.release_set('b')
    assert release == ['b', 'c', 'd']
    entries = []
    while entry := merge.commit_next('heavy', 501, release=release):
        entries.append(entry)
    assert [e['segment_id'] for e in entries] == ['b', 'c']
    assert all(e['recovered_release'] for e in entries)
    assert release == []  # d is still leased: dropped, it commits on its own completion.
    assert store.rows['jobs', 'd']['merge_pending'] and store.rows['jobs', 'e']['merge_pending']


def test_release_set_is_bounded():
    store, _, _ = admitted({'a': 1})
    siblings = [f's{n}' for n in range(RELEASE_SIBLINGS_MAX + 10)]
    recovered(store, 'a', 10, siblings=siblings)
    release = OrderedMerge(store).release_set('a')
    assert release[0] == 'a' and len(release) == RELEASE_SIBLINGS_MAX + 1


def test_release_passes_the_catch_up_depth_hold():
    store, queue, leases = admitted({'c0': 1, 'c1': 2, 'r': 3})
    for segment in ('c0', 'c1', 'r'):
        store.rows['jobs', segment]['fresh_capture'] = False
    complete(queue, leases, 'c0', 10)
    complete(queue, leases, 'c1', 10)
    merge = OrderedMerge(store, head_wait_seconds=W, catch_up_depth=2)
    assert [e['segment_id'] for e in drain(merge, 11)] == ['c0', 'c1']
    recovered(store, 'r', 20)
    assert merge.commit_next('heavy', 21) is None  # Two committed rows await projection: held.
    entry = merge.commit_next('heavy', 21, release=merge.release_set('r'))
    assert entry['segment_id'] == 'r' and entry['recovered_release'] is True and entry['log_sequence'] == 3


def test_only_the_recovered_unit_passes_the_depth_hold_not_its_siblings():
    store, queue, leases = admitted({'c0': 1, 'c1': 2, 'r': 3, 's': 4})
    for segment in ('c0', 'c1', 'r', 's'):
        store.rows['jobs', segment]['fresh_capture'] = False
    for segment in ('c0', 'c1', 's'):
        complete(queue, leases, segment, 10)
    merge = OrderedMerge(store, head_wait_seconds=W, catch_up_depth=2)
    assert [e['segment_id'] for e in drain(merge, 11)] == ['c0', 'c1']
    recovered(store, 'r', 20, siblings=('s',))
    release = merge.release_set('r')
    entries = []
    while entry := merge.commit_next('heavy', 21, release=release):
        entries.append(entry)
    # The ready catch-up sibling s keeps the depth hold.
    assert [e['segment_id'] for e in entries] == ['r']
    assert store.rows['jobs', 's']['merge_pending'] is True


class _NoFreshIndexStore(MemoryStore):
    def fresh_pending(self, owner_key, limit):
        raise FailedPrecondition('The query requires an index.')


def test_missing_fresh_index_fallback_keeps_the_release_set():

    store, _, _ = admitted({'a': 1, 'b': 2})
    store.__class__ = _NoFreshIndexStore
    for segment in ('a', 'b'):
        store.rows['jobs', segment]['fresh_capture'] = False
    recovered(store, 'b', 500)
    merge = OrderedMerge(store, head_wait_seconds=W, catch_up_depth=4)
    entry = merge.commit_next('heavy', 501, release=merge.release_set('b'))
    assert entry['segment_id'] == 'b' and entry['recovered_release'] is True


def test_strict_order_still_wins_when_the_head_is_ready():
    store, queue, leases = admitted({'a': 1, 'b': 2})
    complete(queue, leases, 'a', 10)
    recovered(store, 'b', 500)
    merge = OrderedMerge(store, head_wait_seconds=W)
    release = merge.release_set('b')
    first = merge.commit_next('heavy', 501, release=release)
    second = merge.commit_next('heavy', 501, release=release)
    assert [first['segment_id'], second['segment_id']] == ['a', 'b']
    assert 'recovered_release' not in first and 'recovered_release' not in second


def test_committed_or_quarantined_release_rows_are_dropped_and_strict_result_returned():
    store, _, _ = admitted({'a': 1, 'b': 2})
    store.rows['jobs', 'b'].update(state='quarantined', merge_pending=False)
    merge = OrderedMerge(store, head_wait_seconds=W)
    release = ['b']
    assert merge.commit_next('heavy', 10**6, release=release) is None
    assert release == []


def test_kill_switch_off_keeps_the_head_wait(monkeypatch):
    monkeypatch.setenv(SWITCH, 'false')
    store, _, _ = admitted({'a': 1, 'b': 2})
    recovered(store, 'b', time.time())  # Serving uses the wall clock: settled just now.
    merge = OrderedMerge(store, head_wait_seconds=W)
    assert merge.commit_next('heavy', 501, release=['b']) is None
    service = Serving(store)
    service.drain_owner('heavy', recovered='b')
    assert ('results', 'b') not in store.rows


def test_a_fenced_release_commit_drops_the_row_and_returns_the_strict_result(monkeypatch):
    store, _, _ = admitted({'a': 1, 'b': 2})
    recovered(store, 'b', 500)
    merge = OrderedMerge(store, head_wait_seconds=W)
    release = merge.release_set('b')
    calls, original = [], store.run

    def run(body):
        calls.append(body)
        # Calls: strict commit, release pre-read, then the release commit.
        if len(calls) == 3:
            raise BatchPrivacyBlocked('account_deleted')
        return original(body)

    monkeypatch.setattr(store, 'run', run)
    assert merge.commit_next('heavy', 501, release=release) is None
    assert release == [] and ('results', 'b') not in store.rows


def test_serving_wake_commits_the_recovered_row_before_the_chain_walk():
    store, _, _ = admitted({'a': 1, 'b': 2})
    recovered(store, 'b', time.time())  # Serving uses the wall clock: settled just now.
    seen = []
    projector = Mock(has_async_followups=False)
    projector.project_owner.side_effect = (
        lambda owner, recovered: seen.append(('results', recovered) in store.rows) or []
    )
    service = Serving(store, projector=projector)
    service.reconcile(owner_id='heavy', recovered='b')
    assert seen == [True]
    assert store.rows['results', 'b']['recovered_release'] is True


def test_release_log_has_closed_labels_and_no_ids(caplog):
    store, _, _ = admitted({'secret-head': 1, 'secret-unit': 2})
    recovered(store, 'secret-unit', 500)
    merge = OrderedMerge(store, head_wait_seconds=W)
    with caplog.at_level(logging.INFO):
        assert merge.commit_next('heavy', 501, release=merge.release_set('secret-unit'))
    lines = [r.getMessage() for r in caplog.records if 'recovered_release' in r.getMessage()]
    assert lines == ['event=batch_merge outcome=recovered_release source=ordered_merge head_state=leased count=1']
    assert not any('secret' in r.getMessage() or 'heavy' in r.getMessage() for r in caplog.records)
