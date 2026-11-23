"""Real transaction atomicity, contention and durable discovery; synthetic only."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import os
import json
import struct
import time
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import Mock

from google.api_core.exceptions import ServiceUnavailable
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database import record_wal_handoff as handoff
from database import record_wal_sample as sample_state
from database import batch_pipeline_purge as purge
from database import batch_pipeline_conversation_purge as conversation_purge
from database import record_wal_capacity as capacity
from contextlib import contextmanager
from database import batch_pipeline_privacy as privacy
from database.batch_pipeline_privacy import BatchPrivacyBlocked, privacy_owner_key
from database.batch_pipeline_store import FirestoreStore
from utils.batch_pipeline import live_upload, intake, record_wal_erasure, record_wal_sample
from utils.batch_pipeline.artifact_reads import ArtifactReadBudget
from utils.other import storage, local_storage
from utils.other.local_storage import LocalStorageClient

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
    for stage in (namespace, capacity.NAMESPACE):
        for doc in handoff.intake_collection(client, stage).stream():
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
    assert count == 2 and 0 < oldest <= accepted['accepted_at']
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


@pytest.mark.parametrize('erasure', ['account', 'conversation', 'resumable'])
async def test_registered_handoff_status_restart_and_actual_original_erasure(world, monkeypatch, tmp_path, erasure):
    client, namespace, uid, cid, conversation, files, begin, originals = world
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('ENCRYPTION_SECRET', 'synthetic-wal-combined-emulator-secret')
    monkeypatch.setenv('BUCKET_PRIVATE_CLOUD_SYNC', 'synthetic-wal-private')
    monkeypatch.delenv('BUCKET_BATCH_PIPELINE', raising=False)
    monkeypatch.setenv('RECORD_WAL_HANDOFF_ENABLED', 'true')
    monkeypatch.setattr(storage, 'private_cloud_sync_bucket', 'synthetic-wal-private')
    objects = LocalStorageClient(tmp_path / 'durable-storage')
    monkeypatch.setattr(storage, '_get_storage_client', lambda: objects)
    monkeypatch.setattr(local_storage, 'create_storage_client', lambda: objects)
    monkeypatch.setattr(record_wal_erasure, 'create_storage_client', lambda: objects)
    monkeypatch.setattr(
        storage.conversation_tombstones,
        'is_deleted',
        lambda owner, record: (
            client.collection('users').document(owner).collection('deleted_conversations').document(record).get().exists
        ),
    )
    store = FirestoreStore(namespace, firestore_client=client)
    monkeypatch.setattr(live_upload, 'FirestoreStore', lambda *_: store)
    paths = []
    for ordinal in range(2):
        path = tmp_path / files[ordinal]['name']
        packet = struct.pack('<h', ordinal + 1) * 160
        path.write_bytes(struct.pack('<I', len(packet)) + packet)
        paths.append(path)
    response = await live_upload.registered_record_response(
        uid=uid,
        conversation_id=cid,
        content_id='synthetic-combined',
        paths=paths,
        source='omi',
        client_device_id='synthetic-device',
        loaded_conversation=conversation.get().to_dict(),
        policy=SimpleNamespace(live_admission_enabled=False, live_record_enabled=True),
    )
    assert response.status_code == 202
    job_id = json.loads(response.body)['job_id']
    assert intake.durable_status(store, uid, job_id)['status'] == 'processing'
    assert handoff.has_receipts(uid, cid, firestore_client=client)
    restarted = firestore.Client(project=client.project, credentials=AnonymousCredentials())
    try:
        assert handoff.read_status(restarted, namespace, uid, job_id)['status'] == 'processing'
    finally:
        restarted.close()
    assert handoff.pending_sample(client, namespace)[0] == 2
    assert len(list(objects.bucket('synthetic-wal-private').list_blobs(prefix=f'record-wal/{uid}/'))) == 2
    # Simulate object-only interrupted custody: account/protection erasure must
    # also find media which no committed file receipt can reference yet.
    orphan = objects.bucket('synthetic-wal-private').blob(f'record-wal/{uid}/{cid}/orphan.bin')
    orphan.upload_from_string(b'synthetic crash orphan', if_generation_match=0)
    if erasure == 'account':
        purge.purge_batch_owner(uid, namespaces=(namespace,), firestore_client=client)
    else:
        client.collection('users').document(uid).collection('deleted_conversations').document(cid).set(
            {'deleted': True}
        )
        if erasure == 'conversation':
            sweep = purge.purge_record_wal_owner
            monkeypatch.setattr(
                purge,
                'purge_record_wal_owner',
                Mock(side_effect=OSError('synthetic prefix failure')),
            )
            with pytest.raises(OSError, match='synthetic prefix failure'):
                purge.purge_batch_owner(uid, conversation_id=cid, namespaces=(namespace,), firestore_client=client)
            assert capacity.sample(client)['files'] == 2
            assert any(row.to_dict().get('receipt') for row in handoff.intake_collection(client, namespace).stream())
            assert len(list(objects.bucket('synthetic-wal-private').list_blobs(prefix=f'record-wal/{uid}/'))) == 3
            monkeypatch.setattr(purge, 'purge_record_wal_owner', sweep)
            release = capacity.erase_file
            monkeypatch.setattr(
                capacity,
                'erase_file',
                Mock(side_effect=OSError('synthetic post-sweep crash')),
            )
            with pytest.raises(OSError, match='synthetic post-sweep crash'):
                purge.purge_batch_owner(uid, conversation_id=cid, namespaces=(namespace,), firestore_client=client)
            assert capacity.sample(client)['files'] == 2  # Missing reply cannot undercharge.
            assert not list(objects.bucket('synthetic-wal-private').list_blobs(prefix=f'record-wal/{uid}/'))
            monkeypatch.setattr(capacity, 'erase_file', release)
            purge.purge_batch_owner(uid, conversation_id=cid, namespaces=(namespace,), firestore_client=client)
        else:
            monkeypatch.setattr(conversation_purge, 'NAMESPACES', (namespace,))
            monkeypatch.setattr(conversation_purge, 'purge_jobstore_owner', lambda *_: None)
            conversation_purge.purge_conversation(uid, cid, SyntheticProgress(), firestore_client=client)
    assert capacity.sample(client) == {'bytes': 0, 'files': 0}
    assert not list(objects.bucket('synthetic-wal-private').list_blobs(prefix=f'record-wal/{uid}/'))
    assert not list(handoff.intake_collection(client, namespace).stream())
    assert all(path.exists() for path in paths)  # 202 never released the phone copies.


class SyntheticProgress:
    """No production gate claim; real erasing transactions still execute on the emulator."""

    position = {}

    def checkpoint(self, position, **kwargs):
        self.position = position

    def segments(self, namespace):
        return set()

    def pending_segments(self, namespace, limit):
        return []

    def expired(self):
        return False

    def settle_stuck(self, resolve):
        pass

    @contextmanager
    def unit(self):
        yield SimpleNamespace(fence=lambda tx: None, remote=lambda action, target: action())


def test_global_capacity_serializes_concurrent_admission_across_namespaces(world, monkeypatch):
    client, namespace, uid, cid, conversation, files, begin, originals = world
    monkeypatch.setenv('RECORD_WAL_PENDING_GLOBAL_FILES', '1')
    other = client.collection('users').document('synthetic-second-owner')
    other.set({'private_cloud_sync_enabled': True})
    other.collection('conversations').document(cid).set(conversation.get().to_dict())

    def admit(owner, stage, entries):
        try:
            handoff.begin(client, stage, owner, cid, entries, 'omi', 'synthetic-device')
            return 'reserved'
        except capacity.CapacityExceeded:
            return 'capacity'

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(admit, uid, namespace, files[:1]),
                pool.submit(admit, 'synthetic-second-owner', capacity.NAMESPACE, files[1:]),
            ]
            assert sorted(future.result(timeout=30) for future in futures) == ['capacity', 'reserved']
        assert capacity.sample(client) == {'bytes': 356, 'files': 1}
    finally:
        client.recursive_delete(other)


def test_completed_legacy_purge_checkpoint_still_sweeps_crash_orphans(world, monkeypatch, tmp_path):
    client, namespace, uid, cid, conversation, files, begin, originals = world
    objects = LocalStorageClient(tmp_path)
    monkeypatch.setenv('BUCKET_PRIVATE_CLOUD_SYNC', 'synthetic-wal-private')
    monkeypatch.setattr(record_wal_erasure, 'create_storage_client', lambda: objects)
    monkeypatch.setattr(local_storage, 'create_storage_client', lambda: objects)
    monkeypatch.setattr(conversation_purge, 'NAMESPACES', (namespace,))
    client.collection('users').document(uid).collection('deleted_conversations').document(cid).set({'deleted': True})
    bucket = objects.bucket('synthetic-wal-private')
    bucket.blob(f'record-wal/{uid}/{cid}/orphan.bin').upload_from_string(b'synthetic crash orphan')
    bucket.blob(f'record-wal/{uid}/other/keep.bin').upload_from_string(b'synthetic other conversation')
    progress = SyntheticProgress()
    progress.position = {'ns': 1, 'phase': 'discover'}
    conversation_purge.purge_conversation(uid, cid, progress, firestore_client=client)
    assert [blob.name for blob in bucket.list_blobs(prefix=f'record-wal/{uid}/')] == [
        f'record-wal/{uid}/other/keep.bin'
    ]


def test_sample_slot_only_has_one_winner_across_runtime_namespaces(world, monkeypatch):
    client, _, uid, cid, _, _, _, _ = world
    old_revision = FirestoreStore('batch_pipeline_test_sampler_a', firestore_client=client)
    new_revision = FirestoreStore('batch_pipeline_test_sampler_b', firestore_client=client)
    slot = 600_000

    def claim(store):
        return sample_state.claim_slot(store, slot, ArtifactReadBudget(time.monotonic() + 5, 0, 0))

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(claim, [old_revision, new_revision])) == [False, True]

    # An authorization memo can return no owner rows. Both sampler fences need
    # a fresh complete snapshot even when the production memo lever enforces.
    monkeypatch.setattr(privacy, 'lever_enabled', lambda name, *_: name in {'bpp_owner_memo', 'bpp_owner_memo_enforce'})
    memo = Mock(side_effect=AssertionError('sampler must read live rows'))
    monkeypatch.setattr(privacy, '_assert_batch_write_allowed_memo', memo)
    budget = ArtifactReadBudget(time.monotonic() + 5, 0, 0)
    reads = record_wal_sample.SampleReads(budget)
    generation, snapshot = sample_state.authority(old_revision, uid, cid, 'omi', 'synthetic-device', budget, reads)
    assert snapshot['record_upload_revision'] == 7
    _, same = sample_state.authority(
        old_revision, uid, cid, 'omi', 'synthetic-device', budget, reads, expected_generation=generation
    )
    assert same == snapshot
    assert reads.issued == 10
    memo.assert_not_called()
