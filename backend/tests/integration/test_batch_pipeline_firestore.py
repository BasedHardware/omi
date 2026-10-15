"""Real transaction/query boundary; refuses every non-loopback emulator host."""

from concurrent.futures import ThreadPoolExecutor
import os
import uuid

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database.batch_pipeline_store import FirestoreStore
from utils.batch_pipeline.contracts import WorkItem, WorkResult, Priority
from utils.batch_pipeline.scheduler import Scheduler
from utils.batch_pipeline.merge import OrderedMerge

pytestmark = pytest.mark.integration


@pytest.fixture
def store():
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('loopback Firestore emulator required; no cloud fallback')
    client = firestore.Client(project='demo-batch-pipeline', credentials=AnonymousCredentials())
    store = FirestoreStore(f'batch_pipeline_test_{uuid.uuid4().hex}', firestore_client=client)
    yield store
    # Isolated emulator namespace only; do not delete or inspect other namespaces.
    for table in ('jobs', 'queues', 'owners', 'control', 'results', 'gpus'):
        for doc in client.collection(f'{store.namespace}_{table}').stream():
            doc.reference.delete()
    client.close()


def work(segment, capture=1, owner='synthetic-owner', priority=Priority.DEEP):
    return WorkItem(segment, owner, capture, f'gs://synthetic/{segment}', 30, priority)


def test_parallel_claims_ordered_commit_and_recovery(store):
    queue = Scheduler(store)
    merge = OrderedMerge(store)
    for name, capture in [('b', 2), ('a', 1), ('c', 3)]:
        assert queue.enqueue(work(name, capture), 0)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(queue.pull, 0, 1) for _ in range(2)]
        leases = [lease for future in futures for lease in future.result()]
    leases.extend(queue.pull(0))
    assert len({v.item.segment_id for v in leases}) == 3
    assert store.oldest(2, ready_only=True) is None
    assert store.oldest(2, ready_only=False) == 0
    by_id = {v.item.segment_id: v for v in leases}
    assert queue.complete(WorkResult('b', 'gs://results/b'), by_id['b'].token, 1)
    assert merge.commit_next('synthetic-owner', 1) is None
    assert queue.complete(WorkResult('a', 'gs://results/a'), by_id['a'].token, 1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(merge.commit_next, 'synthetic-owner', 2) for _ in range(2)]
        entries = [f.result() for f in futures]
    assert sorted(v['segment_id'] for v in entries if v) == ['a', 'b']
    assert queue.recover(121) == 1
    assert not queue.complete(WorkResult('c', 'gs://results/stale'), by_id['c'].token, 122)
    assert queue.recover(126) == 1
    retried = queue.pull(126)[0]
    assert retried.attempt == 2
    assert queue.complete(WorkResult('c', 'gs://results/c'), retried.token, 127)
    assert merge.commit_next('synthetic-owner', 128)['segment_id'] == 'c'
    assert merge.commit_next('synthetic-owner', 128) is None
    assert merge.committed_result('a')['result']['result_uri'] == 'gs://results/a'
    assert not queue.enqueue(work('a', 1), 129)
    with pytest.raises(ValueError, match='watermark'):
        queue.enqueue(work('late', 0), 129)


def test_competing_admission_and_merge_never_regresses_watermark(store):
    queue = Scheduler(store)
    merge = OrderedMerge(store)
    queue.enqueue(work('later', 2), 0)
    lease = queue.pull(0)[0]
    queue.complete(WorkResult('later', 'gs://results/later'), lease.token, 1)

    def admit_earlier():
        try:
            return queue.enqueue(work('earlier', 1), 1)
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        admission = pool.submit(admit_earlier)
        commit = pool.submit(merge.commit_next, 'synthetic-owner', 2)
        admitted, committed = admission.result(), commit.result()
    if admitted:
        assert committed is None
        assert merge.committed_result('later') == {}
    else:
        assert committed['segment_id'] == 'later'


def test_priority_and_owner_fairness_are_durable_across_instances(store):
    first = Scheduler(store)
    second = Scheduler(store)
    for n in range(3):
        first.enqueue(work(f'h{n}'), 0)
    first.enqueue(work('light', owner='light'), 0)
    first.enqueue(work('fresh', owner='fresh', priority=Priority.FRESH), 0)
    assert first.pull(1)[0].item.segment_id == 'fresh'
    assert second.pull(1)[0].item.segment_id == 'h0'
    assert first.pull(1)[0].item.segment_id == 'light'
    assert second.pull(1)[0].item.segment_id == 'h1'


def test_shared_gpu_has_one_flight_across_competing_worker_transactions(store, monkeypatch):
    from utils.batch_pipeline.contracts import PoolCapacity
    from dataclasses import replace

    monkeypatch.setenv('BATCH_PIPELINE_SHARED_LIVE_ENABLED', 'true')
    first, second = Scheduler(store, pool='live'), Scheduler(store, pool='live')
    for name in ('a', 'b'):
        first.enqueue(replace(work(name, owner=name), unit_kind='capture_span'), 0)
    capacity = PoolCapacity(1, 1, shared_with_live=True, memory_headroom_bytes=8 * 1024**3, gpu_id='emulator-gpu')
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(q.pull, 1, capacity=capacity) for q in (first, second)]
        leases = [v for f in futures for v in f.result()]
    assert len(leases) == 1
    lease = leases[0]
    first.recover(122)
    assert second.pull(122, capacity=replace(capacity, observed_at=122)) == []
    assert first.acknowledge_gpu_idle('emulator-gpu', lease.token)
    assert len(second.pull(122, capacity=replace(capacity, observed_at=122))) == 1
