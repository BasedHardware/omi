from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import GoogleAPICallError

import database.chat_first_delivery_attempts as delivery_attempts_module
from database.chat_first_delivery_attempts import (
    _clean_id,
    _ensure_utc,
    dead_letter_ref,
    delivery_attempt_ref,
    intent_ref,
    repair_transient_dead_letters,
    requeue_transient_dead_letter,
    user_ref,
)


class TestCleanId:
    """Tests for _clean_id validation and path traversal sanitization."""

    @pytest.mark.parametrize(
        "valid_val",
        [
            "usr_12345",
            "intent-abc-789",
            "simple_id",
            "a" * 128,
            "  trimmed_id  ",
        ],
    )
    def test_valid_ids_pass(self, valid_val):
        cleaned = _clean_id(valid_val, "test_field")
        assert cleaned == valid_val.strip()

    @pytest.mark.parametrize(
        "invalid_val,expected_err",
        [
            (12345, "expected string"),
            (None, "expected string"),
            ([], "expected string"),
            ({}, "expected string"),
            ("", "cannot be empty"),
            ("    ", "cannot be empty"),
            ("\t\n", "cannot be empty"),
            ("..", "path traversal detected"),
            ("../evil", "path traversal detected"),
            ("evil/path", "path traversal detected"),
            ("evil\\path", "path traversal detected"),
            ("a" * 129, "exceeds 128 characters"),
        ],
    )
    def test_invalid_ids_raise_value_error(self, invalid_val, expected_err):
        with pytest.raises(ValueError, match=expected_err):
            _clean_id(invalid_val, "test_field")


class TestEnsureUtc:
    """Tests for _ensure_utc timezone normalization."""

    def test_naive_becomes_aware_utc(self):
        naive = datetime(2026, 10, 25, 12, 0, 0)
        aware = _ensure_utc(naive)
        assert aware.tzinfo == timezone.utc
        assert aware.year == 2026
        assert aware.hour == 12

    def test_aware_non_utc_converts_to_utc(self):
        tz_plus_3 = timezone(timedelta(hours=3))
        aware_non_utc = datetime(2026, 10, 25, 15, 0, 0, tzinfo=tz_plus_3)
        aware_utc = _ensure_utc(aware_non_utc)
        assert aware_utc.tzinfo == timezone.utc
        assert aware_utc.hour == 12

    def test_aware_utc_remains_unchanged(self):
        aware = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)
        result = _ensure_utc(aware)
        assert result == aware
        assert result.tzinfo == timezone.utc

    @pytest.mark.parametrize("invalid", ["2026-10-25", 12345678, None, []])
    def test_non_datetime_raises_type_error(self, invalid):
        with pytest.raises(TypeError, match="expected datetime"):
            _ensure_utc(invalid)


class TestReferenceFunctions:
    """Tests for user_ref, intent_ref, delivery_attempt_ref, dead_letter_ref."""

    def test_user_ref_valid(self):
        mock_client = MagicMock()
        ref = user_ref("valid_uid", firestore_client=mock_client)
        mock_client.collection.assert_called_once_with("users")
        mock_client.collection.return_value.document.assert_called_once_with("valid_uid")

    def test_user_ref_traversal_rejected(self):
        mock_client = MagicMock()
        with pytest.raises(ValueError, match="path traversal detected"):
            user_ref("../traversal_uid", firestore_client=mock_client)

    def test_intent_ref_valid(self):
        mock_client = MagicMock()
        intent_ref("valid_uid", "valid_intent", firestore_client=mock_client)
        mock_client.collection.return_value.document.return_value.collection.assert_called_once_with(
            "chat_first_proactive_intents"
        )

    def test_intent_ref_traversal_rejected(self):
        mock_client = MagicMock()
        with pytest.raises(ValueError, match="path traversal detected"):
            intent_ref("valid_uid", "intent/traversal", firestore_client=mock_client)

    def test_delivery_attempt_ref_valid(self):
        mock_client = MagicMock()
        delivery_attempt_ref("valid_uid", "valid_intent", firestore_client=mock_client)
        mock_client.collection.return_value.document.return_value.collection.assert_called_once_with(
            "chat_first_delivery_attempts"
        )

    def test_dead_letter_ref_valid(self):
        mock_client = MagicMock()
        dead_letter_ref("valid_uid", "valid_intent", firestore_client=mock_client)
        mock_client.collection.return_value.document.return_value.collection.assert_called_once_with(
            "chat_first_dead_letters"
        )


