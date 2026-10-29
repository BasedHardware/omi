"""Three pullers, real loopback Firestore transactions, no cloud fallback."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import logging
import os
import threading
import uuid

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from config.batch_pipeline import scheduler_control_key
from database import firestore_transaction_retry as retry
from database.batch_pipeline_store import FirestoreStore
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


@pytest.mark.parametrize('single_shard', [True, False])
def test_three_workers_pull_rounds_without_duplicate_or_lost_leases(lane, caplog, single_shard):
    stores, owners = lane
    workers = [Scheduler(store, worker_id=f'worker-{n}') for n, store in enumerate(stores[1:])]
    admit = Scheduler(stores[0])
    leases = []
    expected = set()
    conflicts_by_round = []
    caplog.set_level(logging.WARNING, logger=retry.__name__)
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
                    if operation.startswith(('batch_claim shard=scheduler_', 'batch_pull shard=scheduler_')):
                        conflicts[operation.split('scheduler_')[1]] += 1
            assert all(count <= 1 for count in conflicts.values()), conflicts
            conflicts_by_round.append(dict(conflicts))
            # Drain sequentially between rounds so a busy ownership hint is
            # allowed to defer a pull but can never discard its obligation.
            leases.extend(workers[round_number % 3].pull(round_number, 4))
    assert Counter(lease.item.segment_id for lease in leases) == Counter({segment: 1 for segment in expected})
    assert len({lease.token for lease in leases}) == len(expected)
    print(f'shard-spread single_shard={single_shard} issued={len(leases)} conflicts_by_round={conflicts_by_round}')
    for lease in leases:
        row = stores[0].run(lambda tx: tx.get('jobs', lease.item.segment_id))
        assert row['state'] == 'leased' and row['token'] == lease.token and row['attempt'] == 1
    # A burst cannot exclude an independent light owner in the first round.
    if not single_shard:
        assert 'light' in {lease.item.owner_id for lease in leases[:4]}


def test_busy_shard_is_read_only_and_falls_back_to_another_shard(lane):
    stores, owners = lane
    queue = Scheduler(stores[0])
    for uid in owners:
        queue.enqueue(item(uid, uid), 0)
    shard = scheduler_control_key(owner_key(owners[0]))
    stores[0].run(lambda tx: tx.put('pull_claims', shard, {'token': 'other-holder', 'expires_at': 100}))
    before = stores[0].run(lambda tx: tx.get('control', shard))
    assert queue._pull_shard(1, shard, Priority.FRESH, 7200, None) == (None, 'busy')
    assert stores[0].run(lambda tx: tx.get('control', shard)) == before
    assert {lease.item.owner_id for lease in queue.pull(1, 3)} == set(owners[1:])
    assert stores[0].run(lambda tx: tx.get('jobs', owners[0]))['state'] == 'ready'


def test_expired_pull_holder_cannot_write_after_takeover(lane, monkeypatch):
    stores, owners = lane
    queue = Scheduler(stores[0])
    queue.enqueue(item('head', owners[0]), 0)
    shard = scheduler_control_key(owner_key(owners[0]))
    original_run = stores[0].run
    calls = 0

    def run(body):
        nonlocal calls
        calls += 1
        if calls == 1:
            stores[1].run(lambda tx: tx.put('pull_claims', shard, {'token': 'replacement', 'expires_at': 100}))
        return original_run(body)

    monkeypatch.setattr(stores[0], 'run', run)
    before = original_run(lambda tx: tx.get('control', shard))
    assert queue._pull_shard(1, shard, Priority.FRESH, 7200, None) == (None, 'busy')
    assert original_run(lambda tx: tx.get('control', shard)) == before
    assert original_run(lambda tx: tx.get('jobs', 'head'))['state'] == 'ready'
    assert original_run(lambda tx: tx.get('pull_claims', shard))['token'] == 'replacement'


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
