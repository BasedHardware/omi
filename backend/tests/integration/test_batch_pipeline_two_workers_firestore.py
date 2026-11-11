"""Two dedicated GPU workers draining one Firestore queue.

Prod runs a fixed two-replica worker Deployment. Each replica is one process
with one ``Pump`` over its own Firestore client. These tests run two real
``Pump``/``Scheduler``/``OrderedMerge`` stacks, each in its own thread and
event loop with its own client, against the loopback emulator. Only the CUDA
chain is replaced by a timed fake, and spend admission by the same fenced
lease seal the backend RPC performs.

Claims: no segment is accepted twice, every owner's result log is one gap-free
chain in capture order, a stolen lease never publishes, a privacy fence that
lands mid-flight publishes nothing, and a quarantine is recorded once.

Throughput is measured in ``tests/unit/test_batch_pipeline_two_workers.py``:
the emulator holds a collection-wide lock for every transactional query, so
its wall time measures emulator locking, not the scheduler.
"""

from __future__ import annotations

from collections import Counter
import os
import random
import threading
import time
import uuid

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database.batch_pipeline_privacy import advance_privacy_generation
from database.batch_pipeline_store import FirestoreStore
from tests.support.batch_two_workers import FakeGpu, Recorder, build_pump, item, run_pumps
from utils.batch_pipeline import pump as pump_module
from utils.batch_pipeline import scheduler as scheduler_module
from utils.batch_pipeline.contracts import WorkResult
from utils.batch_pipeline.scheduler import Scheduler, owner_key

pytestmark = pytest.mark.integration

TABLES = ('jobs', 'queues', 'owners', 'control', 'results', 'gpus', 'intakes')


def _client():
    return firestore.Client(project='demo-batch-pipeline', credentials=AnonymousCredentials())


