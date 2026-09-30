"""Hermetic unit tests for backend/database/person_aliases.py resilience guards."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch
import pytest

from google.api_core.exceptions import NotFound

from database.person_aliases import (
    normalized_person_alias,
    rename_person_retaining_aliases,
    update_person_name_transaction,
)


# --- Tests for normalized_person_alias ---

@pytest.mark.parametrize("invalid_val", [None, 123, 45.6, [], {}, True])
def test_normalized_person_alias_rejects_non_string(invalid_val):
    assert normalized_person_alias(invalid_val) is None


@pytest.mark.parametrize("blank_val", ["", "   ", "\t\n  \r "])
def test_normalized_person_alias_rejects_blank_strings(blank_val):
    assert normalized_person_alias(blank_val) is None


def test_normalized_person_alias_rejects_oversized_strings():
    oversized = "a" * 129
    assert normalized_person_alias(oversized) is None
    exact_limit = "a" * 128
    assert normalized_person_alias(exact_limit) == exact_limit


def test_normalized_person_alias_normalizes_whitespace():
    raw = "   Bob   \t  Smith \n   Jr.  "
    assert normalized_person_alias(raw) == "Bob Smith Jr."


# --- Tests for update_person_name_transaction ---

def test_update_person_name_transaction_rejects_none_args():
    # If transaction or person_ref is None, must return False safely
    assert update_person_name_transaction.to_wrap(None, MagicMock(), "Alice") is False
    assert update_person_name_transaction.to_wrap(MagicMock(), None, "Alice") is False


def test_update_person_name_transaction_rejects_invalid_name():
    transaction = MagicMock()
    person_ref = MagicMock()
    assert update_person_name_transaction.to_wrap(transaction, person_ref, "   ") is False
    assert update_person_name_transaction.to_wrap(transaction, person_ref, None) is False
    transaction.update.assert_not_called()


def test_update_person_name_transaction_returns_false_when_doc_missing():
    transaction = MagicMock()
    person_ref = MagicMock()
    snapshot = person_ref.get.return_value
    snapshot.exists = False
    assert update_person_name_transaction.to_wrap(transaction, person_ref, "Alice") is False
    transaction.update.assert_not_called()


def test_update_person_name_transaction_caps_stored_aliases_to_24():
    transaction = MagicMock()
    person_ref = MagicMock()
    snapshot = person_ref.get.return_value
    snapshot.exists = True
    # 40 existing distinct aliases
    existing_aliases = [f"Alias {i}" for i in range(40)]
    snapshot.to_dict.return_value = {
        "name": "Old Name",
        "aliases": existing_aliases,
    }

    result = update_person_name_transaction.to_wrap(transaction, person_ref, "New Name")
    assert result is True
    payload = transaction.update.call_args.args[1]
    assert payload["name"] == "New Name"
    # Aliases must be capped at 24 entries maximum
    assert len(payload["aliases"]) <= 24
    assert payload["aliases"][-1] == "Old Name"


def test_update_person_name_transaction_handles_corrupt_stored_aliases():
    transaction = MagicMock()
    person_ref = MagicMock()
    snapshot = person_ref.get.return_value
    snapshot.exists = True
    snapshot.to_dict.return_value = {
        "name": "Bob",
        "aliases": "not-a-list",
    }
    result = update_person_name_transaction.to_wrap(transaction, person_ref, "Robert")
    assert result is True
    payload = transaction.update.call_args.args[1]
    assert payload["name"] == "Robert"
    assert payload["aliases"] == ["Bob"]


# --- Tests for rename_person_retaining_aliases ---

@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, []])
def test_rename_person_retaining_aliases_rejects_invalid_uid(invalid_uid):
    fake_db = MagicMock()
    assert rename_person_retaining_aliases(fake_db, invalid_uid, "p1", "Alice") is False
    fake_db.collection.assert_not_called()


@pytest.mark.parametrize("invalid_pid", [None, "", "   ", 123, []])
def test_rename_person_retaining_aliases_rejects_invalid_person_id(invalid_pid):
    fake_db = MagicMock()
    assert rename_person_retaining_aliases(fake_db, "u1", invalid_pid, "Alice") is False
    fake_db.collection.assert_not_called()


@pytest.mark.parametrize("invalid_name", [None, "", "   ", "a" * 129])
def test_rename_person_retaining_aliases_rejects_invalid_name_before_txn(invalid_name):
    fake_db = MagicMock()
    assert rename_person_retaining_aliases(fake_db, "u1", "p1", invalid_name) is False
    fake_db.collection.assert_not_called()


def test_rename_person_retaining_aliases_falls_back_to_default_client():
    fake_default_client = MagicMock()
    person_ref = fake_default_client.collection.return_value.document.return_value.collection.return_value.document.return_value
    person_ref.get.return_value.exists = True
    person_ref.get.return_value.to_dict.return_value = {"name": "Old"}

    with patch("database.person_aliases.get_firestore_client", return_value=fake_default_client):
        with patch("database.person_aliases.update_person_name_transaction", return_value=True):
            res = rename_person_retaining_aliases(None, "u1", "p1", "New")
            assert res is True
            fake_default_client.collection.assert_called_with("users")


def test_rename_person_retaining_aliases_catches_not_found():
    fake_db = MagicMock()
    with patch(
        "database.person_aliases.update_person_name_transaction",
        side_effect=NotFound("document missing"),
    ):
        assert rename_person_retaining_aliases(fake_db, "u1", "p1", "Alice") is False
