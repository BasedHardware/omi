"""Control steady-write skip: the admission write ledger (batch contention family).

Every unit admission of an already-active owner appended the owner's control
document with byte-identical content: ``activate`` is value-stable on the warm
path and a warm queue's ring membership does not change. Under sibling
admission bursts those content-free writes carried the hottest per-owner
document inside every append transaction's write set, so N concurrent sibling
appends aborted each other through the shared five-attempt contention budget
until ``operation=batch_pipeline_store attempt=5/5 outcome=exhausted`` was
logged. The steady-write skip turns the write into a decision: identical
snapshot means nothing changed and the write is skipped; any real activation
change (cold activation, first ring membership, a frontier seed) writes
exactly as before. These tests pin the admission write ledger: which
documents a warm append touches, which a cold append must touch, the
byte-parity of every write that survives, and the kill switch that restores
the unconditional write.

Failure-Class: FC-control-document-carries-content-free-append-writes
"""

from copy import deepcopy

import pytest

from config.batch_pipeline import control_steady_write_skip_enabled, scheduler_control_key
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, MemoryTransaction, item
from utils.batch_pipeline.contracts import Priority
from utils.batch_pipeline.scheduler import Scheduler, owner_key

OWNER = 'heavy'
KEY = owner_key(OWNER)
QUEUE = f'{int(Priority.DEEP)}_{KEY}'
FRESH_QUEUE = f'{int(Priority.FRESH)}_{KEY}'
CONTROL = scheduler_control_key(KEY)


class LedgerTransaction(MemoryTransaction):
    """MemoryTransaction twin that records every put in order."""

    def __init__(self, rows):
        super().__init__(rows)
        self.puts = []

    def put(self, table, key, value):
        self.puts.append((table, key))
        super().put(table, key, value)


class LedgerStore(MemoryStore):
    """MemoryStore that keeps the put ledger of every transaction it runs."""

    def __init__(self):
        super().__init__()
        self.ledgers = []

    def run(self, body, *, operation=None):
        with self.lock:
            snapshot = deepcopy(self.rows)
            tx = LedgerTransaction(snapshot)
            result = body(tx)
            self.rows = snapshot
            self.ledgers.append(list(tx.puts))
            return result

    @property
    def last(self):
        return self.ledgers[-1]

    def control_writes(self, key=None):
        return sum(1 for puts in self.ledgers if ('control', key or CONTROL) in puts)


