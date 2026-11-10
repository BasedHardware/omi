"""Deferred-drain lane alignment grid: storm windows reshape WHEN, never the budget.



Every armed attempt of the deferred publication-drain lane lands at

``due_at = now + max(documented backoff step, min(storm window, lane max))``.

This grid pins that composition per attempt, per window, per lane surface

(publication loss, due-lane re-arm, continuation re-offer), plus the

end-to-end due sweep, multi-owner wake order, flush and cancellation

boundaries, and the attempt-cap refusals a storm cannot buy out of.



Failure-Class: FC-deferred-drain-restrike-collides-inside-the-armed-storm-window

"""

import asyncio

import contextlib

import gc

import logging

import types


import pytest


from database.firestore_transaction_retry import FirestoreContentionExhausted

import utils.batch_pipeline.pump as pump_module

from utils.batch_pipeline.pump import (
    DRAIN_BACKLOG_CONTINUATION_ATTEMPTS,
    DRAIN_RETRY_BASE_SECONDS,
    DRAIN_RETRY_LEDGER_CAP,
    DRAIN_RETRY_MAX_ATTEMPTS,
    DRAIN_RETRY_MAX_SECONDS,
    contention_retry_after,
    deferred_drain_delay,
)

from utils.batch_pipeline.pump import Pump


@pytest.fixture(autouse=True)
def inline_blocking(monkeypatch):

    async def passthrough(executor, function, *args, **kwargs):

        return function(*args, **kwargs)

    monkeypatch.setattr(pump_module, 'run_blocking', passthrough)


@pytest.fixture(autouse=True)
async def lane_cleanup():
    """No test leaves a pending lane behind: stop and cancel same-loop lanes."""

    yield

    loop = asyncio.get_running_loop()

    for obj in gc.get_objects():

        if isinstance(obj, Pump):

            obj._deferred_stopped = True

            lane = obj.__dict__.get('_deferred_lane')

            if lane is not None and not lane.done() and lane.get_loop() is loop:

                lane.cancel()

                with contextlib.suppress(asyncio.CancelledError, RuntimeError):

                    await lane


class ScriptMerge:

    def __init__(self, script=None):

        self.held_owners = set()

        self.drained = []

        self.commits = 0

        self.script = list(script or [])

    def commit_next(self, owner_id, now):

        self.drained.append(owner_id)

        self.commits += 1

        if self.script:

            step = self.script.pop(0)

            if isinstance(step, BaseException):

                raise step

            return step

        return None


class FakeClock:

    def __init__(self, now=1000.0):

        self.now = now

    def monotonic(self):

        return self.now

    def advance(self, seconds):

        self.now += seconds


def make_pump(merge=None, clock=None):

    pump = Pump(
        types.SimpleNamespace(),
        types.SimpleNamespace(),
        merge=merge or ScriptMerge(),
        publish_concurrency=1,
    )

    pump._monotonic = clock.monotonic if clock is not None else (lambda: 1000.0)

    return pump


def loss(window):
    """One scripted drain loss: stamped when the store damper ran."""

    if window is None:

        return FirestoreContentionExhausted('no damper in scope')

    return FirestoreContentionExhausted('storm', retry_after=window)


def aligned_delay(attempt, window):
    """The documented composition the lane must land every armed attempt at."""

    base = 0.0 if attempt is None else deferred_drain_delay(attempt)

    stamp = 0.0 if window is None else min(window, DRAIN_RETRY_MAX_SECONDS)

    return max(base, stamp)


async def test_arm_alignment_attempt_1_default():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(None), None]), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 1
    assert armed["due_at"] == pytest.approx(clock.now + 0.5)


async def test_arm_alignment_attempt_1_w0_001():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.001), None]), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 1
    assert armed["due_at"] == pytest.approx(clock.now + 0.5)


async def test_arm_alignment_attempt_1_w0_1():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.1), None]), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 1
    assert armed["due_at"] == pytest.approx(clock.now + 0.5)


async def test_arm_alignment_attempt_1_w0_25():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.25), None]), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 1
    assert armed["due_at"] == pytest.approx(clock.now + 0.5)


async def test_arm_alignment_attempt_1_w0_4():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.4), None]), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 1
    assert armed["due_at"] == pytest.approx(clock.now + 0.5)


async def test_arm_alignment_attempt_1_w0_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.5), None]), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 1
    assert armed["due_at"] == pytest.approx(clock.now + 0.5)


async def test_arm_alignment_attempt_1_w0_6():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.6), None]), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 1
    assert armed["due_at"] == pytest.approx(clock.now + 0.6)


async def test_arm_alignment_attempt_1_w0_75():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.75), None]), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 1
    assert armed["due_at"] == pytest.approx(clock.now + 0.75)


