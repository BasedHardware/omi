"""Strict discovery ownership under failures; legacy maintenance stays advisory."""

from copy import deepcopy
from unittest.mock import AsyncMock, Mock

import pytest

from config.batch_pipeline_leader import UPLOAD_COALESCING_SCAN
from database import batch_pipeline_coalescing as rows
from database.batch_pipeline_leader import LeaseLost
from tests.unit.test_batch_pipeline_leader import Clock, LostAckStore
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline import upload_coalescing
from utils.batch_pipeline.leader import LeaderLease


def lease(store, clock, holder):
    return LeaderLease(store, UPLOAD_COALESCING_SCAN, ttl_seconds=6, clock=clock, holder=holder)


def test_strict_role_ignores_advisory_bypass_and_fails_closed(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_LEADER_LEASE_ENABLED', 'false')
    store, clock = MemoryStore(), Clock()
    first, second = lease(store, clock, 'a'), lease(store, clock, 'b')
    assert first.acquire() and not second.acquire()
    broken = Mock()
    broken.run.side_effect = RuntimeError('unavailable')
    candidate = lease(broken, clock, 'c')
    assert not candidate.acquire()
    with pytest.raises(LeaseLost):
        candidate.guard()


def test_lost_ack_does_not_scan_and_adopts_same_durable_token_next_tick():
    store, clock = LostAckStore(), Clock()
    first, second = lease(store, clock, 'a'), lease(store, clock, 'b')
    store.lose_next = True
    assert not first.acquire() and not second.acquire()
    assert first.acquire()
    assert first.guard().token == store.rows['leases', UPLOAD_COALESCING_SCAN]['token']


@pytest.mark.parametrize('operation', ['position', 'advance', 'heartbeat', 'claim'])
def test_replaced_or_expired_scanner_cannot_mutate_custody_cursor_or_health(operation):
    store, clock = MemoryStore(), Clock()
    first, second = lease(store, clock, 'a'), lease(store, clock, 'b')
    assert first.acquire()
    stale = first.guard()
    store.rows['coalesce_quota', 'global'] = {'groups': 1, 'last_scan_at': clock.now, 'scan_epoch': 0}
    clock.now += 7
    assert second.acquire()
    before = deepcopy(store.rows)
    with pytest.raises(LeaseLost):
        if operation == 'position':
            rows.scan_position(store, scan=stale)
        elif operation == 'advance':
            rows.advance_scan(store, 0, {'scan_at': 1, 'id': 'late'}, scan=stale)
        elif operation == 'heartbeat':
            rows.note_scan(store, producer_enabled=True, scan=stale)
        else:
            rows.claim(store, 'late', clock.now, producer_enabled=True, scan=stale)
    assert store.rows == before


def test_expiry_without_replacement_and_retry_clock_are_checked():
    store, clock = MemoryStore(), Clock()
    first = lease(store, clock, 'a')
    assert first.acquire()
    guard = first.guard()
    clock.now += 6
    with pytest.raises(LeaseLost):
        rows.note_scan(store, producer_enabled=True, scan=guard)
    # The store re-enters a transaction body after a retry; it must use that
    # attempt's clock rather than the acquisition's original start time.
    original = store.run

    def delayed(body):
        clock.now += 3
        return original(body)

    store.run = delayed
    assert first.acquire()
    assert store.rows['leases', UPLOAD_COALESCING_SCAN]['expires_at'] == clock.now + 6


@pytest.mark.asyncio
async def test_follower_and_lease_error_never_reach_scan(monkeypatch):
    store, clock = MemoryStore(), Clock()
    first, second = lease(store, clock, 'a'), lease(store, clock, 'b')
    assert first.acquire()
    scan = AsyncMock()
    monkeypatch.setattr(upload_coalescing, '_drain_scan', scan)
    await upload_coalescing.drain(store, leader=second)
    store.run = Mock(side_effect=RuntimeError('unavailable'))
    await upload_coalescing.drain(store, leader=first)
    scan.assert_not_called()


@pytest.mark.asyncio
async def test_late_query_after_takeover_is_not_accepted_as_progress_or_health(monkeypatch):
    store, clock = MemoryStore(), Clock()
    store.client = Mock()
    store.namespace = 'synthetic'
    first, second = lease(store, clock, 'a'), lease(store, clock, 'b')
    monkeypatch.setattr(upload_coalescing.time, 'time', clock)

    def late(*args, **kwargs):
        clock.now += 7
        assert second.acquire()
        return [{'id': 'late', 'scan_at': clock.now}]

    monkeypatch.setattr(rows, 'due', late)
    drain = AsyncMock()
    monkeypatch.setattr(upload_coalescing, 'drain_group', drain)
    await upload_coalescing.drain(store, leader=first)
    drain.assert_not_called()
    assert ('coalesce_quota', 'global') not in store.rows
