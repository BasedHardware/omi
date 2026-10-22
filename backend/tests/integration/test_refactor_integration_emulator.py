"""Cross-lane lifecycle transactions against a loopback-only Firestore emulator."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
from urllib.parse import urlparse
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database import conversation_merge_jobs as merges
from database import conversation_quiet_checks as checks
from database import recording_sessions
from database import review_overlay_merge

pytestmark = pytest.mark.integration


@pytest.fixture
def world():
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if urlparse(f'//{host}').hostname not in {'127.0.0.1', 'localhost', '::1'}:
        pytest.fail('requires loopback Firestore emulator')
    client = firestore.Client(project='demo-refactor-integration', credentials=AnonymousCredentials())
    owner = uuid4().hex
    user = client.collection('users').document(owner)
    yield client, owner, user
    client.close()


def seed_empty(world):
    client, owner, user = world
    now = datetime.now(timezone.utc)
    user.collection('conversations').document('empty').set(
        {
            'source': 'omi',
            'status': 'in_progress',
            'has_content': False,
            'finished_at': now - timedelta(minutes=10),
            'external_data': {'recording_session_id': 'recording'},
        }
    )
    user.collection('recording_sessions').document('recording').set(
        {
            'uid': owner,
            'recording_session_id': 'recording',
            'conversation_id': 'empty',
            'lifecycle_phase': 'in_progress',
            'lease_expires_at': now - timedelta(minutes=5),
        }
    )
    return now


@pytest.mark.parametrize('race', ['none', 'reconnect', 'content'])
def test_empty_cleanup_rechecks_lease_and_content_after_evaluation(world, monkeypatch, race):
    client, owner, user = world
    now = seed_empty(world)
    monkeypatch.setenv('LIFECYCLE_V2_MODE', 'serve')
    check = checks.arm_quiet_check(owner, 'empty', 120, firestore_client=client)
    result = checks.evaluate_quiet_check(check['job_id'], check['dispatch_generation'], firestore_client=client)
    assert result['status'] == 'empty_ready'
    if race == 'reconnect':
        user.collection('recording_sessions').document('recording').update(
            {'lease_expires_at': now + timedelta(minutes=10)}
        )
    elif race == 'content':
        user.collection('conversations').document('empty').update({'has_content': True})
    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        owner,
        'empty',
        'recording',
        firestore_client=client,
        recovery_cutoff=result['recovery_cutoff'],
        require_expired_recording_lease=True,
    )
    assert deleted is (race == 'none')
    assert user.collection('conversations').document('empty').get().exists is (race != 'none')


def test_racing_merge_admissions_claim_every_source_or_none(world):
    client, owner, user = world
    for cid in ('a', 'b'):
        user.collection('conversations').document(cid).set({'status': 'completed'})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: merges.admit(owner, ['a', 'b'], False, firestore_client=client), range(2)))
    winner = next(result for result in results if result is not None)
    assert sum(result is not None for result in results) == 1
    assert all(
        user.collection('conversations').document(cid).get().to_dict()['merge_job_id'] == winner['job_id']
        for cid in ('a', 'b')
    )


def seed_merge(world):
    client, owner, user = world
    for index, cid in enumerate(('a', 'b')):
        user.collection('conversations').document(cid).set(
            {
                'status': 'completed',
                'transcript_segments': [
                    {'id': cid, 'text': 'synthetic fixture', 'start': index, 'end': index + 1, 'is_user': False}
                ],
            }
        )
    job = merges.admit(owner, ['a', 'b'], False, firestore_client=client)
    claimed = merges.claim(job['job_id'], firestore_client=client)
    target = user.collection('conversations').document(job['merge_target_id'])
    segments = [
        user.collection('conversations').document(cid).get().to_dict()['transcript_segments'][0] for cid in ('a', 'b')
    ]
    target.set({'status': 'completed', 'transcript_segments': segments})
    assert merges.renew(job['job_id'], claimed['lease_epoch'], phase='source_retraction', firestore_client=client)
    return job, claimed, target


def test_correction_transfer_atomically_seals_cleanup_and_expiry_requeues_without_rollback(world, monkeypatch):
    client, owner, user = world
    job, claimed, target = seed_merge(world)
    assert review_overlay_merge.transfer(
        owner,
        ['a', 'b'],
        target.id,
        placements=[[0], [1]],
        firestore_client=client,
        merge_job_id=job['job_id'],
        merge_lease_epoch=claimed['lease_epoch'],
    )
    persisted = client.collection(merges.COLLECTION).document(job['job_id']).get().to_dict()
    assert persisted['phase'] == 'source_cleanup'
    assert all(
        user.collection('conversations').document(cid).get().to_dict()['transcript_corrections_moved_to'] == target.id
        for cid in ('a', 'b')
    )
    monkeypatch.setattr(merges, '_now', lambda: datetime.now(timezone.utc) + merges.LEASE + timedelta(seconds=1))
    replay = merges.begin_recovery(job['job_id'], firestore_client=client)
    assert replay['recovery'] == 'resume_cleanup' and replay['dispatch_generation'] == 2
    assert target.get().exists
    assert all(
        user.collection('conversations').document(cid).get().to_dict()['status'] == 'merging' for cid in ('a', 'b')
    )


def test_stale_worker_cannot_move_corrections_after_lease_recovery(world, monkeypatch):
    client, owner, user = world
    job, claimed, target = seed_merge(world)
    monkeypatch.setattr(merges, '_now', lambda: datetime.now(timezone.utc) + merges.LEASE + timedelta(seconds=1))
    recovery = merges.begin_recovery(job['job_id'], firestore_client=client)
    assert recovery['recovery'] == 'rollback'
    with pytest.raises(Exception, match='lease expired'):
        review_overlay_merge.transfer(
            owner,
            ['a', 'b'],
            target.id,
            placements=[[0], [1]],
            firestore_client=client,
            merge_job_id=job['job_id'],
            merge_lease_epoch=claimed['lease_epoch'],
        )
    assert all(
        not user.collection('conversations').document(cid).get().to_dict().get('transcript_corrections_moved_to')
        for cid in ('a', 'b')
    )
