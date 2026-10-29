"""Pull ownership policy; real transaction contention lives in the emulator suite."""

import hashlib
import threading
from collections import Counter
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config.batch_pipeline import scheduler_control_key, shard_spread_enabled
from database import batch_pipeline_store as store_module
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline.control import field
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


# --- multi-worker sim: writes spread, leases never duplicate (#23927) ------------
#
# One simulated worker cannot see the 10-28 failure shape: every worker writing
# the lowest control shard. This store models the real spread-mode candidate
# semantics (service stays the fairness key; equal-service shards use worker
# affinity; busy shards are excluded) plus the Firestore behavior that made the
# pile-up expensive: a control write whose shard was committed by another puller
# after this puller's candidate read aborts (write-write contention on the hot
# document). N >= 4 real Schedulers then drain M shards concurrently.


class SpreadMemoryStore(MemoryStore):
    def __init__(self):
        super().__init__()
        self.control_writes: Counter[str] = Counter()
        self.claim_attempts: Counter[str] = Counter()
        self.contention_events: Counter[str] = Counter()
        self.control_versions: Counter[str] = Counter()
        self._selection = threading.local()
        self._round_view: dict[str, dict] | None = None
        self._round_generation = 0
        # The puller whose pull is in flight; the test drives workers one at
        # a time, so a thread-local view would leak one puller's committed
        # writes into the next puller's in-flight snapshot.
        self.current_puller = ''
        self._puller_views: dict[str, dict] = {}

    def freeze_candidates(self):
        """Start a round: every puller's next candidate read sees this same
        control snapshot, the way concurrent Firestore index reads race. Each
        puller keeps its own copy: a puller's own committed writes refresh its
        view (its re-queries would see them), while the other pullers'
        in-flight queries still see the round snapshot. ``_version`` carries
        the commit version the snapshot saw, so a transaction on a shard
        another puller committed after this snapshot aborts."""
        with self.lock:
            self._round_view = {}
            for (table, key), value in self.rows.items():
                if table == 'control':
                    stamped = deepcopy(value)
                    stamped['_version'] = self.control_versions[key]
                    self._round_view[key] = stamped
            self._round_generation += 1
            self._puller_views = {}

    def _candidate_view(self) -> dict[str, dict]:
        view = self._puller_views.get(self.current_puller)
        if view is None:
            view = {key: deepcopy(value) for key, value in (self._round_view or {}).items()}
            self._puller_views[self.current_puller] = view
        return view

    def run(self, body):
        from database.firestore_transaction_retry import FirestoreContentionExhausted

        attempted = []

        def observed(tx):
            plain_put = tx.put

            def counting_put(table, key, value):
                if table == 'control':
                    selected = getattr(self._selection, 'shard', None)
                    if selected == key and self.control_versions[key] != getattr(self._selection, 'version', None):
                        self.contention_events[key] += 1
                        raise FirestoreContentionExhausted('control shard write-write contention')
                    attempted.append(key)
                    self.control_writes[key] += 1
                    self.control_versions[key] += 1
                    view = self._puller_views.get(self.current_puller)
                    if view is not None and key in view:
                        refreshed = deepcopy(value)
                        refreshed['_version'] = self.control_versions[key]
                        view[key] = refreshed
                return plain_put(table, key, value)

            tx.put = counting_put
            return body(tx)

        try:
            return super().run(observed)
        except FirestoreContentionExhausted:
            # The snapshot MemoryStore discarded carried these counters.
            for shard in attempted:
                self.control_writes[shard] -= 1
                self.control_versions[shard] -= 1
            raise

    def control_candidate(self, priority, pool, now, *, worker_id='', exclude=()):
        if self._round_view is not None:
            source = self._candidate_view()
        else:
            with self.lock:
                source = {key: value for (table, key), value in self.rows.items() if table == 'control'}
        candidates = [
            (value[field(priority, 'service')], value[field(priority, pool + '_available_at')], key)
            for key, value in source.items()
            if value.get(field(priority, 'active'))
            and value[field(priority, pool + '_available_at')] <= now
            and key not in exclude
        ]
        chosen = None
        if candidates:
            if worker_id:
                # Mirrors the production query: service primary, worker
                # affinity on ties, exclusions honored — the MemoryStore
                # default ignores worker_id, the legacy single-shard shape.
                candidates.sort(key=lambda row: (row[0], hashlib.sha256(f'{worker_id}:{row[2]}'.encode()).digest()))
                chosen = candidates[0][2]
            else:
                chosen = min(candidates)[2]
            # The candidate read is this puller's transaction snapshot.
            self._selection.shard = chosen
            self._selection.version = source[chosen].get('_version', self.control_versions[chosen])
        return chosen

    def acquire_pull_claim(self, shard, token, now, ttl):
        self.claim_attempts[shard] += 1
        return super().acquire_pull_claim(shard, token, now, ttl)


def owners_across_shards(shards: int):
    """Distinct synthetic owner ids hashing onto ``shards`` distinct shards."""
    owners, seen = [], set()
    n = 0
    while len(seen) < shards:
        owner = f'sim-owner-{n}'
        n += 1
        shard = scheduler_control_key(owner_key(owner))
        if shard not in seen:
            owners.append(owner)
            seen.add(shard)
    return owners


