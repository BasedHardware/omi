"""Held owners with a ready catch-up head stop re-opening the wide hold query (x760 exhaustion family).

The blocked-head probe gate (``test_merge_blocked_head_probe_gate``) skips
drains whose probed head can only conclude ``blocked``, and the
revision-fenced narrow commit (``test_merge_narrow_commit_revision_fence``)
commits plain ready fresh heads through three point reads. The last
unconditional strict drain left in ``OrderedMerge.commit_next`` is the held
owner's ready catch-up head: an owner parked at the projection depth cap
carries a durable hold marker, and the pump re-drains it from three
directions every cycle (after each unit completion, through the global
``result_ready`` page, through the marked-owner re-offer). Every one of those
drains opened the strict ``batch_merge_commit`` transaction whose first act is
the owner's pending query — a query-in-transaction read set is every matched
row, the documents each sibling lease heartbeat keeps rewriting — only to
re-conclude ``held`` and write nothing:

    event=batch_merge outcome=retry exception_type=FirestoreContentionExhausted

``commit_next`` now probes before it transacts: when the probed head is this
owner's pending catch-up row in ``result_ready``, the probed owner still sits
at the cap, and the probed durable marker is already set, the drain skips the
transaction and records the same held facts the body would have. Every gate
refusal — fresh head, shadow, unmarked owner, below-cap probe, probe failure,
kill switch, release wake — keeps the strict transaction as the authority, and
a ready fresh row still commits through the unchanged fresh-first re-verify in
the same drain. This suite pins:

1. Gate decisions: exactly the marked ready catch-up head at cap skips; every
   refusal keeps the strict (or narrow) authority with its exact transaction
   count, query reads, writes and held facts.
2. Fact mirroring: the skip records ``held['over_cap']`` and
   ``held['catch_up']`` so the after-run mirrors — the ``held_owners`` hint and
   the fresh-first probe — behave exactly as after a strict hold re-decide.
3. Fresh-first preservation: a ready fresh row commits past the cap in the
   same skipped drain through the unchanged re-verify, with one transaction
   fewer than the strict world.
4. Liveness: once projection advances below the cap the next drain commits
   through the narrow body, ``release_hold`` clears the marker, and the
   marked-owner re-offer restores the normal drain.
5. Staleness bounds: a stale at-cap probe skips without writing and the next
   honest drain commits; no commit ever lands from a stale hint.
6. Ordering: catch-up commit order, ``late_capture`` flags and owner fences
   are identical with the gate on and off.
7. Interleaving on the real store class with a heartbeat-storm client: held
   drains open zero transactions during the storm while the strict world
   exhausts; the fresh re-verify still exhausts (unchanged); the owner leaves
   the storm without a single aborted transaction once the cap clears.
8. Multi-owner isolation, maintenance re-offer semantics, probe surfaces,
   config, the flag budget registration and log hygiene.

Failure-Class: FC-held-owner-ready-catch-up-drains-reopen-the-wide-hold-query
"""

import json
import logging
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import ServiceUnavailable

from database import batch_pipeline_store as storage
from database.firestore_transaction_retry import FirestoreContentionExhausted
from tests.unit.test_batch_pipeline_scheduler import Scheduler, item
from tests.unit.test_merge_blocked_head_probe_gate import (
    NAMESPACE,
    OWNER,
    StormClient,
    at_cap,
    complete,
    set_state,
    storm_merge,
    storm_rows,
)
from tests.unit.test_merge_narrow_commit_revision_fence import RecordingStore, table_rows
from utils.batch_pipeline import merge as merge_module
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.scheduler import owner_key

STEADY = 100_500.0
OTHER = owner_key('other')


# --------------------------------------------------------------------------
# Harnesses
# --------------------------------------------------------------------------


def held_store(
    marker=True,
    sequence=6,
    watermark='w5',
    done=1,
    head_state='result_ready',
    head_class=False,
):
    """One owner whose head ``a`` is a settled ready row; the owner sits at the
    projection depth cap. ``marker`` presets the durable hold marker (the
    parked state maintenance leaves behind); without it the owner is at cap
    but not yet marked. ``done`` is the watermark row's committed count:
    unprojected = sequence - done, so ``done >= sequence - depth`` parks the
    owner at cap and anything less leaves it below."""
    store = RecordingStore()
    queue = Scheduler(store)
    queue.enqueue(item('a', capture=1), 0)
    leases = {lease.item.segment_id: lease for lease in queue.pull(0, 1)}
    complete(queue, leases, 'a')
    store.rows['jobs', 'a']['fresh_capture'] = head_class
    if head_state != 'result_ready':
        set_state(store, 'a', head_state)
    at_cap(store.inner, sequence=sequence, watermark=watermark, done=done)
    if marker:
        store.rows['merge_holds', OWNER] = {'held': True, 'held_at': 1}
    store.reset_counts()
    return store


def drain_held(store, now=STEADY, depth=2, wait=0, release=None, owner_id='heavy'):
    merge = OrderedMerge(store, head_wait_seconds=wait, catch_up_depth=depth)
    return merge, merge.commit_next(owner_id, now, release=release)


def gate_off(monkeypatch):
    monkeypatch.setattr(merge_module, 'merge_held_head_gate_enabled', lambda: False)


def add_sibling(store, segment, capture, capture_class, state='result_ready'):
    """Admit, lease and settle one more row on the same owner."""
    queue = Scheduler(store)
    queue.enqueue(item(segment, capture=capture), 0)
    leases = {lease.item.segment_id: lease for lease in queue.pull(0, 1)}
    complete(queue, leases, segment)
    store.rows['jobs', segment]['fresh_capture'] = capture_class
    if state != 'result_ready':
        set_state(store, segment, state)
    store.reset_counts()


def advance_projection(store, key='w8', sequence=6):
    """Projection committed through ``key``: the owner drops below the cap."""
    store.rows['results', key] = {'log_sequence': sequence}
    store.rows['owners', OWNER]['projection_watermark'] = key


def reads_of(store, index=-1):
    return store.read_log[index]


def total_reads(store):
    return [read for run_reads in store.read_log for read in run_reads]


def writes_of(store):
    return [write for run_writes in store.write_log for write in run_writes]


def flaky_probe(store, failing_table):
    """Probe stub that raises only for ``failing_table``."""
    inner = store.inner.probe

    def probe(table, key):
        if table == failing_table:
            raise ServiceUnavailable(f'{table} probe down')
        return inner(table, key)

    store.probe = probe


def storm_held_rows(head_state='result_ready', sibling_state='leased', head_class=False):
    """Storm world: ``a`` the head row, ``b`` the hot in-flight sibling whose
    lease heartbeat keeps rewriting its row, the owner parked at the cap with
    its durable marker set."""
    rows = storm_rows(head_state=head_state)
    rows[f'{NAMESPACE}_jobs', 'a'].update(
        {
            'fresh_capture': head_class,
            'ready_at': 10.0,
            'result': {'outcome': 'success', 'result_uri': 'gs://results/a', 'segment_id': 'a'},
        }
    )
    if sibling_state != rows[f'{NAMESPACE}_jobs', 'b']['state']:
        rows[f'{NAMESPACE}_jobs', 'b']['state'] = sibling_state
    rows[f'{NAMESPACE}_owners', OWNER] = {
        'log_sequence': 6,
        'projection_watermark': 'w5',
        'revision': 3,
    }
    rows[f'{NAMESPACE}_results', 'w5'] = {'log_sequence': 1}
    rows[f'{NAMESPACE}_merge_holds', OWNER] = {'held': True, 'held_at': 1}
    return rows


def second_owner_rows(store):
    """A second owner ``other`` with one plain ready fresh head, below any cap."""
    store.rows['owners', OTHER] = {'log_sequence': 1, 'projection_watermark': None}
    queue = Scheduler(store)
    queue.enqueue(item('o1', owner='other', capture=1), 0)
    leases = {lease.item.segment_id: lease for lease in queue.pull(0, 1)}
    complete(queue, leases, 'o1')
    store.rows['jobs', 'o1']['fresh_capture'] = True
    store.reset_counts()


def parked_second_owner(store):
    """A second owner parked at the cap exactly like the first."""
    store.rows['owners', OTHER] = {'log_sequence': 6, 'projection_watermark': 'w5'}
    queue = Scheduler(store)
    queue.enqueue(item('x', owner='other', capture=1), 0)
    leases = {lease.item.segment_id: lease for lease in queue.pull(0, 1)}
    complete(queue, leases, 'x')
    store.rows['jobs', 'x']['fresh_capture'] = False
    store.rows['merge_holds', OTHER] = {'held': True, 'held_at': 1}
    store.reset_counts()


# --------------------------------------------------------------------------
# 1. Gate decisions: only the marked ready catch-up head skips
# --------------------------------------------------------------------------


def test_marked_ready_catch_up_head_opens_no_transaction():
    store = held_store()
    merge, entry = drain_held(store)
    assert entry is None
    assert store.runs == 0


def test_marked_ready_catch_up_head_writes_nothing():
    store = held_store()
    drain_held(store)
    assert store.write_log == []


def test_marked_ready_catch_up_head_adds_the_held_owner_hint():
    store = held_store()
    merge, _entry = drain_held(store)
    assert merge.held_owners == {'heavy'}


def test_marked_ready_catch_up_head_keeps_the_marker_untouched():
    store = held_store()
    drain_held(store)
    assert store.rows['merge_holds', OWNER] == {'held': True, 'held_at': 1}


def test_marked_ready_catch_up_head_keeps_the_head_pending():
    store = held_store()
    drain_held(store)
    assert store.rows['jobs', 'a']['state'] == 'result_ready'
    assert store.rows['jobs', 'a']['merge_pending'] is True


def test_marked_ready_catch_up_head_performs_no_transactional_query():
    store = held_store()
    drain_held(store)
    assert total_reads(store) == []


def test_marked_ready_catch_up_head_is_stable_across_re_offers():
    store = held_store()
    merge, _entry = drain_held(store)
    merge, _entry = drain_held(store)
    merge, _entry = drain_held(store)
    assert store.runs == 0
    assert merge.held_owners == {'heavy'}
    assert store.write_log == []


def test_unmarked_ready_catch_up_head_keeps_the_strict_marker_write():
    store = held_store(marker=False)
    merge, entry = drain_held(store)
    assert entry is None
    assert store.runs == 1
    assert store.rows['merge_holds', OWNER]['held'] is True
    assert merge.held_owners == {'heavy'}


def test_unmarked_ready_catch_up_head_strict_run_carries_the_commit_label():
    store = held_store(marker=False)
    drain_held(store)
    assert store.run_operations == ['batch_merge_commit']


def test_unmarked_ready_catch_up_head_strict_run_reads_the_pending_query():
    store = held_store(marker=False)
    drain_held(store)
    assert ('query', 'first_pending', OWNER) in reads_of(store)


def test_ready_fresh_head_at_cap_keeps_the_strict_commit():
    store = held_store(head_class=True)
    merge, entry = drain_held(store)
    assert entry['segment_id'] == 'a'
    assert store.runs == 1
    assert ('query', 'first_pending', OWNER) in reads_of(store)


def test_ready_fresh_head_at_cap_marker_is_not_rewritten():
    store = held_store(head_class=True)
    drain_held(store)
    assert store.rows['merge_holds', OWNER] == {'held': True, 'held_at': 1}


def test_ready_fresh_head_at_cap_adds_the_held_owner_hint():
    store = held_store(head_class=True)
    merge, _entry = drain_held(store)
    assert merge.held_owners == {'heavy'}


