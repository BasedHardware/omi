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
from database import conversation_purge_budget as purge_budget
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

    def no_configured_shadow(namespace, _uid, _after):
        shadows.append(namespace)
        return False, None

    monkeypatch.setattr(purge, 'purge_owner_page', no_configured_shadow)
    monkeypatch.setattr(purge, 'conversation_objects', lambda uid, cid, **k: originals.append(cid) or [])
    monkeypatch.setattr(scans.jobs, 'UNIT_YIELD_SECONDS', 0)
    app = FastAPI()
    app.include_router(users.router)
    app.dependency_overrides[users.verify_conversation_batch_purge_cloud_tasks_oidc] = lambda: 0
    with TestClient(app) as client:
        for _ in range(6):
            response = client.post(
                '/v1/conversations/deletion-batch-purges/run', json={'job_id': leader, 'generation': generation}
            )
            assert response.status_code == 200
            outcome = response.json()['outcome']
            if outcome == 'purged':
                break
            assert outcome == 'checkpointed'
            generation = _dispatch(world, leader)
        else:
            pytest.fail('bounded route did not converge')
    assert 4 <= reads.count(('batch_pipeline_prod', 'results')) <= 5
    assert 4 <= reads.count(('batch_pipeline_dev', 'results')) <= 5
    assert 4 <= len(parked) <= 6 and set(originals) == set(cids)
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
    jobs.finish_run(follower, row['generation'], legacy_token, 'checkpointed', firestore_client=world.client)
    settled = world.client.collection(jobs.COLLECTION).document(follower).get().to_dict()
    assert settled['last_outcome'] == 'checkpointed' and settled['run_token'] is None
    assert settled['due_at'] <= jobs._now()
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


def test_delivered_leader_outside_first_candidate_page_still_seals_a_bounded_group(world):
    ids = [world.arm(f'overflow-{n}') for n in range(scans.MAX_MEMBERS + 1)]
    leader = max(ids)  # default name order places it beyond the first limit(16)
    assert leader not in {snapshot.id for snapshot in scans.owner_candidates(world.uid, firestore_client=world.client)}
    generation = _dispatch(world, leader)
    status, scan = scans._claim(world.client, leader, generation)
    assert status == 'run' and leader in scan['members']
    assert len(scan['members']) == scans.MAX_MEMBERS
    outside = set(ids) - scan['members'].keys()
    assert len(outside) == 1
    excluded = world.client.collection(jobs.COLLECTION).document(outside.pop()).get().to_dict()
    assert not excluded.get('scan_epoch') and not jobs.lease_held(excluded)
    assert scans.handback(world.client, leader, scan['epoch'], scan['token'])
    assert all(world.client.collection(jobs.COLLECTION).document(job).get().exists for job in ids)


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
            legal_holds.place_legal_hold(world.uid, issuer='admin', active=True)
            placed.append(True)
        return rows

    monkeypatch.setattr(purge.queries, 'owner_documents', place_hold)
    assert _run(world, leader, generation) == 'held'
    for job in (leader, follower):
        assert world.client.collection(jobs.COLLECTION).document(job).get().exists
        assert jobs.segment_records(job, purge.NAMESPACES[0], firestore_client=world.client)
    legal_holds.place_legal_hold(world.uid, issuer='admin', active=False)
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


def test_legacy_leader_takeover_cannot_rejoin_its_old_shared_cursor(world):
    leader, follower = world.arm('one'), world.arm('two')
    generation = _dispatch(world, leader)
    _, scan = scans._claim(world.client, leader, generation)
    progress = scans.ScanProgress(world.client, leader, scan)
    progress.checkpoint({'ns': 1, 'phase': 'dependents', 'table': 3})
    progress.finish('checkpointed')
    # A pre-coalescing binary can claim the leader after its handoff/expiry.
    claim, row, token = jobs.begin_run(leader, generation, firestore_client=world.client)
    assert claim == 'run'
    legacy = jobs.RunProgress(world.client, leader, generation, token, world.uid, row.get('progress'))
    legacy.checkpoint({'ns': 0, 'phase': 'parked'})
    jobs.finish_run(leader, generation, token, 'checkpointed', firestore_client=world.client)
    # Even if that binary has now released its lease, the shared cursor must
    # never be resurrected over the independent worker's changed ownership.
    assert scans._claim(world.client, leader, generation) == ('legacy', None)
    row = world.client.collection(jobs.COLLECTION).document(leader).get().to_dict()
    assert row['progress'] == {'ns': 0, 'phase': 'parked'} and not row.get('owner_scan')
    assert not world.client.collection(jobs.COLLECTION).document(follower).get().to_dict().get('scan_epoch')


