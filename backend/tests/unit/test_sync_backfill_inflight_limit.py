"""Retired Redis slot primitive, retained for older v1 and rollback callers.

``SYNC_BACKFILL_INFLIGHT_LIMIT`` defaults enabled (only ``false`` disables) and
independently of the legacy ``SYNC_BACKFILL_ADMISSION_LIMITS`` daily caps. One
concurrent backfill job per uid on the ``sync_backfill:inflight:{uid}`` NX slot,
owner-token release, and the daily-cap gate staying on its own flag.
"""

from __future__ import annotations

import pytest

from utils.sync import backfill


class _FakeRedis:
    """Minimal dict-backed Redis surface for the slot/reserve scripts."""

    def __init__(self):
        self.store: dict[str, str] = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    def get(self, key):
        return self.store.get(key)

    def eval(self, script, numkeys, *args):
        if numkeys == 1:
            key, token = args
            if self.store.get(key) == token:
                del self.store[key]
                return 1
            return 0
        return [-1, 0]


@pytest.fixture
def fake_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(backfill, 'redis_client', fake)
    return fake


def test_inflight_slot_enforced_by_default(fake_redis, monkeypatch):
    monkeypatch.delenv('SYNC_BACKFILL_INFLIGHT_LIMIT', raising=False)
    monkeypatch.delenv('SYNC_BACKFILL_ADMISSION_LIMITS', raising=False)

    assert backfill.try_acquire_backfill_slot('u1', 'job-a') is True
    assert backfill.try_acquire_backfill_slot('u1', 'job-b') is False
    assert backfill.try_acquire_backfill_slot('u1', 'job-a') is True
    assert backfill.try_acquire_backfill_slot('u2', 'job-b') is True


def test_explicit_false_disables_the_slot(fake_redis, monkeypatch):
    monkeypatch.setenv('SYNC_BACKFILL_INFLIGHT_LIMIT', 'false')
    monkeypatch.delenv('SYNC_BACKFILL_ADMISSION_LIMITS', raising=False)

    assert backfill.try_acquire_backfill_slot('u1', 'job-a') is True
    assert backfill.try_acquire_backfill_slot('u1', 'job-b') is True


def test_legacy_flag_still_enforces_the_slot(fake_redis, monkeypatch):
    monkeypatch.setenv('SYNC_BACKFILL_INFLIGHT_LIMIT', 'false')
    monkeypatch.setenv('SYNC_BACKFILL_ADMISSION_LIMITS', 'true')

    assert backfill.try_acquire_backfill_slot('u1', 'job-a') is True
    assert backfill.try_acquire_backfill_slot('u1', 'job-b') is False


def test_redis_failure_propagates_to_the_503_boundary(fake_redis, monkeypatch):
    def boom(*_args, **_kwargs):
        raise ConnectionError('redis down')

    monkeypatch.setattr(backfill.redis_client, 'set', boom)
    with pytest.raises(ConnectionError):
        backfill.try_acquire_backfill_slot('u1', 'job-a')


def test_release_only_deletes_the_owners_token(fake_redis, monkeypatch):
    backfill.try_acquire_backfill_slot('u1', 'job-a')

    backfill.release_backfill_slot('u1', 'job-other')
    assert fake_redis.store['sync_backfill:inflight:u1'] == 'job-a'

    backfill.release_backfill_slot('u1', 'job-a')
    assert 'sync_backfill:inflight:u1' not in fake_redis.store


def test_daily_speech_caps_stay_on_the_legacy_flag(fake_redis, monkeypatch):
    monkeypatch.delenv('SYNC_BACKFILL_ADMISSION_LIMITS', raising=False)
    reservation = backfill.reserve_backfill_speech('u1', 'job-a', speech_ms=3_600_000)
    assert reservation.allowed is True

    monkeypatch.setenv('SYNC_BACKFILL_ADMISSION_LIMITS', 'true')
    reservation = backfill.reserve_backfill_speech('u1', 'job-a', speech_ms=3_600_000)
    assert reservation.allowed is False
    assert reservation.reason == 'backfill_paced'


def test_slot_key_uses_the_existing_inflight_name_and_ttl(fake_redis):
    backfill.try_acquire_backfill_slot('u1', 'job-a')
    assert fake_redis.store == {'sync_backfill:inflight:u1': 'job-a'}