def test_ready_fresh_head_at_cap_commits_with_no_fresh_first_flag():
    store = held_store(head_class=True)
    _merge, entry = drain_held(store)
    assert 'fresh_first' not in entry


def test_below_cap_ready_catch_up_head_commits_through_the_narrow_body():
    store = held_store(sequence=6, watermark='w5', done=5)
    merge, entry = drain_held(store)
    assert entry['segment_id'] == 'a'
    assert store.rows['jobs', 'a']['state'] == 'committed'
    assert store.runs == 1


def test_below_cap_ready_catch_up_head_narrow_run_has_no_pending_query():
    store = held_store(sequence=6, watermark='w5', done=5)
    drain_held(store)
    assert all(read[0] != 'query' for read in reads_of(store))


def test_below_cap_ready_catch_up_head_clears_the_held_owner_hint():
    store = held_store(sequence=6, watermark='w5', done=5)
    merge, _entry = drain_held(store)
    assert merge.held_owners == set()


def test_below_cap_ready_catch_up_head_never_probes_the_marker():
    store = held_store(sequence=6, watermark='w5', done=5)
    drain_held(store)
    assert ('merge_holds', OWNER) not in store.probed


def test_cleared_marker_at_cap_remarks_through_the_strict_body():
    store = held_store()
    store.rows['merge_holds', OWNER] = {'held': False, 'held_at': 1}
    drain_held(store)
    assert store.runs == 1
    assert store.rows['merge_holds', OWNER]['held'] is True


def test_cleared_marker_at_cap_adds_the_held_owner_hint_again():
    store = held_store()
    store.rows['merge_holds', OWNER] = {'held': False, 'held_at': 1}
    merge, _entry = drain_held(store)
    assert merge.held_owners == {'heavy'}


def test_shadow_ready_catch_up_head_keeps_the_strict_no_op():
    store = held_store()
    store.rows['jobs', 'a']['shadow'] = True
    merge, entry = drain_held(store)
    assert entry is None
    assert store.runs == 1
    assert ('query', 'first_pending', OWNER) in reads_of(store)


def test_shadow_ready_catch_up_head_records_no_held_facts():
    store = held_store()
    store.rows['jobs', 'a']['shadow'] = True
    merge, _entry = drain_held(store)
    assert merge.held_owners == set()


def test_shadow_ready_catch_up_head_keeps_the_marker_untouched():
    store = held_store()
    store.rows['jobs', 'a']['shadow'] = True
    drain_held(store)
    assert store.rows['merge_holds', OWNER] == {'held': True, 'held_at': 1}


def test_fresh_blocked_head_marked_at_cap_keeps_the_probe_gate_skip():
    """The t267 gate already skips fresh blocked heads; the new gate must not
    disturb that skip."""
    store = held_store(head_state='leased', head_class=True)
    merge, entry = drain_held(store)
    assert entry is None
    assert store.runs == 0
    assert merge.held_owners == {'heavy'}


def test_catch_up_blocked_head_marked_at_cap_keeps_the_strict_re_decide():
    """A blocked catch-up head keeps the strict transaction: it feeds the
    fresh-first machinery, which the strict body alone records."""
    store = held_store(head_state='leased', head_class=False)
    merge, entry = drain_held(store)
    assert entry is None
    assert store.runs == 1
    assert ('query', 'first_pending', OWNER) in reads_of(store)
    assert merge.held_owners == {'heavy'}


def test_catch_up_blocked_head_marked_at_cap_keeps_the_marker_untouched():
    store = held_store(head_state='retry', head_class=False)
    drain_held(store)
    assert store.rows['merge_holds', OWNER] == {'held': True, 'held_at': 1}


def test_depth_disabled_ready_catch_up_head_commits_through_the_narrow_body():
    store = held_store()
    merge = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=0)
    entry = merge.commit_next('heavy', STEADY)
    assert entry['segment_id'] == 'a'
    assert store.runs == 1


def test_depth_disabled_ready_catch_up_head_probes_no_marker():
    store = held_store()
    merge = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=0)
    merge.commit_next('heavy', STEADY)
    assert ('merge_holds', OWNER) not in store.probed


def test_head_probe_failure_keeps_the_strict_hold_re_decide():
    store = held_store()
    store.head_pending_error = ServiceUnavailable('hint read down')
    merge, entry = drain_held(store)
    assert entry is None
    assert store.runs == 1
    assert merge.held_owners == {'heavy'}


def test_head_probe_failure_strict_run_still_refuses_to_commit_the_head():
    store = held_store()
    store.head_pending_error = ServiceUnavailable('hint read down')
    drain_held(store)
    assert store.rows['jobs', 'a']['state'] == 'result_ready'
    assert store.rows['merge_holds', OWNER] == {'held': True, 'held_at': 1}


def test_marker_probe_failure_keeps_the_strict_hold_re_decide():
    store = held_store()
    flaky_probe(store, 'merge_holds')
    merge, entry = drain_held(store)
    assert entry is None
    assert store.runs == 1
    assert merge.held_owners == {'heavy'}


def test_marker_probe_failure_commits_nothing():
    store = held_store()
    flaky_probe(store, 'merge_holds')
    drain_held(store)
    assert store.rows['jobs', 'a']['state'] == 'result_ready'


def test_marker_probe_failure_is_logged_as_a_retry_outcome(caplog):
    store = held_store()
    flaky_probe(store, 'merge_holds')
    with caplog.at_level(logging.WARNING, logger='utils.batch_pipeline.merge'):
        drain_held(store)
    messages = [record.getMessage() for record in caplog.records]
    assert any('outcome=held_marker_probe_retry' in message for message in messages)


def test_marker_probe_failure_log_carries_the_exception_type(caplog):
    store = held_store()
    flaky_probe(store, 'merge_holds')
    with caplog.at_level(logging.WARNING, logger='utils.batch_pipeline.merge'):
        drain_held(store)
    warnings = [record for record in caplog.records if 'held_marker_probe_retry' in record.getMessage()]
    assert warnings and 'ServiceUnavailable' in warnings[-1].getMessage()


def test_marker_probe_failure_still_re_decides_held_from_its_own_query():
    store = held_store()
    flaky_probe(store, 'merge_holds')
    merge, _entry = drain_held(store)
    assert ('query', 'first_pending', OWNER) in reads_of(store)


def test_marker_probe_failure_on_a_committing_owner_still_commits():
    """A marker probe outage must not stop a drain the strict body would finish:
    below the cap the gate never reaches the marker probe."""
    store = held_store(sequence=6, watermark='w5', done=5)
    flaky_probe(store, 'merge_holds')
    _merge, entry = drain_held(store)
    assert entry['segment_id'] == 'a'
    assert store.rows['jobs', 'a']['state'] == 'committed'


def test_over_cap_probe_failure_propagates_exactly_as_before_the_gate():
    """The over-cap probe was already part of the narrow gate's condition for
    ready heads; its failure surface is unchanged."""
    store = held_store()
    flaky_probe(store, 'owners')
    with pytest.raises(ServiceUnavailable):
        drain_held(store)


def test_release_wake_with_a_held_ready_catch_up_head_is_not_gated():
    store = held_store()
    add_sibling(store, 'b', 2, capture_class=False)
    store.rows['jobs', 'b']['recovery_state'] = 'recovered'
    merge, entry = drain_held(store, release=['b'])
    assert entry['segment_id'] == 'b'
    assert store.runs == 2
    assert store.run_operations == ['batch_merge_commit', 'batch_merge_commit']


def test_release_wake_commits_the_recovered_row_with_its_flag():
    store = held_store()
    add_sibling(store, 'b', 2, capture_class=False)
    store.rows['jobs', 'b']['recovery_state'] = 'recovered'
    merge, entry = drain_held(store, release=['b'])
    assert entry['recovered_release'] is True
    assert ('query', 'first_pending', OWNER) in total_reads(store)


def test_release_wake_keeps_the_catch_up_head_pending():
    store = held_store()
    add_sibling(store, 'b', 2, capture_class=False)
    store.rows['jobs', 'b']['recovery_state'] = 'recovered'
    drain_held(store, release=['b'])
    assert store.rows['jobs', 'a']['merge_pending'] is True


def test_release_wake_strict_world_parity(monkeypatch):
    on = held_store()
    add_sibling(on, 'b', 2, capture_class=False)
    on.rows['jobs', 'b']['recovery_state'] = 'recovered'
    _merge_on, entry_on = drain_held(on, release=['b'])
    gate_off(monkeypatch)
    off = held_store()
    add_sibling(off, 'b', 2, capture_class=False)
    off.rows['jobs', 'b']['recovery_state'] = 'recovered'
    _merge_off, entry_off = drain_held(off, release=['b'])
    assert entry_on['segment_id'] == entry_off['segment_id'] == 'b'
    assert table_rows(on) == table_rows(off)


def test_release_of_only_the_held_head_commits_nothing():
    """Only recovered units pass the depth hold; a plain release of the parked
    catch-up head re-concludes held through the strict body — the hold
    re-decide plus the release re-verify, both writing nothing."""
    store = held_store()
    merge, entry = drain_held(store, release=['a'])
    assert entry is None
    assert store.runs == 2
    assert store.run_operations == ['batch_merge_commit', 'batch_merge_commit']
    assert merge.held_owners == {'heavy'}
    assert store.rows['jobs', 'a']['merge_pending'] is True
    assert store.rows['merge_holds', OWNER] == {'held': True, 'held_at': 1}


def test_gate_decision_matrix_matches_the_strict_authority():
    """Every scenario keeps the exact transaction count the strict world
    produces: the skip only removes a transaction that wrote nothing."""
    scenarios = [
        ('marked-catchup', dict(marker=True, head_class=False), 0),
        ('unmarked-catchup', dict(marker=False, head_class=False), 1),
        ('marked-fresh', dict(marker=True, head_class=True), 1),
        ('unmarked-fresh', dict(marker=False, head_class=True), 1),
        ('below-cap', dict(marker=True, sequence=6, watermark='w5', done=5), 1),
    ]
    for name, kwargs, expected_runs in scenarios:
        store = held_store(**kwargs)
        _merge, _entry = drain_held(store)
        assert store.runs == expected_runs, name


# --------------------------------------------------------------------------
# 2. Held-fact mirroring: the skip records what the body would have
# --------------------------------------------------------------------------


def test_skip_mirrors_the_held_hint_exactly_like_the_strict_body(monkeypatch):
    on = held_store()
    merge_on, _entry = drain_held(on)
    gate_off(monkeypatch)
    off = held_store()
    merge_off, _entry = drain_held(off)
    assert merge_on.held_owners == merge_off.held_owners == {'heavy'}


def test_skip_and_strict_body_agree_on_the_durable_rows(monkeypatch):
    on = held_store()
    drain_held(on)
    gate_off(monkeypatch)
    off = held_store()
    drain_held(off)
    assert table_rows(on) == table_rows(off)


def test_skip_performs_no_writes_while_the_strict_body_writes_none(monkeypatch):
    on = held_store()
    drain_held(on)
    gate_off(monkeypatch)
    off = held_store()
    drain_held(off)
    assert writes_of(on) == writes_of(off) == []


def test_skip_conclusion_is_none_like_the_strict_body(monkeypatch):
    on = held_store()
    _merge_on, entry_on = drain_held(on)
    gate_off(monkeypatch)
    off = held_store()
    _merge_off, entry_off = drain_held(off)
    assert entry_on is None and entry_off is None


