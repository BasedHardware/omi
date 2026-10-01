"""Unit tests verifying defensive guards and resilience in account_deletion_transitions."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest
from google.api_core.exceptions import NotFound

from database.account_deletion_transitions import (
    adopt_legacy_late_agent_vm_cleanup,
    mark_wipe_completed,
    read_agent_vm_migration_journals,
    record_late_agent_vm_cleanup,
)


class _MockDocRef:
    def __init__(self, data=None, exists=True):
        self.data = data or {}
        self.exists = exists
        self.updates = []
        self.sets = []

    def get(self, transaction=None):
        return self

    def to_dict(self):
        return self.data

    def set(self, payload, merge=False):
        self.sets.append((payload, merge))

    def update(self, payload):
        self.updates.append(payload)


class _MockCollection:
    def __init__(self, snapshots=None, stream_exc=None):
        self.snapshots = snapshots or []
        self.stream_exc = stream_exc

    def document(self, doc_id):
        return self

    def collection(self, coll_id):
        return self

    def stream(self):
        if self.stream_exc:
            raise self.stream_exc
        return iter(self.snapshots)


class _MockSnapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return self._data


def test_read_agent_vm_migration_journals_validates_uid():
    """Verify read_agent_vm_migration_journals rejects empty, whitespace, and non-string uids."""
    with pytest.raises(ValueError, match="uid is required"):
        read_agent_vm_migration_journals("")
    with pytest.raises(ValueError, match="uid is required"):
        read_agent_vm_migration_journals("   ")
    with pytest.raises(ValueError, match="uid is required"):
        read_agent_vm_migration_journals(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="uid is required"):
        read_agent_vm_migration_journals(12345)  # type: ignore[arg-type]


def test_read_agent_vm_migration_journals_rejects_path_delimiters():
    """Verify path delimiters in uid are rejected."""
    with pytest.raises(ValueError, match="uid cannot contain path delimiters"):
        read_agent_vm_migration_journals("user/123")


def test_read_agent_vm_migration_journals_validates_limit():
    """Verify limit must be a positive integer."""
    with pytest.raises(ValueError, match="limit must be a positive integer"):
        read_agent_vm_migration_journals("user-1", limit=0)
    with pytest.raises(ValueError, match="limit must be a positive integer"):
        read_agent_vm_migration_journals("user-1", limit=-5)
    with pytest.raises(ValueError, match="limit must be a positive integer"):
        read_agent_vm_migration_journals("user-1", limit="10")  # type: ignore[arg-type]


def test_read_agent_vm_migration_journals_handles_not_found():
    """Verify NotFound exception returns an empty list gracefully."""
    mock_client = MagicMock()
    mock_coll = _MockCollection(stream_exc=NotFound("Collection missing"))
    mock_client.collection.return_value = mock_coll

    journals = read_agent_vm_migration_journals("user-1", firestore_client=mock_client)
    assert journals == []


def test_read_agent_vm_migration_journals_bounds_results():
    """Verify stream iteration is bounded by the limit parameter."""
    snapshots = [
        _MockSnapshot(f"mig-{i}", {"migrationId": f"mig-{i}", "status": "ok"})
        for i in range(10)
    ]
    mock_client = MagicMock()
    mock_coll = _MockCollection(snapshots=snapshots)
    mock_client.collection.return_value = mock_coll

    journals = read_agent_vm_migration_journals("user-1", limit=3, firestore_client=mock_client)
    assert len(journals) == 3
    assert [j["migrationId"] for j in journals] == ["mig-0", "mig-1", "mig-2"]


def test_read_agent_vm_migration_journals_detects_malformed_data():
    """Verify non-dict snapshot payloads raise RuntimeError."""
    mock_client = MagicMock()
    mock_coll = _MockCollection(snapshots=[_MockSnapshot("mig-bad", "corrupted-string")])
    mock_client.collection.return_value = mock_coll

    with pytest.raises(RuntimeError, match="Agent VM migration journal is malformed"):
        read_agent_vm_migration_journals("user-1", firestore_client=mock_client)


def test_read_agent_vm_migration_journals_detects_mismatched_identity():
    """Verify mismatched migrationId in data vs document ID raises RuntimeError."""
    mock_client = MagicMock()
    mock_coll = _MockCollection(snapshots=[_MockSnapshot("mig-1", {"migrationId": "mig-mismatch"})])
    mock_client.collection.return_value = mock_coll

    with pytest.raises(RuntimeError, match="Agent VM migration journal identity is ambiguous"):
        read_agent_vm_migration_journals("user-1", firestore_client=mock_client)


def test_mark_wipe_completed_requires_doc_ref():
    """Verify mark_wipe_completed fails fast on None doc_ref."""
    mock_txn = MagicMock()
    with pytest.raises(ValueError, match="doc_ref is required"):
        mark_wipe_completed(mock_txn, None)


def test_mark_wipe_completed_normalizes_naive_datetime():
    """Verify naive now is coerced to timezone.utc and sets status completed."""
    mock_txn = MagicMock()
    doc_ref = _MockDocRef(data={"wipe_status": "in_progress"}, exists=True)
    naive_dt = datetime(2026, 9, 30, 20, 0, 0)

    result = mark_wipe_completed(mock_txn, doc_ref, now=naive_dt)

    assert result is True
    assert mock_txn.set.call_count == 1
    call_doc, payload = mock_txn.set.call_args[0]
    kwargs = mock_txn.set.call_args[1]
    assert call_doc is doc_ref
    assert kwargs.get("merge") is True
    assert payload["wipe_status"] == "completed"
    assert payload["wipe_completed_at"].tzinfo == timezone.utc


def test_mark_wipe_completed_handles_late_cleanup_failure():
    """Verify presence of late_agent_vm_cleanup marks wipe as failed."""
    mock_txn = MagicMock()
    doc_ref = _MockDocRef(
        data={"late_agent_vm_cleanup": {"vmName": "vm-1"}},
        exists=True,
    )

    result = mark_wipe_completed(mock_txn, doc_ref)

    assert result is False
    assert mock_txn.set.call_count == 1
    call_doc, payload = mock_txn.set.call_args[0]
    kwargs = mock_txn.set.call_args[1]
    assert call_doc is doc_ref
    assert kwargs.get("merge") is True
    assert payload["wipe_status"] == "failed"
    assert payload["wipe_failed_at"].tzinfo == timezone.utc


def test_record_late_agent_vm_cleanup_validates_inputs():
    """Verify input validation on record_late_agent_vm_cleanup."""
    mock_txn = MagicMock()
    doc_ref = _MockDocRef(data={"wipe_status": "in_progress"}, exists=True)

    with pytest.raises(ValueError, match="doc_ref is required"):
        record_late_agent_vm_cleanup(mock_txn, None, "vm-1", "us-central1-a")

    with pytest.raises(ValueError, match="vm_name must be a non-empty string"):
        record_late_agent_vm_cleanup(mock_txn, doc_ref, "   ", "us-central1-a")

    with pytest.raises(ValueError, match="zone must be a non-empty string"):
        record_late_agent_vm_cleanup(mock_txn, doc_ref, "vm-1", "")

    with pytest.raises(ValueError, match="late Agent VM cleanup instance identity must be numeric"):
        record_late_agent_vm_cleanup(mock_txn, doc_ref, "vm-1", "zone-1", expected_instance_id="abc-not-num")


def test_record_late_agent_vm_cleanup_writes_record():
    """Verify successful late agent VM cleanup record writing with timezone-aware timestamp."""
    mock_txn = MagicMock()
    doc_ref = _MockDocRef(data={"wipe_status": "in_progress"}, exists=True)
    naive_dt = datetime(2026, 9, 30, 20, 0, 0)

    result = record_late_agent_vm_cleanup(
        mock_txn,
        doc_ref,
        vm_name="  my-vm  ",
        zone="  us-central1-a  ",
        expected_instance_id="1234567890",
        now=naive_dt,
    )

    assert result is True
    assert mock_txn.set.call_count == 1
    call_doc, payload = mock_txn.set.call_args[0]
    kwargs = mock_txn.set.call_args[1]
    assert call_doc is doc_ref
    assert kwargs.get("merge") is True
    assert payload["wipe_status"] == "failed"
    assert payload["wipe_failed_at"].tzinfo == timezone.utc
    assert payload["late_agent_vm_cleanup"] == {
        "vmName": "my-vm",
        "zone": "us-central1-a",
        "expectedInstanceId": "1234567890",
    }


def test_adopt_legacy_late_agent_vm_cleanup_validates_inputs():
    """Verify adopt_legacy_late_agent_vm_cleanup validates doc_ref, strings, and numeric ID."""
    mock_txn = MagicMock()
    doc_ref = _MockDocRef(data={"wipe_status": "in_progress"}, exists=True)

    with pytest.raises(ValueError, match="doc_ref is required"):
        adopt_legacy_late_agent_vm_cleanup(mock_txn, None, "vm-1", "zone", "12345")

    with pytest.raises(ValueError, match="vm_name must be a non-empty string"):
        adopt_legacy_late_agent_vm_cleanup(mock_txn, doc_ref, "", "zone", "12345")

    with pytest.raises(ValueError, match="late Agent VM cleanup instance identity must be numeric"):
        adopt_legacy_late_agent_vm_cleanup(mock_txn, doc_ref, "vm-1", "zone", "not-digits")


def test_adopt_legacy_late_agent_vm_cleanup_updates_target():
    """Verify adopt_legacy_late_agent_vm_cleanup issues transaction.update when valid."""
    mock_txn = MagicMock()
    doc_ref = _MockDocRef(
        data={
            "wipe_status": "in_progress",
            "late_agent_vm_cleanup": {"vmName": "vm-legacy", "zone": "zone-a"},
        },
        exists=True,
    )

    result = adopt_legacy_late_agent_vm_cleanup(
        mock_txn,
        doc_ref,
        vm_name="vm-legacy",
        zone="zone-a",
        expected_instance_id="99999",
    )

    assert result is True
    assert mock_txn.update.call_count == 1
    call_doc, payload = mock_txn.update.call_args[0]
    assert call_doc is doc_ref
    assert payload == {"late_agent_vm_cleanup.expectedInstanceId": "99999"}

