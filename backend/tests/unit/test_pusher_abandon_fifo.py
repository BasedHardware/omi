"""Worker ownership deduplicates eviction/EOF and bounds scale-down bursts."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from utils import pusher_record_finish as finish


@pytest.mark.parametrize('all_first', [False, True])
async def test_same_worker_merges_scopes_into_one_slot(monkeypatch, all_first):
    monkeypatch.setattr(finish, 'MAX_ABANDON_RECORD_DRAINS', 1)
    barrier = SimpleNamespace(forget_evicted_tokens=Mock(), abandon_recordings=AsyncMock())
    futures = SimpleNamespace(wait=AsyncMock())
    gate = asyncio.Event()
    worker = asyncio.create_task(gate.wait())
    first, second = (None, {'record'}) if all_first else ({'record'}, None)
    assert finish.abandon_evicted_record_drain(worker, barrier, futures, prepared=first)
    owner = next(iter(finish._abandon_record_drains))
    assert finish.abandon_evicted_record_drain(worker, barrier, futures, prepared=second)
    assert len(finish._abandon_record_drains) == 1 and not finish._abandon_queue
    gate.set()
    await asyncio.wait_for(owner, 2)
    barrier.abandon_recordings.assert_awaited_once_with()
    assert finish.abandon_evicted_record_drain(worker, barrier, futures, prepared={'record'})
    assert not finish._abandon_record_drains


@pytest.mark.parametrize('expire', [False, True])
async def test_fifo_count_and_time_limits_keep_unsettled_fence(monkeypatch, expire):
    monkeypatch.setattr(finish, 'MAX_ABANDON_RECORD_DRAINS', 1)
    monkeypatch.setattr(finish, 'MAX_QUEUED_ABANDON_RECORD_DRAINS', 2)
    if expire:
        monkeypatch.setattr(finish, 'ABANDON_QUEUE_DEADLINE_SECONDS', 0.5)
    workers, barriers, order = [], [], []
    active_gate = asyncio.Event()
    for index in range(4):
        worker = asyncio.create_task(active_gate.wait() if index == 0 else asyncio.sleep(0))
        workers.append(worker)

        async def attest(index=index):
            order.append(index)

        barrier = SimpleNamespace(forget_evicted_tokens=Mock(), abandon_recordings=AsyncMock(side_effect=attest))
        barriers.append(barrier)
        assert finish.abandon_evicted_record_drain(worker, barrier, SimpleNamespace(wait=AsyncMock())) is (index < 3)
    try:
        assert len(finish._abandon_record_drains) == 1 and len(finish._abandon_queue) == 2
        if expire:
            async with asyncio.timeout(2):
                while finish._abandon_queue:
                    await asyncio.sleep(0.05)
            assert order == []
        active_gate.set()
        async with asyncio.timeout(2):
            while finish._abandon_by_worker:
                await asyncio.sleep(0)
        assert order == ([0] if expire else [0, 1, 2])
        barriers[3].abandon_recordings.assert_not_awaited()
        assert not finish._closed_record_drains
    finally:
        active_gate.set()
        await asyncio.gather(*workers)


async def test_shutdown_cancellation_does_not_start_queued_owners(monkeypatch):
    monkeypatch.setattr(finish, 'MAX_ABANDON_RECORD_DRAINS', 1)
    gate = asyncio.Event()
    workers = [asyncio.create_task(gate.wait()) for _ in range(2)]
    barrier = SimpleNamespace(forget_evicted_tokens=Mock(), abandon_recordings=AsyncMock())
    futures = SimpleNamespace(wait=AsyncMock())
    try:
        for worker in workers:
            assert finish.abandon_evicted_record_drain(worker, barrier, futures)
        owner = next(iter(finish._abandon_record_drains))
        owner.cancel()
        await asyncio.gather(owner, return_exceptions=True)
        assert not finish._abandon_queue and not finish._abandon_by_worker
        assert not finish._abandon_record_drains
        barrier.abandon_recordings.assert_not_awaited()
        assert all(not worker.cancelled() and not worker.done() for worker in workers)
    finally:
        gate.set()
        await asyncio.gather(*workers)