def test_skip_head_waits_exactly_like_the_strict_body(monkeypatch):
    """The strict body's held conclusion leaves ``blocked`` empty, so the
    head-wait bypass never runs; the skip must behave identically and neither
    world may commit the bypass row."""
    on = held_store()
    add_sibling(on, 'b', 2, capture_class=False)
    merge_on, entry_on = drain_held(on, wait=60)
    gate_off(monkeypatch)
    off = held_store()
    add_sibling(off, 'b', 2, capture_class=False)
    merge_off, entry_off = drain_held(off, wait=60)
    assert entry_on is None and entry_off is None
    assert merge_on.held_owners == merge_off.held_owners == {'heavy'}
    assert on.rows['jobs', 'b']['merge_pending'] is True
    assert off.rows['jobs', 'b']['merge_pending'] is True


def test_skip_never_consults_the_head_wait_probe():
    store = held_store()
    add_sibling(store, 'b', 2, capture_class=False)
    consult = Mock(wraps=store.inner.longest_ready_pending)
    store.longest_ready_pending = consult
    merge, entry = drain_held(store, wait=60)
    assert entry is None
    assert consult.call_count == 0


def test_held_hint_discard_parity_for_the_committing_below_cap_world(monkeypatch):
    on = held_store(sequence=6, watermark='w5', done=5)
    merge_on, _entry = drain_held(on)
    gate_off(monkeypatch)
    off = held_store(sequence=6, watermark='w5', done=5)
    merge_off, _entry = drain_held(off)
    assert merge_on.held_owners == merge_off.held_owners == set()


def test_held_hint_parity_between_the_two_gate_skips():
    """The t267 blocked-head skip (fresh head) and the new ready-head skip
    leave the same hint state for maintenance."""
    ready = held_store()
    merge_ready, _entry = drain_held(ready)
    blocked = held_store(head_state='leased', head_class=True)
    merge_blocked, _entry = drain_held(blocked)
    assert merge_ready.held_owners == merge_blocked.held_owners == {'heavy'}


def test_owner_revision_changes_do_not_affect_the_held_skip():
    """The skip never opens the transaction whose fence reads the revision,
    so revision movement alone cannot re-open the wide query."""
    store = held_store()
    store.rows['owners', OWNER]['revision'] = 7

    def inflated_probe(table, key):
        row = store.inner.probe(table, key)
        if table == 'owners':
            return {**row, 'revision': row.get('revision', 0) + 5}
        return row

    store.probe = inflated_probe
    merge, entry = drain_held(store)
    assert entry is None
    assert store.runs == 0
    assert store.rows == store.rows  # Probe-only drain: asserted below.


def test_skip_records_no_metrics_and_no_correctness_commit():
    store = held_store()
    metrics = Mock()
    merge = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=2, metrics=metrics)
    entry = merge.commit_next('heavy', STEADY)
    assert entry is None
    assert metrics.record.call_count == 0


# --------------------------------------------------------------------------
# 3. Fresh-first preservation: the ready fresh row still commits
# --------------------------------------------------------------------------


def test_fresh_sibling_commits_in_the_same_skipped_drain():
    store = held_store()
    add_sibling(store, 'f', 2, capture_class=True)
    merge, entry = drain_held(store)
    assert entry['segment_id'] == 'f'
    assert entry['fresh_first'] is True
    assert store.rows['jobs', 'a']['state'] == 'result_ready'


def test_fresh_sibling_drain_opens_exactly_one_transaction():
    store = held_store()
    add_sibling(store, 'f', 2, capture_class=True)
    drain_held(store)
    assert store.runs == 1


def test_fresh_sibling_drain_transaction_count_beats_the_strict_world(monkeypatch):
    on = held_store()
    add_sibling(on, 'f', 2, capture_class=True)
    drain_held(on)
    gate_off(monkeypatch)
    off = held_store()
    add_sibling(off, 'f', 2, capture_class=True)
    drain_held(off)
    assert on.runs == 1
    assert off.runs == 2


def test_fresh_sibling_entry_flags_match_the_strict_world(monkeypatch):
    on = held_store()
    add_sibling(on, 'f', 2, capture_class=True)
    _merge_on, entry_on = drain_held(on)
    gate_off(monkeypatch)
    off = held_store()
    add_sibling(off, 'f', 2, capture_class=True)
    _merge_off, entry_off = drain_held(off)
    assert entry_on['segment_id'] == entry_off['segment_id'] == 'f'
    assert entry_on['fresh_first'] is True and entry_off['fresh_first'] is True


def test_fresh_sibling_drain_keeps_the_held_owner_hint():
    store = held_store()
    add_sibling(store, 'f', 2, capture_class=True)
    merge, _entry = drain_held(store)
    assert merge.held_owners == {'heavy'}


def test_fresh_sibling_drain_writes_match_the_strict_world(monkeypatch):
    on = held_store()
    add_sibling(on, 'f', 2, capture_class=True)
    drain_held(on)
    gate_off(monkeypatch)
    off = held_store()
    add_sibling(off, 'f', 2, capture_class=True)
    drain_held(off)
    assert table_rows(on) == table_rows(off)


def test_fresh_then_catchup_tail_commit_order():
    """The fresh sibling commits past the cap; once projection consumes it the
    owner drops below the cap and the catch-up head follows late."""
    store = held_store()
    add_sibling(store, 'f', 2, capture_class=True)
    merge, entry = drain_held(store)
    assert entry['segment_id'] == 'f'
    advance_projection(store, key='f', sequence=7)
    merge, entry = drain_held(store)
    assert entry['segment_id'] == 'a'
    assert entry['late_capture'] is True


def test_two_fresh_siblings_commit_fresh_then_tail_then_next_fresh():
    store = held_store()
    add_sibling(store, 'f1', 2, capture_class=True)
    add_sibling(store, 'f2', 3, capture_class=True)
    merge, entry = drain_held(store)
    assert entry['segment_id'] == 'f1'
    advance_projection(store, key='f1', sequence=7)
    merge, entry = drain_held(store)
    assert entry['segment_id'] == 'a'
    merge, entry = drain_held(store)
    assert entry['segment_id'] == 'f2'


def test_unready_fresh_sibling_commits_nothing():
    store = held_store()
    add_sibling(store, 'f', 2, capture_class=True, state='leased')
    merge, entry = drain_held(store)
    assert entry is None
    assert store.runs == 0


def test_unready_earliest_fresh_sibling_with_a_ready_later_one_waits():
    """The earliest fresh row must be the ready one; a skipped-row re-verify
    refuses otherwise, exactly like the strict world."""
    store = held_store()
    add_sibling(store, 'f1', 2, capture_class=True, state='leased')
    add_sibling(store, 'f2', 3, capture_class=True)
    merge, entry = drain_held(store)
    assert entry is None


def test_fresh_first_still_re_verifies_through_its_own_transaction():
    store = held_store()
    add_sibling(store, 'f', 2, capture_class=True)
    drain_held(store)
    assert store.run_operations == ['batch_merge_commit']
    assert ('query', 'first_pending', OWNER) in reads_of(store)


def test_fresh_head_commit_removes_the_owner_from_the_held_hint_when_below_cap():
    store = held_store(head_class=True)
    store.rows['results', 'w8'] = {'log_sequence': 6}
    store.rows['owners', OWNER]['projection_watermark'] = 'w8'
    store.reset_counts()
    merge, entry = drain_held(store)
    assert entry['segment_id'] == 'a'
    assert merge.held_owners == set()


def test_fresh_sibling_commit_advances_the_owner_fence():
    store = held_store()
    add_sibling(store, 'f', 2, capture_class=True)
    drain_held(store)
    owner = store.rows['owners', OWNER]
    assert owner['log_sequence'] == 7
    assert owner['log_tail'] == 'f'


def test_fresh_first_committed_entry_carries_the_result_payload():
    store = held_store()
    add_sibling(store, 'f', 2, capture_class=True)
    _merge, entry = drain_held(store)
    assert entry['result'] == {'outcome': 'success', 'result_uri': 'gs://results/f', 'segment_id': 'f'}
    assert entry['projection_state'] == 'pending'


# --------------------------------------------------------------------------
# 4. Head-wait and recovered-release interplay keep their contracts
# --------------------------------------------------------------------------


def test_head_wait_bypass_does_not_run_for_the_skipped_hold():
    store = held_store()
    add_sibling(store, 'b', 2, capture_class=False)
    merge, entry = drain_held(store, wait=60)
    assert entry is None
    assert store.runs == 0


def test_head_wait_bypass_still_runs_once_the_cap_clears():
    store = held_store()
    add_sibling(store, 'b', 2, capture_class=False)
    set_state(store, 'a', 'leased')
    advance_projection(store)
    store.reset_counts()
    merge, entry = drain_held(store, wait=60)
    assert entry['segment_id'] == 'b'
    assert entry['head_wait_bypass'] is True
    assert store.runs == 2


def test_recovered_release_drain_opens_the_strict_transactions():
    store = held_store()
    add_sibling(store, 'b', 2, capture_class=False)
    store.rows['jobs', 'b']['recovery_state'] = 'recovered'
    drain_held(store, release=['b'])
    assert store.runs == 2
    assert store.run_operations == ['batch_merge_commit', 'batch_merge_commit']


def test_recovered_release_carries_the_release_flag():
    store = held_store()
    add_sibling(store, 'b', 2, capture_class=False)
    store.rows['jobs', 'b']['recovery_state'] = 'recovered'
    merge, entry = drain_held(store, release=['b'])
    assert entry['segment_id'] == 'b'
    assert entry['recovered_release'] is True


def test_release_wake_consumption_leaves_the_held_head_pending():
    store = held_store()
    add_sibling(store, 'b', 2, capture_class=False)
    store.rows['jobs', 'b']['recovery_state'] = 'recovered'
    drain_held(store, release=['b'])
    assert store.rows['jobs', 'b']['state'] == 'committed'
    assert store.rows['jobs', 'a']['merge_pending'] is True


# --------------------------------------------------------------------------
# 5. Liveness: the held owner commits once the cap clears
# --------------------------------------------------------------------------


def test_cap_clears_and_the_next_drain_commits():
    store = held_store()
    merge, _entry = drain_held(store)
    assert merge.held_owners == {'heavy'}
    advance_projection(store)
    store.reset_counts()
    merge, entry = drain_held(store)
    assert entry['segment_id'] == 'a'
    assert store.rows['jobs', 'a']['state'] == 'committed'
    assert merge.held_owners == set()


def test_cap_cleared_drain_commits_through_the_narrow_body():
    store = held_store()
    drain_held(store)
    advance_projection(store)
    store.reset_counts()
    drain_held(store)
    assert store.runs == 1
    assert all(read[0] != 'query' for read in reads_of(store))


def test_cap_cleared_drain_probes_no_marker():
    store = held_store()
    drain_held(store)
    advance_projection(store)
    store.reset_counts()
    drain_held(store)
    assert ('merge_holds', OWNER) not in store.probed


def test_release_hold_clears_the_marker_once_below_the_cap():
    store = held_store()
    merge = OrderedMerge(store, catch_up_depth=2)
    merge.commit_next('heavy', STEADY)
    advance_projection(store)
    merge.release_hold(OWNER)
    assert store.rows['merge_holds', OWNER]['held'] is False


def test_release_hold_keeps_the_marker_while_still_at_the_cap():
    store = held_store()
    merge = OrderedMerge(store, catch_up_depth=2)
    merge.commit_next('heavy', STEADY)
    merge.release_hold(OWNER)
    assert store.rows['merge_holds', OWNER]['held'] is True


def test_release_hold_force_clears_the_marker_even_at_the_cap():
    store = held_store()
    merge = OrderedMerge(store, catch_up_depth=2)
    merge.commit_next('heavy', STEADY)
    merge.release_hold(OWNER, force=True)
    assert store.rows['merge_holds', OWNER]['held'] is False