@pytest.mark.parametrize('phase', ['seal', 'resume'])
def test_ambiguous_claim_commit_recovers_same_members_and_token(monkeypatch, world, phase):
    from google.api_core.exceptions import ServiceUnavailable

    leader, follower = world.arm('one'), world.arm('two')
    generation = _dispatch(world, leader)
    if phase == 'resume':
        _, first = scans._claim(world.client, leader, generation)
        progress = scans.ScanProgress(world.client, leader, first)
        progress.checkpoint({'ns': 0, 'phase': 'discover'})
        progress.finish('checkpointed')
    run_transactional = scans.run_transactional
    lost = []

    def lose_reply(client, operation, **kwargs):
        def commit_then_lose_response(transaction):
            result = operation(transaction)  # Real emulator commit, then lose its reply at the caller boundary.
            if not lost:
                lost.append(True)
                raise ServiceUnavailable('synthetic reply lost after commit')
            return result

        return run_transactional(client, commit_then_lose_response, **kwargs)

    monkeypatch.setattr(scans, 'run_transactional', lose_reply)
    status, scan = scans._claim(world.client, leader, generation)
    assert status == 'run' and set(scan['members']) == {leader, follower}
    for job, member in scan['members'].items():
        row = world.client.collection(jobs.COLLECTION).document(job).get().to_dict()
        assert row['run_token'] == scan['token'] and row['generation'] == member['generation']
    scans.ScanProgress(world.client, leader, scan).checkpoint({'ns': 0, 'phase': 'discover'})


def test_paused_scan_retains_takeover_proof_but_cannot_write_again(world):
    leader, follower = world.arm('one'), world.arm('two')
    generation = _dispatch(world, leader)
    _, scan = scans._claim(world.client, leader, generation)
    progress = scans.ScanProgress(world.client, leader, scan)
    progress.finish('checkpointed')
    for operation in (
        lambda: progress.checkpoint({'ns': 1}),
        lambda: progress.add_segments(follower, purge.NAMESPACES[0], ['stale']),
    ):
        with pytest.raises(jobs.RunSuperseded):
            operation()
    assert not jobs.segment_records(follower, purge.NAMESPACES[0], firestore_client=world.client)


def test_lease_renewal_keeps_active_members_out_of_the_due_queue(monkeypatch, world):
    leader, follower = world.arm('one'), world.arm('two')
    generation = _dispatch(world, leader)
    _, scan = scans._claim(world.client, leader, generation)
    sealed = jobs._now()
    renewed = sealed + timedelta(seconds=240)
    monkeypatch.setattr(jobs, '_now', lambda: renewed)
    scans.ScanProgress(world.client, leader, scan).checkpoint({'ns': 0, 'phase': 'discover'})
    for job in (leader, follower):
        row = world.client.collection(jobs.COLLECTION).document(job).get().to_dict()
        assert row['due_at'] == row['lease_until'] == renewed + timedelta(seconds=jobs.LEASE_SECONDS)
    assert jobs.due_jobs(now=sealed + timedelta(seconds=301), firestore_client=world.client) == []


