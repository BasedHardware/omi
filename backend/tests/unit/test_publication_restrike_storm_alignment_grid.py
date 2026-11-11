"""Publication re-strike storm alignment grid (the batch_completion loss family)

Every re-strike attempt of the publication lane lands at

    wait = max(documented ladder step, min(measured storm window, storm cap))

with the storm cap at 4.0s and the ladder at 0.25s / 0.5s / 1.0s. This grid
walks the input lattice (payload class x landing plan) plus the fresh-window
re-aim lattice (entry window x first re-strike window x second re-strike
window), and pins each combination's exact wait sequence, terminal outcome,
store-call count and terminal ERROR line as literals on the real
``Pump._publish`` lane with recorded sleeps. The extraction matrices pin the
shared classifier and the untouched drain clamp per payload class.

The harness is restated from ``tests/unit/test_publication_restrike_lane.py``
so this file runs isolated.

Failure-Class: FC-publication-restrike-collides-inside-the-armed-storm-window
"""

import logging
import math
import types

import pytest
from google.api_core.exceptions import Aborted

import utils.batch_pipeline.pump as pump_module
from config.batch_pipeline import Priority
from database.firestore_transaction_retry import FirestoreContentionExhausted
from utils.batch_pipeline.contracts import (
    FailedWork,
    LeasedWork,
    RecoveryWork,
    ValidationFailureWork,
    WorkItem,
    WorkResult,
)
from utils.batch_pipeline.pump import (
    Pump,
    contention_retry_after,
    publication_restrike_delay,
    publication_restrike_storm_after,
)

FC = 'FC-publication-restrike-collides-inside-the-armed-storm-window'
PUMP_LOGGER = 'utils.batch_pipeline.pump'


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
    """Fake scheduler scripting the complete and fail transition surfaces."""

    def __init__(self, complete=(), fail=()):
        self.calls = []
        self.complete_script = list(complete)
        self.fail_script = list(fail)

    def _pop(self, script, name, *payload):
        self.calls.append((name, *payload))
        step = script.pop(0)
        if callable(step) and not isinstance(step, BaseException):
            return step()
        if isinstance(step, BaseException):
            raise step
        return step

    def complete(self, result, token, now):
        return self._pop(self.complete_script, 'complete', result.segment_id, token)

    def fail(self, segment_id, token, now, **kwargs):
        return self._pop(self.fail_script, 'fail', segment_id, token, kwargs)


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


class _ABSENT:
    """Marker for a chain that carries no ``retry_after`` stamp."""

    pass


def _E(w=_ABSENT):
    """A contention exhaustion carrying (or missing) the stamped window."""
    try:
        raise Aborted('synthetic_publication commit race')
    except Aborted as cause:
        error = FirestoreContentionExhausted('Firestore transaction contention exhausted for synthetic_publication')
        error.__cause__ = cause
        if w is not _ABSENT:
            error.retry_after = w
        return error


async def _run(monkeypatch, caplog, *script):
    async def passthrough(executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(pump_module, 'run_blocking', passthrough)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: True)
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=list(script))
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    return pump, scheduler, lost, accepted


def error_lines(caplog):
    return [r for r in caplog.records if 'event=batch_completion outcome=retry' in r.getMessage()]


async def _run_fail(monkeypatch, caplog, result, *script):
    async def passthrough(executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(pump_module, 'run_blocking', passthrough)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: True)
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=list(script))
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {result.segment_id: result}, lost)
    return pump, scheduler, lost, accepted


# ---------------------------------------------------------------------------
# Payload x landing plan: the real lane pins each cell exactly
# ---------------------------------------------------------------------------


async def test_lane_payload_absent_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_absent_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_absent_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(), _E(), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_absent_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_absent_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [0.25]
    assert len(scheduler.calls) == 2


async def test_lane_payload_absent_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_none_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(None), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_none_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(None), _E(None), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_none_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(None), _E(None), _E(None), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_none_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(None), _E(None), _E(None), _E(None))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_none_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(None), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [0.25]
    assert len(scheduler.calls) == 2


async def test_lane_payload_none_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(None), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_true_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(True), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_true_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(True), _E(True), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_true_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(True), _E(True), _E(True), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_true_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(True), _E(True), _E(True), _E(True))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_true_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(True), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [0.25]
    assert len(scheduler.calls) == 2


async def test_lane_payload_true_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(True), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_false_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(False), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_false_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(False), _E(False), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_false_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(False), _E(False), _E(False), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_false_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(False), _E(False), _E(False), _E(False))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_false_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(False), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [0.25]
    assert len(scheduler.calls) == 2


async def test_lane_payload_false_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(False), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_s2_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E('2'), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_s2_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E('2'), _E('2'), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_s2_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E('2'), _E('2'), _E('2'), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_s2_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E('2'), _E('2'), _E('2'), _E('2'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_s2_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E('2'), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [0.25]
    assert len(scheduler.calls) == 2


async def test_lane_payload_s2_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E('2'), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_list_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E([2.0]), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_list_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E([2.0]), _E([2.0]), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_list_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E([2.0]), _E([2.0]), _E([2.0]), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_list_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E([2.0]), _E([2.0]), _E([2.0]), _E([2.0]))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_list_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E([2.0]), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [0.25]
    assert len(scheduler.calls) == 2


async def test_lane_payload_list_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E([2.0]), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_nan_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(float('nan')), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_nan_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(float('nan')), _E(float('nan')), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_nan_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(
        monkeypatch, caplog, _E(float('nan')), _E(float('nan')), _E(float('nan')), True
    )
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_nan_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(
        monkeypatch, caplog, _E(float('nan')), _E(float('nan')), _E(float('nan')), _E(float('nan'))
    )
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_nan_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(float('nan')), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [0.25]
    assert len(scheduler.calls) == 2


async def test_lane_payload_nan_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(float('nan')), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_inf_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(float('inf')), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_inf_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(float('inf')), _E(float('inf')), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_inf_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(
        monkeypatch, caplog, _E(float('inf')), _E(float('inf')), _E(float('inf')), True
    )
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_inf_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(
        monkeypatch, caplog, _E(float('inf')), _E(float('inf')), _E(float('inf')), _E(float('inf'))
    )
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_inf_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(float('inf')), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [0.25]
    assert len(scheduler.calls) == 2


async def test_lane_payload_inf_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(float('inf')), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_neginf_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(float('-inf')), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_neginf_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(float('-inf')), _E(float('-inf')), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_neginf_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(
        monkeypatch, caplog, _E(float('-inf')), _E(float('-inf')), _E(float('-inf')), True
    )
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_neginf_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(
        monkeypatch, caplog, _E(float('-inf')), _E(float('-inf')), _E(float('-inf')), _E(float('-inf'))
    )
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_neginf_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(float('-inf')), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [0.25]
    assert len(scheduler.calls) == 2


async def test_lane_payload_neginf_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(float('-inf')), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_neg1_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(-1.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_neg1_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(-1.0), _E(-1.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_neg1_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(-1.0), _E(-1.0), _E(-1.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_neg1_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(-1.0), _E(-1.0), _E(-1.0), _E(-1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_neg1_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(-1.0), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [0.25]
    assert len(scheduler.calls) == 2


async def test_lane_payload_neg1_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(-1.0), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_0_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_0_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.0), _E(0.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_0_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.0), _E(0.0), _E(0.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_0_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.0), _E(0.0), _E(0.0), _E(0.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_0_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.0), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [0.25]
    assert len(scheduler.calls) == 2


async def test_lane_payload_0_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.0), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_i0_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_i0_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0), _E(0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_i0_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0), _E(0), _E(0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_i0_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0), _E(0), _E(0), _E(0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_i0_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [0.25]
    assert len(scheduler.calls) == 2


async def test_lane_payload_i0_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_i2_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [2.0]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_i2_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2), _E(2), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [2.0, 2.0]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_i2_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2), _E(2), _E(2), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [2.0, 2.0, 2.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_i2_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2), _E(2), _E(2), _E(2))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 2.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_i2_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [2.0]
    assert len(scheduler.calls) == 2


async def test_lane_payload_i2_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_i4_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_i4_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4), _E(4), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0, 4.0]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_i4_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4), _E(4), _E(4), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_i4_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4), _E(4), _E(4), _E(4))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_i4_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [4.0]
    assert len(scheduler.calls) == 2


async def test_lane_payload_i4_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_i100_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_i100_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100), _E(100), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0, 4.0]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_i100_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100), _E(100), _E(100), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_i100_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100), _E(100), _E(100), _E(100))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_i100_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [4.0]
    assert len(scheduler.calls) == 2


async def test_lane_payload_i100_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_0p05_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.05), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_0p05_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.05), _E(0.05), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_0p05_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.05), _E(0.05), _E(0.05), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_0p05_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.05), _E(0.05), _E(0.05), _E(0.05))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_0p05_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.05), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [0.25]
    assert len(scheduler.calls) == 2


async def test_lane_payload_0p05_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.05), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_0p2499_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.2499), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_0p2499_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.2499), _E(0.2499), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_0p2499_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.2499), _E(0.2499), _E(0.2499), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_0p2499_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.2499), _E(0.2499), _E(0.2499), _E(0.2499))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_0p2499_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.2499), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [0.25]
    assert len(scheduler.calls) == 2