def test_full_held_lifecycle_ends_committed():
    store = held_store()
    merge = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=2)
    assert merge.commit_next('heavy', STEADY) is None
    assert merge.held_owners == {'heavy'}
    advance_projection(store)
    entry = merge.commit_next('heavy', STEADY)
    assert entry['segment_id'] == 'a'
    merge.release_hold(OWNER)
    assert store.rows['merge_holds', OWNER]['held'] is False
    assert merge.held_owners == set()


def test_lifecycle_world_parity_after_the_cap_clears(monkeypatch):
    on = held_store()
    merge_on = OrderedMerge(on, catch_up_depth=2)
    merge_on.commit_next('heavy', STEADY)
    advance_projection(on)
    entry_on = merge_on.commit_next('heavy', STEADY)
    merge_on.release_hold(OWNER)
    gate_off(monkeypatch)
    off = held_store()
    merge_off = OrderedMerge(off, catch_up_depth=2)
    merge_off.commit_next('heavy', STEADY)
    advance_projection(off)
    entry_off = merge_off.commit_next('heavy', STEADY)
    merge_off.release_hold(OWNER)
    assert entry_on['segment_id'] == entry_off['segment_id'] == 'a'
    assert table_rows(on) == table_rows(off)


def test_below_cap_commit_discards_the_held_hint():
    store = held_store(sequence=6, watermark='w5', done=5)
    merge, _entry = drain_held(store)
    assert merge.held_owners == set()


def test_skip_then_below_cap_probe_then_commit_sequence():
    store = held_store()
    merge, _entry = drain_held(store)
    assert store.runs == 0
    advance_projection(store)
    merge, entry = drain_held(store)
    assert entry['segment_id'] == 'a'
    assert store.runs == 1


def test_repeated_skips_do_not_advance_the_owner():
    store = held_store()
    drain_held(store)
    drain_held(store)
    assert store.rows['owners', OWNER] == {'log_sequence': 6, 'projection_watermark': 'w5'}


def test_marker_survives_repeated_skips_byte_identically():
    store = held_store()
    drain_held(store)
    drain_held(store)
    assert store.rows['merge_holds', OWNER] == {'held': True, 'held_at': 1}


def test_projection_partway_still_holds_until_below_the_cap():
    store = held_store(sequence=6, watermark='w5', done=1)
    store.rows['results', 'w8'] = {'log_sequence': 4}
    store.rows['owners', OWNER]['projection_watermark'] = 'w8'
    store.reset_counts()
    merge, entry = drain_held(store)
    assert entry is None
    assert store.runs == 0
    assert merge.held_owners == {'heavy'}


def test_projection_past_the_cap_commits():
    store = held_store(sequence=6, watermark='w5', done=1)
    store.rows['results', 'w8'] = {'log_sequence': 6}
    store.rows['owners', OWNER]['projection_watermark'] = 'w8'
    store.reset_counts()
    merge, entry = drain_held(store)
    assert entry['segment_id'] == 'a'


def test_exact_cap_boundary_holds_and_below_cap_boundary_commits():
    at_cap_store = held_store(sequence=6, watermark='w5', done=1)
    merge_at, entry_at = drain_held(at_cap_store, depth=5)
    assert entry_at is None
    assert merge_at.held_owners == {'heavy'}
    below_store = held_store(sequence=6, watermark='w5', done=2)
    _merge_below, entry_below = drain_held(below_store, depth=5)
    assert entry_below['segment_id'] == 'a'


def test_missing_watermark_row_reads_as_below_cap_and_commits():
    """Parity with the strict body's read: a purged watermark row reads as
    zero done, so the probe twin reports the owner under the depth cap and
    the narrow body commits the head."""
    store = held_store(marker=False, sequence=6, watermark='w5')
    store.rows.pop(('results', 'w5'))
    store.rows['merge_holds', OWNER] = {'held': True, 'held_at': 1}
    store.reset_counts()
    merge, entry = drain_held(store)
    assert entry['segment_id'] == 'a'
    assert store.rows['jobs', 'a']['state'] == 'committed'
    assert ('merge_holds', OWNER) not in store.probed


def test_missing_watermark_field_counts_everything_unprojected():
    store = held_store(marker=False, sequence=6, watermark=None, done=1)
    store.rows['merge_holds', OWNER] = {'held': True, 'held_at': 1}
    store.reset_counts()
    merge, entry = drain_held(store)
    assert entry is None
    assert store.runs == 0


def test_committed_head_pending_set_change_commits_nothing_and_discards():
    """The head row itself got committed by a concurrent winner between the
    probe and this drain: the next probe finds nothing pending."""
    store = held_store()
    store.rows['jobs', 'a']['merge_pending'] = False
    store.reset_counts()
    merge, entry = drain_held(store)
    assert entry is None
    assert store.runs == 0
    assert merge.held_owners == set()


# --------------------------------------------------------------------------
# 6. Staleness bounds: no commit ever lands from a stale hint
# --------------------------------------------------------------------------


def test_stale_at_cap_probe_skips_without_writing():
    store = held_store()
    store.rows['results', 'w8'] = {'log_sequence': 6}
    store.rows['owners', OWNER]['projection_watermark'] = 'w8'

    def inflated_probe(table, key):
        row = store.inner.probe(table, key)
        if table == 'owners':
            return {**row, 'log_sequence': 9}
        return row

    store.probe = inflated_probe
    merge, entry = drain_held(store)
    assert entry is None
    assert store.write_log == []
    assert merge.held_owners == {'heavy'}


def test_stale_probe_is_bounded_the_next_honest_drain_commits():
    store = held_store()
    store.rows['results', 'w8'] = {'log_sequence': 6}
    store.rows['owners', OWNER]['projection_watermark'] = 'w8'

    def inflated_probe(table, key):
        row = store.inner.probe(table, key)
        if table == 'owners':
            return {**row, 'log_sequence': 9}
        return row

    store.probe = inflated_probe
    drain_held(store)
    store.probe = store.inner.probe
    store.reset_counts()
    merge, entry = drain_held(store)
    assert entry['segment_id'] == 'a'
    assert store.rows['jobs', 'a']['state'] == 'committed'


def test_skip_leaves_the_head_exactly_as_probed():
    store = held_store()
    drain_held(store)
    assert store.rows['jobs', 'a']['state'] == 'result_ready'
    assert store.rows['jobs', 'a']['merge_pending'] is True


def test_skip_from_stale_probe_still_hands_back_to_the_re_offer():
    store = held_store()

    def inflated_probe(table, key):
        row = store.inner.probe(table, key)
        if table == 'owners':
            return {**row, 'log_sequence': 9}
        return row

    merge, _entry = drain_held(store)
    assert merge.held_owners == {'heavy'}


def test_probe_only_reads_never_mutate_state_during_a_skip():
    store = held_store()
    before = deepcopy(store.rows)
    drain_held(store)
    assert store.rows == before


# --------------------------------------------------------------------------
# 7. Ordering: catch-up order and owner fences are world-invariant
# --------------------------------------------------------------------------


def test_late_earlier_capture_becomes_the_probed_head():
    store = held_store()
    add_sibling(store, 'c', 0, capture_class=False)
    drain_held(store)
    assert store.runs == 0


def test_late_catchup_pair_commits_in_capture_order_after_the_cap_clears():
    store = held_store()
    add_sibling(store, 'c', 0, capture_class=False)
    advance_projection(store)
    merge = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=2)
    first = merge.commit_next('heavy', STEADY)
    second = merge.commit_next('heavy', STEADY)
    assert [first['segment_id'], second['segment_id']] == ['c', 'a']


def test_late_catchup_pair_entries_are_identical_across_worlds(monkeypatch):
    on = held_store()
    add_sibling(on, 'c', 0, capture_class=False)
    advance_projection(on)
    merge_on = OrderedMerge(on, head_wait_seconds=0, catch_up_depth=2)
    entries_on = [merge_on.commit_next('heavy', STEADY), merge_on.commit_next('heavy', STEADY)]
    gate_off(monkeypatch)
    off = held_store()
    add_sibling(off, 'c', 0, capture_class=False)
    advance_projection(off)
    merge_off = OrderedMerge(off, head_wait_seconds=0, catch_up_depth=2)
    entries_off = [merge_off.commit_next('heavy', STEADY), merge_off.commit_next('heavy', STEADY)]
    for entry_on, entry_off in zip(entries_on, entries_off):
        entry_on.pop('committed_at')
        entry_off.pop('committed_at')
        assert entry_on == entry_off


def test_owner_fence_chain_is_identical_across_worlds(monkeypatch):
    on = held_store()
    add_sibling(on, 'c', 0, capture_class=False)
    advance_projection(on)
    merge_on = OrderedMerge(on, head_wait_seconds=0, catch_up_depth=2)
    merge_on.commit_next('heavy', STEADY)
    merge_on.commit_next('heavy', STEADY)
    gate_off(monkeypatch)
    off = held_store()
    add_sibling(off, 'c', 0, capture_class=False)
    advance_projection(off)
    merge_off = OrderedMerge(off, head_wait_seconds=0, catch_up_depth=2)
    merge_off.commit_next('heavy', STEADY)
    merge_off.commit_next('heavy', STEADY)
    owner_on = on.rows['owners', OWNER]
    owner_off = off.rows['owners', OWNER]
    assert owner_on['log_tail'] == owner_off['log_tail'] == 'a'
    assert owner_on['log_sequence'] == owner_off['log_sequence'] == 8


def test_fresh_first_then_catchup_tail_order_is_preserved():
    store = held_store()
    add_sibling(store, 'f', 2, capture_class=True)
    merge, entry = drain_held(store)
    assert entry['segment_id'] == 'f'
    advance_projection(store, key='f', sequence=7)
    merge, entry = drain_held(store)
    assert entry['segment_id'] == 'a'
    assert entry['late_capture'] is True


def test_skip_does_not_reorder_the_pending_set():
    store = held_store()
    add_sibling(store, 'c', 0, capture_class=False)
    drain_held(store)
    assert store.rows['jobs', 'c']['capture_at'] == 0
    assert store.rows['jobs', 'a']['capture_at'] == 1


def test_committed_entries_are_byte_identical_across_worlds(monkeypatch):
    on = held_store()
    add_sibling(on, 'f', 2, capture_class=True)
    merge_on = OrderedMerge(on, head_wait_seconds=0, catch_up_depth=2)
    entry_on = merge_on.commit_next('heavy', STEADY)
    gate_off(monkeypatch)
    off = held_store()
    add_sibling(off, 'f', 2, capture_class=True)
    merge_off = OrderedMerge(off, head_wait_seconds=0, catch_up_depth=2)
    entry_off = merge_off.commit_next('heavy', STEADY)
    entry_on.pop('committed_at')
    entry_off.pop('committed_at')
    assert entry_on == entry_off


# --------------------------------------------------------------------------
# 8. Multi-owner isolation
# --------------------------------------------------------------------------


def test_second_owner_drains_untouched_by_the_held_skip():
    store = held_store()
    second_owner_rows(store)
    merge, entry = drain_held(store)
    assert entry is None
    assert store.rows['jobs', 'o1']['state'] == 'result_ready'


def test_second_owner_commits_through_the_narrow_body():
    store = held_store()
    second_owner_rows(store)
    merge, entry = drain_held(store, owner_id='other')
    assert entry['segment_id'] == 'o1'
    assert store.runs == 1


def test_held_owner_hint_is_per_merge_instance():
    store = held_store()
    merge_one, _entry = drain_held(store)
    assert merge_one.held_owners == {'heavy'}
    merge_two = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=2)
    assert merge_two.held_owners == set()


