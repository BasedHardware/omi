"""Queue-document FIFO link parity (batch contention family).

The owner FIFO's link used to live on each unit's job document: appending a
unit read and rewrote the in-flight tail unit's document, colliding with its
20-second heartbeat, its completion and failure transitions, and the pull's
head-priority splice until the shared five-attempt contention budget
exhausted. The queue document now carries the order as a bounded array; these
tests pin the append write-set contract, the conversion and straggler
migrations, walk/predecessor/purge parity, and the attribution labels that
name the caller in every contention line.
"""

import logging
from copy import deepcopy
from dataclasses import replace
from threading import RLock

import pytest

from config.batch_pipeline import contention_retry_enabled, fifo_array_link_enabled, scheduler_control_key
from database.batch_pipeline_purge import _delete_job
from database.batch_pipeline_store import FirestoreTransaction
from database.batch_pipeline_transaction_labels import current_operation, store_operation
from tests.unit.test_batch_pipeline_intake import proposal, submit
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, MemoryTransaction, item
from utils.batch_pipeline import provider_stt as provider_stt_module
from utils.batch_pipeline import scheduler as scheduler_module
from utils.batch_pipeline.contracts import Priority, WorkResult
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.provider_stt import ProviderSttStore
from utils.batch_pipeline.scheduler import (
    FIFO_ARRAY_MAX_ITEMS,
    FIFO_LINK_MIGRATION_WALK_CAP,
    FIFO_LINK_PROBE_BACKOFF_SECONDS,
    Scheduler,
    owner_key,
)

OWNER = 'heavy'
KEY = owner_key(OWNER)
QUEUE = f'{int(Priority.DEEP)}_{KEY}'
LIGHT_QUEUE = f"{int(Priority.DEEP)}_{owner_key('light')}"
FRESH_QUEUE = f'{int(Priority.FRESH)}_{KEY}'
CONTROL = scheduler_control_key(KEY)
W = 60