async def test_lane_payload_0p2499_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.2499), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_0p25_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_0p25_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.25), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_0p25_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.25), _E(0.25), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_0p25_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.25), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_0p25_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [0.25]
    assert len(scheduler.calls) == 2


async def test_lane_payload_0p25_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_0p2501_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.2501), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.2501]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_0p2501_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.2501), _E(0.2501), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.2501, 0.5]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_0p2501_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.2501), _E(0.2501), _E(0.2501), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.2501, 0.5, 1.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_0p2501_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.2501), _E(0.2501), _E(0.2501), _E(0.2501))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.2501, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_0p2501_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.2501), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [0.2501]
    assert len(scheduler.calls) == 2


async def test_lane_payload_0p2501_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.2501), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.2501]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_0p3_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.3), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.3]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_0p3_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.3), _E(0.3), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.3, 0.5]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_0p3_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.3), _E(0.3), _E(0.3), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.3, 0.5, 1.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_0p3_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.3), _E(0.3), _E(0.3), _E(0.3))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.3, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_0p3_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.3), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [0.3]
    assert len(scheduler.calls) == 2


async def test_lane_payload_0p3_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.3), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.3]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_0p5_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.5]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_0p5_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.5), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.5, 0.5]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_0p5_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.5), _E(0.5), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.5, 0.5, 1.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_0p5_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.5), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_0p5_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [0.5]
    assert len(scheduler.calls) == 2


async def test_lane_payload_0p5_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_0p75_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.75), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.75]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_0p75_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.75), _E(0.75), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.75, 0.75]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_0p75_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.75), _E(0.75), _E(0.75), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.75, 0.75, 1.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_0p75_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.75), _E(0.75), _E(0.75), _E(0.75))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.75, 0.75, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_0p75_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.75), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [0.75]
    assert len(scheduler.calls) == 2


async def test_lane_payload_0p75_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.75), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.75]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_1_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [1.0]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_1_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(1.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [1.0, 1.0]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_1_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(1.0), _E(1.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [1.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_1_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(1.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_1_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [1.0]
    assert len(scheduler.calls) == 2


async def test_lane_payload_1_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_1p25_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.25), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [1.25]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_1p25_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.25), _E(1.25), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [1.25, 1.25]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_1p25_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.25), _E(1.25), _E(1.25), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [1.25, 1.25, 1.25]
    assert len(scheduler.calls) == 4


async def test_lane_payload_1p25_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.25), _E(1.25), _E(1.25), _E(1.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.25, 1.25, 1.25]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_1p25_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.25), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [1.25]
    assert len(scheduler.calls) == 2


async def test_lane_payload_1p25_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.25), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.25]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_1p999_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.999), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [1.999]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_1p999_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.999), _E(1.999), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [1.999, 1.999]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_1p999_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.999), _E(1.999), _E(1.999), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [1.999, 1.999, 1.999]
    assert len(scheduler.calls) == 4


async def test_lane_payload_1p999_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.999), _E(1.999), _E(1.999), _E(1.999))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.999, 1.999, 1.999]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_1p999_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.999), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [1.999]
    assert len(scheduler.calls) == 2


async def test_lane_payload_1p999_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.999), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.999]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_2_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [2.0]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_2_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(2.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [2.0, 2.0]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_2_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(2.0), _E(2.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [2.0, 2.0, 2.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_2_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(2.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 2.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_2_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [2.0]
    assert len(scheduler.calls) == 2


async def test_lane_payload_2_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_2p0001_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0001), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [2.0001]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_2p0001_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0001), _E(2.0001), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [2.0001, 2.0001]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_2p0001_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0001), _E(2.0001), _E(2.0001), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [2.0001, 2.0001, 2.0001]
    assert len(scheduler.calls) == 4


async def test_lane_payload_2p0001_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0001), _E(2.0001), _E(2.0001), _E(2.0001))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0001, 2.0001, 2.0001]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_2p0001_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0001), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [2.0001]
    assert len(scheduler.calls) == 2


async def test_lane_payload_2p0001_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0001), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0001]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_2p5_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.5), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [2.5]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_2p5_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.5), _E(2.5), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [2.5, 2.5]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_2p5_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.5), _E(2.5), _E(2.5), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [2.5, 2.5, 2.5]
    assert len(scheduler.calls) == 4


async def test_lane_payload_2p5_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.5), _E(2.5), _E(2.5), _E(2.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.5, 2.5, 2.5]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_2p5_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.5), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [2.5]
    assert len(scheduler.calls) == 2


async def test_lane_payload_2p5_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.5), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.5]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_3_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(3.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [3.0]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_3_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(3.0), _E(3.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [3.0, 3.0]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_3_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(3.0), _E(3.0), _E(3.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [3.0, 3.0, 3.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_3_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(3.0), _E(3.0), _E(3.0), _E(3.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [3.0, 3.0, 3.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_3_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(3.0), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [3.0]
    assert len(scheduler.calls) == 2


async def test_lane_payload_3_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(3.0), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [3.0]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_3p5_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(3.5), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [3.5]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_3p5_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(3.5), _E(3.5), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [3.5, 3.5]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_3p5_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(3.5), _E(3.5), _E(3.5), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [3.5, 3.5, 3.5]
    assert len(scheduler.calls) == 4


async def test_lane_payload_3p5_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(3.5), _E(3.5), _E(3.5), _E(3.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [3.5, 3.5, 3.5]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_3p5_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(3.5), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [3.5]
    assert len(scheduler.calls) == 2


async def test_lane_payload_3p5_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(3.5), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [3.5]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_3p999_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(3.999), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [3.999]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_3p999_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(3.999), _E(3.999), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [3.999, 3.999]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_3p999_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(3.999), _E(3.999), _E(3.999), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [3.999, 3.999, 3.999]
    assert len(scheduler.calls) == 4


async def test_lane_payload_3p999_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(3.999), _E(3.999), _E(3.999), _E(3.999))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [3.999, 3.999, 3.999]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_3p999_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(3.999), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [3.999]
    assert len(scheduler.calls) == 2


async def test_lane_payload_3p999_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(3.999), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [3.999]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_4_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_4_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(4.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0, 4.0]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_4_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(4.0), _E(4.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_4_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(4.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_4_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [4.0]
    assert len(scheduler.calls) == 2


async def test_lane_payload_4_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_4p0001_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0001), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_4p0001_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0001), _E(4.0001), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0, 4.0]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_4p0001_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0001), _E(4.0001), _E(4.0001), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_4p0001_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0001), _E(4.0001), _E(4.0001), _E(4.0001))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_4p0001_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0001), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [4.0]
    assert len(scheduler.calls) == 2


async def test_lane_payload_4p0001_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0001), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_7p9_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(7.9), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_7p9_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(7.9), _E(7.9), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0, 4.0]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_7p9_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(7.9), _E(7.9), _E(7.9), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_7p9_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(7.9), _E(7.9), _E(7.9), _E(7.9))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_7p9_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(7.9), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [4.0]
    assert len(scheduler.calls) == 2


