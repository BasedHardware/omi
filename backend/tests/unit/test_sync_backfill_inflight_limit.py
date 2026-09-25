"""Per-uid backfill in-flight slot: default-on guard over the existing NX key.

``SYNC_BACKFILL_INFLIGHT_LIMIT`` defaults enabled (only ``false`` disables) and
independently of the legacy ``SYNC_BACKFILL_ADMISSION_LIMITS`` daily caps. One
concurrent backfill job per uid on the ``sync_backfill:inflight:{uid}`` NX slot,
owner-token release, and the daily-cap gate staying on its own flag.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import routers.sync as sync_router
from database.sync_jobs import SyncLedgerFenceMode
from utils.sync import backfill
from utils.sync.lanes import CaptureTimeTrust, SyncLane, SyncLaneDecision


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


def _v2_endpoint_harness(monkeypatch, *, slot_result=True, slot_error=None):
    """Bring the v2 endpoint up to the backfill admission boundary with fakes.

    Everything before the slot claim is stubbed; ``_retrieve_file_paths_v2`` is
    a spy so a refused admission can prove no audio bytes were ever consumed —
    which is what keeps the client WAL un-acknowledged and retryable.
    """
    monkeypatch.setattr(
        sync_router,
        'get_sync_ledger_fence_mode',
        MagicMock(return_value=SyncLedgerFenceMode.LEGACY),
    )
    monkeypatch.setattr(
        sync_router,
        'resolve_client_device',
        MagicMock(return_value=MagicMock(client_device_id=None, platform=None)),
    )
    monkeypatch.setattr(sync_router, 'geolocation_from_private_header', lambda _header: None)
    monkeypatch.setattr(sync_router, 'verify_capture_manifest', MagicMock(return_value=None))
    monkeypatch.setattr(
        sync_router,
        'classify_sync_lane',
        MagicMock(
            return_value=SyncLaneDecision(
                lane=SyncLane.BACKFILL,
                trust=CaptureTimeTrust.LEGACY,
                reason='aged_capture',
                oldest_capture_at=None,
                newest_capture_at=None,
                maximum_age_seconds=None,
            )
        ),
    )
    monkeypatch.setattr(sync_router, 'has_transcription_credits', MagicMock(return_value=True))
    monkeypatch.setattr(sync_router, 'is_cloud_tasks_dispatch_enabled', MagicMock(return_value=False))
    monkeypatch.setattr(sync_router, 'has_byok_keys', MagicMock(return_value=False))
    slot_mock = MagicMock(side_effect=slot_error) if slot_error is not None else MagicMock(return_value=slot_result)
    monkeypatch.setattr(sync_router, 'try_acquire_backfill_slot', slot_mock)
    file_read = MagicMock(return_value=[])
    monkeypatch.setattr(sync_router, '_retrieve_file_paths_v2', file_read)

    async def passthrough(_executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(sync_router, 'run_blocking', passthrough)
    files = [SimpleNamespace(filename='1700000000-clip-1.opus')]
    return files, file_read


def test_v2_429_before_any_file_read_keeps_wal(monkeypatch):
    files, file_read = _v2_endpoint_harness(monkeypatch, slot_result=False)

    resp = asyncio.run(sync_router.sync_local_files_v2(files=files, uid='u1'))

    assert resp.status_code == 429
    assert resp.headers['retry-after'] == '60'
    assert resp.headers['x-omi-rate-limit-reason'] == 'backfill_paced'
    body = json.loads(resp.body)
    assert body == {
        'code': 'backfill_paced',
        'detail': 'Another historical recovery job is still in flight; local audio was not consumed.',
    }
    file_read.assert_not_called()


def test_v2_redis_failure_is_503_before_any_file_read(monkeypatch):
    files, file_read = _v2_endpoint_harness(monkeypatch, slot_error=ConnectionError('redis down'))

    resp = asyncio.run(sync_router.sync_local_files_v2(files=files, uid='u1'))

    assert resp.status_code == 503
    assert resp.headers['x-omi-rate-limit-reason'] == 'backfill_capacity'
    body = json.loads(resp.body)
    assert body['code'] == 'backfill_capacity'
    file_read.assert_not_called()
