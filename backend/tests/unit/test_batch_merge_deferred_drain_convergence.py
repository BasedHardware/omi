"""Deferred publication-drain convergence contracts.

A publication drain that loses to Firestore contention arms the owner on a
bounded deferred lane instead of waiting for an incidental later drain. This
suite pins the lane end to end: arming, the carried attempt budget, the exact
backoff schedule, due-drain lifecycle, cancellation safety, the 100-commit
continuation, ledger bounds, flush-at-stop semantics, lane scheduling, and
the log taxonomy that replaced the bare swallowed ERROR line.

Failure-Class: FC-publication-drain-contention-exhaustion-left-without-a-convergence-owner
"""

import asyncio
import contextlib
import logging
import types

import pytest

from database.firestore_transaction_retry import FirestoreContentionExhausted
import utils.batch_pipeline.pump as pump_module
from utils.batch_pipeline.pump import Pump

try:
    # The lane's budget names. A parent revision without the deferred lane
    # collects fine and fails at runtime below — that failure IS the RED
    # half of this suite's red/green proof.
    from utils.batch_pipeline.pump import (
        DRAIN_BACKLOG_CONTINUATION_ATTEMPTS,
        DRAIN_RETRY_BASE_SECONDS,
        DRAIN_RETRY_LEDGER_CAP,
        DRAIN_RETRY_MAX_ATTEMPTS,
        DRAIN_RETRY_MAX_SECONDS,
        deferred_drain_delay,
    )
except ImportError:
    pass


