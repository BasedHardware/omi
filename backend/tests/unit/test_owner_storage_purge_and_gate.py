from contextlib import contextmanager
from types import SimpleNamespace
import struct
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import Forbidden

from utils.other import storage as storage_mod
from database import account_deletion_operational_holds
from utils.retrieval import frame_request_storage


class _Blob:
    def __init__(self, bucket, name):
        self.bucket = bucket
        self.name = name

    def upload_from_string(self, data, **kwargs):
        self.bucket.names.add(self.name)

    @contextmanager
    def open(self, mode, **kwargs):
        stream = MagicMock()
        yield stream
        self.bucket.names.add(self.name)

    def delete(self):
        self.bucket.names.remove(self.name)

    def exists(self):
        return self.name in self.bucket.names


class _Bucket:
    def __init__(self, names):
        self.names = set(names)
        self.location = "us-central1"
        self.versioning_enabled = False
        self.soft_delete_policy = SimpleNamespace(retention_duration_seconds=0)

    def reload(self):
        pass

    def blob(self, name):
        return _Blob(self, name)

    def list_blobs(self, *, prefix, **kwargs):
        return [_Blob(self, name) for name in sorted(self.names) if name.startswith(prefix)]


class _Client:
    def __init__(self, buckets):
        self.buckets = buckets

    def bucket(self, name):
        return self.buckets[name]


@pytest.fixture(autouse=True)
def _no_sync_uploads(monkeypatch):
    # Sync staging lookups read the owner's ledger; these fakes have none unless a test says so.
    from database.sync_ledger_sources import StagingPlan

    monkeypatch.setattr('database.sync_ledger_sources.staging_plan', lambda *args, **kwargs: StagingPlan())


def test_owner_prefix_purge_removes_private_and_non_private_uid_objects(monkeypatch):
    uid = 'uid1'
    buckets = {
        'speech': _Bucket({f'{uid}/speech.wav', 'other/speech.wav'}),
        'private': _Bucket(
            {
                f'chunks/{uid}/conv/a.opus',
                f'raw-mobile-batch/{uid}/digest/audio.bin',
                f'audio/{uid}/conv/a.wav',
                f'merged/{uid}/conv/a.wav',
                f'playback/{uid}/conv/a.mp3',
                'chunks/other/keep.opus',
            }
        ),
        'sync': _Bucket({f'syncing/{uid}/job/input.bin', 'syncing/other/job/input.bin'}),
        'chat': _Bucket({f'{uid}/chat.txt', 'other/chat.txt'}),
    }
    monkeypatch.setattr(storage_mod, 'speech_profiles_bucket', 'speech')
    monkeypatch.setattr(storage_mod, 'private_cloud_sync_bucket', 'private')
    monkeypatch.setattr(storage_mod, 'syncing_local_bucket', 'sync')
    monkeypatch.setattr(storage_mod, 'chat_files_bucket', 'chat')
    monkeypatch.setattr(storage_mod, '_get_storage_client', lambda: _Client(buckets))

    deleted = storage_mod.delete_all_user_storage_objects(uid)

    assert deleted == 8
    assert buckets['speech'].names == {'other/speech.wav'}
    assert buckets['private'].names == {'chunks/other/keep.opus'}
    assert buckets['sync'].names == {'syncing/other/job/input.bin'}
    assert buckets['chat'].names == {'other/chat.txt'}


def test_owner_prefix_purge_removes_diagnostic_ticket_lookup(monkeypatch):
    ticket = 'ABCDEF123456'
    bucket = _Bucket(
        {
            f'diagnostics/uid1/{ticket}.json',
            f'diagnostics/tickets/{ticket}.json',
            'diagnostics/other/keep.json',
        }
    )
    monkeypatch.setattr(storage_mod, 'speech_profiles_bucket', None)
    monkeypatch.setattr(storage_mod, 'private_cloud_sync_bucket', 'private')
    monkeypatch.setattr(storage_mod, 'syncing_local_bucket', None)
    monkeypatch.setattr(storage_mod, 'chat_files_bucket', None)
    monkeypatch.setattr(storage_mod, '_get_storage_client', lambda: _Client({'private': bucket}))

    assert storage_mod.delete_all_user_storage_objects('uid1') == 2
    assert bucket.names == {'diagnostics/other/keep.json'}


