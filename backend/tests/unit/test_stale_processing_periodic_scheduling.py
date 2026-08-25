"""Behavioral test that the periodic (not only startup) reconcile drives the sweep.

The hermetic listen_pusher_stack gauntlet exercises the startup drain; this test
proves the periodic ``_periodic_listen_finalization_reconcile`` loop itself
invokes the stale-processing reconciliation on its cadence (#10461 point 3).
"""

from __future__ import annotations

import asyncio

import pytest

import main


class _StopLoop(Exception):
    """Sentinel raised from the fake sleep to exit the infinite periodic loop."""


def test_periodic_reconcile_invokes_the_stale_processing_sweep(monkeypatch):
    stale_calls: list[bool] = []

    def fake_stale(**kwargs):
        stale_calls.append(True)
        return {'completed': 0, 'migrated': 0, 'skipped': 0, 'error': 0}

    monkeypatch.setattr(main, 'reconcile_stale_processing_conversations', fake_stale)
    monkeypatch.setattr(main, 'reconcile_listen_finalization_jobs', lambda **kwargs: {'requeued': 0})

    original_sleep = asyncio.sleep
    state = {'sleeps': 0}

    async def fake_sleep(seconds):
        state['sleeps'] += 1
        if state['sleeps'] >= 2:
            raise _StopLoop()
        await original_sleep(0)

    monkeypatch.setattr(main.asyncio, 'sleep', fake_sleep)

    with pytest.raises(_StopLoop):
        asyncio.run(main._periodic_listen_finalization_reconcile(interval_seconds=1))

    # Exactly one full periodic cycle ran before the loop was stopped: the sweep ran once.
    assert stale_calls == [True]
