"""PL-211: pending deletion fences asynchronous work; restoration releases the fence.

The same real Scheduler and transaction bodies run on old Firestore, new Postgres,
and the simulator. Customer documents are synthetic, using the real privacy policy.
Require all three with OMI_REQUIRE_STORE_BACKENDS=all under a loopback emulator.
"""

from copy import deepcopy

import pytest

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from testing.store_fixtures import store_backend  # noqa: F401
from utils.batch_pipeline.contracts import Priority, WorkItem, WorkResult
from utils.batch_pipeline.scheduler import Scheduler, owner_key

pytestmark = pytest.mark.integration


@pytest.fixture(params=[False, True], ids=['legacy-pull', 'shard-claim-pull'])
def h(store_backend, request, monkeypatch):
    monkeypatch.setenv('BATCH_SHARD_SPREAD_ENABLED', str(request.param).lower())
    store_backend.seed_user('o')
    if store_backend.name == 'emulator':
        reference = store_backend.customer.client.collection('account_deletions').document(store_backend.uid('o'))

        def cleanup():
            reference.delete()
            for claim in store_backend.customer.client.collection(f'{store_backend.namespace}_pull_claims').stream():
                claim.reference.delete()

        store_backend.cleanup_steps.append(cleanup)
    return store_backend


def marker(h, status):
    # CustomerData uses strict synthetic Firestore for sim/Postgres, while the
    # old Store's customer authority is the real loopback emulator.
    row = {'wipe_status': status}
    if h.name == 'emulator':
        h.customer.client.collection('account_deletions').document(h.uid('o')).set(row)
    else:
        h.customer.client.rows['account_deletions', h.uid('o')] = row


def read(h, table, key):
    return h.store.run(lambda tx: tx.get(table, key))


def work(h, sid='retained'):
    return WorkItem(sid, h.uid('o'), 1000.0, f'gs://synthetic/{sid}', 30.0, Priority.FRESH, privacy_generation=0)


def assert_retained(h, expected):
    assert read(h, 'jobs', 'retained') == expected
    assert read(h, 'results', 'retained') == {}


def test_pl211_pending_deletion_refuses_admission_atomically_then_restore_admits(h):
    scheduler = Scheduler(h.store)
    marker(h, 'pending_deletion')
    with pytest.raises(BatchPrivacyBlocked):
        scheduler.enqueue(work(h), 1000.0)
    assert read(h, 'jobs', 'retained') == {}
    assert read(h, 'owners', owner_key(h.uid('o'))) == {}
    # The admission callback buffers queue/control writes before the job privacy
    # fence; a refused transaction must not leave dispatchable coordination.
    assert h.store.control_candidate(int(Priority.FRESH), 'batch', 1001.0) is None
    marker(h, 'cancelled')
    assert Scheduler(h.store).enqueue(work(h), 1001.0)
    lease = Scheduler(h.store).pull(1002.0)[0]
    assert lease.item == work(h) and lease.attempt == 1
    assert Scheduler(h.store).complete(WorkResult('retained', 'gs://synthetic/result'), lease.token, 1003.0)


def test_pl211_pending_deletion_prevents_pull_without_consuming_work_then_restore_resumes(h):
    assert Scheduler(h.store).enqueue(work(h), 1000.0)
    admitted = deepcopy(read(h, 'jobs', 'retained'))
    marker(h, 'pending_deletion')
    for now in (1001.0, 1031.0):
        assert Scheduler(h.store).pull(now) == []
        assert_retained(h, admitted)
    marker(h, 'cancelled')
    # A privacy-refused shard uses the scheduler's existing 30-second retry
    # clock. Restoration must resume at that bound without re-enqueueing.
    lease = Scheduler(h.store).pull(1061.0)[0]
    assert lease.item == work(h) and lease.attempt == 1
    assert read(h, 'jobs', 'retained')['policy'] == admitted['policy']
    assert Scheduler(h.store).complete(WorkResult('retained', 'gs://synthetic/result'), lease.token, 1062.0)


@pytest.mark.parametrize('action', ['heartbeat', 'complete', 'publish'])
def test_pl211_deletion_after_lease_refuses_worker_writes_then_restore_completes(h, action):
    scheduler = Scheduler(h.store)
    assert scheduler.enqueue(work(h), 1000.0)
    lease = scheduler.pull(1001.0)[0]
    leased = deepcopy(read(h, 'jobs', 'retained'))
    result = WorkResult('retained', 'gs://synthetic/result')
    marker(h, 'pending_deletion')

    def attempt():
        restarted = Scheduler(h.store)
        if action == 'heartbeat':
            return restarted.heartbeat('retained', lease.token, 1002.0)
        if action == 'complete':
            return restarted.complete(result, lease.token, 1002.0)

        def publish(tx):
            tx.put('owners', 'rollback-sentinel', {'published': True})
            tx.put('results', 'retained', {'segment_id': 'retained', 'projection_state': 'pending'})

        return h.store.run(publish)

    for _ in range(2):
        with pytest.raises(BatchPrivacyBlocked):
            attempt()
        assert_retained(h, leased)
        assert read(h, 'owners', 'rollback-sentinel') == {}

    marker(h, 'cancelled')
    restored = Scheduler(h.store)
    assert restored.heartbeat('retained', lease.token, 1003.0)
    assert restored.complete(result, lease.token, 1004.0)
    assert restored.complete(result, lease.token, 1005.0)  # identical retry
    assert not restored.complete(result, 'stale-token', 1005.0)
    completed = read(h, 'jobs', 'retained')
    assert completed['state'] == 'result_ready'
    assert completed['attempt'] == leased['attempt'] == 1
    assert completed['audio_uri'] == leased['audio_uri']
    assert completed['policy'] == leased['policy']
    if action == 'publish':
        attempt()
        assert read(h, 'results', 'retained')['projection_state'] == 'pending'
        assert read(h, 'owners', 'rollback-sentinel') == {'published': True}