@pytest.fixture
def lane(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('loopback Firestore emulator required; no cloud fallback')
    # Prod worker values: head priority on, cap dispatch dark.
    monkeypatch.setenv('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', 'true')
    monkeypatch.delenv('STT_CAP_DISPATCH_ENABLED', raising=False)
    monkeypatch.delenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', raising=False)
    namespaces: list[tuple[firestore.Client, str]] = []

    def make(owners):
        namespace = f'batch_pipeline_test_{uuid.uuid4().hex}'
        admin = _client()
        for uid in owners:
            admin.collection('users').document(uid).set({'data_protection_level': 'enhanced'})
        namespaces.append((admin, namespace))
        # One client per simulated process, like two pods.
        return admin, namespace, [FirestoreStore(namespace, firestore_client=_client()) for _ in range(2)]

    yield make
    # Isolated emulator namespaces only; never inspect or delete others.
    for admin, namespace in namespaces:
        for table in TABLES:
            for doc in admin.collection(f'{namespace}_{table}').stream():
                doc.reference.delete()
        admin.close()


def jobs(admin, namespace):
    return {doc.id: doc.to_dict() for doc in admin.collection(f'{namespace}_jobs').stream()}


def results(admin, namespace):
    return {doc.id: doc.to_dict() for doc in admin.collection(f'{namespace}_results').stream()}


def assert_owner_chain(entries, owner, expected):
    chain = sorted((v for v in entries.values() if v['owner_key'] == owner_key(owner)), key=lambda v: v['log_sequence'])
    assert [v['segment_id'] for v in chain] == expected, 'result log is not in capture order'
    assert [v['log_sequence'] for v in chain] == list(range(1, len(expected) + 1)), 'result log has a gap'
    assert [v['previous_segment_id'] for v in chain] == [None, *expected[:-1]], 'predecessor chain broken'
    assert not any(v['late_capture'] for v in chain)


def test_two_workers_commit_each_segment_once_in_capture_order(lane):
    owners = ['burst', *(f'solo-{n}' for n in range(5)), 'empty']
    admin, namespace, stores = lane(owners)
    burst = [f'burst-{n}' for n in range(8)]
    work = [item(seg, 'burst', n + 1) for n, seg in enumerate(burst)]
    work += [item(f'solo-{n}-{k}', f'solo-{n}', k + 1) for n in range(5) for k in range(2)]
    work.append(item('empty-0', 'empty', 1))
    random.Random(7).shuffle(work)  # Admission order differs from capture order.
    admit = Scheduler(stores[0])
    for value in work:
        assert admit.enqueue(value, time.time())

    recorder = Recorder()
    pumps = [
        build_pump(
            name,
            store,
            recorder,
            FakeGpu(name, recorder.gpu, seconds=0.2, jitter=0.4, recovery={'empty-0'}),
            batch_size=3,
        )
        for name, store in zip(('worker-a', 'worker-b'), stores)
    ]
    expected = {v.segment_id for v in work} - {'empty-0'}

    def drained():
        with recorder.lock:
            return {seg for _, seg in recorder.committed} >= expected and recorder.failed['empty-0'] == 1

    run_pumps(pumps, drained, timeout=120)

    workers = Counter(name for name, _ in recorder.gpu)
    assert set(workers) == {'worker-a', 'worker-b'}, f'only one worker drained: {workers}'
    # Healthy heartbeats: every unit computed once, accepted once, committed once.
    assert Counter(seg for _, seg in recorder.gpu) == Counter({v.segment_id: 1 for v in work})
    assert recorder.accepted == Counter({seg: 1 for seg in expected})
    assert Counter(seg for _, seg in recorder.committed) == Counter({seg: 1 for seg in expected})
    # Both workers' merges contributed, and the burst owner was split across them.
    burst_gpu = {name for name, seg in recorder.gpu if seg.startswith('burst-')}
    assert burst_gpu == {'worker-a', 'worker-b'}, f'burst owner was not split across workers: {burst_gpu}'

    entries = results(admin, namespace)
    assert set(entries) == expected
    assert_owner_chain(entries, 'burst', burst)
    for n in range(5):
        assert_owner_chain(entries, f'solo-{n}', [f'solo-{n}-0', f'solo-{n}-1'])
    # Each result carries the URI of the worker that held the winning lease.
    for seg, entry in entries.items():
        assert entry['result']['result_uri'].endswith('/' + seg)

    rows = jobs(admin, namespace)
    assert {seg for seg, job in rows.items() if job['state'] == 'committed'} == expected
    # Empty ASR: one quarantine handoff, held for the CPU recovery host, no
    # result, no lease. That is the precondition for one paid recovery intent.
    empty = rows['empty-0']
    assert recorder.failed == Counter({'empty-0': 1})
    assert empty['state'] == 'quarantined' and empty['recovery_state'] == 'held'
    assert empty['merge_pending'] is False and not empty['token'] and empty['lease_until'] == 0.0
    assert 'result' not in empty and 'empty-0' not in entries
    assert empty['worker_empty_evidence'] == {'padded_retry': 'empty', 'version': 1}


def test_stolen_lease_never_publishes_and_owner_commits_once(lane, monkeypatch):
    monkeypatch.setattr(scheduler_module, 'LEASE_SECONDS', 1.0)
    monkeypatch.setattr(pump_module, 'HEARTBEAT_SECONDS', 60.0)  # A's lease lapses mid-chain.
    admin, namespace, stores = lane(['owner'])
    admit = Scheduler(stores[0])
    assert admit.enqueue(item('stolen', 'owner', 1), time.time())
    assert admit.enqueue(item('next', 'owner', 2), time.time())

    recorder = Recorder()
    slow = FakeGpu('worker-a', recorder.gpu, slow={'stolen': 2.5, 'next': 2.5})
    fast = FakeGpu('worker-b', recorder.gpu, seconds=0.05)
    # A wedges after its first pull (as if partitioned) and offers no more
    # capacity; only B can re-lease the expired units.
    a_slots = lambda: 0 if any(name == 'worker-a' for name, _ in recorder.gpu) else 2  # noqa: E731
    pumps = [
        build_pump('worker-a', stores[0], recorder, slow, batch_size=2, slots=a_slots),
        build_pump('worker-b', stores[1], recorder, fast, batch_size=2),
    ]

    def a_holds_both():
        rows = jobs(admin, namespace)
        return all(rows[seg]['state'] == 'leased' for seg in ('stolen', 'next'))

    def drained():
        with recorder.lock:
            return {seg for _, seg in recorder.committed} == {'stolen', 'next'}

    run_pumps(pumps, drained, timeout=90, starts={1: a_holds_both})

    computed = Counter(seg for _, seg in recorder.gpu)
    assert computed == Counter({'stolen': 2, 'next': 2}), 'expected one lost and one replacement computation'
    assert recorder.accepted == Counter({'stolen': 1, 'next': 1})
    entries = results(admin, namespace)
    assert_owner_chain(entries, 'owner', ['stolen', 'next'])
    # The expired holder's late result never reached the log.
    assert {v['result']['result_uri'] for v in entries.values()} == {
        'gs://synthetic/worker-b/stolen',
        'gs://synthetic/worker-b/next',
    }
    rows = jobs(admin, namespace)
    assert all(rows[seg]['attempt'] == 2 for seg in ('stolen', 'next'))


def test_privacy_fence_mid_flight_publishes_nothing_under_two_workers(lane, monkeypatch):
    # Prod's 6:1 lease/heartbeat ratio, short enough to expire fenced leases.
    # The emulator can stall one heartbeat for seconds under two writers.
    monkeypatch.setattr(scheduler_module, 'LEASE_SECONDS', 15.0)
    monkeypatch.setattr(pump_module, 'HEARTBEAT_SECONDS', 2.5)
    admin, namespace, stores = lane(['fenced', 'open'])
    admit = Scheduler(stores[0])
    for owner in ('fenced', 'open'):
        for k in range(2):
            assert admit.enqueue(item(f'{owner}-{k}', owner, k + 1), time.time())

    recorder = Recorder()
    gate = threading.Event()

    class GatedGpu(FakeGpu):
        def process_batch(self, items, **kwargs):
            with self.lock:
                self.ledger.extend((self.name, v.segment_id) for v in items)
            assert gate.wait(30)
            time.sleep(0.2)
            return [WorkResult(v.segment_id, f'gs://synthetic/{self.name}/{v.segment_id}') for v in items]

    pumps = [
        build_pump(name, store, recorder, GatedGpu(name, recorder.gpu), batch_size=2)
        for name, store in zip(('worker-a', 'worker-b'), stores)
    ]
    fenced = {'fenced-0', 'fenced-1'}

    def fence_then_drain():
        with recorder.lock:
            started = {seg for _, seg in recorder.gpu}
        if not gate.is_set() and fenced <= started:
            advance_privacy_generation(admin, 'fenced', blocked=True)
            gate.set()
        rows = jobs(admin, namespace)
        return (
            gate.is_set()
            and all(rows[f'open-{k}']['state'] == 'committed' for k in range(2))
            and all(rows[seg]['state'] == 'privacy_blocked' for seg in fenced)
        )

    def describe():
        return {
            seg: (job.get('state'), job.get('attempt'), job.get('failure'))
            for seg, job in jobs(admin, namespace).items()
        }

    run_pumps(pumps, fence_then_drain, timeout=240, describe=describe)

    entries = results(admin, namespace)
    assert set(entries) == {'open-0', 'open-1'}
    assert_owner_chain(entries, 'open', ['open-0', 'open-1'])
    assert not any(seg in fenced for seg in recorder.accepted)
    assert not any(seg in fenced for _, seg in recorder.committed)
    rows = jobs(admin, namespace)
    for seg in fenced:
        assert 'result' not in rows[seg] and not rows[seg]['token']
