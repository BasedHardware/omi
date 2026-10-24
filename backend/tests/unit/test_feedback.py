"""Unit tests for feedback database module input validation, client injection, and stream resilience."""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from tests.unit.memory_import_isolation import install_database_client_stub

install_database_client_stub()

from database import feedback as feedback_db


def test_get_feedback_event_empty_or_whitespace_returns_none():
    assert feedback_db.get_feedback_event("") is None
    assert feedback_db.get_feedback_event("   ") is None
    assert feedback_db.get_feedback_event(None) is None


def test_get_feedback_event_client_injection_and_exception_handling():
    client_mock = MagicMock()
    doc_mock = MagicMock()
    doc_mock.get.side_effect = RuntimeError("Firestore unavailable")
    col_mock = MagicMock()
    col_mock.document.return_value = doc_mock
    client_mock.collection.return_value = col_mock

    res = feedback_db.get_feedback_event("evt-123", firestore_client=client_mock)
    assert res is None


def test_get_report_empty_returns_none():
    assert feedback_db.get_report("") is None
    assert feedback_db.get_report("   ") is None
    assert feedback_db.get_report(None) is None


def test_get_report_client_injection_exception_handling():
    client_mock = MagicMock()
    doc_mock = MagicMock()
    doc_mock.get.side_effect = RuntimeError("Connection timed out")
    col_mock = MagicMock()
    col_mock.document.return_value = doc_mock
    client_mock.collection.return_value = col_mock

    res = feedback_db.get_report("2026-10-17", firestore_client=client_mock)
    assert res is None


def test_save_report_client_injection():
    client_mock = MagicMock()
    col_mock = MagicMock()
    doc_mock = MagicMock()
    col_mock.document.return_value = doc_mock
    client_mock.collection.return_value = col_mock

    report_mock = MagicMock()
    report_mock.date = "2026-10-17"
    report_mock.model_dump.return_value = {"date": "2026-10-17"}

    feedback_db.save_report(report_mock, firestore_client=client_mock)
    client_mock.collection.assert_called_with("feedback_reports")
    doc_mock.set.assert_called_with({"date": "2026-10-17"})
