"""New originals participate in existing account/conversation privacy erasure."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.unit.test_owner_storage_purge_and_gate import _Bucket, _Client
from utils.other import storage
from utils.batch_pipeline.retention import delete_batch_object
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


def test_account_erasure_discovers_pre_receipt_crash_orphans(monkeypatch):
    bucket = _Bucket({'record-wal/synthetic/record/orphan.enc', 'record-wal/other/record/keep.enc'})
    monkeypatch.setattr(storage, '_get_storage_client', lambda: _Client({'private': bucket}))
    monkeypatch.setattr(storage, 'private_cloud_sync_bucket', 'private')
    storage.purge_record_wal_owner('synthetic')
    assert bucket.names == {'record-wal/other/record/keep.enc'}


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
