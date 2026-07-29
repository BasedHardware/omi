"""Tests for Developer API key memory grant seeding/removal (PR #8429 P2 fix).

Addresses Codex P2 feedback: freshly created Developer API keys with
memories:read/memories:write scopes must seed the matching app/key memory
grant so the grant gate does not reject them with missing_app_key_scope_grant.

These tests verify the pure grant-write helpers directly against the neutral
storage port (``_store()`` seam), asserting on stored state rather than
Firestore call mechanics.
"""

import database.memory_app_key_grants as memory_app_key_grants
from database.memory_app_key_grants import (
    APP_KEY_MEMORY_GRANT_SUBPATH,
    build_app_key_scope_grant_contract_state,
    remove_developer_api_key_memory_grant,
    seed_developer_api_key_memory_grant,
)
from tests.store_fakes import FakeDocumentStore
from utils.memory.product_authorization import (
    MemoryGrantOperation,
    ProductAuthorizationContext,
    authorize_app_key_scope_memory_grant,
)


def _patch_store(monkeypatch):
    store = FakeDocumentStore()
    monkeypatch.setattr(memory_app_key_grants, '_store', lambda: store)
    return store


def _grant_keys(store, uid='uid1'):
    doc = store.get(f'users/{uid}/{APP_KEY_MEMORY_GRANT_SUBPATH}').to_dict()
    return doc['grants']['developer_api']['apps']['developer_api']['keys']


def test_seed_read_only_grant_writes_default_read_contract(monkeypatch):
    store = _patch_store(monkeypatch)
    path = seed_developer_api_key_memory_grant('uid1', 'key1', default_read=True, write=False)

    expected_doc = f'users/uid1/{APP_KEY_MEMORY_GRANT_SUBPATH}'
    assert path == expected_doc

    written_data = store.get(expected_doc).to_dict()
    expected = build_app_key_scope_grant_contract_state(
        consumer='developer_api',
        app_id='developer_api',
        key_id='key1',
        scopes=['memories.read'],
        default_read=True,
    )
    assert written_data == expected


def test_seed_write_grant_includes_write_scope_and_flag(monkeypatch):
    store = _patch_store(monkeypatch)
    seed_developer_api_key_memory_grant('uid1', 'key2', default_read=True, write=True)
    grant = _grant_keys(store)['key2']
    assert grant['write'] is True
    assert 'memories.read' in grant['scopes']
    assert 'memories.write' in grant['scopes']


def test_seed_merge_preserves_existing_key_grants(monkeypatch):
    store = _patch_store(monkeypatch)
    seed_developer_api_key_memory_grant('uid1', 'key1', default_read=True)
    seed_developer_api_key_memory_grant('uid1', 'key2', default_read=True)

    keys = _grant_keys(store)
    assert 'key1' in keys
    assert 'key2' in keys


def test_seeded_grant_passes_authorization_gate(monkeypatch):
    store = _patch_store(monkeypatch)
    seed_developer_api_key_memory_grant('uid1', 'key1', default_read=True)

    state = store.get(f'users/uid1/{APP_KEY_MEMORY_GRANT_SUBPATH}').to_dict()
    context = ProductAuthorizationContext(
        uid='uid1',
        consumer='developer_api',
        surface='test',
        app_id='developer_api',
        key_id='key1',
        scopes=('memories.read',),
    )
    decision = authorize_app_key_scope_memory_grant(
        context,
        persisted_grant_state=state,
        operation=MemoryGrantOperation.DEFAULT_READ,
    )
    assert decision.allowed is True
    assert decision.reason == 'ok'


def test_remove_grant_deletes_key_entry_only(monkeypatch):
    store = _patch_store(monkeypatch)
    seed_developer_api_key_memory_grant('uid1', 'key1', default_read=True)
    seed_developer_api_key_memory_grant('uid1', 'key2', default_read=True)

    remove_developer_api_key_memory_grant('uid1', 'key1')

    keys = _grant_keys(store)
    assert 'key1' not in keys
    assert 'key2' in keys


def test_remove_grant_deletes_uuid_key_id_entry_only(monkeypatch):
    """A UUID key id (hyphenated leaf) is targeted unambiguously via a dotted key."""
    key_id = '0f6a4d1c-9b2e-4a77-8c31-2f5c9a8d7e10'
    store = _patch_store(monkeypatch)
    seed_developer_api_key_memory_grant('uid1', key_id, default_read=True)
    seed_developer_api_key_memory_grant('uid1', 'key2', default_read=True)

    remove_developer_api_key_memory_grant('uid1', key_id)

    keys = _grant_keys(store)
    assert key_id not in keys
    assert 'key2' in keys


def test_remove_grant_missing_document_is_noop(monkeypatch):
    """Legacy keys with no seeded grant document: removal is a silent no-op."""
    store = _patch_store(monkeypatch)
    remove_developer_api_key_memory_grant('uid1', 'never-seeded')
    assert store.get(f'users/uid1/{APP_KEY_MEMORY_GRANT_SUBPATH}').exists is False