def kill_switch(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_FIFO_ARRAY_LINK_ENABLED', 'false')


def array_mode(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_FIFO_ARRAY_LINK_ENABLED', 'true')


def queue_row(store):
    return store.rows.get(('queues', QUEUE)) or {}


class LabeledStore(MemoryStore):
    def __init__(self):
        super().__init__()
        self.labels = []

    def run(self, body, *, operation=None):
        self.labels.append(operation if operation is not None else current_operation())
        return super().run(body, operation=operation)


class RecordingTransaction(MemoryTransaction):
    def __init__(self, rows):
        super().__init__(rows)
        self.reads, self.writes = set(), set()

    def get(self, table, key):
        self.reads.add((table, key))
        return super().get(table, key)

    def put(self, table, key, value):
        self.writes.add((table, key))
        super().put(table, key, value)


class RecordingStore(MemoryStore):
    def __init__(self):
        super().__init__()
        self.last = None
        self.max_writes = 0
        self.max_job_writes = 0

    def run(self, body, *, operation=None):
        with self.lock:
            snapshot = deepcopy(self.rows)
            tx = RecordingTransaction(snapshot)
            result = body(tx)
            self.last = tx
            self.max_writes = max(self.max_writes, len(tx.writes))
            self.max_job_writes = max(self.max_job_writes, sum(1 for table, _ in tx.writes if table == 'jobs'))
            self.rows = snapshot
            return result

    @property
    def last_reads(self):
        return set(self.last.reads) if self.last else set()

    @property
    def last_writes(self):
        return set(self.last.writes) if self.last else set()


# --- flag plumbing -----------------------------------------------------------------------


def test_fifo_link_defaults_on():
    assert fifo_array_link_enabled()


def test_fifo_link_kill_switch_string_false_disables(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_FIFO_ARRAY_LINK_ENABLED', 'false')
    assert not fifo_array_link_enabled()


def test_fifo_link_padded_false_still_disables(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_FIFO_ARRAY_LINK_ENABLED', ' FALSE ')
    assert not fifo_array_link_enabled()


def test_fifo_link_zero_is_not_the_kill_switch_token(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_FIFO_ARRAY_LINK_ENABLED', '0')
    assert fifo_array_link_enabled()


def test_fifo_link_migration_cap_swallows_two_max_bundles():
    # A rolling update can leave at most one 128-unit legacy bundle chained
    # between array touches; the migration cap must absorb two with headroom.
    assert FIFO_LINK_MIGRATION_WALK_CAP >= 2 * 128


# --- attribution labels -------------------------------------------------------------------


def test_store_operation_sets_and_resets_the_label():
    with store_operation('batch_probe'):
        assert current_operation() == 'batch_probe'
    assert current_operation() is None


def test_store_operation_resets_the_label_when_the_body_raises():
    with pytest.raises(RuntimeError), store_operation('batch_probe'):
        raise RuntimeError('boom')
    assert current_operation() is None


def test_store_operation_nests_and_restores_in_order():
    with store_operation('batch_outer'):
        with store_operation('batch_inner'):
            assert current_operation() == 'batch_inner'
        assert current_operation() == 'batch_outer'
    assert current_operation() is None


def test_store_operation_nested_exception_restores_both_labels():
    with store_operation('batch_outer'):
        with pytest.raises(RuntimeError), store_operation('batch_inner'):
            raise RuntimeError('boom')
        assert current_operation() == 'batch_outer'
    assert current_operation() is None


@pytest.mark.parametrize('bad', ['', 'Upper', 'with space', 'dash-dash', 'x' * 65])
def test_store_operation_rejects_non_static_labels(bad):
    with pytest.raises(ValueError):
        with store_operation(bad):
            pass


def test_heartbeat_runs_under_its_own_label():
    store = LabeledStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(1)[0]
    assert queue.heartbeat('a', lease.token, 1)
    assert 'batch_heartbeat' in store.labels


def test_complete_runs_under_its_own_label():
    store = LabeledStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(1)[0]
    assert queue.complete(WorkResult('a', 'gs://results/a'), lease.token, 1)
    assert 'batch_complete' in store.labels


def test_fail_runs_under_its_own_label():
    store = LabeledStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(1)[0]
    assert queue.fail('a', lease.token, 1)
    assert 'batch_fail' in store.labels


def test_defer_runs_under_its_own_label():
    store = LabeledStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(1)[0]
    assert queue.defer('a', lease.token, 1)
    assert 'batch_defer' in store.labels


def test_release_runs_under_its_own_label():
    store = LabeledStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(1)[0]
    assert queue.release('a', lease.token, 1)
    assert 'batch_release' in store.labels


def test_recover_runs_under_its_own_label():
    store = LabeledStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    queue.pull(1)[0]
    store.rows['jobs', 'a']['lease_until'] = 0.5
    assert queue.recover(1) == 1
    assert 'batch_recover' in store.labels


def test_single_enqueue_runs_under_its_own_label():
    store = LabeledStore()
    assert Scheduler(store).enqueue(item('a'), 0)
    assert store.labels == ['batch_enqueue']


def test_merge_commit_runs_under_its_own_label():
    store = LabeledStore()
    queue = Scheduler(store)
    queue.enqueue(item('a', capture=1), 0)
    queue.enqueue(item('b', capture=2), 0)
    leases = {lease.item.segment_id: lease for lease in queue.pull(1, 2)}
    store.rows['jobs', 'b']['lease_until'] = 11
    assert queue.complete(WorkResult('b', 'gs://results/b'), leases['b'].token, 10)
    merge = OrderedMerge(store, head_wait_seconds=W)
    bypass = merge.commit_next(OWNER, 10 + W)
    assert bypass['segment_id'] == 'b'
    assert 'batch_merge_commit' in store.labels


def test_admit_runs_under_its_own_label(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_UID_ALLOWLIST', 'synthetic-owner')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '0')
    store = LabeledStore()
    assert submit(store, *proposal())['outcome'] == 'batch'
    assert 'batch_admit' in store.labels


def test_provider_stt_supersede_runs_under_its_own_label():
    store = LabeledStore()
    protocol = ProviderSttStore(store)
    store.rows['jobs', 's'] = {
        'segment_id': 's',
        'owner_id': OWNER,
        'owner_key': KEY,
        'state': sorted(provider_stt_module.STAGE_STATES)[0],
        'merge_pending': True,
        'priority': int(Priority.DEEP),
    }
    store.rows['owners', KEY] = {}
    assert protocol.supersede('s', 10) is True
    assert 'batch_provider_stt' in store.labels


def test_pull_keeps_its_shard_label_not_the_default():
    store = LabeledStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    assert queue.pull(1)
    assert any(label.startswith('batch_pull') for label in store.labels)
    assert 'batch_pipeline_store' not in store.labels


@pytest.mark.parametrize('entry', ['heartbeat', 'fail', 'release'])
def test_labels_apply_under_the_contention_kill_switch(monkeypatch, entry):
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', 'false')
    assert not contention_retry_enabled()
    store = LabeledStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(1)[0]
    assert getattr(queue, entry)('a', lease.token, 1) is True
    assert f'batch_{entry}' in store.labels


def test_complete_label_applies_under_the_contention_kill_switch(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', 'false')
    store = LabeledStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(1)[0]
    assert queue.complete(WorkResult('a', 'gs://results/a'), lease.token, 1) is True
    assert 'batch_complete' in store.labels


# --- array append: shape and the write-set contract ----------------------------------------


def test_first_append_seeds_the_array_with_mirrors():
    store = MemoryStore()
    assert Scheduler(store).enqueue(item('a'), 0)
    queue = queue_row(store)
    assert queue['link_mode'] == 'fifo_array'
    assert queue['items'] == ['a']
    assert queue['head'] == 'a' and queue['tail'] == 'a'


def test_appends_extend_the_array_in_admission_order():
    store = MemoryStore()
    queue = Scheduler(store)
    for segment in ('a', 'b', 'c'):
        assert queue.enqueue(item(segment), index_now(segment))
    assert queue_row(store)['items'] == ['a', 'b', 'c']


def index_now(segment):
    return {'a': 0, 'b': 1000, 'c': 2000}.get(segment, 0)


def test_append_never_reads_or_writes_an_existing_job_document():
    store = RecordingStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    queue.pull(1)
    queue.enqueue(item('b'), 1000)
    assert not any(address[0] == 'jobs' and address[1] != 'b' for address in store.last_reads)
    assert not any(address[0] == 'jobs' and address[1] != 'b' for address in store.last_writes)


def test_append_write_set_is_queue_control_owner_and_the_new_job_only():
    store = RecordingStore()
    assert Scheduler(store).enqueue(item('a'), 0)
    assert {table for table, _ in store.last_writes} == {'queues', 'control', 'owners', 'jobs'}


def test_appended_job_document_keeps_an_empty_next_pointer():
    store = MemoryStore()
    Scheduler(store).enqueue(item('a'), 0)
    assert store.rows['jobs', 'a'].get('next', '') == ''


def test_streaming_append_is_disjoint_from_the_inflight_units_heartbeat():
    store = RecordingStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(1)[0]
    queue.enqueue(item('b'), 1000)
    append_touch = store.last_reads | store.last_writes
    queue.heartbeat('a', lease.token, 1001)
    heartbeat_touch = store.last_reads | store.last_writes
    assert not (append_touch & heartbeat_touch)


def test_flag_off_append_crosses_the_inflight_tail_document(monkeypatch):
    kill_switch(monkeypatch)
    store = RecordingStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    store.last = None
    queue.enqueue(item('b'), 1000)
    assert ('jobs', 'a') in store.last_reads | store.last_writes


def test_flag_off_append_keeps_chain_semantics(monkeypatch):
    kill_switch(monkeypatch)
    store = MemoryStore()
    queue = Scheduler(store)
    for segment, now in (('a', 0), ('b', 1000)):
        assert queue.enqueue(item(segment), now)
    assert store.rows['jobs', 'a']['next'] == 'b'
    assert store.rows['jobs', 'b']['next'] == ''
    assert queue_row(store)['head'] == 'a' and queue_row(store)['tail'] == 'b'
    assert 'link_mode' not in queue_row(store)


def test_flag_off_walk_leases_in_chain_order(monkeypatch):
    kill_switch(monkeypatch)
    store = MemoryStore()
    queue = Scheduler(store)
    for segment, now in (('a', 0), ('b', 1000), ('c', 2000)):
        queue.enqueue(item(segment), now)
    assert [lease.item.segment_id for lease in drain(queue)] == ['a', 'b', 'c']


def drain(queue, *, start=1.0):
    now = start
    while True:
        leases = queue.pull(now)
        if not leases:
            return
        now += 1
        yield from leases


def test_two_owners_get_independent_arrays():
    store = MemoryStore()
    queue = Scheduler(store)
    assert queue.enqueue(item('a', owner='heavy'), 0)
    assert queue.enqueue(item('b', owner='light'), 1000)
    assert queue_row(store)['items'] == ['a']
    assert (store.rows.get(('queues', LIGHT_QUEUE)) or {}).get('items') == ['b']


def test_duplicate_segment_never_double_appends():
    store = MemoryStore()
    queue = Scheduler(store)
    assert queue.enqueue(item('a'), 0)
    assert not queue.enqueue(item('a'), 1000)
    assert queue_row(store)['items'] == ['a']


def test_array_capacity_bound_refuses_and_admission_retries(monkeypatch):
    monkeypatch.setattr(scheduler_module, 'FIFO_ARRAY_MAX_ITEMS', 1)
    store = MemoryStore()
    queue = Scheduler(store)
    assert queue.enqueue(item('a'), 0)
    with pytest.raises(RuntimeError, match='fifo array capacity exceeded'):
        queue.enqueue(item('b'), 1000)


def test_active_owner_capacity_bound_raises_for_a_new_array(monkeypatch):
    monkeypatch.setattr(scheduler_module, 'MAX_ACTIVE_OWNERS', 0)
    store = MemoryStore()
    with pytest.raises(RuntimeError, match='active owner capacity exceeded'):
        Scheduler(store).enqueue(item('a'), 0)


def test_existing_owner_appends_do_not_recheck_the_owner_capacity_bound(monkeypatch):
    monkeypatch.setattr(scheduler_module, 'MAX_ACTIVE_OWNERS', 1)
    store = MemoryStore()
    Scheduler(store).enqueue(item('a'), 0)
    assert Scheduler(store).enqueue(item('b'), 1000)
    assert queue_row(store)['items'] == ['a', 'b']


def test_append_deficit_resets_only_for_a_new_queue():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    store.rows['queues', QUEUE]['deficit'] = 12.0
    store.rows['queues', QUEUE]['continuing'] = True
    queue.enqueue(item('b'), 1000)
    assert queue_row(store)['deficit'] == 12.0
    assert queue_row(store)['continuing'] is True


def test_new_array_append_resets_the_continuing_flag():
    store = MemoryStore()
    Scheduler(store).enqueue(item('a'), 0)
    assert queue_row(store)['continuing'] is False
    assert queue_row(store)['deficit'] == 0.0


def test_new_queue_append_activates_the_ring():
    store = MemoryStore()
    Scheduler(store).enqueue(item('a'), 0)
    assert QUEUE in store.rows['control', CONTROL]['rings'][str(int(Priority.DEEP))]


def test_append_updates_the_service_availability_window():
    store = MemoryStore()
    Scheduler(store).enqueue(item('a'), 0)
    control = store.rows['control', CONTROL]
    assert control[f'p{int(Priority.DEEP)}_active'] is True
    assert control[f'p{int(Priority.DEEP)}_batch_available_at'] <= 0


def test_plain_appends_never_stamp_the_probe_backoff():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    queue.enqueue(item('b'), 1000)
    assert 'link_probe_at' not in queue_row(store)


def test_tail_mirror_advances_with_every_append():
    store = MemoryStore()
    queue = Scheduler(store)
    for segment, now in (('a', 0), ('b', 1000), ('c', 2000)):
        queue.enqueue(item(segment), now)
    assert queue_row(store)['head'] == 'a'
    assert queue_row(store)['tail'] == 'c'


# --- conversion from the legacy chain -------------------------------------------------------


def seed_legacy_chain(monkeypatch, segments, *, owner=OWNER):
    kill_switch(monkeypatch)
    store = MemoryStore()
    queue = Scheduler(store)
    for index, segment in enumerate(segments):
        assert queue.enqueue(item(segment, owner=owner, capture=index + 1), index * 1000)
    return store, queue


def test_conversion_stamps_the_array_representation(monkeypatch):
    store, queue = seed_legacy_chain(monkeypatch, ['a', 'b'])
    array_mode(monkeypatch)
    assert queue.enqueue(item('c'), 3000)
    assert queue_row(store)['link_mode'] == 'fifo_array'


def test_conversion_preserves_chain_order(monkeypatch):
    store, queue = seed_legacy_chain(monkeypatch, ['a', 'b', 'c'])
    array_mode(monkeypatch)
    queue.enqueue(item('d'), 3000)
    assert queue_row(store)['items'] == ['a', 'b', 'c', 'd']
    assert queue_row(store)['head'] == 'a' and queue_row(store)['tail'] == 'd'


def test_conversion_of_an_empty_legacy_queue_starts_a_fresh_array(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    array_mode(monkeypatch)
    assert queue.enqueue(item('a'), 0)
    assert queue_row(store)['items'] == ['a']


def test_conversion_vetoes_on_a_missing_chain_row(monkeypatch):
    store, queue = seed_legacy_chain(monkeypatch, ['a', 'b'])
    del store.rows['jobs', 'a']
    array_mode(monkeypatch)
    assert queue.enqueue(item('c'), 3000)
    assert 'link_mode' not in queue_row(store)
    assert 'link_probe_at' in queue_row(store)
    assert queue_row(store)['tail'] == 'c'
    assert store.rows['jobs', 'b']['next'] == 'c'


def test_conversion_vetoes_on_a_tail_mirror_mismatch(monkeypatch):
    store, queue = seed_legacy_chain(monkeypatch, ['a', 'b'])
    store.rows['queues', QUEUE]['tail'] = 'a'
    array_mode(monkeypatch)
    assert queue.enqueue(item('c'), 3000)
    assert 'link_mode' not in queue_row(store)


def test_conversion_vetoes_on_a_chain_cycle(monkeypatch):
    store, queue = seed_legacy_chain(monkeypatch, ['a', 'b'])
    store.rows['jobs', 'b']['next'] = 'a'
    array_mode(monkeypatch)
    assert queue.enqueue(item('c'), 3000)
    assert 'link_mode' not in queue_row(store)


def test_conversion_vetoes_beyond_the_migration_cap(monkeypatch):
    monkeypatch.setattr(scheduler_module, 'FIFO_LINK_MIGRATION_WALK_CAP', 2)
    store, queue = seed_legacy_chain(monkeypatch, ['a', 'b', 'c'])
    array_mode(monkeypatch)
    assert queue.enqueue(item('d'), 3000)
    assert 'link_mode' not in queue_row(store)
    assert store.rows['jobs', 'c']['next'] == 'd'


def test_vetoed_conversion_stamps_a_probe_backoff(monkeypatch):
    store, queue = seed_legacy_chain(monkeypatch, ['a', 'b'])
    store.rows['queues', QUEUE]['tail'] = 'a'
    array_mode(monkeypatch)
    assert queue.enqueue(item('c'), 3000)
    assert queue_row(store)['link_probe_at'] == 3000


def test_probe_backoff_defers_the_next_conversion_attempt(monkeypatch):
    store, queue = seed_legacy_chain(monkeypatch, ['a', 'b'])
    store.rows['queues', QUEUE]['tail'] = 'a'
    array_mode(monkeypatch)
    assert queue.enqueue(item('c'), 3000)
    store.rows['queues', QUEUE]['tail'] = 'b'
    assert queue.enqueue(item('d'), 3000 + FIFO_LINK_PROBE_BACKOFF_SECONDS - 1)
    assert 'link_mode' not in queue_row(store)


def test_probe_backoff_keeps_a_corrupted_queue_working_legacy(monkeypatch):
    store, queue = seed_legacy_chain(monkeypatch, ['a', 'b'])
    # A corrupted link points at a foreign row, so the head walk never ends at
    # the mirrored tail: every conversion attempt vetoes, and the queue keeps
    # serving through the legacy append path it has always used.
    store.rows['jobs', 'a']['next'] = 'foreign'
    store.rows['jobs', 'foreign'] = job_row('foreign', state='dead')
    array_mode(monkeypatch)
    assert queue.enqueue(item('c'), 3000)
    assert queue_row(store)['link_probe_at'] == 3000
    assert 'link_mode' not in queue_row(store)
    # Deferred attempts within the window keep the stamp anchored at the last
    # real conversion attempt; they do not extend the window.
    assert queue.enqueue(item('d'), 3050)
    assert queue_row(store)['link_probe_at'] == 3000
    # Past the window a real attempt re-runs, re-vetoes and re-stamps.
    assert queue.enqueue(item('e'), 3060)
    assert queue_row(store)['link_probe_at'] == 3060
    assert 'link_mode' not in queue_row(store)
    assert queue_row(store).get('items') in (None, [])
    assert queue_row(store)['tail'] == 'e'
    assert store.rows['jobs', 'd']['next'] == 'e'
    assert store.rows['jobs', 'a']['next'] == 'foreign'


def test_conversion_reads_the_chain_but_writes_no_legacy_job_documents(monkeypatch):
    store = RecordingStore()
    queue = Scheduler(store)
    for segment, now in (('a', 0), ('b', 1000)):
        queue.enqueue(item(segment), now)
    store.max_writes = 0
    store.last = None
    del store.rows['queues', QUEUE]
    array_mode(monkeypatch)
    queue.enqueue(item('c'), 2000)
    assert not any(address[0] == 'jobs' and address[1] in ('a', 'b') for address in store.last_writes)


def test_flag_off_never_converts_a_legacy_queue(monkeypatch):
    store, queue = seed_legacy_chain(monkeypatch, ['a', 'b'])
    assert queue.enqueue(item('c'), 2000)
    assert 'link_mode' not in queue_row(store)
    assert store.rows['jobs', 'b']['next'] == 'c'


def test_flag_off_on_an_array_queue_still_drains(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    for segment, now in (('a', 0), ('b', 1000)):
        queue.enqueue(item(segment), now)
    kill_switch(monkeypatch)
    assert [lease.item.segment_id for lease in drain(queue)] == ['a', 'b']
    assert queue_row(store)['items'] == []


# --- straggler absorption (mixed-version rolls) ----------------------------------------------


def chain_straggler(monkeypatch, store, work, now=100000.0):
    """Simulate an older binary chaining onto a converted queue mid-roll."""
    monkeypatch.setenv('BATCH_PIPELINE_FIFO_ARRAY_LINK_ENABLED', 'false')
    try:
        store.run(lambda tx: Scheduler.enqueue_in_transaction(tx, work, now))
    finally:
        monkeypatch.setenv('BATCH_PIPELINE_FIFO_ARRAY_LINK_ENABLED', 'true')


def test_tail_continuation_straggler_is_absorbed_on_the_next_append(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    chain_straggler(monkeypatch, store, item('b'))
    assert queue_row(store)['items'] == ['a']
    assert store.rows['jobs', 'a']['next'] == 'b'
    assert queue_row(store)['tail'] == 'b'
    assert queue.enqueue(item('c'), 101000)
    assert queue_row(store)['items'] == ['a', 'b', 'c']


def test_multi_straggler_chain_is_absorbed_in_order(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    chain_straggler(monkeypatch, store, item('b'))
    chain_straggler(monkeypatch, store, item('c'), 100001)
    assert queue_row(store)['items'] == ['a']
    assert queue.enqueue(item('d'), 101000)
    assert queue_row(store)['items'] == ['a', 'b', 'c', 'd']


def test_head_stray_chain_is_absorbed_when_the_array_is_empty(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(1)[0]
    assert queue.complete(WorkResult('a', 'gs://results/a'), lease.token, 2)
    assert queue.pull(2) == []
    assert queue_row(store).get('items') == [] and queue_row(store)['head'] == ''
    chain_straggler(monkeypatch, store, item('b'), 100000)
    assert queue_row(store)['head'] == 'b' and queue_row(store)['tail'] == 'b'
    assert queue.enqueue(item('c'), 101000)
    assert queue_row(store)['items'] == ['b', 'c']


def test_absorption_is_idempotent_once_the_tail_is_consistent():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    for _ in range(2):
        changed = scheduler_module._fifo_absorb_strays(MemoryTransaction(deepcopy(store.rows)), queue_row(store))
        assert changed is False
    assert queue_row(store)['items'] == ['a']


def test_absorption_stops_at_a_purged_row(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    chain_straggler(monkeypatch, store, item('b'))
    del store.rows['jobs', 'b']
    assert scheduler_module._fifo_absorb_strays(MemoryTransaction(deepcopy(store.rows)), queue_row(store)) is False
    assert queue_row(store)['items'] == ['a']


def test_absorption_overflow_refuses_the_whole_append(monkeypatch):
    monkeypatch.setattr(scheduler_module, 'FIFO_LINK_MIGRATION_WALK_CAP', 1)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    chain_straggler(monkeypatch, store, item('b'))
    store.rows['jobs', 'b']['next'] = 'c'
    store.rows['jobs', 'c'] = job_row('c')
    store.rows['queues', QUEUE]['tail'] = 'c'
    with pytest.raises(RuntimeError, match='fifo link migration chain overflow'):
        queue.enqueue(item('d'), 101000)
    assert queue_row(store)['items'] == ['a']
    assert queue_row(store)['tail'] == 'c'
    assert store.rows['jobs', 'b']['next'] == 'c'


def test_absorption_with_a_foreign_tail_is_refused():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    store.rows['queues', QUEUE]['tail'] = 'not-a-unit'
    assert scheduler_module._fifo_absorb_strays(MemoryTransaction(deepcopy(store.rows)), queue_row(store)) is False
    assert queue_row(store)['items'] == ['a']


def test_walk_absorbs_stragglers_and_leases_them_in_order(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    chain_straggler(monkeypatch, store, item('b'))
    assert [lease.item.segment_id for lease in drain(queue)] == ['a', 'b']
    assert queue_row(store)['items'] == []


def test_walk_absorption_persists_the_array_and_the_tail_mirror(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    chain_straggler(monkeypatch, store, item('b'))
    leases = queue.pull(1, 4)
    assert [lease.item.segment_id for lease in leases] == ['a', 'b']
    assert queue_row(store)['items'] == []
    assert queue_row(store)['tail'] == ''


def test_absorption_updates_the_tail_mirror(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    chain_straggler(monkeypatch, store, item('b'))
    assert queue.enqueue(item('c'), 101000)
    assert queue_row(store)['tail'] == 'c'


def test_legacy_queue_is_never_absorbed():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    rows = deepcopy(store.rows)
    rows['queues', QUEUE].pop('link_mode')
    queue_dict = rows['queues', QUEUE]
    assert scheduler_module._fifo_absorb_strays(MemoryTransaction(rows), queue_dict) is False


def test_absorption_never_reanimates_popped_items(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(1)[0]
    queue.complete(WorkResult('a', 'gs://results/a'), lease.token, 2)
    store.rows['queues', QUEUE]['tail'] = 'a'
    store.rows['jobs', 'a']['next'] = 'ghost'
    assert scheduler_module._fifo_absorb_strays(MemoryTransaction(deepcopy(store.rows)), queue_row(store)) is False
    assert queue_row(store)['items'] == []


# --- walk over the array ---------------------------------------------------------------------


def test_walk_leases_the_array_head_and_advances_the_mirror():
    store = MemoryStore()
    queue = Scheduler(store)
    for segment, now in (('a', 0), ('b', 1000), ('c', 2000)):
        queue.enqueue(item(segment), now)
    assert queue.pull(1)[0].item.segment_id == 'a'
    assert queue_row(store)['items'] == ['b', 'c']
    assert queue_row(store)['head'] == 'b'


def test_array_walk_leases_in_the_same_order_as_the_legacy_chain(monkeypatch):
    orders = {}
    for flag in ('true', 'false'):
        monkeypatch.setenv('BATCH_PIPELINE_FIFO_ARRAY_LINK_ENABLED', flag)
        store = MemoryStore()
        queue = Scheduler(store)
        for index in range(8):
            queue.enqueue(item(f'u{index}', capture=index + 1, duration=30 + 10 * (index % 3)), index * 10)
        orders[flag] = [lease.item.segment_id for lease in drain(queue)]
    assert orders['true'] == orders['false']
    assert len(orders['true']) == 8


def test_multi_lease_off_leases_one_unit_per_pull(monkeypatch):
    monkeypatch.setenv('BATCH_PULL_MULTI_LEASE_ENABLED', 'false')
    store = MemoryStore()
    queue = Scheduler(store)
    for index in range(3):
        queue.enqueue(item(f'o{index}'), index * 1000)
    assert [lease.item.segment_id for lease in drain(queue)] == ['o0', 'o1', 'o2']


def test_emptying_the_array_pops_the_ring_and_resets_the_queue():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    assert queue.pull(1)
    assert queue_row(store)['items'] == []
    assert queue_row(store)['head'] == '' and queue_row(store)['tail'] == ''
    assert QUEUE not in store.rows['control', CONTROL]['rings'][str(int(Priority.DEEP))]


def test_empty_array_queue_rejoins_the_ring_on_a_later_append():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    queue.pull(1)
    queue.enqueue(item('b'), 1000)
    assert QUEUE in store.rows['control', CONTROL]['rings'][str(int(Priority.DEEP))]
    assert queue_row(store)['head'] == 'b'


def test_multi_lease_drains_the_array_in_order():
    store = MemoryStore()
    queue = Scheduler(store, worker_id='w')
    for index in range(6):
        queue.enqueue(item(f'm{index}'), index * 1000)
    leases = queue.pull(1, 4)
    assert [lease.item.segment_id for lease in leases] == ['m0', 'm1', 'm2', 'm3']
    assert queue_row(store)['items'] == ['m4', 'm5']


def test_write_headroom_stops_each_walk_transaction(monkeypatch):
    monkeypatch.setattr(scheduler_module, 'PULL_WRITE_HEADROOM', 2)
    store = RecordingStore()
    queue = Scheduler(store, worker_id='w')
    for index in range(6):
        queue.enqueue(item(f'h{index}'), index * 1000)
    leases = [lease.item.segment_id for lease in drain(queue)]
    assert leases == [f'h{index}' for index in range(6)]
    assert store.max_job_writes < 6


def test_leases_stay_fenced_in_array_mode():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(1)[0]
    job = store.rows['jobs', 'a']
    assert job['state'] == 'leased' and job['token'] == lease.token
    assert job['attempt'] == 1 and job['lease_until'] == 1 + 120.0


def test_stale_tokens_never_heartbeat_complete_fail_or_release():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    queue.pull(1)[0]
    assert not queue.heartbeat('a', 'wrong-token', 2)
    assert not queue.complete(WorkResult('a', 'gs://results/a'), 'wrong-token', 2)
    assert not queue.fail('a', 'wrong-token', 2)
    assert not queue.release('a', 'wrong-token', 2)
    assert store.rows['jobs', 'a']['state'] == 'leased'


def test_retry_requeue_appends_through_the_array():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    queue.pull(1)[0]
    store.rows['jobs', 'a']['lease_until'] = 0.5
    assert queue.recover(1) == 1
    assert store.rows['jobs', 'a']['state'] == 'retry'
    assert queue.recover(7) == 1
    assert store.rows['jobs', 'a']['state'] == 'ready'
    assert queue_row(store)['items'] == ['a']


def test_lease_expiry_requeue_keeps_the_attempt_charged():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    queue.pull(1)[0]
    store.rows['jobs', 'a']['lease_until'] = 0.5
    queue.recover(1)
    assert store.rows['jobs', 'a']['attempt'] == 1


def test_array_lease_increments_attempts_across_requeues():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    assert queue.pull(1)[0].attempt == 1
    store.rows['jobs', 'a']['lease_until'] = 0.5
    queue.recover(1)
    queue.recover(7)
    assert queue.pull(8)[0].attempt == 2


def test_redrive_appends_through_the_array():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(1)[0]
    assert queue.fail('a', lease.token, 1, quarantine=True)
    assert store.rows['jobs', 'a']['state'] == 'quarantined'
    store.rows['jobs', 'a'].update(state='dead', merge_pending=True, failure='')
    assert queue.redrive_dead('a', 10)
    assert store.rows['jobs', 'a']['state'] == 'ready'
    assert queue_row(store)['items'] == ['a']


def test_restore_appends_through_the_array():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(1)[0]
    assert queue_row(store)['items'] == []
    store.rows['jobs', 'a'].update(
        state='quarantined',
        recovery_state='failed_held',
        merge_pending=False,
        lease_until=0.0,
        token='',
        artifact_disposition={'state': 'restored'},
    )
    store.run(lambda tx: Scheduler.restore_audio_in_transaction(tx, tx.get('jobs', 'a'), 10))
    assert store.rows['jobs', 'a']['state'] == 'ready'
    assert queue_row(store)['items'] == ['a']


def test_quarantine_leaves_the_array_untouched():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    queue.enqueue(item('b'), 1000)
    lease = queue.pull(1)[0]
    assert queue.fail('a', lease.token, 2, quarantine=True)
    assert queue_row(store)['items'] == ['b']


def test_unclassified_quarantine_signature_contract_is_unchanged(caplog):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    store.rows['jobs', 'a']['attempt'] = 4
    lease = queue.pull(1)[0]
    with caplog.at_level(logging.ERROR, logger='utils.batch_pipeline.scheduler'):
        assert queue.fail('a', lease.token, 2)
    assert 'reason=worker_failed attempt=5' in caplog.text
    assert 'stage=unknown' in caplog.text
    assert 'worker_reason=unclassified' in caplog.text


# --- head-priority promotion over the array ---------------------------------------------------


def enable_head_priority(monkeypatch, on=True):
    monkeypatch.setenv('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', str(on).lower())


def test_promotion_moves_the_capture_head_to_the_array_front(monkeypatch):
    enable_head_priority(monkeypatch)
    store = MemoryStore()
    queue = Scheduler(store, worker_id='w')
    for index, (segment, capture) in enumerate((('newest', 3), ('older', 2), ('head', 1))):
        queue.enqueue(item(segment, capture=capture), index * 1000)
    assert queue.pull(1)[0].item.segment_id == 'head'
    assert queue_row(store)['items'] == ['newest', 'older']


def test_promotion_never_writes_a_job_document_for_the_splice(monkeypatch):
    enable_head_priority(monkeypatch)
    store = RecordingStore()
    queue = Scheduler(store, worker_id='w')
    for index, (segment, capture) in enumerate((('newest', 3), ('older', 2), ('head', 1))):
        queue.enqueue(item(segment, capture=capture), index * 1000)
    queue.pull(1)
    job_writes = [address for address in store.last_writes if address[0] == 'jobs']
    # The splice itself adds no predecessor write; the promoted unit and the
    # eligibility-passed old head are the only job writes, exactly as the
    # legacy pull already wrote them.
    assert ('jobs', 'older') not in job_writes
    assert ('jobs', 'head') in job_writes
    assert ('jobs', 'newest') in job_writes


def test_flag_off_promotion_still_relinks_the_chain(monkeypatch):
    enable_head_priority(monkeypatch)
    kill_switch(monkeypatch)
    store = MemoryStore()
    queue = Scheduler(store, worker_id='w')
    for index, (segment, capture) in enumerate((('newest', 3), ('older', 2), ('head', 1))):
        queue.enqueue(item(segment, capture=capture), index * 1000)
    assert queue.pull(1)[0].item.segment_id == 'head'
    # Legacy splice: the promoted unit links to the old queue head, the
    # predecessor's pointer closes over it, and the mirror advanced past the
    # lease to the splice's successor.
    assert store.rows['jobs', 'head']['next'] == 'newest'
    assert store.rows['jobs', 'older']['next'] == ''
    assert queue_row(store)['head'] == 'newest'


def test_promotion_removes_the_head_from_mid_array(monkeypatch):
    enable_head_priority(monkeypatch)
    store = MemoryStore()
    queue = Scheduler(store, worker_id='w')
    for index, (segment, capture) in enumerate((('n1', 4), ('n2', 3), ('head', 1), ('n4', 2))):
        queue.enqueue(item(segment, capture=capture), index * 1000)
    assert queue.pull(1)[0].item.segment_id == 'head'
    assert queue_row(store)['items'] == ['n1', 'n2', 'n4']


def test_promotion_updates_the_tail_mirror_when_the_head_was_last(monkeypatch):
    enable_head_priority(monkeypatch)
    store = MemoryStore()
    queue = Scheduler(store, worker_id='w')
    queue.enqueue(item('at_tail', capture=9), 0)
    queue.enqueue(item('head', capture=1), 1000)
    assert queue.pull(1)[0].item.segment_id == 'head'
    assert queue_row(store)['tail'] == 'at_tail'


def test_promotion_skips_a_stale_next_pointer_in_array_mode(monkeypatch):
    enable_head_priority(monkeypatch)
    store = MemoryStore()
    queue = Scheduler(store, worker_id='w')
    queue.enqueue(item('newest', capture=2), 0)
    queue.enqueue(item('head', capture=1), 1000)
    store.rows['jobs', 'newest']['next'] = 'stale-elsewhere'
    assert queue.pull(1)[0].item.segment_id == 'head'
    assert queue_row(store)['items'] == ['newest']


def test_flag_off_promotion_still_requires_the_live_next_pointer(monkeypatch):
    enable_head_priority(monkeypatch)
    kill_switch(monkeypatch)
    store = MemoryStore()
    queue = Scheduler(store, worker_id='w')
    queue.enqueue(item('newest', capture=2), 0)
    queue.enqueue(item('head', capture=1), 1000)
    store.rows['jobs', 'newest']['next'] = 'stale-elsewhere'
    assert queue.pull(1)[0].item.segment_id == 'newest'


def test_promotion_budget_still_guards_the_array(monkeypatch):
    enable_head_priority(monkeypatch)
    monkeypatch.setattr(scheduler_module, 'HEAD_OWNER_BUDGET', 0)
    store = MemoryStore()
    queue = Scheduler(store, worker_id='w')
    for index, (segment, capture) in enumerate((('newest', 3), ('older', 2), ('head', 1))):
        queue.enqueue(item(segment, capture=capture), index * 1000)
    assert queue.pull(1)[0].item.segment_id == 'newest'


def test_head_priority_off_keeps_array_fifo_order(monkeypatch):
    enable_head_priority(monkeypatch, on=False)
    store = MemoryStore()
    queue = Scheduler(store, worker_id='w')
    for index, (segment, capture) in enumerate((('newest', 3), ('older', 2), ('head', 1))):
        queue.enqueue(item(segment, capture=capture), index * 1000)
    assert queue.pull(1)[0].item.segment_id == 'newest'


def test_promotion_inside_one_multi_lease_transaction(monkeypatch):
    enable_head_priority(monkeypatch)
    store = MemoryStore()
    queue = Scheduler(store, worker_id='w')
    for index, (segment, capture) in enumerate((('new1', 3), ('new2', 2), ('head', 1))):
        queue.enqueue(item(segment, capture=capture), index * 1000)
    leased = [lease.item.segment_id for lease in queue.pull(1, 3)]
    assert leased[0] == 'head'
    assert sorted(leased) == ['head', 'new1', 'new2']


def test_no_promotion_when_the_array_predecessor_is_leased(monkeypatch):
    enable_head_priority(monkeypatch)
    store = MemoryStore()
    queue = Scheduler(store, worker_id='w')
    queue.enqueue(item('newest', capture=2), 0)
    queue.enqueue(item('head', capture=1), 1000)
    store.rows['jobs', 'newest']['state'] = 'leased'
    assert queue.pull(1)[0].item.segment_id == 'newest'


def test_already_front_head_is_never_promoted_again(monkeypatch):
    enable_head_priority(monkeypatch)
    store = MemoryStore()
    queue = Scheduler(store, worker_id='w')
    queue.enqueue(item('head', capture=1), 0)
    queue.enqueue(item('newer', capture=2), 1000)
    assert queue.pull(1)[0].item.segment_id == 'head'
    assert queue_row(store)['items'] == ['newer']


def test_promotion_over_a_just_converted_queue(monkeypatch):
    store, queue = seed_legacy_chain(monkeypatch, ['newest', 'older', 'head'])
    for index, segment in enumerate(('newest', 'older', 'head')):
        store.rows['jobs', segment]['capture_at'] = 3 - index
    enable_head_priority(monkeypatch)
    array_mode(monkeypatch)
    assert queue.enqueue(item('tail-unit', capture=4), 3000)
    assert queue_row(store)['items'] == ['newest', 'older', 'head', 'tail-unit']
    assert queue.pull(1)[0].item.segment_id == 'head'
    assert queue_row(store)['items'] == ['newest', 'older', 'tail-unit']


# --- bundle admission through one transaction --------------------------------------------------


def admit_bundle(store, segments, now=100000.0):
    def body(tx):
        return [
            Scheduler.enqueue_in_transaction(tx, item(segment, capture=index + 1), now)
            for index, segment in enumerate(segments)
        ]

    return store.run(body)


def test_bundle_appends_every_unit_in_one_transaction():
    store = RecordingStore()
    assert admit_bundle(store, [f'b{index}' for index in range(8)])
    assert queue_row(store)['items'] == [f'b{index}' for index in range(8)]


def test_bundle_coalesces_queue_and_control_writes():
    store = RecordingStore()
    admit_bundle(store, [f'b{index}' for index in range(8)])
    assert sum(1 for address in store.last_writes if address[0] == 'queues') == 1
    assert sum(1 for address in store.last_writes if address[0] == 'control') == 1


def test_bundle_never_reads_a_preexisting_tail_job_document():
    store = RecordingStore()
    Scheduler(store).enqueue(item('seed'), 0)
    admit_bundle(store, ['b0', 'b1'])
    assert ('jobs', 'seed') not in store.last_reads


def test_bundle_stays_far_below_the_transaction_write_budget():
    store = RecordingStore()
    admit_bundle(store, [f'b{index}' for index in range(128)])
    assert len(store.last_writes) <= 140


def test_bundle_order_survives_conversion_of_a_legacy_queue(monkeypatch):
    store, queue = seed_legacy_chain(monkeypatch, ['old-a', 'old-b'])
    array_mode(monkeypatch)
    admit_bundle(store, ['new-1', 'new-2'])
    assert queue_row(store)['items'] == ['old-a', 'old-b', 'new-1', 'new-2']


def test_bundle_on_a_straggler_queue_absorbs_before_appending(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    chain_straggler(monkeypatch, store, item('s1'))
    admit_bundle(store, ['n1'])
    assert queue_row(store)['items'] == ['a', 's1', 'n1']


def test_bundle_duplicates_are_refused_without_array_growth():
    store = RecordingStore()
    admit_bundle(store, ['dup'])
    assert not Scheduler(store).enqueue(item('dup'), 101000)
    assert queue_row(store)['items'] == ['dup']


def test_128_unit_bundle_preserves_order_end_to_end():
    store = MemoryStore()
    queue = Scheduler(store, worker_id='w')
    segments = [f'big{index:03d}' for index in range(128)]
    admit_bundle(store, segments)
    assert [lease.item.segment_id for lease in drain(queue)] == segments


def test_bundle_after_full_drain_rejoins_the_ring():
    store = MemoryStore()
    queue = Scheduler(store, worker_id='w')
    admit_bundle(store, ['only'])
    assert [lease.item.segment_id for lease in drain(queue)] == ['only']
    assert QUEUE not in store.rows['control', CONTROL]['rings'][str(int(Priority.DEEP))]
    admit_bundle(store, ['again'])
    assert QUEUE in store.rows['control', CONTROL]['rings'][str(int(Priority.DEEP))]


def test_mixed_priority_bundle_lands_in_two_arrays():
    store = RecordingStore()
    fresh = replace(item('fresh-one', owner=OWNER), priority=Priority.FRESH)
    deep = item('deep-one', owner=OWNER)

    def body(tx):
        return [
            Scheduler.enqueue_in_transaction(tx, fresh, 100000),
            Scheduler.enqueue_in_transaction(tx, deep, 100000),
        ]

    assert store.run(body) == [True, True]
    assert (store.rows.get(('queues', FRESH_QUEUE)) or {}).get('items') == ['fresh-one']
    assert queue_row(store)['items'] == ['deep-one']


def test_bundle_within_a_vetoed_probe_window_stays_legacy_consistent(monkeypatch):
    store, queue = seed_legacy_chain(monkeypatch, ['a', 'b'])
    store.rows['queues', QUEUE]['tail'] = 'a'
    array_mode(monkeypatch)
    admit_bundle(store, ['v1'])
    assert 'link_mode' not in queue_row(store)
    assert store.rows['jobs', 'a']['next'] == 'v1'
    assert queue_row(store)['tail'] == 'v1'
    assert 'link_probe_at' in queue_row(store)


# --- the real FirestoreTransaction predecessor --------------------------------------------------


class TinySnapshot:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return deepcopy(self._data) if self._data else {}


class TinyDoc:
    def __init__(self, rows, address):
        self._rows, self._address = rows, address

    @property
    def id(self):
        return self._address[1]

    @property
    def reference(self):
        return self

    def get(self, transaction=None):
        return TinySnapshot(self._rows.get(self._address))

    def set(self, value):
        self._rows[self._address] = deepcopy(value)

    def update(self, fields):
        self._rows.setdefault(self._address, {}).update(deepcopy(fields))

    def delete(self):
        self._rows.pop(self._address, None)

    def to_dict(self):
        return deepcopy(self._rows.get(self._address) or {})

    def collection(self, name):
        raise AssertionError('documents do not own collections in this fake')


class TinyQuery:
    def __init__(self, rows, table, filters=()):
        self._rows, self._table, self._filters = rows, table, tuple(filters)
        self._order = None
        self._limit = None

    def where(self, field=None, operator=None, value=None, filter=None):
        if filter is not None:
            assert filter.op_string == '=='
            return TinyQuery(self._rows, self._table, (*self._filters, (filter.field_path, filter.value)))
        assert operator == '=='
        return TinyQuery(self._rows, self._table, (*self._filters, (field, value)))

    def order_by(self, name):
        query = TinyQuery(self._rows, self._table, self._filters)
        query._order = name
        return query

    def limit(self, size):
        query = TinyQuery(self._rows, self._table, self._filters)
        query._order, query._limit = self._order, size
        return query

    def stream(self, transaction=None):
        docs = [TinyDoc(self._rows, (self._table, key)) for (table, key) in sorted(self._rows) if table == self._table]
        for field, value in self._filters:
            docs = [doc for doc in docs if doc.to_dict().get(field) == value]
        if self._order == '__name__':
            docs.sort(key=lambda doc: doc.id)
        return docs[: self._limit] if self._limit is not None else docs


class TinyCollection:
    def __init__(self, rows, namespace, name):
        prefix = f'{namespace}_'
        assert name.startswith(prefix)
        self._rows, self._table = rows, name[len(prefix) :]

    def document(self, key):
        return TinyDoc(self._rows, (self._table, key))

    def where(self, field=None, operator=None, value=None, filter=None):
        return TinyQuery(self._rows, self._table).where(field, operator, value, filter=filter)


class TinyClient:
    def __init__(self, rows, namespace):
        self._rows, self._namespace = rows, namespace

    def collection(self, name):
        return TinyCollection(self._rows, self._namespace, name)

    def transaction(self, max_attempts: int | None = None):
        return TinyFirestoreTransaction()


class TinyFirestoreTransaction:
    _read_only = False
    _max_attempts = 1
    _id = b'fake-transaction-id'

    def _begin(self, retry_id=None):
        pass

    def _rollback(self):
        pass

    def _commit(self):
        pass

    def _clean_up(self):
        pass

    def set(self, reference, value):
        reference.set(value)

    def update(self, reference, fields):
        reference.update(fields)

    def delete(self, reference):
        reference.delete()


NAMESPACE = 'batch_pipeline_test_unit'


class RowsStore(MemoryStore):
    def __init__(self, rows):
        super().__init__()
        self.rows = rows


def array_tx(rows):
    return FirestoreTransaction(TinyClient(rows, NAMESPACE), NAMESPACE, TinyFirestoreTransaction())


def array_queue_rows(segments):
    return {
        ('queues', QUEUE): {
            'link_mode': 'fifo_array',
            'items': list(segments),
            'head': segments[0] if segments else '',
            'tail': segments[-1] if segments else '',
            'deficit': 0.0,
            'continuing': False,
        }
    }


def job_row(segment, state='ready', *, next_link=None):
    row = {
        'segment_id': segment,
        'owner_id': OWNER,
        'owner_key': KEY,
        'priority': int(Priority.DEEP),
        'state': state,
        'merge_pending': True,
        'capture_at': 1,
    }
    if next_link is not None:
        row['next'] = next_link
    return row


def test_real_transaction_predecessor_returns_the_array_predecessor():
    rows = array_queue_rows(['a', 'b', 'c'])
    for segment in ('a', 'b', 'c'):
        rows[('jobs', segment)] = job_row(segment)
    predecessor = array_tx(rows).ready_predecessor(KEY, int(Priority.DEEP), 'c')
    assert predecessor and predecessor['segment_id'] == 'b'


def test_real_transaction_predecessor_of_the_first_item_is_none():
    rows = array_queue_rows(['a', 'b'])
    rows[('jobs', 'a')] = job_row('a')
    assert array_tx(rows).ready_predecessor(KEY, int(Priority.DEEP), 'a') is None


def test_real_transaction_predecessor_unknown_segment_falls_back_and_returns_none():
    rows = array_queue_rows(['a', 'b'])
    rows[('jobs', 'a')] = job_row('a')
    rows[('jobs', 'b')] = job_row('b')
    assert array_tx(rows).ready_predecessor(KEY, int(Priority.DEEP), 'ghost') is None


def test_real_transaction_predecessor_requires_a_ready_predecessor():
    rows = array_queue_rows(['a', 'b'])
    rows[('jobs', 'a')], rows[('jobs', 'b')] = job_row('a', state='leased'), job_row('b')
    assert array_tx(rows).ready_predecessor(KEY, int(Priority.DEEP), 'b') is None


def test_real_transaction_predecessor_requires_a_priority_match():
    rows = array_queue_rows(['a', 'b'])
    rows[('jobs', 'a')], rows[('jobs', 'b')] = job_row('a'), job_row('b')
    rows[('jobs', 'a')]['priority'] = int(Priority.FRESH)
    assert array_tx(rows).ready_predecessor(KEY, int(Priority.DEEP), 'b') is None


def test_real_transaction_predecessor_requires_an_owner_match():
    rows = array_queue_rows(['a', 'b'])
    rows[('jobs', 'a')], rows[('jobs', 'b')] = job_row('a'), job_row('b')
    rows[('jobs', 'a')]['owner_key'] = owner_key('someone-else')
    assert array_tx(rows).ready_predecessor(KEY, int(Priority.DEEP), 'b') is None


def test_real_transaction_predecessor_sees_buffered_queue_writes():
    rows = array_queue_rows(['a', 'b'])
    rows[('jobs', 'a')], rows[('jobs', 'b')] = job_row('a'), job_row('b')
    rows[('jobs', 'c')] = job_row('c')
    tx = array_tx(rows)
    tx.put('queues', QUEUE, dict(rows['queues', QUEUE], items=['a', 'b', 'c'], tail='c'))
    tx.put('jobs', 'c', rows[('jobs', 'c')])
    assert tx.ready_predecessor(KEY, int(Priority.DEEP), 'c')['segment_id'] == 'b'


def test_real_transaction_predecessor_sees_a_buffered_ready_transition():
    rows = array_queue_rows(['a', 'b'])
    rows[('jobs', 'a')], rows[('jobs', 'b')] = job_row('a', state='leased'), job_row('b')
    tx = array_tx(rows)
    tx.put('jobs', 'a', dict(rows[('jobs', 'a')], state='ready'))
    assert tx.ready_predecessor(KEY, int(Priority.DEEP), 'b')['segment_id'] == 'a'


def test_real_transaction_predecessor_on_a_legacy_queue_uses_the_index_query():
    rows = {
        ('queues', QUEUE): {'head': 'a', 'tail': 'b', 'deficit': 0.0, 'continuing': False},
        ('jobs', 'a'): job_row('a', next_link='b'),
        ('jobs', 'b'): job_row('b'),
    }
    assert array_tx(rows).ready_predecessor(KEY, int(Priority.DEEP), 'b')['segment_id'] == 'a'


def test_real_transaction_predecessor_two_matches_fail_closed():
    rows = {
        ('queues', QUEUE): {'head': 'a', 'tail': 'b', 'deficit': 0.0, 'continuing': False},
        ('jobs', 'a'): job_row('a', next_link='b'),
        ('jobs', 'b'): job_row('b', next_link='b'),
    }
    assert array_tx(rows).ready_predecessor(KEY, int(Priority.DEEP), 'b') is None


def test_real_transaction_predecessor_with_an_absent_queue_falls_back():
    rows = {('jobs', 'b'): job_row('b')}
    assert array_tx(rows).ready_predecessor(KEY, int(Priority.DEEP), 'b') is None


def test_real_transaction_predecessor_coerces_string_priority_into_the_queue_key():
    rows = array_queue_rows(['a', 'b'])
    rows[('jobs', 'a')], rows[('jobs', 'b')] = job_row('a'), job_row('b')
    assert array_tx(rows).ready_predecessor(KEY, str(int(Priority.DEEP)), 'b')['segment_id'] == 'a'


def test_module_ready_predecessor_keeps_the_state_ready_and_next_filters():
    rows = {
        ('jobs', 'a'): job_row('a', next_link='b'),
        ('jobs', 'b'): job_row('b'),
        ('jobs', 'c'): job_row('c', next_link='b', state='committed'),
    }
    from database.batch_pipeline_store import ready_predecessor as module_ready_predecessor

    found = module_ready_predecessor(TinyClient(rows, NAMESPACE), NAMESPACE, KEY, int(Priority.DEEP), 'b')
    assert found and found['segment_id'] == 'a'
    rows[('jobs', 'a')]['state'] = 'leased'
    assert module_ready_predecessor(TinyClient(rows, NAMESPACE), NAMESPACE, KEY, int(Priority.DEEP), 'b') is None


# --- purge unlink over the array -----------------------------------------------------------------


def purge_snapshot(rows, segment):
    return TinyDoc(rows, ('jobs', segment))


def test_purge_unlinks_an_array_row_and_repairs_the_mirrors():
    rows = array_queue_rows(['a', 'b', 'c'])
    for segment in ('a', 'b', 'c'):
        rows[('jobs', segment)] = job_row(segment)
    rows[('owners', KEY)] = {}
    store = RowsStore(rows)
    _delete_job(TinyClient(store.rows, NAMESPACE), NAMESPACE, purge_snapshot(store.rows, 'b'), retain_ordering=False)
    queue = store.rows['queues', QUEUE]
    assert queue['items'] == ['a', 'c']
    assert queue['head'] == 'a' and queue['tail'] == 'c'
    assert ('jobs', 'b') not in store.rows


def test_purge_of_the_array_head_advances_the_mirror():
    rows = array_queue_rows(['a', 'b'])
    rows[('jobs', 'a')], rows[('jobs', 'b')] = job_row('a'), job_row('b')
    rows[('owners', KEY)] = {}
    store = RowsStore(rows)
    _delete_job(TinyClient(store.rows, NAMESPACE), NAMESPACE, purge_snapshot(store.rows, 'a'), retain_ordering=False)
    queue = store.rows['queues', QUEUE]
    assert queue['head'] == 'b' and queue['tail'] == 'b'


def test_purge_of_the_last_array_row_removes_the_queue_and_the_ring():
    rows = array_queue_rows(['a'])
    rows[('jobs', 'a')] = job_row('a')
    rows[('owners', KEY)] = {}
    rows[('control', CONTROL)] = {'rings': {str(int(Priority.DEEP)): [QUEUE]}}
    store = RowsStore(rows)
    _delete_job(TinyClient(store.rows, NAMESPACE), NAMESPACE, purge_snapshot(store.rows, 'a'), retain_ordering=False)
    assert ('queues', QUEUE) not in store.rows
    assert QUEUE not in store.rows['control', CONTROL]['rings'][str(int(Priority.DEEP))]


def test_array_purge_never_rewrites_a_predecessors_next_pointer():
    rows = array_queue_rows(['a', 'b'])
    rows[('jobs', 'a')], rows[('jobs', 'b')] = job_row('a'), job_row('b')
    rows[('owners', KEY)] = {}
    store = RowsStore(rows)
    before = deepcopy(store.rows['jobs', 'a'])
    _delete_job(TinyClient(store.rows, NAMESPACE), NAMESPACE, purge_snapshot(store.rows, 'b'), retain_ordering=False)
    assert store.rows['jobs', 'a'] == before


def test_array_purge_with_retain_ordering_writes_the_erased_marker():
    rows = array_queue_rows(['a', 'b'])
    rows[('jobs', 'a')], rows[('jobs', 'b')] = job_row('a'), job_row('b')
    rows[('results', 'b')] = {
        'segment_id': 'b',
        'owner_key': KEY,
        'capture_at': 1,
        'protocol_version': 1,
        'log_sequence': 1,
        'result_uri': 'gs://results/b',
    }
    rows[('owners', KEY)] = {}
    store = RowsStore(rows)
    _delete_job(TinyClient(store.rows, NAMESPACE), NAMESPACE, purge_snapshot(store.rows, 'b'), retain_ordering=True)
    marker = store.rows['results', 'b']
    assert marker['projection_state'] == 'erased'
    assert 'result_uri' not in marker
    assert marker['segment_id'] == 'b'


def test_array_purge_keeps_the_owners_row_when_not_retaining():
    rows = array_queue_rows(['a'])
    rows[('jobs', 'a')] = job_row('a')
    rows[('owners', KEY)] = {'revision': 7}
    store = RowsStore(rows)
    _delete_job(TinyClient(store.rows, NAMESPACE), NAMESPACE, purge_snapshot(store.rows, 'a'), retain_ordering=False)
    assert ('owners', KEY) not in store.rows or store.rows['owners', KEY].get('revision') == 7


def test_legacy_purge_keeps_the_chain_unlink(monkeypatch):
    kill_switch(monkeypatch)
    store = MemoryStore()
    queue = Scheduler(store)
    for segment, now in (('a', 0), ('b', 1000), ('c', 2000)):
        queue.enqueue(item(segment), now)
    store.rows['jobs', 'b']['state'] = 'dead'
    _delete_job(TinyClient(store.rows, NAMESPACE), NAMESPACE, purge_snapshot(store.rows, 'b'), retain_ordering=False)
    assert store.rows['jobs', 'a']['next'] == 'c'
    assert queue_row(store)['head'] == 'a' and queue_row(store)['tail'] == 'c'


def test_array_purge_of_a_mid_roll_straggler_stops_at_the_purged_row(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    chain_straggler(monkeypatch, store, item('b'))
    store.rows['jobs', 'b']['state'] = 'dead'
    _delete_job(TinyClient(store.rows, NAMESPACE), NAMESPACE, purge_snapshot(store.rows, 'b'), retain_ordering=False)
    assert queue_row(store)['items'] == ['a']
    assert scheduler_module._fifo_absorb_strays(MemoryTransaction(deepcopy(store.rows)), queue_row(store)) is False


# --- end-to-end: streaming owners over the array ---------------------------------------------


def test_streaming_session_through_the_array_stays_order_true():
    store = MemoryStore()
    queue = Scheduler(store)
    merge = OrderedMerge(store, head_wait_seconds=W)
    queue.enqueue(item('u1', capture=1), 0)
    lease = queue.pull(1)[0]
    queue.enqueue(item('u2', capture=2), 1000)
    queue.heartbeat('u1', lease.token, 10)
    assert queue.complete(WorkResult('u1', 'gs://results/u1'), lease.token, 20)
    assert merge.commit_next(OWNER, 20)['segment_id'] == 'u1'
    lease2 = queue.pull(21)[0]
    assert lease2.item.segment_id == 'u2'
    assert queue.complete(WorkResult('u2', 'gs://results/u2'), lease2.token, 40)
    entry = merge.commit_next(OWNER, 41)
    owner = store.rows['owners', KEY]
    assert entry['segment_id'] == 'u2'
    assert owner['log_tail'] == 'u2' and owner['log_sequence'] == 2


def test_failed_streaming_unit_requeues_behind_its_successor():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('u1', capture=1), 0)
    lease = queue.pull(1)[0]
    queue.enqueue(item('u2', capture=2), 1000)
    assert queue.fail('u1', lease.token, 6)
    assert store.rows['jobs', 'u1']['state'] == 'retry'
    assert queue_row(store)['items'] == ['u2']
    store.rows['jobs', 'u1']['available_at'] = 10
    queue.recover(11)
    assert queue_row(store)['items'] == ['u2', 'u1']
    assert queue.pull(12)[0].item.segment_id == 'u2'
    assert queue.pull(13)[0].item.segment_id == 'u1'


def test_the_streaming_lane_never_crosses_the_appends_and_completions():
    store = RecordingStore()
    queue = Scheduler(store)
    queue.enqueue(item('u1'), 0)
    lease = queue.pull(1)[0]
    queue.enqueue(item('u2'), 1000)
    append_touch = store.last_reads | store.last_writes
    queue.complete(WorkResult('u1', 'gs://results/u1'), lease.token, 1001)
    complete_touch = store.last_reads | store.last_writes
    assert ('jobs', 'u1') not in append_touch
    assert ('jobs', 'u2') not in complete_touch


def test_two_owners_stream_independently_over_arrays():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a1', owner='heavy', capture=1), 0)
    queue.enqueue(item('b1', owner='light', capture=1), 1000)
    queue.enqueue(item('a2', owner='heavy', capture=2), 2000)
    queue.enqueue(item('b2', owner='light', capture=2), 3000)
    leased = [lease.item.segment_id for lease in drain(queue)]
    assert sorted(leased) == ['a1', 'a2', 'b1', 'b2']
    # Each owner's own FIFO order survives the shard layout.
    assert leased.index('a1') < leased.index('a2')
    assert leased.index('b1') < leased.index('b2')


def test_flag_flip_mid_session_drains_and_keeps_appending(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a', capture=1), 0)
    queue.enqueue(item('b', capture=2), 1000)
    kill_switch(monkeypatch)
    assert [lease.item.segment_id for lease in drain(queue)] == ['a', 'b']
    array_mode(monkeypatch)
    assert queue.enqueue(item('c', capture=3), 5000)
    assert [lease.item.segment_id for lease in drain(queue)] == ['c']


def test_quarantine_then_redrive_cycle_over_the_array():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(1)[0]
    assert queue.fail('a', lease.token, 1, quarantine=True)
    store.rows['jobs', 'a'].update(state='dead', merge_pending=True, failure='')
    assert queue.redrive_dead('a', 10)
    lease2 = queue.pull(11)[0]
    assert lease2.item.segment_id == 'a'
    assert store.rows['jobs', 'a']['attempt'] == 2


def test_kill_switch_full_session_matches_the_array_order(monkeypatch):
    orders = {}
    for flag in ('true', 'false'):
        monkeypatch.setenv('BATCH_PIPELINE_FIFO_ARRAY_LINK_ENABLED', flag)
        store = MemoryStore()
        queue = Scheduler(store)
        merge = OrderedMerge(store, head_wait_seconds=W)
        for index in range(4):
            queue.enqueue(item(f'k{index}', capture=index + 1), index * 1000)
        committed, now = [], 10
        while True:
            leases = queue.pull(now)
            if not leases:
                break
            for lease in leases:
                assert queue.complete(
                    WorkResult(lease.item.segment_id, f'gs://results/{lease.item.segment_id}'), lease.token, now
                )
                entry = merge.commit_next(OWNER, now)
                if entry:
                    committed.append(entry['segment_id'])
            now += 1
        orders[flag] = committed
    assert orders['true'] == orders['false'] == ['k0', 'k1', 'k2', 'k3']


# --- label completeness and mirror-consistency pins ---------------------------------------------


def test_redrive_dead_runs_under_its_own_label():
    store = LabeledStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    store.rows['jobs', 'a'].update(state='dead', merge_pending=True, failure='')
    assert queue.redrive_dead('a', 10)
    assert 'batch_redrive' in store.labels


def test_gpu_release_runs_under_its_own_label():
    store = LabeledStore()
    queue = Scheduler(store)
    store.rows['gpus', owner_key('gpu-1')] = {'token': 'tok', 'lease_until': 10.0}
    assert queue.acknowledge_gpu_idle('gpu-1', 'tok')
    assert 'batch_gpu_release' in store.labels


def test_probe_window_constant_is_one_minute():
    assert FIFO_LINK_PROBE_BACKOFF_SECONDS == 60.0


def test_empty_ring_pull_never_opens_a_write_transaction():
    store = LabeledStore()
    queue = Scheduler(store, worker_id='w')
    assert queue.pull(1) == []
    assert store.labels == []


def test_complete_twice_is_idempotent_and_keeps_the_array():
    store = RecordingStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(1)[0]
    assert queue.complete(WorkResult('a', 'gs://results/a'), lease.token, 2)
    store.last = None
    assert queue.complete(WorkResult('a', 'gs://results/a'), lease.token, 3)
    assert store.last_writes == set()
    assert queue_row(store)['items'] == []


def test_fail_after_complete_is_fenced():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(1)[0]
    assert queue.complete(WorkResult('a', 'gs://results/a'), lease.token, 2)
    assert not queue.fail('a', lease.token, 3)
    assert store.rows['jobs', 'a']['state'] == 'result_ready'


def test_quarantine_never_moves_the_array_mirrors():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    queue.enqueue(item('b'), 1000)
    lease = queue.pull(1)[0]
    queue.fail('a', lease.token, 2, quarantine=True)
    assert queue_row(store)['head'] == 'b'
    assert queue_row(store)['tail'] == 'b'


def test_predecessor_after_straggler_absorption_resolves_through_the_array(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store, worker_id='w')
    queue.enqueue(item('a', capture=2), 0)
    chain_straggler(monkeypatch, store, item('b', capture=1))
    assert queue.enqueue(item('c', capture=3), 100000)
    assert queue_row(store)['items'] == ['a', 'b', 'c']
    store.rows['jobs', 'a']['state'] = 'ready'
    store.rows['jobs', 'b']['state'] = 'ready'
    store.rows['jobs', 'c']['state'] = 'ready'
    tx = RecordingTransaction(deepcopy(store.rows))
    tx.put('jobs', 'a', store.rows['jobs', 'a'])
    tx.put('jobs', 'b', store.rows['jobs', 'b'])
    tx.put('jobs', 'c', store.rows['jobs', 'c'])
    assert tx.ready_predecessor(KEY, int(Priority.DEEP), 'c')['segment_id'] == 'b'


def test_promotion_then_fifo_continues_in_capture_order(monkeypatch):
    enable_head_priority(monkeypatch)
    store = MemoryStore()
    queue = Scheduler(store, worker_id='w')
    for index, (segment, capture) in enumerate((('new1', 3), ('new2', 2), ('head', 1))):
        queue.enqueue(item(segment, capture=capture), index * 1000)
    leased = [lease.item.segment_id for lease in drain(queue)]
    # Only the capture head jumps the queue; the rest drains in upload order
    # and OrderedMerge alone enforces capture-order commits.
    assert leased == ['head', 'new1', 'new2']


def test_enqueue_label_is_independent_of_the_representation_flag(monkeypatch):
    kill_switch(monkeypatch)
    store = LabeledStore()
    assert Scheduler(store).enqueue(item('a'), 0)
    assert store.labels == ['batch_enqueue']


def test_array_mirrors_never_disagree_with_the_items_after_a_mixed_session(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store, worker_id='w')
    queue.enqueue(item('a', capture=3), 0)
    queue.enqueue(item('head', capture=1), 1000)
    enable_head_priority(monkeypatch)
    chain_straggler(monkeypatch, store, item('s1', capture=4))
    queue.enqueue(item('tail', capture=5), 101000)
    lease = queue.pull(1)[0]
    assert lease.item.segment_id == 'head'
    items = queue_row(store)['items']
    assert queue_row(store)['head'] == items[0]
    assert queue_row(store)['tail'] == items[-1]
    assert items == ['a', 's1', 'tail']


# --- deeper parity pins -----------------------------------------------------------------------


def test_array_purge_skips_the_predecessor_index_query_entirely(monkeypatch):
    rows = array_queue_rows(['a', 'b'])
    rows[('jobs', 'a')], rows[('jobs', 'b')] = job_row('a'), job_row('b')
    rows[('owners', KEY)] = {}

    class ExplodingQueries:
        @staticmethod
        def predecessor_documents(*args, **kwargs):
            raise AssertionError('array purge must not query the next-pointer index')

    monkeypatch.setattr('database.batch_pipeline_purge.queries', ExplodingQueries)
    store = RowsStore(rows)
    _delete_job(TinyClient(store.rows, NAMESPACE), NAMESPACE, purge_snapshot(store.rows, 'b'), retain_ordering=False)
    assert store.rows['queues', QUEUE]['items'] == ['a']


def test_legacy_purge_ownership_mismatch_still_fails_closed(monkeypatch):
    kill_switch(monkeypatch)
    store = MemoryStore()
    queue = Scheduler(store)
    for segment, now in (('a', 0), ('b', 1000)):
        queue.enqueue(item(segment), now)
    foreign = deepcopy(store.rows['jobs', 'b'])
    foreign['owner_key'] = owner_key('someone-else')
    store.rows['jobs', 'b'] = foreign
    with pytest.raises(RuntimeError, match='batch queue ownership mismatch'):
        _delete_job(
            TinyClient(store.rows, NAMESPACE), NAMESPACE, purge_snapshot(store.rows, 'b'), retain_ordering=False
        )
    assert ('jobs', 'b') in store.rows


def test_bundle_across_two_owners_lands_two_arrays_and_two_control_docs():
    store = RecordingStore()

    def body(tx):
        return [
            Scheduler.enqueue_in_transaction(tx, item('x', owner='heavy', capture=1), 100000),
            Scheduler.enqueue_in_transaction(tx, item('y', owner='light', capture=1), 100000),
        ]

    assert store.run(body) == [True, True]
    assert queue_row(store)['items'] == ['x']
    assert (store.rows.get(('queues', LIGHT_QUEUE)) or {}).get('items') == ['y']
    assert sum(1 for address in store.last_writes if address[0] == 'control') == 2


def test_head_stray_multi_entry_chain_is_absorbed_in_order(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), 0)
    lease = queue.pull(1)[0]
    queue.complete(WorkResult('a', 'gs://results/a'), lease.token, 2)
    queue.pull(2)
    chain_straggler(monkeypatch, store, item('b'))
    chain_straggler(monkeypatch, store, item('c'), 100001)
    assert queue_row(store).get('items') in (None, [])
    assert queue.enqueue(item('d'), 101000)
    assert queue_row(store)['items'] == ['b', 'c', 'd']


def test_conversion_preserves_order_with_a_leased_chain_member(monkeypatch):
    store, queue = seed_legacy_chain(monkeypatch, ['a', 'b', 'c'])
    store.rows['jobs', 'b']['state'] = 'leased'
    array_mode(monkeypatch)
    assert queue.enqueue(item('d'), 2000)
    assert queue_row(store)['items'] == ['a', 'b', 'c', 'd']
    assert store.rows['jobs', 'b']['state'] == 'leased'


def test_converted_chain_drains_in_one_multi_lease_transaction(monkeypatch):
    store, queue = seed_legacy_chain(monkeypatch, ['a', 'b', 'c'])
    array_mode(monkeypatch)
    assert queue.enqueue(item('d'), 2000)
    assert queue_row(store)['link_mode'] == 'fifo_array'
    leases = queue.pull(1, 4)
    assert [lease.item.segment_id for lease in leases] == ['a', 'b', 'c', 'd']


def test_store_operation_accepts_registry_style_numeric_labels():
    with store_operation('batch_v2_probe'):
        assert current_operation() == 'batch_v2_probe'
    assert current_operation() is None


def test_absorbed_queue_leases_absorbed_units_in_the_same_multi_lease_batch(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store, worker_id='w')
    queue.enqueue(item('a'), 0)
    chain_straggler(monkeypatch, store, item('b'))
    chain_straggler(monkeypatch, store, item('c'), 100001)
    leases = queue.pull(1, 4)
    assert [lease.item.segment_id for lease in leases] == ['a', 'b', 'c']
    assert queue_row(store)['items'] == []