async def test_arm_alignment_attempt_1_w1_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(1.0), None]), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 1
    assert armed["due_at"] == pytest.approx(clock.now + 1.0)


async def test_arm_alignment_attempt_1_w1_25():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(1.25), None]), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 1
    assert armed["due_at"] == pytest.approx(clock.now + 1.25)


async def test_arm_alignment_attempt_1_w1_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(1.5), None]), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 1
    assert armed["due_at"] == pytest.approx(clock.now + 1.5)


async def test_arm_alignment_attempt_1_w2_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(2.0), None]), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 1
    assert armed["due_at"] == pytest.approx(clock.now + 2.0)


async def test_arm_alignment_attempt_1_w2_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(2.5), None]), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 1
    assert armed["due_at"] == pytest.approx(clock.now + 2.5)


async def test_arm_alignment_attempt_1_w3_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(3.0), None]), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 1
    assert armed["due_at"] == pytest.approx(clock.now + 3.0)


async def test_arm_alignment_attempt_1_w3_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(3.5), None]), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 1
    assert armed["due_at"] == pytest.approx(clock.now + 3.5)


async def test_arm_alignment_attempt_1_w4_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(4.0), None]), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 1
    assert armed["due_at"] == pytest.approx(clock.now + 4.0)


async def test_arm_alignment_attempt_1_w4_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(4.5), None]), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 1
    assert armed["due_at"] == pytest.approx(clock.now + 4.5)


async def test_arm_alignment_attempt_1_w5_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(5.0), None]), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 1
    assert armed["due_at"] == pytest.approx(clock.now + 5.0)


async def test_arm_alignment_attempt_1_w6_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(6.0), None]), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 1
    assert armed["due_at"] == pytest.approx(clock.now + 6.0)


async def test_arm_alignment_attempt_1_w7_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(7.0), None]), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 1
    assert armed["due_at"] == pytest.approx(clock.now + 7.0)


async def test_arm_alignment_attempt_1_w7_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(7.5), None]), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 1
    assert armed["due_at"] == pytest.approx(clock.now + 7.5)


async def test_arm_alignment_attempt_1_w8_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(8.0), None]), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 1
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_1_w8_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(8.5), None]), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 1
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_1_w9_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(9.0), None]), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 1
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_1_w100_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(100.0), None]), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 1
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_2_default():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(None), None]), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 2
    assert armed["due_at"] == pytest.approx(clock.now + 1.0)


async def test_arm_alignment_attempt_2_w0_001():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.001), None]), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 2
    assert armed["due_at"] == pytest.approx(clock.now + 1.0)


async def test_arm_alignment_attempt_2_w0_1():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.1), None]), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 2
    assert armed["due_at"] == pytest.approx(clock.now + 1.0)


async def test_arm_alignment_attempt_2_w0_25():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.25), None]), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 2
    assert armed["due_at"] == pytest.approx(clock.now + 1.0)


async def test_arm_alignment_attempt_2_w0_4():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.4), None]), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 2
    assert armed["due_at"] == pytest.approx(clock.now + 1.0)


async def test_arm_alignment_attempt_2_w0_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.5), None]), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 2
    assert armed["due_at"] == pytest.approx(clock.now + 1.0)


async def test_arm_alignment_attempt_2_w0_6():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.6), None]), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 2
    assert armed["due_at"] == pytest.approx(clock.now + 1.0)


async def test_arm_alignment_attempt_2_w0_75():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.75), None]), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 2
    assert armed["due_at"] == pytest.approx(clock.now + 1.0)


async def test_arm_alignment_attempt_2_w1_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(1.0), None]), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 2
    assert armed["due_at"] == pytest.approx(clock.now + 1.0)


async def test_arm_alignment_attempt_2_w1_25():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(1.25), None]), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 2
    assert armed["due_at"] == pytest.approx(clock.now + 1.25)


async def test_arm_alignment_attempt_2_w1_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(1.5), None]), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 2
    assert armed["due_at"] == pytest.approx(clock.now + 1.5)


async def test_arm_alignment_attempt_2_w2_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(2.0), None]), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 2
    assert armed["due_at"] == pytest.approx(clock.now + 2.0)


async def test_arm_alignment_attempt_2_w2_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(2.5), None]), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 2
    assert armed["due_at"] == pytest.approx(clock.now + 2.5)


async def test_arm_alignment_attempt_2_w3_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(3.0), None]), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 2
    assert armed["due_at"] == pytest.approx(clock.now + 3.0)


async def test_arm_alignment_attempt_2_w3_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(3.5), None]), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 2
    assert armed["due_at"] == pytest.approx(clock.now + 3.5)


