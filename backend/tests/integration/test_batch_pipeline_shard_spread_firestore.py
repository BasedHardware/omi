"""Three pullers, real loopback Firestore transactions, no cloud fallback."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import logging
import os
import threading
import uuid

from google.auth.credentials import AnonymousCredentials
from google.api_core.exceptions import Aborted
from google.cloud import firestore
import pytest

from config.batch_pipeline import scheduler_control_key
from database import firestore_transaction_retry as retry
from database.batch_pipeline_store import FirestoreStore, current_operation
from utils.batch_pipeline.contracts import Priority, WorkItem
from utils.batch_pipeline.scheduler import Scheduler, owner_key

pytestmark = pytest.mark.integration


@pytest.fixture
def lane(monkeypatch):
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('loopback Firestore emulator required; no cloud fallback')
    monkeypatch.delenv('BATCH_SHARD_SPREAD_ENABLED', raising=False)
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', 'true')
    clients = [firestore.Client(project='demo-shard-spread', credentials=AnonymousCredentials()) for _ in range(4)]
    namespace = f'batch_pipeline_test_{uuid.uuid4().hex}'
    stores = [FirestoreStore(namespace, firestore_client=client) for client in clients]
    owners = ['burst', 'light', 'other']
    assert len({scheduler_control_key(owner_key(uid)) for uid in owners}) == 3
    for uid in owners:
        clients[0].collection('users').document(uid).set({'data_protection_level': 'enhanced'})
    yield stores, owners
    for table in ('jobs', 'queues', 'owners', 'control', 'pull_claims'):
        for doc in clients[0].collection(f'{namespace}_{table}').stream():
            doc.reference.delete()
    for client in clients:
        client.close()


def item(segment, owner):
    return WorkItem(segment, owner, 1, f'gs://synthetic/{segment}', 30, Priority.FRESH)


def _observe_pull_fence(monkeypatch, store):
    """Observe existing claim reads/writes without adding reads or serializing pulls."""
    local = threading.local()
    acquire, run = store.acquire_pull_claim, store.run
    observations = []

    def acquire_claim(shard, token, now, ttl):
        won = acquire(shard, token, now, ttl)
        local.claim = (shard, token) if won else None
        return won

    def observed_run(body):
        operation = current_operation()
        if not operation.startswith('batch_pull shard='):
            return run(body)
        shard = operation.split('shard=', 1)[1]
        claim = getattr(local, 'claim', None)
        assert claim and claim[0] == shard, 'pull entered without a successful shard claim'

        def observed_body(tx):
            class ObservedTransaction:
                seen = False
                fenced = False

                def get(self, table, key):
                    if (table, key) == ('pull_claims', shard):
                        row = tx.get(table, key)
                        self.seen = True
                        self.fenced = row.get('token') == claim[1]
                        observations.append(self.fenced)
                        return row
                    assert self.fenced, 'pull read data before checking its claim token'
                    return tx.get(table, key)

                def put(self, table, key, value):
                    assert self.fenced, 'pull wrote data without its claim token'
                    if table == 'pull_claims':
                        assert key == shard and value == {'token': '', 'expires_at': 0.0}
                    return tx.put(table, key, value)

                def __getattr__(self, name):
                    assert self.fenced, 'pull used transaction before checking its claim token'
                    return getattr(tx, name)

            observed = ObservedTransaction()
            result = body(observed)
            assert observed.seen, 'pull did not read its claim in the transaction'
            return result

        return run(observed_body)

    monkeypatch.setattr(store, 'acquire_pull_claim', acquire_claim)
    monkeypatch.setattr(store, 'run', observed_run)
    return observations


@pytest.mark.parametrize('single_shard', [True, False])
def test_three_workers_pull_rounds_without_duplicate_or_lost_leases(lane, caplog, monkeypatch, single_shard):
    stores, owners = lane
    fences = [_observe_pull_fence(monkeypatch, store) for store in stores[1:]]
    workers = [Scheduler(store, worker_id=f'worker-{n}') for n, store in enumerate(stores[1:])]
    admit = Scheduler(stores[0])
    leases = []
    expected = set()
    conflicts_by_round = []
    caplog.set_level(logging.WARNING)
    with ThreadPoolExecutor(max_workers=4) as executor:
        for round_number in range(8):
            # Sparse/hot-owner and independent-shard cases. An admission also
            # races the pulls against the control/queue documents each round.
            for n in range(3):
                uid = owners[0] if single_shard else owners[n]
                segment = f'r{round_number}-{n}'
                assert admit.enqueue(item(segment, uid), round_number)
                expected.add(segment)
            concurrent_segment = f'admit-{round_number}'
            expected.add(concurrent_segment)
            gate = threading.Barrier(4)

            def pull(worker):
                gate.wait(timeout=30)
                return worker.pull(round_number, 1)

            def enqueue():
                gate.wait(timeout=30)
                return admit.enqueue(item(concurrent_segment, owners[0]), round_number)

            caplog.clear()
            futures = [executor.submit(pull, worker) for worker in workers]
            admission = executor.submit(enqueue)
            leases.extend(lease for future in futures for lease in future.result(timeout=90))
            assert admission.result(timeout=90)
            conflicts = Counter()
            for record in caplog.records:
                if record.msg.startswith('firestore_transaction_contention') and 'outcome=retry' in record.getMessage():
                    operation = record.args[0]
                    if operation.startswith('batch_pull shard=scheduler_'):
                        conflicts[operation.split('scheduler_')[1]] += 1
            # Admission can abort one correctly fenced pull more than once.
            # Retry totals diagnose contention; token fences and leases prove safety.
            conflicts_by_round.append(dict(conflicts))
            # Drain sequentially between rounds so a busy ownership hint is
            # allowed to defer a pull but can never discard its obligation.
            leases.extend(workers[round_number % 3].pull(round_number, 4))
            assert not any(
                marker in record.getMessage()
                for record in caplog.records
                for marker in (
                    'outcome=exhausted',
                    'outcome=deadline_exhausted',
                    'event=batch_store_contention',
                    'event=batch_pull outcome=backoff',
                )
            ), [record.getMessage() for record in caplog.records]
    assert any(fences), 'the race must exercise the actual transactional claim check'
    assert Counter(lease.item.segment_id for lease in leases) == Counter({segment: 1 for segment in expected})
    assert len({lease.token for lease in leases}) == len(expected)
    print(f'shard-spread single_shard={single_shard} issued={len(leases)} conflicts_by_round={conflicts_by_round}')
    for lease in leases:
        row = stores[0].run(lambda tx: tx.get('jobs', lease.item.segment_id))
        assert row['state'] == 'leased' and row['token'] == lease.token and row['attempt'] == 1
    # A burst cannot exclude an independent light owner in the first round.
    if not single_shard:
        assert 'light' in {lease.item.owner_id for lease in leases[:4]}


def test_three_pullers_can_only_acquire_one_live_shard_claim(lane):
    stores, owners = lane
    shard = scheduler_control_key(owner_key(owners[0]))
    tokens = [uuid.uuid4().hex for _ in stores[1:]]
    gate = threading.Barrier(3)

    def acquire(store, token):
        gate.wait(timeout=30)
        return store.acquire_pull_claim(shard, token, 1, 100)

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(acquire, store, token) for store, token in zip(stores[1:], tokens)]
        winners = [token for token, future in zip(tokens, futures) if future.result(timeout=90)]
    assert len(winners) == 1
    row = stores[0].run(lambda tx: tx.get('pull_claims', shard))
    assert row == {'token': winners[0], 'expires_at': 101}


def test_one_fenced_pull_can_retry_twice_without_duplicate_lease(lane, monkeypatch, caplog):
    stores, owners = lane
    admit, worker = Scheduler(stores[0]), Scheduler(stores[1])
    assert admit.enqueue(item('retry-head', owners[0]), 0)
    fences = _observe_pull_fence(monkeypatch, stores[1])
    run = stores[1].run
    injected_aborts = 0

    def run_with_aborts(body):
        def abort_before_flush(tx):
            nonlocal injected_aborts
            result = body(tx)
            if injected_aborts < 2:
                injected_aborts += 1
                raise Aborted('synthetic contention before buffered pull writes flush')
            return result

        return run(abort_before_flush)

    monkeypatch.setattr(stores[1], 'run', run_with_aborts)
    caplog.set_level(logging.WARNING, logger=retry.__name__)
    leases = worker.pull(1, 1)
    assert injected_aborts == 2 and len(fences) >= 3 and all(fences)
    retries = [
        record
        for record in caplog.records
        if record.msg.startswith('firestore_transaction_contention')
        and 'operation=batch_pull shard=' in record.getMessage()
        and 'outcome=retry' in record.getMessage()
    ]
    assert len(retries) >= 2
    assert len(leases) == 1 and leases[0].item.segment_id == 'retry-head'
    job = stores[0].run(lambda tx: tx.get('jobs', 'retry-head'))
    assert job['state'] == 'leased' and job['attempt'] == 1 and job['token'] == leases[0].token


def test_fence_observer_rejects_the_unclaimed_legacy_pull(lane, monkeypatch):
    stores, owners = lane
    queue = Scheduler(stores[0])
    assert queue.enqueue(item('unclaimed-head', owners[0]), 0)
    _observe_pull_fence(monkeypatch, stores[0])
    monkeypatch.setenv('BATCH_SHARD_SPREAD_ENABLED', 'false')
    with pytest.raises(AssertionError, match='pull entered without a successful shard claim'):
        queue.pull(1, 1)
    assert stores[1].run(lambda tx: tx.get('jobs', 'unclaimed-head'))['state'] == 'ready'


def test_busy_shard_is_read_only_and_falls_back_to_another_shard(lane):
    stores, owners = lane
    queue = Scheduler(stores[0])
    for uid in owners:
        queue.enqueue(item(uid, uid), 0)
    shard = scheduler_control_key(owner_key(owners[0]))
    stores[0].run(lambda tx: tx.put('pull_claims', shard, {'token': 'other-holder', 'expires_at': 100}))
    before = stores[0].run(lambda tx: tx.get('control', shard))
    assert queue._pull_shard(1, shard, Priority.FRESH, 7200) == (None, 'busy')
    assert stores[0].run(lambda tx: tx.get('control', shard)) == before
    assert {lease.item.owner_id for lease in queue.pull(1, 3)} == set(owners[1:])
    assert stores[0].run(lambda tx: tx.get('jobs', owners[0]))['state'] == 'ready'


@pytest.mark.parametrize('invalidation', ['takeover', 'expiry'])
def test_invalidated_pull_holder_cannot_write(lane, monkeypatch, invalidation):
    stores, owners = lane
    queue = Scheduler(stores[0])
    queue.enqueue(item('head', owners[0]), 0)
    shard = scheduler_control_key(owner_key(owners[0]))
    original_run = stores[0].run
    calls = 0
    invalidated_claim = None

    def run(body):
        nonlocal calls, invalidated_claim
        calls += 1
        if calls == 1:

            def invalidate(tx):
                nonlocal invalidated_claim
                claim = tx.get('pull_claims', shard)
                assert claim['token'] and claim['expires_at'] > 1
                # Expire the acquired claim without changing its token, or replace its holder.
                invalidated_claim = dict(claim)
                if invalidation == 'expiry':
                    invalidated_claim['expires_at'] = 0
                else:
                    invalidated_claim['token'] = 'replacement'
                tx.put('pull_claims', shard, invalidated_claim)

            stores[1].run(invalidate)
        return original_run(body)

    monkeypatch.setattr(stores[0], 'run', run)
    before = original_run(lambda tx: tx.get('control', shard))
    job_before = original_run(lambda tx: tx.get('jobs', 'head'))
    assert queue._pull_shard(1, shard, Priority.FRESH, 7200) == (None, 'busy')
    assert original_run(lambda tx: tx.get('control', shard)) == before
    assert original_run(lambda tx: tx.get('jobs', 'head')) == job_before
    assert original_run(lambda tx: tx.get('pull_claims', shard)) == invalidated_claim


def test_expired_claim_is_recoverable_and_kill_switch_uses_legacy_path(lane, monkeypatch):
    stores, owners = lane
    queue = Scheduler(stores[0])
    queue.enqueue(item('head', owners[0]), 0)
    shard = scheduler_control_key(owner_key(owners[0]))
    stores[0].run(lambda tx: tx.put('pull_claims', shard, {'token': 'crashed', 'expires_at': 1}))
    assert queue.pull(1)[0].item.segment_id == 'head'
    queue.enqueue(item('next', owners[0]), 2)
    stores[0].run(lambda tx: tx.put('pull_claims', shard, {'token': 'live', 'expires_at': 100}))
    monkeypatch.setenv('BATCH_SHARD_SPREAD_ENABLED', 'false')
    assert queue.pull(2)[0].item.segment_id == 'next'
