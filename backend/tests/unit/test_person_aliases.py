from unittest.mock import MagicMock
from google.cloud.firestore_v1 import FieldFilter
import pytest

from database.person_aliases import (
    normalized_person_alias,
    find_person_by_name,
    list_people,
    rename_person_retaining_aliases,
    dismiss_person_soft,
    update_person_name_transaction,
    dismiss_person_transaction,
)


def test_normalized_person_alias_valid():
    assert normalized_person_alias("John Doe") == "John Doe"
    assert normalized_person_alias("  Alice   Smith  ") == "Alice Smith"
    assert normalized_person_alias("Bob") == "Bob"


def test_normalized_person_alias_invalid():
    assert normalized_person_alias("") is None
    assert normalized_person_alias("   ") is None
    assert normalized_person_alias(None) is None
    assert normalized_person_alias(123) is None
    assert normalized_person_alias("A" * 129) is None


def test_find_person_by_name_exact_match():
    db = MagicMock()
    doc_mock = MagicMock()
    doc_mock.id = "person_1"
    doc_mock.to_dict.return_value = {"name": "Alice", "is_dismissed": False}

    query_mock = db.collection.return_value.document.return_value.collection.return_value.where.return_value
    query_mock.stream.return_value = [doc_mock]

    res = find_person_by_name(db, "user_123", "  Alice  ")

    assert res == {"id": "person_1", "name": "Alice", "is_dismissed": False}
    db.collection.assert_called_with("users")
    db.collection("users").document.assert_called_with("user_123")
    user_doc = db.collection("users").document("user_123")
    user_doc.collection.assert_called_with("people")


def test_find_person_by_name_fallback_to_alias():
    db = MagicMock()
    doc_mock = MagicMock()
    doc_mock.id = "person_2"
    doc_mock.to_dict.return_value = {"name": "Robert Smith", "aliases": ["Bob"], "is_dismissed": False}

    people_coll = db.collection.return_value.document.return_value.collection.return_value

    # First query (name == 'Bob') returns empty
    name_query = MagicMock()
    name_query.stream.return_value = []

    # Second query (aliases array_contains 'Bob') returns doc_mock
    alias_query = MagicMock()
    alias_query.stream.return_value = [doc_mock]

    people_coll.where.side_effect = [name_query, alias_query]

    res = find_person_by_name(db, "user_123", "Bob")

    assert res == {"id": "person_2", "name": "Robert Smith", "aliases": ["Bob"], "is_dismissed": False}
    assert people_coll.where.call_count == 2


def test_find_person_by_name_skips_dismissed():
    db = MagicMock()
    dismissed_doc = MagicMock()
    dismissed_doc.to_dict.return_value = {"name": "Alice", "is_dismissed": True}

    active_doc = MagicMock()
    active_doc.id = "person_active"
    active_doc.to_dict.return_value = {"name": "Alice", "is_dismissed": False}

    query_mock = db.collection.return_value.document.return_value.collection.return_value.where.return_value
    query_mock.stream.return_value = [dismissed_doc, active_doc]

    res = find_person_by_name(db, "user_123", "Alice")
    assert res == {"id": "person_active", "name": "Alice", "is_dismissed": False}


def test_find_person_by_name_empty_or_invalid():
    db = MagicMock()
    assert find_person_by_name(db, "", "Alice") is None
    assert find_person_by_name(db, "user_123", "") is None
    assert find_person_by_name(db, "user_123", "   ") is None
    assert find_person_by_name(db, "user_123", None) is None
    db.collection.assert_not_called()


def test_find_person_by_name_handles_stream_exception():
    db = MagicMock()
    people_coll = db.collection.return_value.document.return_value.collection.return_value
    people_coll.where.side_effect = RuntimeError("Firestore unavailable")

    res = find_person_by_name(db, "user_123", "Alice")
    assert res is None


def test_list_people_filtering():
    db = MagicMock()
    doc1 = MagicMock()
    doc1.id = "p1"
    doc1.to_dict.return_value = {"name": "Alice", "is_dismissed": False}

    doc2 = MagicMock()
    doc2.id = "p2"
    doc2.to_dict.return_value = {"name": "Dismissed Bob", "is_dismissed": True}

    people_coll = db.collection.return_value.document.return_value.collection.return_value
    people_coll.stream.return_value = [doc1, doc2]

    # Without dismissed
    active_only = list_people(db, "user_123", include_dismissed=False)
    assert len(active_only) == 1
    assert active_only[0]["id"] == "p1"

    # With dismissed
    all_people = list_people(db, "user_123", include_dismissed=True)
    assert len(all_people) == 2


def test_list_people_empty_uid_returns_empty():
    db = MagicMock()
    assert list_people(db, "") == []
    assert list_people(db, "   ") == []
    db.collection.assert_not_called()


def test_update_person_name_transaction_retains_aliases():
    tx = MagicMock()
    ref = MagicMock()
    snap = MagicMock()
    snap.exists = True
    snap.to_dict.return_value = {
        "name": "Johnny",
        "aliases": ["John", "Jon"],
    }
    ref.get.return_value = snap

    func = getattr(update_person_name_transaction, "__wrapped__", update_person_name_transaction)
    res = func(tx, ref, "Jonathan")

    assert res is True
    tx.update.assert_called_once()
    patch = tx.update.call_args[0][1]
    assert patch["name"] == "Jonathan"
    assert "Johnny" in patch["aliases"]
    assert "John" in patch["aliases"]
    assert "Jon" in patch["aliases"]
    assert patch["is_user_created"] is True


def test_dismiss_person_transaction():
    tx = MagicMock()
    ref = MagicMock()
    snap = MagicMock()
    snap.exists = True
    snap.to_dict.return_value = {"name": "Alice", "is_dismissed": False}
    ref.get.return_value = snap

    func = getattr(dismiss_person_transaction, "__wrapped__", dismiss_person_transaction)
    res = func(tx, ref)

    assert res is True
    tx.update.assert_called_once()
    patch = tx.update.call_args[0][1]
    assert patch["is_dismissed"] is True
    assert "dismissed_at" in patch
