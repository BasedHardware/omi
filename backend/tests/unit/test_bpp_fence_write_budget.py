"""Fence token writes: no rotation for an unchanged authority field, and the batch write budget counts them."""

from types import SimpleNamespace

import pytest
from google.cloud.firestore_v1.types import Document, DocumentMask, Precondition, Write

from database import batch_privacy_write_fence as fence
from database.batch_pipeline_store import FirestoreTransaction
from database.batch_privacy_attempt import CONVERSATION_AUTHORITY_FIELDS
from utils.sync.assignment import _omit_unchanged_authority_fields

ROOT = 'projects/demo/databases/(default)/documents'
ROW = f'{ROOT}/users/u/conversations/c'


def _update(payload):
    return Write(
        update=Document(name=ROW),
        update_mask=DocumentMask(field_paths=sorted(payload)),
        current_document=Precondition(exists=True),
    )


def test_fence_and_writers_share_one_authority_field_set():
    assert fence._CONVERSATION_FIELDS is CONVERSATION_AUTHORITY_FIELDS


def test_unchanged_consent_is_omitted_and_does_not_rotate():
    current = {'private_cloud_sync_enabled': True, 'record_lane_owner': 'sync', 'title': 'old'}
    payload = {'private_cloud_sync_enabled': True, 'record_lane_owner': 'sync', 'title': 'new'}
    _omit_unchanged_authority_fields(payload, current)
    assert payload == {'title': 'new'}
    assert fence.authority_tokens([_update(payload)]) == set()


def test_changed_or_newly_explicit_authority_field_still_rotates():
    changed = {'private_cloud_sync_enabled': False, 'title': 'new'}
    _omit_unchanged_authority_fields(changed, {'private_cloud_sync_enabled': True})
    assert 'private_cloud_sync_enabled' in changed
    assert len(fence.authority_tokens([_update(changed)])) == 1

    # Absent consent means enabled, so writing an explicit value is a change.
    explicit = {'private_cloud_sync_enabled': True}
    _omit_unchanged_authority_fields(explicit, {})
    assert explicit == {'private_cloud_sync_enabled': True}
    assert len(fence.authority_tokens([_update(explicit)])) == 1


class _Collection:
    def document(self, key):
        return SimpleNamespace(collection=lambda name: _Collection(), path=key)


def _store(writes: int, owners: list[str]):
    transaction = SimpleNamespace(set=lambda ref, value: None, update=lambda ref, fields: None)
    store = FirestoreTransaction(SimpleNamespace(collection=lambda name: _Collection()), 'bp', transaction)
    store.writes = {('meta', f'k{i}'): {} for i in range(writes)}
    store.patches = {('conversations', f'{uid}/c{i}'): {'record_lane_owner': 'batch'} for i, uid in enumerate(owners)}
    return store


def test_write_budget_counts_one_fence_token_per_patched_owner():
    # 447 writes + 2 patches + 1 token (one owner) = 450: fits.
    _store(447, ['u1', 'u1']).flush()
    # 447 writes + 2 patches + 2 tokens (two owners) = 451: over budget.
    with pytest.raises(RuntimeError, match='write budget'):
        _store(447, ['u1', 'u2']).flush()
