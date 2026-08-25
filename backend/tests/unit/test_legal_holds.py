from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from database import legal_holds


class _Snapshot:
    def __init__(self, payload=None):
        self._payload = payload
        self.exists = payload is not None

    def to_dict(self):
        return dict(self._payload or {})


class _Reference:
    def __init__(self, client, path):
        self.client = client
        self.path = path

    def get(self, transaction=None):
        del transaction
        return _Snapshot(self.client.docs.get(self.path))


class _Collection:
    def __init__(self, client, path):
        self.client = client
        self.path = path

    def document(self, document_id):
        return _Reference(self.client, f"{self.path}/{document_id}")


class _Transaction:
    def __init__(self, client):
        self.client = client

    def set(self, reference, payload, merge=False):
        current = dict(self.client.docs.get(reference.path, {})) if merge else {}
        self.client.docs[reference.path] = {**current, **payload}


class _FakeClient:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})

    def collection(self, path):
        return _Collection(self, path)

    def transaction(self):
        return _Transaction(self)


def _gate(*, token="token-1", state="running"):
    return {
        "schema_version": "legal_hold_deletion_gate.v1",
        "uid": "uid1",
        "kind": "explicit_memory_deletion",
        "token": token,
        "state": state,
        "started_at": legal_holds.datetime.now(legal_holds.timezone.utc),
        "finished_at": None,
    }


def _client_for(*, exists: bool, data: dict | None = None):
    snapshot = SimpleNamespace(exists=exists, to_dict=lambda: data or {})
    document = MagicMock()
    document.get.return_value = snapshot
    collection = MagicMock()
    collection.document.return_value = document
    client = MagicMock()
    client.document.return_value = document
    client.collection.return_value = collection
    return client


def test_missing_hold_allows_deletion(monkeypatch):
    client = _client_for(exists=False)
    monkeypatch.setattr(legal_holds, "get_firestore_client", lambda: client)

    legal_holds.assert_account_deletion_permitted("uid1")

    client.document.assert_called_once_with("legal_holds/uid1")


def test_active_admin_hold_blocks_deletion():
    client = _client_for(
        exists=True,
        data={"schema_version": "legal_hold.v1", "issuer": "admin", "active": True},
    )

    with pytest.raises(legal_holds.LegalHoldActive):
        legal_holds.assert_account_deletion_permitted("uid1", firestore_client=client)


def test_inactive_service_hold_allows_deletion():
    client = _client_for(
        exists=True,
        data={"schema_version": "legal_hold.v1", "issuer": "legal_hold_service", "active": False},
    )

    legal_holds.assert_account_deletion_permitted("uid1", firestore_client=client)


@pytest.mark.parametrize(
    "data",
    [
        {"schema_version": "legal_hold.v1", "issuer": "user", "active": True},
        {"schema_version": "unknown", "issuer": "admin", "active": True},
        {"schema_version": "legal_hold.v1", "issuer": "admin", "active": "true"},
    ],
)
def test_malformed_or_user_owned_hold_fails_closed(data):
    client = _client_for(exists=True, data=data)

    with pytest.raises(legal_holds.LegalHoldAuthorityUnavailable):
        legal_holds.assert_account_deletion_permitted("uid1", firestore_client=client)


def test_authority_read_error_fails_closed():
    client = MagicMock()
    client.collection.side_effect = RuntimeError("firestore unavailable")

    with pytest.raises(legal_holds.LegalHoldAuthorityUnavailable):
        legal_holds.assert_account_deletion_permitted("uid1", firestore_client=client)


def test_acquire_gate_and_hold_placement_have_one_winner():
    now = legal_holds.datetime.now(legal_holds.timezone.utc)
    client = _FakeClient()

    legal_holds._acquire_destructive_operation_transaction.to_wrap(
        client.transaction(), client, "uid1", "explicit_memory_deletion", "token-1", now
    )

    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        legal_holds._place_legal_hold_transaction.to_wrap(client.transaction(), client, "uid1", "admin", True, now)
    assert "legal_holds/uid1" not in client.docs


def test_active_hold_blocks_gate_without_mutation():
    now = legal_holds.datetime.now(legal_holds.timezone.utc)
    client = _FakeClient(
        {
            "legal_holds/uid1": {
                "schema_version": "legal_hold.v1",
                "issuer": "admin",
                "active": True,
            }
        }
    )

    with pytest.raises(legal_holds.LegalHoldActive):
        legal_holds._acquire_destructive_operation_transaction.to_wrap(
            client.transaction(), client, "uid1", "explicit_memory_deletion", "token-1", now
        )
    assert "legal_hold_deletion_gates/uid1" not in client.docs


def test_gate_finish_is_token_cas_and_failed_gate_allows_later_hold():
    now = legal_holds.datetime.now(legal_holds.timezone.utc)
    client = _FakeClient({"legal_hold_deletion_gates/uid1": _gate()})

    with pytest.raises(legal_holds.LegalHoldAuthorityUnavailable):
        legal_holds._finish_destructive_operation_transaction.to_wrap(
            client.transaction(), client, "uid1", "explicit_memory_deletion", "wrong", "failed", now
        )

    legal_holds._finish_destructive_operation_transaction.to_wrap(
        client.transaction(), client, "uid1", "explicit_memory_deletion", "token-1", "failed", now
    )
    legal_holds._place_legal_hold_transaction.to_wrap(
        client.transaction(), client, "uid1", "legal_hold_service", True, now
    )
    assert client.docs["legal_holds/uid1"]["active"] is True


def test_irreversible_transaction_revalidates_matching_hold_and_gate():
    client = _FakeClient({"legal_hold_deletion_gates/uid1": _gate()})

    legal_holds.assert_destructive_operation_transaction(
        client.transaction(),
        client,
        uid="uid1",
        kind="explicit_memory_deletion",
        token="token-1",
    )

    client.docs["legal_holds/uid1"] = {
        "schema_version": "legal_hold.v1",
        "issuer": "admin",
        "active": True,
    }
    with pytest.raises(legal_holds.LegalHoldActive):
        legal_holds.assert_destructive_operation_transaction(
            client.transaction(),
            client,
            uid="uid1",
            kind="explicit_memory_deletion",
            token="token-1",
        )


def test_external_writer_and_deletion_gate_have_exactly_one_owner():
    now = legal_holds.datetime.now(legal_holds.timezone.utc)
    client = _FakeClient()

    legal_holds._acquire_destructive_operation_transaction.to_wrap(
        client.transaction(), client, "uid1", "external_data_write", "writer-token", now
    )

    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        legal_holds._acquire_destructive_operation_transaction.to_wrap(
            client.transaction(), client, "uid1", "account_deletion", "delete-token", now
        )


def test_account_deletion_marker_blocks_stale_external_writer_before_provider_work():
    now = legal_holds.datetime.now(legal_holds.timezone.utc)
    client = _FakeClient({"account_deletions/uid1": {"wipe_status": "accepted"}})

    with pytest.raises(legal_holds.DestructiveOperationInProgress, match="account deletion"):
        legal_holds._acquire_destructive_operation_transaction.to_wrap(
            client.transaction(), client, "uid1", "external_data_write", "writer-token", now
        )
    assert "legal_hold_deletion_gates/uid1" not in client.docs


def test_inflight_deletion_blocks_external_writer_before_provider_work():
    now = legal_holds.datetime.now(legal_holds.timezone.utc)
    client = _FakeClient({"legal_hold_deletion_gates/uid1": _gate(token="delete-token")})

    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        legal_holds._acquire_destructive_operation_transaction.to_wrap(
            client.transaction(), client, "uid1", "external_data_write", "writer-token", now
        )
