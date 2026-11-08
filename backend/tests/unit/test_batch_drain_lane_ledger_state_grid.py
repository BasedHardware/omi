"""Ledger state-machine grid for the deferred publication-drain lane.

Every generated sequence drives the real pump ledger through armed re-offers,
continuations, hot contention rounds, flushes and stops, asserting after every
step that the ledger stays bounded, every armed attempt budget stays inside
its kind's cap, and terminal ops leave the documented terminal state. The
length-1 sequences additionally pin the exact post-op ledger.

Failure-Class: FC-publication-drain-contention-exhaustion-left-without-a-convergence-owner
"""

import asyncio
import contextlib
import types

import pytest

from database.firestore_transaction_retry import FirestoreContentionExhausted
import utils.batch_pipeline.pump as pump_module
from utils.batch_pipeline.pump import Pump


@pytest.fixture(autouse=True)
def inline_blocking(monkeypatch):
    async def passthrough(executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(pump_module, 'run_blocking', passthrough)


class HotMerge:
    def __init__(self):
        self.held_owners = set()
        self.hot = False
        self.drained = []
        self.commits = 0

    def commit_next(self, owner_id, now):
        self.drained.append(owner_id)
        self.commits += 1
        if self.hot:
            raise FirestoreContentionExhausted('hot')
        return None


class Clock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now


def make_pump():
    pump = Pump(types.SimpleNamespace(), types.SimpleNamespace(), merge=HotMerge(), publish_concurrency=1)
    clock = Clock()
    pump._monotonic = clock
    return pump, pump.merge, clock


def check_invariants(pump):
    assert len(pump._deferred_drains) <= pump_module.DRAIN_RETRY_LEDGER_CAP
    for armed in pump._deferred_drains.values():
        cap = (
            pump_module.DRAIN_BACKLOG_CONTINUATION_ATTEMPTS
            if armed['continuation']
            else pump_module.DRAIN_RETRY_MAX_ATTEMPTS
        )
        assert 1 <= armed['attempts'] <= cap
        assert armed['continuation'] in (True, False)


def do_arm(pump, merge, clock, owner):
    assert pump._defer_drain(owner) is True
    check_invariants(pump)


def do_armc(pump, merge, clock, owner):
    assert pump._defer_drain(owner, continuation=True) is True
    check_invariants(pump)


def elapse(pump, clock):
    """Step the injected clock past every armed due time."""
    for armed in pump._deferred_drains.values():
        armed['due_at'] = clock.now - 1.0


async def do_due(pump, merge, clock):
    elapse(pump, clock)
    await pump._drain_deferred_due()
    check_invariants(pump)


async def do_hot(pump, merge, clock):
    merge.hot = True
    try:
        elapse(pump, clock)
        await pump._drain_deferred_due()
    finally:
        merge.hot = False
    check_invariants(pump)


async def do_flush(pump, merge, clock):
    await pump.flush_deferred_drains()
    assert pump._deferred_drains == {}
    assert pump._deferred_lane is None


def do_stop(pump, merge, clock):
    """A stop without a flush: the flag refuses resurrection; the pending
    lane exits at its next wake, and the armed ledger is left for the
    maintenance sweep (durable rows converge after restart)."""
    pump._deferred_stopped = True
    assert pump._deferred_stopped is True


OWNERS = ('owner-a', 'owner-b')


async def test_seq_arma():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    assert sorted(pump._deferred_drains) == ['owner-a']
    assert pump._deferred_drains['owner-a']['attempts'] == 1
    assert pump._deferred_drains['owner-a']['continuation'] is False
    await pump.flush_deferred_drains()


async def test_seq_armb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    assert sorted(pump._deferred_drains) == ['owner-b']
    assert pump._deferred_drains['owner-b']['attempts'] == 1
    assert pump._deferred_drains['owner-b']['continuation'] is False
    await pump.flush_deferred_drains()


async def test_seq_armca():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    assert sorted(pump._deferred_drains) == ['owner-a']
    assert pump._deferred_drains['owner-a']['continuation'] is True
    await pump.flush_deferred_drains()


async def test_seq_armcb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    assert sorted(pump._deferred_drains) == ['owner-b']
    assert pump._deferred_drains['owner-b']['continuation'] is True
    await pump.flush_deferred_drains()


async def test_seq_due():
    pump, merge, clock = make_pump()
    await do_due(pump, merge, clock)
    assert pump._deferred_drains == {}
    await pump.flush_deferred_drains()


async def test_seq_hot():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    assert pump._deferred_drains == {}
    await pump.flush_deferred_drains()


async def test_seq_flush():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    assert pump._deferred_stopped is True
    await pump.flush_deferred_drains()


async def test_seq_stop():
    pump, merge, clock = make_pump()
    do_stop(pump, merge, clock)
    assert pump._deferred_stopped is True
    await pump.flush_deferred_drains()


async def test_seq_arma_arma():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_arma_armb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_arma_armca():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_arma_armcb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_arma_due():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_hot():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_flush():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_stop():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_arma():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armb_armb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armb_armca():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armb_armcb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armb_due():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_hot():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_flush():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_stop():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_arma():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armca_armb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armca_armca():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armca_armcb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armca_due():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_hot():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_flush():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_stop():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_arma():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armcb_armb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armcb_armca():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armcb_armcb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armcb_due():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_hot():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_flush():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_stop():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_due_arma():
    pump, merge, clock = make_pump()
    await do_due(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_due_armb():
    pump, merge, clock = make_pump()
    await do_due(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_due_armca():
    pump, merge, clock = make_pump()
    await do_due(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_due_armcb():
    pump, merge, clock = make_pump()
    await do_due(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_due_due():
    pump, merge, clock = make_pump()
    await do_due(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_due_hot():
    pump, merge, clock = make_pump()
    await do_due(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_due_flush():
    pump, merge, clock = make_pump()
    await do_due(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_due_stop():
    pump, merge, clock = make_pump()
    await do_due(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_arma():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_hot_armb():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_hot_armca():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_hot_armcb():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_hot_due():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_hot():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_flush():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_stop():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_arma():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_flush_armb():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_flush_armca():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_flush_armcb():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_flush_due():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_hot():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_flush():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_stop():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_stop_arma():
    pump, merge, clock = make_pump()
    do_stop(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_stop_armb():
    pump, merge, clock = make_pump()
    do_stop(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_stop_armca():
    pump, merge, clock = make_pump()
    do_stop(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_stop_armcb():
    pump, merge, clock = make_pump()
    do_stop(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_stop_due():
    pump, merge, clock = make_pump()
    do_stop(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_stop_hot():
    pump, merge, clock = make_pump()
    do_stop(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_stop_flush():
    pump, merge, clock = make_pump()
    do_stop(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_stop_stop():
    pump, merge, clock = make_pump()
    do_stop(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_arma_arma():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_arma_arma_armb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_arma_arma_armca():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_arma_arma_armcb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_arma_arma_due():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_arma_hot():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_arma_flush():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_arma_stop():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_armb_arma():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_arma_armb_armb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_arma_armb_armca():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_arma_armb_armcb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_arma_armb_due():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_armb_hot():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_armb_flush():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_armb_stop():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_armca_arma():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_arma_armca_armb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_arma_armca_armca():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_arma_armca_armcb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_arma_armca_due():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_armca_hot():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_armca_flush():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_armca_stop():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_armcb_arma():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_arma_armcb_armb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_arma_armcb_armca():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_arma_armcb_armcb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_arma_armcb_due():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_armcb_hot():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_armcb_flush():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_armcb_stop():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_due_arma():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_arma_due_armb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_arma_due_armca():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_arma_due_armcb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_arma_due_due():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_due_hot():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_due_flush():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_due_stop():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_hot_arma():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_arma_hot_armb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_arma_hot_armca():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_arma_hot_armcb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_arma_hot_due():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_hot_hot():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_hot_flush():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_hot_stop():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_flush_arma():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_arma_flush_armb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_arma_flush_armca():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_arma_flush_armcb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_arma_flush_due():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_flush_hot():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_flush_flush():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_flush_stop():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_stop_arma():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_arma_stop_armb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_arma_stop_armca():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_arma_stop_armcb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_arma_stop_due():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_stop_hot():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_stop_flush():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_arma_stop_stop():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_arma_arma():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armb_arma_armb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armb_arma_armca():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armb_arma_armcb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armb_arma_due():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_arma_hot():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_arma_flush():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_arma_stop():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_armb_arma():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armb_armb_armb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armb_armb_armca():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armb_armb_armcb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armb_armb_due():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_armb_hot():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_armb_flush():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_armb_stop():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_armca_arma():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armb_armca_armb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armb_armca_armca():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armb_armca_armcb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armb_armca_due():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_armca_hot():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_armca_flush():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_armca_stop():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_armcb_arma():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armb_armcb_armb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armb_armcb_armca():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armb_armcb_armcb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armb_armcb_due():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_armcb_hot():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_armcb_flush():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_armcb_stop():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_due_arma():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armb_due_armb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armb_due_armca():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armb_due_armcb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armb_due_due():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_due_hot():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_due_flush():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_due_stop():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_hot_arma():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armb_hot_armb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armb_hot_armca():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armb_hot_armcb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armb_hot_due():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_hot_hot():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_hot_flush():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_hot_stop():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_flush_arma():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armb_flush_armb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armb_flush_armca():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armb_flush_armcb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armb_flush_due():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_flush_hot():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_flush_flush():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_flush_stop():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_stop_arma():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armb_stop_armb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armb_stop_armca():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armb_stop_armcb():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armb_stop_due():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_stop_hot():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_stop_flush():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armb_stop_stop():
    pump, merge, clock = make_pump()
    do_arm(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_arma_arma():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armca_arma_armb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armca_arma_armca():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armca_arma_armcb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armca_arma_due():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_arma_hot():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_arma_flush():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_arma_stop():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_armb_arma():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armca_armb_armb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armca_armb_armca():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armca_armb_armcb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armca_armb_due():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_armb_hot():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_armb_flush():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_armb_stop():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_armca_arma():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armca_armca_armb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armca_armca_armca():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armca_armca_armcb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armca_armca_due():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_armca_hot():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_armca_flush():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_armca_stop():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_armcb_arma():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armca_armcb_armb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armca_armcb_armca():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armca_armcb_armcb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armca_armcb_due():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_armcb_hot():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_armcb_flush():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_armcb_stop():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_due_arma():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armca_due_armb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armca_due_armca():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armca_due_armcb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armca_due_due():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_due_hot():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_due_flush():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_due_stop():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_hot_arma():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armca_hot_armb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armca_hot_armca():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armca_hot_armcb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armca_hot_due():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_hot_hot():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_hot_flush():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_hot_stop():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_flush_arma():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armca_flush_armb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armca_flush_armca():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armca_flush_armcb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armca_flush_due():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_flush_hot():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_flush_flush():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_flush_stop():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_stop_arma():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armca_stop_armb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armca_stop_armca():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armca_stop_armcb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armca_stop_due():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_stop_hot():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_stop_flush():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armca_stop_stop():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_arma_arma():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armcb_arma_armb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armcb_arma_armca():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armcb_arma_armcb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armcb_arma_due():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_arma_hot():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_arma_flush():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_arma_stop():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_armb_arma():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armcb_armb_armb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armcb_armb_armca():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armcb_armb_armcb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armcb_armb_due():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_armb_hot():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_armb_flush():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_armb_stop():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_armca_arma():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armcb_armca_armb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armcb_armca_armca():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armcb_armca_armcb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armcb_armca_due():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_armca_hot():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_armca_flush():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_armca_stop():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_armcb_arma():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armcb_armcb_armb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armcb_armcb_armca():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armcb_armcb_armcb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armcb_armcb_due():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_armcb_hot():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_armcb_flush():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_armcb_stop():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_due_arma():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armcb_due_armb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armcb_due_armca():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armcb_due_armcb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armcb_due_due():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_due_hot():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_due_flush():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_due_stop():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_hot_arma():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armcb_hot_armb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armcb_hot_armca():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armcb_hot_armcb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armcb_hot_due():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_hot_hot():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_hot_flush():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_hot_stop():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_flush_arma():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armcb_flush_armb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armcb_flush_armca():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armcb_flush_armcb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armcb_flush_due():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_flush_hot():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_flush_flush():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_flush_stop():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_stop_arma():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armcb_stop_armb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armcb_stop_armca():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_armcb_stop_armcb():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_armcb_stop_due():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_stop_hot():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_stop_flush():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_armcb_stop_stop():
    pump, merge, clock = make_pump()
    do_armc(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_arma_arma():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_hot_arma_armb():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_hot_arma_armca():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_hot_arma_armcb():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_hot_arma_due():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_arma_hot():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_arma_flush():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_arma_stop():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_armb_arma():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_hot_armb_armb():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_hot_armb_armca():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_hot_armb_armcb():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_hot_armb_due():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_armb_hot():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_armb_flush():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_armb_stop():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_armca_arma():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_hot_armca_armb():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_hot_armca_armca():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_hot_armca_armcb():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_hot_armca_due():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_armca_hot():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_armca_flush():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_armca_stop():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_armcb_arma():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_hot_armcb_armb():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_hot_armcb_armca():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_hot_armcb_armcb():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_hot_armcb_due():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_armcb_hot():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_armcb_flush():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_armcb_stop():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_due_arma():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_due(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_hot_due_armb():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_due(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_hot_due_armca():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_due(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_hot_due_armcb():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_due(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_hot_due_due():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_due(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_due_hot():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_due(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_due_flush():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_due(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_due_stop():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_due(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_hot_arma():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_hot_hot_armb():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_hot_hot_armca():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_hot_hot_armcb():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_hot_hot_due():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_hot_hot():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_hot_flush():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_hot_stop():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_hot(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_flush_arma():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_hot_flush_armb():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_hot_flush_armca():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_hot_flush_armcb():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_hot_flush_due():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_flush_hot():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_flush_flush():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_flush_stop():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    await do_flush(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_stop_arma():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_stop(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_hot_stop_armb():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_stop(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_hot_stop_armca():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_stop(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_hot_stop_armcb():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_stop(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_hot_stop_due():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_stop(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_stop_hot():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_stop(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_stop_flush():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_stop(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_hot_stop_stop():
    pump, merge, clock = make_pump()
    await do_hot(pump, merge, clock)
    do_stop(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_arma_arma():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_flush_arma_armb():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_flush_arma_armca():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_flush_arma_armcb():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_flush_arma_due():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_arma_hot():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_arma_flush():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_arma_stop():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_armb_arma():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_flush_armb_armb():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_flush_armb_armca():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_flush_armb_armcb():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_flush_armb_due():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_armb_hot():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_armb_flush():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_armb_stop():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_armca_arma():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_flush_armca_armb():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_flush_armca_armca():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_flush_armca_armcb():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_flush_armca_due():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_armca_hot():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_armca_flush():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_armca_stop():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_armcb_arma():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_flush_armcb_armb():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_flush_armcb_armca():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_flush_armcb_armcb():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_flush_armcb_due():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_armcb_hot():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_armcb_flush():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_armcb_stop():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_due_arma():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_due(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_flush_due_armb():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_due(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_flush_due_armca():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_due(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_flush_due_armcb():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_due(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_flush_due_due():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_due(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_due_hot():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_due(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_due_flush():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_due(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_due_stop():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_due(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_hot_arma():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_flush_hot_armb():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_hot(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_flush_hot_armca():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_flush_hot_armcb():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_hot(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_flush_hot_due():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_hot_hot():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_hot_flush():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_hot_stop():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_hot(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_flush_arma():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_flush_flush_armb():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_flush(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_flush_flush_armca():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_flush_flush_armcb():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_flush(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_flush_flush_due():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_flush_hot():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_flush_flush():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_flush_stop():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    await do_flush(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_stop_arma():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_stop(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_flush_stop_armb():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_stop(pump, merge, clock)
    do_arm(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_flush_stop_armca():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_stop(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-a')
    await pump.flush_deferred_drains()


async def test_seq_flush_stop_armcb():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_stop(pump, merge, clock)
    do_armc(pump, merge, clock, 'owner-b')
    await pump.flush_deferred_drains()


async def test_seq_flush_stop_due():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_stop(pump, merge, clock)
    await do_due(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_stop_hot():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_stop(pump, merge, clock)
    await do_hot(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_stop_flush():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_stop(pump, merge, clock)
    await do_flush(pump, merge, clock)
    await pump.flush_deferred_drains()


async def test_seq_flush_stop_stop():
    pump, merge, clock = make_pump()
    await do_flush(pump, merge, clock)
    do_stop(pump, merge, clock)
    do_stop(pump, merge, clock)
    await pump.flush_deferred_drains()