async def test_arm_alignment_attempt_2_w4_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(4.0), None]), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 2
    assert armed["due_at"] == pytest.approx(clock.now + 4.0)


async def test_arm_alignment_attempt_2_w4_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(4.5), None]), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 2
    assert armed["due_at"] == pytest.approx(clock.now + 4.5)


async def test_arm_alignment_attempt_2_w5_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(5.0), None]), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 2
    assert armed["due_at"] == pytest.approx(clock.now + 5.0)


async def test_arm_alignment_attempt_2_w6_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(6.0), None]), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 2
    assert armed["due_at"] == pytest.approx(clock.now + 6.0)


async def test_arm_alignment_attempt_2_w7_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(7.0), None]), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 2
    assert armed["due_at"] == pytest.approx(clock.now + 7.0)


async def test_arm_alignment_attempt_2_w7_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(7.5), None]), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 2
    assert armed["due_at"] == pytest.approx(clock.now + 7.5)


async def test_arm_alignment_attempt_2_w8_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(8.0), None]), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 2
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_2_w8_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(8.5), None]), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 2
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_2_w9_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(9.0), None]), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 2
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_2_w100_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(100.0), None]), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 2
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_3_default():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(None), None]), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 3
    assert armed["due_at"] == pytest.approx(clock.now + 2.0)


async def test_arm_alignment_attempt_3_w0_001():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.001), None]), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 3
    assert armed["due_at"] == pytest.approx(clock.now + 2.0)


async def test_arm_alignment_attempt_3_w0_1():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.1), None]), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 3
    assert armed["due_at"] == pytest.approx(clock.now + 2.0)


async def test_arm_alignment_attempt_3_w0_25():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.25), None]), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 3
    assert armed["due_at"] == pytest.approx(clock.now + 2.0)


async def test_arm_alignment_attempt_3_w0_4():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.4), None]), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 3
    assert armed["due_at"] == pytest.approx(clock.now + 2.0)


async def test_arm_alignment_attempt_3_w0_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.5), None]), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 3
    assert armed["due_at"] == pytest.approx(clock.now + 2.0)


async def test_arm_alignment_attempt_3_w0_6():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.6), None]), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 3
    assert armed["due_at"] == pytest.approx(clock.now + 2.0)


async def test_arm_alignment_attempt_3_w0_75():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.75), None]), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 3
    assert armed["due_at"] == pytest.approx(clock.now + 2.0)


async def test_arm_alignment_attempt_3_w1_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(1.0), None]), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 3
    assert armed["due_at"] == pytest.approx(clock.now + 2.0)


async def test_arm_alignment_attempt_3_w1_25():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(1.25), None]), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 3
    assert armed["due_at"] == pytest.approx(clock.now + 2.0)


async def test_arm_alignment_attempt_3_w1_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(1.5), None]), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 3
    assert armed["due_at"] == pytest.approx(clock.now + 2.0)


async def test_arm_alignment_attempt_3_w2_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(2.0), None]), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 3
    assert armed["due_at"] == pytest.approx(clock.now + 2.0)


async def test_arm_alignment_attempt_3_w2_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(2.5), None]), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 3
    assert armed["due_at"] == pytest.approx(clock.now + 2.5)


async def test_arm_alignment_attempt_3_w3_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(3.0), None]), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 3
    assert armed["due_at"] == pytest.approx(clock.now + 3.0)


async def test_arm_alignment_attempt_3_w3_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(3.5), None]), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 3
    assert armed["due_at"] == pytest.approx(clock.now + 3.5)


async def test_arm_alignment_attempt_3_w4_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(4.0), None]), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 3
    assert armed["due_at"] == pytest.approx(clock.now + 4.0)


async def test_arm_alignment_attempt_3_w4_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(4.5), None]), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 3
    assert armed["due_at"] == pytest.approx(clock.now + 4.5)


async def test_arm_alignment_attempt_3_w5_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(5.0), None]), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 3
    assert armed["due_at"] == pytest.approx(clock.now + 5.0)


async def test_arm_alignment_attempt_3_w6_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(6.0), None]), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 3
    assert armed["due_at"] == pytest.approx(clock.now + 6.0)


async def test_arm_alignment_attempt_3_w7_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(7.0), None]), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 3
    assert armed["due_at"] == pytest.approx(clock.now + 7.0)


async def test_arm_alignment_attempt_3_w7_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(7.5), None]), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 3
    assert armed["due_at"] == pytest.approx(clock.now + 7.5)


async def test_arm_alignment_attempt_3_w8_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(8.0), None]), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 3
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_3_w8_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(8.5), None]), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 3
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_3_w9_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(9.0), None]), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 3
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_3_w100_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(100.0), None]), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 3
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_4_default():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(None), None]), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 4
    assert armed["due_at"] == pytest.approx(clock.now + 4.0)


