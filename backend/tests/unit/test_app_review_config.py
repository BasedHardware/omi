"""Hermetic unit tests for server-driven app review config."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
sys.path.insert(0, str(BACKEND_DIR))
from tests.unit.memory_import_isolation import install_database_client_stub

install_database_client_stub()

import database.app_review_config as arc


class _MemoryCache:
    def __init__(self):
        self._store = {}

    def get_or_fetch(self, key, fetch, ttl=None):
        if key not in self._store:
            self._store[key] = fetch()
        return self._store[key]


@pytest.fixture(autouse=True)
def mock_memory_cache(monkeypatch):
    cache = _MemoryCache()
    monkeypatch.setattr(arc, "get_memory_cache", lambda: cache)
    return cache


def test_unsupported_platform():
    assert arc.should_hide_subscription_ui("user-1", "android", "1.0.0") is False
    assert arc.should_hide_subscription_ui("user-1", "windows", "1.0.0") is False
    assert arc.should_hide_subscription_ui("user-1", None, "1.0.0") is False
    assert arc.should_hide_subscription_ui("user-1", "", "1.0.0") is False


def test_reviewer_uid_hides_ui():
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {
        "reviewer_uids": ["apple_reviewer_1", "  apple_reviewer_2  "],
        "hidden_versions": ["2.0.0"],
    }
    mock_client = MagicMock()
    mock_client.collection.return_value.document.return_value.get.return_value = mock_doc

    # Matched UID -> True
    assert arc.should_hide_subscription_ui("apple_reviewer_1", "ios", "1.5.0", client=mock_client) is True
    # Matched UID with whitespace -> True
    assert arc.should_hide_subscription_ui("apple_reviewer_2", "ios", "1.5.0", client=mock_client) is True
    # Non-matched UID, non-hidden version -> False
    assert arc.should_hide_subscription_ui("normal_user", "ios", "1.5.0", client=mock_client) is False


def test_hidden_version_comparison():
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {
        "reviewer_uids": [],
        "hidden_versions": ["1.0.531", "2.1.0+999"],
    }
    mock_client = MagicMock()
    mock_client.collection.return_value.document.return_value.get.return_value = mock_doc

    # Matches semantic version 1.0.531
    assert arc.should_hide_subscription_ui("user_xyz", "ios", "1.0.531+607", client=mock_client) is True
    # Matches build version
    assert arc.should_hide_subscription_ui("user_xyz", "macos", "2.1.0+999", client=mock_client) is True
    # Does not match
    assert arc.should_hide_subscription_ui("user_xyz", "ios", "1.0.532", client=mock_client) is False


def test_firestore_exception_fails_open():
    mock_client = MagicMock()
    mock_client.collection.side_effect = Exception("Firestore unavailable")

    # Should not raise exception, returns False gracefully
    res = arc.should_hide_subscription_ui("user-1", "ios", "1.0.0", client=mock_client)
    assert res is False
