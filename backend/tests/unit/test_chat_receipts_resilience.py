"""Hermetic unit tests for chat receipts message lookup, validation, and error handling."""

import os
from unittest.mock import MagicMock
import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.chat_receipts as chat_receipts_db


def test_message_receipt_snapshot_success():
    mock_user_ref = MagicMock()
    mock_match = MagicMock()
    mock_user_ref.collection.return_value.where.return_value.limit.return_value.stream.return_value = [mock_match]

    res = chat_receipts_db.message_receipt_snapshot(mock_user_ref, "msg-123", transaction="mock-tx")
    assert res == mock_match
    mock_user_ref.collection.assert_called_once_with("messages")
    mock_user_ref.collection.return_value.where.assert_called_once_with("id", "==", "msg-123")


def test_message_receipt_snapshot_not_found():
    mock_user_ref = MagicMock()
    mock_user_ref.collection.return_value.where.return_value.limit.return_value.stream.return_value = []

    res = chat_receipts_db.message_receipt_snapshot(mock_user_ref, "msg-missing", None)
    assert res is None


def test_message_receipt_snapshot_empty_inputs():
    assert chat_receipts_db.message_receipt_snapshot(None, "msg-1", None) is None
    assert chat_receipts_db.message_receipt_snapshot(MagicMock(), "", None) is None
    assert chat_receipts_db.message_receipt_snapshot(MagicMock(), "   ", None) is None


def test_message_receipt_snapshot_contention_propagates():
    mock_user_ref = MagicMock()
    mock_user_ref.collection.side_effect = Exception("Firestore transaction contention")

    with pytest.raises(Exception, match="Firestore transaction contention"):
        chat_receipts_db.message_receipt_snapshot(mock_user_ref, "msg-fail", transaction="mock-tx")
