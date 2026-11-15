"""Real transaction atomicity, contention and durable discovery; synthetic only."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import os
from uuid import uuid4

from google.api_core.exceptions import ServiceUnavailable
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database import record_wal_handoff as handoff
from database import batch_pipeline_purge as purge
from database.batch_pipeline_privacy import BatchPrivacyBlocked, privacy_owner_key

pytestmark = pytest.mark.skipif(
    not os.getenv('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:')),
    reason='isolated loopback Firestore emulator required',
)


@pytest.fixture
def world(monkeypatch):
    project = os.environ.get('GOOGLE_CLOUD_PROJECT', '')
    assert project.startswith('demo-'), 'emulator proofs require a demo project'
    client = firestore.Client(project=project, credentials=AnonymousCredentials())
    uid, cid = 'synthetic-wal-' + uuid4().hex, 'record'
    namespace = 'batch_pipeline_dev'
    user = client.collection('users').document(uid)
    conversation = user.collection('conversations').document(cid)
    user.set({'private_cloud_sync_enabled': True})
    conversation.set(
        {
            'record_lane_owner': 'batch_live_v1',
            'source': 'omi',
            'client_device_id': 'synthetic-device',
            'private_cloud_sync_enabled': True,
            'record_upload_revision': 7,
            'record_audio_closed': True,
        }
    )
    files = [
        {
            'name': f'audio_omi_pcm16_16000_1_fs160_{1700000000 + ordinal}.bin',
            'sha256': str(ordinal + 1) * 64,
            'size': 324,
            'codec': 'pcm16',
            'sample_rate': 16000,
            'channels': 1,
            'frame_size': 160,
            'capture_start': float(1700000000 + ordinal),
            'frame_count': 1,
            'sample_count': 160,
        }
        for ordinal in range(2)
    ]

    def begin(entries=None):
        return handoff.begin(
            client, namespace, uid, cid, files if entries is None else entries, 'omi', 'synthetic-device'
        )

    def originals(fence):
        return [
            {
                'name': entry['name'],
                'file_id': entry['file_id'],
                'sha256': entry['sha256'],
                'size': entry['size'],
                'stored_size': 356,
                'generation': '17',
                'crc32c': 'synthetic-checksum',
                'uri': f"gs://synthetic/record-wal/{uid}/{cid}/{entry['file_id']}.enc#17",
            }
            for entry in fence['files']
        ]

    monkeypatch.setattr(purge, 'purge_jobstore_owner', lambda *_: 0)
    yield client, namespace, uid, cid, conversation, files, begin, originals
    for doc in handoff.intake_collection(client, namespace).stream():
        doc.reference.delete()
    client.recursive_delete(user)
    # The disposable emulator owns this authority marker; production's write
    # fence correctly forbids deleting privacy generations.
    client.close()


def test_committed_reply_loss_replays_one_revision_and_one_outbox(world, monkeypatch):
    client, namespace, uid, cid, conversation, files, begin, originals = world
    fence = begin()
    commit_rpc = client._firestore_api.commit
    lost = []

    def lose_committed_reply(*args, **kwargs):
        result = commit_rpc(*args, **kwargs)
        request = kwargs.get('request') or args[0]
        if not lost and any(write.update.name.endswith('/' + fence['job_id']) for write in request['writes']):
            lost.append(True)
            raise ServiceUnavailable('synthetic committed response loss')
        return result

    monkeypatch.setattr(client._firestore_api, 'commit', lose_committed_reply)
    accepted = handoff.commit(client, namespace, fence, originals(fence))
    assert accepted['state'] == 'accepted' and lost
    assert conversation.get().to_dict()['record_upload_revision'] == 8
    assert (
        len([row for row in handoff.intake_collection(client, namespace).stream() if row.to_dict().get('outbox')]) == 2
    )
    count, oldest = handoff.pending_sample(client, namespace)
    assert count == 2 and oldest == accepted['accepted_at']
    # Restarted reader/producer with phone offline: no local bytes or old process state.
    monkeypatch.setenv('RECORD_WAL_HANDOFF_ENABLED', 'false')
    restarted = firestore.Client(project=client.project, credentials=AnonymousCredentials())
    try:
        assert handoff.read_status(restarted, namespace, uid, accepted['job_id'])['status'] == 'processing'
    finally:
        restarted.close()
    assert begin()['job_id'] == accepted['job_id']
    assert conversation.get().to_dict()['record_upload_revision'] == 8


def test_interrupted_object_only_attempt_is_superseded_without_acceptance(world):
    client, namespace, uid, cid, conversation, files, begin, originals = world
    interrupted = begin()
    # Synthetic objects exist externally; there is no committed receipt/work yet.
    restarted = begin()
    assert restarted['fence_token'] != interrupted['fence_token']
    with pytest.raises(handoff.HandoffConflict):
        handoff.commit(client, namespace, interrupted, originals(interrupted))
    assert not any(row.to_dict().get('obligation') for row in handoff.intake_collection(client, namespace).stream())
    handoff.commit(client, namespace, restarted, originals(restarted))
    assert conversation.get().to_dict()['record_upload_revision'] == 8


def test_concurrent_rebundles_commit_one_per_file_obligation(world):
    client, namespace, uid, cid, conversation, files, begin, originals = world
    first, second = begin(files[:1]), begin()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(handoff.commit, client, namespace, fence, originals(fence)) for fence in (first, second)]
        results = [future.result(timeout=30) for future in futures]
    assert all(row['state'] == 'accepted' for row in results)
    assert conversation.get().to_dict()['record_upload_revision'] == 9
    rows = [row.to_dict() for row in handoff.intake_collection(client, namespace).stream()]
    assert len([row for row in rows if row.get('kind') == handoff.FILE_KIND]) == 2
    assert len([row for row in rows if row.get('obligation') and row.get('outbox')]) == 2


def test_privacy_generation_change_cannot_commit_and_erasure_finds_all_receipts(world):
    client, namespace, uid, cid, conversation, files, begin, originals = world
    fence = begin()
    privacy = client.collection('batch_pipeline_privacy').document(privacy_owner_key(uid))
    privacy.set({'generation': 1, 'blocked': False, 'purging': False})
    with pytest.raises(BatchPrivacyBlocked):
        handoff.commit(client, namespace, fence, originals(fence))
    assert not any(row.to_dict().get('outbox') for row in handoff.intake_collection(client, namespace).stream())
    # A separate valid bundle proves deletion discovers every new table and URI.
    privacy.set({'generation': 0, 'blocked': False, 'purging': False})
    accepted = handoff.commit(client, namespace, fence, originals(fence))
    client.collection('users').document(uid).collection('deleted_conversations').document(cid).set({'deleted': True})
    deleted = []
    purge.purge_batch_owner(
        uid,
        conversation_id=cid,
        namespaces=(namespace,),
        firestore_client=client,
        delete_uri=lambda owner, uri: deleted.append((owner, uri)),
    )
    assert len(deleted) == 2 and all(owner == uid for owner, _ in deleted)
    assert not list(handoff.intake_collection(client, namespace).stream())
    assert handoff.read_status(client, namespace, uid, accepted['job_id']) is None