def affinity_first_choice(worker_id: str, shards):
    return min(shards, key=lambda shard: hashlib.sha256(f'{worker_id}:{shard}'.encode()).digest())


def test_equal_service_shards_give_each_worker_a_distinct_first_choice():
    """The affinity tiebreak: against a tied control state, workers' first
    candidates differ — the property whose absence piled every worker onto
    one shard. The legacy selection (no worker affinity) collapses them all
    onto the single lowest-service shard."""
    store = SpreadMemoryStore()
    queue = Scheduler(store)
    owners = owners_across_shards(8)
    for owner in owners:
        queue.enqueue(item(f'job-{owner}', owner=owner), 0)
    shards = {scheduler_control_key(owner_key(owner)) for owner in owners}
    # Six worker ids whose affinity rankings lead with six distinct shards.
    workers, tops = [], set()
    n = 0
    while len(workers) < 6:
        worker_id = f'sim-worker-{n}'
        n += 1
        top = affinity_first_choice(worker_id, sorted(shards))
        if top not in tops:
            workers.append(worker_id)
            tops.add(top)
    choices = [store.control_candidate(int(Priority.DEEP), 'batch', 1, worker_id=worker_id) for worker_id in workers]
    assert set(choices) == tops, 'store selection must match the production affinity ranking'
    assert len(choices) == len(set(choices)) == 6
    # The legacy shape this replaced: without affinity, every worker's first
    # choice is the same lowest-(service, id) shard.
    legacy = {store.control_candidate(int(Priority.DEEP), 'batch', 1) for _ in workers}
    assert len(legacy) == 1


def test_shared_snapshot_workers_spread_control_writes_and_never_duplicate_leases(monkeypatch):
    """Six workers pull one item each per round, every round from the SAME
    frozen control snapshot (the way concurrent Firestore index reads race)
    while transactions commit against live state. Deterministic interleaving:
    real thread timing cannot make a unit assertion flake here; the emulator
    suite owns true concurrent transaction contention."""
    monkeypatch.delenv('BATCH_SHARD_SPREAD_ENABLED', raising=False)
    store = SpreadMemoryStore()
    owners = owners_across_shards(12)
    jobs = [f'job-{owner}-{n}' for owner in owners for n in range(4)]
    for owner in owners:
        for n in range(4):
            Scheduler(store).enqueue(item(f'job-{owner}-{n}', owner=owner), 0)
    workers = [Scheduler(store, worker_id=f'worker-{n}') for n in range(6)]
    leased: list = []
    rounds: list[int] = []
    round_writes: list[dict[str, int]] = []
    for index in range(60):
        store.freeze_candidates()
        before = dict(store.control_writes)
        pulled = 0
        pulled = 0
        for worker in workers:
            # Advancing clock: a contention backoff (up to ~30 s) must never
            # freeze a later round of the drain. The scheduler keeps its
            # backoff on the wall clock, so model the expiry explicitly: the
            # round's 100 sim-seconds have passed the 32 s backoff cap.
            store.current_puller = worker.worker_id
            round_leases = worker.pull(1000 + index * 100, 1) or []
            leased.extend(round_leases)
            pulled += len(round_leases)
            worker._contention_backoff_until = 0.0
            worker._contention_failures = 0
        delta = {
            shard: count - before.get(shard, 0)
            for shard, count in store.control_writes.items()
            if count != before.get(shard, 0)
        }
        if delta:
            round_writes.append(delta)
        rounds.append(pulled)
        if pulled == 0:
            break
    segment_ids = [lease.item.segment_id for lease in leased]
    assert sorted(segment_ids) == sorted(jobs), 'every job leased exactly once'
    assert len(segment_ids) == len(set(segment_ids)), 'no duplicate pulls across workers'
    active = {scheduler_control_key(owner_key(owner)) for owner in owners}
    writes = {shard: store.control_writes[shard] for shard in active}
    mean = sum(writes.values()) / len(writes)
    assert mean > 0 and max(writes.values()) <= 2 * mean, f'control writes concentrated: {writes}'
    assert set(store.control_writes) <= active
    assert len({lease.token for lease in leased}) == len(leased)
    # The 10-28 shape this suite exists for: with every shard at equal service,
    # a round's pulls must not pile onto one control document. The legacy
    # no-affinity selection put every puller's transaction on the single
    # lowest-service shard; spread keeps any shard under half the round (small
    # tail rounds get a two-write floor), and a pile-up surfaces as stale
    # write-write contention instead of concentrated writes.
    assert round_writes, 'every drain round must record its control writes'
    for index, delta in enumerate(round_writes):
        total = sum(delta.values())
        assert max(delta.values()) <= max(2, total / 2), f'round {index} piled writes on one shard: {delta}'
    assert sum(store.claim_attempts.values()) > 0, 'spread pulls must fence through the shard claim'
    # Measured on this deterministic shape: spread settles 24 stale-write
    # aborts (exclusion retries racing claim releases); the legacy
    # no-affinity selection (BATCH_SHARD_SPREAD_ENABLED=false) settles 240 —
    # every round, five pullers' transactions pile onto the lowest-service
    # shard and abort. The bound sits far from both.
    assert sum(store.contention_events.values()) <= 60, dict(store.contention_events)
