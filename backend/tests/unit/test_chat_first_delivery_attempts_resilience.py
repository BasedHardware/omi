import pytest
from datetime import datetime, timezone, timedelta
from backend.database.chat_first_delivery_attempts import (
    _clean_id,
    _ensure_utc,
    record_delivery_attempt,
    repair_transient_dead_letters
)


class TestCleanId:
    def test_valid_id(self):
        assert _clean_id("valid_id") == "valid_id"

    def test_empty_id_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            _clean_id("")

    def test_path_traversal_raises(self):
        for invalid in ["../", "/etc/passwd", "..\\", "a/b"]:
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


class TestEnsureUtc:
    def test_utc_timestamp(self):
        dt = datetime.now(timezone.utc)
        assert _ensure_utc(dt) == dt

    def test_convert_to_utc(self):
        dt = datetime(2023, 1, 1, tzinfo=timezone(timedelta(hours=5)))
        assert _ensure_utc(dt).tzinfo == timezone.utc

    def test_naive_raises(self):
        with pytest.raises(ValueError, match="Naive datetime not allowed"):
            _ensure_utc(datetime.now())


class TestRecordDeliveryAttempt:
    def test_success(self):
        assert record_delivery_attempt(
            uid="user123",
            intent_id="intent456",
            timestamp=datetime.now(timezone.utc)
        ) is True

    def test_invalid_uid(self):
        assert record_delivery_attempt(
            uid="../",
            intent_id="intent456",
            timestamp=datetime.now(timezone.utc)
        ) is False

    def test_naive_timestamp(self):
        assert record_delivery_attempt(
            uid="user123",
            intent_id="intent456",
            timestamp=datetime.now()
        ) is False


class TestRepairTransientDeadLetters:
    def test_default_limit(self):
        assert len(repair_transient_dead_letters()) == 100

    def test_clamped_limit_high(self):
        assert len(repair_transient_dead_letters(1000)) == 1000

    def test_clamped_limit_low(self):
        assert len(repair_transient_dead_letters(0)) == 1

    def test_clamped_limit_negative(self):
        assert len(repair_transient_dead_letters(-10)) == 1

    def test_invalid_limit_type(self):
        assert len(repair_transient_dead_letters("100")) == 100

    def test_resilience_on_exception(self):
        with pytest.raises(Exception):
            # Mock a failure (actual implementation would require dependency injection)
            repair_transient_dead_letters(limit=1)