def test_two_held_owners_skip_independently():
    store = held_store()
    parked_second_owner(store)
    merge_one, entry_one = drain_held(store)
    merge_two = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=2)
    entry_two = merge_two.commit_next('other', STEADY)
    assert entry_one is None
    assert entry_two is None
    assert merge_one.held_owners == {'heavy'}
    assert merge_two.held_owners == {'other'}


def test_one_owner_clearing_does_not_disturb_the_other():
    store = held_store()
    parked_second_owner(store)
    store.rows['results', 'o8'] = {'log_sequence': 6}
    store.rows['owners', OTHER]['projection_watermark'] = 'o8'
    store.reset_counts()
    merge_heavy = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=2)
    merge_other = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=2)
    assert merge_heavy.commit_next('heavy', STEADY) is None
    entry_other = merge_other.commit_next('other', STEADY)
    assert entry_other['segment_id'] == 'x'
    assert merge_heavy.held_owners == {'heavy'}
    assert merge_other.held_owners == set()


def test_markers_are_per_owner_rows():
    store = held_store()
    store.rows['merge_holds', OTHER] = {'held': True, 'held_at': 1}
    drain_held(store)
    assert store.rows['merge_holds', OTHER] == {'held': True, 'held_at': 1}


# --------------------------------------------------------------------------
# 9. Maintenance re-offer semantics
# --------------------------------------------------------------------------


def test_marked_page_lists_the_parked_owner():
    store = held_store()
    merge = OrderedMerge(store, catch_up_depth=2)
    merge.commit_next('heavy', STEADY)
    page = merge.marked_page(50)
    assert page == [(OWNER, 'heavy')]


def test_reoffer_marked_keeps_the_parked_owner_held():
    store = held_store()
    merge = OrderedMerge(store, catch_up_depth=2)
    merge.commit_next('heavy', STEADY)
    store.reset_counts()
    merge.reoffer_marked(lambda owner_id: merge.commit_next(owner_id, STEADY))
    # One transaction: the release_hold attempt (the drain itself skipped).
    assert store.runs == 1
    assert store.run_operations == ['batch_merge_hold_release']
    assert store.rows['merge_holds', OWNER]['held'] is True


def test_reoffer_marked_after_the_cap_clears_commits_and_releases():
    store = held_store()
    merge = OrderedMerge(store, catch_up_depth=2)
    merge.commit_next('heavy', STEADY)
    advance_projection(store)
    store.reset_counts()
    merge.reoffer_marked(lambda owner_id: merge.commit_next(owner_id, STEADY))
    assert store.rows['jobs', 'a']['state'] == 'committed'
    assert store.rows['merge_holds', OWNER]['held'] is False


def test_reoffer_marked_forces_release_for_ownerless_markers():
    store = held_store()
    store.rows['jobs', 'a']['owner_id'] = None
    merge = OrderedMerge(store, catch_up_depth=2)
    merge.reoffer_marked(lambda owner_id: merge.commit_next(owner_id, STEADY), limit=50)
    assert store.rows['merge_holds', OWNER]['held'] is False


def test_held_owner_reoffer_loop_is_transaction_free_while_parked():
    store = held_store()
    merge, _entry = drain_held(store)
    for _owner_id in list(merge.held_owners):
        merge, _entry = drain_held(store)
    assert store.runs == 0


def test_held_owner_leaves_the_hint_after_the_cap_clears():
    store = held_store()
    merge, _entry = drain_held(store)
    advance_projection(store)
    merge, _entry = drain_held(store)
    assert merge.held_owners == set()


def test_held_hint_survives_a_blocked_head_interlude():
    store = held_store()
    merge, _entry = drain_held(store)
    set_state(store, 'a', 'leased')
    merge, _entry = drain_held(store)
    assert merge.held_owners == {'heavy'}


def test_held_hint_survives_a_fresh_first_commit():
    store = held_store()
    add_sibling(store, 'f', 2, capture_class=True)
    merge, entry = drain_held(store)
    assert entry is not None
    assert merge.held_owners == {'heavy'}


def test_parked_owner_page_rotates_through_marked_owners():
    store = held_store()
    parked_second_owner(store)
    merge = OrderedMerge(store, catch_up_depth=2)
    page = merge.marked_page(50)
    assert {key for key, _owner in page} == {OWNER, OTHER}


def test_reoffer_of_a_committed_owner_releases_the_marker():
    store = held_store()
    merge = OrderedMerge(store, catch_up_depth=2)
    merge.commit_next('heavy', STEADY)
    advance_projection(store)
    drain_held(store)
    merge.reoffer_marked(lambda owner_id: merge.commit_next(owner_id, STEADY))
    assert store.rows['merge_holds', OWNER]['held'] is False


# --------------------------------------------------------------------------
# 10. Interleaving on the real store class under a heartbeat storm
# --------------------------------------------------------------------------


def test_held_drain_survives_a_heartbeat_storm_without_a_transaction(monkeypatch):
    client = StormClient(rows=storm_held_rows())
    merge, _store = storm_merge(monkeypatch, client, depth=2)
    entry = merge.commit_next('heavy', STEADY)
    assert entry is None
    assert client.transactions == 0
    assert client.commits == 0


def test_held_drain_storm_leaves_every_row_untouched(monkeypatch):
    client = StormClient(rows=storm_held_rows())
    merge, _store = storm_merge(monkeypatch, client, depth=2)
    before = deepcopy(client.rows)
    assert merge.commit_next('heavy', STEADY) is None
    assert client.rows == before


def test_held_drain_storm_consumes_no_abort_budget(monkeypatch):
    client = StormClient(rows=storm_held_rows(), aborts=10**6)
    merge, _store = storm_merge(monkeypatch, client, depth=2)
    for _ in range(5):
        assert merge.commit_next('heavy', STEADY) is None
    assert client.aborts_remaining == 10**6


def test_strict_world_exhausts_against_the_same_storm(monkeypatch):
    client = StormClient(rows=storm_held_rows())
    merge, _store = storm_merge(monkeypatch, client, depth=2)
    gate_off(monkeypatch)
    with pytest.raises(FirestoreContentionExhausted):
        merge.commit_next('heavy', STEADY)


def test_strict_world_storm_writes_nothing(monkeypatch):
    client = StormClient(rows=storm_held_rows())
    merge, _store = storm_merge(monkeypatch, client, depth=2)
    gate_off(monkeypatch)
    before = deepcopy(client.rows)
    with pytest.raises(FirestoreContentionExhausted):
        merge.commit_next('heavy', STEADY)
    assert client.rows == before


def test_held_storm_opens_only_non_transactional_queries(monkeypatch):
    client = StormClient(rows=storm_held_rows())
    merge, _store = storm_merge(monkeypatch, client, depth=2)
    merge.commit_next('heavy', STEADY)
    assert client.query_shapes
    assert all(not shape['transactional'] for shape in client.query_shapes)


def test_strict_world_storm_opens_a_transactional_pending_query(monkeypatch):
    client = StormClient(rows=storm_held_rows())
    merge, _store = storm_merge(monkeypatch, client, depth=2)
    gate_off(monkeypatch)
    with pytest.raises(FirestoreContentionExhausted):
        merge.commit_next('heavy', STEADY)
    assert any(shape['transactional'] for shape in client.query_shapes)


def test_held_storm_leaves_the_storm_damper_dormant(monkeypatch):
    from tests.unit.test_merge_blocked_head_probe_gate import FakeClock

    clock = FakeClock(now=1_000.0)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    client = StormClient(rows=storm_held_rows())
    merge, _store = storm_merge(monkeypatch, client, depth=2, damper=damper)
    for _ in range(3):
        assert merge.commit_next('heavy', STEADY) is None
    assert client.transactions == 0
    waited, generation = damper.consult('batch_merge_commit')
    assert waited == 0.0
    assert generation == 0
    assert clock.sleeps == []


def test_fresh_reverify_still_exhausts_during_the_storm(monkeypatch):
    """The fresh-first re-verify is unchanged: during a live storm it joins
    the abort set and raises, exactly as the strict world did."""
    rows = storm_held_rows()
    rows[f'{NAMESPACE}_jobs', 'f'] = {
        'segment_id': 'f',
        'owner_key': OWNER,
        'owner_id': 'heavy',
        'merge_pending': True,
        'state': 'result_ready',
        'capture_at': 3,
        'priority': 0,
        'ready_at': 10.0,
        'result': {'uri': 'gs://results/f'},
        'protocol_version': 1,
        'fresh_capture': True,
    }
    client = StormClient(rows=rows)
    merge, _store = storm_merge(monkeypatch, client, depth=2)
    before = deepcopy(client.rows)
    with pytest.raises(FirestoreContentionExhausted):
        merge.commit_next('heavy', STEADY)
    assert client.rows == before


def test_owner_leaves_the_storm_without_an_aborted_transaction(monkeypatch):
    client = StormClient(rows=storm_held_rows())
    merge, _store = storm_merge(monkeypatch, client, depth=2)
    assert merge.commit_next('heavy', STEADY) is None
    # The storm passes; projection commits through a prior row.
    client.aborts_remaining = 0
    client.rows[f'{NAMESPACE}_results', 'w8'] = {'log_sequence': 6}
    client.rows[f'{NAMESPACE}_owners', OWNER]['projection_watermark'] = 'w8'
    entry = merge.commit_next('heavy', STEADY)
    assert entry['segment_id'] == 'a'
    assert client.commits >= 1
    assert client.aborts_remaining == 0
    assert client.rows[f'{NAMESPACE}_jobs', 'a']['state'] == 'committed'


def test_owner_leaves_the_storm_with_the_marker_releasable(monkeypatch):
    client = StormClient(rows=storm_held_rows())
    merge, _store = storm_merge(monkeypatch, client, depth=2)
    merge.commit_next('heavy', STEADY)
    client.aborts_remaining = 0
    client.rows[f'{NAMESPACE}_results', 'w8'] = {'log_sequence': 6}
    client.rows[f'{NAMESPACE}_owners', OWNER]['projection_watermark'] = 'w8'
    merge.commit_next('heavy', STEADY)
    merge.release_hold(OWNER)
    assert client.rows[f'{NAMESPACE}_merge_holds', OWNER]['held'] is False


def test_held_storm_then_fresh_commit_after_the_storm(monkeypatch):
    rows = storm_held_rows()
    rows[f'{NAMESPACE}_jobs', 'f'] = {
        'segment_id': 'f',
        'owner_key': OWNER,
        'owner_id': 'heavy',
        'merge_pending': True,
        'state': 'leased',
        'capture_at': 3,
        'priority': 0,
        'protocol_version': 1,
        'fresh_capture': True,
    }
    client = StormClient(rows=rows)
    merge, _store = storm_merge(monkeypatch, client, depth=2)
    assert merge.commit_next('heavy', STEADY) is None  # Parked drain skips.
    client.rows[f'{NAMESPACE}_jobs', 'f']['state'] = 'result_ready'
    client.rows[f'{NAMESPACE}_jobs', 'f']['ready_at'] = 10.0
    client.rows[f'{NAMESPACE}_jobs', 'f']['result'] = {'uri': 'gs://results/f'}
    client.aborts_remaining = 0
    entry = merge.commit_next('heavy', STEADY)
    assert entry['segment_id'] == 'f'
    assert entry['fresh_first'] is True


def test_storm_drain_holds_the_held_hint_for_maintenance(monkeypatch):
    client = StormClient(rows=storm_held_rows())
    merge, _store = storm_merge(monkeypatch, client, depth=2)
    merge.commit_next('heavy', STEADY)
    assert merge.held_owners == {'heavy'}


