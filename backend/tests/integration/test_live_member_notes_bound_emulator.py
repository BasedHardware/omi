"""Real Firestore contention proof for the live-member paid-once permit."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from database import live_member_notes

pytestmark = pytest.mark.integration


@pytest.fixture
def seeded():
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('requires a loopback Firestore emulator')
    client = firestore.Client(project='demo-q12-live-notes', credentials=AnonymousCredentials())
    suffix = uuid4().hex
    job_id, cid, uid = f'job-{suffix}', f'member-{suffix}', f'synthetic-{suffix}'
    job = client.collection('conversation_finalization_jobs').document(job_id)
    conversation = client.collection('users').document(uid).collection('conversations').document(cid)
    job.set(
        {
            'uid': uid,
            'conversation_id': cid,
            'status': 'leased',
            'dispatch_generation': 1,
            'lease_epoch': 2,
            'lease_expires_at': datetime.now(timezone.utc) + timedelta(minutes=10),
            'finalization_revision': 1,
        }
    )
    conversation.set(
        {'status': 'processing', 'finalization_job_id': job_id, 'finalization_revision': 1, 'sync_content_revision': 3}
    )
    try:
        yield client, uid, cid, job_id, job, conversation
    finally:
        conversation.delete()
        job.delete()
        client.close()


def test_concurrent_finalizers_and_retries_buy_one_per_revision(seeded):
    client, uid, cid, job_id, job, conversation = seeded
    barrier = Barrier(4)

    def compete(_):
        barrier.wait(timeout=10)
        return live_member_notes.claim(uid, cid, (job_id, 1, 2), 3, firestore_client=client)

    with ThreadPoolExecutor(max_workers=4) as executor:
        assert sum(executor.map(compete, range(4))) == 1
    for _ in range(3):
        assert not live_member_notes.claim(uid, cid, (job_id, 1, 2), 3, firestore_client=client)
    job.update({'lease_epoch': 3})
    assert not live_member_notes.claim(uid, cid, (job_id, 1, 3), 3, firestore_client=client)
    conversation.update({'sync_content_revision': 4})
    assert not live_member_notes.claim(uid, cid, (job_id, 1, 2), 4, firestore_client=client)
    assert live_member_notes.claim(uid, cid, (job_id, 1, 3), 4, firestore_client=client)
    assert not live_member_notes.claim(uid, cid, (job_id, 1, 3), 4, firestore_client=client)
