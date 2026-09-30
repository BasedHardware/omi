"""Unit tests for database.recurrence_inbox defensive input boundaries and error resilience."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

import database.recurrence_inbox as recurrence_inbox_db
from models.workstream_association import (
    RecurrenceInboxReceipt,
    RecurrenceInboxStatus,
    RecurrenceOutcomeKind,
)


class FakeSnapshot:
    def __init__(self, exists=True, data=None):
        self.exists = exists
        self._data = data or {}

    def to_dict(self):
        return self._data


def _make_mock_signal():
    mock_signal = MagicMock()
    mock_signal.stable_loop_key = "loop_123"
    return mock_signal


def test_clean_str_helper():
    assert recurrence_inbox_db._clean_str("user_1", "uid") == "user_1"
    assert recurrence_inbox_db._clean_str("  user_1  ", "uid") == "user_1"
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        recurrence_inbox_db._clean_str("", "uid")
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        recurrence_inbox_db._clean_str("   ", "uid")
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        recurrence_inbox_db._clean_str(None, "uid")


def test_clean_generation_helper():
    assert recurrence_inbox_db._clean_generation(0) == 0
    assert recurrence_inbox_db._clean_generation(5) == 5
    with pytest.raises(ValueError, match="account_generation must be a non-negative integer"):
        recurrence_inbox_db._clean_generation(-1)
    with pytest.raises(ValueError, match="account_generation must be a non-negative integer"):
        recurrence_inbox_db._clean_generation("5")
    with pytest.raises(ValueError, match="account_generation must be a non-negative integer"):
        recurrence_inbox_db._clean_generation(True)


def test_enqueue_recurrence_signal_validation():
    signal = _make_mock_signal()
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        recurrence_inbox_db.enqueue_recurrence_signal("", signal, account_generation=1)
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        recurrence_inbox_db.enqueue_recurrence_signal("   ", signal, account_generation=1)
    with pytest.raises(ValueError, match="account_generation must be a non-negative integer"):
        recurrence_inbox_db.enqueue_recurrence_signal("u1", signal, account_generation=-1)
    with pytest.raises(ValueError, match="account_generation must be a non-negative integer"):
        recurrence_inbox_db.enqueue_recurrence_signal("u1", signal, account_generation="bad")


def test_list_pending_recurrence_receipts_input_guards():
    assert recurrence_inbox_db.list_pending_recurrence_receipts("", account_generation=1) == []
    assert recurrence_inbox_db.list_pending_recurrence_receipts("   ", account_generation=1) == []
    assert recurrence_inbox_db.list_pending_recurrence_receipts(None, account_generation=1) == []


def test_list_pending_recurrence_receipts_limit_clamping():
    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_db.collection.return_value.document.return_value.collection.return_value.where.return_value.where.return_value.limit.return_value = mock_query
    mock_query.stream.return_value = []

    # Limit <= 0 clamps to 1
    recurrence_inbox_db.list_pending_recurrence_receipts("u1", account_generation=1, limit=-10, firestore_client=mock_db)
    where_chain = mock_db.collection().document().collection().where().where()
    where_chain.limit.assert_called_with(1)

    # Limit > 500 clamps to 500
    recurrence_inbox_db.list_pending_recurrence_receipts("u1", account_generation=1, limit=1000, firestore_client=mock_db)
    where_chain.limit.assert_called_with(500)

    # Non-int limit falls back to default 100
    recurrence_inbox_db.list_pending_recurrence_receipts("u1", account_generation=1, limit="invalid", firestore_client=mock_db)
    where_chain.limit.assert_called_with(100)


def test_complete_recurrence_receipt_validation():
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        recurrence_inbox_db.complete_recurrence_receipt("", "rcpt_1", outcome=RecurrenceOutcomeKind.candidate_created, account_generation=1)
    with pytest.raises(ValueError, match="receipt_id must be a non-empty string"):
        recurrence_inbox_db.complete_recurrence_receipt("u1", "", outcome=RecurrenceOutcomeKind.candidate_created, account_generation=1)
    with pytest.raises(ValueError, match="account_generation must be a non-negative integer"):
        recurrence_inbox_db.complete_recurrence_receipt("u1", "rcpt_1", outcome=RecurrenceOutcomeKind.candidate_created, account_generation=-1)


def test_retry_recurrence_receipt_validation():
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        recurrence_inbox_db.retry_recurrence_receipt("", "rcpt_1", error_code="err", account_generation=1)
    with pytest.raises(ValueError, match="receipt_id must be a non-empty string"):
        recurrence_inbox_db.retry_recurrence_receipt("u1", "  ", error_code="err", account_generation=1)
    with pytest.raises(ValueError, match="account_generation must be a non-negative integer"):
        recurrence_inbox_db.retry_recurrence_receipt("u1", "rcpt_1", error_code="err", account_generation=-5)


def test_retry_recurrence_receipt_error_code_non_string_resilience(monkeypatch):
    mock_client = MagicMock()
    mock_txn = MagicMock()
    mock_client.transaction.return_value = mock_txn

    control_snapshot = FakeSnapshot(exists=True, data={"workflow_mode": "write", "account_generation": 1})
    now = datetime.now(timezone.utc)
    raw_receipt_data = {
        "receipt_id": "r1",
        "loop_key": "loop_1",
        "account_generation": 1,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
    }
    receipt_snapshot = FakeSnapshot(exists=True, data=raw_receipt_data)

    mock_control_ref = MagicMock()
    mock_control_ref.get.return_value = control_snapshot

    mock_receipt_ref = MagicMock()
    mock_receipt_ref.get.return_value = receipt_snapshot

    monkeypatch.setattr(recurrence_inbox_db, "_control_ref", lambda *args, **kwargs: mock_control_ref)
    monkeypatch.setattr(recurrence_inbox_db, "_receipt_ref", lambda *args, **kwargs: mock_receipt_ref)

    mock_from_snapshot = MagicMock()
    mock_from_snapshot.account_generation = 1
    monkeypatch.setattr(recurrence_inbox_db, "_from_snapshot", lambda *args, **kwargs: mock_from_snapshot)

    # 1. Non-string None error_code does not raise TypeError
    recurrence_inbox_db.retry_recurrence_receipt("  u1  ", "  r1  ", error_code=None, account_generation=1, firestore_client=mock_client)
    update_call = mock_txn.update.call_args[0][1]
    assert update_call["last_error_code"] == ""

    # 2. Integer error_code is safely stringified
    recurrence_inbox_db.retry_recurrence_receipt("u1", "r1", error_code=504, account_generation=1, firestore_client=mock_client)
    update_call = mock_txn.update.call_args[0][1]
    assert update_call["last_error_code"] == "504"

    # 3. Exception object error_code is safely stringified
    recurrence_inbox_db.retry_recurrence_receipt("u1", "r1", error_code=RuntimeError("upstream timeout"), account_generation=1, firestore_client=mock_client)
    update_call = mock_txn.update.call_args[0][1]
    assert update_call["last_error_code"] == "upstream timeout"

    # 4. Long error string is truncated cleanly to 128 characters
    long_msg = "X" * 200
    recurrence_inbox_db.retry_recurrence_receipt("u1", "r1", error_code=long_msg, account_generation=1, firestore_client=mock_client)
    update_call = mock_txn.update.call_args[0][1]
    assert len(update_call["last_error_code"]) == 128
    assert update_call["last_error_code"] == "X" * 128