async def test_arm_alignment_attempt_4_w0_001():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.001), None]), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 4
    assert armed["due_at"] == pytest.approx(clock.now + 4.0)


async def test_arm_alignment_attempt_4_w0_1():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.1), None]), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 4
    assert armed["due_at"] == pytest.approx(clock.now + 4.0)


async def test_arm_alignment_attempt_4_w0_25():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.25), None]), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 4
    assert armed["due_at"] == pytest.approx(clock.now + 4.0)


async def test_arm_alignment_attempt_4_w0_4():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.4), None]), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 4
    assert armed["due_at"] == pytest.approx(clock.now + 4.0)


async def test_arm_alignment_attempt_4_w0_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.5), None]), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 4
    assert armed["due_at"] == pytest.approx(clock.now + 4.0)


async def test_arm_alignment_attempt_4_w0_6():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.6), None]), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 4
    assert armed["due_at"] == pytest.approx(clock.now + 4.0)


async def test_arm_alignment_attempt_4_w0_75():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.75), None]), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 4
    assert armed["due_at"] == pytest.approx(clock.now + 4.0)


async def test_arm_alignment_attempt_4_w1_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(1.0), None]), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 4
    assert armed["due_at"] == pytest.approx(clock.now + 4.0)


async def test_arm_alignment_attempt_4_w1_25():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(1.25), None]), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 4
    assert armed["due_at"] == pytest.approx(clock.now + 4.0)


async def test_arm_alignment_attempt_4_w1_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(1.5), None]), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 4
    assert armed["due_at"] == pytest.approx(clock.now + 4.0)


async def test_arm_alignment_attempt_4_w2_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(2.0), None]), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 4
    assert armed["due_at"] == pytest.approx(clock.now + 4.0)


async def test_arm_alignment_attempt_4_w2_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(2.5), None]), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 4
    assert armed["due_at"] == pytest.approx(clock.now + 4.0)


async def test_arm_alignment_attempt_4_w3_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(3.0), None]), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 4
    assert armed["due_at"] == pytest.approx(clock.now + 4.0)


async def test_arm_alignment_attempt_4_w3_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(3.5), None]), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 4
    assert armed["due_at"] == pytest.approx(clock.now + 4.0)


async def test_arm_alignment_attempt_4_w4_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(4.0), None]), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 4
    assert armed["due_at"] == pytest.approx(clock.now + 4.0)


async def test_arm_alignment_attempt_4_w4_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(4.5), None]), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 4
    assert armed["due_at"] == pytest.approx(clock.now + 4.5)


async def test_arm_alignment_attempt_4_w5_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(5.0), None]), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 4
    assert armed["due_at"] == pytest.approx(clock.now + 5.0)


async def test_arm_alignment_attempt_4_w6_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(6.0), None]), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 4
    assert armed["due_at"] == pytest.approx(clock.now + 6.0)


async def test_arm_alignment_attempt_4_w7_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(7.0), None]), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 4
    assert armed["due_at"] == pytest.approx(clock.now + 7.0)


async def test_arm_alignment_attempt_4_w7_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(7.5), None]), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 4
    assert armed["due_at"] == pytest.approx(clock.now + 7.5)