def test_account_purge_releases_approved_hold_before_generation_bound_delete(monkeypatch):
    calls = []
    blob = SimpleNamespace(temporary_hold=True, generation=123, metageneration=2)
    bucket = SimpleNamespace(name='syncing-local')
    bucket.list_blobs = MagicMock(side_effect=[[blob], []])
    monkeypatch.setattr(storage_mod, '_uses_real_gcs_bucket', lambda value: True)

    def release(uid, held_blob):
        assert uid == 'uid1' and held_blob is blob
        calls.append('release')
        blob.temporary_hold = False
        blob.metageneration = 3

    def delete(**kwargs):
        assert blob.temporary_hold is False
        assert kwargs == {'if_generation_match': 123, 'if_metageneration_match': 3}
        calls.append('delete')

    blob.delete = delete
    monkeypatch.setattr(account_deletion_operational_holds, 'release_operational_hold_for_account_deletion', release)
    assert storage_mod._delete_owner_bucket_prefix(bucket, 'syncing/uid1/', account_deletion_uid='uid1') == 1
    assert calls == ['release', 'delete']


def test_account_purge_keeps_required_failure_when_hold_is_unapproved(monkeypatch):
    blob = SimpleNamespace(temporary_hold=True, delete=MagicMock())
    bucket = SimpleNamespace(name='syncing-local', list_blobs=MagicMock(return_value=[blob]))
    monkeypatch.setattr(
        account_deletion_operational_holds,
        'release_operational_hold_for_account_deletion',
        MagicMock(side_effect=RuntimeError('unapproved hold')),
    )
    with pytest.raises(RuntimeError, match='unapproved hold'):
        storage_mod._delete_owner_bucket_prefix(bucket, 'syncing/uid1/', account_deletion_uid='uid1')
    blob.delete.assert_not_called()


def test_frame_prefix_purge_covers_both_tiers(monkeypatch):
    uid = 'uid1'
    temporary = _Bucket({f'frame-requests/{uid}/temporary', 'frame-requests/other/keep'})
    permanent = _Bucket({f'frame-requests/{uid}/permanent', 'frame-requests/other/keep'})
    client = _Client({'temporary': temporary, 'permanent': permanent})
    monkeypatch.setenv('BUCKET_FRAME_REQUESTS_TEMPORARY', 'temporary')
    monkeypatch.setenv('BUCKET_FRAME_REQUESTS', 'permanent')
    monkeypatch.setattr(frame_request_storage, '_get_storage_client', lambda: client)

    deleted = frame_request_storage.delete_all_frame_request_pixels_for_user(uid)

    assert deleted == 2
    assert temporary.names == {'frame-requests/other/keep'}
    assert permanent.names == {'frame-requests/other/keep'}


def test_real_gcs_owner_write_is_blocked_before_mutation(monkeypatch):
    bucket = _Bucket(set())
    blob = bucket.blob('uid1/recording.wav')
    client = _Client({'recordings': bucket})
    monkeypatch.setattr(storage_mod, '_get_storage_client', lambda: client)
    monkeypatch.setattr(storage_mod, 'memories_recordings_bucket', 'recordings')
    monkeypatch.setattr(storage_mod, '_uses_real_gcs_bucket', lambda value: True)

    @contextmanager
    def blocked_gate(uid, *, firestore_client=None):
        raise RuntimeError('account deletion owns gate')
        yield  # pragma: no cover

    monkeypatch.setattr(storage_mod, 'external_write_fence', blocked_gate)
    upload = MagicMock()
    monkeypatch.setattr(blob, 'upload_from_filename', upload, raising=False)
    monkeypatch.setattr(bucket, 'blob', lambda name: blob)

    with pytest.raises(RuntimeError, match='owns gate'):
        storage_mod.upload_conversation_recording('/tmp/audio.wav', 'uid1', 'conv1')
    upload.assert_not_called()


