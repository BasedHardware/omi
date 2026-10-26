from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest

from database.phone_call_usage import (
    _clean_uid,
    _period_id,
    _period_reset_epoch,
    _key,
    get_current_month_count,
    reserve_current_month_slot,
    increment_current_month,
)


class FakeRedisPipeline:
    def __init__(self, fake_redis):
        self.fake_redis = fake_redis
        self.ops = []

    def incr(self, key, delta=1):
        self.ops.append(("incr", key, delta))
        return self

    def expire(self, key, seconds):
        self.ops.append(("expire", key, seconds))
        return self

    def execute(self):
        for op, key, val in self.ops:
            if op == "incr":
                self.fake_redis.data[key] = self.fake_redis.data.get(key, 0) + val
            elif op == "expire":
                self.fake_redis.expires[key] = val
        return [True] * len(self.ops)


class FakeRedis:
    def __init__(self):
        self.data = {}
        self.expires = {}

    def get(self, key):
        return self.data.get(key)

    def incr(self, key, delta=1):
        val = int(self.data.get(key, 0)) + delta
        self.data[key] = val
        return val

    def decr(self, key, delta=1):
        val = int(self.data.get(key, 0)) - delta
        self.data[key] = val
        return val

    def expire(self, key, seconds):
        self.expires[key] = seconds
        return True

    def pipeline(self):
        return FakeRedisPipeline(self)


class TestCleanUid:
    @pytest.mark.parametrize(
        "raw_uid,expected",
        [
            ("user123", "user123"),
            ("  user_abc_456  ", "user_abc_456"),
            ("usr-xyz-789", "usr-xyz-789"),
            ("a" * 128, "a" * 128),
        ],
    )
    def test_clean_uid_valid(self, raw_uid, expected):
        assert _clean_uid(raw_uid) == expected

    @pytest.mark.parametrize(
        "bad_uid",
        [
            None,
            "",
            "   ",
            "\t\n  \r",
            12345,
            True,
            False,
            ["user123"],
            {"uid": "user123"},
            object(),
            "a" * 129,
        ],
    )
    def test_clean_uid_invalid(self, bad_uid):
        assert _clean_uid(bad_uid) is None


class TestPeriodCalculations:
    def test_period_id_format(self):
        dt = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
        assert _period_id(dt) == "2026-10"

    def test_period_reset_epoch_same_year(self):
        dt = datetime(2026, 5, 15, tzinfo=timezone.utc)
        expected = int(datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp())
        assert _period_reset_epoch(dt) == expected

    def test_period_reset_epoch_december_rollover(self):
        dt = datetime(2026, 12, 25, tzinfo=timezone.utc)
        expected = int(datetime(2027, 1, 1, tzinfo=timezone.utc).timestamp())
        assert _period_reset_epoch(dt) == expected

    def test_key_format(self):
        assert _key("u123", "2026-10") == "phone_call_usage:u123:2026-10"


class TestGetCurrentMonthCount:
    def test_get_count_valid_user_empty(self):
        fake = FakeRedis()
        count, reset_at = get_current_month_count("user123", client=fake)
        assert count == 0
        assert reset_at > 0

    def test_get_count_valid_user_with_existing_usage(self):
        fake = FakeRedis()
        now = datetime.now(timezone.utc)
        key = _key("user123", _period_id(now))
        fake.data[key] = 7

        count, reset_at = get_current_month_count("user123", client=fake)
        assert count == 7
        assert reset_at == _period_reset_epoch(now)

    def test_get_count_invalid_uid_fails_open(self):
        fake = FakeRedis()
        for bad_uid in [None, "", "   ", 123, True, "x" * 200]:
            count, reset_at = get_current_month_count(bad_uid, client=fake)
            assert count == 0
            assert reset_at > 0

    def test_get_count_corrupted_redis_data_returns_zero(self):
        fake = FakeRedis()
        now = datetime.now(timezone.utc)
        key = _key("user123", _period_id(now))
        fake.data[key] = "not-a-number"

        count, reset_at = get_current_month_count("user123", client=fake)
        assert count == 0

    def test_get_count_redis_client_exception_fails_open(self):
        mock_client = MagicMock()
        mock_client.get.side_effect = ConnectionError("Redis down")

        count, reset_at = get_current_month_count("user123", client=mock_client)
        assert count == 0
        assert reset_at > 0


class TestReserveCurrentMonthSlot:
    def test_reserve_within_limit_succeeds(self):
        fake = FakeRedis()
        success, used_before, reset_at = reserve_current_month_slot("user123", 5, client=fake)
        assert success is True
        assert used_before == 0
        assert reset_at > 0

        # Second reservation increments
        success2, used_before2, reset_at2 = reserve_current_month_slot("user123", 5, client=fake)
        assert success2 is True
        assert used_before2 == 1
        assert reset_at2 == reset_at

    def test_reserve_at_exact_limit(self):
        fake = FakeRedis()
        for i in range(3):
            ok, used, _ = reserve_current_month_slot("user123", 3, client=fake)
            assert ok is True
            assert used == i

        # Fourth attempt breaches limit and rolls back
        ok, used, _ = reserve_current_month_slot("user123", 3, client=fake)
        assert ok is False
        assert used == 3

        # Current count remains at limit (3) due to rollback
        count, _ = get_current_month_count("user123", client=fake)
        assert count == 3

    def test_reserve_invalid_uid_fails_open(self):
        fake = FakeRedis()
        for bad_uid in [None, "", "  ", 999, False, "z" * 150]:
            success, used_before, reset_at = reserve_current_month_slot(bad_uid, 5, client=fake)
            assert success is True
            assert used_before == 0
            assert reset_at > 0
        # Redis should not have been populated with invalid keys
        assert len(fake.data) == 0

    @pytest.mark.parametrize("bad_limit", [0, -1, -50, True, False, "5", 5.5, None, object()])
    def test_reserve_invalid_limit_fails_closed(self, bad_limit):
        fake = FakeRedis()
        success, used_before, reset_at = reserve_current_month_slot("user123", bad_limit, client=fake)
        assert success is False
        assert used_before == 0
        assert reset_at > 0
        assert len(fake.data) == 0

    def test_reserve_redis_error_fails_open(self):
        mock_client = MagicMock()
        mock_client.incr.side_effect = TimeoutError("Redis timed out")

        success, used_before, reset_at = reserve_current_month_slot("user123", 5, client=mock_client)
        assert success is True
        assert used_before == 0
        assert reset_at > 0


class TestIncrementCurrentMonth:
    def test_increment_valid_user(self):
        fake = FakeRedis()
        increment_current_month("user123", client=fake)

        now = datetime.now(timezone.utc)
        key = _key("user123", _period_id(now))
        assert fake.data.get(key) == 1
        assert fake.expires.get(key) == 40 * 24 * 3600

        increment_current_month("user123", client=fake)
        assert fake.data.get(key) == 2

    def test_increment_invalid_uid_no_ops(self):
        fake = FakeRedis()
        for bad_uid in [None, "", "   ", 1234, True, "m" * 130]:
            increment_current_month(bad_uid, client=fake)
        assert len(fake.data) == 0

    def test_increment_redis_error_suppressed(self):
        mock_client = MagicMock()
        mock_client.pipeline.side_effect = RuntimeError("Redis pipe failure")

        # Must not raise
        increment_current_month("user123", client=mock_client)
