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
    for uid in ('synthetic-owner', 'light', 'fresh', 'a', 'b'):
        client.collection('users').document(uid).set({'data_protection_level': 'enhanced'})
    yield store
    # Isolated emulator namespace only; do not delete or inspect other namespaces.
    for table in ('jobs', 'queues', 'owners', 'control', 'results', 'gpus', 'intakes'):
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
    assert queue.enqueue(work('late', 0), 129)
    late = queue.pull(129)[0]
    assert queue.complete(WorkResult('late', 'gs://results/late'), late.token, 130)
    entry = merge.commit_next('synthetic-owner', 131)
    assert entry['capture_at'] == 0 and entry['previous_segment_id'] == 'c' and entry['late_capture']


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
    assert admitted
    lease = queue.pull(2)[0]
    queue.complete(WorkResult('earlier', 'gs://results/earlier'), lease.token, 3)
    entries = [committed] if committed else []
    while entry := merge.commit_next('synthetic-owner', 4):
        entries.append(entry)
    assert {v['segment_id'] for v in entries} == {'earlier', 'later'}
    assert entries[0]['previous_segment_id'] is None
    assert entries[1]['previous_segment_id'] == entries[0]['segment_id']
    from utils.batch_pipeline.scheduler import owner_key

    owner = store.run(lambda tx: tx.get('owners', owner_key('synthetic-owner')))
    assert owner['watermark'] == {'capture_at': 2, 'segment_id': 'later'}


def test_priority_and_owner_fairness_are_durable_across_instances(store):
    first = Scheduler(store)
    second = Scheduler(store)
    for n in range(3):
        first.enqueue(work(f'h{n}'), 0)
    first.enqueue(work('light', owner='light'), 0)
    first.enqueue(work('fresh', owner='fresh', priority=Priority.FRESH), 0)
    assert first.pull(1)[0].item.segment_id == 'fresh'
    first_two = [second.pull(1)[0].item.segment_id, first.pull(1)[0].item.segment_id]
    assert set(first_two) == {'h0', 'light'}
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


def test_atomic_intake_vs_legacy_retry_and_rollback(store, monkeypatch):
    from dataclasses import replace
    from database.batch_pipeline_intake import admit
    from database import sync_ledger
    from utils.batch_pipeline.contracts import ProjectionBinding
    from utils.batch_pipeline.intake import durable_status
    from utils.batch_pipeline.scheduler import owner_key

    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')

    def forbidden(*args):
        raise AssertionError('batch content must never check Redis absence for takeover')

    monkeypatch.setattr(sync_ledger, 'get_sync_job', forbidden)
    content_id = 'content_' + uuid.uuid4().hex

    def submit(number):
        segment = f'segment-{number}'
        value = replace(work(segment), privacy_generation=0)
        binding = ProjectionBinding('synthetic-owner', f'bp_{number}', content_id, (segment,))
        return admit(
            store,
            [value],
            binding,
            100,
            namespace=store.namespace,
            intake={
                'owner_id': binding.owner_id,
                'owner_key': owner_key(binding.owner_id),
                'content_id': content_id,
                'segment_ids': [segment],
                'total_files': 1,
                'lane': 'backfill',
            },
        )

    ref = sync_ledger.sync_content_ledger_ref(store.client, 'synthetic-owner', content_id)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts = list(pool.map(submit, [1, 2]))
        assert receipts[0] == receipts[1]
        winner = receipts[0]['job_id']
        row = ref.get().to_dict()
        assert 'expires_at' not in row  # No TTL may remove pending route ownership.
        monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'false')
        assert submit(3)['job_id'] == winner
        legacy = sync_ledger.claim_sync_content(
            'synthetic-owner', content_id, 'legacy-retry', 'backfill', firestore_client=store.client
        )
        assert legacy['outcome'] == 'busy' and legacy['dispatch_protocol'] == 'batch_v1'
        assert legacy['job_id'] == winner
        assert durable_status(store, 'synthetic-owner', winner)['status'] == 'queued'
        assert len(list(store.client.collection(f'{store.namespace}_jobs').stream())) == 1
        assert store.run(lambda tx: tx.get('jobs', 'segment-3')) == {}
    finally:
        ref.delete()