def test_local_owner_write_keeps_offline_fake_provider_behavior(monkeypatch):
    bucket = _Bucket(set())
    client = _Client({'recordings': bucket})
    monkeypatch.setattr(storage_mod, '_get_storage_client', lambda: client)
    monkeypatch.setattr(storage_mod, 'memories_recordings_bucket', 'recordings')
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    blob = bucket.blob('uid1/conv1.wav')
    upload = MagicMock()
    monkeypatch.setattr(blob, 'upload_from_filename', upload, raising=False)
    monkeypatch.setattr(bucket, 'blob', lambda name: blob)

    storage_mod.upload_conversation_recording('/tmp/audio.wav', 'uid1', 'conv1')

    upload.assert_called_once_with('/tmp/audio.wav')


def test_uid_scoped_temporary_sync_upload_is_fenced(monkeypatch):
    bucket = _Bucket(set())
    client = _Client({'sync': bucket})
    blob = bucket.blob('syncing/uid1/job/input.bin')
    upload = MagicMock()
    monkeypatch.setattr(blob, 'upload_from_filename', upload, raising=False)
    monkeypatch.setattr(bucket, 'blob', lambda name: blob)
    monkeypatch.setattr(storage_mod, '_get_storage_client', lambda: client)
    monkeypatch.setattr(storage_mod, 'syncing_local_bucket', 'sync')
    monkeypatch.setattr(storage_mod, '_uses_real_gcs_bucket', lambda value: True)

    @contextmanager
    def blocked_gate(uid, *, firestore_client=None):
        raise RuntimeError('account deletion owns gate')
        yield  # pragma: no cover

    monkeypatch.setattr(storage_mod, 'external_write_fence', blocked_gate)

    with pytest.raises(RuntimeError, match='owns gate'):
        storage_mod.upload_syncing_temporal_file('syncing/uid1/job/input.bin')
    upload.assert_not_called()


def test_account_wipe_removes_packs_intents_and_receipts_with_flag_off(monkeypatch):
    prefixes = (
        storage_mod.audio_packs.SOURCE_PREFIX,
        storage_mod.audio_packs.PACK_PREFIX,
        storage_mod.audio_packs.INDEX_PREFIX,
    )
    names = {f'{p}uid1/day/object' for p in prefixes}
    names.add(f'{storage_mod.audio_packs.INDEX_PREFIX}uid1/captures/receipt.json')
    other = {f'{p}other/day/object' for p in prefixes}
    canonical = _Bucket(names | other)
    monkeypatch.setenv('AUDIO_CANONICAL_PACKING_ENABLED', 'false')
    monkeypatch.setenv('BUCKET_CANONICAL_AUDIO', 'canonical')
    monkeypatch.setattr(storage_mod, 'speech_profiles_bucket', None)
    monkeypatch.setattr(storage_mod, 'private_cloud_sync_bucket', 'private')
    monkeypatch.setattr(storage_mod, 'syncing_local_bucket', None)
    monkeypatch.setattr(storage_mod, 'chat_files_bucket', None)
    monkeypatch.setattr(
        storage_mod, '_get_storage_client', lambda: _Client({'canonical': canonical, 'private': _Bucket(set())})
    )
    assert storage_mod.delete_all_user_storage_objects('uid1') == 4
    assert canonical.names == other