async def test_arm_alignment_attempt_4_w8_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(8.0), None]), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 4
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_4_w8_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(8.5), None]), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 4
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_4_w9_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(9.0), None]), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 4
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_4_w100_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(100.0), None]), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 4
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_5_default():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(None), None]), clock=clock)
    for k in range(4):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 5
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_5_w0_001():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.001), None]), clock=clock)
    for k in range(4):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 5
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_5_w0_1():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.1), None]), clock=clock)
    for k in range(4):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 5
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_5_w0_25():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.25), None]), clock=clock)
    for k in range(4):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 5
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_5_w0_4():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.4), None]), clock=clock)
    for k in range(4):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 5
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_5_w0_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.5), None]), clock=clock)
    for k in range(4):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 5
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_5_w0_6():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.6), None]), clock=clock)
    for k in range(4):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 5
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_5_w0_75():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.75), None]), clock=clock)
    for k in range(4):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 5
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_5_w1_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(1.0), None]), clock=clock)
    for k in range(4):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 5
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_5_w1_25():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(1.25), None]), clock=clock)
    for k in range(4):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 5
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_5_w1_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(1.5), None]), clock=clock)
    for k in range(4):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 5
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_5_w2_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(2.0), None]), clock=clock)
    for k in range(4):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 5
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_5_w2_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(2.5), None]), clock=clock)
    for k in range(4):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 5
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_5_w3_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(3.0), None]), clock=clock)
    for k in range(4):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 5
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_5_w3_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(3.5), None]), clock=clock)
    for k in range(4):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 5
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_5_w4_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(4.0), None]), clock=clock)
    for k in range(4):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 5
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_5_w4_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(4.5), None]), clock=clock)
    for k in range(4):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 5
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_5_w5_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(5.0), None]), clock=clock)
    for k in range(4):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 5
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_5_w6_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(6.0), None]), clock=clock)
    for k in range(4):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 5
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_5_w7_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(7.0), None]), clock=clock)
    for k in range(4):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 5
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_5_w7_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(7.5), None]), clock=clock)
    for k in range(4):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 5
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_5_w8_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(8.0), None]), clock=clock)
    for k in range(4):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 5
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_5_w8_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(8.5), None]), clock=clock)
    for k in range(4):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 5
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_5_w9_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(9.0), None]), clock=clock)
    for k in range(4):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 5
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_5_w100_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(100.0), None]), clock=clock)
    for k in range(4):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 5
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_6_default():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(None), None]), clock=clock)
    for k in range(5):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 6
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_6_w0_001():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.001), None]), clock=clock)
    for k in range(5):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 6
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_6_w0_1():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.1), None]), clock=clock)
    for k in range(5):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 6
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_6_w0_25():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.25), None]), clock=clock)
    for k in range(5):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 6
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_6_w0_4():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.4), None]), clock=clock)
    for k in range(5):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 6
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_6_w0_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.5), None]), clock=clock)
    for k in range(5):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 6
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_6_w0_6():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.6), None]), clock=clock)
    for k in range(5):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 6
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_6_w0_75():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(0.75), None]), clock=clock)
    for k in range(5):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 6
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_6_w1_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(1.0), None]), clock=clock)
    for k in range(5):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 6
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_6_w1_25():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(1.25), None]), clock=clock)
    for k in range(5):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 6
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_6_w1_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(1.5), None]), clock=clock)
    for k in range(5):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 6
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_6_w2_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(2.0), None]), clock=clock)
    for k in range(5):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 6
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_6_w2_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(2.5), None]), clock=clock)
    for k in range(5):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 6
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_6_w3_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(3.0), None]), clock=clock)
    for k in range(5):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 6
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_6_w3_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(3.5), None]), clock=clock)
    for k in range(5):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 6
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_6_w4_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(4.0), None]), clock=clock)
    for k in range(5):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 6
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_6_w4_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(4.5), None]), clock=clock)
    for k in range(5):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 6
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_6_w5_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(5.0), None]), clock=clock)
    for k in range(5):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 6
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_6_w6_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(6.0), None]), clock=clock)
    for k in range(5):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 6
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_6_w7_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(7.0), None]), clock=clock)
    for k in range(5):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 6
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_6_w7_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(7.5), None]), clock=clock)
    for k in range(5):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 6
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_6_w8_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(8.0), None]), clock=clock)
    for k in range(5):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 6
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_6_w8_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(8.5), None]), clock=clock)
    for k in range(5):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 6
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_6_w9_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(9.0), None]), clock=clock)
    for k in range(5):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 6
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_arm_alignment_attempt_6_w100_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(script=[loss(100.0), None]), clock=clock)
    for k in range(5):
        assert pump._defer_drain('owner-a', attempts=k) is True
    await pump._drain_after_publication('owner-a')
    armed = pump._deferred_drains['owner-a']
    assert armed["attempts"] == 6
    assert armed["due_at"] == pytest.approx(clock.now + 8.0)


async def test_continuation_alignment_attempt_1_default():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=0.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 1
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 0.0)


async def test_continuation_alignment_attempt_1_w0_25():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=0.25) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 1
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 0.25)


async def test_continuation_alignment_attempt_1_w0_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=0.5) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 1
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 0.5)


async def test_continuation_alignment_attempt_1_w1_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=1.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 1
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 1.0)


async def test_continuation_alignment_attempt_1_w2_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=2.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 1
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 2.0)


async def test_continuation_alignment_attempt_1_w3_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=3.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 1
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 3.0)


async def test_continuation_alignment_attempt_1_w4_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=4.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 1
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 4.0)


async def test_continuation_alignment_attempt_1_w5_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=5.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 1
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 5.0)


async def test_continuation_alignment_attempt_1_w6_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=6.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 1
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 6.0)


async def test_continuation_alignment_attempt_1_w7_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=7.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 1
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 7.0)


async def test_continuation_alignment_attempt_1_w8_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=8.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 1
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 8.0)


async def test_continuation_alignment_attempt_1_w8_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=8.5) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 1
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 8.0)


async def test_continuation_alignment_attempt_1_w9_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=9.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 1
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 8.0)


