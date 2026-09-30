"""Unit tests for database translation admission input sanitization, error boundaries, and resilience."""

from unittest.mock import MagicMock
import pytest

from database.translation_admission import (
    TranslationReservation,
    _clean_date,
    _clean_deadline,
    _clean_id,
    _clean_int,
    _clean_str,
    _resolve_redis,
    release_translation,
    reservation_is_current,
    reserve_translation,
)


class TestTranslationAdmissionSanitization:
    """Tests for input validation, boundary clamping, and delimiter protection."""

    def test_clean_id_valid(self):
        assert _clean_id("user123") == "user123"
        assert _clean_id("conv-abc_456") == "conv-abc_456"
        assert _clean_id("  trimmed_id  ") == "trimmed_id"

    def test_clean_id_invalid_and_delimiters(self):
        assert _clean_id(None) == ""
        assert _clean_id("") == ""
        assert _clean_id("   ") == ""
        assert _clean_id(12345) == ""
        # Delimiters and injection attempts
        assert _clean_id("user:injected") == ""
        assert _clean_id("user\ninjected") == ""
        assert _clean_id("user\rinjected") == ""
        assert _clean_id("user\0injected") == ""
        assert _clean_id("user injected") == ""
        # Length overflow (> 128)
        assert _clean_id("a" * 129) == ""
        assert _clean_id("a" * 128) == "a" * 128

    def test_clean_str(self):
        assert _clean_str("en") == "en"
        assert _clean_str("  rev-1  ") == "rev-1"
        assert _clean_str(None) == ""
        assert _clean_str("") == ""
        assert _clean_str("hello\0world") == ""
        assert _clean_str("x" * 200, max_len=100) == ""

    def test_clean_date(self):
        assert _clean_date("20260930") == "20260930"
        assert _clean_date("  20260930  ") == "20260930"
        # Invalid format falls back to valid 8-digit date string
        fallback = _clean_date("invalid-date")
        assert len(fallback) == 8 and fallback.isdigit()
        assert len(_clean_date(None)) == 8
        assert len(_clean_date("")) == 8

    def test_clean_int(self):
        assert _clean_int(100) == 100
        assert _clean_int(1) == 1
        # Bools are ints in Python but must be rejected
        assert _clean_int(True) is None
        assert _clean_int(False) is None
        # Non-ints, negatives, zero
        assert _clean_int(0) is None
        assert _clean_int(-5) is None
        assert _clean_int(12.34) is None
        assert _clean_int("100") is None
        assert _clean_int(None) is None
        # Upper bound
        assert _clean_int(10_000_001) is None
        assert _clean_int(10_000_000) == 10_000_000

    def test_clean_deadline(self):
        assert _clean_deadline(5.0) == 5.0
        assert _clean_deadline(10) == 10.0
        # Clamping
        assert _clean_deadline(0.01) == 0.1
        assert _clean_deadline(500.0) == 300.0
        # Inf and NaN protection
        assert _clean_deadline(float("nan")) == 3.0
        assert _clean_deadline(float("inf")) == 3.0
        assert _clean_deadline(float("-inf")) == 3.0
        assert _clean_deadline("3.0") == 3.0
        assert _clean_deadline(True) == 3.0
        assert _clean_deadline(None) == 3.0


class TestReserveTranslationResilience:
    """Tests for reserve_translation error boundaries and admission semantics."""

    def test_reserve_rejects_invalid_inputs(self):
        mock_client = MagicMock()
        # Invalid uid
        res, reason = reserve_translation("", "c1", "en", "r1", "p1", 100, 500, 1000, client=mock_client)
        assert res is None and reason == "budget_denied"

        res, reason = reserve_translation("uid:colon", "c1", "en", "r1", "p1", 100, 500, 1000, client=mock_client)
        assert res is None and reason == "budget_denied"

        # Invalid conversation_id
        res, reason = reserve_translation("u1", "", "en", "r1", "p1", 100, 500, 1000, client=mock_client)
        assert res is None and reason == "budget_denied"

        # Invalid reserved_chars (zero, negative, bool)
        res, reason = reserve_translation("u1", "c1", "en", "r1", "p1", 0, 500, 1000, client=mock_client)
        assert res is None and reason == "budget_denied"

        res, reason = reserve_translation("u1", "c1", "en", "r1", "p1", True, 500, 1000, client=mock_client)
        assert res is None and reason == "budget_denied"

        # Invalid limits
        res, reason = reserve_translation("u1", "c1", "en", "r1", "p1", 100, -1, 1000, client=mock_client)
        assert res is None and reason == "budget_denied"

        res, reason = reserve_translation("u1", "c1", "en", "r1", "p1", 100, 500, False, client=mock_client)
        assert res is None and reason == "budget_denied"
        mock_client.eval.assert_not_called()

    def test_reserve_handles_redis_unavailable(self):
        # Client is None and redis_db.r is None
        res, reason = reserve_translation("u1", "c1", "en", "r1", "p1", 100, 500, 1000, client=None)
        assert res is None and reason == "redis_unavailable"

        # Client raises exception on eval
        mock_client = MagicMock()
        mock_client.eval.side_effect = RuntimeError("Redis connection broken")
        res, reason = reserve_translation("u1", "c1", "en", "r1", "p1", 100, 500, 1000, client=mock_client)
        assert res is None and reason == "redis_unavailable"

    def test_reserve_admitted(self):
        mock_client = MagicMock()
        mock_client.eval.return_value = 1
        res, reason = reserve_translation(
            "u1", "c1", "en", "r1", "p1", 100, 500, 1000, client=mock_client, day="20260930"
        )
        assert reason == "admitted"
        assert res is not None
        assert isinstance(res, TranslationReservation)
        assert res.reserved_chars == 100
        assert len(res.keys) == 4
        assert res.keys[0] == "translation:viewed:v1:uid:u1:inflight"
        assert res.keys[2] == "translation:viewed:v1:budget:uid:u1:20260930"
        assert res.keys[3] == "translation:viewed:v1:budget:global:20260930"

    def test_reserve_duplicate_and_budget_denied(self):
        mock_client = MagicMock()
        # Duplicate suppressed (returns 0)
        mock_client.eval.return_value = 0
        res, reason = reserve_translation("u1", "c1", "en", "r1", "p1", 100, 500, 1000, client=mock_client)
        assert res is None and reason == "duplicate_suppressed"

        # Budget denied (returns -1)
        mock_client.eval.return_value = -1
        res, reason = reserve_translation("u1", "c1", "en", "r1", "p1", 100, 500, 1000, client=mock_client)
        assert res is None and reason == "budget_denied"