async def test_lane_payload_7p9_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(7.9), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_8_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_8_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(8.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0, 4.0]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_8_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(8.0), _E(8.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_8_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(8.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_8_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [4.0]
    assert len(scheduler.calls) == 2


async def test_lane_payload_8_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


async def test_lane_payload_100_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete']


async def test_lane_payload_100_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(100.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0, 4.0]
    assert [c[0] for c in scheduler.calls] == ['complete', 'complete', 'complete']


async def test_lane_payload_100_plan_lands_3(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(100.0), _E(100.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4


async def test_lane_payload_100_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(100.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_lane_payload_100_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [4.0]
    assert len(scheduler.calls) == 2


async def test_lane_payload_100_plan_foreign_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), ValueError('revoked lease'))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0]
    assert error_lines(caplog)[0].getMessage() == ('event=batch_completion outcome=retry exception_type=ValueError')


# ---------------------------------------------------------------------------
# Extraction matrices: the shared classifier and the untouched drain clamp
# ---------------------------------------------------------------------------


def test_storm_after_payload_absent_is_no_window():
    assert publication_restrike_storm_after(_E()) == 0.0


def test_storm_after_payload_none():
    error = _E()
    error.retry_after = None
    assert publication_restrike_storm_after(error) == 0.0


def test_storm_after_payload_true():
    error = _E()
    error.retry_after = True
    assert publication_restrike_storm_after(error) == 0.0


def test_storm_after_payload_false():
    error = _E()
    error.retry_after = False
    assert publication_restrike_storm_after(error) == 0.0


def test_storm_after_payload_s2():
    error = _E()
    error.retry_after = '2'
    assert publication_restrike_storm_after(error) == 0.0


def test_storm_after_payload_list():
    error = _E()
    error.retry_after = [2.0]
    assert publication_restrike_storm_after(error) == 0.0


def test_storm_after_payload_nan():
    error = _E()
    error.retry_after = float('nan')
    assert publication_restrike_storm_after(error) == 0.0


def test_storm_after_payload_inf():
    error = _E()
    error.retry_after = float('inf')
    assert publication_restrike_storm_after(error) == 0.0


def test_storm_after_payload_neginf():
    error = _E()
    error.retry_after = float('-inf')
    assert publication_restrike_storm_after(error) == 0.0


def test_storm_after_payload_neg1():
    error = _E()
    error.retry_after = -1.0
    assert publication_restrike_storm_after(error) == 0.0


def test_storm_after_payload_0():
    error = _E()
    error.retry_after = 0.0
    assert publication_restrike_storm_after(error) == 0.0


def test_storm_after_payload_i0():
    error = _E()
    error.retry_after = 0
    assert publication_restrike_storm_after(error) == 0.0


def test_storm_after_payload_i2():
    error = _E()
    error.retry_after = 2
    assert publication_restrike_storm_after(error) == 2.0


def test_storm_after_payload_i4():
    error = _E()
    error.retry_after = 4
    assert publication_restrike_storm_after(error) == 4.0


def test_storm_after_payload_i100():
    error = _E()
    error.retry_after = 100
    assert publication_restrike_storm_after(error) == 4.0


def test_storm_after_payload_0p05():
    error = _E()
    error.retry_after = 0.05
    assert publication_restrike_storm_after(error) == 0.05


def test_storm_after_payload_0p2499():
    error = _E()
    error.retry_after = 0.2499
    assert publication_restrike_storm_after(error) == 0.2499


def test_storm_after_payload_0p25():
    error = _E()
    error.retry_after = 0.25
    assert publication_restrike_storm_after(error) == 0.25


def test_storm_after_payload_0p2501():
    error = _E()
    error.retry_after = 0.2501
    assert publication_restrike_storm_after(error) == 0.2501


def test_storm_after_payload_0p3():
    error = _E()
    error.retry_after = 0.3
    assert publication_restrike_storm_after(error) == 0.3


def test_storm_after_payload_0p5():
    error = _E()
    error.retry_after = 0.5
    assert publication_restrike_storm_after(error) == 0.5


def test_storm_after_payload_0p75():
    error = _E()
    error.retry_after = 0.75
    assert publication_restrike_storm_after(error) == 0.75


def test_storm_after_payload_1():
    error = _E()
    error.retry_after = 1.0
    assert publication_restrike_storm_after(error) == 1.0


def test_storm_after_payload_1p25():
    error = _E()
    error.retry_after = 1.25
    assert publication_restrike_storm_after(error) == 1.25


def test_storm_after_payload_1p999():
    error = _E()
    error.retry_after = 1.999
    assert publication_restrike_storm_after(error) == 1.999


def test_storm_after_payload_2():
    error = _E()
    error.retry_after = 2.0
    assert publication_restrike_storm_after(error) == 2.0


def test_storm_after_payload_2p0001():
    error = _E()
    error.retry_after = 2.0001
    assert publication_restrike_storm_after(error) == 2.0001


def test_storm_after_payload_2p5():
    error = _E()
    error.retry_after = 2.5
    assert publication_restrike_storm_after(error) == 2.5


def test_storm_after_payload_3():
    error = _E()
    error.retry_after = 3.0
    assert publication_restrike_storm_after(error) == 3.0


def test_storm_after_payload_3p5():
    error = _E()
    error.retry_after = 3.5
    assert publication_restrike_storm_after(error) == 3.5


def test_storm_after_payload_3p999():
    error = _E()
    error.retry_after = 3.999
    assert publication_restrike_storm_after(error) == 3.999


def test_storm_after_payload_4():
    error = _E()
    error.retry_after = 4.0
    assert publication_restrike_storm_after(error) == 4.0


def test_storm_after_payload_4p0001():
    error = _E()
    error.retry_after = 4.0001
    assert publication_restrike_storm_after(error) == 4.0


def test_storm_after_payload_7p9():
    error = _E()
    error.retry_after = 7.9
    assert publication_restrike_storm_after(error) == 4.0


def test_storm_after_payload_8():
    error = _E()
    error.retry_after = 8.0
    assert publication_restrike_storm_after(error) == 4.0


def test_storm_after_payload_100():
    error = _E()
    error.retry_after = 100.0
    assert publication_restrike_storm_after(error) == 4.0


def test_drain_clamp_payload_absent_is_no_window():
    assert contention_retry_after(_E()) == 0.0


def test_drain_clamp_payload_none():
    error = _E()
    error.retry_after = None
    assert contention_retry_after(error) == 0.0


def test_drain_clamp_payload_true():
    error = _E()
    error.retry_after = True
    assert contention_retry_after(error) == 0.0


def test_drain_clamp_payload_false():
    error = _E()
    error.retry_after = False
    assert contention_retry_after(error) == 0.0


def test_drain_clamp_payload_s2():
    error = _E()
    error.retry_after = '2'
    assert contention_retry_after(error) == 0.0


def test_drain_clamp_payload_list():
    error = _E()
    error.retry_after = [2.0]
    assert contention_retry_after(error) == 0.0


def test_drain_clamp_payload_nan():
    error = _E()
    error.retry_after = float('nan')
    assert contention_retry_after(error) == 0.0


def test_drain_clamp_payload_inf():
    error = _E()
    error.retry_after = float('inf')
    assert contention_retry_after(error) == 0.0


def test_drain_clamp_payload_neginf():
    error = _E()
    error.retry_after = float('-inf')
    assert contention_retry_after(error) == 0.0


def test_drain_clamp_payload_neg1():
    error = _E()
    error.retry_after = -1.0
    assert contention_retry_after(error) == 0.0


def test_drain_clamp_payload_0():
    error = _E()
    error.retry_after = 0.0
    assert contention_retry_after(error) == 0.0


def test_drain_clamp_payload_i0():
    error = _E()
    error.retry_after = 0
    assert contention_retry_after(error) == 0.0


def test_drain_clamp_payload_i2():
    error = _E()
    error.retry_after = 2
    assert contention_retry_after(error) == 2.0


def test_drain_clamp_payload_i4():
    error = _E()
    error.retry_after = 4
    assert contention_retry_after(error) == 4.0


def test_drain_clamp_payload_i100():
    error = _E()
    error.retry_after = 100
    assert contention_retry_after(error) == 8.0


def test_drain_clamp_payload_0p05():
    error = _E()
    error.retry_after = 0.05
    assert contention_retry_after(error) == 0.05


def test_drain_clamp_payload_0p2499():
    error = _E()
    error.retry_after = 0.2499
    assert contention_retry_after(error) == 0.2499


def test_drain_clamp_payload_0p25():
    error = _E()
    error.retry_after = 0.25
    assert contention_retry_after(error) == 0.25


def test_drain_clamp_payload_0p2501():
    error = _E()
    error.retry_after = 0.2501
    assert contention_retry_after(error) == 0.2501


def test_drain_clamp_payload_0p3():
    error = _E()
    error.retry_after = 0.3
    assert contention_retry_after(error) == 0.3


def test_drain_clamp_payload_0p5():
    error = _E()
    error.retry_after = 0.5
    assert contention_retry_after(error) == 0.5


def test_drain_clamp_payload_0p75():
    error = _E()
    error.retry_after = 0.75
    assert contention_retry_after(error) == 0.75


def test_drain_clamp_payload_1():
    error = _E()
    error.retry_after = 1.0
    assert contention_retry_after(error) == 1.0


def test_drain_clamp_payload_1p25():
    error = _E()
    error.retry_after = 1.25
    assert contention_retry_after(error) == 1.25


def test_drain_clamp_payload_1p999():
    error = _E()
    error.retry_after = 1.999
    assert contention_retry_after(error) == 1.999


def test_drain_clamp_payload_2():
    error = _E()
    error.retry_after = 2.0
    assert contention_retry_after(error) == 2.0


def test_drain_clamp_payload_2p0001():
    error = _E()
    error.retry_after = 2.0001
    assert contention_retry_after(error) == 2.0001


def test_drain_clamp_payload_2p5():
    error = _E()
    error.retry_after = 2.5
    assert contention_retry_after(error) == 2.5


def test_drain_clamp_payload_3():
    error = _E()
    error.retry_after = 3.0
    assert contention_retry_after(error) == 3.0


def test_drain_clamp_payload_3p5():
    error = _E()
    error.retry_after = 3.5
    assert contention_retry_after(error) == 3.5


def test_drain_clamp_payload_3p999():
    error = _E()
    error.retry_after = 3.999
    assert contention_retry_after(error) == 3.999


def test_drain_clamp_payload_4():
    error = _E()
    error.retry_after = 4.0
    assert contention_retry_after(error) == 4.0


def test_drain_clamp_payload_4p0001():
    error = _E()
    error.retry_after = 4.0001
    assert contention_retry_after(error) == 4.0001


def test_drain_clamp_payload_7p9():
    error = _E()
    error.retry_after = 7.9
    assert contention_retry_after(error) == 7.9


def test_drain_clamp_payload_8():
    error = _E()
    error.retry_after = 8.0
    assert contention_retry_after(error) == 8.0


def test_drain_clamp_payload_100():
    error = _E()
    error.retry_after = 100.0
    assert contention_retry_after(error) == 8.0


def test_ladder_attempt_00_is_unchanged_by_the_storm_term():
    assert publication_restrike_delay(0) == 0.25


def test_ladder_attempt_01_is_unchanged_by_the_storm_term():
    assert publication_restrike_delay(1) == 0.25


def test_ladder_attempt_02_is_unchanged_by_the_storm_term():
    assert publication_restrike_delay(2) == 0.5


def test_ladder_attempt_03_is_unchanged_by_the_storm_term():
    assert publication_restrike_delay(3) == 1.0


def test_ladder_attempt_04_is_unchanged_by_the_storm_term():
    assert publication_restrike_delay(4) == 2.0


def test_ladder_attempt_05_is_unchanged_by_the_storm_term():
    assert publication_restrike_delay(5) == 2.0


def test_ladder_attempt_06_is_unchanged_by_the_storm_term():
    assert publication_restrike_delay(6) == 2.0


def test_ladder_attempt_07_is_unchanged_by_the_storm_term():
    assert publication_restrike_delay(7) == 2.0


def test_ladder_attempt_08_is_unchanged_by_the_storm_term():
    assert publication_restrike_delay(8) == 2.0


def test_ladder_attempt_09_is_unchanged_by_the_storm_term():
    assert publication_restrike_delay(9) == 2.0


def test_ladder_attempt_10_is_unchanged_by_the_storm_term():
    assert publication_restrike_delay(10) == 2.0


def test_ladder_attempt_11_is_unchanged_by_the_storm_term():
    assert publication_restrike_delay(11) == 2.0


def test_ladder_attempt_12_is_unchanged_by_the_storm_term():
    assert publication_restrike_delay(12) == 2.0


# ---------------------------------------------------------------------------
# Fresh-window re-aim lattice: each wait re-aims at the freshest window
# ---------------------------------------------------------------------------


async def test_reaim_absent__absent__absent(monkeypatch, caplog):
    # Entry window absent, re-strike windows absent then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__absent__0p1(monkeypatch, caplog):
    # Entry window absent, re-strike windows absent then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__absent__0p25(monkeypatch, caplog):
    # Entry window absent, re-strike windows absent then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__absent__0p5(monkeypatch, caplog):
    # Entry window absent, re-strike windows absent then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__absent__1(monkeypatch, caplog):
    # Entry window absent, re-strike windows absent then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__absent__2(monkeypatch, caplog):
    # Entry window absent, re-strike windows absent then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__absent__4(monkeypatch, caplog):
    # Entry window absent, re-strike windows absent then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__absent__8(monkeypatch, caplog):
    # Entry window absent, re-strike windows absent then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__absent__100(monkeypatch, caplog):
    # Entry window absent, re-strike windows absent then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p1__absent(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.1 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.1), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p1__0p1(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.1 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.1), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p1__0p25(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.1 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.1), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p1__0p5(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.1 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.1), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p1__1(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.1 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.1), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p1__2(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.1 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.1), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p1__4(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.1 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.1), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p1__8(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.1 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.1), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p1__100(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.1 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.1), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p25__absent(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.25 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.25), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p25__0p1(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.25 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.25), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p25__0p25(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.25 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.25), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p25__0p5(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.25 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.25), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p25__1(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.25 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.25), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p25__2(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.25 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.25), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p25__4(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.25 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.25), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p25__8(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.25 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.25), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p25__100(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.25 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.25), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p5__absent(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.5 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.5), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p5__0p1(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.5 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.5), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p5__0p25(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.5 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.5), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p5__0p5(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.5 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.5), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p5__1(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.5 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.5), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p5__2(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.5 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.5), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p5__4(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.5 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.5), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p5__8(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.5 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.5), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__0p5__100(monkeypatch, caplog):
    # Entry window absent, re-strike windows 0.5 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(0.5), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__1__absent(monkeypatch, caplog):
    # Entry window absent, re-strike windows 1.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(1.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__1__0p1(monkeypatch, caplog):
    # Entry window absent, re-strike windows 1.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(1.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__1__0p25(monkeypatch, caplog):
    # Entry window absent, re-strike windows 1.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(1.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__1__0p5(monkeypatch, caplog):
    # Entry window absent, re-strike windows 1.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(1.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__1__1(monkeypatch, caplog):
    # Entry window absent, re-strike windows 1.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(1.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__1__2(monkeypatch, caplog):
    # Entry window absent, re-strike windows 1.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(1.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__1__4(monkeypatch, caplog):
    # Entry window absent, re-strike windows 1.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(1.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__1__8(monkeypatch, caplog):
    # Entry window absent, re-strike windows 1.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(1.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__1__100(monkeypatch, caplog):
    # Entry window absent, re-strike windows 1.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(1.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__2__absent(monkeypatch, caplog):
    # Entry window absent, re-strike windows 2.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(2.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__2__0p1(monkeypatch, caplog):
    # Entry window absent, re-strike windows 2.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(2.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__2__0p25(monkeypatch, caplog):
    # Entry window absent, re-strike windows 2.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(2.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__2__0p5(monkeypatch, caplog):
    # Entry window absent, re-strike windows 2.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(2.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__2__1(monkeypatch, caplog):
    # Entry window absent, re-strike windows 2.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(2.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__2__2(monkeypatch, caplog):
    # Entry window absent, re-strike windows 2.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(2.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__2__4(monkeypatch, caplog):
    # Entry window absent, re-strike windows 2.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(2.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__2__8(monkeypatch, caplog):
    # Entry window absent, re-strike windows 2.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(2.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__2__100(monkeypatch, caplog):
    # Entry window absent, re-strike windows 2.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(2.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__4__absent(monkeypatch, caplog):
    # Entry window absent, re-strike windows 4.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(4.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__4__0p1(monkeypatch, caplog):
    # Entry window absent, re-strike windows 4.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(4.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__4__0p25(monkeypatch, caplog):
    # Entry window absent, re-strike windows 4.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(4.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__4__0p5(monkeypatch, caplog):
    # Entry window absent, re-strike windows 4.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(4.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__4__1(monkeypatch, caplog):
    # Entry window absent, re-strike windows 4.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(4.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__4__2(monkeypatch, caplog):
    # Entry window absent, re-strike windows 4.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(4.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__4__4(monkeypatch, caplog):
    # Entry window absent, re-strike windows 4.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(4.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__4__8(monkeypatch, caplog):
    # Entry window absent, re-strike windows 4.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(4.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__4__100(monkeypatch, caplog):
    # Entry window absent, re-strike windows 4.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(4.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__8__absent(monkeypatch, caplog):
    # Entry window absent, re-strike windows 8.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(8.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__8__0p1(monkeypatch, caplog):
    # Entry window absent, re-strike windows 8.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(8.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__8__0p25(monkeypatch, caplog):
    # Entry window absent, re-strike windows 8.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(8.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__8__0p5(monkeypatch, caplog):
    # Entry window absent, re-strike windows 8.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(8.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__8__1(monkeypatch, caplog):
    # Entry window absent, re-strike windows 8.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(8.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__8__2(monkeypatch, caplog):
    # Entry window absent, re-strike windows 8.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(8.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__8__4(monkeypatch, caplog):
    # Entry window absent, re-strike windows 8.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(8.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__8__8(monkeypatch, caplog):
    # Entry window absent, re-strike windows 8.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(8.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__8__100(monkeypatch, caplog):
    # Entry window absent, re-strike windows 8.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(8.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__100__absent(monkeypatch, caplog):
    # Entry window absent, re-strike windows 100.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(100.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__100__0p1(monkeypatch, caplog):
    # Entry window absent, re-strike windows 100.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(100.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__100__0p25(monkeypatch, caplog):
    # Entry window absent, re-strike windows 100.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(100.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__100__0p5(monkeypatch, caplog):
    # Entry window absent, re-strike windows 100.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(100.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__100__1(monkeypatch, caplog):
    # Entry window absent, re-strike windows 100.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(100.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__100__2(monkeypatch, caplog):
    # Entry window absent, re-strike windows 100.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(100.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__100__4(monkeypatch, caplog):
    # Entry window absent, re-strike windows 100.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(100.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__100__8(monkeypatch, caplog):
    # Entry window absent, re-strike windows 100.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(100.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_absent__100__100(monkeypatch, caplog):
    # Entry window absent, re-strike windows 100.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(), _E(100.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__absent__absent(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows absent then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__absent__0p1(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows absent then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__absent__0p25(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows absent then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__absent__0p5(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows absent then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__absent__1(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows absent then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__absent__2(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows absent then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__absent__4(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows absent then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__absent__8(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows absent then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__absent__100(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows absent then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p1__absent(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.1 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.1), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p1__0p1(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.1 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.1), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p1__0p25(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.1 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.1), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p1__0p5(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.1 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.1), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p1__1(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.1 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.1), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p1__2(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.1 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.1), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p1__4(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.1 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.1), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p1__8(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.1 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.1), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p1__100(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.1 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.1), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p25__absent(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.25 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.25), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p25__0p1(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.25 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.25), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p25__0p25(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.25 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.25), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p25__0p5(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.25 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.25), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p25__1(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.25 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.25), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p25__2(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.25 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.25), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p25__4(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.25 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.25), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p25__8(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.25 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.25), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p25__100(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.25 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.25), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p5__absent(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.5 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.5), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p5__0p1(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.5 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.5), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p5__0p25(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.5 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.5), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p5__0p5(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.5 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.5), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p5__1(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.5 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.5), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p5__2(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.5 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.5), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p5__4(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.5 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.5), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p5__8(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.5 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.5), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__0p5__100(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 0.5 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(0.5), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__1__absent(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 1.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(1.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__1__0p1(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 1.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(1.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__1__0p25(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 1.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(1.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__1__0p5(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 1.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(1.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__1__1(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 1.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(1.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__1__2(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 1.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(1.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__1__4(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 1.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(1.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__1__8(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 1.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(1.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__1__100(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 1.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(1.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__2__absent(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 2.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(2.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__2__0p1(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 2.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(2.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__2__0p25(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 2.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(2.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__2__0p5(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 2.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(2.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__2__1(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 2.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(2.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__2__2(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 2.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(2.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__2__4(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 2.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(2.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__2__8(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 2.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(2.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__2__100(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 2.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(2.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__4__absent(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 4.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(4.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__4__0p1(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 4.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(4.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__4__0p25(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 4.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(4.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__4__0p5(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 4.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(4.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__4__1(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 4.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(4.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__4__2(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 4.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(4.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__4__4(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 4.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(4.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__4__8(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 4.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(4.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__4__100(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 4.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(4.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__8__absent(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 8.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(8.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__8__0p1(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 8.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(8.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__8__0p25(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 8.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(8.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__8__0p5(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 8.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(8.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__8__1(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 8.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(8.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__8__2(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 8.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(8.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__8__4(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 8.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(8.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__8__8(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 8.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(8.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__8__100(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 8.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(8.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__100__absent(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 100.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(100.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__100__0p1(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 100.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(100.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__100__0p25(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 100.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(100.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__100__0p5(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 100.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(100.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__100__1(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 100.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(100.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__100__2(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 100.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(100.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__100__4(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 100.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(100.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__100__8(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 100.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(100.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p1__100__100(monkeypatch, caplog):
    # Entry window 0.1, re-strike windows 100.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.1), _E(100.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__absent__absent(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows absent then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__absent__0p1(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows absent then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__absent__0p25(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows absent then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__absent__0p5(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows absent then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__absent__1(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows absent then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__absent__2(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows absent then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__absent__4(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows absent then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__absent__8(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows absent then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__absent__100(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows absent then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p1__absent(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.1 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.1), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p1__0p1(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.1 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.1), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p1__0p25(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.1 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.1), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p1__0p5(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.1 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.1), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p1__1(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.1 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.1), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p1__2(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.1 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.1), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p1__4(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.1 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.1), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p1__8(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.1 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.1), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p1__100(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.1 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.1), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p25__absent(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.25 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.25), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p25__0p1(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.25 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.25), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p25__0p25(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.25 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.25), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p25__0p5(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.25 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.25), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p25__1(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.25 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.25), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p25__2(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.25 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.25), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p25__4(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.25 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.25), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p25__8(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.25 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.25), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p25__100(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.25 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.25), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p5__absent(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.5 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.5), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p5__0p1(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.5 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.5), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p5__0p25(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.5 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.5), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p5__0p5(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.5 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.5), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p5__1(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.5 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.5), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p5__2(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.5 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.5), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p5__4(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.5 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.5), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p5__8(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.5 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.5), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__0p5__100(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 0.5 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(0.5), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__1__absent(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 1.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(1.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__1__0p1(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 1.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(1.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__1__0p25(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 1.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(1.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__1__0p5(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 1.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(1.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__1__1(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 1.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(1.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__1__2(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 1.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(1.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__1__4(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 1.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(1.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__1__8(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 1.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(1.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__1__100(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 1.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(1.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__2__absent(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 2.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(2.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__2__0p1(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 2.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(2.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__2__0p25(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 2.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(2.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__2__0p5(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 2.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(2.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__2__1(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 2.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(2.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__2__2(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 2.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(2.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__2__4(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 2.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(2.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__2__8(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 2.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(2.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__2__100(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 2.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(2.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__4__absent(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 4.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(4.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__4__0p1(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 4.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(4.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__4__0p25(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 4.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(4.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__4__0p5(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 4.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(4.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__4__1(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 4.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(4.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__4__2(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 4.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(4.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__4__4(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 4.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(4.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__4__8(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 4.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(4.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__4__100(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 4.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(4.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__8__absent(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 8.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(8.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__8__0p1(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 8.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(8.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__8__0p25(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 8.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(8.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__8__0p5(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 8.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(8.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__8__1(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 8.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(8.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__8__2(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 8.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(8.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__8__4(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 8.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(8.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__8__8(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 8.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(8.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__8__100(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 8.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(8.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__100__absent(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 100.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(100.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__100__0p1(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 100.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(100.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__100__0p25(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 100.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(100.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__100__0p5(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 100.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(100.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__100__1(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 100.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(100.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__100__2(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 100.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(100.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__100__4(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 100.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(100.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__100__8(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 100.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(100.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p25__100__100(monkeypatch, caplog):
    # Entry window 0.25, re-strike windows 100.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.25), _E(100.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__absent__absent(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows absent then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__absent__0p1(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows absent then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__absent__0p25(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows absent then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__absent__0p5(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows absent then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__absent__1(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows absent then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__absent__2(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows absent then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__absent__4(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows absent then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__absent__8(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows absent then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__absent__100(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows absent then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p1__absent(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.1 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.1), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p1__0p1(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.1 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.1), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p1__0p25(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.1 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.1), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p1__0p5(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.1 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.1), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p1__1(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.1 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.1), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p1__2(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.1 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.1), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p1__4(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.1 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.1), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p1__8(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.1 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.1), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p1__100(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.1 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.1), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p25__absent(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.25 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.25), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p25__0p1(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.25 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.25), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p25__0p25(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.25 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.25), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p25__0p5(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.25 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.25), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p25__1(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.25 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.25), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p25__2(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.25 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.25), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p25__4(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.25 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.25), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p25__8(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.25 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.25), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p25__100(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.25 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.25), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p5__absent(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.5 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.5), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p5__0p1(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.5 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.5), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p5__0p25(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.5 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.5), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p5__0p5(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.5 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.5), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p5__1(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.5 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.5), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p5__2(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.5 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.5), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p5__4(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.5 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.5), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p5__8(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.5 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.5), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__0p5__100(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 0.5 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(0.5), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__1__absent(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 1.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(1.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__1__0p1(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 1.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(1.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__1__0p25(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 1.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(1.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__1__0p5(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 1.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(1.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__1__1(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 1.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(1.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__1__2(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 1.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(1.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 1.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__1__4(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 1.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(1.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__1__8(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 1.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(1.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__1__100(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 1.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(1.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__2__absent(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 2.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(2.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__2__0p1(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 2.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(2.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__2__0p25(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 2.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(2.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__2__0p5(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 2.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(2.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__2__1(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 2.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(2.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__2__2(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 2.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(2.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 2.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__2__4(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 2.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(2.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__2__8(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 2.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(2.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__2__100(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 2.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(2.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__4__absent(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 4.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(4.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__4__0p1(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 4.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(4.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__4__0p25(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 4.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(4.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__4__0p5(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 4.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(4.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__4__1(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 4.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(4.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__4__2(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 4.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(4.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__4__4(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 4.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(4.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__4__8(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 4.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(4.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__4__100(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 4.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(4.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__8__absent(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 8.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(8.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__8__0p1(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 8.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(8.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__8__0p25(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 8.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(8.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__8__0p5(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 8.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(8.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__8__1(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 8.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(8.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__8__2(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 8.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(8.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__8__4(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 8.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(8.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__8__8(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 8.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(8.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__8__100(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 8.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(8.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__100__absent(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 100.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(100.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__100__0p1(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 100.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(100.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__100__0p25(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 100.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(100.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__100__0p5(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 100.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(100.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__100__1(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 100.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(100.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__100__2(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 100.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(100.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__100__4(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 100.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(100.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__100__8(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 100.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(100.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_0p5__100__100(monkeypatch, caplog):
    # Entry window 0.5, re-strike windows 100.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(0.5), _E(100.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.5, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__absent__absent(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows absent then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__absent__0p1(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows absent then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__absent__0p25(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows absent then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__absent__0p5(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows absent then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__absent__1(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows absent then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__absent__2(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows absent then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__absent__4(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows absent then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__absent__8(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows absent then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__absent__100(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows absent then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p1__absent(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.1 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.1), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p1__0p1(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.1 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.1), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p1__0p25(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.1 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.1), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p1__0p5(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.1 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.1), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p1__1(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.1 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.1), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p1__2(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.1 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.1), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p1__4(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.1 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.1), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p1__8(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.1 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.1), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p1__100(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.1 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.1), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p25__absent(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.25 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.25), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p25__0p1(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.25 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.25), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p25__0p25(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.25 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.25), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p25__0p5(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.25 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.25), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p25__1(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.25 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.25), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p25__2(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.25 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.25), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p25__4(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.25 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.25), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p25__8(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.25 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.25), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p25__100(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.25 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.25), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p5__absent(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.5 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.5), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p5__0p1(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.5 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.5), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p5__0p25(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.5 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.5), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p5__0p5(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.5 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.5), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p5__1(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.5 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.5), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p5__2(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.5 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.5), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p5__4(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.5 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.5), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p5__8(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.5 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.5), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__0p5__100(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 0.5 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(0.5), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__1__absent(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 1.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(1.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__1__0p1(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 1.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(1.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__1__0p25(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 1.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(1.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__1__0p5(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 1.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(1.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__1__1(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 1.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(1.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__1__2(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 1.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(1.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 1.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__1__4(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 1.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(1.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__1__8(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 1.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(1.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__1__100(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 1.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(1.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__2__absent(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 2.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(2.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__2__0p1(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 2.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(2.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__2__0p25(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 2.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(2.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__2__0p5(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 2.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(2.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__2__1(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 2.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(2.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__2__2(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 2.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(2.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 2.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__2__4(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 2.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(2.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__2__8(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 2.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(2.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__2__100(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 2.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(2.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__4__absent(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 4.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(4.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__4__0p1(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 4.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(4.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__4__0p25(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 4.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(4.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__4__0p5(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 4.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(4.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__4__1(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 4.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(4.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__4__2(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 4.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(4.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__4__4(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 4.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(4.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__4__8(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 4.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(4.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__4__100(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 4.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(4.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__8__absent(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 8.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(8.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__8__0p1(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 8.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(8.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__8__0p25(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 8.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(8.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__8__0p5(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 8.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(8.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__8__1(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 8.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(8.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__8__2(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 8.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(8.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__8__4(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 8.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(8.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__8__8(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 8.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(8.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__8__100(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 8.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(8.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__100__absent(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 100.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(100.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__100__0p1(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 100.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(100.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__100__0p25(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 100.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(100.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__100__0p5(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 100.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(100.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__100__1(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 100.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(100.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__100__2(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 100.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(100.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__100__4(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 100.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(100.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__100__8(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 100.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(100.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_1__100__100(monkeypatch, caplog):
    # Entry window 1.0, re-strike windows 100.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(1.0), _E(100.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__absent__absent(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows absent then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__absent__0p1(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows absent then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__absent__0p25(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows absent then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__absent__0p5(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows absent then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__absent__1(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows absent then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__absent__2(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows absent then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__absent__4(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows absent then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__absent__8(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows absent then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__absent__100(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows absent then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p1__absent(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.1 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.1), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p1__0p1(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.1 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.1), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p1__0p25(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.1 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.1), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p1__0p5(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.1 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.1), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p1__1(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.1 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.1), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p1__2(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.1 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.1), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p1__4(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.1 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.1), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p1__8(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.1 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.1), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p1__100(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.1 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.1), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p25__absent(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.25 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.25), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p25__0p1(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.25 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.25), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p25__0p25(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.25 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.25), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p25__0p5(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.25 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.25), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p25__1(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.25 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.25), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p25__2(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.25 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.25), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p25__4(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.25 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.25), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p25__8(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.25 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.25), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p25__100(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.25 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.25), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p5__absent(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.5 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.5), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p5__0p1(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.5 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.5), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p5__0p25(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.5 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.5), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p5__0p5(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.5 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.5), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p5__1(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.5 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.5), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p5__2(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.5 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.5), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p5__4(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.5 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.5), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p5__8(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.5 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.5), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__0p5__100(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 0.5 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(0.5), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__1__absent(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 1.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(1.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__1__0p1(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 1.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(1.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__1__0p25(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 1.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(1.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__1__0p5(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 1.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(1.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__1__1(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 1.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(1.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__1__2(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 1.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(1.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 1.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__1__4(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 1.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(1.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__1__8(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 1.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(1.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__1__100(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 1.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(1.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__2__absent(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 2.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(2.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__2__0p1(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 2.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(2.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__2__0p25(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 2.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(2.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__2__0p5(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 2.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(2.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__2__1(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 2.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(2.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__2__2(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 2.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(2.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 2.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__2__4(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 2.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(2.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__2__8(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 2.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(2.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__2__100(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 2.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(2.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__4__absent(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 4.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(4.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__4__0p1(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 4.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(4.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__4__0p25(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 4.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(4.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__4__0p5(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 4.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(4.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__4__1(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 4.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(4.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__4__2(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 4.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(4.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__4__4(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 4.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(4.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__4__8(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 4.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(4.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__4__100(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 4.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(4.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__8__absent(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 8.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(8.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__8__0p1(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 8.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(8.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__8__0p25(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 8.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(8.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__8__0p5(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 8.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(8.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__8__1(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 8.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(8.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__8__2(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 8.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(8.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__8__4(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 8.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(8.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__8__8(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 8.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(8.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__8__100(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 8.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(8.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__100__absent(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 100.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(100.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__100__0p1(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 100.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(100.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__100__0p25(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 100.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(100.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__100__0p5(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 100.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(100.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__100__1(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 100.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(100.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__100__2(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 100.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(100.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__100__4(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 100.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(100.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__100__8(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 100.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(100.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_2__100__100(monkeypatch, caplog):
    # Entry window 2.0, re-strike windows 100.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(2.0), _E(100.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [2.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__absent__absent(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows absent then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__absent__0p1(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows absent then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__absent__0p25(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows absent then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__absent__0p5(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows absent then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__absent__1(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows absent then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__absent__2(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows absent then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__absent__4(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows absent then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__absent__8(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows absent then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__absent__100(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows absent then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p1__absent(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.1 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.1), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p1__0p1(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.1 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.1), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p1__0p25(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.1 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.1), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p1__0p5(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.1 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.1), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p1__1(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.1 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.1), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p1__2(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.1 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.1), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p1__4(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.1 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.1), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p1__8(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.1 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.1), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p1__100(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.1 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.1), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p25__absent(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.25 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.25), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p25__0p1(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.25 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.25), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p25__0p25(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.25 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.25), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p25__0p5(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.25 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.25), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p25__1(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.25 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.25), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p25__2(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.25 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.25), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p25__4(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.25 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.25), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p25__8(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.25 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.25), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p25__100(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.25 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.25), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p5__absent(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.5 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.5), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p5__0p1(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.5 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.5), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p5__0p25(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.5 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.5), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p5__0p5(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.5 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.5), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p5__1(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.5 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.5), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p5__2(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.5 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.5), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p5__4(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.5 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.5), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p5__8(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.5 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.5), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__0p5__100(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 0.5 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(0.5), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__1__absent(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 1.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(1.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__1__0p1(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 1.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(1.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__1__0p25(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 1.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(1.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__1__0p5(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 1.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(1.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__1__1(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 1.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(1.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__1__2(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 1.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(1.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__1__4(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 1.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(1.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__1__8(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 1.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(1.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__1__100(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 1.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(1.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__2__absent(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 2.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(2.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__2__0p1(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 2.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(2.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__2__0p25(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 2.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(2.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__2__0p5(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 2.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(2.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__2__1(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 2.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(2.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__2__2(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 2.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(2.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__2__4(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 2.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(2.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__2__8(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 2.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(2.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__2__100(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 2.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(2.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__4__absent(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 4.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(4.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__4__0p1(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 4.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(4.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__4__0p25(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 4.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(4.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__4__0p5(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 4.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(4.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__4__1(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 4.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(4.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__4__2(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 4.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(4.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__4__4(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 4.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(4.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__4__8(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 4.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(4.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__4__100(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 4.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(4.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__8__absent(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 8.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(8.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__8__0p1(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 8.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(8.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__8__0p25(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 8.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(8.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__8__0p5(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 8.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(8.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__8__1(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 8.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(8.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__8__2(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 8.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(8.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__8__4(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 8.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(8.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__8__8(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 8.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(8.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__8__100(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 8.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(8.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__100__absent(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 100.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(100.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__100__0p1(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 100.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(100.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__100__0p25(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 100.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(100.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__100__0p5(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 100.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(100.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__100__1(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 100.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(100.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__100__2(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 100.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(100.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__100__4(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 100.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(100.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__100__8(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 100.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(100.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_4__100__100(monkeypatch, caplog):
    # Entry window 4.0, re-strike windows 100.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(4.0), _E(100.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__absent__absent(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows absent then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__absent__0p1(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows absent then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__absent__0p25(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows absent then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__absent__0p5(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows absent then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__absent__1(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows absent then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__absent__2(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows absent then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__absent__4(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows absent then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__absent__8(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows absent then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__absent__100(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows absent then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p1__absent(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.1 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.1), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p1__0p1(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.1 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.1), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p1__0p25(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.1 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.1), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p1__0p5(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.1 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.1), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p1__1(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.1 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.1), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p1__2(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.1 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.1), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p1__4(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.1 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.1), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p1__8(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.1 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.1), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p1__100(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.1 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.1), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p25__absent(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.25 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.25), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p25__0p1(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.25 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.25), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p25__0p25(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.25 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.25), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p25__0p5(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.25 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.25), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p25__1(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.25 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.25), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p25__2(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.25 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.25), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p25__4(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.25 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.25), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p25__8(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.25 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.25), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p25__100(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.25 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.25), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p5__absent(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.5 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.5), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p5__0p1(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.5 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.5), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p5__0p25(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.5 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.5), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p5__0p5(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.5 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.5), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p5__1(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.5 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.5), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p5__2(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.5 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.5), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p5__4(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.5 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.5), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p5__8(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.5 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.5), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__0p5__100(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 0.5 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(0.5), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__1__absent(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 1.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(1.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__1__0p1(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 1.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(1.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__1__0p25(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 1.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(1.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__1__0p5(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 1.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(1.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__1__1(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 1.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(1.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__1__2(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 1.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(1.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__1__4(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 1.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(1.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__1__8(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 1.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(1.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__1__100(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 1.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(1.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__2__absent(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 2.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(2.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__2__0p1(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 2.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(2.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__2__0p25(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 2.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(2.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__2__0p5(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 2.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(2.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__2__1(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 2.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(2.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__2__2(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 2.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(2.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__2__4(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 2.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(2.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__2__8(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 2.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(2.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__2__100(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 2.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(2.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__4__absent(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 4.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(4.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__4__0p1(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 4.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(4.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__4__0p25(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 4.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(4.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__4__0p5(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 4.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(4.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__4__1(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 4.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(4.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__4__2(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 4.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(4.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__4__4(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 4.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(4.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__4__8(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 4.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(4.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__4__100(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 4.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(4.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__8__absent(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 8.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(8.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__8__0p1(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 8.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(8.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__8__0p25(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 8.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(8.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__8__0p5(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 8.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(8.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__8__1(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 8.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(8.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__8__2(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 8.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(8.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__8__4(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 8.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(8.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__8__8(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 8.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(8.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__8__100(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 8.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(8.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__100__absent(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 100.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(100.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__100__0p1(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 100.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(100.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__100__0p25(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 100.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(100.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__100__0p5(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 100.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(100.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__100__1(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 100.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(100.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__100__2(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 100.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(100.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__100__4(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 100.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(100.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__100__8(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 100.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(100.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_8__100__100(monkeypatch, caplog):
    # Entry window 8.0, re-strike windows 100.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(8.0), _E(100.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__absent__absent(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows absent then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__absent__0p1(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows absent then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__absent__0p25(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows absent then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__absent__0p5(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows absent then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__absent__1(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows absent then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__absent__2(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows absent then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__absent__4(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows absent then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__absent__8(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows absent then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__absent__100(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows absent then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p1__absent(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.1 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.1), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p1__0p1(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.1 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.1), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p1__0p25(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.1 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.1), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p1__0p5(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.1 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.1), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p1__1(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.1 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.1), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p1__2(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.1 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.1), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p1__4(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.1 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.1), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p1__8(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.1 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.1), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p1__100(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.1 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.1), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p25__absent(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.25 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.25), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p25__0p1(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.25 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.25), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p25__0p25(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.25 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.25), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p25__0p5(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.25 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.25), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p25__1(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.25 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.25), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p25__2(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.25 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.25), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p25__4(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.25 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.25), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p25__8(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.25 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.25), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p25__100(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.25 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.25), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p5__absent(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.5 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.5), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p5__0p1(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.5 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.5), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p5__0p25(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.5 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.5), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p5__0p5(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.5 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.5), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p5__1(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.5 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.5), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p5__2(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.5 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.5), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p5__4(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.5 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.5), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p5__8(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.5 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.5), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__0p5__100(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 0.5 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(0.5), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 0.5, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__1__absent(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 1.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(1.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__1__0p1(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 1.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(1.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__1__0p25(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 1.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(1.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__1__0p5(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 1.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(1.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__1__1(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 1.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(1.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__1__2(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 1.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(1.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__1__4(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 1.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(1.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__1__8(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 1.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(1.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__1__100(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 1.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(1.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 1.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__2__absent(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 2.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(2.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__2__0p1(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 2.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(2.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__2__0p25(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 2.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(2.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__2__0p5(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 2.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(2.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__2__1(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 2.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(2.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__2__2(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 2.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(2.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__2__4(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 2.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(2.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__2__8(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 2.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(2.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__2__100(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 2.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(2.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 2.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__4__absent(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 4.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(4.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__4__0p1(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 4.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(4.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__4__0p25(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 4.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(4.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__4__0p5(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 4.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(4.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__4__1(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 4.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(4.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__4__2(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 4.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(4.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__4__4(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 4.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(4.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__4__8(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 4.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(4.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__4__100(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 4.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(4.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__8__absent(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 8.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(8.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__8__0p1(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 8.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(8.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__8__0p25(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 8.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(8.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__8__0p5(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 8.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(8.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__8__1(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 8.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(8.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__8__2(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 8.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(8.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__8__4(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 8.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(8.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__8__8(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 8.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(8.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__8__100(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 8.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(8.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__100__absent(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 100.0 then absent: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(100.0), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__100__0p1(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 100.0 then 0.1: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(100.0), _E(0.1), _E(0.1))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__100__0p25(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 100.0 then 0.25: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(100.0), _E(0.25), _E(0.25))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__100__0p5(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 100.0 then 0.5: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(100.0), _E(0.5), _E(0.5))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__100__1(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 100.0 then 1.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(100.0), _E(1.0), _E(1.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__100__2(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 100.0 then 2.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(100.0), _E(2.0), _E(2.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 2.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__100__4(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 100.0 then 4.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(100.0), _E(4.0), _E(4.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__100__8(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 100.0 then 8.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(100.0), _E(8.0), _E(8.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_reaim_100__100__100(monkeypatch, caplog):
    # Entry window 100.0, re-strike windows 100.0 then 100.0: the lane exhausts
    # its budget and every wait re-aims at the freshest measurement.
    pump, scheduler, lost, accepted = await _run(monkeypatch, caplog, _E(100.0), _E(100.0), _E(100.0), _E(100.0))
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


# ---------------------------------------------------------------------------
# The fail transition (worker failure / quarantine publications) rides the
# same aligned waits: one cell per result kind x payload x landing plan
# ---------------------------------------------------------------------------


async def test_fail_failedwork_payload_absent_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(monkeypatch, caplog, FailedWork('seg-1'), _E(), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [c[0] for c in scheduler.calls] == ['fail', 'fail']


async def test_fail_failedwork_payload_absent_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(monkeypatch, caplog, FailedWork('seg-1'), _E(), _E(), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5]
    assert len(scheduler.calls) == 3


async def test_fail_failedwork_payload_absent_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(monkeypatch, caplog, FailedWork('seg-1'), _E(), _E(), _E(), _E())
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_fail_failedwork_payload_absent_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(monkeypatch, caplog, FailedWork('seg-1'), _E(), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [0.25]
    assert len(scheduler.calls) == 2


async def test_fail_failedwork_payload_0p25_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(monkeypatch, caplog, FailedWork('seg-1'), _E(0.25), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [c[0] for c in scheduler.calls] == ['fail', 'fail']


async def test_fail_failedwork_payload_0p25_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, FailedWork('seg-1'), _E(0.25), _E(0.25), True
    )
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5]
    assert len(scheduler.calls) == 3


async def test_fail_failedwork_payload_0p25_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, FailedWork('seg-1'), _E(0.25), _E(0.25), _E(0.25), _E(0.25)
    )
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_fail_failedwork_payload_0p25_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(monkeypatch, caplog, FailedWork('seg-1'), _E(0.25), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [0.25]
    assert len(scheduler.calls) == 2


async def test_fail_failedwork_payload_1p5_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(monkeypatch, caplog, FailedWork('seg-1'), _E(1.5), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [1.5]
    assert [c[0] for c in scheduler.calls] == ['fail', 'fail']


async def test_fail_failedwork_payload_1p5_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(monkeypatch, caplog, FailedWork('seg-1'), _E(1.5), _E(1.5), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [1.5, 1.5]
    assert len(scheduler.calls) == 3


async def test_fail_failedwork_payload_1p5_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, FailedWork('seg-1'), _E(1.5), _E(1.5), _E(1.5), _E(1.5)
    )
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.5, 1.5, 1.5]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_fail_failedwork_payload_1p5_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(monkeypatch, caplog, FailedWork('seg-1'), _E(1.5), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [1.5]
    assert len(scheduler.calls) == 2


async def test_fail_failedwork_payload_4_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(monkeypatch, caplog, FailedWork('seg-1'), _E(4.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0]
    assert [c[0] for c in scheduler.calls] == ['fail', 'fail']


async def test_fail_failedwork_payload_4_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(monkeypatch, caplog, FailedWork('seg-1'), _E(4.0), _E(4.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0, 4.0]
    assert len(scheduler.calls) == 3


async def test_fail_failedwork_payload_4_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, FailedWork('seg-1'), _E(4.0), _E(4.0), _E(4.0), _E(4.0)
    )
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_fail_failedwork_payload_4_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(monkeypatch, caplog, FailedWork('seg-1'), _E(4.0), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [4.0]
    assert len(scheduler.calls) == 2


async def test_fail_failedwork_payload_100_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(monkeypatch, caplog, FailedWork('seg-1'), _E(100.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0]
    assert [c[0] for c in scheduler.calls] == ['fail', 'fail']


async def test_fail_failedwork_payload_100_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, FailedWork('seg-1'), _E(100.0), _E(100.0), True
    )
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0, 4.0]
    assert len(scheduler.calls) == 3


async def test_fail_failedwork_payload_100_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, FailedWork('seg-1'), _E(100.0), _E(100.0), _E(100.0), _E(100.0)
    )
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_fail_failedwork_payload_100_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(monkeypatch, caplog, FailedWork('seg-1'), _E(100.0), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [4.0]
    assert len(scheduler.calls) == 2


async def test_fail_validationfailurework_payload_absent_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, ValidationFailureWork('seg-1', 'assemble_words', 'empty_asr'), _E(), True
    )
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [c[0] for c in scheduler.calls] == ['fail', 'fail']


async def test_fail_validationfailurework_payload_absent_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, ValidationFailureWork('seg-1', 'assemble_words', 'empty_asr'), _E(), _E(), True
    )
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5]
    assert len(scheduler.calls) == 3


async def test_fail_validationfailurework_payload_absent_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, ValidationFailureWork('seg-1', 'assemble_words', 'empty_asr'), _E(), _E(), _E(), _E()
    )
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_fail_validationfailurework_payload_absent_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, ValidationFailureWork('seg-1', 'assemble_words', 'empty_asr'), _E(), False
    )
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [0.25]
    assert len(scheduler.calls) == 2