async def test_continuation_alignment_attempt_1_w100_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(0):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=100.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 1
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 8.0)


async def test_continuation_alignment_attempt_2_default():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=0.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 2
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 0.0)


async def test_continuation_alignment_attempt_2_w0_25():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=0.25) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 2
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 0.25)


async def test_continuation_alignment_attempt_2_w0_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=0.5) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 2
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 0.5)


async def test_continuation_alignment_attempt_2_w1_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=1.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 2
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 1.0)


async def test_continuation_alignment_attempt_2_w2_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=2.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 2
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 2.0)


async def test_continuation_alignment_attempt_2_w3_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=3.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 2
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 3.0)


async def test_continuation_alignment_attempt_2_w4_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=4.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 2
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 4.0)


async def test_continuation_alignment_attempt_2_w5_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=5.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 2
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 5.0)


async def test_continuation_alignment_attempt_2_w6_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=6.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 2
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 6.0)


async def test_continuation_alignment_attempt_2_w7_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=7.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 2
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 7.0)


async def test_continuation_alignment_attempt_2_w8_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=8.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 2
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 8.0)


async def test_continuation_alignment_attempt_2_w8_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=8.5) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 2
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 8.0)


async def test_continuation_alignment_attempt_2_w9_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=9.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 2
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 8.0)


async def test_continuation_alignment_attempt_2_w100_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(1):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=100.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 2
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 8.0)


async def test_continuation_alignment_attempt_3_default():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=0.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 3
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 0.0)


async def test_continuation_alignment_attempt_3_w0_25():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=0.25) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 3
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 0.25)


async def test_continuation_alignment_attempt_3_w0_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=0.5) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 3
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 0.5)


async def test_continuation_alignment_attempt_3_w1_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=1.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 3
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 1.0)


async def test_continuation_alignment_attempt_3_w2_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=2.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 3
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 2.0)


async def test_continuation_alignment_attempt_3_w3_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=3.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 3
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 3.0)


async def test_continuation_alignment_attempt_3_w4_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=4.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 3
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 4.0)


async def test_continuation_alignment_attempt_3_w5_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=5.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 3
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 5.0)


async def test_continuation_alignment_attempt_3_w6_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=6.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 3
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 6.0)


async def test_continuation_alignment_attempt_3_w7_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=7.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 3
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 7.0)


async def test_continuation_alignment_attempt_3_w8_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=8.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 3
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 8.0)


async def test_continuation_alignment_attempt_3_w8_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=8.5) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 3
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 8.0)


async def test_continuation_alignment_attempt_3_w9_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=9.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 3
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 8.0)


async def test_continuation_alignment_attempt_3_w100_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(2):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=100.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 3
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 8.0)


async def test_continuation_alignment_attempt_4_default():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=0.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 4
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 0.0)


async def test_continuation_alignment_attempt_4_w0_25():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=0.25) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 4
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 0.25)


async def test_continuation_alignment_attempt_4_w0_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=0.5) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 4
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 0.5)


async def test_continuation_alignment_attempt_4_w1_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=1.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 4
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 1.0)


async def test_continuation_alignment_attempt_4_w2_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=2.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 4
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 2.0)


async def test_continuation_alignment_attempt_4_w3_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=3.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 4
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 3.0)


async def test_continuation_alignment_attempt_4_w4_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=4.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 4
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 4.0)


async def test_continuation_alignment_attempt_4_w5_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=5.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 4
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 5.0)


async def test_continuation_alignment_attempt_4_w6_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=6.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 4
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 6.0)


async def test_continuation_alignment_attempt_4_w7_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=7.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 4
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 7.0)


async def test_continuation_alignment_attempt_4_w8_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=8.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 4
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 8.0)


async def test_continuation_alignment_attempt_4_w8_5():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=8.5) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 4
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 8.0)


async def test_continuation_alignment_attempt_4_w9_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=9.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 4
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 8.0)


async def test_continuation_alignment_attempt_4_w100_0():
    clock = FakeClock()
    pump = make_pump(ScriptMerge(), clock=clock)
    for k in range(3):
        assert pump._defer_drain('owner-a', continuation=True, attempts=k) is True
    assert pump._defer_drain('owner-a', continuation=True, retry_after=100.0) is True
    entry = pump._deferred_drains['owner-a']
    assert entry["attempts"] == 4
    assert entry["continuation"] is True
    assert entry["due_at"] == pytest.approx(clock.now + 8.0)


async def test_lane_e2e_w0_25_does_not_drain_before_the_window():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(0.25), None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    clock.advance(0.5 - 0.001)
    assert await pump._drain_deferred_due() == 0
    assert 'owner-a' in pump._deferred_drains
    assert merge.drained == ['owner-a']


