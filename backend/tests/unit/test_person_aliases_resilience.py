from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch
import pytest

from google.api_core.exceptions import NotFound

from database.person_aliases import (
    dismiss_person_soft,
    dismiss_person_transaction,
    normalized_person_alias,
    rename_person_retaining_aliases,
    update_person_name_transaction,
)


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


def test_update_person_name_transaction_boundary_guards():
    # Null transaction or person_ref returns False
    assert update_person_name_transaction.to_wrap(None, MagicMock(), "Alice") is False
    assert update_person_name_transaction.to_wrap(MagicMock(), None, "Alice") is False

    # Invalid name returns False before accessing snapshot
    mock_ref = MagicMock()
    assert update_person_name_transaction.to_wrap(MagicMock(), mock_ref, "") is False
    assert update_person_name_transaction.to_wrap(MagicMock(), mock_ref, "   ") is False
    assert update_person_name_transaction.to_wrap(MagicMock(), mock_ref, "a" * 130) is False
    mock_ref.get.assert_not_called()


def test_dismiss_person_transaction_boundary_guards():
    assert dismiss_person_transaction.to_wrap(None, MagicMock()) is False
    assert dismiss_person_transaction.to_wrap(MagicMock(), None) is False


def test_rename_person_retaining_aliases_input_validation():
    mock_client = MagicMock()

    # Invalid uid
    assert rename_person_retaining_aliases(mock_client, "", "person_1", "Valid Name") is False
    assert rename_person_retaining_aliases(mock_client, "   ", "person_1", "Valid Name") is False
    assert rename_person_retaining_aliases(mock_client, None, "person_1", "Valid Name") is False
    assert rename_person_retaining_aliases(mock_client, "../bad_uid", "person_1", "Valid Name") is False

    # Invalid person_id
    assert rename_person_retaining_aliases(mock_client, "user_1", "", "Valid Name") is False
    assert rename_person_retaining_aliases(mock_client, "user_1", "   ", "Valid Name") is False
    assert rename_person_retaining_aliases(mock_client, "user_1", None, "Valid Name") is False
    assert rename_person_retaining_aliases(mock_client, "user_1", "person/bad", "Valid Name") is False

    # Invalid name pre-validation
    assert rename_person_retaining_aliases(mock_client, "user_1", "person_1", "") is False
    assert rename_person_retaining_aliases(mock_client, "user_1", "person_1", "   ") is False
    assert rename_person_retaining_aliases(mock_client, "user_1", "person_1", "a" * 130) is False
    mock_client.transaction.assert_not_called()


def test_rename_person_retaining_aliases_client_fallback():
    mock_fallback_client = MagicMock()
    mock_txn = MagicMock()
    mock_fallback_client.transaction.return_value = mock_txn

    with patch("database.person_aliases._client", return_value=mock_fallback_client):
        with patch("database.person_aliases.update_person_name_transaction", return_value=True):
            # Passing db_client=None should not crash with AttributeError
            result = rename_person_retaining_aliases(None, "user_123", "person_456", "New Name")
            assert result is True


def test_dismiss_person_soft_input_validation():
    mock_client = MagicMock()

    assert dismiss_person_soft(mock_client, "", "person_1") is False
    assert dismiss_person_soft(mock_client, "user_1", "") is False
    assert dismiss_person_soft(mock_client, "../bad", "person_1") is False
    assert dismiss_person_soft(mock_client, "user_1", "bad/path") is False