async def test_fail_validationfailurework_payload_0p25_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, ValidationFailureWork('seg-1', 'assemble_words', 'empty_asr'), _E(0.25), True
    )
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [c[0] for c in scheduler.calls] == ['fail', 'fail']


async def test_fail_validationfailurework_payload_0p25_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, ValidationFailureWork('seg-1', 'assemble_words', 'empty_asr'), _E(0.25), _E(0.25), True
    )
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5]
    assert len(scheduler.calls) == 3


async def test_fail_validationfailurework_payload_0p25_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch,
        caplog,
        ValidationFailureWork('seg-1', 'assemble_words', 'empty_asr'),
        _E(0.25),
        _E(0.25),
        _E(0.25),
        _E(0.25),
    )
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_fail_validationfailurework_payload_0p25_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, ValidationFailureWork('seg-1', 'assemble_words', 'empty_asr'), _E(0.25), False
    )
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [0.25]
    assert len(scheduler.calls) == 2


async def test_fail_validationfailurework_payload_1p5_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, ValidationFailureWork('seg-1', 'assemble_words', 'empty_asr'), _E(1.5), True
    )
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [1.5]
    assert [c[0] for c in scheduler.calls] == ['fail', 'fail']


async def test_fail_validationfailurework_payload_1p5_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, ValidationFailureWork('seg-1', 'assemble_words', 'empty_asr'), _E(1.5), _E(1.5), True
    )
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [1.5, 1.5]
    assert len(scheduler.calls) == 3