def test_late_intake_is_atomic_and_revocation_fences_heartbeat_and_result(store, monkeypatch):
    from dataclasses import replace
    from database.batch_pipeline_intake import admit
    from database.batch_pipeline_privacy import BatchPrivacyBlocked
    from utils.batch_pipeline.contracts import ProjectionBinding

    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    queue = Scheduler(store)
    queue.enqueue(work('committed', capture=10), 0)
    lease = queue.pull(0)[0]
    queue.complete(WorkResult('committed', 'gs://synthetic/result'), lease.token, 1)
    OrderedMerge(store).commit_next('synthetic-owner', 2)
    late = replace(work('late', capture=1), privacy_generation=0)
    binding = ProjectionBinding('synthetic-owner', 'bp_late', 'content_' + uuid.uuid4().hex, ('late',))
    admit(store, [late], binding, 3, namespace=store.namespace)
    assert (
        store.run(lambda tx: tx.get('content', f'synthetic-owner/{binding.content_id}'))['dispatch_protocol']
        == 'batch_v1'
    )
    assert store.run(lambda tx: tx.get('jobs', 'late'))['late_capture']
    running = queue.pull(3)[0]
    queue.complete(WorkResult('late', 'gs://synthetic/late'), running.token, 3)
    entry = OrderedMerge(store).commit_next('synthetic-owner', 3)
    assert entry['previous_segment_id'] == 'committed' and entry['capture_at'] == 1
    assert store.projection_pending() == ['committed', 'late']
    queue.enqueue(replace(work('revoked', capture=20), conversation_id='deleted-source'), 3)
    running = queue.pull(3)[0]
    tombstone = (
        store.client.collection('users')
        .document('synthetic-owner')
        .collection('deleted_conversations')
        .document('deleted-source')
    )
    tombstone.set({'deleted': True})
    try:
        with pytest.raises(BatchPrivacyBlocked):
            queue.heartbeat('revoked', running.token, 4)
        with pytest.raises(BatchPrivacyBlocked):
            queue.complete(WorkResult('revoked', 'gs://synthetic/late-result'), running.token, 4)
        assert OrderedMerge(store).committed_result('revoked') == {}
    finally:
        tombstone.delete()


def test_revoked_ring_head_does_not_starve_other_owners_or_priorities(store):
    from dataclasses import replace

    queue = Scheduler(store)
    queue.enqueue(replace(work('blocked', owner='a', priority=Priority.FRESH), conversation_id='deleted'), 0)
    queue.enqueue(work('fresh-ok', owner='fresh', priority=Priority.FRESH), 0)
    queue.enqueue(work('deep-ok', owner='b'), 0)
    tombstone = store.client.collection('users').document('a').collection('deleted_conversations').document('deleted')
    tombstone.set({'deleted': True})
    try:
        assert queue.pull(1)[0].item.segment_id == 'fresh-ok'
        assert queue.pull(1)[0].item.segment_id == 'deep-ok'
        assert queue.pull(1) == []
        assert store.run(lambda tx: tx.get('jobs', 'blocked'))['state'] == 'ready'
    finally:
        tombstone.delete()


