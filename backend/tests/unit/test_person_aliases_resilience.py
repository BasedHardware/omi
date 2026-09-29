"""Hermetic unit tests for backend/database/person_aliases.py resilience, validation, and boundaries."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import NotFound

import database.person_aliases as aliases_db


def test_clean_id_validates_and_normalizes():
    assert aliases_db._clean_id("user-123") == "user-123"
    assert aliases_db._clean_id("  p-abc  ") == "p-abc"
    assert aliases_db._clean_id("user_456") == "user_456"

    # Invalid / pathological IDs
    assert aliases_db._clean_id("") == ""
    assert aliases_db._clean_id("   ") == ""
    assert aliases_db._clean_id(None) == ""
    assert aliases_db._clean_id(12345) == ""  # type: ignore
    assert aliases_db._clean_id("users/admin") == ""
    assert aliases_db._clean_id("users\\admin") == ""
    assert aliases_db._clean_id("../evil") == ""
    assert aliases_db._clean_id("x" * 129) == ""


def test_normalized_person_alias_validates_and_cleans():
    assert aliases_db.normalized_person_alias("Alice") == "Alice"
    assert aliases_db.normalized_person_alias("  Bob   Smith  ") == "Bob Smith"

    assert aliases_db.normalized_person_alias("") is None
    assert aliases_db.normalized_person_alias("   ") is None
    assert aliases_db.normalized_person_alias(None) is None
    assert aliases_db.normalized_person_alias(12345) is None  # type: ignore
    assert aliases_db.normalized_person_alias("a" * 129) is None
    assert aliases_db.normalized_person_alias("Hello\x00World") is None


def test_rename_person_retaining_aliases_rejects_invalid_inputs_without_io():
    mock_client = MagicMock()

    # Invalid uid
    assert aliases_db.rename_person_retaining_aliases(mock_client, "", "p1", "Alice") is False
    assert aliases_db.rename_person_retaining_aliases(mock_client, "   ", "p1", "Alice") is False
    assert aliases_db.rename_person_retaining_aliases(mock_client, "user/admin", "p1", "Alice") is False

    # Invalid person_id
    assert aliases_db.rename_person_retaining_aliases(mock_client, "u1", "", "Alice") is False
    assert aliases_db.rename_person_retaining_aliases(mock_client, "u1", "p/admin", "Alice") is False

    # Invalid name
    assert aliases_db.rename_person_retaining_aliases(mock_client, "u1", "p1", "") is False
    assert aliases_db.rename_person_retaining_aliases(mock_client, "u1", "p1", "    ") is False
    assert aliases_db.rename_person_retaining_aliases(mock_client, "u1", "p1", "a" * 130) is False

    assert not mock_client.collection.called
    assert not mock_client.transaction.called


def test_rename_person_retaining_aliases_maps_not_found_to_false():
    mock_client = MagicMock()
    with patch.object(
        aliases_db,
        "update_person_name_transaction",
        side_effect=NotFound("Person document deleted"),
    ):
        result = aliases_db.rename_person_retaining_aliases(mock_client, "u1", "p1", "Alice")
        assert result is False


def test_rename_person_retaining_aliases_handles_transaction_exception():
    mock_client = MagicMock()
    with patch.object(
        aliases_db,
        "update_person_name_transaction",
        side_effect=Exception("Firestore 503 deadline exceeded"),
    ):
        result = aliases_db.rename_person_retaining_aliases(mock_client, "u1", "p1", "Alice")
        assert result is False


def test_rename_person_retaining_aliases_success_flow():
    mock_client = MagicMock()
    mock_coll1 = MagicMock()
    mock_doc1 = MagicMock()
    mock_coll2 = MagicMock()
    mock_doc2 = MagicMock()

    mock_client.collection.return_value = mock_coll1
    mock_coll1.document.return_value = mock_doc1
    mock_doc1.collection.return_value = mock_coll2
    mock_coll2.document.return_value = mock_doc2

    with patch.object(aliases_db, "update_person_name_transaction", return_value=True) as mock_tx:
        result = aliases_db.rename_person_retaining_aliases(mock_client, "  u1  ", "  p1  ", "  Alice Wonder  ")
        assert result is True
        mock_client.collection.assert_called_once_with("users")
        mock_coll1.document.assert_called_once_with("u1")
        mock_doc1.collection.assert_called_once_with("people")
        mock_coll2.document.assert_called_once_with("p1")
        mock_tx.assert_called_once()


def test_update_person_name_transaction_nonexistent_person_returns_false():
    transaction = MagicMock()
    person_ref = MagicMock()
    snapshot = person_ref.get.return_value
    snapshot.exists = False

    fn = getattr(aliases_db.update_person_name_transaction, "to_wrap", aliases_db.update_person_name_transaction)
    assert fn(transaction, person_ref, "Alice") is False
    assert not transaction.update.called


def test_update_person_name_transaction_rejects_empty_name():
    transaction = MagicMock()
    person_ref = MagicMock()
    snapshot = person_ref.get.return_value
    snapshot.exists = True
    snapshot.to_dict.return_value = {"name": "Bob"}

    fn = getattr(aliases_db.update_person_name_transaction, "to_wrap", aliases_db.update_person_name_transaction)
    assert fn(transaction, person_ref, "   ") is False
    assert not transaction.update.called


def test_update_person_name_transaction_retains_and_caps_aliases():
    transaction = MagicMock()
    person_ref = MagicMock()
    snapshot = person_ref.get.return_value
    snapshot.exists = True
    snapshot.to_dict.return_value = {
        "name": "Alice",
        "aliases": ["Ally", "A. Smith"],
    }

    fn = getattr(aliases_db.update_person_name_transaction, "to_wrap", aliases_db.update_person_name_transaction)
    res = fn(transaction, person_ref, " Alicia Smith ")
    assert res is True

    transaction.update.assert_called_once()
    payload = transaction.update.call_args[0][1]
    assert payload["name"] == "Alicia Smith"
    # "Alice" (prior name) is added to aliases, "Alicia Smith" is the new name
    assert payload["aliases"] == ["Ally", "A. Smith", "Alice"]
    assert isinstance(payload["updated_at"], datetime)


def test_update_person_name_transaction_caps_at_24_aliases():
    transaction = MagicMock()
    person_ref = MagicMock()
    snapshot = person_ref.get.return_value
    snapshot.exists = True
    snapshot.to_dict.return_value = {
        "name": "Old Name",
        "aliases": [f"Alias {i}" for i in range(30)],
    }

    fn = getattr(aliases_db.update_person_name_transaction, "to_wrap", aliases_db.update_person_name_transaction)
    res = fn(transaction, person_ref, "Brand New Name")
    assert res is True

    payload = transaction.update.call_args[0][1]
    assert len(payload["aliases"]) <= 24
    assert payload["aliases"][-1] == "Old Name"


def test_get_person_aliases_validation_and_retrieval():
    mock_client = MagicMock()
    mock_ref = MagicMock()
    mock_client.collection.return_value.document.return_value.collection.return_value.document.return_value = mock_ref

    # Invalid input
    assert aliases_db.get_person_aliases(mock_client, "", "p1") == []
    assert aliases_db.get_person_aliases(mock_client, "u1", "") == []

    # Non-existent doc
    mock_ref.get.return_value.exists = False
    assert aliases_db.get_person_aliases(mock_client, "u1", "p1") == []

    # Valid doc with aliases
    mock_ref.get.return_value.exists = True
    mock_ref.get.return_value.to_dict.return_value = {"aliases": ["Ally", "  Bobby  ", "Ally", "", None, 123]}
    assert aliases_db.get_person_aliases(mock_client, "u1", "p1") == ["Ally", "Bobby"]

    # Exception boundary
    mock_ref.get.side_effect = Exception("Storage error")
    assert aliases_db.get_person_aliases(mock_client, "u1", "p1") == []
