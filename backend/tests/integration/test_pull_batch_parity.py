"""PL-321/322/323: real Scheduler transactions on old Firestore, Postgres and sim.

Sources: #24252 (hour heads parked by clock noise) and #24259 (batched pulls).
Require every backend with OMI_REQUIRE_STORE_BACKENDS=all. Only policy inputs,
time and the walk's configurable test bounds are synthetic; Store semantics,
privacy checks, leases and ordered merge are real. No provider or cloud calls.
"""

from dataclasses import replace
import math

import pytest

from config.batch_pipeline import scheduler_control_key
from config.policy import BatchUnitPolicy, SchedulerPolicy, resolve_stage_policy
from database import batch_pipeline_policy
from testing.store_fixtures import build_backend, store_backend  # noqa: F401
from utils.batch_pipeline import scheduler as scheduler_module
from utils.batch_pipeline.contracts import PoolCapacity, Priority, WorkItem, WorkResult
from utils.batch_pipeline.control import field
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.scheduler import Scheduler, owner_key

pytestmark = pytest.mark.integration

POLICY = BatchUnitPolicy(batch_enabled=True, batch_percent=100)
HALF_FRAME = 1 / 32000


@pytest.fixture(autouse=True)
def policy_inputs(monkeypatch):
    # Explicit admission input avoids the serving rollout cache. Stage policies
    # are pinned through the same transaction below, with no policy resolver IO.
    monkeypatch.setattr(scheduler_module, 'resolve_batch_policy', lambda *_: POLICY)
    monkeypatch.setattr(scheduler_module, 'cap_dispatch_enabled', lambda *_: False)
    monkeypatch.setattr(
        batch_pipeline_policy, 'resolve_stage_policy', lambda uid, stage: resolve_stage_policy(uid, stage, flags={})
    )
    monkeypatch.setenv('BATCH_SHARD_SPREAD_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PULL_MULTI_LEASE_ENABLED', 'true')


def work(segment, uid, *, capture=1.0, duration=30.0, conversation=None):
    return WorkItem(
        segment,
        uid,
        capture,
        f'gs://synthetic/{segment}',
        duration,
        Priority.DEEP,
        conversation_id=conversation,
        privacy_generation=0,
    )


def enqueue(h, items, *, head_priority=False, pin_scheduler=True):
    part = SchedulerPolicy(head_priority=head_priority).to_dict()

    def body(tx):
        for item in items:
            assert Scheduler.enqueue_in_transaction(tx, item, 0.0, policy=POLICY)
            if pin_scheduler:
                row = tx.get('jobs', item.segment_id)
                tx.put('jobs', item.segment_id, {**row, 'policy_parts': {'scheduler': part}})

    h.store.run(body)


def row(h, segment):
    return h.store.run(lambda tx: tx.get('jobs', segment))


@pytest.mark.parametrize('multi', [False, True], ids=['single', 'batched'])
@pytest.mark.parametrize(
    'duration,fits',
    [
        (3600.0, True),
        (3600.0 + 4.76837158203125e-7, True),  # actual epoch-subtraction shape
        (math.nextafter(3600.0 + HALF_FRAME, -math.inf), True),
        (3600.0 + HALF_FRAME, True),
        (math.nextafter(3600.0 + HALF_FRAME, math.inf), False),
        (3600.0 + 1 / 16000, False),
    ],
    ids=['exact-hour', 'clock-noise', 'below-half-frame', 'half-frame', 'above-half-frame', 'extra-frame'],
)
def test_pl321_frame_exact_head_progresses_but_a_real_extra_frame_stays_fenced(
    store_backend, monkeypatch, multi, duration, fits
):
    h = store_backend
    uid = h.seed_user('hour')
    monkeypatch.setenv('BATCH_PULL_MULTI_LEASE_ENABLED', str(multi).lower())
    items = [work('hour', uid, duration=duration), work('later', uid, capture=3601.0)]
    enqueue(h, items)
    queue = Scheduler(h.store)
    capacity = PoolCapacity(observed_at=10.0, available_slots=2, max_item_seconds=3600.0)
    leases = queue.pull(10.0, 2, capacity=capacity)
    if fits:
        assert [lease.item for lease in leases] == items
        assert len({lease.token for lease in leases}) == 2
        assert all(lease.attempt == 1 for lease in leases)
        assert Scheduler(h.store).pull(11.0, 2, capacity=replace(capacity, observed_at=11.0)) == []
    else:
        assert leases == []
        for item in items:
            held = row(h, item.segment_id)
            assert held['state'] == 'ready' and held['attempt'] == 0 and not held['token']
            assert held['audio_uri'] == item.audio_uri and held['merge_pending']
            assert held['policy'] == POLICY.to_dict()
        # A larger eligible pool after the bounded park can resume the exact
        # same jobs; refusal must not consume or replace their retained input.
        resumed = Scheduler(h.store).pull(
            41.0, 2, capacity=replace(capacity, observed_at=41.0, max_item_seconds=3601.0)
        )
        assert [lease.item for lease in resumed] == items
        assert all(lease.attempt == 1 for lease in resumed)