def test_handback_emits_shared_fallback_telemetry_once(monkeypatch, world):
    from unittest.mock import Mock

    leader, follower = world.arm('one'), world.arm('two')
    generation = _dispatch(world, leader)
    _, scan = scans._claim(world.client, leader, generation)
    event = Mock()
    monkeypatch.setattr(scans, 'record_fallback', event)
    assert scans.handback(world.client, leader, scan['epoch'], scan['token'])
    assert not scans.handback(world.client, leader, scan['epoch'], scan['token'])
    event.assert_called_once()
    assert event.call_args.kwargs['outcome'] == 'degraded'


def test_tombstone_loss_after_seal_hands_back_without_a_failed_task(monkeypatch, world):
    from unittest.mock import Mock

    leader, follower = world.arm('one'), world.arm('two')
    generation = _dispatch(world, leader)
    claim = scans._claim

    def wipe_after_seal(*args, **kwargs):
        status, scan = claim(*args, **kwargs)
        if status == 'run':
            for member in scan['members'].values():
                world.client.document(f"users/{world.uid}/deleted_conversations/{member['conversation_id']}").delete()
        return status, scan

    monkeypatch.setattr(scans, '_claim', wipe_after_seal)
    traverse = Mock(side_effect=AssertionError('missing intent must stop before traversal'))
    monkeypatch.setattr(scans, 'purge_conversations', traverse)
    assert _run(world, leader, generation) == 'superseded'
    traverse.assert_not_called()
    for job in (leader, follower):
        row = world.client.collection(jobs.COLLECTION).document(job).get().to_dict()
        assert not row.get('scan_epoch') and row.get('last_outcome') != 'failed'
        assert jobs.run_job(job, row['generation'], firestore_client=world.client) == 'no_tombstone'


def test_tombstone_loss_between_authority_and_data_plane_preflight_is_not_failure(monkeypatch, world):
    leader, follower = world.arm('one'), world.arm('two')
    generation = _dispatch(world, leader)
    check = scans.ScanProgress.check_authority

    def wipe_after_check(progress):
        check(progress)
        for member in progress.scan['members'].values():
            world.client.document(f"users/{world.uid}/deleted_conversations/{member['conversation_id']}").delete()

    monkeypatch.setattr(scans.ScanProgress, 'check_authority', wipe_after_check)
    assert _run(world, leader, generation) == 'superseded'
    for job in (leader, follower):
        row = world.client.collection(jobs.COLLECTION).document(job).get().to_dict()
        assert not row.get('scan_epoch') and row.get('last_outcome') != 'failed'
        assert jobs.run_job(job, row['generation'], firestore_client=world.client) == 'no_tombstone'


@pytest.mark.parametrize('outcome', ['held', 'checkpointed'])
def test_rearm_at_retry_handoff_is_supersession_not_a_failed_task(monkeypatch, world, outcome):
    leader, follower = world.arm('one'), world.arm('two')
    generation = _dispatch(world, leader)

    def interrupt(uid, members, progress, **kwargs):
        progress.checkpoint({'ns': 0, 'phase': 'discover'})
        world.arm('two')
        if outcome == 'held':
            raise legal_holds.LegalHoldActive(world.uid)
        raise purge.PurgeCheckpointed()

    monkeypatch.setattr(scans, 'purge_conversations', interrupt)
    assert _run(world, leader, generation) == 'superseded'
    for job in (leader, follower):
        row = world.client.collection(jobs.COLLECTION).document(job).get().to_dict()
        assert row and not row.get('scan_epoch') and row.get('last_outcome') != 'failed'


