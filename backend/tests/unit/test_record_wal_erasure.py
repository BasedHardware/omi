"""New originals participate in existing account/conversation privacy erasure."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import PreconditionFailed

from tests.unit.test_owner_storage_purge_and_gate import _Bucket, _Client
from utils.other import storage
from utils.other.local_storage import LocalStorageClient
from utils.batch_pipeline import record_wal_erasure
from utils.batch_pipeline.retention import delete_batch_object, purge_batch_storage_owner
from scripts import retention_contract


def test_conversation_erasure_removes_originals_in_every_relevant_bucket(monkeypatch):
    buckets = {
        name: _Bucket({'record-wal/synthetic/record/a.enc', 'record-wal/synthetic/other/keep.enc'})
        for name in ('private', 'derived')
    }
    monkeypatch.setattr(storage, '_get_storage_client', lambda: _Client(buckets))
    monkeypatch.setattr(storage, 'private_cloud_sync_bucket', 'private')
    monkeypatch.setenv('BUCKET_AUDIO_DERIVED', 'derived')
    monkeypatch.delenv('BUCKET_CANONICAL_AUDIO', raising=False)
    monkeypatch.setattr(storage, 'invalidate_pack_index', lambda *_: None)
    storage.delete_conversation_audio_files('synthetic', 'record')
    assert all(bucket.names == {'record-wal/synthetic/other/keep.enc'} for bucket in buckets.values())


def test_conversation_wal_erasure_still_aborts_on_a_stale_generation(monkeypatch):
    failure = PreconditionFailed('stale WAL generation', errors=[{'reason': 'conditionNotMet'}])
    first = SimpleNamespace(generation=1, metageneration=2, delete=Mock(side_effect=failure))
    second = SimpleNamespace(generation=3, metageneration=4, delete=Mock())
    list_blobs = Mock(
        side_effect=lambda *, prefix, versions: [first, second] if prefix == 'record-wal/synthetic/record/' else []
    )
    bucket = SimpleNamespace(name='private', list_blobs=list_blobs)
    monkeypatch.setattr(storage, '_get_storage_client', lambda: _Client({'private': bucket}))
    monkeypatch.setattr(storage, '_uses_real_gcs_bucket', lambda _: True)
    monkeypatch.setattr(storage, 'private_cloud_sync_bucket', 'private')
    monkeypatch.delenv('BUCKET_AUDIO_DERIVED', raising=False)
    monkeypatch.delenv('BUCKET_CANONICAL_AUDIO', raising=False)

    with pytest.raises(PreconditionFailed, match='stale WAL generation'):
        storage.delete_privacy_conversation_audio('synthetic', 'record')

    first.delete.assert_called_once_with(if_generation_match=1, if_metageneration_match=2)
    second.delete.assert_not_called()
    list_blobs.assert_called_with(prefix='record-wal/synthetic/record/', versions=True)


def test_account_erasure_discovers_pre_receipt_crash_orphans(monkeypatch, tmp_path):
    client = LocalStorageClient(tmp_path)
    bucket = client.bucket('private')
    bucket.blob('record-wal/synthetic/record/orphan.enc').upload_from_string(b'synthetic orphan')
    bucket.blob('record-wal/other/record/keep.enc').upload_from_string(b'synthetic other owner')
    monkeypatch.setenv('BUCKET_PRIVATE_CLOUD_SYNC', 'private')
    monkeypatch.setattr(record_wal_erasure, 'create_storage_client', lambda: client)
    monkeypatch.delenv('BUCKET_BATCH_PIPELINE', raising=False)
    purge_batch_storage_owner('synthetic', 'batch_pipeline_dev', wal_originals=True)
    assert [blob.name for blob in bucket.list_blobs(prefix='record-wal/')] == ['record-wal/other/record/keep.enc']


@pytest.mark.parametrize(
    'uri',
    [
        'gs://private/record-wal/other/record/a.enc#17',
        'gs://private/record-wal/synthetic/../other/a.enc#17',
        'gs://foreign/record-wal/synthetic/record/a.enc#17',
        'gs://private/raw-live/synthetic/record/a.enc#17',
    ],
)
def test_receipt_purge_rejects_foreign_or_unrelated_objects(monkeypatch, uri):
    monkeypatch.setenv('BUCKET_PRIVATE_CLOUD_SYNC', 'private')
    monkeypatch.delenv('BUCKET_BATCH_PIPELINE', raising=False)
    monkeypatch.delenv('BUCKET_TEMPORAL_SYNC_LOCAL', raising=False)
    with pytest.raises(ValueError):
        delete_batch_object('synthetic', uri, storage_client=Mock())


def test_receipt_purge_pins_the_exact_original_generation(monkeypatch):
    monkeypatch.setenv('BUCKET_PRIVATE_CLOUD_SYNC', 'private')
    blob, bucket = Mock(), Mock()
    bucket.blob.return_value = blob
    client = SimpleNamespace(bucket=lambda name: bucket if name == 'private' else None)
    delete_batch_object('synthetic', 'gs://private/record-wal/synthetic/record/a.enc#17', storage_client=client)
    bucket.blob.assert_called_once_with('record-wal/synthetic/record/a.enc', generation=17)
    blob.delete.assert_called_once_with(if_generation_match=17)


@pytest.mark.parametrize(
    'condition',
    [
        {'age': 30},
        {'age': 30, 'matchesPrefix': ['record-wal/']},
        {'age': 30, 'matchesPrefix': ['record-wal/'], 'matchesSuffix': ['.bin.enc']},
    ],
)
def test_pending_originals_cannot_age_out_under_bucket_lifecycle(condition):
    contract = retention_contract.load()
    policy = {'rule': [{'action': {'type': 'Delete'}, 'condition': condition}]}
    assert retention_contract.floor_violations(contract, 'omi-private-cloud-sync', policy)


@pytest.mark.parametrize('bucket_name', ['private-primary', 'private-alternate'])
def test_conversation_orphan_sweep_erases_all_generations_and_only_exact_prefix(monkeypatch, bucket_name):
    rows = {
        ('record-wal/synthetic/record/receipted.enc', 1),
        ('record-wal/synthetic/record/receipted.enc', 2),
        ('record-wal/synthetic/record/crash-orphan.enc', 3),
        ('record-wal/synthetic/record-other/keep.enc', 4),
        ('record-wal/other/record/keep.enc', 5),
    }

    # Bind name in each delete callback; every generation must be removed.
    def listing(**kwargs):
        assert kwargs['versions'] is True
        return [
            SimpleNamespace(
                name=name,
                generation=generation,
                delete=lambda _name=name, **opts: rows.remove((_name, opts['if_generation_match'])),
            )
            for name, generation in list(rows)
            if name.startswith(kwargs['prefix'])
        ]

    monkeypatch.setenv('BUCKET_PRIVATE_CLOUD_SYNC', bucket_name)
    monkeypatch.setattr(
        record_wal_erasure,
        'create_storage_client',
        lambda: SimpleNamespace(
            bucket=lambda name: SimpleNamespace(list_blobs=listing) if name == bucket_name else None
        ),
    )
    page = record_wal_erasure.conversation_objects('synthetic', 'record', limit=2)
    assert len(page) == 2 and all(uri.startswith(f'gs://{bucket_name}/record-wal/synthetic/record/') for uri in page)
    record_wal_erasure.purge_record_wal_owner('synthetic', 'record')
    assert rows == {('record-wal/synthetic/record-other/keep.enc', 4), ('record-wal/other/record/keep.enc', 5)}


def test_conversation_orphan_failure_does_not_ack_erasure(monkeypatch):
    blob = SimpleNamespace(generation=17, delete=Mock(side_effect=OSError('synthetic unavailable')))
    bucket = SimpleNamespace(list_blobs=lambda **_: [blob])
    monkeypatch.setattr(record_wal_erasure, 'create_storage_client', lambda: SimpleNamespace(bucket=lambda _: bucket))
    with pytest.raises(OSError, match='synthetic unavailable'):
        record_wal_erasure.purge_record_wal_owner('synthetic', 'record')


@pytest.mark.parametrize('uid,cid', [('synthetic', '../record'), ('../synthetic', 'record'), ('synthetic', '')])
def test_orphan_sweep_rejects_unbounded_scope(uid, cid):
    with pytest.raises(ValueError):
        record_wal_erasure.purge_record_wal_owner(uid, cid)
