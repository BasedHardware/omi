from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import GoogleAPICallError

from database.chat_first_delivery_attempts import (
    DEAD_LETTERS_COLLECTION,
    DELIVERY_ATTEMPTS_COLLECTION,
    INTENTS_COLLECTION,
    ChatFirstMalformedDeliveryAttempt,
    DeliveryAttemptState,
    _as_utc,
    _clean_id,
    _ensure_utc,
    dead_letter_payload,
    dead_letter_ref,
    delivery_attempt_ref,
    intent_ref,
    repair_transient_dead_letters,
    requeue_transient_dead_letter,
    reset_malformed_delivery_attempt,
    user_ref,
)
from models.chat_first import CaptureLinkSpec, ProactiveIntent


class TestCleanId:
    def test_valid_id(self):
        assert _clean_id("valid_id") == "valid_id"
        assert _clean_id("user_123-abc") == "user_123-abc"

    def test_empty_id_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            _clean_id("")
        with pytest.raises(ValueError, match="cannot be empty"):
            _clean_id("   ")

    def test_path_traversal_raises(self):
        for invalid in ["../", "/etc/passwd", "..\\", "a/b", "c\\d", "foo/../bar"]:
            with pytest.raises(ValueError, match="invalid path traversal"):
                _clean_id(invalid)

    def test_null_bytes_raises(self):
        with pytest.raises(ValueError, match="null bytes"):
            _clean_id("id\x00")

    def test_length_exceeds_raises(self):
        with pytest.raises(ValueError, match="exceeds maximum length"):
            _clean_id("a" * 65)

    def test_non_string_raises(self):
        with pytest.raises(ValueError, match="must be a string"):
            _clean_id(123)
        with pytest.raises(ValueError, match="must be a string"):
            _clean_id(None)


class TestEnsureUtcAndAsUtc:
    def test_utc_timestamp(self):
        dt = datetime.now(timezone.utc)
        assert _ensure_utc(dt) == dt

    def test_convert_to_utc(self):
        dt = datetime(2023, 1, 1, tzinfo=timezone(timedelta(hours=5)))
        assert _ensure_utc(dt).tzinfo == timezone.utc

    def test_naive_raises(self):
        with pytest.raises(ValueError, match="Naive datetime not allowed"):
            _ensure_utc(datetime.now())

    def test_as_utc_handles_none(self):
        assert _as_utc(None) is None

    def test_as_utc_normalizes_naive(self):
        naive = datetime(2024, 1, 1, 12, 0, 0)
        aware = _as_utc(naive)
        assert aware is not None
        assert aware.tzinfo == timezone.utc


class TestFirestoreReferencesSanitization:
    def test_user_ref_validation(self):
        client = MagicMock()
        user_ref("valid_user", firestore_client=client)
        client.collection.assert_called_once_with("users")
        client.collection.return_value.document.assert_called_once_with("valid_user")

        with pytest.raises(ValueError, match="invalid path traversal"):
            user_ref("../bad_user", firestore_client=client)

    def test_intent_ref_validation(self):
        client = MagicMock()
        intent_ref("valid_user", "valid_intent", firestore_client=client)

        with pytest.raises(ValueError, match="cannot be empty"):
            intent_ref("valid_user", "", firestore_client=client)

        with pytest.raises(ValueError, match="invalid path traversal"):
            intent_ref("bad/user", "valid_intent", firestore_client=client)

    def test_delivery_attempt_ref_validation(self):
        client = MagicMock()
        delivery_attempt_ref("valid_user", "valid_intent", firestore_client=client)

        with pytest.raises(ValueError, match="exceeds maximum length"):
            delivery_attempt_ref("valid_user", "i" * 65, firestore_client=client)

    def test_dead_letter_ref_validation(self):
        client = MagicMock()
        dead_letter_ref("valid_user", "valid_intent", firestore_client=client)

        with pytest.raises(ValueError, match="must be a string"):
            dead_letter_ref("valid_user", None, firestore_client=client)


class TestResetMalformedDeliveryAttempt:
    def test_preserves_valid_and_normalizes_datetime(self):
        now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        intent = MagicMock()
        raw = {
            "fetch_count": 3,
            "requeue_count": 1,
            "materialization_attempts": 2,
            "last_rejection_code": "unknown_error",
        }
        res = reset_malformed_delivery_attempt(intent, raw, now=now)
        assert res["fetch_count"] == 4
        assert res["requeue_count"] == 1
        assert res["last_fetched_at"] == now

    def test_handles_naive_datetime(self):
        now = datetime(2025, 1, 1, 12, 0, 0)
        intent = MagicMock()
        raw = {"fetch_count": 0}
        res = reset_malformed_delivery_attempt(intent, raw, now=now)
        assert res["last_fetched_at"].tzinfo == timezone.utc