class TestReleaseTranslationResilience:
    """Tests for release_translation parameter safety and error handling."""

    def test_release_invalid_reservation(self):
        assert release_translation(None, 10) is False  # type: ignore
        assert release_translation("invalid", 10) is False  # type: ignore

        bad_res = TranslationReservation(keys=("k1", "k2"), token="tok", reserved_chars=100)  # type: ignore
        assert release_translation(bad_res, 10) is False

    def test_release_actual_chars_safe_handling(self):
        mock_client = MagicMock()
        mock_client.eval.return_value = 1
        res = TranslationReservation(keys=("k1", "k2", "k3", "k4"), token="token123", reserved_chars=100)

        # Normal refund: 100 - 30 = 70 refund
        assert release_translation(res, 30, client=mock_client) is True
        args = mock_client.eval.call_args[0]
        assert args[7] == 70  # refund amount

        # Negative actual_chars treated as 0: 100 - 0 = 100 refund
        assert release_translation(res, -20, client=mock_client) is True
        args = mock_client.eval.call_args[0]
        assert args[7] == 100

        # Boolean actual_chars treated as 0
        assert release_translation(res, True, client=mock_client) is True
        args = mock_client.eval.call_args[0]
        assert args[7] == 100

        # NaN actual_chars treated as 0
        assert release_translation(res, float("nan"), client=mock_client) is True  # type: ignore[arg-type]
        args = mock_client.eval.call_args[0]
        assert args[7] == 100

        # Float actual_chars cast to int
        assert release_translation(res, 40.7, client=mock_client) is True  # type: ignore[arg-type]
        args = mock_client.eval.call_args[0]
        assert args[7] == 60

    def test_release_redis_exception(self):
        mock_client = MagicMock()
        mock_client.eval.side_effect = RuntimeError("Redis timeout")
        res = TranslationReservation(keys=("k1", "k2", "k3", "k4"), token="token123", reserved_chars=100)
        assert release_translation(res, 10, client=mock_client) is False


class TestReservationIsCurrentResilience:
    """Tests for reservation_is_current with str/bytes Redis return values."""

    def test_reservation_is_current_invalid_input(self):
        assert reservation_is_current(None) is False  # type: ignore
        assert reservation_is_current("not-a-res") is False  # type: ignore

    def test_reservation_is_current_handles_bytes_and_str(self):
        res = TranslationReservation(keys=("k1", "k2", "k3", "k4"), token="my-token-123", reserved_chars=50)

        # Redis returns bytes
        mock_client = MagicMock()
        mock_client.get.side_effect = lambda k: b"my-token-123"
        assert reservation_is_current(res, client=mock_client) is True

        # Redis returns str (e.g. decode_responses=True)
        mock_client.get.side_effect = lambda k: "my-token-123"
        assert reservation_is_current(res, client=mock_client) is True

        # Token mismatch
        mock_client.get.side_effect = lambda k: b"other-token"
        assert reservation_is_current(res, client=mock_client) is False

        # Key expired (returns None)
        mock_client.get.side_effect = lambda k: None
        assert reservation_is_current(res, client=mock_client) is False

    def test_reservation_is_current_handles_exception(self):
        res = TranslationReservation(keys=("k1", "k2", "k3", "k4"), token="tok", reserved_chars=50)
        mock_client = MagicMock()
        mock_client.get.side_effect = RuntimeError("Redis down")
        assert reservation_is_current(res, client=mock_client) is False
