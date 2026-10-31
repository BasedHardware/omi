"""PL-194: a later failed pull cannot strand earlier committed leases (source #23915).

Run the real Scheduler and Store transactions on sim, Firestore emulator and Postgres.
Only clocks, policy inputs and the pre-commit failure are synthetic; no worker/provider runs.
"""

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Event, current_thread

import pytest

from config.batch_pipeline import scheduler_control_key
from config.policy import resolve_batch_policy, resolve_stage_policy
from database import batch_pipeline_policy
from database.firestore_transaction_retry import FirestoreContentionExhausted
from testing.store_fixtures import store_backend  # noqa: F401
from utils.batch_pipeline import scheduler as scheduler_module
from utils.batch_pipeline.contracts import Priority, WorkItem, WorkResult
from utils.batch_pipeline.scheduler import Scheduler, owner_key

pytestmark = pytest.mark.integration


class SyntheticPullFailure(RuntimeError):
    pass


@pytest.mark.parametrize('spread', [False, True], ids=['legacy-selection', 'shard-claims'])
@pytest.mark.parametrize('failing_lease', [1, 3], ids=['first-pull', 'partial-pull'])
@pytest.mark.parametrize('contention', [False, True], ids=['unexpected', 'contention-exhausted'])
def test_pl194_failed_pull_returns_every_committed_lease(store_backend, monkeypatch, spread, failing_lease, contention):
    h = store_backend
    clock = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    monkeypatch.setenv('BATCH_SHARD_SPREAD_ENABLED', str(spread).lower())
    monkeypatch.setattr(scheduler_module, 'cap_dispatch_enabled', lambda *_: False)
    # Explicit complete policy inputs avoid host cohorts, remote config and admission reads.
    monkeypatch.setattr(
        batch_pipeline_policy, 'resolve_stage_policy', lambda uid, stage: resolve_stage_policy(uid, stage, flags={})
    )
    queue = Scheduler(h.store, worker_id='synthetic-worker')
    items = {}
    for index in range(3):
        uid = h.seed_user(f'owner-{index}')
        segment = f'segment-{index}'
        item = WorkItem(segment, uid, 1 + index, f'gs://synthetic/{segment}', 30, Priority.FRESH)
        policy = resolve_batch_policy(uid, flags={}, now=1000)
        assert h.store.run(lambda tx: queue.enqueue_in_transaction(tx, item, 1000, policy=policy))
        items[segment] = item

    run = h.store.run
    committed, aborted = [], {}
    failure = FirestoreContentionExhausted('synthetic exhaustion') if contention else SyntheticPullFailure('synthetic')

    def failing_run(body):
        def commit(tx):
            before, writes = {}, set()

            class ObservedTransaction:
                def __getattr__(self, name):
                    return getattr(tx, name)

                def get(self, table, key):
                    value = tx.get(table, key)
                    before.setdefault((table, key), deepcopy(value))
                    return value

                def put(self, table, key, value):
                    writes.add((table, key))
                    return tx.put(table, key, value)

            result = body(ObservedTransaction())
            # Postgres acquires the shard claim in a separate transaction returning bool.
            if isinstance(result, tuple) and result[0] is not None:
                lease = result[0][0]
                if len(committed) + 1 == failing_lease:
                    assert writes <= before.keys()
                    aborted.update(lease=lease, before={key: before[key] for key in writes if key[0] != 'pull_claims'})
                    raise failure  # real body finished; buffered lease/queue/service writes must roll back
            return result

        result = run(commit)
        if isinstance(result, tuple) and result[0] is not None:
            committed.append(result[0][0])
        return result

    monkeypatch.setattr(h.store, 'run', failing_run)
    if failing_lease == 1 and not contention:
        with pytest.raises(SyntheticPullFailure):
            queue.pull(1001, 3)
        pulled = []
    else:
        pulled = queue.pull(1001, 3)
    assert aborted and len(pulled) == failing_lease - 1
    assert pulled == committed  # every actual commit is returned, with its original fencing token
    monkeypatch.setattr(h.store, 'run', run)

    for (table, key), before in aborted['before'].items():
        assert run(lambda tx: tx.get(table, key)) == before
    failed = aborted['lease']
    assert run(lambda tx: tx.get('jobs', failed.item.segment_id))['attempt'] == 0
    assert not queue.complete(WorkResult(failed.item.segment_id, 'gs://synthetic/uncommitted'), failed.token, 1002)

    if contention:
        # A hot retry cannot even enter a transaction while the cooldown is live.
        def forbidden_run(_body):
            pytest.fail('cooldown entered the Store')

        monkeypatch.setattr(h.store, 'run', forbidden_run)
        assert queue.pull(1001, 3) == []
        clock[0] += 0.5
        monkeypatch.setattr(h.store, 'run', run)

    for lease in pulled:
        row = run(lambda tx: tx.get('jobs', lease.item.segment_id))
        assert row['state'] == 'leased' and row['token'] == lease.token and row['attempt'] == lease.attempt == 1
        assert queue.complete(
            WorkResult(lease.item.segment_id, f'gs://synthetic/result-{lease.item.segment_id}'), lease.token, 1002
        )

    # Reconstruct before any issued job lease expires. Only the aborted shard claim may need expiry.
    restarted = Scheduler(h.store, worker_id='replacement-worker')
    if spread:
        shard = scheduler_control_key(owner_key(failed.item.owner_id))
        claim = run(lambda tx: tx.get('pull_claims', shard))
        assert claim['token'] and claim['expires_at'] == 1031
    remaining = restarted.pull(1031, 3)
    assert {lease.item.segment_id for lease in remaining} == set(items) - {lease.item.segment_id for lease in pulled}
    assert len(remaining) + len(pulled) == 3
    for lease in remaining:
        assert lease.attempt == 1 and lease.token != failed.token
        assert queue.complete(
            WorkResult(lease.item.segment_id, f'gs://synthetic/result-{lease.item.segment_id}'), lease.token, 1032
        )
    assert restarted.pull(1033, 3) == []
    for segment, item in items.items():
        row = run(lambda tx: tx.get('jobs', segment))
        assert row['state'] == 'result_ready' and row['attempt'] == 1
        assert row['audio_uri'] == item.audio_uri and row['policy']['policy_id']