class TestDeadLetterPayload:
    def test_dead_letter_payload_normalizes_terminal_at(self):
        intent = ProactiveIntent(
            intent_id="test-intent",
            continuity_key="test-key",
            account_generation=1,
            source="agent_judgment",
            delivery_state="dead_letter",
            dead_letter_reason="unacknowledged_after_fetch_budget",
            blocks=[CaptureLinkSpec(type="captureLink", conversation_id="c1", summary="test")],
            created_at=datetime.now(timezone.utc),
        )
        terminal_at = datetime(2025, 1, 1, 10, 0, 0)
        payload = dead_letter_payload(intent, terminal_at=terminal_at)
        assert payload["last_fetched_at"].tzinfo == timezone.utc


class TestRepairTransientDeadLetters:
    def test_clamps_limit_and_handles_invalid_types(self):
        client = MagicMock()
        collection_mock = MagicMock()
        collection_mock.where.return_value = collection_mock
        collection_mock.order_by.return_value = collection_mock
        collection_mock.limit.return_value = collection_mock
        collection_mock.stream.return_value = []
        client.collection.return_value.document.return_value.collection.return_value = collection_mock

        # High limit clamped to 100 (2 * 100 = 200 passed to limit)
        assert repair_transient_dead_letters("u1", account_generation=1, limit=9999, now=datetime.now(timezone.utc), firestore_client=client) is False
        collection_mock.limit.assert_called_with(200)

        # Zero or negative limit clamped to 1 (2 * 1 = 2 passed to limit)
        assert repair_transient_dead_letters("u1", account_generation=1, limit=0, now=datetime.now(timezone.utc), firestore_client=client) is False
        collection_mock.limit.assert_called_with(2)

        assert repair_transient_dead_letters("u1", account_generation=1, limit=-10, now=datetime.now(timezone.utc), firestore_client=client) is False
        collection_mock.limit.assert_called_with(2)

        # Invalid type falls back to default 10 (2 * 10 = 20 passed to limit)
        assert repair_transient_dead_letters("u1", account_generation=1, limit="bad", now=datetime.now(timezone.utc), firestore_client=client) is False
        collection_mock.limit.assert_called_with(20)

    def test_handles_google_api_call_error(self):
        client = MagicMock()
        client.collection.side_effect = GoogleAPICallError("Network failure")
        failed = repair_transient_dead_letters(
            "u1",
            account_generation=1,
            limit=10,
            now=datetime.now(timezone.utc),
            firestore_client=client,
        )
        assert failed is True

    def test_handles_unexpected_exception(self):
        client = MagicMock()
        client.collection.side_effect = RuntimeError("Fatal crash")
        failed = repair_transient_dead_letters(
            "u1",
            account_generation=1,
            limit=10,
            now=datetime.now(timezone.utc),
            firestore_client=client,
        )
        assert failed is True

    def test_skips_malformed_snapshots_resiliently(self):
        client = MagicMock()
        snap1 = MagicMock()
        snap1.id = "snap1"
        snap1.to_dict.return_value = {
            "last_rejection_at": datetime.now(timezone.utc) - timedelta(hours=10)
        }
        collection_mock = MagicMock()
        collection_mock.where.return_value = collection_mock
        collection_mock.order_by.return_value = collection_mock
        collection_mock.limit.return_value = collection_mock
        collection_mock.stream.return_value = [snap1]
        client.collection.return_value.document.return_value.collection.return_value = collection_mock

        mock_requeue = MagicMock(side_effect=ChatFirstMalformedDeliveryAttempt("corrupt doc"))

        failed = repair_transient_dead_letters(
            "u1",
            account_generation=1,
            limit=10,
            now=datetime.now(timezone.utc),
            firestore_client=client,
            requeue=mock_requeue,
        )
        assert failed is False
        mock_requeue.assert_called_once()


class TestRequeueTransientDeadLetter:
    def test_requeue_validates_uid_and_intent_id(self):
        client = MagicMock()
        with pytest.raises(ValueError, match="invalid path traversal"):
            requeue_transient_dead_letter("../u1", "intent1", account_generation=1, now=datetime.now(timezone.utc), firestore_client=client)

        with pytest.raises(ValueError, match="cannot be empty"):
            requeue_transient_dead_letter("u1", "   ", account_generation=1, now=datetime.now(timezone.utc), firestore_client=client)