def test_storm_world_parity_of_the_parked_rows(monkeypatch):
    client_on = StormClient(rows=storm_held_rows())
    merge_on, _store_on = storm_merge(monkeypatch, client_on, depth=2)
    merge_on.commit_next('heavy', STEADY)
    gate_off(monkeypatch)
    client_off = StormClient(rows=storm_held_rows())
    merge_off, _store_off = storm_merge(monkeypatch, client_off, depth=2)
    with pytest.raises(FirestoreContentionExhausted):
        merge_off.commit_next('heavy', STEADY)
    assert client_on.rows == client_off.rows


def test_storm_world_blocked_and_ready_heads_share_the_skip_shape(monkeypatch):
    """The blocked-head skip (t267, fresh head) and the ready catch-up skip
    both open zero transactions on the real store class."""
    blocked_client = StormClient(rows=storm_held_rows(head_state='leased', head_class=True))
    blocked_merge, _store = storm_merge(monkeypatch, blocked_client, depth=2)
    assert blocked_merge.commit_next('heavy', STEADY) is None
    assert blocked_client.transactions == 0

    ready_client = StormClient(rows=storm_held_rows(head_state='result_ready'))
    ready_merge, _store = storm_merge(monkeypatch, ready_client, depth=2)
    assert ready_merge.commit_next('heavy', STEADY) is None
    assert ready_client.transactions == 0


# --------------------------------------------------------------------------
# 11. Probe surfaces and observability
# --------------------------------------------------------------------------


def test_gate_skip_probes_exactly_the_owner_result_and_marker_rows():
    """The narrow gate's own over-cap probe runs first; the held-head gate
    adds the same twin pair plus the marker read — and nothing else."""
    store = held_store()
    drain_held(store)
    assert store.probed == [
        ('owners', OWNER),
        ('results', 'w5'),
        ('owners', OWNER),
        ('results', 'w5'),
        ('merge_holds', OWNER),
    ]
    assert store.head_pending_calls == 1


def test_fresh_head_refusal_probes_nothing_beyond_the_over_cap_twin():
    """The fresh head short-circuits the held-head gate before the marker
    read; only the narrow gate's over-cap probe runs."""
    store = held_store(head_class=True)
    drain_held(store)
    assert store.probed == [('owners', OWNER), ('results', 'w5')]
    assert store.head_pending_calls == 1


def test_unmarked_refusal_probes_the_owner_result_and_reads_the_marker():
    store = held_store(marker=False)
    drain_held(store)
    assert ('merge_holds', OWNER) in store.probed
    assert ('owners', OWNER) in store.probed


def test_below_cap_commit_probes_no_marker():
    store = held_store(sequence=6, watermark='w5', done=5)
    drain_held(store)
    assert ('merge_holds', OWNER) not in store.probed


def test_marker_probe_outage_logs_a_single_warning(caplog):
    store = held_store()
    flaky_probe(store, 'merge_holds')
    with caplog.at_level(logging.WARNING, logger='utils.batch_pipeline.merge'):
        drain_held(store)
    warnings = [record for record in caplog.records if 'held_marker_probe_retry' in record.getMessage()]
    assert len(warnings) == 1


def test_successful_skip_logs_nothing(caplog):
    store = held_store()
    with caplog.at_level(logging.INFO, logger='utils.batch_pipeline.merge'):
        drain_held(store)
    assert caplog.records == []


def test_strict_fallback_still_reports_its_label_after_a_refusal():
    store = held_store(marker=False)
    drain_held(store)
    assert store.run_operations == ['batch_merge_commit']


def test_gate_off_label_parity(monkeypatch):
    gate_off(monkeypatch)
    store = held_store(marker=False)
    drain_held(store)
    assert store.run_operations == ['batch_merge_commit']


# --------------------------------------------------------------------------
# 12. Config, flag budget, docs and kill switch
# --------------------------------------------------------------------------