async def test_lane_e2e_w0_25_drains_after_the_window():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(0.25), None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    clock.advance(0.5 + 0.001)
    assert await pump._drain_deferred_due() == 1
    assert 'owner-a' not in pump._deferred_drains
    assert merge.drained == ['owner-a', 'owner-a']


async def test_lane_e2e_w0_5_does_not_drain_before_the_window():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(0.5), None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    clock.advance(0.5 - 0.001)
    assert await pump._drain_deferred_due() == 0
    assert 'owner-a' in pump._deferred_drains
    assert merge.drained == ['owner-a']


async def test_lane_e2e_w0_5_drains_after_the_window():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(0.5), None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    clock.advance(0.5 + 0.001)
    assert await pump._drain_deferred_due() == 1
    assert 'owner-a' not in pump._deferred_drains
    assert merge.drained == ['owner-a', 'owner-a']


async def test_lane_e2e_w1_0_does_not_drain_before_the_window():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(1.0), None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    clock.advance(1.0 - 0.001)
    assert await pump._drain_deferred_due() == 0
    assert 'owner-a' in pump._deferred_drains
    assert merge.drained == ['owner-a']


async def test_lane_e2e_w1_0_drains_after_the_window():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(1.0), None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    clock.advance(1.0 + 0.001)
    assert await pump._drain_deferred_due() == 1
    assert 'owner-a' not in pump._deferred_drains
    assert merge.drained == ['owner-a', 'owner-a']


async def test_lane_e2e_w2_0_does_not_drain_before_the_window():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(2.0), None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    clock.advance(2.0 - 0.001)
    assert await pump._drain_deferred_due() == 0
    assert 'owner-a' in pump._deferred_drains
    assert merge.drained == ['owner-a']


async def test_lane_e2e_w2_0_drains_after_the_window():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(2.0), None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    clock.advance(2.0 + 0.001)
    assert await pump._drain_deferred_due() == 1
    assert 'owner-a' not in pump._deferred_drains
    assert merge.drained == ['owner-a', 'owner-a']


async def test_lane_e2e_w4_0_does_not_drain_before_the_window():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(4.0), None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    clock.advance(4.0 - 0.001)
    assert await pump._drain_deferred_due() == 0
    assert 'owner-a' in pump._deferred_drains
    assert merge.drained == ['owner-a']


async def test_lane_e2e_w4_0_drains_after_the_window():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(4.0), None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    clock.advance(4.0 + 0.001)
    assert await pump._drain_deferred_due() == 1
    assert 'owner-a' not in pump._deferred_drains
    assert merge.drained == ['owner-a', 'owner-a']


async def test_lane_e2e_w8_0_does_not_drain_before_the_window():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(8.0), None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    clock.advance(8.0 - 0.001)
    assert await pump._drain_deferred_due() == 0
    assert 'owner-a' in pump._deferred_drains
    assert merge.drained == ['owner-a']


async def test_lane_e2e_w8_0_drains_after_the_window():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(8.0), None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    clock.advance(8.0 + 0.001)
    assert await pump._drain_deferred_due() == 1
    assert 'owner-a' not in pump._deferred_drains
    assert merge.drained == ['owner-a', 'owner-a']


async def test_lane_e2e_w100_0_does_not_drain_before_the_window():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(100.0), None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    clock.advance(8.0 - 0.001)
    assert await pump._drain_deferred_due() == 0
    assert 'owner-a' in pump._deferred_drains
    assert merge.drained == ['owner-a']


async def test_lane_e2e_w100_0_drains_after_the_window():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(100.0), None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    clock.advance(8.0 + 0.001)
    assert await pump._drain_deferred_due() == 1
    assert 'owner-a' not in pump._deferred_drains
    assert merge.drained == ['owner-a', 'owner-a']


async def test_lane_e2e_w0_001_does_not_drain_before_the_window():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(0.001), None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    clock.advance(0.5 - 0.001)
    assert await pump._drain_deferred_due() == 0
    assert 'owner-a' in pump._deferred_drains
    assert merge.drained == ['owner-a']


async def test_lane_e2e_w0_001_drains_after_the_window():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(0.001), None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    clock.advance(0.5 + 0.001)
    assert await pump._drain_deferred_due() == 1
    assert 'owner-a' not in pump._deferred_drains
    assert merge.drained == ['owner-a', 'owner-a']


async def test_lane_e2e_default_does_not_drain_before_the_window():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(None), None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    clock.advance(0.5 - 0.001)
    assert await pump._drain_deferred_due() == 0
    assert 'owner-a' in pump._deferred_drains
    assert merge.drained == ['owner-a']