def test_canonical_bucket_rejects_retained_generations(monkeypatch):
    bucket = _Bucket(set())
    monkeypatch.setenv('BUCKET_CANONICAL_AUDIO', 'canonical')
    monkeypatch.setattr(storage_mod, '_get_storage_client', lambda: _Client({'canonical': bucket}))
    bucket.versioning_enabled = True
    with pytest.raises(RuntimeError, match='versioning off'):
        storage_mod.get_canonical_audio_bucket()
    bucket.versioning_enabled = False
    bucket.soft_delete_policy.retention_duration_seconds = 604800
    with pytest.raises(RuntimeError, match='soft delete off'):
        storage_mod.get_canonical_audio_bucket()


def test_merge_cleanup_preserves_canonical_and_explicit_privacy_calls_erase(monkeypatch):
    monkeypatch.setenv('BUCKET_CANONICAL_AUDIO', 'canonical')
    private = _Bucket(set())
    monkeypatch.setattr(storage_mod, '_get_storage_client', lambda: _Client({'private': private}))
    monkeypatch.setattr(storage_mod, 'private_cloud_sync_bucket', 'private')
    erased = MagicMock()
    linked = MagicMock()
    monkeypatch.setattr(storage_mod.audio_packs, 'delete_conversation', erased)
    monkeypatch.setattr(storage_mod.audio_packs, 'link_conversations', linked)
    monkeypatch.setattr(storage_mod, 'get_canonical_audio_bucket', lambda: private)

    @contextmanager
    def gate(*args, **kwargs):
        yield

    monkeypatch.setattr(storage_mod, 'destructive_operation_gate', gate)
    storage_mod.delete_conversation_audio_files('u', 'c')
    erased.assert_not_called()
    storage_mod.delete_conversation_audio_files('u', 'c', merged_into='merged')
    linked.assert_called_once_with(private, 'u', ['c'], 'merged')
    erased.assert_not_called()
    storage_mod.delete_privacy_conversation_audio('u', 'merged')
    erased.assert_called_once_with(private, 'u', 'merged')


def test_conversation_purge_attempts_other_prefixes_when_some_generations_are_protected(monkeypatch):
    protected = {'chunks/u/c/held', 'raw-live/u/c/held'}
    other = 'playback/u/c/deletable'
    wal = 'record-wal/u/c/original'
    private = _Bucket(protected | {other, wal})
    private.name = 'private'
    delete = _Blob.delete

    def delete_with_hold(blob):
        if blob.name in protected:
            raise Forbidden('protected', errors=[{'reason': 'objectUnderActiveHold'}])
        delete(blob)

    monkeypatch.setattr(storage_mod, '_get_storage_client', lambda: _Client({'private': private}))
    monkeypatch.setattr(storage_mod, 'private_cloud_sync_bucket', 'private')
    monkeypatch.delenv('BUCKET_AUDIO_DERIVED', raising=False)
    monkeypatch.delenv('BUCKET_CANONICAL_AUDIO', raising=False)
    monkeypatch.setattr(_Blob, 'generation', 1, raising=False)
    monkeypatch.setattr(_Blob, 'delete', delete_with_hold)

    for _ in range(2):
        with pytest.raises(account_deletion_operational_holds.StoragePrefixPurgeBlocked) as error:
            storage_mod.delete_privacy_conversation_audio('u', 'c')
        assert error.value.objects == {('private', name, 1): 'objectUnderActiveHold' for name in protected}
        assert private.names == protected | {wal}


def _prepare_playback(monkeypatch):
    private = _Bucket(set())
    monkeypatch.setattr(storage_mod, '_get_storage_client', lambda: _Client({'private': private}))
    monkeypatch.setattr(storage_mod, 'private_cloud_sync_bucket', 'private')

    @contextmanager
    def gate(*args, **kwargs):
        yield

    monkeypatch.setattr(storage_mod, 'owner_storage_write_gate', gate)
    return private


