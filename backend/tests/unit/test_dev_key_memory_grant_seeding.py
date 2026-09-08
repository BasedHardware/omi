"""Tests for Developer API key memory grant seeding/removal (PR #8429 P2 fix).

Addresses Codex P2 feedback: freshly created Developer API keys with
memories:read/memories:write scopes must seed the matching app/key memory
grant so the grant gate does not reject them with missing_app_key_scope_grant.

These tests verify the pure grant-write helpers directly (no Firestore/network)
using a fake db_client that supports document().set(merge=True) and .update().
"""

import types

import pytest
from google.cloud import firestore

from database.memory_app_key_grants import (
    APP_KEY_MEMORY_GRANT_SUBPATH,
    seed_developer_api_key_memory_grant,
    remove_developer_api_key_memory_grant,
    build_app_key_scope_grant_contract_state,
)
from utils.memory.product_authorization import (
    MemoryGrantOperation,
    ProductAuthorizationContext,
    authorize_app_key_scope_memory_grant,
)

# The real sentinel, so the deletion path is exercised exactly as production does.
_DELETE_SENTINEL = firestore.DELETE_FIELD


def _split_escaped_field_path(path: str) -> list[str]:
    """Split a Firestore API field path, unwrapping backtick-escaped segments.

    Mirrors the server side of ``FieldPath.to_api_repr()``: segments that are not
    simple identifiers (UUID key ids with hyphens) come back backtick-quoted.
    """
    return [seg[1:-1] if seg.startswith('`') and seg.endswith('`') else seg for seg in path.split('.')]


def _deep_merge(base: dict, overlay: dict) -> None:
    for key, val in overlay.items():
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val


class _DocRef:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def set(self, data, merge=False):
        if self._path not in self._store.data:
            self._store.data[self._path] = {}
        if merge:
            _deep_merge(self._store.data[self._path], data)
        else:
            self._store.data[self._path] = data
        self._store.set_calls.append((self._path, merge))

    def get(self):
        return types.SimpleNamespace(
            exists=self._path in self._store.data,
            to_dict=lambda: self._store.data.get(self._path, {}),
        )

    def update(self, fields):
        if self._path not in self._store.data:
            self._store.data[self._path] = {}
        target = self._store.data[self._path]
        for dotted_path, value in fields.items():
            # Firestore only accepts string update keys; a FieldPath instance raises
            # ``AttributeError: 'FieldPath' object has no attribute 'strip'``.
            if not isinstance(dotted_path, str):
                raise AttributeError(f"'{type(dotted_path).__name__}' object has no attribute 'strip'")
            parts = _split_escaped_field_path(dotted_path)
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            if value is _DELETE_SENTINEL:
                target.pop(parts[-1], None)
            else:
                target[parts[-1]] = value
        self._store.update_calls.append((self._path, fields))


class FakeDbStore:
    def __init__(self):
        self.data: dict = {}
        self.set_calls: list = []
        self.update_calls: list = []

    def document(self, path):
        return _DocRef(self, path)


def test_seed_read_only_grant_writes_default_read_contract():
    store = FakeDbStore()
    path = seed_developer_api_key_memory_grant('uid1', 'key1', default_read=True, write=False, db_client=store)

    expected_doc = f'users/uid1/{APP_KEY_MEMORY_GRANT_SUBPATH}'
    assert path == expected_doc
    assert len(store.set_calls) == 1

    written_data = store.data[expected_doc]
    expected = build_app_key_scope_grant_contract_state(
        consumer='developer_api',
        app_id='developer_api',
        key_id='key1',
        scopes=['memories.read'],
        default_read=True,
    )
    assert written_data == expected


def test_seed_write_grant_includes_write_scope_and_flag():
    store = FakeDbStore()
    seed_developer_api_key_memory_grant('uid1', 'key2', default_read=True, write=True, db_client=store)
    grant = store.data[f'users/uid1/{APP_KEY_MEMORY_GRANT_SUBPATH}']['grants']['developer_api']['apps'][
        'developer_api'
    ]['keys']['key2']
    assert grant['write'] is True
    assert 'memories.read' in grant['scopes']
    assert 'memories.write' in grant['scopes']