async def test_lane_e2e_default_drains_after_the_window():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(None), None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    clock.advance(0.5 + 0.001)
    assert await pump._drain_deferred_due() == 1
    assert 'owner-a' not in pump._deferred_drains
    assert merge.drained == ['owner-a', 'owner-a']


async def test_multi_owner_wake_order_pair_0():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(0.5), loss(2.0), None, None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    await pump._drain_after_publication('owner-b')
    clock.advance(min(0.5, 2.0) + 0.001)
    drained = await pump._drain_deferred_due()
    assert drained == 1
    assert merge.drained[-1] == 'owner-a'
    assert 'owner-b' in pump._deferred_drains


async def test_multi_owner_wake_order_pair_1():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(2.0), loss(0.5), None, None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    await pump._drain_after_publication('owner-b')
    clock.advance(min(2.0, 0.5) + 0.001)
    drained = await pump._drain_deferred_due()
    assert drained == 1
    assert merge.drained[-1] == 'owner-b'
    assert 'owner-a' in pump._deferred_drains


async def test_multi_owner_wake_order_pair_2():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(0.25), loss(8.0), None, None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    await pump._drain_after_publication('owner-b')
    clock.advance(min(0.5, 8.0) + 0.001)
    drained = await pump._drain_deferred_due()
    assert drained == 1
    assert merge.drained[-1] == 'owner-a'
    assert 'owner-b' in pump._deferred_drains


async def test_multi_owner_wake_order_pair_3():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(8.0), loss(0.25), None, None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    await pump._drain_after_publication('owner-b')
    clock.advance(min(8.0, 0.5) + 0.001)
    drained = await pump._drain_deferred_due()
    assert drained == 1
    assert merge.drained[-1] == 'owner-b'
    assert 'owner-a' in pump._deferred_drains


async def test_multi_owner_wake_order_pair_4():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(1.0), loss(1.0), None, None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    await pump._drain_after_publication('owner-b')
    clock.advance(min(1.0, 1.0) + 0.001)
    drained = await pump._drain_deferred_due()
    assert drained == 2
    assert not pump._deferred_drains


async def test_multi_owner_wake_order_pair_5():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(0.5), loss(0.5), None, None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    await pump._drain_after_publication('owner-b')
    clock.advance(min(0.5, 0.5) + 0.001)
    drained = await pump._drain_deferred_due()
    assert drained == 2
    assert not pump._deferred_drains


async def test_multi_owner_wake_order_pair_6():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(2.0), loss(2.0), None, None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    await pump._drain_after_publication('owner-b')
    clock.advance(min(2.0, 2.0) + 0.001)
    drained = await pump._drain_deferred_due()
    assert drained == 2
    assert not pump._deferred_drains


async def test_multi_owner_wake_order_pair_7():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(3.0), loss(4.0), None, None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    await pump._drain_after_publication('owner-b')
    clock.advance(min(3.0, 4.0) + 0.001)
    drained = await pump._drain_deferred_due()
    assert drained == 1
    assert merge.drained[-1] == 'owner-a'
    assert 'owner-b' in pump._deferred_drains


async def test_multi_owner_wake_order_pair_8():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(4.0), loss(4.0), None, None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    await pump._drain_after_publication('owner-b')
    clock.advance(min(4.0, 4.0) + 0.001)
    drained = await pump._drain_deferred_due()
    assert drained == 2
    assert not pump._deferred_drains


async def test_multi_owner_wake_order_pair_9():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(0.001), loss(100.0), None, None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    await pump._drain_after_publication('owner-b')
    clock.advance(min(0.5, 8.0) + 0.001)
    drained = await pump._drain_deferred_due()
    assert drained == 1
    assert merge.drained[-1] == 'owner-a'
    assert 'owner-b' in pump._deferred_drains


async def test_multi_owner_wake_order_pair_10():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(100.0), loss(0.001), None, None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    await pump._drain_after_publication('owner-b')
    clock.advance(min(8.0, 0.5) + 0.001)
    drained = await pump._drain_deferred_due()
    assert drained == 1
    assert merge.drained[-1] == 'owner-b'
    assert 'owner-a' in pump._deferred_drains


async def test_multi_owner_wake_order_pair_11():
    clock = FakeClock()
    merge = ScriptMerge(script=[loss(6.0), loss(7.0), None, None])
    pump = make_pump(merge, clock=clock)
    await pump._drain_after_publication('owner-a')
    await pump._drain_after_publication('owner-b')
    clock.advance(min(6.0, 7.0) + 0.001)
    drained = await pump._drain_deferred_due()
    assert drained == 1
    assert merge.drained[-1] == 'owner-a'
    assert 'owner-b' in pump._deferred_drains
