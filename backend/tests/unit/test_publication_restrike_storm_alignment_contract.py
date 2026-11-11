"""Storm alignment contract for the publication re-strike lane.

The exhausted publication chain arrives carrying the window the store's
storm damper armed for the label (``error.retry_after``, stamped by
``FirestoreStore.run``). The lane used to discard it and re-strike on the
bare ladder, firing into the window's interior: the entry consult then
parks the publication's db-executor thread on a blocking sleep for the
residual, and a chain that still loses re-arms the storm the lane just
re-entered. The contract here pins the landed shape: every attempt waits
``max(ladder step, min(measured window, storm cap))``, the storm shifts
WHEN the replay lands and never the attempt budget, a mid-lane
re-exhaustion re-aims the next wait at the freshly armed window, and every
hostile payload keeps the documented ladder byte-for-byte.

Failure-Class: FC-publication-restrike-collides-inside-the-armed-storm-window
"""

import logging
import math
import types

import pytest
from google.api_core.exceptions import Aborted

import utils.batch_pipeline.pump as pump_module
from config.batch_pipeline import Priority
from database.firestore_transaction_retry import (
    FirestoreContentionExhausted,
    run_with_transaction_contention_retry,
)
from database.jobstore.postgres_store import JobStoreContentionExhausted
from utils.batch_pipeline.contracts import LeasedWork, WorkItem, WorkResult
from utils.batch_pipeline.pump import (
    PUBLICATION_RESTRIKE_MAX_ATTEMPTS,
    PUBLICATION_RESTRIKE_STORM_MAX_SECONDS,
    Pump,
    contention_retry_after,
    publication_restrike_storm_after,
)

FC = 'FC-publication-restrike-collides-inside-the-armed-storm-window'
PUMP_LOGGER = 'utils.batch_pipeline.pump'


# ---------------------------------------------------------------------------
# Harness (restated from test_publication_restrike_lane.py so this file
# runs isolated)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def inline_blocking(monkeypatch):
    async def passthrough(executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(pump_module, 'run_blocking', passthrough)


class SleepRecorder:
    """Async stand-in for ``asyncio.sleep`` recording every requested delay."""

    def __init__(self):
        self.delays = []

    async def __call__(self, delay, *args, **kwargs):
        self.delays.append(round(delay, 6))


def make_lease(segment='seg-1', token='tok-1', owner='owner-1'):
    item = WorkItem(
        segment_id=segment,
        owner_id=owner,
        capture_at=1.0,
        audio_uri='gs://bucket/seg',
        duration_seconds=3.0,
        priority=Priority.FRESH,
    )
    return LeasedWork(item=item, token=token, attempt=1, lease_until=200.0)


class ScriptScheduler:
    """Fake scheduler scripting every publication transition surface."""

    def __init__(self, complete=()):
        self.calls = []
        self.complete_script = list(complete)

    def complete(self, result, token, now):
        self.calls.append(('complete', result.segment_id, token))
        step = self.complete_script.pop(0)
        if callable(step) and not isinstance(step, BaseException):
            return step()
        if isinstance(step, BaseException):
            raise step
        return step


def make_pump(scheduler=None):
    pump = Pump(
        types.SimpleNamespace(),
        types.SimpleNamespace(),
        merge=types.SimpleNamespace(),
        publish_concurrency=1,
    )
    pump.scheduler = scheduler or ScriptScheduler()
    sleeps = SleepRecorder()
    pump._publication_sleep = sleeps
    pump.sleeps = sleeps
    return pump


def stamped(w, tag='synthetic_publication'):
    """A contention exhaustion carrying the damper's stamped window."""
    try:
        raise Aborted(f'{tag} commit race')
    except Aborted as cause:
        error = FirestoreContentionExhausted(f'Firestore transaction contention exhausted for {tag}')
        error.__cause__ = cause
        error.retry_after = w
        return error


def bare_loss(tag='synthetic_publication'):
    """A contention exhaustion with no stamped window (foreign store / flag off)."""
    error = FirestoreContentionExhausted(f'Firestore transaction contention exhausted for {tag}')
    try:
        raise Aborted(f'{tag} commit race')
    except Aborted as cause:
        error.__cause__ = cause
    return error


def chain_exhaustion(operation_name='synthetic_publication'):
    """Raise a real exhaustion from the production retry chain (no stamp)."""

    def operation(tx):
        raise Aborted(f'{operation_name} commit contention')

    run_with_transaction_contention_retry(
        lambda: object(), operation, operation_name=operation_name, max_attempts=1, sleep=lambda seconds: None
    )


def events(caplog, token):
    return [r.getMessage() for r in caplog.records if token in r.getMessage()]


def error_lines(caplog):
    return [r for r in caplog.records if 'event=batch_completion outcome=retry' in r.getMessage()]


async def run_lane(monkeypatch, caplog, script):
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: True)
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=script)
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    return pump, scheduler, lost, accepted