def test_canonical_bucket_policy_cached_until_expiry(monkeypatch):
    bucket = _Bucket(set())
    bucket.reload = MagicMock()
    client = _Client({'canonical': bucket})
    monkeypatch.setenv('BUCKET_CANONICAL_AUDIO', 'canonical')
    monkeypatch.setattr(storage_mod, '_get_storage_client', lambda: client)
    monkeypatch.setattr(storage_mod, '_canonical_bucket_cache', None)
    now = [100]
    monkeypatch.setattr(storage_mod.time, 'monotonic', lambda: now[0])
    assert storage_mod.get_canonical_audio_bucket() is bucket
    assert storage_mod.get_canonical_audio_bucket() is bucket
    bucket.reload.assert_called_once()
    now[0] += 301
    storage_mod.get_canonical_audio_bucket()
    assert bucket.reload.call_count == 2


def test_privacy_erases_snapshotted_bridge_donors_only_at_explicit_boundary(monkeypatch):
    private = _prepare_playback(monkeypatch)
    monkeypatch.setenv('BUCKET_CANONICAL_AUDIO', 'canonical')
    monkeypatch.setattr(storage_mod, 'get_canonical_audio_bucket', lambda: private)
    erased = MagicMock()
    monkeypatch.setattr(storage_mod.audio_packs, 'delete_conversation', erased)

    @contextmanager
    def gate(*args, **kwargs):
        yield

    monkeypatch.setattr(storage_mod, 'destructive_operation_gate', gate)
    storage_mod.delete_privacy_conversation_audio('u', 'survivor', source_ids=['donor', 'donor'])
    assert erased.call_count == 2
    assert {call.args for call in erased.call_args_list} == {(private, 'u', 'survivor'), (private, 'u', 'donor')}


def _staging_buckets(monkeypatch, jobs, *, shared_live=(), in_flight=()):
    private = _Bucket({'chunks/u/c/a.bin', 'chunks/u/donor/b.bin', 'chunks/u/other/c.bin'})
    syncing = _Bucket({'syncing/u/job-a/1.bin', 'syncing/u/job-a/seg_1.wav', 'syncing/u/job-other/2.bin'})
    syncing.names.add('syncing/stranger/job-a/3.bin')
    derived = _Bucket({'syncing/u/job-a/4.bin', 'chunks/u/c/d.bin'})
    for name, bucket in (('private', private), ('syncing', syncing), ('derived', derived)):
        bucket.name = name
    monkeypatch.setattr(
        storage_mod,
        '_get_storage_client',
        lambda: _Client({'private': private, 'syncing': syncing, 'derived': derived}),
    )
    monkeypatch.setattr(storage_mod, 'private_cloud_sync_bucket', 'private')
    monkeypatch.setattr(storage_mod, 'syncing_local_bucket', 'syncing')
    monkeypatch.setenv('BUCKET_AUDIO_DERIVED', 'derived')
    monkeypatch.delenv('BUCKET_CANONICAL_AUDIO', raising=False)
    looked_up = []

    from database.sync_ledger_sources import StagingPlan

    def lookup(uid, conversation_ids, **kwargs):
        looked_up.append((uid, list(conversation_ids), *([kwargs['recorded']] if kwargs.get('recorded') else [])))
        return StagingPlan(erasable=tuple(jobs), shared_live=tuple(shared_live), in_flight=tuple(in_flight))

    monkeypatch.setattr('database.sync_ledger_sources.staging_plan', lookup)
    return private, syncing, derived, looked_up


def test_privacy_delete_erases_sync_staging_and_donor_prefixes(monkeypatch):
    private, syncing, derived, looked_up = _staging_buckets(monkeypatch, ['job-a'])
    storage_mod.delete_privacy_conversation_audio('u', 'c', source_ids=['donor'])
    assert looked_up == [('u', ['c', 'donor'])]
    assert private.names == {'chunks/u/other/c.bin'}
    # Only this owner's staging for the upload that fed the conversation goes.
    assert syncing.names == {'syncing/u/job-other/2.bin', 'syncing/stranger/job-a/3.bin'}
    assert derived.names == set()


