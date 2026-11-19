"""Synthetic key/purge races on loopback Firestore with real transactions, never cloud."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from threading import Barrier, Event
import uuid

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from utils.other import lake_wipe, object_lake as lake, space_keys
from utils.other.local_storage import LocalStorageClient, LocalBlob

pytestmark = pytest.mark.integration


@pytest.fixture
def state(tmp_path, monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('loopback Firestore emulator required; no cloud fallback')
    client = firestore.Client(project='demo-pgf-c4', credentials=AnonymousCredentials())
    uid = f'synthetic-c4-{uuid.uuid4().hex}'
    storage_client = LocalStorageClient(tmp_path)
    bucket = storage_client.bucket('lake-c4-contention')
    monkeypatch.setattr(lake, 'create_storage_client', lambda: storage_client)
    for key, value in {
        'BUCKET_OBJECT_LAKE': bucket.name,
        'OBJECT_LAKE_RELEASE': 'v1',
        'OBJECT_LAKE_WRITE_ENABLED': 'true',
        'OBJECT_LAKE_WRITE_PERCENT': '100',
        'OMI_ENV_STAGE': 'offline',
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv('OBJECT_LAKE_KMS_KEY', raising=False)
    monkeypatch.setattr(
        space_keys, 'space_key_firestore_client', lambda supplied=None: supplied if supplied is not None else client
    )
    monkeypatch.setattr(lake, '_lake_bucket', lambda: bucket)
    monkeypatch.setattr(
        lake_wipe.users_db,
        'get_user_deletion_wipe_status',
        lambda owner: (client.collection('account_deletions').document(owner).get().to_dict() or {}).get('wipe_status'),
    )
    space_keys.clear_space_key_cache()
    try:
        yield client, uid, bucket
    finally:
        client.collection('account_deletions').document(uid).set({'wipe_status': 'running'})
        lake.delete_space_upload_candidates(uid)
        for blob in bucket.list_blobs():
            blob.delete()
        client.collection('space_keys').document(uid).delete()
        client.collection('account_deletions').document(uid).delete()
        client.collection('users').document(uid).collection('deleted_conversations').document('c').delete()
        space_keys.clear_space_key_cache()
        client.close()


def assert_destroyed(client, uid):
    data = client.collection('space_keys').document(uid).get().to_dict()
    assert set(data) == {'space_id', 'state', 'destroyed_at'}
    assert data['space_id'] == uid and data['state'] == 'destroyed'
    with pytest.raises(space_keys.SpaceKeyDestroyed):
        space_keys.get_or_create_space_key(uid)


@pytest.mark.parametrize('operation', [space_keys.get_or_create_space_key, space_keys.rotate_space_key])
def test_concurrent_destroy_vs_create_or_rotate_has_no_resurrection(state, operation):
    client, uid, _ = state
    if operation is space_keys.rotate_space_key:
        space_keys.get_or_create_space_key(uid)
    barrier = Barrier(2)

    def writer():
        barrier.wait(timeout=10)
        try:
            return operation(uid)
        except space_keys.SpaceKeyDestroyed:
            return 'fenced'

    def destroy():
        barrier.wait(timeout=10)
        return space_keys.destroy_space_keys(uid)

    with ThreadPoolExecutor(max_workers=2) as pool:
        write_future = pool.submit(writer)
        destroy_future = pool.submit(destroy)
        destroy_future.result(timeout=60)
        write_future.result(timeout=60)
    assert_destroyed(client, uid)


def test_cached_unwrap_observes_other_thread_destroy_commit(state):
    client, uid, _ = state
    space_keys.get_or_create_space_key(uid)
    assert len(space_keys.unwrap_space_dek(uid, 1)) == 32
    committed = Event()

    def destroy():
        space_keys.destroy_space_keys(uid)
        committed.set()

    def unwrap_after_commit():
        assert committed.wait(timeout=30)
        with pytest.raises(space_keys.SpaceKeyDestroyed):
            space_keys.unwrap_space_dek(uid, 1)

    with ThreadPoolExecutor(max_workers=2) as pool:
        reader = pool.submit(unwrap_after_commit)
        pool.submit(destroy).result(timeout=60)
        reader.result(timeout=60)
    assert_destroyed(client, uid)


def test_inflight_put_cannot_finalize_after_account_wipe(state):
    client, uid, bucket = state
    uploading, release = Event(), Event()

    def paused_upload(method, uri, data, headers):
        if method == 'PUT' and not str(headers.get('Content-Range', '')).startswith('bytes */'):
            uploading.set()
            assert release.wait(timeout=30)

    bucket.client._http.before_request = paused_upload

    def put():
        with pytest.raises(lake.LakeFetchError):
            lake.put_space_object(uid, 'transcript', 'c', b'[]')

    with ThreadPoolExecutor(max_workers=1) as pool:
        writer = pool.submit(put)
        try:
            assert uploading.wait(timeout=30)
            client.collection('account_deletions').document(uid).set({'wipe_status': 'running'})
            assert lake_wipe.purge_owner_lake_content(uid)['status'] == 'purged'
            assert lake_wipe.destroy_owner_lake_keys(uid)['status'] == 'destroyed'
        finally:
            release.set()
        writer.result(timeout=60)
    assert not list(bucket.list_blobs(prefix=f'v1/spaces/{uid}/'))
    assert lake.delete_space_upload_candidates(uid) == 0


def test_conversation_upload_after_purge_final_listing_self_deletes(state, monkeypatch):
    client, uid, bucket = state
    uploading, release = Event(), Event()

    def paused_upload(method, uri, data, headers):
        if method == 'PUT' and not str(headers.get('Content-Range', '')).startswith('bytes */'):
            uploading.set()
            assert release.wait(timeout=30)

    bucket.client._http.before_request = paused_upload

    def put():
        with pytest.raises(lake.LakeFetchError):
            lake.put_space_object(uid, 'transcript', 'c', b'late transcript')

    with ThreadPoolExecutor(max_workers=1) as pool:
        writer = pool.submit(put)
        try:
            assert uploading.wait(timeout=30)
            assert lake_wipe.purge_conversation_lake_objects(uid, 'c') == 0
            assert (
                client.collection('users').document(uid).collection('deleted_conversations').document('c').get().exists
            )
            assert not list(bucket.list_blobs(prefix=f'v1/spaces/{uid}/'))
        finally:
            release.set()
        writer.result(timeout=60)
    assert not list(bucket.list_blobs(prefix=f'v1/spaces/{uid}/'))
    assert lake.delete_space_upload_candidates(uid) == 0


def test_candidate_range_erases_only_owner_including_abandoned_intents(state):
    client, uid, bucket = state
    sibling = uid + '-sibling'
    attempt = record_candidate('previous-bucket', f'v1/spaces/{uid}/transcript/orphan/digest')
    lake._settle_upload_candidate('previous-bucket', f'v1/spaces/{uid}/transcript/orphan/digest', attempt)
    record_candidate(bucket.name, f'v1/spaces/{sibling}/transcript/keep/digest')
    client.collection('account_deletions').document(uid).set({'wipe_status': 'running'})
    client.collection('account_deletions').document(sibling).set({'wipe_status': 'running'})
    try:
        assert lake_wipe.purge_owner_lake_content(uid)['candidates_deleted'] == 0
        assert lake_wipe.destroy_owner_lake_keys(uid)['status'] == 'destroyed'
        assert lake.delete_space_upload_candidates(uid) == 0
        assert lake.delete_space_upload_candidates(sibling) == 1
    finally:
        lake.delete_space_upload_candidates(sibling)
        client.collection('account_deletions').document(sibling).delete()


def test_late_upload_worker_loss_keeps_discovery_until_final_purge(state, monkeypatch):
    client, uid, bucket = state
    upload = LocalBlob.upload_from_string

    class WorkerLost(BaseException):
        pass

    def crash_after_late_upload(blob, *args, **kwargs):
        client.collection('account_deletions').document(uid).set({'wipe_status': 'running'})
        assert lake_wipe.purge_owner_lake_content(uid)['status'] == 'purged'
        assert not list(bucket.list_blobs())
        upload(blob, *args, **kwargs)
        raise WorkerLost()

    monkeypatch.setattr(LocalBlob, 'upload_from_string', crash_after_late_upload)
    with pytest.raises(WorkerLost):
        lake.put_space_object(uid, 'transcript', 'late', b'worker lost after upload')
    assert len(list(bucket.list_blobs())) == 1
    key = next(iter(bucket.list_blobs())).name
    candidate_id = hashlib.sha256(f'{bucket.name}/{key}'.encode()).hexdigest()
    row = client.collection('lake_upload_candidates').document(candidate_id).get().to_dict()
    assert row['settled'] is False and len(row['in_flight']) == 1
    assert lake_wipe.destroy_owner_lake_keys(uid)['status'] == 'destroyed'
    assert not list(bucket.list_blobs())
    assert lake.delete_space_upload_candidates(uid) == 0
    assert_destroyed(client, uid)


def test_delayed_candidate_cannot_reappear_after_wipe_scan(state, monkeypatch):
    client, uid, bucket = state
    paused, release = Event(), Event()
    record = lake._record_upload_candidate

    def delayed_record(*args):
        paused.set()
        assert release.wait(timeout=30)
        return record(*args)

    monkeypatch.setattr(lake, '_record_upload_candidate', delayed_record)

    def put():
        with pytest.raises(lake.LakeWriteFenced):
            lake.put_space_object(uid, 'transcript', 'late', b'[]')

    with ThreadPoolExecutor(max_workers=1) as pool:
        writer = pool.submit(put)
        try:
            assert paused.wait(timeout=30)
            client.collection('account_deletions').document(uid).set({'wipe_status': 'running'})
            assert lake_wipe.purge_owner_lake_content(uid)['status'] == 'purged'
        finally:
            release.set()
        writer.result(timeout=60)
    assert not list(bucket.list_blobs())
    assert lake.delete_space_upload_candidates(uid) == 0


def test_concurrent_upload_candidates_are_idempotent_under_real_transactions(state):
    client, uid, _ = state
    space_keys.get_or_create_space_key(uid)
    barrier = Barrier(2)

    def put():
        barrier.wait(timeout=10)
        return lake.put_space_object(uid, 'transcript', 'same', b'[]')

    with ThreadPoolExecutor(max_workers=2) as pool:
        one, two = pool.submit(put), pool.submit(put)
        first, second = one.result(timeout=60), two.result(timeout=60)
    assert first == second
    assert lake.get_space_object(first) == b'[]'
    client.collection('account_deletions').document(uid).set({'wipe_status': 'running'})
    assert lake.delete_space_upload_candidates(uid) == 1


def test_same_key_admissions_use_server_times_and_settle_independently(state):
    client, uid, bucket = state
    key = f'v1/spaces/{uid}/transcript/concurrent/digest'
    one = record_candidate(bucket.name, key)
    two = record_candidate(bucket.name, key)
    candidate_id = hashlib.sha256(f'{bucket.name}/{key}'.encode()).hexdigest()
    row = client.collection('lake_upload_candidates').document(candidate_id).get().to_dict()
    assert row['admitted_at'].tzinfo is not None
    assert set(row['in_flight']) == {one, two}
    assert all(
        attempt['admitted_at'].tzinfo is not None and attempt['session'] for attempt in row['in_flight'].values()
    )
    client.collection('account_deletions').document(uid).set({'wipe_status': 'running'})
    lake._settle_upload_candidate(bucket.name, key, two)
    lake.assert_space_uploads_quiescent(uid)
    lake._settle_upload_candidate(bucket.name, key, one)
    assert lake_wipe.destroy_owner_lake_keys(uid)['status'] == 'destroyed'
    assert lake.delete_space_upload_candidates(uid) == 0


def test_conversation_purge_fences_sessions_and_erases_with_real_ranges(state):
    client, uid, _ = state
    lake.put_space_object(uid, 'transcript', 'c', b'settled')
    key = f'v1/spaces/{uid}/transcript/c/abandoned'
    record_candidate('old-bucket', key)
    candidate = client.collection('lake_upload_candidates').document(
        hashlib.sha256(f'old-bucket/{key}'.encode()).hexdigest()
    )
    assert lake_wipe.purge_conversation_lake_objects(uid, 'c') == 1
    assert not candidate.get().exists
    assert lake.delete_space_upload_candidates(uid) == 0


def test_last_conversation_attempt_deletes_candidate_in_real_transaction(state):
    client, uid, bucket = state
    key = f'v1/spaces/{uid}/transcript/c/digest'
    one = record_candidate(bucket.name, key)
    two = record_candidate(bucket.name, key)
    lake_wipe._fence_conversation_uploads(uid, 'c')
    candidate = client.collection('lake_upload_candidates').document(
        hashlib.sha256(f'{bucket.name}/{key}'.encode()).hexdigest()
    )
    lake._settle_upload_candidate(bucket.name, key, one, delete_if_fenced=True)
    assert set(candidate.get().to_dict()['in_flight']) == {two}
    lake._settle_upload_candidate(bucket.name, key, two, delete_if_fenced=True)
    assert not candidate.get().exists


def record_candidate(bucket, key):
    blob = lake.create_storage_client().bucket(bucket).blob(key)
    session = blob.create_resumable_upload_session(
        content_type='application/octet-stream', size=9, if_generation_match=0, timeout=(1, 1), retry=None
    )
    return lake._record_upload_candidate(bucket, key, session, 9)