# ---------------------------------------------------------------------------
# The measured window reshapes the wait, never the budget
# ---------------------------------------------------------------------------


async def test_window_deeper_than_the_ladder_step_moves_the_first_wait(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await run_lane(monkeypatch, caplog, [stamped(1.5), True])
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [1.5]


async def test_the_damper_cap_window_is_landed_after_in_full(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await run_lane(monkeypatch, caplog, [stamped(4.0), True])
    assert accepted is True
    assert pump.sleeps.delays == [4.0]


async def test_a_window_beyond_the_storm_cap_clamps_to_the_cap(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await run_lane(monkeypatch, caplog, [stamped(100.0), True])
    assert accepted is True
    assert pump.sleeps.delays == [4.0]


async def test_window_shallower_than_the_step_never_shortens_the_ladder(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await run_lane(monkeypatch, caplog, [stamped(0.05), True])
    assert accepted is True
    assert pump.sleeps.delays == [0.25]


async def test_window_equal_to_the_step_keeps_the_ladder_answer(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await run_lane(monkeypatch, caplog, [stamped(0.25), True])
    assert accepted is True
    assert pump.sleeps.delays == [0.25]


async def test_integer_windows_are_measured_like_floats(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await run_lane(monkeypatch, caplog, [stamped(2), True])
    assert accepted is True
    assert pump.sleeps.delays == [2.0]


async def test_no_stamped_window_keeps_the_documented_ladder(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await run_lane(monkeypatch, caplog, [bare_loss(), True])
    assert accepted is True
    assert pump.sleeps.delays == [0.25]


async def test_production_chain_exhaustion_without_a_stamp_keeps_the_ladder(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await run_lane(monkeypatch, caplog, [chain_exhaustion, True])
    assert accepted is True
    assert pump.sleeps.delays == [0.25]


async def test_postgres_job_store_window_is_measured(monkeypatch, caplog):
    try:
        raise Aborted('job store race')
    except Aborted as cause:
        error = JobStoreContentionExhausted('job store transaction kept conflicting')
        error.__cause__ = cause
        error.retry_after = 1.0
    pump, scheduler, lost, accepted = await run_lane(monkeypatch, caplog, [error, True])
    assert accepted is True
    assert pump.sleeps.delays == [1.0]


async def test_postgres_exhaustion_without_a_stamp_keeps_the_ladder(monkeypatch, caplog):
    try:
        raise Aborted('job store race')
    except Aborted as cause:
        error = JobStoreContentionExhausted('job store transaction kept conflicting')
        error.__cause__ = cause
    pump, scheduler, lost, accepted = await run_lane(monkeypatch, caplog, [error, True])
    assert accepted is True
    assert pump.sleeps.delays == [0.25]


async def test_second_attempt_re_aims_at_the_freshly_armed_window(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await run_lane(monkeypatch, caplog, [stamped(4.0), stamped(2.0), True])
    assert accepted is True
    assert pump.sleeps.delays == [4.0, 2.0]


async def test_third_attempt_re_aims_and_the_ladder_step_can_win(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await run_lane(
        monkeypatch, caplog, [stamped(0.1), stamped(0.1), stamped(0.1), True]
    )
    # Three shallow windows: the ladder step wins on every attempt and the
    # lane lands on the third, budget unchanged.
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(error_lines(caplog)) == 0


async def test_mid_lane_re_exhaustion_re_aims_each_remaining_wait(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await run_lane(monkeypatch, caplog, [stamped(3.0), stamped(8.0), True])
    assert accepted is True
    assert pump.sleeps.delays == [3.0, 4.0]


async def test_a_stampless_second_loss_falls_back_to_the_ladder_step(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await run_lane(monkeypatch, caplog, [stamped(4.0), bare_loss(), True])
    assert accepted is True
    assert pump.sleeps.delays == [4.0, 0.5]


async def test_a_deep_window_never_buys_a_fourth_attempt(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await run_lane(
        monkeypatch, caplog, [stamped(4.0), stamped(4.0), stamped(4.0), stamped(4.0)]
    )
    # Entry loss + three re-strikes, every one stamped a deep window: the
    # storm never extends the budget and the legacy catch site owns the loss.
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_non_contention_loss_aborts_before_any_wait_even_when_stamped(monkeypatch, caplog):
    error = ValueError('admission refusal')
    error.retry_after = 1.0
    pump, scheduler, lost, accepted = await run_lane(monkeypatch, caplog, [error])
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == []
    assert error_lines(caplog)[0].getMessage() == 'event=batch_completion outcome=retry exception_type=ValueError'


async def test_foreign_error_on_the_second_attempt_ends_the_lane(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await run_lane(monkeypatch, caplog, [stamped(4.0), ValueError('revoked lease')])
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0]
    assert error_lines(caplog)[0].getMessage() == 'event=batch_completion outcome=retry exception_type=ValueError'


async def test_dead_lease_on_the_landed_restrike_is_the_durable_answer(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await run_lane(monkeypatch, caplog, [stamped(4.0), False])
    assert accepted is False
    assert lost == set()  # settled: the fence answered, no lost marker
    assert pump.sleeps.delays == [4.0]


async def test_flag_off_keeps_the_immediate_fallback_even_with_a_stamp(monkeypatch, caplog):
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[stamped(4.0)])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == []
    assert len(error_lines(caplog)) == 1


# ---------------------------------------------------------------------------
# Telemetry reflects the aligned wait
# ---------------------------------------------------------------------------


async def test_restrike_wait_line_carries_the_aligned_delay(monkeypatch, caplog):
    await run_lane(monkeypatch, caplog, [stamped(1.5), True])
    waits = events(caplog, 'event=batch_publication outcome=restrike_wait')
    assert waits == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=1500 '
        'exception_type=FirestoreContentionExhausted'
    ]


async def test_landed_lane_reports_committed_after_a_storm_wait(monkeypatch, caplog):
    await run_lane(monkeypatch, caplog, [stamped(4.0), True])
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=1 accepted=true'
    ]


# ---------------------------------------------------------------------------
# Helper contract: extraction, cap, and the untouched drain clamp
# ---------------------------------------------------------------------------


def test_storm_cap_is_the_store_damper_window_cap_as_a_float():
    assert PUBLICATION_RESTRIKE_STORM_MAX_SECONDS == 4.0
    assert isinstance(PUBLICATION_RESTRIKE_STORM_MAX_SECONDS, float)


def test_attempt_budget_is_unchanged_by_the_storm_term():
    assert PUBLICATION_RESTRIKE_MAX_ATTEMPTS == 3


@pytest.mark.parametrize(
    'payload,expected',
    [
        (None, 0.0),
        (True, 0.0),
        (False, 0.0),
        ('2', 0.0),
        (object(), 0.0),
        ([2.0], 0.0),
        (0.0, 0.0),
        (-1.0, 0.0),
        (float('nan'), 0.0),
        (float('inf'), 0.0),
        (float('-inf'), 0.0),
        (0.05, 0.05),
        (0.25, 0.25),
        (2, 2.0),
        (3.999, 3.999),
        (4.0, 4.0),
        (4.0001, 4.0),
        (100.0, 4.0),
    ],
)
def test_publication_restrike_storm_after_extraction_matrix(payload, expected):
    error = FirestoreContentionExhausted('exhausted')
    if payload is not None:
        error.retry_after = payload
    assert publication_restrike_storm_after(error) == expected


def test_publication_restrike_storm_after_reads_a_missing_attribute_as_no_window():
    assert publication_restrike_storm_after(bare_loss()) == 0.0


def test_publication_restrike_storm_after_on_none_never_raises():
    assert publication_restrike_storm_after(None) == 0.0


@pytest.mark.parametrize(
    'payload,expected',
    [
        (100.0, 8.0),
        (4.0, 4.0),
        (7.9, 7.9),
        ('8', 0.0),
        (True, 0.0),
        (-4.0, 0.0),
    ],
)
def test_contention_retry_after_drain_clamp_is_unchanged_by_the_refactor(payload, expected):
    error = FirestoreContentionExhausted('exhausted')
    error.retry_after = payload
    assert contention_retry_after(error) == expected


def test_contention_retry_after_still_clamps_at_the_drain_lane_max():
    error = FirestoreContentionExhausted('exhausted')
    error.retry_after = 100.0
    assert contention_retry_after(error) == 8.0 == pump_module.DRAIN_RETRY_MAX_SECONDS


def test_fc_token_is_declared_in_the_lane_doc():
    import os

    doc = open(os.path.join(os.path.dirname(__file__), '..', '..', 'docs', 'publication-restrike-lane.md')).read()
    assert FC in doc
    assert 'max(ladder step, min(measured window, storm cap))' in doc


def test_fc_token_is_declared_in_the_pump_module():
    import inspect

    assert FC in inspect.getsource(pump_module)
