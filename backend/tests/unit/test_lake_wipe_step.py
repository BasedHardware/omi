"""C4 erasure acceptance: real encrypted lake and key authority, synthetic ceremony deps."""

import hashlib
import zlib
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest

from config import object_lake as config
from database import transcript_pointer as pointer
from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules
from tests.unit.fixtures.lake_firestore import LakeFirestore as StrictFirestore
from utils.other import lake_wipe, object_lake as lake, space_keys
from utils.other.local_storage import LocalStorageClient


@pytest.fixture
def world(tmp_path, monkeypatch):
    for key, value in {
        'BUCKET_OBJECT_LAKE': 'lake-c4-test',
        'OBJECT_LAKE_RELEASE': 'v1',
        'OBJECT_LAKE_WRITE_ENABLED': 'true',
        'OBJECT_LAKE_WRITE_PERCENT': '100',
        'OBJECT_LAKE_READ_ENABLED': 'true',
        'OBJECT_LAKE_WIPE_DRAIN_SECONDS': '0',
        'OMI_ENV_STAGE': 'offline',
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv('OBJECT_LAKE_KMS_KEY', raising=False)
    store = StrictFirestore()
    bucket = LocalStorageClient(tmp_path).bucket('lake-c4-test')
    monkeypatch.setattr(lake, '_lake_bucket', lambda: bucket)
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


def test_lake_dark_prefix_has_zero_io(monkeypatch):
    monkeypatch.delenv('BUCKET_OBJECT_LAKE', raising=False)
    forbidden = Mock(side_effect=AssertionError('lake-dark purge performed IO'))
    monkeypatch.setattr(lake_wipe.users_db, 'get_user_deletion_wipe_status', forbidden)
    monkeypatch.setattr(lake, 'delete_space_prefix', forbidden)
    monkeypatch.setattr(lake, 'delete_space_entity', forbidden)
    assert lake_wipe.purge_owner_lake_content('owner') == {'status': 'noop'}
    assert lake_wipe.purge_conversation_lake_objects('owner', 'c') == 0
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


@pytest.mark.parametrize('value,expected', [(None, 5), ('-1', 0), ('70', 60), ('0', 0), ('1.25', 1.25)])
def test_drain_bounds(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv('OBJECT_LAKE_WIPE_DRAIN_SECONDS', raising=False)
    else:
        monkeypatch.setenv('OBJECT_LAKE_WIPE_DRAIN_SECONDS', value)
    assert config.wipe_drain_seconds() == expected


@pytest.mark.parametrize('value', ['nan', 'inf', '-inf', 'bad'])
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
    lake._record_upload_candidate('old-bucket', 'v1/spaces/owner/transcript/orphan/digest')
    lake._record_upload_candidate('lake-c4-test', 'v1/spaces/owner-other/transcript/keep/digest')
    marker(store)
    result = lake_wipe.purge_owner_lake_content('owner')
    assert result['objects_deleted'] == 0 and result['candidates_deleted'] == 1
    remaining = [row['key'] for path, row in store.rows.items() if path[0] == 'lake_upload_candidates']
    assert remaining == ['v1/spaces/owner-other/transcript/keep/digest']
    assert lake_wipe.purge_owner_lake_content('owner')['candidates_deleted'] == 0


def test_candidate_purge_failure_prevents_keys_and_firestore(world, ceremony, monkeypatch):
    _, store = world
    service, events = ceremony
    lake.put_space_object('owner', 'transcript', 'c', b'[]')
    monkeypatch.setattr(lake, 'delete_space_upload_candidates', Mock(side_effect=lake.LakeFetchError('candidate down')))
    assert service.background_wipe_user_data('owner') is False
    assert 'failed' in events and 'lake_keys' not in events and 'firestore' not in events
    assert space_keys.get_space_keys('owner') is not None


def test_lake_dark_key_step_also_erases_existing_upload_intents(world, monkeypatch):
    _, store = world
    lake._record_upload_candidate('old-bucket', 'v1/spaces/owner/transcript/orphan/digest')
    marker(store)
    monkeypatch.delenv('BUCKET_OBJECT_LAKE')
    lake_wipe.destroy_owner_lake_keys('owner')
    assert not any(path[0] == 'lake_upload_candidates' for path in store.rows)
    assert store.rows[('space_keys', 'owner')]['state'] == 'destroyed'
