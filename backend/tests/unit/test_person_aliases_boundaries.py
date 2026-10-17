"""Hermetic unit tests for person aliases sanitization, query resilience, and client defaults."""

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

from database import person_aliases


def test_normalized_person_alias_validations():
    assert person_aliases.normalized_person_alias("  Alice   Smith  ") == "Alice Smith"
    assert person_aliases.normalized_person_alias("") is None
    assert person_aliases.normalized_person_alias("   ") is None
    assert person_aliases.normalized_person_alias(123) is None
    assert person_aliases.normalized_person_alias("a" * 129) is None
    assert person_aliases.normalized_person_alias("a" * 128) == "a" * 128


def test_list_people_skips_dismissed_and_corrupted():
    fake_client = MagicMock()
    doc_active = MagicMock()
    doc_active.id = "p1"
    doc_active.to_dict.return_value = {"name": "Bob", "is_dismissed": False}

    doc_dismissed = MagicMock()
    doc_dismissed.id = "p2"
    doc_dismissed.to_dict.return_value = {"name": "Charlie", "is_dismissed": True}

    doc_corrupt = MagicMock()
    doc_corrupt.id = "p3"
    doc_corrupt.to_dict.return_value = None

    people_ref = fake_client.collection.return_value.document.return_value.collection.return_value
    people_ref.stream.return_value = [doc_active, doc_dismissed, doc_corrupt]

    # Without dismissed
    active = person_aliases.list_people(fake_client, "u1", include_dismissed=False)
    assert len(active) == 1
    assert active[0]["name"] == "Bob"
    assert active[0]["id"] == "p1"

    # With dismissed
    all_people = person_aliases.list_people(fake_client, "u1", include_dismissed=True)
    assert len(all_people) == 2
    assert all_people[0]["id"] == "p1"
    assert all_people[1]["id"] == "p2"


def test_find_person_by_name_boundaries():
    fake_client = MagicMock()
    # Blank or invalid query should return None immediately
    assert person_aliases.find_person_by_name(fake_client, "u1", "") is None
    assert person_aliases.find_person_by_name(fake_client, "u1", "   ") is None
    assert person_aliases.find_person_by_name(fake_client, "u1", None) is None

    doc_dismissed = MagicMock()
    doc_dismissed.id = "p1"
    doc_dismissed.to_dict.return_value = {"name": "Alice", "is_dismissed": True}

    doc_active = MagicMock()
    doc_active.id = "p2"
    doc_active.to_dict.return_value = {"name": "Alice", "is_dismissed": False}

    query = fake_client.collection.return_value.document.return_value.collection.return_value.where.return_value
    query.stream.return_value = [doc_dismissed, doc_active]

    found = person_aliases.find_person_by_name(fake_client, "u1", "  Alice  ")
    assert found is not None
    assert found["id"] == "p2"
    assert found["name"] == "Alice"


def test_client_fallback_to_get_firestore_client():
    fake_client = MagicMock()
    with patch.object(person_aliases, "get_firestore_client", return_value=fake_client):
        # Passes db_client=None
        res = person_aliases.list_people(None, "u1")
        assert isinstance(res, list)
        fake_client.collection.assert_called_with("users")
