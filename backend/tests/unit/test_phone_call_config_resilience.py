"""Hermetic unit tests for phone call config resilience, client injection, and catalog fallbacks."""

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

import database.phone_call_config as pcc


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
    monkeypatch.setattr(pcc, "get_memory_cache", lambda: cache)
    return cache


def test_fetch_config_missing_doc_returns_catalog_defaults():
    mock_doc = MagicMock()
    mock_doc.exists = False
    mock_client = MagicMock()
    mock_client.collection.return_value.document.return_value.get.return_value = mock_doc

    free_cfg = pcc.get_free_plan_config(client=mock_client)
    assert free_cfg["phone_calls_profile"] == "free"
    assert "max_duration_seconds" in free_cfg
    assert free_cfg["effective_overlay"]["source"] == "catalog"

    paid_cfg = pcc.get_paid_plan_config(client=mock_client)
    assert paid_cfg["phone_calls_profile"] == "paid"
    assert paid_cfg["effective_overlay"]["source"] == "catalog"


def test_fetch_config_exception_fails_open_to_catalog():
    mock_client = MagicMock()
    mock_client.collection.side_effect = Exception("Firestore unavailable")

    cfg = pcc.get_config_for_plan("basic", client=mock_client)
    assert cfg["phone_calls_profile"] == "free"
    assert cfg["effective_overlay"]["source"] == "catalog"


def test_custom_firestore_overlay_is_applied():
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {
        "paid_plan": {
            "max_duration_seconds": 3600,
            "monthly_call_limit": 100,
        }
    }
    mock_client = MagicMock()
    mock_client.collection.return_value.document.return_value.get.return_value = mock_doc

    cfg = pcc.get_paid_plan_config(client=mock_client)
    assert cfg["max_duration_seconds"] == 3600
    assert cfg["monthly_call_limit"] == 100
    assert cfg["effective_overlay"]["source"] == "firestore"
    assert cfg["effective_overlay"]["declared"] is True