def test_seed_merge_preserves_existing_key_grants():
    store = FakeDbStore()
    seed_developer_api_key_memory_grant('uid1', 'key1', default_read=True, db_client=store)
    seed_developer_api_key_memory_grant('uid1', 'key2', default_read=True, db_client=store)

    keys = store.data[f'users/uid1/{APP_KEY_MEMORY_GRANT_SUBPATH}']['grants']['developer_api']['apps']['developer_api'][
        'keys'
    ]
    assert 'key1' in keys
    assert 'key2' in keys


def test_seeded_grant_passes_authorization_gate():
    store = FakeDbStore()
    seed_developer_api_key_memory_grant('uid1', 'key1', default_read=True, db_client=store)

    state = store.data[f'users/uid1/{APP_KEY_MEMORY_GRANT_SUBPATH}']
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


def test_remove_grant_deletes_key_entry_only():
    store = FakeDbStore()
    seed_developer_api_key_memory_grant('uid1', 'key1', default_read=True, db_client=store)
    seed_developer_api_key_memory_grant('uid1', 'key2', default_read=True, db_client=store)

    remove_developer_api_key_memory_grant('uid1', 'key1', db_client=store)

    keys = store.data[f'users/uid1/{APP_KEY_MEMORY_GRANT_SUBPATH}']['grants']['developer_api']['apps']['developer_api'][
        'keys'
    ]
    assert 'key1' not in keys
    assert 'key2' in keys


def test_remove_grant_uses_escaped_string_field_path_for_uuid_key_id():
    """Regression: the delete key must be an escaped string, not a FieldPath instance.

    ``google.cloud.firestore`` exposes no ``FieldPath`` attribute, and ``update()``
    rejects FieldPath keys, so building the update key from one turned every
    Developer API key deletion into a 500 after the key row was already removed.
    """
    key_id = '0f6a4d1c-9b2e-4a77-8c31-2f5c9a8d7e10'
    store = FakeDbStore()
    seed_developer_api_key_memory_grant('uid1', key_id, default_read=True, db_client=store)
    seed_developer_api_key_memory_grant('uid1', 'key2', default_read=True, db_client=store)

    remove_developer_api_key_memory_grant('uid1', key_id, db_client=store)

    _path, fields = store.update_calls[-1]
    (update_key,) = fields
    assert isinstance(update_key, str)
    assert update_key == f'grants.developer_api.apps.developer_api.keys.`{key_id}`'

    keys = store.data[f'users/uid1/{APP_KEY_MEMORY_GRANT_SUBPATH}']['grants']['developer_api']['apps']['developer_api'][
        'keys'
    ]
    assert key_id not in keys
    assert 'key2' in keys


def test_remove_grant_field_path_is_accepted_by_firestore_update_parser():
    """The produced key must survive Firestore's own update-path parsing."""
    from google.cloud.firestore_v1 import _helpers

    key_id = '0f6a4d1c-9b2e-4a77-8c31-2f5c9a8d7e10'
    store = FakeDbStore()
    seed_developer_api_key_memory_grant('uid1', key_id, default_read=True, db_client=store)

    remove_developer_api_key_memory_grant('uid1', key_id, db_client=store)

    _path, fields = store.update_calls[-1]
    extractor = _helpers.DocumentExtractorForUpdate(fields)
    assert [p.to_api_repr() for p in extractor.top_level_paths] == list(fields)


def test_fake_doc_ref_rejects_non_string_update_key():
    """Guard the seam itself: a FieldPath-style key must fail like real Firestore."""
    store = FakeDbStore()
    with pytest.raises(AttributeError):
        store.document('users/uid1/x').update({('grants', 'developer_api'): _DELETE_SENTINEL})
