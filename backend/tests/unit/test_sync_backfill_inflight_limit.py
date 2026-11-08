"""Legacy slot release and daily caps survive retirement of unused admission."""

from __future__ import annotations

import pytest

from utils.sync import backfill


class _FakeRedis:
    """Minimal dict-backed Redis surface for the slot/reserve scripts."""

    def __init__(self):
        self.store: dict[str, str] = {}

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
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setattr(backfill, 'redis_client', fake)
    return fake


def test_release_only_deletes_the_owners_token(fake_redis):
    # An older revision may have left a slot behind; token-fenced cleanup stays.
    fake_redis.store['sync_backfill:inflight:u1'] = 'job-a'

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