@pytest.mark.parametrize('limit', [1, 100])
def test_fenced_expired_lease_does_not_block_recovery_behind_it(store, limit):
    from dataclasses import replace

    queue = Scheduler(store)
    queue.enqueue(replace(work('fenced', owner='a'), conversation_id='deleted'), 0)
    queue.pull(0)
    queue.enqueue(work('normal', owner='b'), 0)
    normal = queue.pull(1)[0]
    assert not store.quarantine_fenced('normal', 2)
    assert store.run(lambda tx: tx.get('jobs', 'normal'))['token'] == normal.token
    tombstone = store.client.collection('users').document('a').collection('deleted_conversations').document('deleted')
    tombstone.set({'deleted': True})
    try:
        # Page size one: first scan must quarantine the fenced head independently.
        assert queue.recover(122, limit=limit) == (1 if limit == 100 else 0)
        assert store.run(lambda tx: tx.get('jobs', 'fenced'))['state'] == 'privacy_blocked'
        if limit == 1:
            assert queue.recover(122, limit=1) == 1
        assert store.due('leased', 122, 1) == []
        queue.recover(127, limit=1)
        lease = queue.pull(127)[0]
        assert lease.item.segment_id == 'normal' and lease.token != normal.token
        assert queue.complete(WorkResult('normal', 'gs://results/normal'), lease.token, 128)
    finally:
        tombstone.delete()


def test_distinct_owners_write_distinct_control_shards(store):
    from config.batch_pipeline import scheduler_control_key
    from utils.batch_pipeline.scheduler import owner_key

    queue = Scheduler(store)
    for owner in ('a', 'b'):
        queue.enqueue(work(owner, owner=owner), 0)
    keys = {scheduler_control_key(owner_key(uid)) for uid in ('a', 'b')}
    assert len(keys) == 2
    controls = store.client.collection(f'{store.namespace}_control')
    assert {doc.id for doc in controls.stream()} == keys
    assert not controls.document('scheduler').get().exists
    assert {v.item.owner_id for v in queue.pull(1, 2)} == {'a', 'b'}


def test_idle_shard_rejoins_at_persistent_frontier_in_transaction(store):
    from utils.batch_pipeline.scheduler import owner_key
    from config.batch_pipeline import scheduler_control_key

    queue = Scheduler(store)
    queue.enqueue(work('old', owner='a'), 0)
    queue.pull(1)
    queue.enqueue(work('new-owner', owner='b'), 2)
    key = scheduler_control_key(owner_key('b'))
    assert store.run(lambda tx: tx.get('control', key))['p2_service'] == 30
    queue.enqueue(work('returning', owner='a'), 2)
    assert {lease.item.owner_id for lease in queue.pull(2, 2)} == {'a', 'b'}
    queue.enqueue(work('rejoin', owner='a'), 3)
    key = scheduler_control_key(owner_key('a'))
    assert store.run(lambda tx: tx.get('control', key))['p2_service'] == 60


@pytest.mark.parametrize('enabled', [False, True])
def test_head_priority_splice_uses_real_queries_and_survives_flag_rollback(store, monkeypatch, enabled):
    monkeypatch.setenv('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', str(enabled).lower())
    queue = Scheduler(store)
    for sid, capture in [('newer', 20), ('head', 10)]:
        queue.enqueue(work(sid, capture), 0)
    first = queue.pull(1)[0]
    assert first.item.segment_id == ('head' if enabled else 'newer')
    monkeypatch.setenv('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', 'false')
    queue.enqueue(work('tail', 30), 2)
    rest = queue.pull(3, 2)
    assert [v.item.segment_id for v in rest] == (['newer', 'tail'] if enabled else ['head', 'tail'])
    for lease in [first, *rest]:
        assert queue.complete(WorkResult(lease.item.segment_id, 'gs://synthetic/result'), lease.token, 4)
    merge = OrderedMerge(store)
    assert [merge.commit_next('synthetic-owner', 5)['segment_id'] for _ in range(3)] == ['head', 'newer', 'tail']


def test_head_priority_does_not_flush_privacy_fenced_link_mutations(store, monkeypatch):
    from dataclasses import replace

    monkeypatch.setenv('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', 'true')
    queue = Scheduler(store)
    queue.enqueue(work('newer', 20), 0)
    queue.enqueue(replace(work('head', 10), conversation_id='removed'), 0)
    store.client.collection('users').document('synthetic-owner').collection('deleted_conversations').document(
        'removed'
    ).set({'deleted': True})
    assert queue.pull(1)[0].item.segment_id == 'newer'
    assert queue.pull(2) == []
    assert store.run(lambda tx: tx.get('jobs', 'head'))['state'] == 'ready'


