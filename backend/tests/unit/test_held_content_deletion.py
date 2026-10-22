"""Hermetic held-custody deletion: real cleanup code, injected storage/DB boundaries."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import NotFound

from database import batch_pipeline_purge, user_data_deletion
from utils.other import storage
from utils.sync import cap_hold_recovery as recovery
from utils.sync.cap_hold_erasure import terminal_receipts


@pytest.fixture
def artifacts(monkeypatch):
    prefix = 'chunks/synthetic/cap-held/'
    row = {
        'audio_path': prefix + 'source.enc',
        'metadata_path': prefix + 'metadata.enc',
        'audio_parts': [prefix + 'legacy-part.enc'],
        'stage_parts': [{'id': 'fragment', 'audio_path': prefix + 'fragment.enc'}],
        'piece_plan': {'piece': {'audio_path': prefix + 'frozen.enc', 'metadata_path': prefix + 'context.enc'}},
    }
    paths = {prefix + name + '.enc' for name in ('source', 'metadata', 'legacy-part', 'fragment', 'frozen', 'context')}
    objects = set(paths)
    fault = SimpleNamespace(path=None)

    def blob(path):
        def delete():
            if path == fault.path:
                raise RuntimeError('synthetic storage unavailable')
            if path not in objects:
                raise NotFound('synthetic missing object')
            objects.remove(path)

        return SimpleNamespace(delete=delete)

    monkeypatch.setattr(recovery.cap_hold, 'get_private_cloud_sync_bucket', lambda: SimpleNamespace(blob=blob))
    reference = Mock()
    reference.get.return_value.to_dict.side_effect = lambda: dict(row)
    snapshot = SimpleNamespace(reference=reference)
    return row, paths, objects, fault, snapshot


@pytest.mark.parametrize('version', [3, 4])
def test_erasure_removes_source_fragments_frozen_pieces_and_sidecars_before_manifest(artifacts, version):
    row, paths, objects, fault, snapshot = artifacts
    row['live_custody_version'] = version
    recovery._erase('synthetic', snapshot, row)
    assert not objects
    if version == 4:
        snapshot.reference.delete.assert_not_called()
        snapshot.reference.set.assert_called_once_with(
            {
                'state': 'purged',
                'live_custody_version': 4,
                'terminal_receipts': terminal_receipts(row),
                'stage_fragment_ids': ['fragment'],
                'next_attempt_at': recovery.cap_hold.RETAINED_NEXT_ATTEMPT_AT,
            }
        )
    else:
        snapshot.reference.delete.assert_called_once_with()
        snapshot.reference.set.assert_not_called()
    # Repeating after a lost cleanup reply tolerates already removed objects.
    recovery._erase('synthetic', snapshot, row)
    assert not objects


def test_erasure_failure_retains_manifest_and_retry_removes_remaining_objects(artifacts):
    row, paths, objects, fault, snapshot = artifacts
    fault.path = row['metadata_path']
    with pytest.raises(RuntimeError, match='storage unavailable'):
        recovery._erase('synthetic', snapshot, row)
    snapshot.reference.delete.assert_not_called()
    snapshot.reference.set.assert_not_called()
    assert fault.path in objects
    fault.path = None
    recovery._erase('synthetic', snapshot, row)
    assert not objects
    snapshot.reference.delete.assert_called_once_with()


def test_erasure_never_deletes_another_owners_object(artifacts):
    row, paths, objects, fault, snapshot = artifacts
    row['piece_plan']['foreign'] = {'audio_path': 'chunks/other/cap-held/foreign.enc'}
    objects.add('chunks/other/cap-held/foreign.enc')
    with pytest.raises(ValueError, match='owner mismatch'):
        recovery._erase('synthetic', snapshot, row)
    assert 'chunks/other/cap-held/foreign.enc' in objects
    snapshot.reference.delete.assert_not_called()
    snapshot.reference.set.assert_not_called()


def test_account_storage_purge_covers_held_orphans_and_preserves_neighbour(monkeypatch):
    # Exercise cloud-prefix selection with an injected bucket, never a cloud client.
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.delenv('PROVIDER_MODE', raising=False)
    for name in ('BUCKET_CANONICAL_AUDIO', 'BUCKET_AUDIO_DERIVED'):
        monkeypatch.delenv(name, raising=False)
    for name in ('speech_profiles_bucket', 'syncing_local_bucket', 'chat_files_bucket'):
        monkeypatch.setattr(storage, name, None)
    monkeypatch.setattr(storage, 'private_cloud_sync_bucket', 'synthetic-private')
    objects = {
        'chunks/synthetic/cap-held/source.enc',
        'chunks/synthetic/cap-held/orphan-fragment.enc',
        'chunks/synthetic/cap-held/frozen-piece.enc',
        'chunks/synthetic-other/cap-held/keep.enc',
    }

    def listing(*, prefix, **kwargs):
        return [
            SimpleNamespace(name=path, delete=lambda path=path: objects.remove(path))
            for path in sorted(objects)
            if path.startswith(prefix)
        ]

    bucket = SimpleNamespace(list_blobs=listing)
    monkeypatch.setattr(storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: bucket))
    assert storage.delete_all_user_storage_objects('synthetic') == 3
    assert objects == {'chunks/synthetic-other/cap-held/keep.enc'}
    assert storage.delete_all_user_storage_objects('synthetic') == 0


@pytest.mark.parametrize('root_exists', [False, True])
def test_account_wipe_enumerates_custody_and_choice_subcollections_even_without_root(monkeypatch, root_exists):
    names = ['stt_cap_holds', 'stt_cap_hold_summary', 'processing_backlog', 'budget_choice']
    subcollections = [SimpleNamespace(id=name) for name in names]
    user = Mock()
    user.get.return_value.exists = root_exists
    user.collections.return_value = subcollections
    client = Mock()
    client.collection.return_value.document.return_value = user
    monkeypatch.setattr(batch_pipeline_purge, 'purge_batch_owner', lambda uid: None)
    monkeypatch.setattr(user_data_deletion, 'get_data_plane_firestore_client', lambda: Mock())
    recursive = Mock()
    assert user_data_deletion.purge_user_subtree('synthetic', client, recursive)['status'] == 'ok'
    assert [call.args[0].id for call in recursive.call_args_list] == names
    assert all(call.kwargs == {'client': client} for call in recursive.call_args_list)
    assert user.delete.call_count == int(root_exists)


def test_v4_purge_reads_new_ingest_proofs_and_repeated_tombstone_keeps_barrier(artifacts):
    row, _, objects, _, snapshot = artifacts
    row.update(live_custody_version=4, seconds=0.01, piece_plan={})
    current = {
        **row,
        'piece_ingests': {
            'piece': {
                'state': 'transcribed',
                'has_content': True,
                'conversation_id': 'destination',
                'seconds': 0.01,
                'attempt': 1,
                'provider': 'modulate',
            }
        },
    }
    snapshot.reference.get.return_value.to_dict.side_effect = lambda: dict(current)
    recovery._erase('synthetic', snapshot, row)
    tombstone = snapshot.reference.set.call_args.args[0]
    assert tombstone['terminal_receipts']['conversation_ids'] == ['destination']
    assert tombstone['terminal_receipts']['pieces'][0]['outcome'] == 'transcribed'
    assert tombstone['stage_fragment_ids'] == ['fragment']
    assert not any(
        key in tombstone for key in ('audio_path', 'metadata_path', 'metadata', 'piece_ingests', 'piece_plan')
    )
    current.clear()
    current.update(tombstone)
    recovery._erase('synthetic', snapshot, tombstone)
    assert snapshot.reference.set.call_args.args[0] == tombstone
