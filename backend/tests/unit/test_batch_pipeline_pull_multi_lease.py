"""One claimed shard transaction leases a pull batch; order and fences stay as before.

The store here behaves like a Firestore transaction where it matters: gets read
the transaction's snapshot plus its own buffered writes, index queries read only
the snapshot (never the transaction's writes), and writes land at commit. It counts round trips so the gain is
measured, not assumed.
"""

from collections import Counter
from copy import deepcopy
from dataclasses import replace

import pytest

from config.batch_pipeline import pull_multi_lease_enabled, scheduler_control_key
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, MemoryTransaction, item
from utils.batch_pipeline.contracts import PoolCapacity, Priority, WorkResult
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.scheduler import Scheduler, owner_key


class SnapshotTransaction(MemoryTransaction):
    def __init__(self, rows, counts):
        super().__init__(rows)
        self.writes, self.read, self.counts = {}, set(), counts

    def get(self, table, key):
        if (table, key) not in self.read:
            self.read.add((table, key))
            self.counts['reads'] += 1
        return deepcopy(self.writes.get((table, key), self.rows.get((table, key), {})))

    def put(self, table, key, value):
        self.writes[table, key] = deepcopy(value)

    def check_privacy(self, uid, conversation_ids=(), expected_generation=None):
        self.counts['privacy'] += 1
        return super().check_privacy(uid, conversation_ids, expected_generation)

    def first_pending(self, owner_key):
        self.counts['queries'] += 1
        return deepcopy(super().first_pending(owner_key))

    def ready_predecessor(self, owner_key, priority, segment_id):
        self.counts['queries'] += 1
        return super().ready_predecessor(owner_key, priority, segment_id)


class SnapshotStore(MemoryStore):
    def __init__(self):
        super().__init__()
        self.counts = Counter()

    def run(self, body):
        with self.lock:
            self.counts['transactions'] += 1
            tx = SnapshotTransaction(self.rows, self.counts)
            result = body(tx)
            if len(tx.writes) > 450:
                raise RuntimeError('batch transaction write budget exceeded')  # FirestoreTransaction.flush
            rows = deepcopy(self.rows)
            rows.update(tx.writes)
            self.rows = rows
            return result

    def acquire_pull_claim(self, shard, token, now, ttl):
        self.counts['claims'] += 1
        return super().acquire_pull_claim(shard, token, now, ttl)

    def control_candidate(self, priority, pool, now, *, worker_id='', exclude=()):
        self.counts['candidate_queries'] += 1
        return super().control_candidate(priority, pool, now, worker_id=worker_id, exclude=exclude)


def owners_in_shard(n, start=0):
    shard = scheduler_control_key(owner_key('seed'))
    found = [str(v) for v in range(start, start + 100000) if scheduler_control_key(owner_key(str(v))) == shard]
    return found[:n]


def backlog(queue, owners, units, *, out_of_order=False):
    durations = (30, 60, 143, 300)
    for o, owner in enumerate(owners):
        for n in range(units):
            # Upload order may differ from capture order (recovered units).
            capture = (units - n) if out_of_order and n % 3 == 0 else n + units
            queue.enqueue(item(f'{owner}-{n}', owner=owner, capture=capture, duration=durations[(o + n) % 4]), 0)


def drain(queue, now, batch=8):
    leased = []
    while pulled := queue.pull(now, batch):
        leased.extend(pulled)
        now += 1
    return leased


def round_trips(counts):
    # Each claim is a get plus a conditional write; every other count is one RPC.
    return counts['reads'] + counts['queries'] + counts['privacy'] + counts['candidate_queries'] + 2 * counts['claims']


def test_switch_defaults_on_and_reads_changes_at_call_boundary(monkeypatch):
    monkeypatch.delenv('BATCH_PULL_MULTI_LEASE_ENABLED', raising=False)
    assert pull_multi_lease_enabled()
    monkeypatch.setenv('BATCH_PULL_MULTI_LEASE_ENABLED', ' FALSE ')
    assert not pull_multi_lease_enabled()


