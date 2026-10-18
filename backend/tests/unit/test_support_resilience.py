"""Hermetic unit tests for database.support identifier validation, safe reads, and audit logging."""

import hashlib
from datetime import datetime, timezone
from typing import Any
import pytest

from database import support


class FakeSnapshot:
    def __init__(self, data: Any, exists: bool = True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class FakeDocumentRef:
    def __init__(self, doc_id: str, store: dict[str, Any], fail_write: bool = False):
        self.doc_id = doc_id
        self._store = store
        self._fail_write = fail_write

    def get(self, field_paths: list[str] | None = None):
        self._store.setdefault('reads', []).append((self.doc_id, field_paths))
        if self.doc_id in self._store:
            val = self._store[self.doc_id]
            if isinstance(val, FakeSnapshot):
                return val
            return FakeSnapshot(val, exists=val is not None)
        return FakeSnapshot(None, exists=False)

    def set(self, data: dict[str, Any]):
        if self._fail_write:
            raise RuntimeError("Firestore write failed")
        self._store.setdefault('writes', []).append((self.doc_id, data))


class FakeCollectionRef:
    def __init__(self, name: str, root_store: dict[str, Any]):
        self.name = name
        self.root_store = root_store

    def document(self, doc_id: str | None = None):
        doc_key = doc_id if doc_id is not None else f"auto-id-{len(self.root_store.get('writes', []))}"
        return FakeDocumentRef(doc_key, self.root_store)


class FakeFirestoreClient:
    def __init__(self):
        self.collections: dict[str, dict[str, Any]] = {}

    def collection(self, name: str):
        store = self.collections.setdefault(name, {})
        return FakeCollectionRef(name, store)


# ============================================================================
# 1. UID Validation Tests
# ============================================================================


@pytest.mark.parametrize(
    "valid_uid",
    [
        "user_123",
        "uid-abc-xyz",
        "9999",
        "Admin_User",
        "a",
    ],
)
def test_validate_uid_accepts_clean_uids(valid_uid):
    assert support._validate_uid(valid_uid) == valid_uid


def test_validate_uid_strips_surrounding_whitespace():
    assert support._validate_uid("  user_123  ") == "user_123"


@pytest.mark.parametrize(
    "invalid_uid",
    [
        "",
        "   ",
        None,
        12345,
        ["user"],
        {"id": "user"},
        "user/subdoc",
        "user\\subdoc",
        "/root",
        "trail/",
        ".",
        "..",
        "__reserved__",
    ],
)
def test_validate_uid_rejects_malformed_and_traversal_uids(invalid_uid):
    with pytest.raises(ValueError):
        support._validate_uid(invalid_uid)


# ============================================================================
# 2. get_support_access Tests
# ============================================================================


def test_get_support_access_returns_data_for_existing_doc():
    client = FakeFirestoreClient()
    client.collections.setdefault('supportData', {})['caller_1'] = {'role': 'support:admin', 'tier': 1}

    result = support.get_support_access('caller_1', firestore_client=client)
    assert result == {'role': 'support:admin', 'tier': 1}
    assert client.collections['supportData']['reads'] == [('caller_1', None)]


def test_get_support_access_returns_none_when_doc_missing():
    client = FakeFirestoreClient()
    result = support.get_support_access('non_existent', firestore_client=client)
    assert result is None


def test_get_support_access_returns_none_for_corrupted_non_dict_snapshot():
    client = FakeFirestoreClient()
    client.collections.setdefault('supportData', {})['corrupted'] = FakeSnapshot("string-data", exists=True)

    result = support.get_support_access('corrupted', firestore_client=client)
    assert result is None


@pytest.mark.parametrize("invalid_uid", ["", "   ", "user/path", None, 123])
def test_get_support_access_safely_rejects_invalid_uids(invalid_uid):
    client = FakeFirestoreClient()
    result = support.get_support_access(invalid_uid, firestore_client=client)
    assert result is None
    assert 'reads' not in client.collections.get('supportData', {})


def test_get_support_access_falls_back_to_global_client_when_omitted(monkeypatch):
    client = FakeFirestoreClient()
    client.collections.setdefault('supportData', {})['caller_global'] = {'role': 'agent'}
    monkeypatch.setattr(support, 'get_firestore_client', lambda: client)

    result = support.get_support_access('caller_global')
    assert result == {'role': 'agent'}


# ============================================================================
# 3. get_support_activity Tests
# ============================================================================


def test_get_support_activity_returns_activity_for_existing_user():
    client = FakeFirestoreClient()
    client.collections.setdefault('users', {})['target_1'] = {
        'last_active_at': 1700000000,
        'last_active_platform': 'macos',
    }

    result = support.get_support_activity('target_1', firestore_client=client)
    assert result == {'last_active_at': 1700000000, 'last_active_platform': 'macos'}
    assert client.collections['users']['reads'] == [('target_1', ['last_active_at', 'last_active_platform'])]


def test_get_support_activity_returns_empty_dict_when_user_missing():
    client = FakeFirestoreClient()
    result = support.get_support_activity('unknown_user', firestore_client=client)
    assert result == {}


def test_get_support_activity_returns_empty_dict_for_non_dict_snapshot():
    client = FakeFirestoreClient()
    client.collections.setdefault('users', {})['bad_user'] = FakeSnapshot(None, exists=True)

    result = support.get_support_activity('bad_user', firestore_client=client)
    assert result == {}


@pytest.mark.parametrize("invalid_uid", ["", "   ", "path/traversal", None, 999])
def test_get_support_activity_safely_handles_invalid_uids(invalid_uid):
    client = FakeFirestoreClient()
    result = support.get_support_activity(invalid_uid, firestore_client=client)
    assert result == {}
    assert 'reads' not in client.collections.get('users', {})


def test_get_support_activity_falls_back_to_global_client_when_omitted(monkeypatch):
    client = FakeFirestoreClient()
    client.collections.setdefault('users', {})['global_target'] = {'last_active_platform': 'ios'}
    monkeypatch.setattr(support, 'get_firestore_client', lambda: client)

    result = support.get_support_activity('global_target')
    assert result == {'last_active_platform': 'ios'}


# ============================================================================
# 4. write_support_audit Tests
# ============================================================================


def test_write_support_audit_lookup_records_expected_payload():
    client = FakeFirestoreClient()
    support.write_support_audit(
        actor_uid='admin_1',
        action='lookup',
        target_uid='customer_2',
        email='User.Test@Example.Com',
        firestore_client=client,
    )

    writes = client.collections['support_audit_log']['writes']
    assert len(writes) == 1
    doc_id, payload = writes[0]
    assert payload['actor_uid'] == 'admin_1'
    assert payload['action'] == 'lookup'
    assert payload['target_uid'] == 'customer_2'
    assert payload['email_sha256'] == hashlib.sha256(b'user.test@example.com').hexdigest()
    assert payload['at'] is support.firestore.SERVER_TIMESTAMP
    assert 'window_from' not in payload
    assert 'window_to' not in payload


def test_write_support_audit_trace_includes_window_parameters():
    client = FakeFirestoreClient()
    w_from = datetime(2026, 10, 1, tzinfo=timezone.utc)
    w_to = datetime(2026, 10, 8, tzinfo=timezone.utc)

    support.write_support_audit(
        actor_uid='agent_x',
        action='trace',
        target_uid='target_y',
        email='trace@example.com',
        window_from=w_from,
        window_to=w_to,
        firestore_client=client,
    )

    writes = client.collections['support_audit_log']['writes']
    assert len(writes) == 1
    _, payload = writes[0]
    assert payload['action'] == 'trace'
    assert payload['window_from'] == w_from
    assert payload['window_to'] == w_to


@pytest.mark.parametrize("invalid_action", ["", "delete", "export", "audit", 123])
def test_write_support_audit_rejects_invalid_action(invalid_action):
    client = FakeFirestoreClient()
    with pytest.raises(ValueError, match="Invalid action"):
        support.write_support_audit(
            actor_uid='admin_1',
            action=invalid_action,  # type: ignore[arg-type]
            target_uid='target_1',
            email='test@example.com',
            firestore_client=client,
        )


@pytest.mark.parametrize("bad_actor", ["", "   ", "slash/actor", None])
def test_write_support_audit_rejects_invalid_actor_uid(bad_actor):
    client = FakeFirestoreClient()
    with pytest.raises(ValueError, match="Invalid uid"):
        support.write_support_audit(
            actor_uid=bad_actor,
            action='lookup',
            target_uid='target_1',
            email='test@example.com',
            firestore_client=client,
        )


@pytest.mark.parametrize("bad_target", ["", "   ", "slash/target", None])
def test_write_support_audit_rejects_invalid_target_uid(bad_target):
    client = FakeFirestoreClient()
    with pytest.raises(ValueError, match="Invalid uid"):
        support.write_support_audit(
            actor_uid='admin_1',
            action='lookup',
            target_uid=bad_target,
            email='test@example.com',
            firestore_client=client,
        )


@pytest.mark.parametrize("bad_email", ["", "   ", None, 123, []])
def test_write_support_audit_rejects_invalid_email(bad_email):
    client = FakeFirestoreClient()
    with pytest.raises(ValueError, match="Invalid email"):
        support.write_support_audit(
            actor_uid='admin_1',
            action='lookup',
            target_uid='target_1',
            email=bad_email,  # type: ignore[arg-type]
            firestore_client=client,
        )


def test_write_support_audit_falls_back_to_global_client_when_omitted(monkeypatch):
    client = FakeFirestoreClient()
    monkeypatch.setattr(support, 'get_firestore_client', lambda: client)

    support.write_support_audit(
        actor_uid='admin_global',
        action='lookup',
        target_uid='target_global',
        email='global@example.com',
    )

    writes = client.collections['support_audit_log']['writes']
    assert len(writes) == 1
    assert writes[0][1]['actor_uid'] == 'admin_global'