@pytest.fixture(autouse=True)
def inline_blocking(monkeypatch):
    async def passthrough(executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(pump_module, 'run_blocking', passthrough)


@pytest.fixture(autouse=True)
async def lane_hygiene():
    """No test leaves a pending lane behind: stop and cancel same-loop lanes."""
    yield
    loop = asyncio.get_running_loop()
    pumps = [obj for obj in gc_objects() if isinstance(obj, Pump)]
    for pump in pumps:
        with contextlib.suppress(Exception):
            pump._deferred_stopped = True
        lane = pump.__dict__.get('_deferred_lane')
        if lane is not None and not lane.done() and lane.get_loop() is loop:
            lane.cancel()
            with contextlib.suppress(asyncio.CancelledError, RuntimeError):
                await lane


def gc_objects():
    import gc

    return gc.get_objects()


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


def make_pump(merge=None, **overrides):
    pump = Pump(
        types.SimpleNamespace(),
        types.SimpleNamespace(),
        merge=merge or ScriptMerge(),
        publish_concurrency=overrides.pop('publish_concurrency', 1),
    )
    for name, value in overrides.items():
        setattr(pump, name, value)
    return pump


class Clock:
    def __init__(self, start=100.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


# ---------------------------------------------------------------------------
# Arming at the publication catch site
# ---------------------------------------------------------------------------


async def test_exhausted_publication_drain_arms_the_owner():
    pump = make_pump(ScriptMerge([FirestoreContentionExhausted('hot')]))
    await pump._drain_after_publication('owner-1')
    armed = pump._deferred_drains['owner-1']
    assert armed['attempts'] == 1
    assert armed['continuation'] is False


async def test_first_deferral_uses_the_base_backoff_step():
    clock = Clock()
    pump = make_pump(ScriptMerge([FirestoreContentionExhausted('hot')]), _monotonic=clock)
    await pump._drain_after_publication('owner-1')
    assert pump._deferred_drains['owner-1']['due_at'] == clock.now + DRAIN_RETRY_BASE_SECONDS


async def test_armed_owner_starts_the_lane_task():
    pump = make_pump(ScriptMerge([FirestoreContentionExhausted('hot')]))
    assert pump._deferred_lane is None
    await pump._drain_after_publication('owner-1')
    assert pump._deferred_lane is not None
    assert not pump._deferred_lane.done()


async def test_deferral_does_not_raise_out_of_the_catch_site():
    pump = make_pump(ScriptMerge([FirestoreContentionExhausted('hot')]))
    await pump._drain_after_publication('owner-1')  # must not raise


@pytest.mark.parametrize(
    'error', [FirestoreContentionExhausted('hot'), TimeoutError('slow'), ValueError('bad'), KeyError('x')]
)
async def test_every_exception_class_arms_the_lane(error):
    pump = make_pump(ScriptMerge([error]))
    await pump._drain_after_publication('owner-1')
    assert pump._deferred_drains['owner-1']['attempts'] == 1


async def test_cancellation_is_never_armed_and_always_propagates():
    pump = make_pump(ScriptMerge([asyncio.CancelledError()]))
    with pytest.raises(asyncio.CancelledError):
        await pump._drain_after_publication('owner-1')
    assert pump._deferred_drains == {}


async def test_healthy_drain_arms_nothing():
    pump = make_pump()
    await pump._drain_after_publication('owner-1')
    assert pump._deferred_drains == {}
    assert pump._deferred_lane is None


async def test_armed_entry_carries_no_stale_continuation_flag():
    pump = make_pump(ScriptMerge([FirestoreContentionExhausted('hot')]))
    await pump._drain_after_publication('owner-1')
    assert pump._deferred_drains['owner-1']['continuation'] is False


# ---------------------------------------------------------------------------
# The attempt budget carries forward
# ---------------------------------------------------------------------------


async def test_repeated_publication_losses_carry_one_budget():
    clock = Clock()
    merge = ScriptMerge()

    def always_hot(owner_id, now):
        merge.commits += 1
        raise FirestoreContentionExhausted('hot')

    merge.commit_next = always_hot
    pump = make_pump(merge, _monotonic=clock)
    for _ in range(3):
        clock.advance(30.0)
        await pump._drain_after_publication('owner-1')
    assert pump._deferred_drains['owner-1']['attempts'] == 3


async def test_carry_forward_reaches_the_cap_and_refuses():
    clock = Clock()
    merge = ScriptMerge()

    def always_hot(owner_id, now):
        merge.commits += 1
        raise FirestoreContentionExhausted('hot')

    merge.commit_next = always_hot
    pump = make_pump(merge, _monotonic=clock)
    for _ in range(64):
        clock.advance(30.0)
        await pump._drain_after_publication('owner-1')
        if not pump._deferred_drains:
            break
    assert pump._deferred_drains == {}


async def test_refusal_leaves_no_entry_behind():
    clock = Clock()
    merge = ScriptMerge()

    def always_hot(owner_id, now):
        merge.commits += 1
        raise FirestoreContentionExhausted('hot')

    merge.commit_next = always_hot
    pump = make_pump(merge, _monotonic=clock)
    for _ in range(64):
        clock.advance(30.0)
        await pump._drain_after_publication('owner-1')
        if not pump._deferred_drains:
            break
    assert 'owner-1' not in pump._deferred_drains


async def test_a_converged_owner_restarts_a_fresh_budget():
    clock = Clock()
    script = [FirestoreContentionExhausted('hot'), {'segment_id': 'a'}, None, FirestoreContentionExhausted('hot'), None]
    pump = make_pump(ScriptMerge(script), _monotonic=clock)
    await pump._drain_after_publication('owner-1')
    assert pump._deferred_drains['owner-1']['attempts'] == 1
    clock.advance(30.0)
    await pump._drain_deferred_due()
    assert pump._deferred_drains == {}
    clock.advance(30.0)
    await pump._drain_after_publication('owner-1')
    assert pump._deferred_drains['owner-1']['attempts'] == 1


async def test_explicit_attempts_override_the_ledger():
    clock = Clock()
    pump = make_pump(ScriptMerge(), _monotonic=clock)
    assert pump._defer_drain('owner-1', attempts=DRAIN_RETRY_MAX_ATTEMPTS) is False
    assert pump._deferred_drains == {}


async def test_explicit_attempts_within_the_cap_arm():
    clock = Clock()
    pump = make_pump(ScriptMerge(), _monotonic=clock)
    assert pump._defer_drain('owner-1', attempts=DRAIN_RETRY_MAX_ATTEMPTS - 1) is True
    assert pump._deferred_drains['owner-1']['attempts'] == DRAIN_RETRY_MAX_ATTEMPTS


# ---------------------------------------------------------------------------
# The backoff schedule
# ---------------------------------------------------------------------------


def test_delay_schedule_is_the_documented_doubling():
    expected = {1: 0.5, 2: 1.0, 3: 2.0, 4: 4.0, 5: 8.0, 6: 8.0, 7: 8.0}
    for attempt, value in expected.items():
        assert deferred_drain_delay(attempt) == value


def test_delay_is_bounded_by_the_max_constant():
    assert DRAIN_RETRY_MAX_SECONDS == 8.0
    for attempt in range(1, 33):
        assert deferred_drain_delay(attempt) <= DRAIN_RETRY_MAX_SECONDS


def test_delay_never_decreases():
    values = [deferred_drain_delay(a) for a in range(1, 17)]
    assert values == sorted(values)


def test_delay_returns_float_for_every_attempt():
    for attempt in range(0, 40):
        assert isinstance(deferred_drain_delay(attempt), float)


def test_first_attempt_ignores_larger_multipliers():
    assert deferred_drain_delay(1) == DRAIN_RETRY_BASE_SECONDS == 0.5


def test_module_constants_match_the_documented_budget():
    assert DRAIN_RETRY_BASE_SECONDS == 0.5
    assert DRAIN_RETRY_MAX_ATTEMPTS == 6
    assert DRAIN_BACKLOG_CONTINUATION_ATTEMPTS == 4
    assert DRAIN_RETRY_LEDGER_CAP == 512


# ---------------------------------------------------------------------------
# Due-drain lifecycle
# ---------------------------------------------------------------------------


async def test_undue_owner_is_never_drained():
    clock = Clock()
    merge = ScriptMerge([FirestoreContentionExhausted('hot'), None])
    pump = make_pump(merge, _monotonic=clock)
    await pump._drain_after_publication('owner-1')
    drained = await pump._drain_deferred_due()
    assert drained == 0
    assert merge.commits == 1  # only the publication drain ran


async def test_due_owner_is_drained_and_converged():
    clock = Clock()
    merge = ScriptMerge([FirestoreContentionExhausted('hot'), None])
    pump = make_pump(merge, _monotonic=clock)
    await pump._drain_after_publication('owner-1')
    clock.advance(DRAIN_RETRY_BASE_SECONDS + 0.01)
    drained = await pump._drain_deferred_due()
    assert drained == 1
    assert merge.commits == 2
    assert pump._deferred_drains == {}


async def test_due_drain_failure_rearms_with_the_carried_budget():
    clock = Clock()
    merge = ScriptMerge()

    def always_hot(owner_id, now):
        merge.commits += 1
        raise FirestoreContentionExhausted('hot')

    merge.commit_next = always_hot
    pump = make_pump(merge, _monotonic=clock)
    await pump._drain_after_publication('owner-1')
    clock.advance(30.0)
    await pump._drain_deferred_due()
    assert pump._deferred_drains['owner-1']['attempts'] == 2
    assert pump._deferred_drains['owner-1']['due_at'] == clock.now + deferred_drain_delay(2)


async def test_due_drain_cap_refusal_empties_the_ledger():
    clock = Clock()
    merge = ScriptMerge()

    def always_hot(owner_id, now):
        merge.commits += 1
        raise FirestoreContentionExhausted('hot')

    merge.commit_next = always_hot
    pump = make_pump(merge, _monotonic=clock)
    pump._defer_drain('owner-1', attempts=DRAIN_RETRY_MAX_ATTEMPTS - 1)
    clock.advance(30.0)
    await pump._drain_deferred_due()
    assert pump._deferred_drains == {}
    assert merge.commits == 1


async def test_due_drain_returns_the_drained_owner_count():
    clock = Clock()
    merge = ScriptMerge([FirestoreContentionExhausted('hot'), None, None])
    pump = make_pump(merge, _monotonic=clock)
    pump._defer_drain('a')
    pump._defer_drain('b')
    clock.advance(30.0)
    assert await pump._drain_deferred_due() == 1  # a failed again and re-armed
    assert pump._deferred_drains['a']['attempts'] == 2
    clock.advance(30.0)
    assert await pump._drain_deferred_due() == 1  # a converges on its second budget
    assert pump._deferred_drains == {}


async def test_only_due_owners_are_drained():
    clock = Clock()
    merge = ScriptMerge([None, FirestoreContentionExhausted('hot'), None])
    pump = make_pump(merge, _monotonic=clock)
    pump._defer_drain('due-now')
    pump._deferred_drains['due-later'] = {'attempts': 1, 'due_at': clock.now + 999.0, 'continuation': False}
    clock.advance(30.0)
    drained = await pump._drain_deferred_due()
    assert drained == 1
    assert 'due-later' in pump._deferred_drains


async def test_sibling_convergence_lets_the_loser_move_on():
    """An owner drained by a sibling between arm and due is skipped, not double-committed."""
    clock = Clock()
    merge = ScriptMerge([FirestoreContentionExhausted('hot'), None])
    pump = make_pump(merge, _monotonic=clock)
    await pump._drain_after_publication('owner-1')
    del pump._deferred_drains['owner-1']  # sibling converged it meanwhile
    clock.advance(30.0)
    assert await pump._drain_deferred_due() == 0


async def test_cancelled_due_drain_rearms_and_propagates():
    clock = Clock()
    merge = ScriptMerge()
    merge.commit_next = lambda owner_id, now: (_ for _ in ()).throw(asyncio.CancelledError())
    pump = make_pump(merge, _monotonic=clock)
    armed = {'attempts': 2, 'due_at': clock.now - 1.0, 'continuation': False}
    pump._deferred_drains['owner-1'] = dict(armed)
    with pytest.raises(asyncio.CancelledError):
        await pump._drain_deferred_due()
    rearmed = pump._deferred_drains['owner-1']
    assert rearmed['attempts'] == armed['attempts']
    assert rearmed['continuation'] == armed['continuation']
    assert rearmed['due_at'] >= clock.now - 1.0  # retrigged, never lost


async def test_due_drain_waits_for_the_owner_serial_lock():
    """A deferred drain cannot overlap a publication drain of the same owner."""
    clock = Clock()
    merge = ScriptMerge([None])
    pump = make_pump(merge, _monotonic=clock)
    pump._defer_drain('owner-1')
    overlap = []
    original = merge.commit_next

    async def hold_lock_elsewhere():
        async with pump._owner_serial('owner-1'):
            overlap.append('held')
            await asyncio.sleep(0.02)
            overlap.append('released')

    holder = asyncio.create_task(hold_lock_elsewhere())
    await asyncio.sleep(0)
    lane = asyncio.create_task(pump._drain_deferred_due())
    await asyncio.gather(holder, lane)
    assert overlap[0] == 'held' and overlap[1] == 'released'


# ---------------------------------------------------------------------------
# The 100-commit continuation
# ---------------------------------------------------------------------------


def endless_merge(counter):
    merge = ScriptMerge()

    def commit_next(owner_id, now):
        counter['n'] += 1
        merge.drained.append(owner_id)
        return {'segment_id': f's{counter["n"]}'}

    merge.commit_next = commit_next
    return merge


async def test_backlog_bound_reaches_100_commits():
    counter = {'n': 0}
    clock = Clock()
    pump = make_pump(endless_merge(counter), _monotonic=clock)
    await pump.drain_owner('owner-1')
    assert counter['n'] == 100


async def test_backlog_bound_arms_an_instant_continuation():
    counter = {'n': 0}
    clock = Clock()
    pump = make_pump(endless_merge(counter), _monotonic=clock)
    await pump.drain_owner('owner-1')
    armed = pump._deferred_drains['owner-1']
    assert armed['continuation'] is True
    assert armed['attempts'] == 1
    assert armed['due_at'] - clock.now < 0.001


async def test_continuation_drains_immediately_when_due():
    counter = {'n': 0}
    clock = Clock()
    pump = make_pump(endless_merge(counter), _monotonic=clock)
    await pump.drain_owner('owner-1')
    before = counter['n']
    await pump._drain_deferred_due()
    assert counter['n'] == before + 100


async def test_continuation_budget_is_smaller_than_the_contention_budget():
    counter = {'n': 0}
    clock = Clock()
    pump = make_pump(endless_merge(counter), _monotonic=clock)
    await pump.drain_owner('owner-1')  # bound-hit: arms the first continuation
    rounds = 0
    while pump._deferred_drains and rounds < 16:
        await pump._drain_deferred_due()
        rounds += 1
    assert rounds == DRAIN_BACKLOG_CONTINUATION_ATTEMPTS
    assert counter['n'] == 100 * (1 + DRAIN_BACKLOG_CONTINUATION_ATTEMPTS)
    assert pump._deferred_drains == {}


async def test_continuation_success_converges_the_lane():
    counter = {'n': 0}
    clock = Clock()
    merge = ScriptMerge([{'segment_id': 'a'}] * 100)
    pump = make_pump(merge, _monotonic=clock)
    await pump.drain_owner('owner-1')
    assert pump._deferred_drains['owner-1']['continuation'] is True
    await pump._drain_deferred_due()
    assert pump._deferred_drains == {}


async def test_healthy_drain_below_the_bound_arms_nothing():
    clock = Clock()
    pump = make_pump(ScriptMerge([{'segment_id': 'a'}, None]), _monotonic=clock)
    await pump.drain_owner('owner-1')
    assert pump._deferred_drains == {}


# ---------------------------------------------------------------------------
# Ledger bounds and eviction
# ---------------------------------------------------------------------------


async def test_ledger_is_bounded_at_the_cap():
    clock = Clock()
    pump = make_pump(ScriptMerge(), _monotonic=clock)
    for i in range(DRAIN_RETRY_LEDGER_CAP + 10):
        pump._defer_drain(f'owner-{i}')
    assert len(pump._deferred_drains) == DRAIN_RETRY_LEDGER_CAP


async def test_eviction_is_oldest_armed_first():
    clock = Clock()
    pump = make_pump(ScriptMerge(), _monotonic=clock)
    for i in range(DRAIN_RETRY_LEDGER_CAP + 3):
        pump._defer_drain(f'owner-{i}')
    assert 'owner-0' not in pump._deferred_drains
    assert 'owner-1' not in pump._deferred_drains
    assert 'owner-2' not in pump._deferred_drains
    assert 'owner-3' in pump._deferred_drains
    assert f'owner-{DRAIN_RETRY_LEDGER_CAP + 2}' in pump._deferred_drains


async def test_evictions_are_counted():
    clock = Clock()
    pump = make_pump(ScriptMerge(), _monotonic=clock)
    for i in range(DRAIN_RETRY_LEDGER_CAP + 5):
        pump._defer_drain(f'owner-{i}')
    assert pump._deferred_evictions == 5


async def test_rearming_moves_an_owner_to_the_armed_tail():
    clock = Clock()
    pump = make_pump(ScriptMerge(), _monotonic=clock)
    pump._defer_drain('old')
    for i in range(1, DRAIN_RETRY_LEDGER_CAP):
        pump._defer_drain(f'filler-{i}')
    pump._defer_drain('old')  # re-armed: newest insertion
    for i in range(3):
        pump._defer_drain(f'new-{i}')
    assert 'old' in pump._deferred_drains
    assert 'filler-1' not in pump._deferred_drains


async def test_ledger_holds_independent_owner_budgets():
    clock = Clock()
    pump = make_pump(ScriptMerge(), _monotonic=clock)
    pump._defer_drain('a', attempts=2)
    pump._defer_drain('b', attempts=5)
    assert pump._deferred_drains['a']['attempts'] == 3
    assert pump._deferred_drains['b']['attempts'] == 6


# ---------------------------------------------------------------------------
# Flush at stop
# ---------------------------------------------------------------------------


async def test_flush_drains_every_armed_owner_once():
    clock = Clock()
    merge = ScriptMerge([FirestoreContentionExhausted('hot'), None, FirestoreContentionExhausted('hot'), None])
    pump = make_pump(merge, _monotonic=clock)
    pump._defer_drain('a')
    pump._defer_drain('b')
    await pump.flush_deferred_drains()
    assert pump._deferred_drains == {}
    assert merge.commits == 2


async def test_flush_stops_the_lane():
    clock = Clock()
    pump = make_pump(ScriptMerge(), _monotonic=clock)
    pump._defer_drain('a')
    pump._ensure_deferred_lane()
    await pump.flush_deferred_drains()
    assert pump._deferred_stopped is True
    assert pump._deferred_lane is None


async def test_flush_survives_a_failing_drain():
    clock = Clock()
    merge = ScriptMerge()

    def always_hot(owner_id, now):
        merge.commits += 1
        raise FirestoreContentionExhausted('hot')

    merge.commit_next = always_hot
    pump = make_pump(merge, _monotonic=clock)
    pump._defer_drain('a')
    pump._defer_drain('b')
    await pump.flush_deferred_drains()  # must not raise
    assert pump._deferred_drains == {}
    assert merge.commits == 2


async def test_flush_is_idempotent():
    clock = Clock()
    pump = make_pump(ScriptMerge(), _monotonic=clock)
    pump._defer_drain('a')
    await pump.flush_deferred_drains()
    await pump.flush_deferred_drains()
    assert pump._deferred_drains == {}


async def test_flush_of_an_empty_ledger_is_a_noop():
    clock = Clock()
    pump = make_pump(ScriptMerge(), _monotonic=clock)
    await pump.flush_deferred_drains()
    assert pump._deferred_stopped is True


async def test_flush_cancels_a_running_lane_cleanly():
    clock = Clock()
    pump = make_pump(ScriptMerge(), _monotonic=clock)
    pump._defer_drain('owner-1')  # lane armed, waiting on the 0.5s backoff
    pump._ensure_deferred_lane()
    await asyncio.sleep(0.01)
    await pump.flush_deferred_drains()
    await asyncio.sleep(0.01)
    assert pump._deferred_lane is None


async def test_armed_after_flush_stays_dormant_for_maintenance():
    clock = Clock()
    pump = make_pump(ScriptMerge(), _monotonic=clock)
    await pump.flush_deferred_drains()
    assert pump._defer_drain('owner-1') is True  # ledger arms
    assert pump._deferred_lane is None  # but the lane refuses to run


# ---------------------------------------------------------------------------
# Lane scheduling
# ---------------------------------------------------------------------------


async def test_lane_converges_a_failed_drain_end_to_end():
    merge = ScriptMerge([FirestoreContentionExhausted('hot'), None])
    pump = make_pump(merge)
    await pump._drain_after_publication('owner-1')
    await asyncio.sleep(DRAIN_RETRY_BASE_SECONDS + 0.2)
    assert pump._deferred_drains == {}
    assert merge.commits == 2
    assert pump._deferred_lane is None


async def test_lane_exits_when_the_ledger_empties():
    clock = Clock()
    pump = make_pump(ScriptMerge(), _monotonic=clock)
    pump._defer_drain('a')
    lane = pump._deferred_lane
    pump._deferred_drains.clear()
    pump._deferred_wake.set()
    await asyncio.wait_for(lane, timeout=1.0)
    assert lane.done() and not lane.cancelled()


async def test_wake_event_preempts_the_backoff_wait():
    clock = Clock()
    merge = ScriptMerge([FirestoreContentionExhausted('hot'), None])
    pump = make_pump(merge, _monotonic=clock)
    await pump._drain_after_publication('owner-1')
    clock.advance(DRAIN_RETRY_BASE_SECONDS + 0.01)  # due now, lane still waiting
    pump._deferred_wake.set()
    await asyncio.wait_for(asyncio.shield(pump._deferred_lane), timeout=1.0)
    assert merge.commits == 2


async def test_stopped_lane_never_starts():
    clock = Clock()
    pump = make_pump(ScriptMerge(), _monotonic=clock)
    pump._deferred_stopped = True
    pump._defer_drain('a')
    assert pump._deferred_lane is None


async def test_lane_restart_after_natural_exit():
    clock = Clock()
    pump = make_pump(ScriptMerge(), _monotonic=clock)
    pump._defer_drain('a')
    lane = pump._deferred_lane
    pump._deferred_drains.clear()
    pump._deferred_wake.set()
    await asyncio.wait_for(lane, timeout=1.0)
    assert pump._deferred_lane is None  # exited cleanly
    merge = ScriptMerge([FirestoreContentionExhausted('hot'), None])
    pump.merge = merge
    await pump._drain_after_publication('owner-9')  # arms again after exit
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_lane_resurrection_guard_tolerates_a_closed_loop(monkeypatch):
    """A lane cancelled by loop teardown must not raise from its own finally."""
    clock = Clock()
    pump = make_pump(ScriptMerge(), _monotonic=clock)
    pump._defer_drain('a')
    lane = pump._deferred_lane

    def refuse(*args, **kwargs):
        raise RuntimeError('loop is closed')

    monkeypatch.setattr(pump, '_ensure_deferred_lane', refuse)
    pump._deferred_drains.clear()
    pump._deferred_wake.set()
    await asyncio.wait_for(asyncio.shield(lane), timeout=1.0)
    assert lane.done()


async def test_due_lane_reports_zero_for_an_empty_ledger():
    clock = Clock()
    pump = make_pump(ScriptMerge(), _monotonic=clock)
    assert await pump._drain_deferred_due() == 0


# ---------------------------------------------------------------------------
# Log taxonomy
# ---------------------------------------------------------------------------


class LiveRecords(list):
    """A list view over caplog.records evaluated at read time, not call time."""

    def __init__(self, caplog):
        super().__init__()
        self._caplog = caplog

    def __iter__(self):
        return iter(record.getMessage() for record in self._caplog.records)

    def __len__(self):
        return len(self._caplog.records)


def capture_records(caplog, level=logging.INFO):
    caplog.set_level(level)
    return LiveRecords(caplog)


async def test_deferral_logs_the_deferred_info_line(caplog):
    records = capture_records(caplog)
    pump = make_pump(ScriptMerge([FirestoreContentionExhausted('hot')]))
    await pump._drain_after_publication('owner-1')
    deferred = [line for line in records if 'event=batch_merge_drain outcome=deferred' in line]
    assert deferred == ['event=batch_merge_drain outcome=deferred exception_type=FirestoreContentionExhausted']
    await pump.flush_deferred_drains()


async def test_converged_redrain_logs_the_converged_line(caplog):
    records = capture_records(caplog)
    clock = Clock()
    merge = ScriptMerge([FirestoreContentionExhausted('hot'), None])
    pump = make_pump(merge, _monotonic=clock)
    await pump._drain_after_publication('owner-1')
    clock.advance(30.0)
    await pump._drain_deferred_due()
    converged = [line for line in records if 'event=batch_merge_drain outcome=converged' in line]
    assert converged == ['event=batch_merge_drain outcome=converged attempt=1']
    await pump.flush_deferred_drains()


async def test_first_attempt_deferral_logs_no_error_line(caplog):
    records = capture_records(caplog)
    pump = make_pump(ScriptMerge([FirestoreContentionExhausted('hot')]))
    await pump._drain_after_publication('owner-1')
    assert not [line for line in records if 'event=batch_merge outcome=retry' in line]
    await pump.flush_deferred_drains()


async def test_cap_refusal_logs_the_historical_error_line(caplog):
    records = capture_records(caplog)
    clock = Clock()
    merge = ScriptMerge()

    def always_hot(owner_id, now):
        merge.commits += 1
        raise FirestoreContentionExhausted('hot')

    merge.commit_next = always_hot
    pump = make_pump(merge, _monotonic=clock)
    pump._deferred_drains['owner-1'] = {
        'attempts': DRAIN_RETRY_MAX_ATTEMPTS,
        'due_at': clock.now,
        'continuation': False,
    }
    clock.advance(30.0)
    await pump._drain_deferred_due()
    retry = [line for line in records if 'event=batch_merge outcome=retry' in line]
    assert len(retry) == 1
    assert 'exception_type=FirestoreContentionExhausted' in retry[0]


async def test_cap_refusal_at_the_publication_site_logs_the_error_line(caplog):
    records = capture_records(caplog)
    clock = Clock()
    merge = ScriptMerge()

    def always_hot(owner_id, now):
        merge.commits += 1
        raise FirestoreContentionExhausted('hot')

    merge.commit_next = always_hot
    pump = make_pump(merge, _monotonic=clock)
    pump._deferred_drains['owner-1'] = {
        'attempts': DRAIN_RETRY_MAX_ATTEMPTS,
        'due_at': clock.now,
        'continuation': False,
    }
    await pump._drain_after_publication('owner-1')
    retry = [line for line in records if 'event=batch_merge outcome=retry' in line]
    assert len(retry) == 1


async def test_continuation_convergence_logs_the_converged_line(caplog):
    records = capture_records(caplog)
    clock = Clock()
    merge = ScriptMerge([{'segment_id': 'a'}] * 100)
    pump = make_pump(merge, _monotonic=clock)
    await pump.drain_owner('owner-1')
    await pump._drain_deferred_due()
    converged = [line for line in records if 'event=batch_merge_drain outcome=converged' in line]
    assert converged == ['event=batch_merge_drain outcome=converged attempt=1']
    await pump.flush_deferred_drains()


async def test_flush_loss_logs_the_error_line_per_owner(caplog):
    records = capture_records(caplog)
    clock = Clock()
    merge = ScriptMerge()

    def always_hot(owner_id, now):
        merge.commits += 1
        raise FirestoreContentionExhausted('hot')

    merge.commit_next = always_hot
    pump = make_pump(merge, _monotonic=clock)
    pump._defer_drain('a', attempts=2)
    pump._defer_drain('b', attempts=5)
    await pump.flush_deferred_drains()
    retry = [line for line in records if 'event=batch_merge outcome=retry' in line]
    assert len(retry) == 2


async def test_due_drain_failure_logs_the_deferred_info_line_with_the_attempt(caplog):
    records = capture_records(caplog)
    clock = Clock()
    merge = ScriptMerge()

    def always_hot(owner_id, now):
        merge.commits += 1
        raise FirestoreContentionExhausted('hot')

    merge.commit_next = always_hot
    pump = make_pump(merge, _monotonic=clock)
    pump._defer_drain('owner-1', attempts=2)
    clock.advance(30.0)
    await pump._drain_deferred_due()
    deferred = [line for line in records if 'event=batch_merge_drain outcome=deferred' in line]
    assert len(deferred) == 1
    assert 'attempt=3' in deferred[0]
    assert 'exception_type=FirestoreContentionExhausted' in deferred[0]


async def test_cap_refusal_at_due_logs_the_error_line_with_the_attempt(caplog):
    records = capture_records(caplog)
    clock = Clock()
    merge = ScriptMerge()

    def always_hot(owner_id, now):
        merge.commits += 1
        raise FirestoreContentionExhausted('hot')

    merge.commit_next = always_hot
    pump = make_pump(merge, _monotonic=clock)
    pump._defer_drain('owner-1', attempts=DRAIN_RETRY_MAX_ATTEMPTS - 1)
    clock.advance(30.0)
    await pump._drain_deferred_due()
    retry = [line for line in records if 'event=batch_merge outcome=retry' in line]
    assert len(retry) == 1
    assert f'attempt={DRAIN_RETRY_MAX_ATTEMPTS}' in retry[0]


# ---------------------------------------------------------------------------
# Pump.run teardown
# ---------------------------------------------------------------------------


async def test_run_teardown_flushes_armed_owners():
    clock = Clock()
    merge = ScriptMerge([FirestoreContentionExhausted('hot'), None])
    pump = make_pump(merge, _monotonic=clock)
    stop = asyncio.Event()
    await pump._drain_after_publication('owner-1')
    assert pump._deferred_drains

    async def stop_soon():
        await asyncio.sleep(0.01)
        stop.set()

    asyncio.create_task(stop_soon())
    await asyncio.wait_for(pump.run(stop), timeout=5.0)
    assert pump._deferred_drains == {}
    assert merge.commits == 2


async def test_run_teardown_survives_a_failing_flush_drain():
    clock = Clock()
    merge = ScriptMerge()

    def always_hot(owner_id, now):
        merge.commits += 1
        raise FirestoreContentionExhausted('hot')

    merge.commit_next = always_hot
    pump = make_pump(merge, _monotonic=clock)
    stop = asyncio.Event()
    pump._defer_drain('owner-1')
    asyncio.create_task(_stop_soon(stop))
    await asyncio.wait_for(pump.run(stop), timeout=5.0)  # must not raise
    assert pump._deferred_drains == {}


async def _stop_soon(stop, delay=0.01):
    await asyncio.sleep(delay)
    stop.set()


async def test_run_teardown_stops_the_lane():
    clock = Clock()
    pump = make_pump(ScriptMerge(), _monotonic=clock)
    stop = asyncio.Event()
    pump._defer_drain('a')
    asyncio.create_task(_stop_soon(stop))
    await asyncio.wait_for(pump.run(stop), timeout=5.0)
    assert pump._deferred_lane is None


# ---------------------------------------------------------------------------
# Publication-flight integration
# ---------------------------------------------------------------------------


def lease_of(segment='seg-1', owner='owner-1'):
    from utils.batch_pipeline.contracts import LeasedWork, Priority, WorkItem

    item = WorkItem(
        segment_id=segment,
        owner_id=owner,
        capture_at=1000.0,
        audio_uri='gs://bucket/audio/seg-1',
        duration_seconds=12.0,
        priority=Priority.RECENT,
    )
    return LeasedWork(item=item, token='tok', attempt=1, lease_until=1999.0)


async def test_flight_with_a_failing_drain_arms_only_that_owner():
    from utils.batch_pipeline.contracts import WorkResult

    clock = Clock()
    merge = ScriptMerge()

    def always_hot(owner_id, now):
        merge.commits += 1
        raise FirestoreContentionExhausted('hot')

    merge.commit_next = always_hot
    pump = make_pump(merge, publish_concurrency=4, _monotonic=clock)
    pump.scheduler.complete = lambda result, token, now: True
    leases = [lease_of('seg-a', 'owner-a'), lease_of('seg-b', 'owner-b')]
    result_map = {'seg-a': WorkResult('seg-a', 'gs://a'), 'seg-b': WorkResult('seg-b', 'gs://b')}
    await pump._publish_flight(leases, result_map, set())
    assert sorted(pump._deferred_drains) == ['owner-a', 'owner-b']
    await pump.flush_deferred_drains()


async def test_flight_with_a_partial_drain_failure_arms_only_the_loser():
    from utils.batch_pipeline.contracts import WorkResult

    clock = Clock()
    merge = ScriptMerge()
    losers = {'owner-b'}

    def commit_next(owner_id, now):
        merge.drained.append(owner_id)
        if owner_id in losers:
            raise FirestoreContentionExhausted('hot')
        return None

    merge.commit_next = commit_next
    pump = make_pump(merge, publish_concurrency=4, _monotonic=clock)
    pump.scheduler.complete = lambda result, token, now: True
    leases = [lease_of('seg-a', 'owner-a'), lease_of('seg-b', 'owner-b')]
    result_map = {'seg-a': WorkResult('seg-a', 'gs://a'), 'seg-b': WorkResult('seg-b', 'gs://b')}
    await pump._publish_flight(leases, result_map, set())
    assert sorted(pump._deferred_drains) == ['owner-b']
    await pump.flush_deferred_drains()


async def test_flight_with_a_healthy_drain_arms_nothing():
    from utils.batch_pipeline.contracts import WorkResult

    clock = Clock()
    pump = make_pump(ScriptMerge(), publish_concurrency=4, _monotonic=clock)
    pump.scheduler.complete = lambda result, token, now: True
    leases = [lease_of('seg-a', 'owner-a'), lease_of('seg-b', 'owner-b')]
    result_map = {'seg-a': WorkResult('seg-a', 'gs://a'), 'seg-b': WorkResult('seg-b', 'gs://b')}
    await pump._publish_flight(leases, result_map, set())
    assert pump._deferred_drains == {}
    assert pump._deferred_lane is None


async def test_serial_flight_arms_the_owner_when_its_drain_fails():
    from utils.batch_pipeline.contracts import WorkResult

    clock = Clock()
    merge = ScriptMerge()

    def always_hot(owner_id, now):
        merge.commits += 1
        raise FirestoreContentionExhausted('hot')

    merge.commit_next = always_hot
    pump = make_pump(merge, publish_concurrency=1, _monotonic=clock)
    pump.scheduler.complete = lambda result, token, now: True
    await pump._publish_flight([lease_of('seg-a')], {'seg-a': WorkResult('seg-a', 'gs://a')}, set())
    assert pump._deferred_drains['owner-1']['attempts'] == 1
    await pump.flush_deferred_drains()


async def test_all_lost_flight_arms_nothing():
    from utils.batch_pipeline.contracts import WorkResult

    clock = Clock()
    pump = make_pump(ScriptMerge(), publish_concurrency=4, _monotonic=clock)
    pump.scheduler.complete = lambda result, token, now: (_ for _ in ()).throw(FirestoreContentionExhausted('x'))
    await pump._publish_flight([lease_of('seg-a')], {'seg-a': WorkResult('seg-a', 'gs://a')}, set())
    assert pump._deferred_drains == {}