@pytest.mark.parametrize('head_priority', [False, True], ids=['fifo', 'merge-head'])
def test_pl322_batched_snapshot_queries_cannot_duplicate_a_lease_or_replay_a_merge(store_backend, head_priority):
    h = store_backend
    uid = h.seed_user('order')
    captures = [('u4', 40.0), ('u1', 10.0), ('u5', 50.0), ('u2', 20.0), ('u3', 30.0)]
    enqueue(h, [work(segment, uid, capture=capture) for segment, capture in captures], head_priority=head_priority)
    queue = Scheduler(h.store, worker_id='synthetic')
    leases = queue.pull(1.0, 8)
    assert sorted(lease.item.segment_id for lease in leases) == ['u1', 'u2', 'u3', 'u4', 'u5']
    assert len({lease.token for lease in leases}) == 5
    if not head_priority:
        assert [lease.item.segment_id for lease in leases] == [segment for segment, _ in captures]
    assert Scheduler(h.store).pull(2.0, 8) == []
    for i, lease in enumerate(leases):
        saved = row(h, lease.item.segment_id)
        assert saved['state'] == 'leased' and saved['token'] == lease.token and saved['attempt'] == 1
        result = WorkResult(lease.item.segment_id, f'gs://synthetic/results/{lease.item.segment_id}')
        assert not queue.complete(result, leases[(i + 1) % len(leases)].token, 3.0)
        assert queue.complete(result, lease.token, 3.0)
        settled = row(h, lease.item.segment_id)
        assert queue.complete(result, lease.token, 4.0)  # acknowledged idempotently, without another write
        assert row(h, lease.item.segment_id) == settled
    merge = OrderedMerge(h.store)
    assert [merge.commit_next(uid, 5.0 + n)['segment_id'] for n in range(5)] == ['u1', 'u2', 'u3', 'u4', 'u5']
    assert merge.commit_next(uid, 11.0) is None
    for segment, _ in captures:
        assert row(h, segment)['state'] == 'committed'


@pytest.mark.parametrize('fence', ['privacy', 'pool'])
def test_pl322_each_new_head_rechecks_privacy_and_pool_before_advancing_its_fifo(store_backend, fence):
    h = store_backend
    uid = h.seed_user('privacy')
    for conversation in ('first', 'deleted', 'behind'):
        h.customer.add_conversation(uid, conversation)
    items = [
        work(name, uid, capture=float(i + 1), conversation=name)
        for i, name in enumerate(('first', 'deleted', 'behind'))
    ]
    if fence == 'pool':
        items[1] = replace(items[1], duration_seconds=7200.0)
    enqueue(h, items)
    if fence == 'privacy':
        h.customer.delete_conversation(uid, 'deleted')
    capacity = PoolCapacity(observed_at=1.0, available_slots=8, max_item_seconds=3600.0)
    leases = Scheduler(h.store).pull(1.0, 8, capacity=capacity)
    assert [lease.item.segment_id for lease in leases] == ['first']
    for item in items[1:]:
        saved = row(h, item.segment_id)
        assert saved['state'] == 'ready' and saved['attempt'] == 0 and saved['audio_uri'] == item.audio_uri
    assert Scheduler(h.store).pull(2.0, 8, capacity=replace(capacity, observed_at=2.0)) == []


class ObserveTransactions:
    """Forward every real operation; record only the attempted write footprint."""

    def __init__(self, store):
        self.store = store
        self.writes = []

    def __getattr__(self, name):
        return getattr(self.store, name)

    def run(self, body):
        def observed(tx):
            written = set()

            class View:
                def __getattr__(self, name):
                    return getattr(tx, name)

                def put(self, table, key, value):
                    written.add((table, key))
                    return tx.put(table, key, value)

            result = body(View())
            self.writes.append(written)
            return result

        return self.store.run(observed)


