"""Real transaction atomicity, contention and durable discovery; synthetic only."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import os
import json
import struct
import time
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, Mock

from google.api_core.exceptions import Aborted, ServiceUnavailable
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


@pytest.fixture
def duplicate_world(world, monkeypatch):
    from config.record_audio import record_identity
    from config.record_wal_duplicate import SOURCE_FIELD
    from database import record_wal_duplicate as duplicate

    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    client, namespace, uid, cid, conversation, files, _, _ = world
    store = FirestoreStore(namespace, firestore_client=client)
    conversation.update({'status': 'completed', 'finished_at': datetime.now(timezone.utc)})
    record, segment = record_identity(uid, cid)
    canonical = 'bp_' + record
    source = {
        'bucket': 'private',
        'revision': 7,
        'units': [segment],
        'slices': [{'unit': segment, 'path': 'raw-live/example', 'generation': 2, 'first': 0, 'count': 3200}],
    }
    client.collection(namespace + '_intakes').document(canonical).set(
        {
            'owner_id': uid,
            'conversation_id': cid,
            'content_id': record,
            'segment_ids': [segment],
            'total_files': 1,
            'lane': 'fresh',
            SOURCE_FIELD: source,
        }
    )
    job_ref = client.collection(namespace + '_jobs').document(segment)
    job_ref.set({'state': 'committed', 'owner_id': uid, 'conversation_id': cid, 'privacy_generation': 0})
    store.run(
        lambda tx: tx.put(
            'content',
            f'{uid}/{record}',
            {
                'job_id': canonical,
                'dispatch_protocol': 'batch_v1',
                'status': 'completed',
                'result': {'total_segments': 1, 'failed_segments': 0, 'errors': [], 'new_memories': [cid]},
            },
        )
    )

    def request(content):
        return duplicate.Request(uid, cid, 'omi', 'synthetic-device', content, None, 'header-digest')

    def attempt(req, **options):
        budget = ArtifactReadBudget(time.monotonic() + 10, 0, 0)
        return duplicate.reconcile(store, duplicate.PointReads(budget), req, **options)

    yield SimpleNamespace(
        store=store,
        files=files,
        request=request,
        attempt=attempt,
        canonical=canonical,
        conversation=conversation,
        user=client.collection('users').document(uid),
        cid=cid,
        intake=client.collection(namespace + '_intakes').document(canonical),
        job_ref=job_ref,
    )
    job_ref.delete()


def test_duplicate_cas_replay_while_disabled_and_rebundle(duplicate_world, monkeypatch):
    from config.record_wal_duplicate import mode

    case = duplicate_world
    first = case.request('first')
    candidate = case.attempt(first, files=case.files)
    assert candidate is not None
    saved = case.attempt(first, files=case.files, expected=candidate.scope, placements=['a', 'b'], commit=True)
    assert saved.reply['job_id'] == case.canonical
    monkeypatch.setenv('RECORD_WAL_DUPLICATE_PERCENT', '0')
    assert mode(first.uid, time.time()) == ('off', None)
    assert case.attempt(first).reply == saved.reply
    assert case.attempt(first, files=[{**case.files[0], 'sha256': 'f' * 64}, case.files[1]]) is None
    rebundle = case.request('second')
    existing = case.attempt(rebundle, files=case.files[:1])
    assert len(existing.known) == 1
    assert (
        case.attempt(rebundle, files=case.files[:1], expected=existing.scope, placements=['wrong'], commit=True) is None
    )
    assert case.attempt(rebundle) is None
    assert (
        case.attempt(rebundle, files=case.files[:1], expected=existing.scope, placements=['a'], commit=True).reply
        == saved.reply
    )
    original = case.attempt(first)
    later = case.attempt(rebundle)
    assert later.prior['expires_at'] > original.prior['expires_at']
    assert later.known[later.file_ids[0]]['expires_at'] == later.prior['expires_at']
    assert original.known[original.file_ids[1]]['expires_at'] == original.prior['expires_at']


def test_duplicate_terminal_keeps_its_alias_window_after_canonical_expiry(duplicate_world, monkeypatch):
    from config.record_audio import record_identity
    from database import record_wal_duplicate as duplicate
    from utils.batch_pipeline import intake
    from utils.sync.stage import collection_name

    case = duplicate_world
    first = case.request('terminal-witness')
    candidate = case.attempt(first, files=case.files)
    saved = case.attempt(first, files=case.files, expected=candidate.scope, placements=['a', 'b'], commit=True)
    assert saved.reply['job_id'] == case.canonical
    ledger = case.user.collection(collection_name('sync_content_ledger'))
    alias = ledger.document(first.content_id)
    witness = case.store.client.collection(case.store.namespace + '_intakes').document(
        'wal_duplicate_terminal_' + case.canonical
    )
    first_expiry = alias.get().to_dict()['expires_at']
    assert witness.get().to_dict()['expires_at'] == first_expiry
    case.intake.delete()
    case.job_ref.delete()
    ledger.document(record_identity(first.uid, first.cid)[0]).delete()
    monkeypatch.setenv('RECORD_WAL_DUPLICATE_PERCENT', '0')
    monkeypatch.setattr(intake, 'FirestoreStore', lambda *_: case.store)
    legacy = Mock(side_effect=AssertionError('legacy status ran'))
    monkeypatch.setattr(intake, 'durable_status', legacy)
    assert case.attempt(first).reply == saved.reply
    assert intake.get_durable_job_status(case.canonical, first.uid) == saved.reply
    assert legacy.call_count == 0
    assert witness.get().to_dict()['expires_at'] == first_expiry
    assert alias.get().to_dict()['expires_at'] == first_expiry
    assert case.attempt(case.request('late-rebundle'), files=case.files) is None

    # TTL removal is asynchronous. Past the absolute deadline, even retained
    # documents do not authorize replay.
    past = datetime(2000, 1, 1, tzinfo=timezone.utc)
    alias.update({'expires_at': past})
    assert case.attempt(first) is None
    witness.update({'expires_at': past})
    assert duplicate.terminal_status(case.store, first.uid, case.canonical) == (True, None)


@pytest.mark.parametrize('erase', ('conversation', 'account'))
def test_duplicate_terminal_receipt_is_purged_with_its_erased_owner(duplicate_world, erase):
    from database import record_wal_duplicate as duplicate

    case = duplicate_world
    request = case.request('purge-witness')
    candidate = case.attempt(request, files=case.files)
    assert case.attempt(request, files=case.files, expected=candidate.scope, placements=['a', 'b'], commit=True)
    assert duplicate.terminal_status(case.store, request.uid, case.canonical)[1]['status'] == 'completed'
    if erase == 'conversation':
        marker = case.user.collection('deleted_conversations').document(case.cid)
        marker.set({'reason': 'synthetic'})
    else:
        marker = case.store.client.collection('account_deletions').document(request.uid)
        marker.set({'wipe_status': 'pending_deletion'})
    with pytest.raises(BatchPrivacyBlocked):
        case.attempt(request)
    with pytest.raises(BatchPrivacyBlocked):
        duplicate.terminal_status(case.store, request.uid, case.canonical)
    purge.purge_batch_owner(
        request.uid,
        conversation_id=case.cid if erase == 'conversation' else None,
        namespaces=(case.store.namespace,),
        firestore_client=case.store.client,
        delete_uri=Mock(side_effect=AssertionError('metadata-only witness has no object URI')),
    )
    assert duplicate.terminal_status(case.store, request.uid, case.canonical) == (False, None)
    marker.delete()


@pytest.mark.parametrize('race', ('revision', 'tombstone', 'merge_removal'))
def test_duplicate_cas_revalidates_source_and_privacy_after_compare(duplicate_world, race):
    case = duplicate_world
    request = case.request('race')
    old = case.attempt(request, files=case.files)
    authority = {'expected': old.scope, 'files': case.files, 'placements': ['a', 'b'], 'commit': True}
    if race == 'tombstone':
        case.user.collection('deleted_conversations').document(case.cid).set({'reason': 'synthetic'})
        with pytest.raises(BatchPrivacyBlocked):
            case.attempt(request, **authority)
    else:
        if race == 'revision':
            case.conversation.update({'record_upload_revision': 8})
        else:
            from database.record_audio import fence_record_audio_removal

            fence_record_audio_removal(request.uid, request.cid, firestore_client=case.store.client)
        assert case.attempt(request, **authority) is None
        assert case.attempt(request) is None


def test_duplicate_shadow_and_mixed_version_leave_no_alias(duplicate_world, monkeypatch):
    from database import record_wal_duplicate as duplicate

    lifecycle = Mock()
    monkeypatch.setattr(duplicate, 'lifecycle_rpcs', lifecycle)
    case = duplicate_world
    request = case.request('shadow')
    old = case.attempt(request, files=case.files)
    snapshot = case.attempt(request, files=case.files, expected=old.scope, placements=['a', 'b'])
    assert snapshot.reply['job_id'] == case.canonical
    assert [call.args[1:] for call in lifecycle.labels.call_args_list] == [
        ('begin', 'attempt'),
        ('begin', 'success'),
        ('rollback', 'attempt'),
        ('rollback', 'success'),
    ] * 2
    assert case.attempt(request) is None
    case.intake.update({'wal_duplicate_source_v1': firestore.DELETE_FIELD})
    assert case.attempt(request, files=case.files) is None


def test_duplicate_settlement_holds_an_unknown_competing_alias(duplicate_world):
    from config.record_wal_duplicate import RECEIPT_FIELD

    case = duplicate_world
    request = case.request('unknown-alias')
    before = case.attempt(request, files=case.files)
    case.store.run(lambda tx: tx.put('content', f'{request.uid}/{request.content_id}', {RECEIPT_FIELD: {}}))
    assert case.attempt(request, files=case.files, expected=before.scope, placements=['a', 'b'], commit=True) is None


def test_duplicate_competing_concurrent_retries_publish_one_alias(duplicate_world):
    from google.api_core.exceptions import Aborted

    case = duplicate_world
    request = case.request('concurrent')
    old = case.attempt(request, files=case.files)

    def commit():
        try:
            return case.attempt(request, files=case.files, expected=old.scope, placements=['a', 'b'], commit=True)
        except Aborted:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: commit(), range(2)))
    successful_creates = sum(1 for result in results if result and result.prior is None)
    assert successful_creates <= 1
    # A bounded snapshot can refuse both contenders under emulator locks.
    # The next request still converges on one durable alias.
    if not successful_creates:
        assert commit().prior is None
    assert case.attempt(request).reply['job_id'] == case.canonical
    assert commit().prior is not None


@pytest.mark.asyncio
@pytest.mark.parametrize('rotate_privacy', (False, True))
async def test_duplicate_replay_route_never_calls_legacy_status_or_archive(
    duplicate_world, monkeypatch, tmp_path, rotate_privacy
):
    from database import record_wal_handoff as handoff

    case = duplicate_world
    first = case.request('route')
    request = type(first)(
        first.uid, first.cid, first.source, first.device, first.content_id, None, handoff.identity({})
    )
    old = case.attempt(request, files=case.files)
    assert case.attempt(request, files=case.files, expected=old.scope, placements=['a', 'b'], commit=True)
    monkeypatch.setattr(live_upload, 'FirestoreStore', lambda *_: case.store)
    legacy = Mock(side_effect=AssertionError('legacy status ran'))
    archive = Mock(side_effect=AssertionError('archive ran'))
    monkeypatch.setattr(live_upload, 'durable_status', legacy)
    path = tmp_path / 'already-hashed'
    monkeypatch.setenv('RECORD_WAL_DUPLICATE_PERCENT', '0')
    if rotate_privacy:
        case.store.client.collection('batch_pipeline_privacy').document(privacy_owner_key(request.uid)).set(
            {'generation': 1, 'blocked': False, 'purging': False}
        )
    response = await live_upload.registered_record_response(
        uid=request.uid,
        conversation_id=request.cid,
        content_id=request.content_id,
        paths=[str(path)],
        source=request.source,
        client_device_id=request.device,
        loaded_conversation=case.conversation.get().to_dict(),
        before_coverage=archive,
    )
    if rotate_privacy:
        assert response.status_code == 503
    else:
        assert response.status_code == 202
        assert json.loads(response.body)['job_id'] == case.canonical
        assert json.loads(response.body)['status'] == 'completed'
    legacy.assert_not_called()
    archive.assert_not_called()


@pytest.mark.asyncio
async def test_legacy_alias_transaction_retries_after_settlement_wins(duplicate_world, monkeypatch):
    from config.record_wal_duplicate import RECEIPT_FIELD
    from database.batch_pipeline_store import FirestoreTransaction
    from utils.batch_pipeline import record_lease_append
    from utils.sync.stage import collection_name

    case = duplicate_world
    request = case.request('legacy-loses')
    alias = case.user.collection(collection_name('sync_content_ledger')).document(request.content_id)
    client = case.store.client
    api = client._firestore_api
    commit_rpc = api.commit
    winner = {'dispatch_protocol': 'batch_v1', 'job_id': case.canonical, RECEIPT_FIELD: {'scope': 'synthetic'}}
    aborted, observed = [], []
    original_get = FirestoreTransaction.get

    def get(view, table, key):
        row = original_get(view, table, key)
        if (table, key) == ('content', f'{request.uid}/{request.content_id}'):
            observed.append(row)
        return row

    def interleave(*args, **kwargs):
        rpc = kwargs.get('request') or args[0]
        if not aborted and any(write.update.name.endswith('/' + alias.path) for write in rpc['writes']):
            assert observed == [{}, {}]
            # The emulator uses read locks. Release the losing transaction
            # before committing the competing write and reporting contention.
            api.rollback(
                request={'database': rpc['database'], 'transaction': rpc['transaction']},
                metadata=kwargs.get('metadata', ()),
                timeout=2,
                retry=None,
            )
            aborted.append(True)
            alias.set(winner)
            raise Aborted('synthetic competing settlement')
        return commit_rpc(*args, **kwargs)

    monkeypatch.setattr(FirestoreTransaction, 'get', get)
    monkeypatch.setattr(api, 'commit', interleave)
    monkeypatch.setattr(live_upload, 'FirestoreStore', lambda *_: case.store)
    monkeypatch.setenv('RECORD_WAL_HANDOFF_ENABLED', 'false')
    monkeypatch.setattr(live_upload, 'coverage_wait_memo_enabled', lambda: False)
    monkeypatch.setattr(record_lease_append, 'retain_upload', AsyncMock())
    monkeypatch.setattr(live_upload, 'artifacts_for', lambda _: object())
    monkeypatch.setattr(live_upload, '_covered', lambda *_: True)
    legacy = Mock(side_effect=AssertionError('legacy status must not redrive a settled alias'))
    monkeypatch.setattr(live_upload, 'durable_status', legacy)
    response = await live_upload.registered_record_response(
        uid=request.uid,
        conversation_id=request.cid,
        content_id=request.content_id,
        paths=['synthetic'],
        source=request.source,
        client_device_id=request.device,
        loaded_conversation=case.conversation.get().to_dict(),
    )
    assert aborted == [True]
    assert observed == [{}, {}, winner]
    assert response.status_code == 503
    assert alias.get().to_dict() == winner
    legacy.assert_not_called()


def test_merge_removal_cannot_use_missing_source_as_durable_fence(duplicate_world):
    from google.api_core.exceptions import NotFound
    from database.record_audio import fence_record_audio_removal

    case = duplicate_world
    request = case.request('missing-source')
    case.conversation.delete()
    with pytest.raises(NotFound):
        fence_record_audio_removal(request.uid, request.cid, firestore_client=case.store.client)
    case.user.collection('deleted_conversations').document(case.cid).set({'reason': 'synthetic'})
    fence_record_audio_removal(request.uid, request.cid, firestore_client=case.store.client)
    assert not case.conversation.get().exists


def _prepare_retained_merge(case, other_id, monkeypatch):
    from database import conversation_merge_jobs as jobs

    monkeypatch.setattr(jobs, 'stop_quiet_checks_for_job', lambda *args, **kwargs: None)
    request = case.request('retained')
    other = case.user.collection('conversations').document(other_id)
    other.set({'status': 'completed', 'private_cloud_sync_enabled': True})
    admitted = jobs.admit(request.uid, [request.cid, other_id], False, firestore_client=case.store.client)
    assert admitted
    return jobs.claim(admitted['job_id'], firestore_client=case.store.client)


def _publish_retained_merge(case, job):
    from database import review_overlay_merge

    target_id = job['merge_target_id']
    case.user.collection('conversations').document(target_id).set(
        {'status': 'completed', 'private_cloud_sync_enabled': True}
    )
    assert review_overlay_merge.transfer(
        job['uid'],
        job['conversation_ids'],
        target_id,
        firestore_client=case.store.client,
        merge_job_id=job['job_id'],
        merge_lease_epoch=job['lease_epoch'],
    )
    return target_id


@pytest.mark.asyncio
@pytest.mark.parametrize('erase_end', ['original', 'successor'])
async def test_duplicate_replays_original_handle_through_preparation_and_two_merges(
    duplicate_world, monkeypatch, erase_end
):
    from config.record_wal_duplicate import MERGE_TARGET_FIELD, RETAINED_DONORS_FIELD
    from database import conversation_merge_jobs as jobs, conversation_tombstones
    from database import record_wal_duplicate as duplicate
    from database.record_audio import fence_record_audio_removal

    case = duplicate_world
    request = case.request('retained')
    old = case.attempt(request, files=case.files)
    assert case.attempt(request, files=case.files, expected=old.scope, placements=['a', 'b'], commit=True)
    first = _prepare_retained_merge(case, 'first-other', monkeypatch)

    # An interruption after the donor fence leaves the original readable and
    # refuses new settlements. Cleanup cannot run before publication.
    assert case.attempt(request).reply['job_id'] == case.canonical
    assert case.attempt(case.request('new-bundle'), files=case.files) is None
    from database.record_wal_merge import RetainedMergeDeferred

    with pytest.raises(RetainedMergeDeferred):
        fence_record_audio_removal(request.uid, request.cid, firestore_client=case.store.client)

    successor = _publish_retained_merge(case, first)
    assert fence_record_audio_removal(request.uid, request.cid, firestore_client=case.store.client)
    assert case.attempt(request).reply['job_id'] == case.canonical

    second_other = case.user.collection('conversations').document('second-other')
    second_other.set({'status': 'completed', 'private_cloud_sync_enabled': True})
    admitted = jobs.admit(request.uid, [successor, 'second-other'], False, firestore_client=case.store.client)
    assert admitted
    second = jobs.claim(admitted['job_id'], firestore_client=case.store.client)
    final_target = _publish_retained_merge(case, second)
    assert case.conversation.get().to_dict()[MERGE_TARGET_FIELD] == final_target
    assert case.user.collection('conversations').document(final_target).get().to_dict()[RETAINED_DONORS_FIELD] == [
        case.cid
    ]
    assert case.user.collection('conversations').document(successor).get().to_dict()['sync_merged_from'] == []
    monkeypatch.setenv('RECORD_WAL_DUPLICATE_PERCENT', '0')
    assert case.attempt(request).reply['job_id'] == case.canonical
    monkeypatch.setattr(live_upload, 'FirestoreStore', lambda *_: case.store)
    legacy = Mock(side_effect=AssertionError('legacy poll would redrive'))
    monkeypatch.setattr(live_upload, 'durable_status', legacy)
    response = await live_upload.registered_record_response(
        uid=request.uid,
        conversation_id=request.cid,
        content_id=request.content_id,
        paths=['synthetic'],
        source=request.source,
        client_device_id=request.device,
        loaded_conversation=case.conversation.get().to_dict(),
    )
    assert isinstance(response, live_upload.JSONResponse)
    assert response.status_code == 202
    assert json.loads(bytes(response.body))['job_id'] == case.canonical
    legacy.assert_not_called()
    assert duplicate.terminal_status(case.store, request.uid, case.canonical)[1]['status'] == 'completed'

    erased = case.cid if erase_end == 'original' else final_target
    conversation_tombstones.accept_deletion(
        request.uid, erased, firestore_client=case.store.client, legal_hold_deferred=True
    )
    with pytest.raises(BatchPrivacyBlocked):
        case.attempt(request)
    with pytest.raises(BatchPrivacyBlocked):
        duplicate.terminal_status(case.store, request.uid, case.canonical)
    if erase_end == 'successor':
        from database.conversation_batch_purge_jobs import erasure_job_ref

        owed = erasure_job_ref(case.store.client, request.uid, final_target).get().to_dict()
        assert owed['audio_source_ids'] == [case.cid]


def test_erase_after_merge_preparation_blocks_publication(duplicate_world, monkeypatch):
    from config.record_wal_duplicate import MERGE_TARGET_FIELD
    from database.review_store import ReviewConflict
    from database import conversation_tombstones

    case = duplicate_world
    request = case.request('retained')
    old = case.attempt(request, files=case.files)
    assert case.attempt(request, files=case.files, expected=old.scope, placements=['a', 'b'], commit=True)
    prepared = _prepare_retained_merge(case, 'other', monkeypatch)
    conversation_tombstones.accept_deletion(
        request.uid, request.cid, firestore_client=case.store.client, legal_hold_deferred=True
    )
    with pytest.raises(ReviewConflict, match='Merge source unavailable'):
        _publish_retained_merge(case, prepared)
    assert MERGE_TARGET_FIELD not in case.conversation.get().to_dict()


def test_retained_merge_admit_defers_above_limit_without_changing_donors(duplicate_world, monkeypatch):
    from config.record_wal_duplicate import MERGE_PLAN_FIELD, SETTLED_FIELD
    from database import conversation_merge_jobs as jobs

    case = duplicate_world
    request = case.request('limit')
    monkeypatch.setattr(jobs, 'stop_quiet_checks_for_job', lambda *args, **kwargs: None)
    refs = [case.user.collection('conversations').document(f'source-{number:02}') for number in range(17)]
    for ref in refs:
        ref.set({'status': 'completed', SETTLED_FIELD: True})
    assert jobs.admit(request.uid, [ref.id for ref in refs], False, firestore_client=case.store.client) is None
    assert all(ref.get().to_dict()['status'] == 'completed' for ref in refs)
    admitted = jobs.admit(request.uid, [ref.id for ref in refs[:16]], False, firestore_client=case.store.client)
    assert admitted and len(admitted[MERGE_PLAN_FIELD]) == 16
    claimed = jobs.claim(admitted['job_id'], firestore_client=case.store.client)
    target = _publish_retained_merge(case, claimed)
    row = case.user.collection('conversations').document(target).get().to_dict()
    assert row['sync_merged_from'] == [ref.id for ref in refs[:16]]


def test_retained_merge_with_custom_stt_defers_before_claiming_sources(duplicate_world):
    from config.record_wal_duplicate import SETTLED_FIELD
    from database import conversation_merge_jobs as jobs

    case = duplicate_world
    request = case.request('custom-stt')
    case.conversation.update({SETTLED_FIELD: True})
    custom = case.user.collection('conversations').document('custom')
    custom.set({'status': 'completed', 'uses_custom_stt': True})
    before = [ref.get().to_dict() for ref in (case.conversation, custom)]
    assert jobs.admit(request.uid, [case.cid, custom.id], False, firestore_client=case.store.client) is None
    assert [ref.get().to_dict() for ref in (case.conversation, custom)] == before


def test_merge_preparation_wins_against_uncommitted_settlement(duplicate_world, monkeypatch):
    case = duplicate_world
    request = case.request('retained')
    old = case.attempt(request, files=case.files)
    _prepare_retained_merge(case, 'other', monkeypatch)
    assert case.attempt(request, files=case.files, expected=old.scope, placements=['a', 'b'], commit=True) is None
    assert case.attempt(request) is None