@pytest.mark.parametrize('head_priority', [False, True])
def test_batch_transaction_cuts_transactions_and_round_trips_per_lease(monkeypatch, head_priority):
    monkeypatch.setenv('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', str(head_priority).lower())
    owners = owners_in_shard(4) + ['a', 'b', 'c', 'd']
    measured = {}
    for multi in (False, True):
        monkeypatch.setenv('BATCH_PULL_MULTI_LEASE_ENABLED', str(multi).lower())
        store = SnapshotStore()
        queue = Scheduler(store, worker_id='w')
        backlog(queue, owners, 8, out_of_order=head_priority)
        store.counts.clear()
        leased = drain(queue, 1)
        assert len(leased) == len({v.item.segment_id for v in leased}) == len(owners) * 8
        measured[multi] = {
            'transactions_per_lease': store.counts['transactions'] / len(leased),
            'round_trips_per_lease': round_trips(store.counts) / len(leased),
        }
    before, after = measured[False], measured[True]
    # Before: one transaction per lease plus the empty probes that end a drain.
    assert before['transactions_per_lease'] >= 1.0
    assert after['transactions_per_lease'] <= before['transactions_per_lease'] / 4
    # Head priority keeps its per-head index queries; the ring re-read goes.
    assert after['round_trips_per_lease'] <= before['round_trips_per_lease'] / (2.5 if head_priority else 3)


@pytest.mark.parametrize('head_priority', [False, True])
def test_one_shard_leases_in_the_same_order_as_one_lease_per_transaction(monkeypatch, head_priority):
    monkeypatch.setenv('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', str(head_priority).lower())
    owners = owners_in_shard(5)
    orders = {}
    for multi in (False, True):
        monkeypatch.setenv('BATCH_PULL_MULTI_LEASE_ENABLED', str(multi).lower())
        queue = Scheduler(SnapshotStore(), worker_id='w')
        backlog(queue, owners, 10, out_of_order=head_priority)
        orders[multi] = [v.item.segment_id for v in drain(queue, 1)]
    # Same DRR walk over one ring: identical leases in identical order.
    assert orders[True] == orders[False]
    assert len(orders[True]) == 50


def test_every_shard_keeps_owner_fifo_and_leases_every_unit_once(monkeypatch):
    owners = owners_in_shard(3) + ['a', 'b', 'c']
    queue = Scheduler(SnapshotStore(), worker_id='w')
    backlog(queue, owners, 9)
    leased = drain(queue, 1)
    assert sorted(v.item.segment_id for v in leased) == sorted(f'{o}-{n}' for o in owners for n in range(9))
    for owner in owners:
        assert [v.item.segment_id for v in leased if v.item.owner_id == owner] == [f'{owner}-{n}' for n in range(9)]


def test_each_lease_has_its_own_fenced_token(monkeypatch):
    store = SnapshotStore()
    queue = Scheduler(store, worker_id='w')
    backlog(queue, owners_in_shard(2), 4)
    store.counts.clear()
    leases = queue.pull(1, 8)
    assert len(leases) == 8 and store.counts['transactions'] == 1
    assert len({v.token for v in leases}) == 8
    first, second = leases[0], leases[1]
    assert not queue.complete(WorkResult(first.item.segment_id, 'gs://synthetic/x'), second.token, 2)
    for lease in leases:
        job = store.rows['jobs', lease.item.segment_id]
        assert job['state'] == 'leased' and job['token'] == lease.token and job['attempt'] == 1
        assert queue.heartbeat(lease.item.segment_id, lease.token, 2)
        assert queue.complete(WorkResult(lease.item.segment_id, 'gs://synthetic/x'), lease.token, 3)


