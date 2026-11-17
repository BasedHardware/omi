"""Real transaction races for sealed owner groups. Requires a loopback emulator."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import batch_pipeline_conversation_purge as purge
from database import batch_pipeline_conversation_purge_scans as scans
from database import conversation_batch_purge_jobs as jobs
from database import legal_holds
from tests.integration.test_conversation_batch_purge_emulator import plane  # noqa: F401


@pytest.fixture
def world(monkeypatch, plane):
    monkeypatch.delenv(scans.SWITCH, raising=False)
    monkeypatch.setattr(purge, 'conversation_objects', lambda *a, **k: [])
    monkeypatch.setattr(purge, 'purge_jobstore_owner', lambda *a: 0)
    monkeypatch.setattr(purge, 'mirror_refresh', lambda *a: None)
    from utils.batch_pipeline import retention
    from utils.other import local_storage

    monkeypatch.setattr(local_storage, 'create_storage_client', MagicMock)
    monkeypatch.setattr(retention, 'delete_batch_object', lambda *a, **k: None)

    def arm(cid, *, progress=None):
        plane.client.document(f'users/{plane.uid}/deleted_conversations/{cid}').set({'id': cid})
        ref = jobs.job_ref(plane.client, plane.uid, cid)
        ref.set(jobs.arm_fields(plane.uid, cid), merge=True)
        if progress:
            ref.update({'progress': progress})
        return ref.id

    return SimpleNamespace(**vars(plane), arm=arm)


def _dispatch(world, job):
    return jobs.claim_dispatch(job, firestore_client=world.client)[0]


def _run(world, job, generation, **kwargs):
    return scans.run_job(job, generation, firestore_client=world.client, sleep=lambda _: None, **kwargs)


def _expire(world, scan):
    for job in scan['members']:
        world.client.collection(jobs.COLLECTION).document(job).update(
            {
                'lease_until': jobs._now() - timedelta(seconds=1),
                'due_at': jobs._now(),
            }
        )


def _seed(world, cids, *, others=0):
    for namespace in purge.NAMESPACES:
        world.client.collection(f'{namespace}_owners').document(world.key).set({'projection_watermark': 'none'})
        batch = world.client.batch()
        for n, cid in enumerate(cids):
            segment = f'mine-{n}'
            batch.set(
                world.client.collection(f'{namespace}_results').document(segment),
                {
                    'owner_key': world.key,
                    'owner_id': world.uid,
                    'conversation_id': cid,
                    'segment_id': segment,
                },
            )
            batch.set(
                world.client.collection(f'{namespace}_artifacts').document(segment),
                {
                    'owner_key': 'corrupt',
                    'owner_id': world.uid,
                    'segment_id': segment,
                },
            )
            batch.set(
                world.client.collection(f'{namespace}_intakes').document(segment),
                {
                    'owner_key': world.key,
                    'owner_id': world.uid,
                    'segment_ids': [segment],
                },
            )
        for n in range(others):
            batch.set(
                world.client.collection(f'{namespace}_results').document(f'other-{n:04}'),
                {
                    'owner_key': world.key,
                    'owner_id': world.uid,
                    'conversation_id': 'retained',
                    'segment_id': f'other-{n:04}',
                },
            )
        batch.commit()


def _assert_erased(world, cids):
    for namespace in purge.NAMESPACES:
        for n, cid in enumerate(cids):
            result = world.client.collection(f'{namespace}_results').document(f'mine-{n}').get().to_dict()
            assert result.get('projection_state') == 'erased'
            for table in ('artifacts', 'intakes'):
                assert not world.client.collection(f'{namespace}_{table}').document(f'mine-{n}').get().exists
            assert not jobs.job_ref(world.client, world.uid, cid).get().exists
            assert jobs.segment_records(jobs.job_id(world.uid, cid), namespace, firestore_client=world.client) == []


def test_real_route_six_members_one_traversal_both_namespaces(monkeypatch, world):
    from routers import users

    cids = [f'c{n}' for n in range(6)]
    leader, *followers = [world.arm(cid) for cid in cids]
    generation = _dispatch(world, leader)
    _seed(world, cids, others=210)
    reads, parked, shadows, originals = [], [], [], []
    owner_query, artifact_query = purge.queries.owner_documents, purge.queries.artifacts_by_owner_id

    def counted(*args, **kwargs):
        reads.append((args[1], args[2]))
        return owner_query(*args, **kwargs)

    def counted_parked(*args, **kwargs):
        parked.append(args[1])
        return artifact_query(*args, **kwargs)

    monkeypatch.setattr(purge.queries, 'owner_documents', counted)
    monkeypatch.setattr(purge.queries, 'artifacts_by_owner_id', counted_parked)
    monkeypatch.setattr(purge, 'purge_jobstore_owner', lambda ns, uid: shadows.append(ns))
    monkeypatch.setattr(purge, 'conversation_objects', lambda uid, cid, **k: originals.append(cid) or [])
    monkeypatch.setattr(scans.jobs, 'UNIT_YIELD_SECONDS', 0)
    app = FastAPI()
    app.include_router(users.router)
    app.dependency_overrides[users.verify_conversation_batch_purge_cloud_tasks_oidc] = lambda: 0
    with TestClient(app) as client:
        response = client.post(
            '/v1/conversations/deletion-batch-purges/run', json={'job_id': leader, 'generation': generation}
        )
    assert response.status_code == 200 and response.json()['outcome'] == 'purged'
    assert reads.count(('batch_pipeline_prod', 'results')) == 4
    assert reads.count(('batch_pipeline_dev', 'results')) == 4
    assert len(parked) == 4 and set(originals) == set(cids)
    assert shadows == list(purge.NAMESPACES)
    _assert_erased(world, cids)
    assert _run(world, leader, generation) == 'missing'


def test_checkpoint_duplicate_delivery_and_new_generation_resume(monkeypatch, world):
    cids = ['one', 'two', 'three']
    leader, *_ = [world.arm(cid) for cid in cids]
    generation = _dispatch(world, leader)
    _seed(world, cids, others=210)
    assert _run(world, leader, generation, budget_seconds=0) == 'checkpointed'
    state = world.client.collection(jobs.COLLECTION).document(leader).get().to_dict()['owner_scan']
    assert state['position']  # even an empty discovery table advances durably
    generation = _dispatch(world, leader)
    assert generation == 2
    # Same-generation delivery resumes safely, then another delivery observes completion.
    assert _run(world, leader, generation) == 'purged'
    assert _run(world, leader, generation) == 'missing'
    _assert_erased(world, cids)


def test_rollback_after_discovery_uses_canonical_member_bindings(monkeypatch, world):
    cids = ['one', 'two']
    leader, follower = [world.arm(cid) for cid in cids]
    generation = _dispatch(world, leader)
    _seed(world, cids)
    original = purge.queries.owner_documents

    def stop_at_artifacts(client, namespace, table, key, **kwargs):
        if table == 'artifacts':
            monkeypatch.setenv(scans.SWITCH, 'false')
        return original(client, namespace, table, key, **kwargs)

    monkeypatch.setattr(purge.queries, 'owner_documents', stop_at_artifacts)
    assert _run(world, leader, generation) == 'superseded'
    for job in (leader, follower):
        row = world.client.collection(jobs.COLLECTION).document(job).get().to_dict()
        assert row.get('progress') is None and not row.get('scan_epoch')
        assert jobs.segment_records(job, purge.NAMESPACES[0], firestore_client=world.client)
        assert jobs.run_job(job, row['generation'], firestore_client=world.client, sleep=lambda _: None) == 'purged'
    _assert_erased(world, cids)


def test_late_arrival_and_rearm_never_inherit_sealed_cursor(world):
    leader, follower = world.arm('one'), world.arm('two')
    generation = _dispatch(world, leader)
    status, scan = scans._claim(world.client, leader, generation)
    assert status == 'run'
    late = world.arm('late')
    assert late not in scan['members']
    progress = scans.ScanProgress(world.client, leader, scan, sleep=lambda _: None)
    progress.checkpoint({'ns': 1, 'phase': 'discover'})
    before = world.client.collection(jobs.COLLECTION).document(follower).get().to_dict()['arm_revision']
    world.arm('two')
    assert world.client.collection(jobs.COLLECTION).document(follower).get().to_dict()['arm_revision'] != before
    with pytest.raises(jobs.RunSuperseded):
        progress.finish('completed')
    scans.handback(world.client, leader, scan['epoch'], scan['token'])
    for job in (leader, follower, late):
        assert world.client.collection(jobs.COLLECTION).document(job).get().exists
    _seed(world, ['one', 'two', 'late'])
    assert _run(world, leader, generation) == 'purged'
    _assert_erased(world, ['one', 'two', 'late'])


def test_old_worker_takeover_invalidates_scan_but_preserves_other_member(world):
    leader, follower = world.arm('one'), world.arm('two')
    generation = _dispatch(world, leader)
    _, scan = scans._claim(world.client, leader, generation)
    assert (
        jobs.run_job(follower, scan['members'][follower]['generation'], firestore_client=world.client) == 'in_progress'
    )
    _expire(world, scan)
    claim, _, legacy_token = jobs.begin_run(
        follower, scan['members'][follower]['generation'], firestore_client=world.client
    )
    assert claim == 'run'
    progress = scans.ScanProgress(world.client, leader, scan)
    with pytest.raises(jobs.RunSuperseded):
        progress.checkpoint({'ns': 2})
    scans.handback(world.client, leader, scan['epoch'], scan['token'])
    row = world.client.collection(jobs.COLLECTION).document(follower).get().to_dict()
    assert row['run_token'] == legacy_token  # old binary retains its own lease
    assert (
        jobs.finish_run(follower, row['generation'], legacy_token, 'checkpointed', firestore_client=world.client)
        is False
    )
    _seed(world, ['one', 'two'])
    for job in (leader, follower):
        row = world.client.collection(jobs.COLLECTION).document(job).get().to_dict()
        assert jobs.run_job(job, row['generation'], firestore_client=world.client, sleep=lambda _: None) == 'purged'
    _assert_erased(world, ['one', 'two'])


def test_partial_legacy_progress_is_never_enrolled(world):
    leader, follower = world.arm('one'), world.arm('two', progress={'ns': 0, 'phase': 'parked'})
    generation = _dispatch(world, leader)
    assert scans._claim(world.client, leader, generation) == ('legacy', None)
    assert world.client.collection(jobs.COLLECTION).document(follower).get().to_dict()['progress']['phase'] == 'parked'


def test_concurrent_sealers_never_share_a_member(world):
    ids = [world.arm(f'c{i}') for i in range(6)]
    generations = {job: _dispatch(world, job) for job in ids[:2]}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda job: scans._claim(world.client, job, generations[job]), ids[:2]))
    claims = [scan for status, scan in results if status == 'run']
    assert len(claims) == 1
    assert len(claims[0]['members']) == 6


def test_old_rearm_without_revision_field_is_detected(world):
    leader, follower = world.arm('one'), world.arm('two')
    generation = _dispatch(world, leader)
    _, scan = scans._claim(world.client, leader, generation)
    world.client.collection(jobs.COLLECTION).document(follower).update({'armed_at': jobs._now()})
    with pytest.raises(jobs.RunSuperseded):
        scans.ScanProgress(world.client, leader, scan).checkpoint({'ns': 2})


def test_max_group_bound_and_stale_handback_cannot_revoke_new_token(world):
    ids = [world.arm(f'c{i}') for i in range(scans.MAX_MEMBERS + 4)]
    leader = ids[0]
    generation = _dispatch(world, leader)
    _, scan = scans._claim(world.client, leader, generation)
    assert 2 <= len(scan['members']) <= scans.MAX_MEMBERS
    progress = scans.ScanProgress(world.client, leader, scan)
    progress.checkpoint({'ns': 0, 'phase': 'discover'})
    progress.finish('checkpointed')
    _, successor = scans._claim(world.client, leader, generation)
    assert successor['token'] != scan['token']
    assert not scans.handback(world.client, leader, scan['epoch'], scan['token'])
    assert world.client.collection(jobs.COLLECTION).document(leader).get().to_dict()['run_token'] == successor['token']


def test_all_phases_required_and_missing_tombstone_revokes_group(world):
    leader, follower = world.arm('one'), world.arm('two')
    generation = _dispatch(world, leader)
    _, scan = scans._claim(world.client, leader, generation)
    progress = scans.ScanProgress(world.client, leader, scan)
    with pytest.raises(RuntimeError, match='phases'):
        progress.finish('completed')
    world.client.document(f'users/{world.uid}/deleted_conversations/two').delete()
    with pytest.raises(jobs.RunSuperseded):
        with progress.unit():
            pytest.fail('missing deletion intent granted a destructive unit')
    scans.handback(world.client, leader, scan['epoch'], scan['token'])
    assert (
        jobs.run_job(follower, scan['members'][follower]['generation'], firestore_client=world.client) == 'no_tombstone'
    )
    assert world.client.collection(jobs.COLLECTION).document(leader).get().exists


def test_legal_hold_between_group_units_preserves_all_obligations(monkeypatch, world):
    cids = ['one', 'two']
    leader, follower = [world.arm(cid) for cid in cids]
    generation = _dispatch(world, leader)
    _seed(world, cids)
    page = purge.queries.owner_documents
    placed = []

    def place_hold(client, namespace, table, key, **kwargs):
        rows = page(client, namespace, table, key, **kwargs)
        if table == 'artifacts' and not placed:
            legal_holds.place_legal_hold(world.uid, issuer='synthetic', active=True)
            placed.append(True)
        return rows

    monkeypatch.setattr(purge.queries, 'owner_documents', place_hold)
    assert _run(world, leader, generation) == 'held'
    for job in (leader, follower):
        assert world.client.collection(jobs.COLLECTION).document(job).get().exists
        assert jobs.segment_records(job, purge.NAMESPACES[0], firestore_client=world.client)
    legal_holds.place_legal_hold(world.uid, issuer='synthetic', active=False)
    assert _run(world, leader, generation) == 'purged'
    _assert_erased(world, cids)


def test_shared_wal_reservations_release_once_after_unknown_delete(monkeypatch, world):
    from database import record_wal_capacity as capacity
    from utils.batch_pipeline import retention
    from google.api_core.exceptions import ServiceUnavailable

    leader, follower = world.arm('one'), world.arm('two')
    generation = _dispatch(world, leader)
    uri = f'gs://synthetic/record-wal/{world.uid}/one/file.enc#123'
    # One reservation referenced by both members. Each capacity ledger must
    # retire exactly once even when a remote delete's first outcome is unknown.
    for ref in capacity._refs(world.client, world.uid):
        ref.set({'schema': capacity.SCHEMA, 'bytes': 100, 'files': 1})
    ref = world.client.collection('batch_pipeline_prod_intakes').document('shared-wal')
    ref.set(
        {
            'owner_key': world.key,
            'owner_id': world.uid,
            'kind': capacity.RESERVATION_KIND,
            'conversation_ids': ['one', 'two'],
            'quota_bytes': 100,
            'uri': uri,
        }
    )
    calls = []

    def uncertain(*args, **kwargs):
        calls.append(True)
        raise ServiceUnavailable('synthetic unresolved outcome')

    monkeypatch.setattr(retention, 'delete_batch_object', uncertain)
    with pytest.raises(ServiceUnavailable):
        _run(world, leader, generation)
    assert ref.get().exists and capacity.sample(world.client) == {'bytes': 100, 'files': 1}
    monkeypatch.setattr(retention, 'delete_batch_object', lambda *a, **k: None)
    assert _run(world, leader, generation) == 'purged'
    assert capacity.sample(world.client) == {'bytes': 0, 'files': 0}
    assert not ref.get().exists
    assert _run(world, follower, 1) == 'missing'
