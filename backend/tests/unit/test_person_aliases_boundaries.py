"""Authoritative unit tests for person_aliases malformed doc filtering and empty query bounds."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import database.person_aliases as person_aliases_db


def test_list_people_filters_corrupt_and_dismissed():
    mock_db = MagicMock()
    doc_valid = MagicMock()
    doc_valid.id = "p-1"
    doc_valid.to_dict.return_value = {"name": "Alice", "is_dismissed": False}

    doc_corrupt = MagicMock()
    doc_corrupt.id = "p-corrupt"
    doc_corrupt.to_dict.return_value = None

    doc_dismissed = MagicMock()
    doc_dismissed.id = "p-dismissed"
    doc_dismissed.to_dict.return_value = {"name": "Bob", "is_dismissed": True}

    mock_db.collection.return_value.document.return_value.collection.return_value.stream.return_value = [
        doc_valid,
        doc_corrupt,
        doc_dismissed,
    ]

    res = person_aliases_db.list_people(mock_db, "uid-1")
    assert len(res) == 1
    assert res[0]["name"] == "Alice"
    assert res[0]["id"] == "p-1"


def test_find_person_by_name_empty_or_whitespace():
    mock_db = MagicMock()
    assert person_aliases_db.find_person_by_name(mock_db, "uid-1", "") is None
    assert person_aliases_db.find_person_by_name(mock_db, "uid-1", "   ") is None
    mock_db.collection.assert_not_called()


def test_find_person_by_name_success_and_corrupt():
    mock_db = MagicMock()
    doc_corrupt = MagicMock()
    doc_corrupt.id = "p-bad"
    doc_corrupt.to_dict.return_value = "invalid-string-not-dict"

    doc_good = MagicMock()
    doc_good.id = "p-2"
    doc_good.to_dict.return_value = {"name": "Charlie", "is_dismissed": False}

    mock_query = MagicMock()
    mock_query.stream.return_value = [doc_corrupt, doc_good]
    mock_db.collection.return_value.document.return_value.collection.return_value.where.return_value = mock_query

    found = person_aliases_db.find_person_by_name(mock_db, "uid-1", "Charlie")
    assert found is not None
    assert found["id"] == "p-2"
    assert found["name"] == "Charlie"