async def test_fail_validationfailurework_payload_1p5_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch,
        caplog,
        ValidationFailureWork('seg-1', 'assemble_words', 'empty_asr'),
        _E(1.5),
        _E(1.5),
        _E(1.5),
        _E(1.5),
    )
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.5, 1.5, 1.5]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_fail_validationfailurework_payload_1p5_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, ValidationFailureWork('seg-1', 'assemble_words', 'empty_asr'), _E(1.5), False
    )
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [1.5]
    assert len(scheduler.calls) == 2


async def test_fail_validationfailurework_payload_4_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, ValidationFailureWork('seg-1', 'assemble_words', 'empty_asr'), _E(4.0), True
    )
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0]
    assert [c[0] for c in scheduler.calls] == ['fail', 'fail']


async def test_fail_validationfailurework_payload_4_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, ValidationFailureWork('seg-1', 'assemble_words', 'empty_asr'), _E(4.0), _E(4.0), True
    )
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0, 4.0]
    assert len(scheduler.calls) == 3


async def test_fail_validationfailurework_payload_4_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch,
        caplog,
        ValidationFailureWork('seg-1', 'assemble_words', 'empty_asr'),
        _E(4.0),
        _E(4.0),
        _E(4.0),
        _E(4.0),
    )
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_fail_validationfailurework_payload_4_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, ValidationFailureWork('seg-1', 'assemble_words', 'empty_asr'), _E(4.0), False
    )
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [4.0]
    assert len(scheduler.calls) == 2


