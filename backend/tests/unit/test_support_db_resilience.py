"""Hermetic unit tests for support database client injection, sanitization, and audit resilience."""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
sys.path.insert(0, str(BACKEND_DIR))
from tests.unit.memory_import_isolation import install_database_client_stub

install_database_client_stub()

import database.support as support_db


def test_get_support_access_success_and_missing():
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {"role": "support_admin", "level": 2}
    mock_client = MagicMock()
    mock_client.collection.return_value.document.return_value.get.return_value = mock_doc

    # Valid UID -> returns dict
    res = support_db.get_support_access("admin-1", firestore_client=mock_client)
    assert res == {"role": "support_admin", "level": 2}

    # Empty UID -> returns None immediately
    assert support_db.get_support_access("", firestore_client=mock_client) is None
    assert support_db.get_support_access("   ", firestore_client=mock_client) is None

    # Missing doc -> returns None
    mock_doc_missing = MagicMock()
    mock_doc_missing.exists = False
    mock_client.collection.return_value.document.return_value.get.return_value = mock_doc_missing
    assert support_db.get_support_access("user-non-support", firestore_client=mock_client) is None


def test_get_support_access_firestore_exception_fails_safe():
    mock_client = MagicMock()
    mock_client.collection.side_effect = Exception("Firestore unavailable")

    res = support_db.get_support_access("admin-1", firestore_client=mock_client)
    assert res is None


def test_get_support_activity():
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {"last_active_at": 1700000000, "last_active_platform": "macos"}
    mock_client = MagicMock()
    mock_client.collection.return_value.document.return_value.get.return_value = mock_doc

    act = support_db.get_support_activity("target-123", firestore_client=mock_client)
    assert act["last_active_platform"] == "macos"

    # Empty UID -> returns {}
    assert support_db.get_support_activity("", firestore_client=mock_client) == {}


def test_write_support_audit_trace_and_lookup():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_client.collection.return_value.document.return_value = mock_doc

    # Action lookup
    support_db.write_support_audit(
        actor_uid="admin-1",
        action="lookup",
        target_uid="user-2",
        email="test@example.com",
        firestore_client=mock_client,
    )
    mock_doc.set.assert_called_once()
    payload = mock_doc.set.call_args[0][0]
    assert payload["actor_uid"] == "admin-1"
    assert payload["action"] == "lookup"
    assert payload["target_uid"] == "user-2"
    assert "email_sha256" in payload

    # Action trace
    t0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 17, tzinfo=timezone.utc)
    mock_doc.reset_mock()
    support_db.write_support_audit(
        actor_uid="admin-1",
        action="trace",
        target_uid="user-2",
        email="test@example.com",
        window_from=t0,
        window_to=t1,
        firestore_client=mock_client,
    )
    payload_trace = mock_doc.set.call_args[0][0]
    assert payload_trace["action"] == "trace"
    assert payload_trace["window_from"] == t0
    assert payload_trace["window_to"] == t1


def test_write_support_audit_exception_raises():
    mock_client = MagicMock()
    mock_client.collection.side_effect = Exception("Outage")
    with pytest.raises(Exception, match="Outage"):
        support_db.write_support_audit(
            actor_uid="admin-1",
            action="lookup",
            target_uid="user-2",
            email="test@example.com",
            firestore_client=mock_client,
        )
