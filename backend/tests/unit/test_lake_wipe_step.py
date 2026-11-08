"""C4 erasure acceptance: real encrypted lake and key authority, synthetic ceremony deps."""

import hashlib
import time
from datetime import datetime, timedelta, timezone
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from types import ModuleType
from unittest.mock import Mock

import pytest

from config import object_lake as config
from database import transcript_pointer as pointer
from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules
from tests.unit.fixtures.lake_firestore import LakeFirestore as StrictFirestore
from utils.other import lake_wipe, object_lake as lake, space_keys
from utils.other.local_storage import LocalStorageClient, LocalBlob


@pytest.fixture
def world(tmp_path, monkeypatch):
    for key, value in {
        'BUCKET_OBJECT_LAKE': 'lake-c4-test',
        'OBJECT_LAKE_RELEASE': 'v1',
        'OBJECT_LAKE_WRITE_ENABLED': 'true',
        'OBJECT_LAKE_WRITE_PERCENT': '100',
        'OBJECT_LAKE_READ_ENABLED': 'true',
        'OBJECT_LAKE_WIPE_DRAIN_SECONDS': '5',
        'OMI_ENV_STAGE': 'offline',
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv('OBJECT_LAKE_KMS_KEY', raising=False)
    store = StrictFirestore()
    storage_client = LocalStorageClient(tmp_path)
    monkeypatch.setattr(lake, 'create_storage_client', lambda: storage_client)
    bucket = storage_client.bucket('lake-c4-test')
    monkeypatch.setattr(lake, '_lake_bucket', lambda: bucket)
    monkeypatch.setattr(lake_wipe, 'time', Mock(sleep=Mock(), time=time.time))
    monkeypatch.setenv('SYNC_TASKS_HANDLER_URL', 'https://synthetic.invalid/v2/sync-jobs/run')
    monkeypatch.setenv('SYNC_TASKS_QUEUE', 'synthetic-queue')
    monkeypatch.setattr(lake_wipe, 'enqueue_named_task', Mock())
    monkeypatch.setattr(
        space_keys, 'space_key_firestore_client', lambda client=None: store if client is None else client
    )
    monkeypatch.setattr(
        lake_wipe.users_db,
        'get_user_deletion_wipe_status',
        lambda uid: (store.collection('account_deletions').document(uid).get().to_dict() or {}).get('wipe_status'),
    )
    space_keys.clear_space_key_cache()
    pointer.clear_memo()
    yield bucket, store
    pointer.clear_memo()
    space_keys.clear_space_key_cache()


def marker(store, status='running'):
    store.rows[('account_deletions', 'owner')] = {'wipe_status': status}


def test_lake_dark_owner_prefix_has_zero_io(monkeypatch):
    monkeypatch.delenv('BUCKET_OBJECT_LAKE', raising=False)
    forbidden = Mock(side_effect=AssertionError('lake-dark purge performed IO'))
    monkeypatch.setattr(lake_wipe.users_db, 'get_user_deletion_wipe_status', forbidden)
    monkeypatch.setattr(lake, 'delete_space_prefix', forbidden)
    monkeypatch.setattr(lake, 'delete_space_entity', forbidden)
    assert lake_wipe.purge_owner_lake_content('owner') == {'status': 'noop'}
    forbidden.assert_not_called()


@pytest.mark.parametrize('status', ['pending', 'pending_deletion', 'failed', None, 'cancelled', 'billing_failed'])
@pytest.mark.parametrize('step', [lake_wipe.purge_owner_lake_content, lake_wipe.destroy_owner_lake_keys])
def test_steps_require_running_marker(world, monkeypatch, status, step):
    _, store = world
    marker(store, status)
    forbidden = Mock(side_effect=AssertionError('destructive IO before running fence'))
    monkeypatch.setattr(lake, 'delete_space_prefix', forbidden)
    monkeypatch.setattr(space_keys, 'destroy_space_keys', forbidden)
    with pytest.raises(RuntimeError, match='requires a running'):
        step('owner')
    forbidden.assert_not_called()


@pytest.mark.parametrize('step', [lake_wipe.purge_owner_lake_content, lake_wipe.destroy_owner_lake_keys])
def test_marker_read_error_propagates(world, monkeypatch, step):
    monkeypatch.setattr(
        lake_wipe.users_db, 'get_user_deletion_wipe_status', Mock(side_effect=RuntimeError('marker down'))
    )
    with pytest.raises(RuntimeError, match='marker down'):
        step('owner')


def test_purge_uses_one_authoritative_marker_read(world, monkeypatch):
    _, store = world
    marker(store)
    read = Mock(return_value='running')
    monkeypatch.setattr(lake_wipe.users_db, 'get_user_deletion_wipe_status', read)
    lake_wipe.purge_owner_lake_content('owner')
    read.assert_called_once_with('owner')


def test_drain_is_between_fence_and_purge(world, monkeypatch):
    events = []
    monkeypatch.setattr(
        lake_wipe.users_db, 'get_user_deletion_wipe_status', lambda uid: events.append('fence') or 'running'
    )
    monkeypatch.setattr(lake_wipe.time, 'sleep', lambda seconds: events.append(('drain', seconds)))
    monkeypatch.setattr(lake, 'delete_space_prefix', lambda uid: events.append('purge') or 7)
    monkeypatch.setenv('OBJECT_LAKE_WIPE_DRAIN_SECONDS', '2.5')
    assert lake_wipe.purge_owner_lake_content('owner') == {
        'status': 'purged',
        'objects_deleted': 7,
        'candidates_deleted': 0,
    }
    assert events == ['fence', ('drain', 2.5), 'purge']


@pytest.mark.parametrize('value,expected', [(None, 5), ('60', 60), ('1.25', 1.25), ('0', 0)])
def test_drain_bounds(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv('OBJECT_LAKE_WIPE_DRAIN_SECONDS', raising=False)
    else:
        monkeypatch.setenv('OBJECT_LAKE_WIPE_DRAIN_SECONDS', value)
    assert config.wipe_drain_seconds() == expected


@pytest.mark.parametrize('value', ['nan', 'inf', '-inf', 'bad', '-1', '70'])
def test_invalid_drain_fails_closed(monkeypatch, value):
    monkeypatch.setenv('OBJECT_LAKE_WIPE_DRAIN_SECONDS', value)
    with pytest.raises(ValueError):
        config.wipe_drain_seconds()


@pytest.mark.parametrize(
    'error', [lake.LakeFetchError('lake down'), RuntimeError('Lake prefix deletion left objects behind')]
)
def test_required_purge_errors_escape(world, monkeypatch, error):
    _, store = world
    marker(store)
    monkeypatch.setattr(lake, 'delete_space_prefix', Mock(side_effect=error))
    with pytest.raises(type(error), match=str(error)):
        lake_wipe.purge_owner_lake_content('owner')


def test_purge_and_destroy_idempotent_even_with_writes_rolled_back(world, monkeypatch):
    bucket, store = world
    lake.put_space_object('owner', 'transcript', 'c1', b'[]')
    space_keys.rotate_space_key('owner')
    lake.put_space_object('owner', 'transcript', 'c2', b'[]')
    marker(store)
    monkeypatch.setenv('OBJECT_LAKE_WRITE_ENABLED', 'false')
    monkeypatch.setenv('OBJECT_LAKE_WRITE_PERCENT', '0')
    assert lake_wipe.purge_owner_lake_content('owner')['objects_deleted'] == 2
    assert lake_wipe.purge_owner_lake_content('owner')['objects_deleted'] == 0
    assert not list(bucket.list_blobs(prefix='v1/spaces/owner/'))
    assert lake_wipe.destroy_owner_lake_keys('owner')['versions_destroyed'] == 2
    assert lake_wipe.destroy_owner_lake_keys('owner')['versions_destroyed'] == 0


@pytest.mark.parametrize('existing', [False, True])
def test_lake_dark_still_tombstones_existing_or_absent_keys(world, monkeypatch, existing):
    _, store = world
    if existing:
        space_keys.get_or_create_space_key('owner')
    marker(store)
    monkeypatch.delenv('BUCKET_OBJECT_LAKE')
    assert lake_wipe.destroy_owner_lake_keys('owner')['versions_destroyed'] == int(existing)
    assert lake_wipe.destroy_owner_lake_keys('owner')['versions_destroyed'] == 0
    assert store.collection('space_keys').document('owner').get().to_dict()['state'] == 'destroyed'


@pytest.fixture
def ceremony(monkeypatch, world):
    monkeypatch.setenv('DIRECTORY_ROUTING_MODE', 'new_owners')
    monkeypatch.setenv('DIRECTORY_PG_DSN', 'synthetic-configured-directory')
    # Fake-before-import, as in test_delete_account_purge_storage. The ceremony
    # itself is real; only unrelated provider/Firestore operations are replaced.
    names = '''database database.directory database.directory.wipe database.messaging database.sync_jobs
        database._client database.legal_holds database.dev_api_key database.mcp_api_key database.mcp_oauth
        database.account_deletion_grace database.account_deletion_marker database.users database.processing_backlog
        database.action_items database.conversations database.screen_activity database.frame_requests database.vector_db
        firebase_admin firebase_admin.auth utils utils.stripe utils.cloud_tasks utils.executors utils.log_sanitizer
        utils.observability utils.observability.fallback utils.other utils.other.endpoints utils.other.storage
        utils.memory utils.memory.canonical_memory_adapter utils.memory.memory_service utils.memory.memory_system
        utils.retrieval utils.retrieval.frame_request_storage utils.twilio_service utils.integration_telemetry
        utils.sync utils.sync.cap_hold services.users.agent_vm_account_cleanup'''.split()
    fakes = {name: AutoMockModule(name) for name in names}
    for module in fakes.values():
        module.__path__ = []
    lake_steps = ModuleType('utils.other.lake_wipe')
    lake_steps.purge_owner_lake_content = lake_wipe.purge_owner_lake_content
    lake_steps.destroy_owner_lake_keys = lake_wipe.destroy_owner_lake_keys
    fakes[lake_steps.__name__] = lake_steps
    with stub_modules(fakes):
        service = load_module_fresh(
            'services.users.account_deletion', Path(__file__).parents[2] / 'services/users/account_deletion.py'
        )
    _, store = world
    events = []

    def step(name, result=None):
        return lambda *args, **kwargs: events.append(name) or result

    def status(value):
        def write(uid):
            events.append(value)
            marker(store, value)
            return True

        return write

    for name, event in {
        'acquire_destructive_operation': 'legal_hold',
        '_cancel_subscription_for_account_deletion': 'billing',
        'delete_agent_vm_for_account': 'agent_vm',
        'delete_account_credentials': 'credentials',
        'delete_user_caller_ids': 'twilio',
        'purge_owner_planes': 'cell',
        'purge_user_conversation_index': 'typesense',
        '_delete_memory_maintenance_registry': 'memory_registry',
    }.items():
        monkeypatch.setattr(service, name, step(event))
    monkeypatch.setattr(service.auth, 'delete_account', step('firebase_auth'))
    monkeypatch.setattr(
        service, 'MessagingStore', lambda: type('Messaging', (), {'delete_account': staticmethod(step('messaging'))})()
    )
    monkeypatch.setattr(
        service, 'purge_derived_user_data', step('derived', {'required_failures': [], 'best_effort_failures': []})
    )
    monkeypatch.setattr(service.users_db, 'delete_user_data', step('firestore', {'status': 'ok'}))
    monkeypatch.setattr(service.users_db, 'mark_user_deletion_wipe_running', status('running'))
    monkeypatch.setattr(service.users_db, 'mark_user_deletion_wipe_completed', status('completed'))
    monkeypatch.setattr(service.users_db, 'mark_user_deletion_wipe_failed', status('failed'))
    for name, real, event in [
        ('purge_owner_lake_content', lake_wipe.purge_owner_lake_content, 'lake_prefix'),
        ('destroy_owner_lake_keys', lake_wipe.destroy_owner_lake_keys, 'lake_keys'),
    ]:

        def run(uid, real=real, event=event):
            events.append(event)
            return real(uid)

        monkeypatch.setattr(service, name, run)
    yield service, events


def test_o1_wipe_coverage_gate_and_crash_retry(world, ceremony):
    bucket, store = world
    service, events = ceremony
    retained = [lake.put_space_object('owner', 'transcript', 'c1', b'[{"text":"one"}]').to_pointer_dict()]
    lake.put_space_object('owner', 'transcript', 'c2', b'[{"text":"two"}]')
    # Existing v1 pointers must report the same shredded state as new v2 ones.
    plaintext = b'[{"text":"legacy"}]'
    digest = hashlib.sha256(plaintext).hexdigest()
    key = f'v1/spaces/owner/transcript/legacy/{digest}'
    nonce = b'0' * 12
    dek = space_keys.unwrap_space_dek('owner', 1)
    payload = lake._HEADER.pack(b'OLK1', 1, 1, nonce) + lake.AESGCM(dek).encrypt(
        nonce, zlib.compress(plaintext), key.encode()
    )
    blob = bucket.blob(key)
    blob.upload_from_string(payload, if_generation_match=0)
    legacy = lake.LakeObjectRef(bucket.name, key, digest, len(payload), 'transcript', 1).to_pointer_dict()
    assert pointer.decode_stored_transcript('owner', legacy, True) == [{"text": "legacy"}]
    retained.append(legacy)
    for _ in range(2):
        events.clear()
        assert service.background_wipe_user_data('owner') is True
        assert events == [
            'legal_hold',
            'running',
            'billing',
            'agent_vm',
            'messaging',
            'credentials',
            'firebase_auth',
            'twilio',
            'derived',
            'cell',
            'lake_prefix',
            'firestore',
            'typesense',
            'memory_registry',
            'lake_keys',
            'completed',
        ]
        assert not list(bucket.list_blobs(prefix='v1/spaces/owner/'))
        assert not any(path[0] == 'lake_upload_candidates' for path in store.rows)
        tombstone = store.collection('space_keys').document('owner').get().to_dict()
        assert set(tombstone) == {'space_id', 'state', 'destroyed_at'}
        assert tombstone['space_id'] == 'owner' and tombstone['state'] == 'destroyed' and tombstone['destroyed_at']
        assert store.collection('account_deletions').document('owner').get().to_dict()['wipe_status'] == 'completed'
        pointer.clear_memo()
        for stale in retained:
            with pytest.raises(pointer.TranscriptShredded):
                pointer.decode_stored_transcript('owner', stale, True)
        with pytest.raises(lake.LakeWriteFenced):
            lake.put_space_object('owner', 'transcript', 'late', b'[]')


def test_failed_prefix_never_destroys_keys_or_user_documents(world, ceremony, monkeypatch):
    _, store = world
    service, events = ceremony
    lake.put_space_object('owner', 'transcript', 'c', b'[]')
    monkeypatch.setattr(lake, 'delete_space_prefix', Mock(side_effect=lake.LakeFetchError('lake down')))
    assert service.background_wipe_user_data('owner') is False
    assert 'failed' in events and 'lake_keys' not in events and 'firestore' not in events
    assert space_keys.get_space_keys('owner') is not None


def test_late_upload_worker_loss_is_purged_again_before_keys(world, ceremony, monkeypatch):
    bucket, store = world
    service, events = ceremony
    admitted, release, dead = Event(), Event(), Event()
    now = datetime.now(timezone.utc)
    quiescence = lake.assert_space_uploads_quiescent
    monkeypatch.setattr(lake, 'assert_space_uploads_quiescent', lambda uid, **kw: quiescence(uid, now=now))
    erase = lake.delete_space_upload_candidates
    monkeypatch.setattr(lake, 'delete_space_upload_candidates', lambda uid, **kw: erase(uid, now=now))
    upload = LocalBlob.upload_from_string
    post_put_check = Mock(side_effect=AssertionError('dead worker reached its post-put check'))
    monkeypatch.setattr(lake, '_check_put_authority', post_put_check)

    class WorkerLost(BaseException):
        pass

    def late_upload(blob, *args, **kwargs):
        admitted.set()
        assert release.wait(timeout=10)
        upload(blob, *args, **kwargs)
        # Model loss after the object commits but before control returns to the
        # writer. No self-cleanup or post-put authority check can execute.
        raise WorkerLost()

    def worker():
        try:
            lake.put_space_object('owner', 'transcript', 'late', b'late upload')
        finally:
            dead.set()

    monkeypatch.setattr(LocalBlob, 'upload_from_string', late_upload)

    def firestore_step(uid):
        # The first prefix purge has completed, with candidates still durable.
        assert events[-1] == 'lake_prefix'
        assert not list(bucket.list_blobs(prefix='v1/spaces/owner/'))
        assert any(path[0] == 'lake_upload_candidates' for path in store.rows)
        # Leave the request in flight through the final destructive step.
        events.append('firestore')
        return {'status': 'ok'}

    monkeypatch.setattr(service.users_db, 'delete_user_data', firestore_step)
    destroy = space_keys.destroy_space_keys

    def checked_destroy(uid):
        # The final step has independently purged the late object's metadata
        # and bytes, verified prefix absence, and erased discovery rows.
        assert not list(bucket.list_blobs(prefix='v1/spaces/owner/'))
        assert not any(path[0] == 'lake_upload_candidates' for path in store.rows)
        return destroy(uid)

    monkeypatch.setattr(space_keys, 'destroy_space_keys', checked_destroy)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(worker)
        try:
            assert admitted.wait(timeout=10)
            assert service.background_wipe_user_data('owner') is False
            assert 'completed' not in events and events[-1] == 'failed'
            assert not list(bucket.list_blobs())
            # The upload commits only after the refused final step, then loses
            # its worker before any completion or authority check.
            release.set()
            assert dead.wait(timeout=10)
            assert len(list(bucket.list_blobs())) == 1
            assert space_keys.get_space_keys('owner') is not None
            assert any(path[0] == 'lake_upload_candidates' for path in store.rows)
            # Still blocked at the exact bound. Retry only once all pre-fence
            # requests are older than the bound; no real-time sleeps.
            admission = next(
                row['admitted_at'] for path, row in store.rows.items() if path[0] == 'lake_upload_candidates'
            )
            now = admission + timedelta(seconds=config.put_quiescence_seconds())
            marker(store)
            with pytest.raises(lake.LakeFetchError, match='still in flight'):
                lake_wipe.destroy_owner_lake_keys('owner', now=now)
            now += timedelta(microseconds=1)
            monkeypatch.setattr(service.users_db, 'delete_user_data', lambda uid: {'status': 'ok'})
            assert service.background_wipe_user_data('owner') is True
        finally:
            release.set()
        with pytest.raises(WorkerLost):
            future.result(timeout=10)
    post_put_check.assert_not_called()
    assert events[-2:] == ['lake_keys', 'completed']
    assert store.rows[('space_keys', 'owner')]['state'] == 'destroyed'
    assert store.rows[('account_deletions', 'owner')]['wipe_status'] == 'completed'


def test_final_prefix_failure_retains_candidates_and_keys_for_retry(world, ceremony, monkeypatch):
    _, store = world
    service, events = ceremony
    lake.put_space_object('owner', 'transcript', 'c', b'[]')
    purge = lake.delete_space_prefix
    calls = []

    def final_failure(uid):
        calls.append(uid)
        if len(calls) == 2:
            raise lake.LakePurgeIncomplete('final prefix not absent')
        return purge(uid)

    monkeypatch.setattr(lake, 'delete_space_prefix', final_failure)
    assert service.background_wipe_user_data('owner') is False
    assert len(calls) == 2
    assert events[-2:] == ['lake_keys', 'failed']
    assert any(path[0] == 'lake_upload_candidates' for path in store.rows)
    assert space_keys.get_space_keys('owner') is not None
    monkeypatch.setattr(lake, 'delete_space_prefix', purge)
    assert service.background_wipe_user_data('owner') is True
    assert not any(path[0] == 'lake_upload_candidates' for path in store.rows)
    assert store.rows[('space_keys', 'owner')]['state'] == 'destroyed'


def test_grace_restore_never_runs_lake_steps(ceremony, monkeypatch):
    service, events = ceremony
    monkeypatch.setattr(
        service.deletion_marker_db,
        'read_account_deletion_marker',
        lambda uid: {'wipe_status': 'pending_deletion', 'grace_actions_complete': True},
    )
    monkeypatch.setattr(service.deletion_grace_db, 'restore_user_deletion', lambda uid: 'restored')
    assert service.restore_account_deletion('owner')['restored'] is True
    assert 'lake_prefix' not in events and 'lake_keys' not in events


@pytest.fixture
def merge_modules():
    # Keep merge off the collection import graph. Import setup is excluded from
    # the shared per-test CPU budget, just as module-level imports would be.
    from database import conversations as conversations_db, review_overlay_merge
    from utils.conversations import merge_conversations as merge

    # Load the production merge's deferred pipeline dependency during setup.
    import utils.conversations.process_conversation  # noqa: F401
    from utils import notification_dispatch

    return conversations_db, review_overlay_merge, merge, notification_dispatch


def test_merge_pointer_sources_get_independent_survivor_objects(world, monkeypatch, merge_modules):
    from datetime import datetime, timedelta, timezone

    conversations_db, review_overlay_merge, merge, notification_dispatch = merge_modules
    _, store = world
    monkeypatch.setenv('OBJECT_LAKE_INLINE_MAX_BYTES', '0')
    monkeypatch.setattr(pointer._client, 'get_data_plane_firestore_client', lambda: store)
    now = datetime(2026, 11, 7, tzinfo=timezone.utc)
    rows = {}
    for index, cid in enumerate(['donor-a', 'donor-b']):
        row = {
            'id': cid,
            'status': 'completed',
            'visibility': 'shared',
            'created_at': now,
            'started_at': now + timedelta(seconds=index * 20),
            'finished_at': now + timedelta(seconds=20 + index * 20),
            'language': 'en',
            'transcript_segments': [{'text': cid, 'start': 0.0, 'end': 10.0, 'speaker_id': 0, 'is_user': True}],
        }
        rows[cid] = conversations_db.encode_conversation_for_write('owner', row, 'standard')
        assert isinstance(rows[cid]['transcript_segments'], dict)
    pointer.clear_memo()
    monkeypatch.setattr(
        merge.conversations_db,
        'get_conversation',
        lambda uid, cid: conversations_db.prepare_conversation_for_read(rows[cid], uid),
    )
    saved = []

    def persist(uid, data):
        rows[data['id']] = conversations_db.encode_conversation_for_write(uid, data, 'standard')
        saved.append(data['id'])

    monkeypatch.setattr(merge.lifecycle_service, 'create_processing_conversation', persist)
    monkeypatch.setattr(merge.lifecycle_service, 'complete', lambda *args: None)
    monkeypatch.setattr(merge, '_collect_all_photos', lambda *args: [])
    monkeypatch.setattr(merge, '_copy_audio_chunks_for_merge', lambda *args, **kwargs: [])
    monkeypatch.setattr(merge, '_delete_conversation_and_related_data', lambda *args, **kwargs: None)
    monkeypatch.setattr(merge, 'canonical_intake_is_fenced', lambda: False)
    monkeypatch.setattr(review_overlay_merge, 'transfer', lambda *args, **kwargs: False)
    monkeypatch.setattr(notification_dispatch, 'dispatch_merge_completed', lambda *args: None)
    monkeypatch.setattr(merge, '_handle_merge_failure', Mock(side_effect=AssertionError('merge failed')))
    merge.perform_merge_async('owner', list(rows), reprocess=False)
    assert len(saved) == 1
    survivor = rows[saved[0]]['transcript_segments']
    assert f"/{saved[0]}/" in survivor['key']
    assert survivor not in [rows[cid]['transcript_segments'] for cid in ['donor-a', 'donor-b']]
    lake_wipe.purge_conversation_lake_objects('owner', 'donor-a', ['donor-b'])
    pointer.clear_memo()
    assert [segment['text'] for segment in pointer.decode_stored_transcript('owner', survivor, True)] == [
        'donor-a',
        'donor-b',
    ]


def test_conversation_retry_uses_raw_inventory_after_blob_already_purged(world, merge_modules, monkeypatch):
    from services import conversation_frame_evidence as evidence

    conversations_db, _, merge, _ = merge_modules
    bucket, _ = world
    parent = lake.put_space_object('owner', 'transcript', 'parent', b'[]')
    lake.put_space_object('owner', 'transcript', 'donor', b'[]')
    rows = {
        'parent': {'id': 'parent', 'transcript_segments': parent.to_pointer_dict(), 'sync_merged_from': ['donor']},
        'donor': {'id': 'donor'},
    }
    # Previous attempt purged the parent, then failed before donor/doc deletion.
    lake.delete_space_entity('owner', 'parent')
    pointer.clear_memo()
    events = []
    monkeypatch.setattr(conversations_db, 'get_conversation_raw_snapshot', lambda uid, cid: rows.get(cid))
    monkeypatch.setattr(
        conversations_db, 'get_conversation', Mock(side_effect=AssertionError('decoded deletion inventory'))
    )
    monkeypatch.setattr(conversations_db, 'get_conversation_photos', lambda *args: [])
    monkeypatch.setattr(evidence.frame_requests_db, 'list_all_frame_request_storage_ids', lambda *args, **kwargs: [])
    monkeypatch.setattr(
        evidence.frame_requests_db, 'persist_conversation_frame_deletion_outbox', lambda *args: events.append('outbox')
    )
    monkeypatch.setattr(evidence.frame_requests_db, 'delete_frame_requests_for_conversation', lambda *args: None)
    monkeypatch.setattr(merge.conversation_tombstones, 'record_deletion', lambda *args: None)
    monkeypatch.setattr(merge, 'record_survivor_deleted', lambda *args: None)

    def delete(uid, cid, **kwargs):
        # Both lake entities must already be absent before any metadata deletion.
        assert not list(bucket.list_blobs(prefix='v1/spaces/owner/'))
        events.append(cid)
        rows.pop(cid, None)

    monkeypatch.setattr(merge, '_delete_conversation_and_related_data', delete)
    monkeypatch.setattr(conversations_db, 'delete_conversation', delete)
    evidence.delete_conversation_and_frame_evidence('owner', 'parent')
    assert rows == {}
    assert events == ['outbox', 'donor', 'parent']


def test_candidate_purge_covers_orphans_old_bucket_and_owner_boundary(world):
    _, store = world
    attempt = lake._record_upload_candidate('old-bucket', 'v1/spaces/owner/transcript/orphan/digest')
    lake._settle_upload_candidate('old-bucket', 'v1/spaces/owner/transcript/orphan/digest', attempt)
    lake._record_upload_candidate('lake-c4-test', 'v1/spaces/owner-other/transcript/keep/digest')
    marker(store)
    result = lake_wipe.purge_owner_lake_content('owner')
    assert result['objects_deleted'] == 0 and result['candidates_deleted'] == 0
    assert sum(path[0] == 'lake_upload_candidates' for path in store.rows) == 2
    lake_wipe.destroy_owner_lake_keys('owner')
    remaining = [row['key'] for path, row in store.rows.items() if path[0] == 'lake_upload_candidates']
    assert remaining == ['v1/spaces/owner-other/transcript/keep/digest']
    assert lake_wipe.purge_owner_lake_content('owner')['candidates_deleted'] == 0


def test_candidate_purge_failure_prevents_key_destroy_and_completion(world, ceremony, monkeypatch):
    _, store = world
    service, events = ceremony
    lake.put_space_object('owner', 'transcript', 'c', b'[]')
    monkeypatch.setattr(lake, 'delete_space_upload_candidates', Mock(side_effect=lake.LakeFetchError('candidate down')))
    assert service.background_wipe_user_data('owner') is False
    assert 'failed' in events and 'lake_keys' in events and 'firestore' in events and 'completed' not in events
    assert space_keys.get_space_keys('owner') is not None


def test_lake_dark_key_step_also_erases_existing_upload_intents(world, monkeypatch):
    _, store = world
    attempt = lake._record_upload_candidate('old-bucket', 'v1/spaces/owner/transcript/orphan/digest')
    lake._settle_upload_candidate('old-bucket', 'v1/spaces/owner/transcript/orphan/digest', attempt)
    marker(store)
    monkeypatch.delenv('BUCKET_OBJECT_LAKE')
    lake_wipe.destroy_owner_lake_keys('owner')
    assert not any(path[0] == 'lake_upload_candidates' for path in store.rows)
    assert store.rows[('space_keys', 'owner')]['state'] == 'destroyed'


def test_settled_young_candidate_does_not_block_final_step(world):
    _, store = world
    ref = lake.put_space_object('owner', 'transcript', 'c', b'[]')
    row = next(row for path, row in store.rows.items() if path[0] == 'lake_upload_candidates')
    assert row['settled'] is True and row['in_flight'] == {}
    marker(store)
    assert lake_wipe.destroy_owner_lake_keys('owner', now=row['admitted_at'])['status'] == 'destroyed'
    assert store.rows[('space_keys', 'owner')]['state'] == 'destroyed'
    assert not any(path[0] == 'lake_upload_candidates' for path in store.rows)


@pytest.mark.parametrize('bad_time', [None, 'invalid', datetime(2026, 1, 1)])
def test_invalid_admission_time_blocks_key_destruction(world, bad_time):
    _, store = world
    lake.put_space_object('owner', 'transcript', 'c', b'[]')
    row = next(row for path, row in store.rows.items() if path[0] == 'lake_upload_candidates')
    row.update(settled=False, in_flight={'lost': bad_time})
    marker(store)
    with pytest.raises(lake.LakeFetchError, match='admission time unavailable'):
        lake_wipe.destroy_owner_lake_keys('owner')
    assert space_keys.get_space_keys('owner') is not None


def test_quiescence_discovery_failure_blocks_final_purge(world, monkeypatch):
    _, store = world
    marker(store)
    monkeypatch.setattr(lake, '_space_candidate_key_range', Mock(side_effect=RuntimeError('Firestore down')))
    forbidden = Mock(side_effect=AssertionError('purged before quiescence'))
    monkeypatch.setattr(lake, 'delete_space_prefix', forbidden)
    with pytest.raises(lake.LakeFetchError, match='quiescence unavailable'):
        lake_wipe.destroy_owner_lake_keys('owner')
    forbidden.assert_not_called()


def test_zero_drain_skips_sleep_but_still_purges(world, monkeypatch):
    bucket, store = world
    monkeypatch.setenv('OBJECT_LAKE_WIPE_DRAIN_SECONDS', '0')
    lake.put_space_object('owner', 'transcript', 'c', b'[]')
    marker(store)
    sleep = Mock(side_effect=AssertionError('zero drain must skip sleep'))
    monkeypatch.setattr(lake_wipe.time, 'sleep', sleep)
    assert lake_wipe.purge_owner_lake_content('owner')['objects_deleted'] == 1
    sleep.assert_not_called()
    assert not list(bucket.list_blobs())


def test_conversation_purge_retains_all_unsettled_candidates_until_delayed_repurge(world):
    bucket, store = world
    lake.put_space_object('owner', 'transcript', 'c', b'settled')
    lake.put_space_object('owner', 'transcript', 'donor', b'donor')
    # Key ranges cover orphan intents and old bucket bindings too.
    old_key = 'v1/spaces/owner/transcript/c/old'
    legacy_key = 'v1/spaces/owner/transcript/c/legacy'
    young_key = 'v1/spaces/owner/transcript/c/young'
    for key in (old_key, legacy_key, young_key):
        lake._record_upload_candidate('old-bucket', key)
    lake.put_space_object('owner', 'transcript', 'c-sibling', b'keep')
    lake.put_space_object('owner-other', 'transcript', 'c', b'keep owner')
    past = datetime.now(timezone.utc) - timedelta(seconds=config.put_quiescence_seconds() + 1)
    for path, row in store.rows.items():
        if path[0] == 'lake_upload_candidates' and row['key'] == old_key:
            row['in_flight'] = {'lost': past}
            row['admitted_at'] = past
        if path[0] == 'lake_upload_candidates' and row['key'] == legacy_key:
            row.pop('in_flight')
            row['created_at'] = past
            row['admitted_at'] = past
    assert lake_wipe.purge_conversation_lake_objects('owner', 'c', ['donor']) == 2
    remaining = {row['key'] for path, row in store.rows.items() if path[0] == 'lake_upload_candidates'}
    assert {old_key, legacy_key, young_key} <= remaining and len(remaining) == 5
    assert all('/c-sibling/' in blob.name or '/owner-other/' in blob.name for blob in bucket.list_blobs())
    # A lost worker cannot self-clean; a later janitor/retry after the bound can.
    assert (
        lake_wipe.repurge_conversation_lake_objects(
            'owner', 'c', now=datetime.now(timezone.utc) + timedelta(seconds=config.put_quiescence_seconds() + 1)
        )
        == 3
    )


def test_last_fenced_attempt_erases_shared_candidate_transactionally(world):
    _, store = world
    key = 'v1/spaces/owner/transcript/c/digest'
    one = lake._record_upload_candidate('old-bucket', key)
    two = lake._record_upload_candidate('old-bucket', key)
    lake_wipe.purge_conversation_lake_objects('owner', 'c')
    lake._settle_upload_candidate('old-bucket', key, two, delete_if_fenced=True)
    row = next(row for path, row in store.rows.items() if path[0] == 'lake_upload_candidates')
    assert set(row['in_flight']) == {one}
    lake._settle_upload_candidate('old-bucket', key, one, delete_if_fenced=True)
    assert not any(path[0] == 'lake_upload_candidates' for path in store.rows)
    assert store.transactions[-1].deletes


def test_conversation_failed_prefix_retains_candidates(world, monkeypatch):
    _, store = world
    lake.put_space_object('owner', 'transcript', 'c', b'[]')
    monkeypatch.setattr(lake, 'delete_space_entity', Mock(side_effect=lake.LakePurgeIncomplete('not absent')))
    with pytest.raises(lake.LakePurgeIncomplete):
        lake_wipe.purge_conversation_lake_objects('owner', 'c')
    assert any(path[0] == 'lake_upload_candidates' for path in store.rows)


def test_failed_late_generation_cleanup_retains_discovery(world, monkeypatch):
    bucket, store = world
    original = LocalBlob.upload_from_string

    def late_upload(blob, *args, **kwargs):
        lake_wipe.purge_conversation_lake_objects('owner', 'c')
        original(blob, *args, **kwargs)
        monkeypatch.setattr(LocalBlob, 'delete', Mock(side_effect=RuntimeError('storage down')))

    monkeypatch.setattr(LocalBlob, 'upload_from_string', late_upload)
    with pytest.raises(lake.LakeFetchError, match='cleanup unavailable'):
        lake.put_space_object('owner', 'transcript', 'c', b'late')
    assert len(list(bucket.list_blobs())) == 1
    assert any(path[0] == 'lake_upload_candidates' for path in store.rows)


@pytest.mark.parametrize('bad_time', [None, 'invalid', datetime(2026, 1, 1)])
def test_conversation_candidate_invalid_admission_fails_closed(world, bad_time):
    _, store = world
    lake._record_upload_candidate('old-bucket', 'v1/spaces/owner/transcript/c/digest')
    row = next(row for path, row in store.rows.items() if path[0] == 'lake_upload_candidates')
    row['in_flight'] = {'lost': bad_time}
    with pytest.raises(lake.LakeFetchError, match='admission time unavailable'):
        lake_wipe.purge_conversation_lake_objects('owner', 'c')
    assert any(path[0] == 'lake_upload_candidates' for path in store.rows)


def test_conversation_candidate_discovery_failure_is_retryable(world, monkeypatch):
    _, store = world
    original = store.collection

    def fail(name):
        if name == 'lake_upload_candidates':
            raise RuntimeError('discovery down')
        return original(name)

    monkeypatch.setattr(store, 'collection', fail)
    with pytest.raises(lake.LakeFetchError, match='candidate purge unavailable'):
        lake_wipe.purge_conversation_lake_objects('owner', 'c')


def test_conversation_worker_loss_retains_young_candidate_until_account_wipe(world, monkeypatch):
    bucket, store = world
    upload = LocalBlob.upload_from_string

    class WorkerLost(BaseException):
        pass

    def lost_writer(blob, *args, **kwargs):
        lake_wipe.purge_conversation_lake_objects('owner', 'c')
        upload(blob, *args, **kwargs)
        raise WorkerLost()

    monkeypatch.setattr(LocalBlob, 'upload_from_string', lost_writer)
    with pytest.raises(WorkerLost):
        lake.put_space_object('owner', 'transcript', 'c', b'late worker loss')
    assert len(list(bucket.list_blobs())) == 1
    row = next(row for path, row in store.rows.items() if path[0] == 'lake_upload_candidates')
    assert row['in_flight'] and not row['settled']
    assert lake.delete_entity_upload_candidates('owner', 'c', now=row['admitted_at']) == 0
    marker(store)
    now = row['admitted_at'] + timedelta(seconds=config.put_quiescence_seconds() + 1)
    assert lake_wipe.destroy_owner_lake_keys('owner', now=now)['status'] == 'destroyed'
    assert not list(bucket.list_blobs())
    assert not any(path[0] == 'lake_upload_candidates' for path in store.rows)


@pytest.mark.parametrize('bucket_configured', [True, False])
@pytest.mark.parametrize('scope', ['conversation', 'account'])
def test_erasure_deletes_recorded_former_bucket_before_candidate_row(world, monkeypatch, bucket_configured, scope):
    _, store = world
    key = 'v1/spaces/owner/transcript/c/former'
    attempt = lake._record_upload_candidate('former-bucket', key)
    lake._settle_upload_candidate('former-bucket', key, attempt)
    blob = lake.create_storage_client().bucket('former-bucket').blob(key)
    blob.upload_from_string(b'encrypted former content')
    if not bucket_configured:
        monkeypatch.delenv('BUCKET_OBJECT_LAKE')
    original = lake._delete_candidate_object
    observations = []

    def checked(row):
        assert any(path[0] == 'lake_upload_candidates' for path in store.rows)
        original(row)
        assert not blob.exists()
        observations.append(row['bucket'])

    monkeypatch.setattr(lake, '_delete_candidate_object', checked)
    if scope == 'conversation':
        lake_wipe.purge_conversation_lake_objects('owner', 'c')
    else:
        marker(store)
        lake_wipe.destroy_owner_lake_keys('owner')
    assert observations == ['former-bucket']
    assert not any(path[0] == 'lake_upload_candidates' for path in store.rows)


@pytest.mark.parametrize('scope', ['conversation', 'account'])
@pytest.mark.parametrize('failure', ['delete', 'verification', 'still_exists'])
def test_former_bucket_failure_keeps_discovery_and_keys(world, monkeypatch, scope, failure):
    _, store = world
    lake.put_space_object('owner', 'transcript', 'c', b'content')
    key = 'v1/spaces/owner/transcript/c/former'
    attempt = lake._record_upload_candidate('former-bucket', key)
    lake._settle_upload_candidate('former-bucket', key, attempt)
    blob = lake.create_storage_client().bucket('former-bucket').blob(key)
    blob.upload_from_string(b'encrypted content')
    original = getattr(LocalBlob, 'exists' if failure == 'verification' else 'delete')

    def fail(target, *args, **kwargs):
        if target.bucket.name == 'former-bucket':
            if failure == 'still_exists':
                return None
            raise RuntimeError('synthetic former bucket outage')
        return original(target, *args, **kwargs)

    monkeypatch.setattr(LocalBlob, 'exists' if failure == 'verification' else 'delete', fail)
    monkeypatch.delenv('BUCKET_OBJECT_LAKE')
    with pytest.raises(lake.LakeFetchError):
        if scope == 'conversation':
            lake_wipe.purge_conversation_lake_objects('owner', 'c')
        else:
            marker(store)
            lake_wipe.destroy_owner_lake_keys('owner')
    assert any(row.get('bucket') == 'former-bucket' for row in store.rows.values())
    assert space_keys.get_space_keys('owner') is not None


def test_unsettled_older_than_old_bound_retains_discovery_and_schedules_day_repurge(world, monkeypatch):
    enqueue = Mock()
    monkeypatch.setattr(lake_wipe, 'enqueue_named_task', enqueue)
    _, store = world
    key = 'v1/spaces/owner/transcript/c/lost'
    lake._record_upload_candidate('former-bucket', key)
    row = next(row for path, row in store.rows.items() if path[0] == 'lake_upload_candidates')
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    row.update(admitted_at=past, in_flight={'lost': past})
    lake_wipe.purge_conversation_lake_objects('owner', 'c')
    assert row['in_flight'] and any(path[0] == 'lake_upload_candidates' for path in store.rows)
    call = enqueue.call_args
    assert call is not None
    assert call.args[1] == 'https://synthetic.invalid/internal/lake/conversation-repurge'
    assert call.args[3] == {'space_id': 'owner', 'entity_id': 'c'}
    assert call.kwargs['schedule_at'] == int(past.timestamp() + 86400) + 1
    assert 'owner' not in call.args[2]


def test_lost_worker_delayed_repurge_redeletes_former_bucket_then_erases(world, monkeypatch):
    _, store = world
    key = 'v1/spaces/owner/transcript/c/lost'
    lake._record_upload_candidate('former-bucket', key)
    lake_wipe.purge_conversation_lake_objects('owner', 'c')
    row = next(row for path, row in store.rows.items() if path[0] == 'lake_upload_candidates')
    # Remote commit after the initial purge, with no surviving writer.
    blob = lake.create_storage_client().bucket('former-bucket').blob(key)
    blob.upload_from_string(b'late encrypted commit')
    monkeypatch.delenv('BUCKET_OBJECT_LAKE')
    due = row['admitted_at'] + timedelta(hours=24)
    with pytest.raises(lake.LakeFetchError, match='still in flight'):
        lake_wipe.repurge_conversation_lake_objects('owner', 'c', now=due)
    assert not blob.exists()
    assert any(path[0] == 'lake_upload_candidates' for path in store.rows)
    blob.upload_from_string(b'late at bound')
    assert lake_wipe.repurge_conversation_lake_objects('owner', 'c', now=due + timedelta(microseconds=1)) == 1
    assert not blob.exists()
    assert not any(path[0] == 'lake_upload_candidates' for path in store.rows)
    assert lake_wipe.repurge_conversation_lake_objects('owner', 'c', now=due + timedelta(seconds=1)) == 0


def test_newest_admission_controls_day_bound_after_newer_attempt_settles(world, monkeypatch):
    enqueue = Mock()
    monkeypatch.setattr(lake_wipe, 'enqueue_named_task', enqueue)
    _, store = world
    key = 'v1/spaces/owner/transcript/c/lost'
    lake._record_upload_candidate('former-bucket', key)
    row = next(row for path, row in store.rows.items() if path[0] == 'lake_upload_candidates')
    now = datetime.now(timezone.utc)
    row.update(in_flight={'lost': now - timedelta(days=2)}, admitted_at=now)
    lake_wipe.purge_conversation_lake_objects('owner', 'c')
    with pytest.raises(lake.LakeFetchError, match='still in flight'):
        lake_wipe.repurge_conversation_lake_objects('owner', 'c', now=now + timedelta(hours=23))
    call = enqueue.call_args
    assert call is not None
    assert call.kwargs['schedule_at'] == int(now.timestamp() + 86400) + 1


@pytest.mark.parametrize('failure', ['missing_config', 'enqueue'])
def test_repurge_enqueue_failure_retains_candidate_and_retries(world, monkeypatch, failure):
    _, store = world
    lake._record_upload_candidate('former-bucket', 'v1/spaces/owner/transcript/c/lost')
    if failure == 'missing_config':
        monkeypatch.delenv('SYNC_TASKS_HANDLER_URL')
    else:
        monkeypatch.setattr(lake_wipe, 'enqueue_named_task', Mock(side_effect=RuntimeError('queue unavailable')))
    with pytest.raises(lake.LakeFetchError):
        lake_wipe.purge_conversation_lake_objects('owner', 'c')
    assert any(path[0] == 'lake_upload_candidates' for path in store.rows)


def test_account_expired_attempt_redeletes_former_bucket_immediately_before_erasure(world, monkeypatch):
    _, store = world
    key = 'v1/spaces/owner/transcript/c/lost'
    lake._record_upload_candidate('former-bucket', key)
    row = next(row for path, row in store.rows.items() if path[0] == 'lake_upload_candidates')
    blob = lake.create_storage_client().bucket('former-bucket').blob(key)
    blob.upload_from_string(b'late encrypted upload')
    marker(store)
    monkeypatch.delenv('BUCKET_OBJECT_LAKE')
    with pytest.raises(lake.LakeFetchError, match='still in flight'):
        lake_wipe.destroy_owner_lake_keys('owner', now=row['admitted_at'] + timedelta(seconds=631))
    assert blob.exists()
    lake_wipe.destroy_owner_lake_keys('owner', now=row['admitted_at'] + timedelta(hours=24, seconds=1))
    assert not blob.exists()
    assert not any(path[0] == 'lake_upload_candidates' for path in store.rows)


def test_unconfigured_lake_still_fences_conversation_before_returning(world, monkeypatch):
    # A bucketless revision cannot prove no bucket-enabled writer is between
    # admission and candidate recording, so it always writes the durable fence.
    _, store = world
    monkeypatch.delenv('BUCKET_OBJECT_LAKE')
    assert lake_wipe.purge_conversation_lake_objects('owner', 'c', source_ids=('d',)) == 0
    fenced = {path[-1] for path in store.rows if 'deleted_conversations' in path}
    assert fenced == {'c', 'd'}