class TestRequeueTransientDeadLetter:
    """Tests for requeue_transient_dead_letter timezone resilience."""

    def test_requeue_handles_mismatched_timezone_awareness(self):
        mock_client = MagicMock()
        # Mock document get returning exists = False to test early exit cleanly
        doc_mock = mock_client.collection.return_value.document.return_value.collection.return_value.document.return_value
        snapshot_mock = MagicMock()
        snapshot_mock.exists = False
        doc_mock.get.return_value = snapshot_mock
        mock_client.transaction.return_value = MagicMock()

        with patch("google.cloud.firestore.transactional", side_effect=lambda fn: fn):
            # Pass naive now and test that it processes cleanly without TypeError
            naive_now = datetime(2026, 10, 25, 12, 0, 0)
            result = requeue_transient_dead_letter(
                "test_uid",
                "test_intent",
                account_generation=1,
                now=naive_now,
                firestore_client=mock_client,
            )
            assert result is None


class TestRepairTransientDeadLetters:
    """Tests for repair_transient_dead_letters resilience and clamping."""

    def test_clamping_and_query_execution(self):
        mock_client = MagicMock()
        mock_stream = []
        mock_query = MagicMock()
        mock_query.stream.return_value = mock_stream
        mock_order = MagicMock()
        mock_order.limit.return_value = mock_query
        mock_builder = MagicMock()
        mock_builder.order_by.return_value = mock_order

        mock_spec = MagicMock()
        mock_spec.build.return_value = mock_builder

        with patch.object(
            delivery_attempts_module,
            "CHAT_FIRST_TRANSIENT_DEAD_LETTER_REPAIR_QUERY",
            mock_spec,
        ):
            # Pass out-of-bounds negative limit
            failed = repair_transient_dead_letters(
                "test_uid",
                account_generation=1,
                limit=-10,
                now=datetime.now(timezone.utc),
                firestore_client=mock_client,
            )
            assert failed is False
            # Clamped to 1, limit(2 * 1) = 2
            mock_order.limit.assert_called_once_with(2)

    def test_catches_broad_exception_without_crashing(self):
        mock_client = MagicMock()
        mock_spec = MagicMock()
        mock_spec.build.side_effect = RuntimeError("Unexpected connection pool drop")

        with patch.object(
            delivery_attempts_module,
            "CHAT_FIRST_TRANSIENT_DEAD_LETTER_REPAIR_QUERY",
            mock_spec,
        ):
            failed = repair_transient_dead_letters(
                "test_uid",
                account_generation=1,
                limit=10,
                now=datetime.now(timezone.utc),
                firestore_client=mock_client,
            )
            # Gracefully returns True (query failed) instead of raising
            assert failed is True

    def test_catches_google_api_call_error(self):
        mock_client = MagicMock()
        mock_spec = MagicMock()
        mock_spec.build.side_effect = GoogleAPICallError("Unavailable")

        with patch.object(
            delivery_attempts_module,
            "CHAT_FIRST_TRANSIENT_DEAD_LETTER_REPAIR_QUERY",
            mock_spec,
        ):
            failed = repair_transient_dead_letters(
                "test_uid",
                account_generation=1,
                limit=10,
                now=datetime.now(timezone.utc),
                firestore_client=mock_client,
            )
            assert failed is True
