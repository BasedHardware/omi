"""Hermetic unit tests for notification token sanitization, bulk cleanup, and client injection."""

from unittest.mock import MagicMock, patch

import database.notifications as notifications_db


def test_remove_invalid_token_resilience_and_client_injection():
    fake_client = MagicMock()
    doc = MagicMock()
    query = fake_client.collection_group.return_value.where.return_value.limit.return_value
    query.stream.return_value = [doc]

    # Valid token with client injection
    notifications_db.remove_invalid_token("  valid-token  ", firestore_client=fake_client)
    fake_client.collection_group.assert_called_with("fcm_tokens")
    doc.reference.delete.assert_called_once()

    # Empty, whitespace, or invalid tokens return early
    fake_client.reset_mock()
    notifications_db.remove_invalid_token("", firestore_client=fake_client)
    notifications_db.remove_invalid_token("   ", firestore_client=fake_client)
    notifications_db.remove_invalid_token(None, firestore_client=fake_client)
    fake_client.collection_group.assert_not_called()


def test_remove_bulk_tokens_deduplication_and_batch_commit():
    fake_client = MagicMock()
    batch = MagicMock()
    fake_client.batch.return_value = batch

    doc1 = MagicMock()
    doc2 = MagicMock()
    query = fake_client.collection_group.return_value.where.return_value
    query.stream.return_value = [doc1, doc2]

    tokens = ["token-1", " token-1 ", "token-2", "", "   ", None]
    notifications_db.remove_bulk_tokens(tokens, firestore_client=fake_client)

    fake_client.collection_group.assert_called_with("fcm_tokens")
    assert batch.delete.call_count == 2
    batch.commit.assert_called_once()


def test_get_all_tokens_client_injection():
    fake_client = MagicMock()
    token_doc = MagicMock()
    token_doc.to_dict.return_value = {"token": "sub-token"}
    subcol = fake_client.collection.return_value.document.return_value.collection.return_value
    subcol.stream.return_value = [token_doc]

    user_doc = MagicMock()
    user_doc.exists = True
    user_doc.to_dict.return_value = {"fcm_token": "legacy-token"}
    user_ref = fake_client.collection.return_value.document.return_value
    user_ref.get.return_value = user_doc

    tokens = notifications_db.get_all_tokens("uid-1", firestore_client=fake_client)
    assert "sub-token" in tokens
    assert "legacy-token" in tokens
