"""Unit tests for GET /v1/folders/by-category/{category_mapping} and its db helper.

routers.folders and database.folders import cleanly, so both the endpoint and the
helper are tested directly with patch.object (no sys.modules mutation).
"""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")

from unittest.mock import patch

import pytest
from fastapi import HTTPException

import database.folders as folders_db
from routers import folders as folders_router


# ---------------------------------------------------------------------------
# db helper: get_folder_by_category_mapping
# ---------------------------------------------------------------------------
def test_helper_finds_matching_category():
    folders = [
        {"id": "1", "category_mapping": "food"},
        {"id": "2", "category_mapping": "work"},
    ]
    with patch.object(folders_db, "get_folders", return_value=folders):
        result = folders_db.get_folder_by_category_mapping("u1", "work")
    assert result["id"] == "2"


def test_helper_returns_none_when_no_match():
    with patch.object(folders_db, "get_folders", return_value=[{"id": "1", "category_mapping": "food"}]):
        assert folders_db.get_folder_by_category_mapping("u1", "missing") is None


def test_helper_returns_none_on_empty():
    with patch.object(folders_db, "get_folders", return_value=[]):
        assert folders_db.get_folder_by_category_mapping("u1", "any") is None


# ---------------------------------------------------------------------------
# endpoint: get_folder_by_category
# ---------------------------------------------------------------------------
def test_endpoint_returns_folder():
    folder = {"id": "1", "name": "Food", "category_mapping": "food"}
    with patch.object(folders_db, "get_folder_by_category_mapping", return_value=folder) as m:
        result = folders_router.get_folder_by_category(category_mapping="food", uid="u1")
    assert result == folder
    m.assert_called_once_with("u1", "food")


def test_endpoint_404_when_absent():
    with patch.object(folders_db, "get_folder_by_category_mapping", return_value=None):
        with pytest.raises(HTTPException) as exc:
            folders_router.get_folder_by_category(category_mapping="none", uid="u1")
    assert exc.value.status_code == 404