def test_stale_head_query_never_re_leases_or_reverts_a_unit_leased_in_the_same_transaction(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', 'true')
    store = SnapshotStore()
    queue = Scheduler(store, worker_id='w')
    # Recovered units arrive before their capture predecessors, so each new
    # head is a promotion candidate while the query still sees the snapshot.
    for sid, capture in [('u4', 40), ('u1', 10), ('u5', 50), ('u2', 20), ('u3', 30)]:
        queue.enqueue(item(sid, capture=capture), 0)
    store.counts.clear()
    leases = queue.pull(1, 8)
    ids = [v.item.segment_id for v in leases]
    assert sorted(ids) == ['u1', 'u2', 'u3', 'u4', 'u5'] and len(set(ids)) == 5
    assert store.counts['transactions'] == 1
    for lease in leases:
        assert store.rows['jobs', lease.item.segment_id]['token'] == lease.token
    for lease in leases:
        assert queue.complete(
            WorkResult(lease.item.segment_id, f'gs://synthetic/{lease.item.segment_id}'), lease.token, 2
        )
    merge = OrderedMerge(store)
    assert [merge.commit_next('heavy', 3 + n)['segment_id'] for n in range(5)] == ['u1', 'u2', 'u3', 'u4', 'u5']


def test_without_the_write_overlay_a_stale_head_would_be_leased_twice(monkeypatch):
    # Proves the test above has teeth: the overlay is what keeps it safe.
    monkeypatch.setenv('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', 'true')
    from utils.batch_pipeline import scheduler

    monkeypatch.setattr(scheduler._OwnWrites, '_own', lambda self, job: job)
    store = SnapshotStore()
    queue = Scheduler(store, worker_id='w')
    for sid, capture in [('u4', 40), ('u1', 10), ('u5', 50), ('u2', 20), ('u3', 30)]:
        queue.enqueue(item(sid, capture=capture), 0)
    ids = [v.item.segment_id for v in queue.pull(1, 8)]
    assert len(ids) != len(set(ids))


def test_every_new_head_rechecks_privacy_inside_the_batch_transaction(monkeypatch):
    check = MemoryTransaction.check_privacy

    def privacy(tx, uid, conversation_ids=(), expected_generation=None):
        if 'deleted' in conversation_ids:
            raise BatchPrivacyBlocked('synthetic deletion')
        return check(tx, uid, conversation_ids, expected_generation)

    monkeypatch.setattr(MemoryTransaction, 'check_privacy', privacy)
    store = SnapshotStore()
    queue = Scheduler(store, worker_id='w')
    queue.enqueue(item('first', capture=1), 0)
    queue.enqueue(replace(item('deleted-unit', capture=2), conversation_id='deleted'), 0)
    queue.enqueue(item('behind', capture=3), 0)
    assert [v.item.segment_id for v in queue.pull(1, 8)] == ['first']
    assert store.rows['jobs', 'deleted-unit']['state'] == 'ready'
    # FIFO: the unit behind the fenced head is never leased around it.
    assert store.rows['jobs', 'behind']['state'] == 'ready'


def test_every_new_head_rechecks_the_pool_ceiling(monkeypatch):
    queue = Scheduler(SnapshotStore(), worker_id='w')
    queue.enqueue(item('short', capture=1, duration=30), 0)
    queue.enqueue(item('too-long', capture=2, duration=600), 0)
    capacity = PoolCapacity(observed_at=1, available_slots=8, reserved_fresh_slots=0, max_item_seconds=300.0)
    assert [v.item.segment_id for v in queue.pull(1, 8, capacity=capacity)] == ['short']


def test_reserved_fresh_slots_still_bound_backfill_in_one_transaction():
    queue = Scheduler(SnapshotStore(), worker_id='w')
    for n in range(6):
        queue.enqueue(item(f'deep-{n}', capture=n), 0)
    capacity = PoolCapacity(observed_at=1, available_slots=4, reserved_fresh_slots=3)
    assert len(queue.pull(1, 8, capacity=capacity)) == 1


@pytest.mark.parametrize('headroom', [None, 10**6])
def test_long_heads_never_push_one_transaction_past_the_write_budget(monkeypatch, headroom):
    # Every short head sits behind 31 long heads that only rotate, one queue
    # write each. Bounding the whole walk, not each lease, keeps 512 queues
    # from becoming 512 buffered writes in one transaction; the write
    # headroom is a second, independent stop.
    from utils.batch_pipeline import scheduler

    if headroom is not None:
        monkeypatch.setattr(scheduler, 'PULL_WRITE_HEADROOM', headroom)
    store = SnapshotStore()
    queue = Scheduler(store, worker_id='w')
    items = [
        item(f'{owner}-0', owner=owner, duration=30 if n % 32 == 31 else 7200)
        for n, owner in enumerate(owners_in_shard(512))
    ]
    MemoryStore.run(store, lambda tx: [Scheduler.enqueue_in_transaction(tx, v, 0) for v in items])
    store.counts.clear()
    leases = queue.pull(1, 16)
    assert len(leases) == 16 and {v.item.duration_seconds for v in leases} == {30}
    if headroom is not None:
        assert store.counts['transactions'] == 4  # 128 visits reach 4 short heads.


def test_kill_switch_restores_one_lease_per_transaction(monkeypatch):
    monkeypatch.setenv('BATCH_PULL_MULTI_LEASE_ENABLED', 'false')
    store = SnapshotStore()
    queue = Scheduler(store, worker_id='w')
    backlog(queue, owners_in_shard(2), 4)
    store.counts.clear()
    assert len(queue.pull(1, 8)) == 8
    assert store.counts['transactions'] == 8


def test_fresh_batch_never_spends_backfill_and_priority_stays_strict():
    queue = Scheduler(SnapshotStore(), worker_id='w')
    for n in range(3):
        queue.enqueue(item(f'fresh-{n}', capture=n, priority=Priority.FRESH), 0)
        queue.enqueue(item(f'deep-{n}', owner='deep', capture=n), 0)
    assert [v.item.segment_id for v in queue.pull(1, 4)] == ['fresh-0', 'fresh-1', 'fresh-2', 'deep-0']
