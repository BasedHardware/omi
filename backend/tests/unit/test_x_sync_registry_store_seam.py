"""X sync registry rides the neutral storage port, not the raw Firestore client (WP2, ADR-0002).

Enroll/unenroll/list operate on the top-level ``x_connector_users`` collection keyed by uid. These
guard the migrated seam via FakeDocumentStore: register writes the uid doc (merge), unregister
deletes it, and list returns exactly the enrolled uids.
"""

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import pytest  # noqa: E402

import database.x_sync_registry as x_sync_registry  # noqa: E402
from tests.store_fakes import FakeDocumentStore  # noqa: E402


@pytest.fixture
def store(monkeypatch):
    fake = FakeDocumentStore()
    monkeypatch.setattr(x_sync_registry, '_store', lambda: fake)
    return fake


def test_register_writes_uid_doc_at_registry_path(store):
    x_sync_registry.register_sync_user('user-1')

    doc = store.get('x_connector_users/user-1')
    assert doc.exists
    assert doc.id == 'user-1'
    assert doc.to_dict()['uid'] == 'user-1'
    assert 'updated_at' in doc.to_dict()


def test_register_is_idempotent_refresh(store):
    x_sync_registry.register_sync_user('user-1')
    first = store.get('x_connector_users/user-1').to_dict()['updated_at']
    x_sync_registry.register_sync_user('user-1')
    # Still a single enrolled user; the doc remains present.
    assert x_sync_registry.list_sync_user_ids() == ['user-1']
    assert store.get('x_connector_users/user-1').to_dict()['updated_at'] >= first


def test_unregister_removes_only_that_user(store):
    x_sync_registry.register_sync_user('user-1')
    x_sync_registry.register_sync_user('user-2')

    x_sync_registry.unregister_sync_user('user-1')

    assert not store.get('x_connector_users/user-1').exists
    assert store.get('x_connector_users/user-2').exists


def test_unregister_missing_user_is_noop(store):
    # deleting an unenrolled uid must not raise
    x_sync_registry.unregister_sync_user('never-enrolled')
    assert x_sync_registry.list_sync_user_ids() == []


def test_list_returns_all_enrolled_uids(store):
    for uid in ('a', 'b', 'c'):
        x_sync_registry.register_sync_user(uid)

    assert sorted(x_sync_registry.list_sync_user_ids()) == ['a', 'b', 'c']


def test_list_empty_registry(store):
    assert x_sync_registry.list_sync_user_ids() == []
