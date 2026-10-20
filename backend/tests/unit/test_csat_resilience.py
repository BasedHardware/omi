"""Hermetic unit tests for CSAT client injection, comment bounds, and Firestore fail-open resilience."""

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

import database.csat as csat_db


def test_fetch_config_firestore_exception_fails_open():
    mock_client = MagicMock()
    mock_client.collection.side_effect = Exception("Transient Firestore timeout")

    # Should not raise exception, returns DEFAULT_CONFIG fallback
    cfg = csat_db._fetch_config(firestore_client=mock_client)
    assert cfg["enabled"] is True
    assert cfg["title"] == csat_db.DEFAULT_TITLE
    assert cfg["question_threshold"] == 3


def test_get_product_config_caches_fail_open_for_ttl():
    mock_client = MagicMock()
    mock_client.collection.side_effect = Exception("Transient Firestore timeout")

    # Clear cache before testing
    cache = csat_db.get_memory_cache()
    if hasattr(cache, "invalidate"):
        cache.invalidate(csat_db._CACHE_KEY)

    # First call fails open and caches fallback
    cfg1 = csat_db.get_product_config(firestore_client=mock_client)
    assert cfg1["enabled"] is True
    assert cfg1["title"] == csat_db.DEFAULT_TITLE
    assert mock_client.collection.call_count == 1

    # Second call within TTL served from cache
    cfg2 = csat_db.get_product_config(firestore_client=mock_client)
    assert cfg2["enabled"] is True
    assert cfg2["title"] == csat_db.DEFAULT_TITLE
    assert mock_client.collection.call_count == 1


def test_submit_rating_truncates_long_comment():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_client.collection.return_value.document.return_value = mock_doc

    long_comment = "x" * 600
    doc_id, created = csat_db.submit_rating(
        uid="uid-100",
        platform="macos",
        app_version="1.0.0",
        score=2,
        comment=long_comment,
        revision=1,
        firestore_client=mock_client,
    )
    assert created is True
    assert doc_id == "macos_uid-100"

    created_payload = mock_doc.create.call_args[0][0]
    assert len(created_payload["comment"]) == csat_db.MAX_COMMENT_LENGTH
    assert created_payload["comment"] == "x" * 500


def test_submit_rating_handles_whitespace_platform():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_client.collection.return_value.document.return_value = mock_doc

    doc_id, created = csat_db.submit_rating(
        uid="uid-200",
        platform="  ios  ",
        app_version="  2.0.0+1  ",
        score=1,
        comment="needs dark mode",
        revision=2,
        firestore_client=mock_client,
    )
    assert created is True
    assert doc_id == "ios_uid-200"

    created_payload = mock_doc.create.call_args[0][0]
    assert created_payload["platform"] == "ios"
    assert created_payload["app_version"] == "2.0.0+1"
