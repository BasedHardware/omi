"""The once-a-day persona regeneration gate must expire on the user's midnight.

`set_persona_update_timestamp` set a TTL running to UTC midnight, so west of UTC the
gate cleared in the middle of the afternoon and a user could trigger a second full
persona regeneration, with its LLM calls, inside one of their own days.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from database import redis_db


@pytest.fixture
def ttl(monkeypatch):
    captured = {}

    class _Redis:
        @staticmethod
        def set(key, value, ex=None):
            captured['key'] = key
            captured['ttl'] = ex

    monkeypatch.setattr(redis_db, 'r', _Redis)
    return captured


def _freeze(monkeypatch, instant):
    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, zone=None):
            return instant.astimezone(zone or timezone.utc)

    monkeypatch.setattr(redis_db, 'datetime', _FrozenDatetime)


def test_the_gate_clears_at_the_users_midnight_not_utcs(ttl, monkeypatch):
    la = ZoneInfo('America/Los_Angeles')
    # 23:00 local is already the next UTC day, so a UTC TTL would be ~25 hours here.
    _freeze(monkeypatch, datetime(2026, 9, 20, 23, 0, tzinfo=la))

    redis_db.set_persona_update_timestamp('uid_1', la)

    assert ttl['ttl'] == pytest.approx(3600, abs=5)


def test_an_afternoon_update_still_holds_the_gate_past_utc_midnight(ttl, monkeypatch):
    la = ZoneInfo('America/Los_Angeles')
    # 16:00 local is 23:00 UTC: a UTC TTL would free the gate one hour later.
    _freeze(monkeypatch, datetime(2026, 9, 20, 16, 0, tzinfo=la))

    redis_db.set_persona_update_timestamp('uid_1', la)

    assert ttl['ttl'] == pytest.approx(8 * 3600, abs=5)


def test_without_a_zone_the_ttl_still_runs_to_utc_midnight(ttl, monkeypatch):
    _freeze(monkeypatch, datetime(2026, 9, 20, 23, 0, tzinfo=timezone.utc))

    redis_db.set_persona_update_timestamp('uid_1')

    assert ttl['ttl'] == pytest.approx(3600, abs=5)


def test_the_ttl_is_never_zero_or_negative(ttl, monkeypatch):
    kiritimati = ZoneInfo('Pacific/Kiritimati')
    _freeze(monkeypatch, datetime(2026, 9, 20, 23, 59, 59, tzinfo=kiritimati))

    redis_db.set_persona_update_timestamp('uid_1', kiritimati)

    assert ttl['ttl'] >= 1
