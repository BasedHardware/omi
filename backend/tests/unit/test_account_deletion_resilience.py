"""Hermetic unit tests for account deletion marker and transitions resilience."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
import pytest

from database import account_deletion_marker
from database.account_deletion_marker import (
    ACCOUNT_DELETION_COLLECTION,
    MAX_UID_LENGTH,
    _clean_uid,
    account_deletion_document,
    clean_uid,
    get_user_deletion_wipe_status,
)
from database.account_deletion_transitions import (
    adopt_legacy_late_agent_vm_cleanup,
    mark_wipe_completed,
    read_agent_vm_migration_journals,
    record_late_agent_vm_cleanup,
)
from database.firestore_read_metrics import FirestoreReadOutcome, FirestoreReadSite

# ---------------------------------------------------------------------------
# Helpers unwrapping @transactional decorators (matching repo test precedent)
# ---------------------------------------------------------------------------
raw_mark_wipe_completed: Any = getattr(mark_wipe_completed, "to_wrap", mark_wipe_completed)
raw_record_late_cleanup: Any = getattr(record_late_agent_vm_cleanup, "to_wrap", record_late_agent_vm_cleanup)
raw_adopt_legacy_cleanup: Any = getattr(
    adopt_legacy_late_agent_vm_cleanup, "to_wrap", adopt_legacy_late_agent_vm_cleanup
)


class FakeTransaction:
    """Lightweight test double for unwrapped transactional callbacks."""

    def __init__(self):
        self.sets = []
        self.updates = []

    def set(self, doc_ref, data, merge=False):
        self.sets.append((doc_ref, data, merge))

    def update(self, doc_ref, data):
        self.updates.append((doc_ref, data))


# ---------------------------------------------------------------------------
# Account Deletion Marker Tests
# ---------------------------------------------------------------------------
def test_clean_uid_validation():
    assert clean_uid(None) == ""
    assert clean_uid(12345) == ""
    assert clean_uid("") == ""
    assert clean_uid("u" * (MAX_UID_LENGTH + 1)) == ""
    assert clean_uid("user/slash") == ""
    assert clean_uid("user\\backslash") == ""
    assert clean_uid("user\0null") == ""
    assert clean_uid("user..traversal") == ""

    # Exact UID representation is preserved
    assert clean_uid("user_123") == "user_123"
    assert clean_uid("u" * MAX_UID_LENGTH) == "u" * MAX_UID_LENGTH

    # Backwards-compatibility alias matches
    assert _clean_uid is clean_uid


def test_account_deletion_document_and_client_injection():
    mock_client = MagicMock()
    mock_coll = MagicMock()
    mock_doc = MagicMock()
    mock_client.collection.return_value = mock_coll
    mock_coll.document.return_value = mock_doc

    # Normal valid uid
    doc = account_deletion_document("user_123", firestore_client=mock_client)
    mock_client.collection.assert_called_with(ACCOUNT_DELETION_COLLECTION)
    mock_coll.document.assert_called_with("user_123")
    assert doc == mock_doc

    # Invalid uid raises ValueError
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        account_deletion_document("", firestore_client=mock_client)

    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        account_deletion_document("bad/path", firestore_client=mock_client)

    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        account_deletion_document("bad..path", firestore_client=mock_client)


def test_get_user_deletion_wipe_status_invalid_uid_fails_closed():
    mock_client = MagicMock()
    # Must raise ValueError so auth fence fails closed with 503 instead of passing through
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        get_user_deletion_wipe_status("", firestore_client=mock_client)

    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        get_user_deletion_wipe_status("bad/uid", firestore_client=mock_client)

    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        get_user_deletion_wipe_status("bad..uid", firestore_client=mock_client)

    mock_client.collection.assert_not_called()


def test_get_user_deletion_wipe_status_malformed_snapshot_raises(monkeypatch):
    mock_client = MagicMock()
    mock_coll = MagicMock()
    mock_doc = MagicMock()
    mock_snapshot = MagicMock()
    # exists is not a boolean
    del mock_snapshot.exists

    mock_client.collection.return_value = mock_coll
    mock_coll.document.return_value = mock_doc
    mock_doc.get.return_value = mock_snapshot

    # Must raise RuntimeError so auth fence fails closed with 503
    with pytest.raises(RuntimeError, match="Malformed Firestore snapshot"):
        get_user_deletion_wipe_status("user_123", firestore_client=mock_client)


def test_get_user_deletion_wipe_status_miss(monkeypatch):
    mock_client = MagicMock()
    mock_coll = MagicMock()
    mock_doc = MagicMock()
    mock_snapshot = MagicMock()
    mock_snapshot.exists = False

    mock_client.collection.return_value = mock_coll
    mock_coll.document.return_value = mock_doc
    mock_doc.get.return_value = mock_snapshot

    recorded_metrics = []

    def fake_record(site, outcome):
        recorded_metrics.append((site, outcome))

    # Object-based monkeypatching per repo standard
    monkeypatch.setattr(account_deletion_marker, "record_document_read", fake_record)

    status = get_user_deletion_wipe_status("user_123", firestore_client=mock_client)
    assert status is None
    assert recorded_metrics == [(FirestoreReadSite.USER_DELETION_WIPE_STATUS, FirestoreReadOutcome.MISS)]


def test_get_user_deletion_wipe_status_hit(monkeypatch):
    mock_client = MagicMock()
    mock_coll = MagicMock()
    mock_doc = MagicMock()
    mock_snapshot = MagicMock()
    mock_snapshot.exists = True
    mock_snapshot.to_dict.return_value = {"wipe_status": "wiping"}

    mock_client.collection.return_value = mock_coll
    mock_coll.document.return_value = mock_doc
    mock_doc.get.return_value = mock_snapshot

    recorded_metrics = []

    def fake_record(site, outcome):
        recorded_metrics.append((site, outcome))

    # Object-based monkeypatching per repo standard
    monkeypatch.setattr(account_deletion_marker, "record_document_read", fake_record)

    status = get_user_deletion_wipe_status("user_123", firestore_client=mock_client)
    assert status == "wiping"
    assert recorded_metrics == [(FirestoreReadSite.USER_DELETION_WIPE_STATUS, FirestoreReadOutcome.HIT)]


# ---------------------------------------------------------------------------
# Account Deletion Transitions Tests
# ---------------------------------------------------------------------------
def test_read_agent_vm_migration_journals_validation():
    mock_client = MagicMock()
    with pytest.raises(ValueError, match="uid is required"):
        read_agent_vm_migration_journals("", firestore_client=mock_client)

    with pytest.raises(ValueError, match="uid is required"):
        read_agent_vm_migration_journals(None, firestore_client=mock_client)

    with pytest.raises(ValueError, match="uid is required and must be a valid identifier"):
        read_agent_vm_migration_journals("user/subpath", firestore_client=mock_client)

    with pytest.raises(ValueError, match="uid is required and must be a valid identifier"):
        read_agent_vm_migration_journals("user..traversal", firestore_client=mock_client)


def test_read_agent_vm_migration_journals_happy_path():
    mock_client = MagicMock()
    mock_users = MagicMock()
    mock_user_doc = MagicMock()
    mock_mig_coll = MagicMock()

    mock_client.collection.return_value = mock_users
    mock_users.document.return_value = mock_user_doc
    mock_user_doc.collection.return_value = mock_mig_coll

    snap1 = MagicMock()
    snap1.id = "mig-2"
    snap1.to_dict.return_value = {"migrationId": "mig-2", "instance": "inst-2"}

    snap2 = MagicMock()
    snap2.id = "mig-1"
    snap2.to_dict.return_value = {"migrationId": "mig-1", "instance": "inst-1"}

    mock_mig_coll.stream.return_value = [snap1, snap2]

    journals = read_agent_vm_migration_journals("user_123", firestore_client=mock_client)
    assert len(journals) == 2
    assert journals[0]["migrationId"] == "mig-1"
    assert journals[1]["migrationId"] == "mig-2"


def test_read_agent_vm_migration_journals_malformed_record():
    mock_client = MagicMock()
    mock_users = MagicMock()
    mock_user_doc = MagicMock()
    mock_mig_coll = MagicMock()

    mock_client.collection.return_value = mock_users
    mock_users.document.return_value = mock_user_doc
    mock_user_doc.collection.return_value = mock_mig_coll

    snap1 = MagicMock()
    snap1.id = "mig-1"
    snap1.to_dict.return_value = "not_a_dict"

    mock_mig_coll.stream.return_value = [snap1]

    with pytest.raises(RuntimeError, match="Agent VM migration journal is malformed"):
        read_agent_vm_migration_journals("user_123", firestore_client=mock_client)


def test_mark_wipe_completed_malformed_snapshot_raises():
    txn = FakeTransaction()
    doc_ref = MagicMock()

    # Case 1: snapshot without boolean exists
    snapshot_bad_exists = MagicMock()
    del snapshot_bad_exists.exists
    doc_ref.get.return_value = snapshot_bad_exists

    with pytest.raises(RuntimeError, match="Malformed snapshot"):
        raw_mark_wipe_completed(txn, doc_ref)

    # Case 2: snapshot exists but data is not dict
    snapshot_corrupt_data = MagicMock()
    snapshot_corrupt_data.exists = True
    snapshot_corrupt_data.to_dict.return_value = "not_a_dict"
    doc_ref.get.return_value = snapshot_corrupt_data

    with pytest.raises(RuntimeError, match="Malformed account deletion marker data"):
        raw_mark_wipe_completed(txn, doc_ref)


def test_mark_wipe_completed_with_and_without_late_cleanup():
    txn = FakeTransaction()
    doc_ref = MagicMock()

    # Case 1: Has late_agent_vm_cleanup -> marks failed
    snapshot1 = MagicMock()
    snapshot1.exists = True
    snapshot1.to_dict.return_value = {"late_agent_vm_cleanup": {"vmName": "vm1"}}
    doc_ref.get.return_value = snapshot1

    success1 = raw_mark_wipe_completed(txn, doc_ref)
    assert success1 is False
    assert len(txn.sets) == 1
    assert txn.sets[0][1]["wipe_status"] == "failed"

    # Case 2: Clean marker -> marks completed
    txn.sets.clear()
    snapshot2 = MagicMock()
    snapshot2.exists = True
    snapshot2.to_dict.return_value = {}
    doc_ref.get.return_value = snapshot2

    success2 = raw_mark_wipe_completed(txn, doc_ref)
    assert success2 is True
    assert len(txn.sets) == 1
    assert txn.sets[0][1]["wipe_status"] == "completed"


def test_record_late_agent_vm_cleanup():
    txn = FakeTransaction()
    doc_ref = MagicMock()

    # Input validation
    with pytest.raises(ValueError, match="vm_name must be a non-empty string"):
        raw_record_late_cleanup(txn, doc_ref, "", "us-central1-a")

    with pytest.raises(ValueError, match="zone must be a non-empty string"):
        raw_record_late_cleanup(txn, doc_ref, "vm-1", "   ")

    with pytest.raises(ValueError, match="late Agent VM cleanup instance identity must be numeric"):
        raw_record_late_cleanup(txn, doc_ref, "vm-1", "us-central1-a", expected_instance_id="abc-not-num")

    # Happy path: blocks access status (e.g. wiping / pending)
    snapshot = MagicMock()
    snapshot.exists = True
    snapshot.to_dict.return_value = {"wipe_status": "wiping"}
    doc_ref.get.return_value = snapshot

    recorded = raw_record_late_cleanup(
        txn,
        doc_ref,
        "  vm-1  ",
        "  us-central1-a  ",
        expected_instance_id="1234567890",
    )
    assert recorded is True
    assert len(txn.sets) == 1
    _, data, merge = txn.sets[0]
    assert merge is True
    assert data["wipe_status"] == "failed"
    assert data["late_agent_vm_cleanup"] == {
        "vmName": "vm-1",
        "zone": "us-central1-a",
        "expectedInstanceId": "1234567890",
    }


def test_adopt_legacy_late_agent_vm_cleanup():
    txn = FakeTransaction()
    doc_ref = MagicMock()

    # Input validation
    with pytest.raises(ValueError, match="late Agent VM cleanup instance identity must be numeric"):
        raw_adopt_legacy_cleanup(txn, doc_ref, "vm-1", "zone-1", expected_instance_id="not-num")

    # Access allowed status (cancelled) -> returns False
    snapshot_cancelled = MagicMock()
    snapshot_cancelled.exists = True
    snapshot_cancelled.to_dict.return_value = {
        "wipe_status": "cancelled",
        "late_agent_vm_cleanup": {"vmName": "vm-1", "zone": "zone-1"},
    }
    doc_ref.get.return_value = snapshot_cancelled

    res = raw_adopt_legacy_cleanup(txn, doc_ref, "vm-1", "zone-1", expected_instance_id="12345")
    assert res is False

    # Happy path adopt: updates doc_ref with expectedInstanceId
    snapshot_wiping = MagicMock()
    snapshot_wiping.exists = True
    snapshot_wiping.to_dict.return_value = {
        "wipe_status": "wiping",
        "late_agent_vm_cleanup": {"vmName": "vm-1", "zone": "zone-1"},
    }
    doc_ref.get.return_value = snapshot_wiping

    res2 = raw_adopt_legacy_cleanup(txn, doc_ref, "vm-1", "zone-1", expected_instance_id="998877")
    assert res2 is True
    assert len(txn.updates) == 1
    assert txn.updates[0][1] == {"late_agent_vm_cleanup.expectedInstanceId": "998877"}