def same_shard_owners(h, count):
    shard = scheduler_control_key(owner_key(h.uid('seed')))
    labels = []
    for n in range(100000):
        label = f'ring-{n}'
        if scheduler_control_key(owner_key(h.uid(label))) == shard:
            labels.append(label)
            if len(labels) == count:
                return shard, [h.seed_user(label) for label in labels]
    raise AssertionError('synthetic same-shard owner search exhausted')


@pytest.mark.parametrize('head_priority', [False, True], ids=['fifo', 'merge-head'])
def test_pl322_same_shard_duration_fair_order_matches_single_lease_transactions(
    store_backend, monkeypatch, head_priority
):
    orders = {}
    for multi in (False, True):
        h = build_backend(store_backend.name)
        try:
            monkeypatch.setenv('BATCH_PULL_MULTI_LEASE_ENABLED', str(multi).lower())
            _, owners = same_shard_owners(h, 3)
            items = [
                work(f'owner-{o}-unit-{n}', uid, capture=capture, duration=(30.0, 60.0, 143.0)[(o + n) % 3])
                for o, uid in enumerate(owners)
                for n, capture in enumerate((40.0, 10.0, 50.0, 20.0, 30.0))
            ]
            enqueue(h, items, head_priority=head_priority)
            queue = Scheduler(h.store, worker_id='synthetic')
            leases = []
            for now in range(1, 20):  # finish before leases expire; a nonprogress loop is a failure
                pulled = queue.pull(float(now), 8)
                if not pulled:
                    break
                leases.extend(pulled)
            assert len(leases) == len({lease.item.segment_id for lease in leases}) == len(items)
            assert len({lease.token for lease in leases}) == len(items)
            orders[multi] = [lease.item.segment_id for lease in leases]
        finally:
            h.close()
    assert orders[True] == orders[False]


@pytest.mark.parametrize('bound', ['writes', 'visits'])
@pytest.mark.parametrize('multi', [False, True], ids=['single', 'batched'])
def test_pl323_bounded_walk_commits_progress_and_resumes_without_a_false_cooldown(
    store_backend, monkeypatch, bound, multi
):
    h = store_backend
    monkeypatch.setenv('BATCH_PULL_MULTI_LEASE_ENABLED', str(multi).lower())
    # Smaller bounds exercise the real stop paths without a 512-owner fixture.
    # Disable the other stop only in the visits case to qualify each bound.
    monkeypatch.setattr(scheduler_module, 'PULL_WRITE_HEADROOM', 12 if bound == 'writes' else 1000000)
    monkeypatch.setattr(scheduler_module, 'MAX_VISITS', 128 if bound == 'writes' else 8)
    shard, owners = same_shard_owners(h, 40)
    short_heads = (39,) if bound == 'writes' else (7, 15, 23, 31, 39)
    items = [work(f'head-{n}', uid, duration=30.0 if n in short_heads else 7200.0) for n, uid in enumerate(owners)]
    enqueue(h, items, pin_scheduler=bound != 'writes')
    observed = ObserveTransactions(h.store)
    queue = Scheduler(observed, worker_id='synthetic')
    capacity = PoolCapacity(
        observed_at=1.0, available_slots=len(short_heads), max_item_seconds=3600.0 if bound == 'writes' else 7200.0
    )
    leases = queue.pull(1.0, len(short_heads), capacity=capacity)
    assert [lease.item.segment_id for lease in leases] == [f'head-{n}' for n in short_heads]
    assert len({lease.token for lease in leases}) == len(short_heads) and all(lease.attempt == 1 for lease in leases)
    assert len(observed.writes) > 1
    assert max(map(len, observed.writes)) <= 20  # eight visits or headroom plus one visit and final control
    control = h.store.run(lambda tx: tx.get('control', shard))
    # Every stopped transaction must resume in this same pull, retaining DRR
    # deficits for the long heads and issuing every selected short head now.
    assert control[field(int(Priority.DEEP), 'batch_available_at')] <= 1.0
    for n, item in enumerate(items):
        saved = row(h, item.segment_id)
        assert saved['audio_uri'] == item.audio_uri
        assert saved['state'] == ('leased' if n in short_heads else 'ready')
        assert saved['attempt'] == (1 if n in short_heads else 0)
