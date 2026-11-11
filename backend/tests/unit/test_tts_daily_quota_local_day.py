"""The TTS daily character quota must reset on the user's midnight, not UTC's.

The daily bucket was keyed `tts:chars:{uid}:{UTC date}` with a TTL running to UTC
midnight, so west of UTC the quota reset in the middle of the afternoon and a user
could spend the whole daily allowance twice inside one of their days.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from database import redis_db


@pytest.fixture
def calls(monkeypatch):
    recorded = []

    def _lua(keys=None, args=None):
        recorded.append({"keys": keys, "args": args})
        return [0, 0]

    monkeypatch.setattr(redis_db, "_TTS_RATE_LIMIT_LUA", _lua)
    return recorded


def _freeze(monkeypatch, instant):
    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, zone=None):
            return instant.astimezone(zone or timezone.utc)

    monkeypatch.setattr(redis_db, "datetime", _FrozenDatetime)


def _daily_key(recorded):
    return recorded[-1]["keys"][1]


def _daily_ttl(recorded):
    return recorded[-1]["args"][-1]


def test_one_local_day_shares_one_quota_bucket(calls, monkeypatch):
    la = ZoneInfo("America/Los_Angeles")

    _freeze(monkeypatch, datetime(2026, 9, 20, 9, tzinfo=la))
    redis_db.check_tts_rate_limit("uid_1", char_count=10, tz=la)
    morning = _daily_key(calls)

    _freeze(monkeypatch, datetime(2026, 9, 20, 19, tzinfo=la))
    redis_db.check_tts_rate_limit("uid_1", char_count=10, tz=la)
    evening = _daily_key(calls)

    assert morning == evening


def test_the_bucket_turns_over_at_local_midnight(calls, monkeypatch):
    la = ZoneInfo("America/Los_Angeles")

    _freeze(monkeypatch, datetime(2026, 9, 20, 23, 30, tzinfo=la))
    redis_db.check_tts_rate_limit("uid_1", char_count=10, tz=la)
    before = _daily_key(calls)

    _freeze(monkeypatch, datetime(2026, 9, 21, 0, 30, tzinfo=la))
    redis_db.check_tts_rate_limit("uid_1", char_count=10, tz=la)
    after = _daily_key(calls)

    assert before != after


def test_the_ttl_expires_at_the_users_midnight(calls, monkeypatch):
    la = ZoneInfo("America/Los_Angeles")
    _freeze(monkeypatch, datetime(2026, 9, 20, 23, 0, tzinfo=la))

    redis_db.check_tts_rate_limit("uid_1", char_count=10, tz=la)

    assert _daily_ttl(calls) == pytest.approx(3600, abs=5)


def test_without_a_zone_the_bucket_is_still_the_utc_day(calls, monkeypatch):
    _freeze(monkeypatch, datetime(2026, 9, 20, 19, tzinfo=ZoneInfo("America/Los_Angeles")))

    redis_db.check_tts_rate_limit("uid_1", char_count=10)

    assert _daily_key(calls).endswith("20260921")
