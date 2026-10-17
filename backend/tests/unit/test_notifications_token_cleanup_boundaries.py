"""Hermetic unit tests for notification token sanitization, bulk cleanup, and batch safety."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

sys.path.insert(0, str(BACKEND_DIR))
from tests.unit.memory_import_isolation import install_database_client_stub

install_database_client_stub()

import database.notifications as notifications_db


def test_remove_invalid_token_resilience():
    fake_client = MagicMock()
    doc = MagicMock()
    query = fake_client.collection_group.return_value.where.return_value.limit.return_value
    query.stream.return_value = [doc]

    with patch.object(notifications_db, "db", fake_client):
        # Valid token
        notifications_db.remove_invalid_token("  valid-token  ")
        fake_client.collection_group.assert_called_with("fcm_tokens")
        doc.reference.delete.assert_called_once()

        # Empty, whitespace, or invalid tokens return early
        fake_client.reset_mock()
        notifications_db.remove_invalid_token("")
        notifications_db.remove_invalid_token("   ")
        notifications_db.remove_invalid_token(None)
        fake_client.collection_group.assert_not_called()


def test_remove_bulk_tokens_deduplication_and_batch_commit():
    fake_client = MagicMock()
    batch = MagicMock()
    fake_client.batch.return_value = batch

    doc1 = MagicMock()
    doc2 = MagicMock()
    query = fake_client.collection_group.return_value.where.return_value
    query.stream.return_value = [doc1, doc2]

    with patch.object(notifications_db, "db", fake_client):
        tokens = ["token-1", " token-1 ", "token-2", "", "   ", None]
        notifications_db.remove_bulk_tokens(tokens)

        fake_client.collection_group.assert_called_with("fcm_tokens")
        assert batch.delete.call_count == 2
        batch.commit.assert_called_once()