def kill_switch(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_CONTROL_STEADY_WRITE_SKIP_ENABLED', 'false')


def control_row(store):
    return store.rows.get(('control', CONTROL)) or {}


def queue_row(store, key=None):
    return store.rows.get(('queues', key or QUEUE)) or {}


def warm_owner(store, segment='seg_base', now=0.0):
    scheduler = Scheduler(store)
    assert scheduler.enqueue(item(segment, owner=OWNER), now)
    return scheduler


def seed_array_queue(store, segments=('seg_base',)):
    """Move the owner's queue onto the landed array representation."""
    store.rows[('queues', QUEUE)] = {
        'link_mode': 'fifo_array',
        'items': list(segments),
        'head': segments[0] if segments else '',
        'tail': segments[-1] if segments else '',
        'deficit': 0.0,
        'continuing': False,
    }


# --- the warm append leaves the control document out of the write set ------


def test_second_admission_of_active_owner_skips_control_write():
    store = LedgerStore()
    scheduler = warm_owner(store)
    assert scheduler.enqueue(item('seg_second', owner=OWNER), 50.0)
    assert ('control', CONTROL) not in store.last


def test_warm_array_append_write_set_is_queue_job_owner_only():
    store = LedgerStore()
    warm_owner(store)
    seed_array_queue(store)
    Scheduler(store).enqueue(item('seg_second', owner=OWNER), 50.0)
    assert store.last == [('queues', QUEUE), ('jobs', 'seg_second'), ('owners', KEY)]


def test_warm_array_append_still_writes_the_queue_document():
    store = LedgerStore()
    warm_owner(store)
    seed_array_queue(store)
    Scheduler(store).enqueue(item('seg_second', owner=OWNER), 50.0)
    assert ('queues', QUEUE) in store.last


def test_warm_array_append_still_writes_the_job_document():
    store = LedgerStore()
    warm_owner(store)
    seed_array_queue(store)
    Scheduler(store).enqueue(item('seg_second', owner=OWNER), 50.0)
    assert ('jobs', 'seg_second') in store.last


def test_warm_array_append_still_rewrites_the_owner_revision():
    store = LedgerStore()
    warm_owner(store)
    seed_array_queue(store)
    Scheduler(store).enqueue(item('seg_second', owner=OWNER), 50.0)
    assert ('owners', KEY) in store.last


def test_first_admission_of_cold_owner_writes_control():
    store = LedgerStore()
    assert Scheduler(store).enqueue(item('seg_first', owner=OWNER), 0.0)
    assert ('control', CONTROL) in store.last


def test_cold_owner_write_set_covers_queue_control_jobs_owners():
    store = LedgerStore()
    Scheduler(store).enqueue(item('seg_first', owner=OWNER), 0.0)
    assert store.last == [
        ('control', CONTROL),
        ('queues', QUEUE),
        ('jobs', 'seg_first'),
        ('owners', KEY),
    ]


def test_warm_legacy_append_within_probe_backoff_skips_control():
    store = LedgerStore()
    warm_owner(store, now=0.0)
    assert Scheduler(store).enqueue(item('seg_second', owner=OWNER), 50.0)
    assert ('control', CONTROL) not in store.last


def test_warm_append_write_set_has_no_control_put():
    store = LedgerStore()
    warm_owner(store, now=0.0)
    Scheduler(store).enqueue(item('seg_second', owner=OWNER), 50.0)
    assert store.last == [('queues', QUEUE), ('jobs', 'seg_second'), ('owners', KEY)]


def test_conversion_append_after_backoff_skips_control():
    store = LedgerStore()
    warm_owner(store, now=0.0)
    Scheduler(store).enqueue(item('seg_second', owner=OWNER), 50.0)
    assert Scheduler(store).enqueue(item('seg_third', owner=OWNER), 120.0)
    assert ('control', CONTROL) not in store.last


def test_conversion_append_lands_the_array_representation():
    store = LedgerStore()
    warm_owner(store, now=0.0)
    Scheduler(store).enqueue(item('seg_second', owner=OWNER), 50.0)
    Scheduler(store).enqueue(item('seg_third', owner=OWNER), 120.0)
    row = queue_row(store)
    assert row['link_mode'] == 'fifo_array'
    assert row['items'] == ['seg_base', 'seg_second', 'seg_third']
    assert row['tail'] == 'seg_third'


def test_third_admission_also_skips_control_write():
    store = LedgerStore()
    scheduler = warm_owner(store)
    scheduler.enqueue(item('seg_second', owner=OWNER), 50.0)
    scheduler.enqueue(item('seg_third', owner=OWNER), 51.0)
    assert ('control', CONTROL) not in store.last


def test_six_sibling_admissions_write_control_exactly_once():
    store = LedgerStore()
    scheduler = Scheduler(store)
    for index in range(6):
        assert scheduler.enqueue(item(f'seg_{index}', owner=OWNER), index * 70.0)
    assert store.control_writes() == 1


def test_six_sibling_array_admissions_write_six_queue_rows():
    store = LedgerStore()
    scheduler = Scheduler(store)
    for index in range(6):
        assert scheduler.enqueue(item(f'seg_{index}', owner=OWNER), index * 70.0)
    assert sum(1 for puts in store.ledgers if ('queues', QUEUE) in puts) == 6


def test_six_sibling_admissions_leave_one_control_write_on_the_kill_switch(monkeypatch):
    kill_switch(monkeypatch)
    store = LedgerStore()
    scheduler = Scheduler(store)
    for index in range(6):
        assert scheduler.enqueue(item(f'seg_{index}', owner=OWNER), index * 70.0)
    assert store.control_writes() == 6


def test_queue_tail_tracks_the_last_admitted_segment():
    store = LedgerStore()
    warm_owner(store)
    Scheduler(store).enqueue(item('seg_second', owner=OWNER), 50.0)
    assert queue_row(store)['tail'] == 'seg_second'


def test_queue_head_survives_the_warm_appends():
    store = LedgerStore()
    warm_owner(store)
    Scheduler(store).enqueue(item('seg_second', owner=OWNER), 50.0)
    assert queue_row(store)['head'] == 'seg_base'


def test_control_content_is_unchanged_by_a_warm_append():
    store = LedgerStore()
    warm_owner(store)
    before = deepcopy(control_row(store))
    Scheduler(store).enqueue(item('seg_second', owner=OWNER), 50.0)
    assert control_row(store) == before


def test_control_content_idempotent_across_five_warm_appends():
    store = LedgerStore()
    warm_owner(store)
    before = deepcopy(control_row(store))
    scheduler = Scheduler(store)
    for index in range(5):
        scheduler.enqueue(item(f'seg_more_{index}', owner=OWNER), index * 70.0)
    assert control_row(store) == before


def test_warm_job_document_still_lands_ready():
    store = LedgerStore()
    warm_owner(store)
    Scheduler(store).enqueue(item('seg_second', owner=OWNER), 50.0)
    job = store.rows.get(('jobs', 'seg_second')) or {}
    assert job.get('state') == 'ready'
    assert job.get('owner_key') == KEY


def test_warm_job_carries_the_owner_key_and_priority():
    store = LedgerStore()
    warm_owner(store)
    Scheduler(store).enqueue(item('seg_second', owner=OWNER), 50.0)
    job = store.rows[('jobs', 'seg_second')]
    assert job['priority'] == int(Priority.DEEP)
    assert job['attempt'] == 0


def test_deduplicated_readmission_performs_no_writes_at_all():
    store = LedgerStore()
    warm_owner(store, segment='seg_dupe')
    assert Scheduler(store).enqueue(item('seg_dupe', owner=OWNER), 50.0) is False
    assert store.last == []


# --- real activation changes still write ------------------------------------


def test_first_unit_at_a_new_priority_writes_control():
    store = LedgerStore()
    warm_owner(store)
    assert Scheduler(store).enqueue(item('seg_fresh_first', owner=OWNER, priority=Priority.FRESH), 50.0)
    assert ('control', CONTROL) in store.last


def test_new_priority_write_stages_the_fresh_ring():
    store = LedgerStore()
    warm_owner(store)
    Scheduler(store).enqueue(item('seg_fresh_first', owner=OWNER, priority=Priority.FRESH), 50.0)
    assert FRESH_QUEUE in control_row(store)['rings'][str(int(Priority.FRESH))]


def test_new_priority_write_activates_the_priority():
    store = LedgerStore()
    warm_owner(store)
    Scheduler(store).enqueue(item('seg_fresh_first', owner=OWNER, priority=Priority.FRESH), 50.0)
    assert control_row(store)['p0_active'] is True


def test_new_priority_write_lands_its_queue_row():
    store = LedgerStore()
    warm_owner(store)
    Scheduler(store).enqueue(item('seg_fresh_first', owner=OWNER, priority=Priority.FRESH), 50.0)
    fresh = store.rows.get(('queues', FRESH_QUEUE)) or {}
    assert fresh['head'] == 'seg_fresh_first'


def test_second_fresh_unit_skips_control_again():
    store = LedgerStore()
    warm_owner(store)
    Scheduler(store).enqueue(item('seg_fresh_first', owner=OWNER, priority=Priority.FRESH), 50.0)
    Scheduler(store).enqueue(item('seg_fresh_second', owner=OWNER, priority=Priority.FRESH), 50.5)
    assert ('control', CONTROL) not in store.last


def test_cold_owner_with_frontier_seed_writes_control_with_the_seed():
    store = LedgerStore()
    store.service_frontier_hint = lambda priority: 5.0
    assert Scheduler(store).enqueue(item('seg_first', owner=OWNER), 0.0)
    assert ('control', CONTROL) in store.last
    assert control_row(store)['p2_service'] == 5.0


def test_warm_owner_keeps_service_even_when_the_hint_rises():
    store = LedgerStore()
    warm_owner(store)
    store.service_frontier_hint = lambda priority: 50.0
    Scheduler(store).enqueue(item('seg_second', owner=OWNER), 50.0)
    assert control_row(store)['p2_service'] == 0.0


def test_second_owner_on_a_fresh_store_writes_its_own_control():
    store = LedgerStore()
    warm_owner(store)
    light_key = owner_key('light')
    assert Scheduler(store).enqueue(item('seg_light', owner='light'), 50.0)
    assert ('control', scheduler_control_key(light_key)) in store.last


def test_second_owner_admission_leaves_heavy_control_untouched():
    store = LedgerStore()
    warm_owner(store)
    before = deepcopy(control_row(store))
    Scheduler(store).enqueue(item('seg_light', owner='light'), 50.0)
    assert control_row(store) == before


def test_priority_expansion_on_second_owner_writes_its_control_twice():
    store = LedgerStore()
    warm_owner(store)
    Scheduler(store).enqueue(item('seg_light', owner='light'), 50.0)
    Scheduler(store).enqueue(item('seg_light_fresh', owner='light', priority=Priority.FRESH), 50.5)
    light_key = owner_key('light')
    # Fresh lands a second queue on the light ring: a real change, a real write.
    assert store.control_writes(scheduler_control_key(light_key)) == 2


# --- kill switch restores the unconditional write ---------------------------


def test_kill_switch_restores_the_warm_control_write(monkeypatch):
    kill_switch(monkeypatch)
    store = LedgerStore()
    scheduler = warm_owner(store)
    scheduler.enqueue(item('seg_second', owner=OWNER), 50.0)
    assert ('control', CONTROL) in store.last


def test_kill_switch_warm_write_set_matches_the_legacy_shape(monkeypatch):
    kill_switch(monkeypatch)
    store = LedgerStore()
    scheduler = warm_owner(store)
    scheduler.enqueue(item('seg_second', owner=OWNER), 50.0)
    assert store.last == [
        ('control', CONTROL),
        ('queues', QUEUE),
        ('jobs', 'seg_second'),
        ('owners', KEY),
    ]


def test_kill_switch_and_skip_produce_identical_documents(monkeypatch):
    kill_switch(monkeypatch)
    killed = LedgerStore()
    scheduler = Scheduler(killed)
    scheduler.enqueue(item('seg_first', owner=OWNER), 0.0)
    scheduler.enqueue(item('seg_second', owner=OWNER), 50.0)
    scheduler.enqueue(item('seg_third', owner=OWNER), 130.0)
    monkeypatch.delenv('BATCH_PIPELINE_CONTROL_STEADY_WRITE_SKIP_ENABLED', raising=False)
    skipped = LedgerStore()
    scheduler = Scheduler(skipped)
    scheduler.enqueue(item('seg_first', owner=OWNER), 0.0)
    scheduler.enqueue(item('seg_second', owner=OWNER), 50.0)
    scheduler.enqueue(item('seg_third', owner=OWNER), 130.0)
    assert control_row(killed) == control_row(skipped)
    assert killed.rows[('queues', QUEUE)] == skipped.rows[('queues', QUEUE)]
    assert killed.rows[('jobs', 'seg_third')] == skipped.rows[('jobs', 'seg_third')]


def test_kill_switch_cold_owner_still_writes(monkeypatch):
    kill_switch(monkeypatch)
    store = LedgerStore()
    assert Scheduler(store).enqueue(item('seg_first', owner=OWNER), 0.0)
    assert ('control', CONTROL) in store.last


def test_flag_helper_defaults_to_enabled(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_CONTROL_STEADY_WRITE_SKIP_ENABLED', raising=False)
    assert control_steady_write_skip_enabled() is True


def test_flag_helper_env_false_disables(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_CONTROL_STEADY_WRITE_SKIP_ENABLED', 'false')
    assert control_steady_write_skip_enabled() is False


def _saturate_ring(store, monkeypatch):
    # Ring capacity is per-owner: the owner's control document holds that
    # owner's queues, so saturation means one existing entry plus MAX=1.
    monkeypatch.setattr('utils.batch_pipeline.scheduler.MAX_ACTIVE_OWNERS', 1)
    key = scheduler_control_key(owner_key('blocked'))
    control = store.rows.setdefault(('control', key), {})
    control.setdefault('rings', {}).setdefault(str(int(Priority.DEEP)), []).append('filler_queue')


def test_kill_switch_ring_capacity_refusal_matches_the_skip(monkeypatch):
    kill_switch(monkeypatch)
    store = LedgerStore()
    warm_owner(store)
    _saturate_ring(store, monkeypatch)
    with pytest.raises(RuntimeError, match='active owner capacity exceeded'):
        Scheduler(store).enqueue(item('seg_blocked', owner='blocked'), 50.0)


def test_skip_mode_ring_capacity_refusal_matches_the_kill_switch(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_CONTROL_STEADY_WRITE_SKIP_ENABLED', raising=False)
    store = LedgerStore()
    warm_owner(store)
    _saturate_ring(store, monkeypatch)
    with pytest.raises(RuntimeError, match='active owner capacity exceeded'):
        Scheduler(store).enqueue(item('seg_blocked', owner='blocked'), 50.0)


def test_ring_capacity_refusal_leaves_no_partial_queue_row(monkeypatch):
    store = LedgerStore()
    warm_owner(store)
    _saturate_ring(store, monkeypatch)
    with pytest.raises(RuntimeError):
        Scheduler(store).enqueue(item('seg_blocked', owner='blocked'), 50.0)
    assert ('queues', f'{int(Priority.DEEP)}_{owner_key("blocked")}') not in store.rows


def test_ring_capacity_refusal_leaves_no_partial_job_row(monkeypatch):
    store = LedgerStore()
    warm_owner(store)
    _saturate_ring(store, monkeypatch)
    with pytest.raises(RuntimeError):
        Scheduler(store).enqueue(item('seg_blocked', owner='blocked'), 50.0)
    assert ('jobs', 'seg_blocked') not in store.rows


def test_warm_append_after_a_failed_append_still_skips(monkeypatch):
    store = LedgerStore()
    scheduler = warm_owner(store)
    _saturate_ring(store, monkeypatch)
    with pytest.raises(RuntimeError):
        Scheduler(store).enqueue(item('seg_blocked', owner='blocked'), 50.0)
    scheduler.enqueue(item('seg_second', owner=OWNER), 51.0)
    assert ('control', CONTROL) not in store.last


def test_mixed_cold_and_warm_admission_ledger_counts_are_exact():
    store = LedgerStore()
    scheduler = Scheduler(store)
    scheduler.enqueue(item('seg_a', owner=OWNER), 0.0)
    scheduler.enqueue(item('seg_b', owner=OWNER), 70.0)
    scheduler.enqueue(item('seg_c', owner=OWNER), 140.0)
    assert store.control_writes() == 1
    assert sum(1 for puts in store.ledgers if ('jobs', 'seg_c') in puts) == 1


def test_two_owners_admitting_in_turn_each_write_once():
    store = LedgerStore()
    scheduler = Scheduler(store)
    scheduler.enqueue(item('seg_h1', owner=OWNER), 0.0)
    scheduler.enqueue(item('seg_l1', owner='light'), 0.0)
    scheduler.enqueue(item('seg_h2', owner=OWNER), 70.0)
    scheduler.enqueue(item('seg_l2', owner='light'), 70.0)
    # Both light units ride the DEEP queue: the first write activates the
    # owner, the second is a warm append whose control write is skipped.
    light_key = owner_key('light')
    assert store.control_writes(scheduler_control_key(light_key)) == 1


def test_interleaved_priorities_write_only_on_first_touch():
    store = LedgerStore()
    scheduler = Scheduler(store)
    scheduler.enqueue(item('seg_deep1', owner=OWNER), 0.0)
    scheduler.enqueue(item('seg_fresh1', owner=OWNER, priority=Priority.FRESH), 0.0)
    scheduler.enqueue(item('seg_deep2', owner=OWNER), 70.0)
    scheduler.enqueue(item('seg_fresh2', owner=OWNER, priority=Priority.FRESH), 70.0)
    assert store.control_writes() == 2


def test_after_a_warm_stream_the_control_document_is_still_well_formed():
    store = LedgerStore()
    scheduler = Scheduler(store)
    for index in range(4):
        scheduler.enqueue(item(f'seg_{index}', owner=OWNER), index * 70.0)
    control = control_row(store)
    assert QUEUE in control['rings'][str(int(Priority.DEEP))]
    assert control['p2_active'] is True
    assert control['p2_batch_available_at'] == 0.0
    assert control['p2_live_available_at'] == 0.0


def test_warm_stream_keeps_every_job_on_its_queue():
    store = LedgerStore()
    scheduler = Scheduler(store)
    for index in range(4):
        scheduler.enqueue(item(f'seg_{index}', owner=OWNER), index * 70.0)
    row = queue_row(store)
    assert row['items'] == ['seg_0', 'seg_1', 'seg_2', 'seg_3']
    assert row['head'] == 'seg_0'
    assert row['tail'] == 'seg_3'


def test_control_writes_per_unit_drop_to_one_over_a_warm_stream():
    store = LedgerStore()
    scheduler = Scheduler(store)
    total = 8
    for index in range(total):
        scheduler.enqueue(item(f'seg_{index}', owner=OWNER), index * 70.0)
    assert store.control_writes() == 1
    assert len(store.ledgers) == total
