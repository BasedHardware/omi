import logging

"""Hermetic unit tests for webhook health app auto-disable resilience and input validation."""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from unittest.mock import MagicMock
import pytest

import database.webhook_health as wh_db


def test_disable_app_in_firestore_success():
    mock_client = MagicMock()
    mock_doc_ref = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc_ref.get.return_value = mock_doc
    mock_client.collection.return_value.document.return_value = mock_doc_ref

    res = wh_db.disable_app_in_firestore(
        "app-123", "HTTP 500", 48, firestore_client=mock_client
    )
    assert res is True
    mock_client.collection.assert_called_once_with("plugins_data")
    mock_client.collection.return_value.document.assert_called_once_with("app-123")
    mock_doc_ref.update.assert_called_once()
    payload = mock_doc_ref.update.call_args[0][0]
    assert payload["disabled"] is True
    assert payload["disabled_reason"] == "webhook_failures"
    assert payload["disabled_error"] == "HTTP 500"
    assert payload["disabled_failure_duration_hours"] == 48

    # Assert cache is updated on success
    with wh_db._cache_lock:
        cached = wh_db._disabled_cache.get("app-123")
        assert cached is not None
        assert cached[0] is True


def test_disable_app_in_firestore_none_error_handled():
    mock_client = MagicMock()
    mock_doc_ref = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc_ref.get.return_value = mock_doc
    mock_client.collection.return_value.document.return_value = mock_doc_ref

    # Error is None; must not raise TypeError on slicing
    res = wh_db.disable_app_in_firestore("app-123", None, 24, firestore_client=mock_client)  # type: ignore[arg-type]
    assert res is True
    payload = mock_doc_ref.update.call_args[0][0]
    assert payload["disabled_error"] == ""


def test_disable_app_in_firestore_raw_error_sanitized():
    mock_client = MagicMock()
    mock_doc_ref = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc_ref.get.return_value = mock_doc
    mock_client.collection.return_value.document.return_value = mock_doc_ref

    raw_error = "Connection refused: internal IP 10.0.0.1 failed to connect"
    res = wh_db.disable_app_in_firestore(
        "app-raw-err", raw_error, 24, firestore_client=mock_client
    )
    assert res is True
    payload = mock_doc_ref.update.call_args[0][0]
    assert payload["disabled_error"] == "Webhook delivery failed"


def test_disable_app_in_firestore_closed_set_diagnostic_preserved():
    mock_client = MagicMock()
    mock_doc_ref = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc_ref.get.return_value = mock_doc
    mock_client.collection.return_value.document.return_value = mock_doc_ref

    res = wh_db.disable_app_in_firestore(
        "app-timeout", "TimeoutException", 24, firestore_client=mock_client
    )
    assert res is True
    payload = mock_doc_ref.update.call_args[0][0]
    assert payload["disabled_error"] == "TimeoutException"


def test_disable_app_in_firestore_empty_app_id():
    mock_client = MagicMock()
    assert (
        wh_db.disable_app_in_firestore("", "err", 24, firestore_client=mock_client)
        is False
    )
    assert (
        wh_db.disable_app_in_firestore("   ", "err", 24, firestore_client=mock_client)
        is False
    )
    assert wh_db.disable_app_in_firestore(None, "err", 24, firestore_client=mock_client) is False  # type: ignore[arg-type]
    mock_client.collection.assert_not_called()


def test_disable_app_in_firestore_non_existent_app():
    mock_client = MagicMock()
    mock_doc_ref = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = False
    mock_doc_ref.get.return_value = mock_doc
    mock_client.collection.return_value.document.return_value = mock_doc_ref

    res = wh_db.disable_app_in_firestore(
        "app-missing", "err", 24, firestore_client=mock_client
    )
    assert res is False
    mock_doc_ref.update.assert_not_called()


def test_disable_app_in_firestore_missing_doc_does_not_poison_cache():
    mock_client = MagicMock()
    mock_doc_ref = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = False
    mock_doc_ref.get.return_value = mock_doc
    mock_client.collection.return_value.document.return_value = mock_doc_ref

    app_id = "app-never-existed"
    with wh_db._cache_lock:
        wh_db._disabled_cache.pop(app_id, None)

    res = wh_db.disable_app_in_firestore(
        app_id, "err", 24, firestore_client=mock_client
    )
    assert res is False
    mock_doc_ref.update.assert_not_called()
    with wh_db._cache_lock:
        assert app_id not in wh_db._disabled_cache


def test_disable_app_in_firestore_exception_handled(caplog):
    mock_client = MagicMock()
    mock_doc_ref = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc_ref.get.return_value = mock_doc
    mock_doc_ref.update.side_effect = Exception(
        "Firestore network timeout with internal ip 10.0.0.1"
    )
    mock_client.collection.return_value.document.return_value = mock_doc_ref

    with caplog.at_level(logging.ERROR):
        res = wh_db.disable_app_in_firestore(
            "app-fail", "err", 24, firestore_client=mock_client
        )
    assert res is False
    assert "10.0.0.1" not in caplog.text
    assert "Failed to disable app app-fail in Firestore: Exception" in caplog.text


def test_disable_app_in_firestore_exception_does_not_poison_cache():
    mock_client = MagicMock()
    mock_doc_ref = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc_ref.get.return_value = mock_doc
    mock_doc_ref.update.side_effect = Exception("Firestore network timeout")
    mock_client.collection.return_value.document.return_value = mock_doc_ref

    app_id = "app-fail-cache"
    with wh_db._cache_lock:
        wh_db._disabled_cache.pop(app_id, None)

    res = wh_db.disable_app_in_firestore(
        app_id, "err", 24, firestore_client=mock_client
    )
    assert res is False
    with wh_db._cache_lock:
        assert app_id not in wh_db._disabled_cache