async def test_fail_validationfailurework_payload_100_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, ValidationFailureWork('seg-1', 'assemble_words', 'empty_asr'), _E(100.0), True
    )
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0]
    assert [c[0] for c in scheduler.calls] == ['fail', 'fail']


async def test_fail_validationfailurework_payload_100_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, ValidationFailureWork('seg-1', 'assemble_words', 'empty_asr'), _E(100.0), _E(100.0), True
    )
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0, 4.0]
    assert len(scheduler.calls) == 3


async def test_fail_validationfailurework_payload_100_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch,
        caplog,
        ValidationFailureWork('seg-1', 'assemble_words', 'empty_asr'),
        _E(100.0),
        _E(100.0),
        _E(100.0),
        _E(100.0),
    )
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_fail_validationfailurework_payload_100_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, ValidationFailureWork('seg-1', 'assemble_words', 'empty_asr'), _E(100.0), False
    )
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [4.0]
    assert len(scheduler.calls) == 2


async def test_fail_recoverywork_payload_absent_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(monkeypatch, caplog, RecoveryWork('seg-1'), _E(), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [c[0] for c in scheduler.calls] == ['fail', 'fail']


async def test_fail_recoverywork_payload_absent_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(monkeypatch, caplog, RecoveryWork('seg-1'), _E(), _E(), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5]
    assert len(scheduler.calls) == 3


async def test_fail_recoverywork_payload_absent_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, RecoveryWork('seg-1'), _E(), _E(), _E(), _E()
    )
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_fail_recoverywork_payload_absent_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(monkeypatch, caplog, RecoveryWork('seg-1'), _E(), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [0.25]
    assert len(scheduler.calls) == 2


async def test_fail_recoverywork_payload_0p25_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(monkeypatch, caplog, RecoveryWork('seg-1'), _E(0.25), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [c[0] for c in scheduler.calls] == ['fail', 'fail']


async def test_fail_recoverywork_payload_0p25_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, RecoveryWork('seg-1'), _E(0.25), _E(0.25), True
    )
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [0.25, 0.5]
    assert len(scheduler.calls) == 3


async def test_fail_recoverywork_payload_0p25_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, RecoveryWork('seg-1'), _E(0.25), _E(0.25), _E(0.25), _E(0.25)
    )
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_fail_recoverywork_payload_0p25_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(monkeypatch, caplog, RecoveryWork('seg-1'), _E(0.25), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [0.25]
    assert len(scheduler.calls) == 2


async def test_fail_recoverywork_payload_1p5_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(monkeypatch, caplog, RecoveryWork('seg-1'), _E(1.5), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [1.5]
    assert [c[0] for c in scheduler.calls] == ['fail', 'fail']


async def test_fail_recoverywork_payload_1p5_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, RecoveryWork('seg-1'), _E(1.5), _E(1.5), True
    )
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [1.5, 1.5]
    assert len(scheduler.calls) == 3


async def test_fail_recoverywork_payload_1p5_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, RecoveryWork('seg-1'), _E(1.5), _E(1.5), _E(1.5), _E(1.5)
    )
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [1.5, 1.5, 1.5]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_fail_recoverywork_payload_1p5_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(monkeypatch, caplog, RecoveryWork('seg-1'), _E(1.5), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [1.5]
    assert len(scheduler.calls) == 2


async def test_fail_recoverywork_payload_4_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(monkeypatch, caplog, RecoveryWork('seg-1'), _E(4.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0]
    assert [c[0] for c in scheduler.calls] == ['fail', 'fail']


async def test_fail_recoverywork_payload_4_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, RecoveryWork('seg-1'), _E(4.0), _E(4.0), True
    )
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0, 4.0]
    assert len(scheduler.calls) == 3