def test_tombstone_audit_after_coalesced_completion(world, caplog):
    from unittest.mock import Mock

    from scripts import audit_conversation_purge_remainders as audit

    start = jobs._now() - timedelta(seconds=1)
    cids = ('synthetic-audit-done-a', 'synthetic-audit-done-b')
    armed = [world.arm(cid) for cid in cids]
    for cid in cids:
        world.client.document(f'users/{world.uid}/deleted_conversations/{cid}').update({'deleted_at': jobs._now()})
    _seed(world, cids)
    assert _run(world, armed[0], _dispatch(world, armed[0])) == 'purged'

    pending = 'synthetic-audit-pending'
    world.arm(pending)
    world.client.document(f'users/{world.uid}/deleted_conversations/{pending}').update({'deleted_at': jobs._now()})
    gcs = Mock()
    gcs.list_blobs.return_value = []
    end = jobs._now() + timedelta(seconds=1)
    report = audit.audit(world.client, gcs, start, end, audit.Budget(200))
    assert (report['tombstones'], report['terminal_checked'], report['pending']) == (3, 2, 1)
    assert not any(report['remainders'].values())

    events = [
        event for event in caplog.messages if event.startswith('event=conversation_batch_purge_owner_scan_audit ')
    ]
    assert len(events) == 2
    assert 'kind=sealed outcome=sealed members=2' in events[0]
    assert 'kind=terminal outcome=completed members=2' in events[1]
    assert events[0].split('epoch_hash=')[1] == events[1].split('epoch_hash=')[1]
    assert all(world.uid not in event and all(cid not in event for cid in cids) for event in events)


def test_pending_artifact_defers_group_until_parked_receipt_replays(world):
    leader = world.arm('one')
    world.arm('two')
    _seed(world, ['one', 'two'])
    receipt = world.client.collection('batch_pipeline_prod_artifacts').document('mine-0')
    receipt.update({'write_pending_until': jobs._now() + timedelta(minutes=5)})

    generation = _dispatch(world, leader)
    before = jobs._now()
    assert _run(world, leader, generation) == 'artifact_pending'
    leader_ref = jobs.job_ref(world.client, world.uid, 'one')
    saved = leader_ref.get().to_dict()
    assert saved['last_outcome'] == 'artifact_pending'
    assert saved['attempts'] == 0 and saved['lease_until'] is None
    assert saved['due_at'] >= before + timedelta(seconds=jobs.ARTIFACT_RETRY_SECONDS)
    assert saved['owner_scan']['position']['phase'] == 'parked'
    assert receipt.get().get('erasure_requested') is True
    assert jobs.segment_records(leader, 'batch_pipeline_prod', firestore_client=world.client)

    # Advance the pending receipt and dispatch clock without waiting or expiring the follower.
    receipt.update({'write_pending_until': before - timedelta(seconds=1)})
    leader_ref.update({'due_at': before})
    assert _run(world, leader, _dispatch(world, leader)) == 'purged'
    _assert_erased(world, ['one', 'two'])


@pytest.mark.parametrize('shared', [False, True])
def test_bounded_worker_redrives_both_cursor_types_after_ambiguous_checkpoint(monkeypatch, world, shared):
    cids = ['one', 'two'] if shared else ['one']
    leader, *_ = [world.arm(cid) for cid in cids]
    _seed(world, cids, others=140)
    if not shared:
        monkeypatch.setenv(scans.SWITCH, 'false')
    generation = _dispatch(world, leader)
    progress_type = scans.ScanProgress if shared else jobs.RunProgress
    checkpoint = progress_type.checkpoint

    def lost_response(progress, *args, **kwargs):
        checkpoint(progress, *args, **kwargs)
        raise RuntimeError('synthetic commit reply lost')

    with monkeypatch.context() as fault:
        fault.setattr(progress_type, 'checkpoint', lost_response)
        with purge_budget.activate(purge_budget.Dispatch(reads=1000)):
            with pytest.raises(RuntimeError, match='commit reply lost'):
                _run(world, leader, generation)

    ref = world.client.collection(jobs.COLLECTION).document(leader)
    pending = ref.get().to_dict()
    cursor = pending['owner_scan']['position'] if shared else pending['progress']
    assert cursor
    for _ in range(20):
        ref.update({'due_at': jobs._now()})
        generation = _dispatch(world, leader)
        with purge_budget.activate(purge_budget.Dispatch(reads=1000)):
            outcome = _run(world, leader, generation)
        if outcome == 'purged':
            break
        assert outcome == 'checkpointed'
    else:
        pytest.fail('purge did not reach completion from the saved cursor')
    with purge_budget.activate(purge_budget.Dispatch(reads=1000)):
        assert _run(world, leader, generation) == 'missing'
    _assert_erased(world, cids)