def test_held_sync_staging_is_kept_and_reported_after_every_prefix_is_tried(monkeypatch):
    private, syncing, derived, _ = _staging_buckets(monkeypatch, ['job-a'])
    held = 'syncing/u/job-a/1.bin'
    delete = _Blob.delete

    def delete_with_hold(blob):
        if blob.name == held:
            raise Forbidden('held', errors=[{'reason': 'objectUnderActiveHold'}])
        delete(blob)

    monkeypatch.setattr(_Blob, 'generation', 1, raising=False)
    monkeypatch.setattr(_Blob, 'delete', delete_with_hold)
    with pytest.raises(account_deletion_operational_holds.StoragePrefixPurgeBlocked) as error:
        storage_mod.delete_privacy_conversation_audio('u', 'c')
    assert error.value.objects == {('syncing', held, 1): 'objectUnderActiveHold'}
    assert syncing.names == {held, 'syncing/u/job-other/2.bin', 'syncing/stranger/job-a/3.bin'}
    assert derived.names == set()
    assert 'chunks/u/c/a.bin' not in private.names


def test_no_ledger_upload_leaves_staging_untouched(monkeypatch):
    _private, syncing, _derived, _ = _staging_buckets(monkeypatch, [])
    before = set(syncing.names)
    assert storage_mod.delete_conversation_sync_staging('u', ['c']) == 0
    assert syncing.names == before


def test_staging_a_live_sibling_still_needs_is_kept(monkeypatch):
    _private, syncing, derived, _ = _staging_buckets(monkeypatch, [], shared_live=['job-a'])
    before_syncing = set(syncing.names)
    storage_mod.delete_privacy_conversation_audio('u', 'c', strict_staging=True)
    assert syncing.names == before_syncing
    # The conversation's own prefix goes; the shared upload's staging stays in both buckets.
    assert derived.names == {'syncing/u/job-a/4.bin'}


def test_unfinished_upload_staging_is_kept_and_raised_only_for_the_durable_runner(monkeypatch):
    from database.sync_ledger_sources import StagingInFlight

    private, syncing, _derived, _ = _staging_buckets(monkeypatch, ['job-other'], in_flight=['job-a'])
    storage_mod.delete_privacy_conversation_audio('u', 'c')
    assert 'syncing/u/job-a/1.bin' in syncing.names
    with pytest.raises(StagingInFlight):
        storage_mod.delete_privacy_conversation_audio('u', 'c', strict_staging=True)
    # Every other step still ran: the conversation prefix and the erasable upload are gone.
    assert 'chunks/u/c/a.bin' not in private.names
    assert 'syncing/u/job-other/2.bin' not in syncing.names
    assert 'syncing/u/job-a/1.bin' in syncing.names


def test_durable_audio_erasure_runs_every_step_under_the_audio_gate(monkeypatch):
    gates = []

    @contextmanager
    def gate(uid, *, kind, wait_seconds=0.0, **kwargs):
        gates.append((uid, kind, wait_seconds))
        yield 'token'

    erased = []
    monkeypatch.setattr(storage_mod, 'destructive_operation_gate', gate)
    monkeypatch.setattr(
        storage_mod,
        'delete_privacy_conversation_audio',
        lambda uid, cid, *, source_ids, strict_staging, recorded_staging, settled_staging: erased.append(
            (uid, cid, source_ids, strict_staging, len(gates))
        )
        or {'shared_live': 0},
    )
    assert storage_mod.erase_conversation_audio('u', 'c', ['donor'], staging={'job-a': ['c']}) == {'shared_live': 0}
    assert gates == [('u', 'audio_conversation_deletion', storage_mod.CONVERSATION_AUDIO_ERASURE_GATE_WAIT_SECONDS)]
    assert erased == [('u', 'c', ['donor'], True, 1)]