def test_projection_cursor_handles_timestamp_ties_deleted_anchor_wrap_and_restart(store):
    from utils.batch_pipeline.projection_discovery import ProjectionDiscovery

    collection = store.client.collection(f'{store.namespace}_results')
    for sid in ('a', 'b', 'c'):
        collection.document(sid).set({'projection_state': 'ready', 'committed_at': 2.0})
    scan = ProjectionDiscovery(store)
    assert scan.next(1) == ['a']
    collection.document('a').delete()
    assert scan.next(1) == ['b']
    assert scan.next(1) == ['c']
    assert scan.next(1) == []
    assert scan.next(1) == ['b']
    assert ProjectionDiscovery(store).next(1) == ['b']


def test_indexed_reverse_upload_head_survives_competing_pulls(store, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', 'true')
    queue = Scheduler(store)
    for n in reversed(range(160)):
        assert queue.enqueue(work(f'reverse-{n:03}', n), 0)
    # Two workers may compute for this owner at once. Only one owns the head;
    # its neighbor uses the ordinary FIFO until that pending head commits.
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(queue.pull, 1) for _ in range(2)]
        leases = [lease for future in futures for lease in future.result()]
    assert len({lease.item.segment_id for lease in leases}) == 2
    assert 'reverse-000' in {lease.item.segment_id for lease in leases}
    assert len([lease for lease in leases if lease.item.segment_id == 'reverse-000']) == 1
    by_id = {lease.item.segment_id: lease for lease in leases}
    later = next(lease for lease in leases if lease.item.segment_id != 'reverse-000')
    assert queue.complete(WorkResult(later.item.segment_id, 'gs://synthetic/later'), later.token, 2)
    merge = OrderedMerge(store)
    assert merge.commit_next('synthetic-owner', 2) is None
    assert queue.complete(WorkResult('reverse-000', 'gs://synthetic/head'), by_id['reverse-000'].token, 3)
    assert merge.commit_next('synthetic-owner', 3)['segment_id'] == 'reverse-000'
    assert queue.pull(4)[0].item.segment_id == 'reverse-001'


def test_partial_pull_failure_keeps_committed_leases_and_release_is_fenced(store, monkeypatch):
    from utils.batch_pipeline import scheduler as module

    queue = Scheduler(store)
    for n, owner in enumerate(('a', 'b', 'light')):
        assert queue.enqueue(work(owner, n, owner=owner), 0)
    built = [0]

    class FailingWorkItem(WorkItem):
        def __post_init__(self):
            built[0] += 1
            if built[0] == 3:
                raise ValueError('synthetic validation failure inside lease 3')
            super().__post_init__()

    # Raised inside the third lease transaction, so Firestore rolls it back.
    monkeypatch.setattr(module, 'WorkItem', FailingWorkItem)
    pulled = queue.pull(1, 3)
    monkeypatch.undo()
    assert len(pulled) == 2
    claimed = {v.item.segment_id for v in pulled}
    (rest,) = {'a', 'b', 'light'} - claimed
    assert [v.item.segment_id for v in queue.pull(2, 3)] == [rest]
    first, second = pulled
    assert queue.complete(WorkResult(first.item.segment_id, 'gs://results/x'), first.token, 3)
    assert not queue.release(second.item.segment_id, 'stale-token', 3)
    assert queue.release(second.item.segment_id, second.token, 3)
    assert not queue.release(first.item.segment_id, first.token, 3)
    assert queue.recover(8) == 1
    retried = queue.pull(8)[0]
    assert retried.item.segment_id == second.item.segment_id and retried.attempt == 2
    assert not queue.complete(WorkResult(second.item.segment_id, 'gs://results/stale'), second.token, 9)
    assert queue.complete(WorkResult(second.item.segment_id, 'gs://results/y'), retried.token, 9)
