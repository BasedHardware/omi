"""D's deletion hook, storage scope and TTL declaration contracts."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from datetime import datetime, timedelta, timezone

import pytest
from google.api_core.exceptions import NotFound

from database import batch_pipeline_purge as purge, conversation_tombstones
from database.batch_pipeline_privacy import privacy_owner_key
from database.user_data_deletion import purge_user_subtree
from scripts.batch_pipeline_ttl import ttl_resources
from utils.batch_pipeline.retention import delete_batch_object, purge_batch_storage_owner


def test_pending_privacy_artifact_repairs_identity_only_after_object_erasure(monkeypatch):
    monkeypatch.setattr(purge, 'mirror_refresh', MagicMock())
    reference = MagicMock()
    snapshot = SimpleNamespace(id='receipt', reference=reference)
    pending = datetime.now(timezone.utc) + timedelta(minutes=5)
    data = {'uri': 'gs://synthetic/owned-object', 'write_pending_until': pending, 'owner_key': 'mismatched'}

    def erase(owner, uri):
        assert owner == 'synthetic-owner' and uri == data['uri']
        reference.update.assert_not_called()

    purge._erase_artifact('synthetic-owner', 'batch_pipeline_prod', snapshot, data, erase)
    update = reference.update.call_args.args[0]
    assert update['owner_id'] == 'synthetic-owner'
    assert update['owner_key'] == privacy_owner_key('synthetic-owner')
    assert update['erasure_requested'] is True and update['cleanup_after'] == pending
    assert update['expires_at'] is purge.firestore.DELETE_FIELD
    reference.delete.assert_not_called()


def test_privacy_artifact_foreign_uri_cannot_repair_or_ack_erasure(monkeypatch):
    monkeypatch.setenv('BUCKET_BATCH_PIPELINE', 'synthetic-batch')
    factory = MagicMock()
    monkeypatch.setattr('utils.other.local_storage.create_storage_client', factory)
    reference = MagicMock()
    snapshot = SimpleNamespace(id='receipt', reference=reference)
    foreign = f'gs://synthetic-batch/batch-pipeline/batch_pipeline_prod/owners/{privacy_owner_key("other")}/audio/x'
    with pytest.raises(ValueError, match='outside configured owner storage'):
        purge._erase_artifact('synthetic-owner', 'batch_pipeline_prod', snapshot, {'uri': foreign}, delete_batch_object)
    factory.assert_not_called()
    reference.update.assert_not_called()
    reference.delete.assert_not_called()


class Ref:
    def __init__(self, rows, path):
        self.rows, self.path = rows, path

    def collection(self, key):
        return Ref(self.rows, f'{self.path}/{key}')

    document = collection

    def get(self):
        data = self.rows.get(self.path)
        return SimpleNamespace(exists=data is not None, to_dict=lambda: data)

    def create(self, data):
        from google.api_core.exceptions import AlreadyExists

        if self.path in self.rows:
            raise AlreadyExists('synthetic existing tombstone')
        self.rows[self.path] = data

    def delete(self):
        self.rows.pop(self.path, None)


@pytest.mark.parametrize('retry', [False, True])
def test_tombstone_precedes_batch_cleanup_and_failure_is_retryable(monkeypatch, retry):
    rows = {'users/u/conversations/c': {'created_at': 'synthetic'}}
    if retry:
        rows['users/u/deleted_conversations/c'] = {'conversation_id': 'c', 'created_at': 'original'}
    client = SimpleNamespace(collection=lambda key: Ref(rows, key))
    monkeypatch.setattr(conversation_tombstones, 'db', client)

    def reject(uid, **kwargs):
        assert kwargs == {'conversation_id': 'c'}
        assert 'users/u/deleted_conversations/c' in rows
        raise RuntimeError('synthetic cleanup failure')

    monkeypatch.setattr('database.batch_pipeline_purge.purge_batch_owner', reject)
    with pytest.raises(RuntimeError, match='cleanup failure'):
        conversation_tombstones.record_deletion('u', 'c')
    assert rows['users/u/deleted_conversations/c']['created_at'] == ('original' if retry else 'synthetic')


def test_account_purge_stops_before_recursive_wipe_if_batch_erasure_fails(monkeypatch):
    client, recursive = MagicMock(), MagicMock()
    monkeypatch.setattr('database.batch_pipeline_purge.purge_batch_owner', MagicMock(side_effect=RuntimeError('retry')))
    with pytest.raises(RuntimeError, match='retry'):
        purge_user_subtree('synthetic', client, recursive)
    client.collection.assert_not_called()
    recursive.assert_not_called()


@pytest.mark.parametrize(
    'uri',
    [
        'https://foreign.example/result',
        'gs://foreign-bucket/syncing/u/a',
        'gs://synthetic-batch/syncing/other/a',
        'gs://synthetic-batch/syncing/u/../other/a',
    ],
)
def test_artifact_erasure_rejects_foreign_scope_without_storage_io(monkeypatch, uri):
    monkeypatch.setenv('BUCKET_BATCH_PIPELINE', 'synthetic-batch')
    factory = MagicMock()
    monkeypatch.setattr('utils.other.local_storage.create_storage_client', factory)
    with pytest.raises(ValueError, match='outside configured owner storage'):
        delete_batch_object('u', uri)
    factory.assert_not_called()


def test_artifact_erasure_pins_generation_and_missing_object_is_idempotent(monkeypatch):
    monkeypatch.setenv('BUCKET_BATCH_PIPELINE', 'synthetic-batch')
    client = MagicMock()
    monkeypatch.setattr('utils.other.local_storage.create_storage_client', lambda: client)
    path = f'batch-pipeline/batch_pipeline_prod/owners/{privacy_owner_key("u")}/results/a/object.enc'
    blob = client.bucket.return_value.blob.return_value
    blob.delete.side_effect = NotFound('synthetic missing')
    delete_batch_object('u', f'gs://synthetic-batch/{path}#42')
    client.bucket.assert_called_once_with('synthetic-batch')
    client.bucket.return_value.blob.assert_called_once_with(path, generation=42)
    blob.delete.assert_called_once_with(if_generation_match=42)


def test_owner_orphan_sweep_stays_inside_owner_namespace_and_checks_versions(monkeypatch):
    monkeypatch.setenv('BUCKET_BATCH_PIPELINE', 'synthetic-batch')
    blob = MagicMock(generation='42')
    client = MagicMock()
    client.bucket.return_value.list_blobs.side_effect = [[blob], []]
    monkeypatch.setattr('utils.other.local_storage.create_storage_client', lambda: client)
    purge_batch_storage_owner('u', 'batch_pipeline_prod')
    prefix = f'batch-pipeline/batch_pipeline_prod/owners/{privacy_owner_key("u")}/'
    client.bucket.return_value.list_blobs.assert_any_call(prefix=prefix, versions=True)
    blob.delete.assert_called_once_with(if_generation_match=42)


def test_completion_ttl_manifest_is_stage_bounded_and_has_no_privacy_authorities():
    resources = ttl_resources('demo-synthetic', 'synthetic-db')
    assert len(resources) == len(set(resources)) == 18
    assert all(resource.endswith('/fields/expires_at') for resource in resources)
    assert {resource.split('/collectionGroups/')[1].split('/')[0] for resource in resources} == {
        f'batch_pipeline_{stage}_{table}'
        for stage in ('prod', 'dev')
        for table in (
            'jobs',
            'results',
            'artifacts',
            'projections',
            'intakes',
            'shadow_jobs',
            'shadow_spend',
            'shadow_lid_probes',
            'shadow_lid_spend',
        )
    }
    with pytest.raises(ValueError):
        ttl_resources('foreign/path')


def test_account_purge_erases_cohort_membership_and_retries_failures(monkeypatch):
    client, recursive = MagicMock(), MagicMock()
    monkeypatch.setattr('database.batch_pipeline_purge.purge_batch_owner', lambda uid: None)
    data_plane = MagicMock(name='data_plane_client')
    monkeypatch.setattr('database.user_data_deletion.get_data_plane_firestore_client', lambda: data_plane)
    client.collection.return_value.document.return_value.get.return_value.exists = False
    assert purge_user_subtree('synthetic', client, recursive)['status'] == 'ok'
    data_plane.collection.assert_any_call('rollout_cohorts')
    data_plane.collection.return_value.document.return_value.delete.assert_called_once_with()
    client.collection.assert_any_call('users')
    data_plane.collection.return_value.document.return_value.delete.side_effect = RuntimeError('retry')
    with pytest.raises(RuntimeError, match='retry'):
        purge_user_subtree('synthetic', client, recursive)


def test_from_segments_ttl_policy_is_separately_reviewable_and_defaults_do_not_expand_batch_scope():
    from pathlib import Path

    policy = Path(__file__).resolve().parents[2] / 'deploy' / 'from-segments-retention.json'
    assert ttl_resources('demo-synthetic', policy_path=policy) == [
        'projects/demo-synthetic/databases/(default)/collectionGroups/from_segments_chunks/fields/expires_at'
    ]
    assert len(ttl_resources('demo-synthetic')) == 18