def test_recorded_staging_reaches_the_plan_on_the_durable_path(monkeypatch):
    _private, syncing, _derived, looked_up = _staging_buckets(monkeypatch, ['job-a'])
    storage_mod.delete_privacy_conversation_audio('u', 'c', strict_staging=True, recorded_staging={'job-a': ['c']})
    assert looked_up == [('u', ['c'], {'job-a': ['c']})]
    assert not any(name.startswith('syncing/u/job-a/') for name in syncing.names)


def test_held_canonical_pack_is_reported_as_a_blocked_object_and_other_steps_run(monkeypatch):
    private, syncing, _derived, _ = _staging_buckets(monkeypatch, ['job-a'])
    canonical = SimpleNamespace(name='canonical')
    monkeypatch.setenv('BUCKET_CANONICAL_AUDIO', 'canonical')
    monkeypatch.setattr(storage_mod, 'get_canonical_audio_bucket', lambda: canonical)

    def held_pack(bucket, uid, cid):
        raise Forbidden('held', errors=[{'reason': 'objectUnderActiveHold'}])

    monkeypatch.setattr(storage_mod.audio_packs, 'delete_conversation', held_pack)

    @contextmanager
    def gate(*args, **kwargs):
        yield

    monkeypatch.setattr(storage_mod, 'destructive_operation_gate', gate)
    with pytest.raises(account_deletion_operational_holds.StoragePrefixPurgeBlocked) as error:
        storage_mod.delete_privacy_conversation_audio('u', 'c', strict_staging=True)
    pack = storage_mod.audio_packs.owner_prefix(storage_mod.audio_packs.PACK_PREFIX, 'u') + 'c'
    assert error.value.objects == {('canonical', pack, 0): 'objectUnderActiveHold'}
    # The held pack did not stop the conversation prefix or the staging purge.
    assert 'chunks/u/c/a.bin' not in private.names
    assert not any(name.startswith('syncing/u/job-a/') for name in syncing.names)


def test_non_hold_canonical_failure_still_raises(monkeypatch):
    _staging_buckets(monkeypatch, [])
    monkeypatch.setenv('BUCKET_CANONICAL_AUDIO', 'canonical')
    monkeypatch.setattr(storage_mod, 'get_canonical_audio_bucket', lambda: SimpleNamespace(name='canonical'))

    def denied(bucket, uid, cid):
        raise Forbidden('denied', errors=[{'reason': 'insufficientPermissions'}])

    monkeypatch.setattr(storage_mod.audio_packs, 'delete_conversation', denied)

    @contextmanager
    def gate(*args, **kwargs):
        yield

    monkeypatch.setattr(storage_mod, 'destructive_operation_gate', gate)
    with pytest.raises(Forbidden):
        storage_mod.delete_privacy_conversation_audio('u', 'c')


def test_best_effort_audio_sweep_holds_the_audio_gate_and_a_hold_stops_it(monkeypatch):
    from database.legal_holds import LegalHoldActive

    gates = []
    swept = MagicMock(return_value={'shared_live': 0})
    monkeypatch.setattr(storage_mod, 'delete_privacy_conversation_audio', swept)

    @contextmanager
    def gate(uid, *, kind, wait_seconds=0.0, **kwargs):
        gates.append((uid, kind))
        yield 'token'

    monkeypatch.setattr(storage_mod, 'destructive_operation_gate', gate)
    storage_mod.delete_conversation_audio_under_gate('u', 'c', source_ids=['donor'])
    assert gates == [('u', 'audio_conversation_deletion')]
    swept.assert_called_once_with('u', 'c', source_ids=['donor'])

    @contextmanager
    def held(uid, **kwargs):
        raise LegalHoldActive('held')
        yield  # pragma: no cover

    swept.reset_mock()
    monkeypatch.setattr(storage_mod, 'destructive_operation_gate', held)
    with pytest.raises(LegalHoldActive):
        storage_mod.delete_conversation_audio_under_gate('u', 'c')
    swept.assert_not_called()