@pytest.mark.parametrize('spread', [False, True], ids=['legacy-selection', 'shard-claims'])
def test_pl194_overlapping_pull_cannot_clear_newer_cooldown(store_backend, monkeypatch, spread):
    h = store_backend
    uid = h.seed_user('owner')
    monkeypatch.setenv('BATCH_SHARD_SPREAD_ENABLED', str(spread).lower())
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: 100.0)
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    monkeypatch.setattr(scheduler_module, 'cap_dispatch_enabled', lambda *_: False)
    monkeypatch.setattr(
        batch_pipeline_policy, 'resolve_stage_policy', lambda uid, stage: resolve_stage_policy(uid, stage, flags={})
    )
    queue = Scheduler(h.store, worker_id='synthetic-worker')
    item = WorkItem('one', uid, 1, 'gs://synthetic/one', 30, Priority.FRESH)
    policy = resolve_batch_policy(uid, flags={}, now=1000)
    assert h.store.run(lambda tx: queue.enqueue_in_transaction(tx, item, 1000, policy=policy))
    candidate, run = h.store.control_candidate, h.store.run
    entered, resume = Event(), Event()
    aborted = []

    def pause_hint(*args, **kwargs):
        value = candidate(*args, **kwargs)
        if current_thread().name.startswith('earlier-pull') and not entered.is_set():
            assert value is not None
            entered.set()
            assert resume.wait(5), 'overlapping pull was never resumed'
        return value

    def fail_newer_pull(body):
        def commit(tx):
            result = body(tx)
            if not current_thread().name.startswith('earlier-pull') and isinstance(result, tuple) and result[0]:
                aborted.append(result[0][0])
                raise FirestoreContentionExhausted('synthetic exhaustion')
            return result

        return run(commit)

    monkeypatch.setattr(h.store, 'control_candidate', pause_hint)
    monkeypatch.setattr(h.store, 'run', fail_newer_pull)
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix='earlier-pull') as pool:
        earlier = pool.submit(queue.pull, 1001)
        try:
            assert entered.wait(5), 'earlier pull never reached the real selection'
            assert queue.pull(1001) == [] and len(aborted) == 1
        finally:
            resume.set()
        issued = earlier.result(timeout=5)
    # With claims the older hint meets the failed transaction's still-live claim;
    # legacy selection can commit. Neither result may erase the newer cooldown.
    assert len(issued) == (0 if spread else 1)
    if issued:
        row = run(lambda tx: tx.get('jobs', 'one'))
        assert row['token'] == issued[0].token and row['attempt'] == issued[0].attempt == 1

    def forbidden_candidate(*_args, **_kwargs):
        pytest.fail('older overlapping pull erased the contention cooldown')

    monkeypatch.setattr(h.store, 'control_candidate', forbidden_candidate)
    assert queue.pull(1001) == []
