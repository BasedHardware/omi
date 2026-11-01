"""Unit tests verifying resilience and input validation in database/webhook_health.py."""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import NotFound

import database.webhook_health as wh


@pytest.fixture(autouse=True)
def _clean_cache():
    wh._disabled_cache.clear()
    yield
    wh._disabled_cache.clear()


# ============================================================================
# DLQ ENQUEUE RESILIENCE
# ============================================================================


def test_enqueue_dev_webhook_dlq_serializes_non_json_types():
    fake_r = MagicMock()
    with patch.object(wh, "r", fake_r):
        now = datetime.now(timezone.utc)
        payload = {
            "timestamp": now,
            "event_id": uuid.uuid4(),
            "tags": {"alpha", "beta"},
        }
        wh.enqueue_dev_webhook_dlq(
            webhook_name="test-hook",
            webhook_url="https://example.com/webhook",
            status_code=500,
            error="Internal Server Error",
            uid="user-123",
            payload=payload,
        )

        assert fake_r.lpush.called
        call_args = fake_r.lpush.call_args[0]
        key, serialized = call_args[0], call_args[1]
        assert key == "dev_webhook_dlq:user-123"

        decoded = json.loads(serialized)
        assert decoded["webhook_name"] == "test-hook"
        assert decoded["status_code"] == 500
        assert "timestamp" in decoded["payload"]
        assert "event_id" in decoded["payload"]


def test_enqueue_dev_webhook_dlq_handles_none_url_and_blank_uid():
    fake_r = MagicMock()
    with patch.object(wh, "r", fake_r):
        wh.enqueue_dev_webhook_dlq(
            webhook_name="test-hook",
            webhook_url=None,  # type: ignore[arg-type]
            status_code=502,
            error=None,  # type: ignore[arg-type]
            uid="   ",
        )

        assert fake_r.lpush.called
        key, serialized = fake_r.lpush.call_args[0]
        assert key == "dev_webhook_dlq:unknown"

        decoded = json.loads(serialized)
        assert decoded["webhook_url"] == ""
        assert decoded["error"] == ""


# ============================================================================
# CACHE EVICTION & WRITE GUARDS
# ============================================================================


def test_evict_oldest_empty_dict_does_not_raise():
    d = {}
    wh._evict_oldest(d)
    assert d == {}


def test_evict_oldest_handles_mixed_and_corrupt_entry_types():
    d = {
        "valid_tuple": (True, 100.0, 1),
        "valid_scalar": 50.0,
        "corrupt_tuple": (True, "not-a-number"),
        "corrupt_scalar": "invalid",
        "none_val": None,
    }
    wh._evict_oldest(d)
    # Evicts 20% (1 item)
    assert len(d) == 4


def test_set_disabled_state_rejects_blank_and_non_string():
    wh._set_disabled_state("", True)
    wh._set_disabled_state("   ", True)
    wh._set_disabled_state(None, True)  # type: ignore[arg-type]
    wh._set_disabled_state(123, True)  # type: ignore[arg-type]
    assert len(wh._disabled_cache) == 0

    wh._set_disabled_state("  app-abc  ", True)
    assert "app-abc" in wh._disabled_cache
    assert wh._disabled_cache["app-abc"][0] is True


# ============================================================================
# FIRESTORE DISABLE RESILIENCE
# ============================================================================


def test_disable_app_in_firestore_success():
    fake_doc_ref = MagicMock()
    fake_coll = MagicMock()
    fake_coll.document.return_value = fake_doc_ref
    fake_db = MagicMock()
    fake_db.collection.return_value = fake_coll

    with patch.object(wh, "db", fake_db):
        wh.disable_app_in_firestore("app-123", "Too many timeouts", 72)

        fake_coll.document.assert_called_once_with("app-123")
        assert fake_doc_ref.update.called
        update_args = fake_doc_ref.update.call_args[0][0]
        assert update_args["disabled"] is True
        assert update_args["disabled_error"] == "Too many timeouts"
        assert update_args["disabled_failure_duration_hours"] == 72

        # Cache is updated on success
        assert wh.is_app_webhook_disabled("app-123") is True


def test_disable_app_in_firestore_not_found_handled_gracefully():
    fake_doc_ref = MagicMock()
    fake_doc_ref.update.side_effect = NotFound("App doc missing")
    fake_coll = MagicMock()
    fake_coll.document.return_value = fake_doc_ref
    fake_db = MagicMock()
    fake_db.collection.return_value = fake_coll

    with patch.object(wh, "db", fake_db):
        # Should not raise exception
        wh.disable_app_in_firestore("missing-app", "Error", 24)
        fake_coll.document.assert_called_once_with("missing-app")
        # Cache must not be updated if document was not found
        assert wh.is_app_webhook_disabled("missing-app") is False


def test_disable_app_in_firestore_blank_app_id_is_noop():
    fake_db = MagicMock()
    with patch.object(wh, "db", fake_db):
        wh.disable_app_in_firestore("   ", "Error", 24)
        wh.disable_app_in_firestore(None, "Error", 24)  # type: ignore[arg-type]
        fake_db.collection.assert_not_called()


# ============================================================================
# MARKETPLACE APP HEALTH VALIDATION
# ============================================================================


def test_app_webhook_functions_guard_blank_and_invalid_inputs():
    fake_r = MagicMock()
    with patch.object(wh, "r", fake_r):
        assert wh.record_app_webhook_failure("", 500, "Error") == 0
        assert wh.record_app_webhook_failure("   ", 500, "Error") == 0
        assert wh.record_app_webhook_failure(None, 500, "Error") == 0  # type: ignore[arg-type]

        wh.record_app_webhook_success("")
        wh.record_app_webhook_success("   ")
        wh.record_app_webhook_success(None)  # type: ignore[arg-type]

        wh.clear_app_webhook_health("")
        wh.clear_app_webhook_health("   ")
        wh.clear_app_webhook_health(None)  # type: ignore[arg-type]

        assert wh.is_app_webhook_disabled("") is False
        assert wh.is_app_webhook_disabled("   ") is False
        assert wh.is_app_webhook_disabled(None) is False  # type: ignore[arg-type]

        assert wh.get_app_webhook_health("") is None
        assert wh.get_app_webhook_health("   ") is None
        assert wh.get_app_webhook_health(None) is None  # type: ignore[arg-type]

        fake_r.register_script.assert_not_called()
        fake_r.delete.assert_not_called()


# ============================================================================
# DEVELOPER WEBHOOK HEALTH VALIDATION
# ============================================================================


def test_dev_webhook_functions_guard_blank_and_invalid_inputs():
    fake_r = MagicMock()
    with patch.object(wh, "r", fake_r):
        assert wh.record_dev_webhook_failure("", "realtime", 500, "Error") is False
        assert wh.record_dev_webhook_failure("   ", "realtime", 500, "Error") is False
        assert wh.record_dev_webhook_failure(None, "realtime", 500, "Error") is False  # type: ignore[arg-type]

        wh.record_dev_webhook_success("", "realtime")
        wh.record_dev_webhook_success("   ", "realtime")
        wh.record_dev_webhook_success(None, "realtime")  # type: ignore[arg-type]

        fake_r.register_script.assert_not_called()
        fake_r.hset.assert_not_called()