async def test_fail_recoverywork_payload_4_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, RecoveryWork('seg-1'), _E(4.0), _E(4.0), _E(4.0), _E(4.0)
    )
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_fail_recoverywork_payload_4_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(monkeypatch, caplog, RecoveryWork('seg-1'), _E(4.0), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [4.0]
    assert len(scheduler.calls) == 2


async def test_fail_recoverywork_payload_100_plan_lands_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(monkeypatch, caplog, RecoveryWork('seg-1'), _E(100.0), True)
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0]
    assert [c[0] for c in scheduler.calls] == ['fail', 'fail']


async def test_fail_recoverywork_payload_100_plan_lands_2(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, RecoveryWork('seg-1'), _E(100.0), _E(100.0), True
    )
    assert accepted is True and lost == set()
    assert pump.sleeps.delays == [4.0, 4.0]
    assert len(scheduler.calls) == 3


async def test_fail_recoverywork_payload_100_plan_exhausts_all(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(
        monkeypatch, caplog, RecoveryWork('seg-1'), _E(100.0), _E(100.0), _E(100.0), _E(100.0)
    )
    assert accepted is False and lost == {'seg-1'}
    assert pump.sleeps.delays == [4.0, 4.0, 4.0]
    assert len(scheduler.calls) == 4
    assert error_lines(caplog)[0].getMessage() == (
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    )


async def test_fail_recoverywork_payload_100_plan_dead_lease_1(monkeypatch, caplog):
    pump, scheduler, lost, accepted = await _run_fail(monkeypatch, caplog, RecoveryWork('seg-1'), _E(100.0), False)
    assert accepted is False and lost == set()  # settled: the fence answered
    assert pump.sleeps.delays == [4.0]
    assert len(scheduler.calls) == 2


# The module needs pytest only for the autouse fixture and asyncio marks.
assert pytest and math and Aborted and FirestoreContentionExhausted