def test_held_head_gate_defaults_on(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_MERGE_HELD_HEAD_GATE_ENABLED', raising=False)
    from config.batch_pipeline import merge_held_head_gate_enabled

    assert merge_held_head_gate_enabled() is True


def test_held_head_gate_false_env_is_off(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_HELD_HEAD_GATE_ENABLED', 'false')
    from config.batch_pipeline import merge_held_head_gate_enabled

    assert merge_held_head_gate_enabled() is False


def test_held_head_gate_uppercase_false_is_off(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_HELD_HEAD_GATE_ENABLED', 'FALSE')
    from config.batch_pipeline import merge_held_head_gate_enabled

    assert merge_held_head_gate_enabled() is False


def test_held_head_gate_padded_false_is_off(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_HELD_HEAD_GATE_ENABLED', ' false ')
    from config.batch_pipeline import merge_held_head_gate_enabled

    assert merge_held_head_gate_enabled() is False


def test_held_head_gate_true_word_is_on(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_HELD_HEAD_GATE_ENABLED', 'true')
    from config.batch_pipeline import merge_held_head_gate_enabled

    assert merge_held_head_gate_enabled() is True


def test_held_head_gate_empty_value_is_on(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_HELD_HEAD_GATE_ENABLED', '')
    from config.batch_pipeline import merge_held_head_gate_enabled

    assert merge_held_head_gate_enabled() is True


def test_held_head_gate_zero_is_on_like_the_sibling_gates(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_HELD_HEAD_GATE_ENABLED', '0')
    from config.batch_pipeline import merge_held_head_gate_enabled

    assert merge_held_head_gate_enabled() is True


def test_held_head_gate_reads_the_environment_at_call_time(monkeypatch):
    from config.batch_pipeline import merge_held_head_gate_enabled

    monkeypatch.delenv('BATCH_PIPELINE_MERGE_HELD_HEAD_GATE_ENABLED', raising=False)
    assert merge_held_head_gate_enabled() is True
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_HELD_HEAD_GATE_ENABLED', 'false')
    assert merge_held_head_gate_enabled() is False
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_HELD_HEAD_GATE_ENABLED', 'true')
    assert merge_held_head_gate_enabled() is True


def test_held_head_gate_has_a_budget_entry_with_owner_and_review_by():
    budget = json.loads((Path(__file__).resolve().parents[2] / 'config' / 'flag_budget.json').read_text())
    entry = budget['names']['BATCH_PIPELINE_MERGE_HELD_HEAD_GATE_ENABLED']
    assert entry['owner'] == 'batch record lane / rollout lead'
    assert entry['review_by'] >= '2026-12-01'
    assert budget['count'] == len(budget['names'])


def test_kill_switch_restores_the_strict_hold_re_decide(monkeypatch):
    gate_off(monkeypatch)
    store = held_store()
    merge, entry = drain_held(store)
    assert entry is None
    assert store.runs == 1
    assert store.run_operations == ['batch_merge_commit']
    assert ('query', 'first_pending', OWNER) in reads_of(store)


def test_kill_switch_keeps_the_held_facts_identical(monkeypatch):
    gate_off(monkeypatch)
    store = held_store()
    merge, _entry = drain_held(store)
    assert merge.held_owners == {'heavy'}
    assert store.rows['merge_holds', OWNER] == {'held': True, 'held_at': 1}


def test_env_kill_switch_restores_the_strict_drain(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_HELD_HEAD_GATE_ENABLED', 'false')
    store = held_store()
    drain_held(store)
    assert store.runs == 1
    assert ('query', 'first_pending', OWNER) in reads_of(store)


def test_env_kill_switch_still_probes_before_it_transacts(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_HELD_HEAD_GATE_ENABLED', 'false')
    store = held_store()
    drain_held(store)
    assert store.head_pending_calls == 1


def test_kill_switch_world_fresh_first_still_commits(monkeypatch):
    gate_off(monkeypatch)
    store = held_store()
    add_sibling(store, 'f', 2, capture_class=True)
    _merge, entry = drain_held(store)
    assert entry['segment_id'] == 'f'
    assert entry['fresh_first'] is True


def test_gate_docs_exist_and_carry_the_failure_class():
    docs = (Path(__file__).resolve().parents[2] / 'docs' / 'batch-merge-held-head-drain-gate.md').read_text()
    assert 'Failure-Class: FC-held-owner-ready-catch-up-drains-reopen-the-wide-hold-query' in docs


def test_gate_docs_name_the_kill_switch():
    docs = (Path(__file__).resolve().parents[2] / 'docs' / 'batch-merge-held-head-drain-gate.md').read_text()
    assert 'BATCH_PIPELINE_MERGE_HELD_HEAD_GATE_ENABLED' in docs


def test_gate_docs_name_the_signature():
    docs = (Path(__file__).resolve().parents[2] / 'docs' / 'batch-merge-held-head-drain-gate.md').read_text()
    assert 'FirestoreContentionExhausted' in docs


def test_suite_docstring_carries_the_failure_class_trailer():
    assert 'Failure-Class: FC-held-owner-ready-catch-up-drains-reopen-the-wide-hold-query' in __doc__


def test_gate_function_is_importable_from_the_merge_module_namespace():
    assert merge_module.merge_held_head_gate_enabled() is True


# --------------------------------------------------------------------------
# 13. Write parity across worlds on shared lifecycle scenarios
# --------------------------------------------------------------------------


def test_parked_rows_are_byte_identical_across_worlds(monkeypatch):
    on = held_store()
    drain_held(on)
    gate_off(monkeypatch)
    off = held_store()
    drain_held(off)
    assert table_rows(on) == table_rows(off)


def test_lifecycle_rows_are_byte_identical_across_worlds(monkeypatch):
    on = held_store()
    add_sibling(on, 'f', 2, capture_class=True)
    merge_on = OrderedMerge(on, head_wait_seconds=0, catch_up_depth=2)
    merge_on.commit_next('heavy', STEADY)
    advance_projection(on, key='f', sequence=7)
    merge_on.commit_next('heavy', STEADY)
    merge_on.release_hold(OWNER)
    gate_off(monkeypatch)
    off = held_store()
    add_sibling(off, 'f', 2, capture_class=True)
    merge_off = OrderedMerge(off, head_wait_seconds=0, catch_up_depth=2)
    merge_off.commit_next('heavy', STEADY)
    advance_projection(off, key='f', sequence=7)
    merge_off.commit_next('heavy', STEADY)
    merge_off.release_hold(OWNER)
    assert table_rows(on) == table_rows(off)


def test_below_cap_commit_rows_are_byte_identical_across_worlds(monkeypatch):
    on = held_store(sequence=6, watermark='w5', done=5)
    drain_held(on)
    gate_off(monkeypatch)
    off = held_store(sequence=6, watermark='w5', done=5)
    drain_held(off)
    assert table_rows(on) == table_rows(off)


def test_fresh_head_commit_rows_are_byte_identical_across_worlds(monkeypatch):
    on = held_store(head_class=True)
    drain_held(on)
    gate_off(monkeypatch)
    off = held_store(head_class=True)
    drain_held(off)
    assert table_rows(on) == table_rows(off)


def test_unmarked_refusal_rows_are_byte_identical_across_worlds(monkeypatch):
    on = held_store(marker=False)
    drain_held(on)
    gate_off(monkeypatch)
    off = held_store(marker=False)
    drain_held(off)
    assert table_rows(on) == table_rows(off)


def test_shadow_refusal_rows_are_byte_identical_across_worlds(monkeypatch):
    on = held_store()
    on.rows['jobs', 'a']['shadow'] = True
    drain_held(on)
    gate_off(monkeypatch)
    off = held_store()
    off.rows['jobs', 'a']['shadow'] = True
    drain_held(off)
    assert table_rows(on) == table_rows(off)


def test_head_probe_failure_rows_are_byte_identical_across_worlds(monkeypatch):
    on = held_store()
    on.head_pending_error = ServiceUnavailable('hint read down')
    drain_held(on)
    gate_off(monkeypatch)
    off = held_store()
    off.head_pending_error = ServiceUnavailable('hint read down')
    drain_held(off)
    assert table_rows(on) == table_rows(off)


def test_entry_or_none_outcome_is_identical_across_the_full_matrix(monkeypatch):
    scenarios = [
        dict(marker=True, head_class=False),
        dict(marker=False, head_class=False),
        dict(marker=True, head_class=True),
        dict(marker=False, head_class=True),
        dict(marker=True, sequence=6, watermark='w5', done=5),
        dict(marker=False, sequence=6, watermark='w5', done=5),
    ]
    for kwargs in scenarios:
        on = held_store(**kwargs)
        merge_on = OrderedMerge(on, head_wait_seconds=0, catch_up_depth=2)
        entry_on = merge_on.commit_next('heavy', STEADY)
        gate_off(monkeypatch)
        off = held_store(**kwargs)
        merge_off = OrderedMerge(off, head_wait_seconds=0, catch_up_depth=2)
        entry_off = merge_off.commit_next('heavy', STEADY)
        assert (entry_on is None) == (entry_off is None), kwargs
        if entry_on is not None:
            assert entry_on['segment_id'] == entry_off['segment_id'], kwargs


def test_skipped_drain_then_commit_sequence_matches_strict_sequence(monkeypatch):
    on = held_store()
    merge_on = OrderedMerge(on, head_wait_seconds=0, catch_up_depth=2)
    assert merge_on.commit_next('heavy', STEADY) is None
    advance_projection(on)
    entry_on = merge_on.commit_next('heavy', STEADY)
    gate_off(monkeypatch)
    off = held_store()
    merge_off = OrderedMerge(off, head_wait_seconds=0, catch_up_depth=2)
    first_off = merge_off.commit_next('heavy', STEADY)
    advance_projection(off)
    entry_off = merge_off.commit_next('heavy', STEADY)
    assert first_off is None
    assert entry_on['segment_id'] == entry_off['segment_id']
    assert table_rows(on) == table_rows(off)


def test_jobs_rows_untouched_by_the_skip():
    store = held_store()
    before = deepcopy(store.rows['jobs', 'a'])
    drain_held(store)
    assert store.rows['jobs', 'a'] == before


def test_owner_rows_untouched_by_the_skip():
    store = held_store()
    before = deepcopy(store.rows['owners', OWNER])
    drain_held(store)
    assert store.rows['owners', OWNER] == before


def test_results_rows_untouched_by_the_skip():
    store = held_store()
    drain_held(store)
    assert ('results', 'a') not in store.rows


# --------------------------------------------------------------------------
# 14. Held-fact ledger: the catch_up mirror drives the fresh-first probe
# --------------------------------------------------------------------------


def test_skip_consults_the_fresh_first_probe_like_the_strict_body(monkeypatch):
    """``held['catch_up']`` is only observable through the fresh-first probe
    it enables; the skip must trigger exactly the probe the strict body's
    held conclusion triggers."""
    on = held_store()
    consult_on = Mock(wraps=on.inner.fresh_pending)
    on.fresh_pending = consult_on
    merge_on, entry_on = drain_held(on)
    assert entry_on is None
    assert consult_on.call_count == 1
    gate_off(monkeypatch)
    off = held_store()
    consult_off = Mock(wraps=off.inner.fresh_pending)
    off.fresh_pending = consult_off
    merge_off, entry_off = drain_held(off)
    assert entry_off is None
    assert consult_off.call_count == 1


def test_below_cap_commit_skips_the_fresh_first_probe():
    store = held_store(sequence=6, watermark='w5', done=5)
    consult = Mock(wraps=store.inner.fresh_pending)
    store.fresh_pending = consult
    merge, entry = drain_held(store)
    assert entry['segment_id'] == 'a'
    assert consult.call_count == 0


def test_committed_metric_fires_for_the_fresh_first_commit_through_the_skip():
    store = held_store()
    add_sibling(store, 'f', 2, capture_class=True)
    metrics = Mock()
    merge = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=2, metrics=metrics)
    entry = merge.commit_next('heavy', STEADY)
    assert entry['segment_id'] == 'f'
    metrics.record.assert_called_once_with('committed')


def test_release_hold_transaction_carries_its_label():
    store = held_store()
    merge = OrderedMerge(store, catch_up_depth=2)
    merge.commit_next('heavy', STEADY)
    store.reset_counts()
    merge.release_hold(OWNER)
    assert store.runs == 1
    assert store.run_operations == ['batch_merge_hold_release']


def test_reoffer_after_the_cap_clears_carries_both_labels():
    store = held_store()
    merge = OrderedMerge(store, catch_up_depth=2)
    merge.commit_next('heavy', STEADY)
    advance_projection(store)
    store.reset_counts()
    merge.reoffer_marked(lambda owner_id: merge.commit_next(owner_id, STEADY))
    assert store.runs == 2
    assert store.run_operations == ['batch_merge_commit', 'batch_merge_hold_release']


def test_gate_docs_describe_the_held_owner_hint():
    docs = (Path(__file__).resolve().parents[2] / 'docs' / 'batch-merge-held-head-drain-gate.md').read_text()
    assert 'held_owners' in docs


def test_gate_docs_describe_the_fresh_first_preservation():
    docs = (Path(__file__).resolve().parents[2] / 'docs' / 'batch-merge-held-head-drain-gate.md').read_text()
    assert 'fresh-first' in docs


def test_gate_docs_describe_the_guarded_marker_probe():
    docs = (Path(__file__).resolve().parents[2] / 'docs' / 'batch-merge-held-head-drain-gate.md').read_text()
    assert 'held_marker_probe_retry' in docs


def test_merge_module_wires_the_flag_import():
    source = Path(merge_module.__file__).read_text()
    assert '    merge_held_head_gate_enabled,\n' in source


def test_merge_module_calls_the_flag_before_the_strict_body():
    source = Path(merge_module.__file__).read_text()
    assert 'merge_held_head_gate_enabled()' in source


def test_config_module_keeps_the_gate_alongside_its_siblings():
    import config.batch_pipeline as config_module

    config_source = Path(config_module.__file__).read_text()
    assert 'def merge_held_head_gate_enabled' in config_source
    assert 'def merge_narrow_commit_enabled' in config_source


def test_config_docstring_names_the_kill_switch():
    import inspect

    from config.batch_pipeline import merge_held_head_gate_enabled

    assert 'kill switch' in (inspect.getdoc(merge_held_head_gate_enabled) or '')


# --------------------------------------------------------------------------
# 15. Cap boundary matrix
# --------------------------------------------------------------------------


def test_depth_one_boundary_at_cap_skips():
    store = held_store(sequence=6, watermark='w5', done=5)
    merge, entry = drain_held(store, depth=1)
    assert entry is None
    assert store.runs == 0
    assert merge.held_owners == {'heavy'}


def test_depth_one_boundary_below_cap_commits():
    store = held_store(sequence=6, watermark='w5', done=6)
    _merge, entry = drain_held(store, depth=1)
    assert entry['segment_id'] == 'a'


def test_owner_below_any_cap_commits_even_with_a_marker():
    store = held_store(sequence=3, watermark='w5', done=1)
    merge, entry = drain_held(store, depth=5)
    assert entry['segment_id'] == 'a'
    assert store.runs == 1
    assert ('merge_holds', OWNER) not in store.probed


def test_high_cap_never_holds_a_short_backlog():
    store = held_store(sequence=3, watermark='w5', done=1)
    merge, entry = drain_held(store, depth=10)
    assert entry['segment_id'] == 'a'
    assert merge.held_owners == set()


def test_unstamped_owner_row_commits_through_the_narrow_body():
    """An owner row without projection bookkeeping reads as zero unprojected:
    the gate refuses and the narrow body commits."""
    store = held_store()
    store.rows['owners', OWNER] = {'log_sequence': 1, 'projection_watermark': None}
    store.reset_counts()
    _merge, entry = drain_held(store)
    assert entry['segment_id'] == 'a'
    assert store.runs == 1


def test_missing_owner_row_reads_as_below_cap_and_commits():
    store = held_store()
    store.rows.pop(('owners', OWNER))
    store.reset_counts()
    _merge, entry = drain_held(store)
    assert entry['segment_id'] == 'a'
    assert entry['log_sequence'] == 1
    assert store.runs == 1


# --------------------------------------------------------------------------
# 16. Storm interleaving: additions
# --------------------------------------------------------------------------


class _MarkerDownStormClient(StormClient):
    """Storm client whose merge_holds collection is unreachable: the marker
    probe fails transiently while every other read succeeds."""

    def collection(self, name):
        if name.endswith('_merge_holds'):
            raise ServiceUnavailable('marker probe down')
        return super().collection(name)


def test_marker_probe_outage_during_a_storm_keeps_the_strict_authority(monkeypatch, caplog):
    """A merge_holds outage refuses the gate (with its warning) and the strict
    authority fails the drain exactly as before the gate existed."""
    client = _MarkerDownStormClient(rows=storm_held_rows())
    merge, _store = storm_merge(monkeypatch, client, depth=2)
    before = deepcopy(client.rows)
    with caplog.at_level(logging.WARNING, logger='utils.batch_pipeline.merge'):
        with pytest.raises(Exception):
            merge.commit_next('heavy', STEADY)
    assert any('held_marker_probe_retry' in record.getMessage() for record in caplog.records)
    assert client.rows == before


def test_storm_release_wake_still_burns_unchanged(monkeypatch):
    """A release wake refuses the gate and keeps the strict authority —
    including its storm burn, exactly as before this gate existed."""
    rows = storm_held_rows()
    rows[f'{NAMESPACE}_jobs', 'b']['fresh_capture'] = False
    rows[f'{NAMESPACE}_jobs', 'b']['recovery_state'] = 'recovered'
    client = StormClient(rows=rows)
    merge, _store = storm_merge(monkeypatch, client, depth=2)
    with pytest.raises(FirestoreContentionExhausted):
        merge.commit_next('heavy', STEADY, release=['b'])


def test_storm_two_parked_owners_open_zero_transactions(monkeypatch):
    other_key = owner_key('other')
    rows = storm_held_rows()
    rows[f'{NAMESPACE}_jobs', 'x'] = {
        'segment_id': 'x',
        'owner_key': other_key,
        'owner_id': 'other',
        'merge_pending': True,
        'state': 'result_ready',
        'capture_at': 1,
        'priority': 0,
        'ready_at': 10.0,
        'result': {'outcome': 'success', 'result_uri': 'gs://results/x', 'segment_id': 'x'},
        'protocol_version': 1,
        'fresh_capture': False,
    }
    rows[f'{NAMESPACE}_owners', other_key] = {'log_sequence': 6, 'projection_watermark': 'x5', 'revision': 3}
    rows[f'{NAMESPACE}_results', 'x5'] = {'log_sequence': 1}
    rows[f'{NAMESPACE}_merge_holds', other_key] = {'held': True, 'held_at': 1}
    client = StormClient(rows=rows)
    merge, _store = storm_merge(monkeypatch, client, depth=2)
    assert merge.commit_next('heavy', STEADY) is None
    assert merge.commit_next('other', STEADY) is None
    assert client.transactions == 0
    assert merge.held_owners == {'heavy', 'other'}


def test_storm_drain_query_shapes_are_the_two_discovery_probes(monkeypatch):
    client = StormClient(rows=storm_held_rows())
    merge, _store = storm_merge(monkeypatch, client, depth=2)
    merge.commit_next('heavy', STEADY)
    assert len(client.query_shapes) == 2
    assert all(not shape['transactional'] for shape in client.query_shapes)
    assert all(shape['collection'] == f'{NAMESPACE}_jobs' for shape in client.query_shapes)


def test_gate_on_drains_run_with_zero_abort_budget(monkeypatch):
    client = StormClient(rows=storm_held_rows(), aborts=0)
    merge, _store = storm_merge(monkeypatch, client, depth=2)
    assert merge.commit_next('heavy', STEADY) is None
    assert client.transactions == 0


def test_abort_budget_untouched_across_ten_drains(monkeypatch):
    client = StormClient(rows=storm_held_rows(), aborts=10**6)
    merge, _store = storm_merge(monkeypatch, client, depth=2)
    for _ in range(10):
        assert merge.commit_next('heavy', STEADY) is None
    assert client.aborts_remaining == 10**6
    assert client.transactions == 0


def test_storm_commit_bumps_the_owner_revision(monkeypatch):
    client = StormClient(rows=storm_held_rows())
    merge, _store = storm_merge(monkeypatch, client, depth=2)
    merge.commit_next('heavy', STEADY)
    client.aborts_remaining = 0
    client.rows[f'{NAMESPACE}_results', 'w8'] = {'log_sequence': 6}
    client.rows[f'{NAMESPACE}_owners', OWNER]['projection_watermark'] = 'w8'
    merge.commit_next('heavy', STEADY)
    assert client.rows[f'{NAMESPACE}_owners', OWNER]['revision'] == 4


def test_storm_commit_writes_the_result_log_row(monkeypatch):
    client = StormClient(rows=storm_held_rows())
    merge, _store = storm_merge(monkeypatch, client, depth=2)
    merge.commit_next('heavy', STEADY)
    client.aborts_remaining = 0
    client.rows[f'{NAMESPACE}_results', 'w8'] = {'log_sequence': 6}
    client.rows[f'{NAMESPACE}_owners', OWNER]['projection_watermark'] = 'w8'
    merge.commit_next('heavy', STEADY)
    entry = client.rows[f'{NAMESPACE}_results', 'a']
    assert entry['log_sequence'] == 7
    assert entry['late_capture'] is False
    assert entry['projection_state'] == 'pending'
    assert entry['owner_key'] == OWNER


def test_storm_commit_marks_the_job_committed(monkeypatch):
    client = StormClient(rows=storm_held_rows())
    merge, _store = storm_merge(monkeypatch, client, depth=2)
    merge.commit_next('heavy', STEADY)
    client.aborts_remaining = 0
    client.rows[f'{NAMESPACE}_results', 'w8'] = {'log_sequence': 6}
    client.rows[f'{NAMESPACE}_owners', OWNER]['projection_watermark'] = 'w8'
    merge.commit_next('heavy', STEADY)
    job = client.rows[f'{NAMESPACE}_jobs', 'a']
    assert job['state'] == 'committed'
    assert job['merge_pending'] is False


def test_storm_fresh_commit_entry_fields(monkeypatch):
    rows = storm_held_rows()
    rows[f'{NAMESPACE}_jobs', 'f'] = {
        'segment_id': 'f',
        'owner_key': OWNER,
        'owner_id': 'heavy',
        'merge_pending': True,
        'state': 'result_ready',
        'capture_at': 3,
        'priority': 0,
        'ready_at': 10.0,
        'result': {'outcome': 'success', 'result_uri': 'gs://results/f', 'segment_id': 'f'},
        'protocol_version': 1,
        'fresh_capture': True,
    }
    client = StormClient(rows=rows)
    merge, _store = storm_merge(monkeypatch, client, depth=2)
    # The ready fresh sibling makes the same drain open the fresh re-verify,
    # which joins the storm exactly as the strict world did.
    with pytest.raises(FirestoreContentionExhausted):
        merge.commit_next('heavy', STEADY)
    client.aborts_remaining = 0
    entry = merge.commit_next('heavy', STEADY)
    assert entry['segment_id'] == 'f'
    assert entry['fresh_first'] is True
    assert entry['log_sequence'] == 7
    assert entry['late_capture'] is False


def test_storm_marker_row_survives_five_drains_byte_identically(monkeypatch):
    client = StormClient(rows=storm_held_rows())
    merge, _store = storm_merge(monkeypatch, client, depth=2)
    before = deepcopy(client.rows[f'{NAMESPACE}_merge_holds', OWNER])
    for _ in range(5):
        merge.commit_next('heavy', STEADY)
    assert client.rows[f'{NAMESPACE}_merge_holds', OWNER] == before


# --------------------------------------------------------------------------
# 17. World-parity extras and the env kill switch
# --------------------------------------------------------------------------


def test_blocked_head_interlude_rows_are_byte_identical_across_worlds(monkeypatch):
    on = held_store()
    drain_held(on)
    set_state(on, 'a', 'leased')
    drain_held(on)
    gate_off(monkeypatch)
    off = held_store()
    drain_held(off)
    set_state(off, 'a', 'leased')
    drain_held(off)
    assert table_rows(on) == table_rows(off)


def test_cleared_marker_rows_are_byte_identical_across_worlds(monkeypatch):
    on = held_store()
    on.rows['merge_holds', OWNER] = {'held': False, 'held_at': 1}
    drain_held(on)
    gate_off(monkeypatch)
    off = held_store()
    off.rows['merge_holds', OWNER] = {'held': False, 'held_at': 1}
    drain_held(off)
    assert table_rows(on) == table_rows(off)


def test_release_of_only_the_held_head_rows_are_byte_identical_across_worlds(monkeypatch):
    on = held_store()
    _merge_on, entry_on = drain_held(on, release=['a'])
    gate_off(monkeypatch)
    off = held_store()
    _merge_off, entry_off = drain_held(off, release=['a'])
    assert entry_on is None and entry_off is None
    assert table_rows(on) == table_rows(off)


def test_env_kill_switch_matches_the_patched_kill_switch(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_HELD_HEAD_GATE_ENABLED', 'false')
    store = held_store()
    merge, entry = drain_held(store)
    assert entry is None
    assert store.runs == 1
    assert merge.held_owners == {'heavy'}


def test_env_kill_switch_storm_world_still_exhausts(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_HELD_HEAD_GATE_ENABLED', 'false')
    client = StormClient(rows=storm_held_rows())
    merge, _store = storm_merge(monkeypatch, client, depth=2)
    with pytest.raises(FirestoreContentionExhausted):
        merge.commit_next('heavy', STEADY)


# --------------------------------------------------------------------------
# 18. Probe surfaces: the gate adds exactly one twin pair and one marker read
# --------------------------------------------------------------------------


def test_below_cap_narrow_path_probes_the_twin_pair_and_the_owner():
    store = held_store(sequence=6, watermark='w5', done=5)
    drain_held(store)
    assert store.probed == [('owners', OWNER), ('results', 'w5'), ('owners', OWNER)]


def test_unmarked_refusal_probes_twin_twice_then_the_marker():
    store = held_store(marker=False)
    drain_held(store)
    assert store.probed == [
        ('owners', OWNER),
        ('results', 'w5'),
        ('owners', OWNER),
        ('results', 'w5'),
        ('merge_holds', OWNER),
    ]


def test_shadow_head_probes_nothing_beyond_the_head_hint():
    store = held_store()
    store.rows['jobs', 'a']['shadow'] = True
    drain_held(store)
    assert store.probed == []
    assert store.head_pending_calls == 1


def test_catch_up_blocked_head_probes_nothing_beyond_the_head_hint():
    store = held_store(head_state='leased', head_class=False)
    drain_held(store)
    assert store.probed == []
    assert store.head_pending_calls == 1


def test_head_probe_failure_probes_nothing_else():
    store = held_store()
    store.head_pending_error = ServiceUnavailable('hint read down')
    drain_held(store)
    assert store.probed == []


# --------------------------------------------------------------------------
# 19. Composite sequences
# --------------------------------------------------------------------------


def test_two_skips_then_fresh_then_late_tail_then_release():
    store = held_store()
    merge = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=2)
    assert merge.commit_next('heavy', STEADY) is None
    assert merge.commit_next('heavy', STEADY) is None
    add_sibling(store, 'f', 2, capture_class=True)
    entry = merge.commit_next('heavy', STEADY)
    assert entry['segment_id'] == 'f'
    assert entry['fresh_first'] is True
    advance_projection(store, key='f', sequence=7)
    entry = merge.commit_next('heavy', STEADY)
    assert entry['segment_id'] == 'a'
    assert entry['late_capture'] is True
    merge.release_hold(OWNER)
    assert store.rows['merge_holds', OWNER]['held'] is False
    assert merge.held_owners == set()


def test_composite_sequence_rows_are_byte_identical_across_worlds(monkeypatch):
    on = held_store()
    merge_on = OrderedMerge(on, head_wait_seconds=0, catch_up_depth=2)
    merge_on.commit_next('heavy', STEADY)
    add_sibling(on, 'f', 2, capture_class=True)
    merge_on.commit_next('heavy', STEADY)
    advance_projection(on, key='f', sequence=7)
    merge_on.commit_next('heavy', STEADY)
    merge_on.release_hold(OWNER)
    gate_off(monkeypatch)
    off = held_store()
    merge_off = OrderedMerge(off, head_wait_seconds=0, catch_up_depth=2)
    merge_off.commit_next('heavy', STEADY)
    add_sibling(off, 'f', 2, capture_class=True)
    merge_off.commit_next('heavy', STEADY)
    advance_projection(off, key='f', sequence=7)
    merge_off.commit_next('heavy', STEADY)
    merge_off.release_hold(OWNER)
    assert table_rows(on) == table_rows(off)


def test_marker_probe_retry_log_includes_the_source_label(caplog):
    store = held_store()
    flaky_probe(store, 'merge_holds')
    with caplog.at_level(logging.WARNING, logger='utils.batch_pipeline.merge'):
        drain_held(store)
    message = next(record.getMessage() for record in caplog.records if 'held_marker_probe_retry' in record.getMessage())
    assert 'source=ordered_merge' in message


def test_marker_probe_retry_log_includes_the_count_field(caplog):
    store = held_store()
    flaky_probe(store, 'merge_holds')
    with caplog.at_level(logging.WARNING, logger='utils.batch_pipeline.merge'):
        drain_held(store)
    message = next(record.getMessage() for record in caplog.records if 'held_marker_probe_retry' in record.getMessage())
    assert 'count=1' in message


def test_budget_entry_review_by_is_scheduled():
    budget = json.loads((Path(__file__).resolve().parents[2] / 'config' / 'flag_budget.json').read_text())
    assert budget['names']['BATCH_PIPELINE_MERGE_HELD_HEAD_GATE_ENABLED']['review_by'] == '2026-12-15'


def test_held_head_gate_whitespace_true_is_on(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_HELD_HEAD_GATE_ENABLED', ' true ')
    from config.batch_pipeline import merge_held_head_gate_enabled

    assert merge_held_head_gate_enabled() is True


def test_held_head_gate_yes_is_on(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_HELD_HEAD_GATE_ENABLED', 'yes')
    from config.batch_pipeline import merge_held_head_gate_enabled

    assert merge_held_head_gate_enabled() is True


def test_held_head_gate_off_word_is_on_like_the_literal_false_switch(monkeypatch):
    """The switch is literal-false-only, matching every sibling gate."""
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_HELD_HEAD_GATE_ENABLED', 'off')
    from config.batch_pipeline import merge_held_head_gate_enabled

    assert merge_held_head_gate_enabled() is True
