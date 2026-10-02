"""The proactive-notification budget must reset on the user's midnight, not UTC's.

`incr_daily_notification_count` / `get_daily_notification_count` bucketed the counter
under `{uid}:daily_noti_count:{UTC date}`. West of UTC that bucket rolls over in the
middle of the afternoon, so a user could receive MAX_DAILY_NOTIFICATIONS before it and
the whole allotment again after it, inside one of their own days.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from database import redis_db


def _key_at(monkeypatch, instant, tz):
    """The bucket key the module would build at a given instant."""

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, zone=None):
            return instant.astimezone(zone or timezone.utc)

    import datetime as datetime_module

    monkeypatch.setattr(datetime_module, "datetime", _FrozenDatetime)
    try:
        return redis_db._daily_notification_key("uid_1", tz)
    finally:
        monkeypatch.undo()


def test_one_local_day_is_one_bucket_across_the_utc_rollover(monkeypatch):
    la = ZoneInfo("America/Los_Angeles")
    morning = datetime(2026, 9, 20, 9, tzinfo=la)
    evening = datetime(2026, 9, 20, 19, tzinfo=la)

    # The UTC date differs across these two instants, the local date does not.
    assert morning.astimezone(timezone.utc).date() != evening.astimezone(timezone.utc).date()
    assert _key_at(monkeypatch, morning, la) == _key_at(monkeypatch, evening, la)


def test_the_bucket_still_turns_over_at_local_midnight(monkeypatch):
    la = ZoneInfo("America/Los_Angeles")
    before = datetime(2026, 9, 20, 23, 30, tzinfo=la)
    after = before + timedelta(hours=1)

    assert _key_at(monkeypatch, before, la) != _key_at(monkeypatch, after, la)


def test_without_a_zone_the_key_is_the_utc_day(monkeypatch):
    instant = datetime(2026, 9, 20, 19, tzinfo=ZoneInfo("America/Los_Angeles"))

    assert _key_at(monkeypatch, instant, None).endswith("2026-09-21")


def test_the_ttl_outlives_a_local_day_that_starts_before_the_utc_one(monkeypatch):
    captured = {}

    class _Redis:
        @staticmethod
        def incr(key):
            captured["key"] = key
            return 1

        @staticmethod
        def expire(key, ttl):
            captured["ttl"] = ttl

    monkeypatch.setattr(redis_db, "r", _Redis)
    redis_db.incr_daily_notification_count("uid_1", ZoneInfo("Pacific/Kiritimati"))

    # Kiritimati is UTC+14, so its day opens 14 hours before the UTC one; a 25 hour
    # TTL could drop the bucket while that day is still running.
    assert captured["ttl"] >= (24 + 14) * 3600
