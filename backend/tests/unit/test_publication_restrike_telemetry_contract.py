"""Lane telemetry contract.

The lane reports on INFO only. Every re-strike logs exactly one wait line before its
backoff sleep (attempt, delay_ms, exception_type) and exactly one committed line when
the fenced transition answers again. The legacy ``event=batch_completion outcome=retry``
ERROR line is reserved for the terminal loss past the lane. No lane event ever carries
a segment identifier: the sensor stays attributable by class, not by customer content.

Failure-Class: FC-publication-contention-discards-completed-gpu-results
"""

import asyncio
import copy
import logging
import types

import pytest
from google.api_core.exceptions import Aborted

import utils.batch_pipeline.pump as pump_module
from config.batch_pipeline import Priority
from database.firestore_transaction_retry import FirestoreContentionExhausted
from utils.batch_pipeline.contracts import (
    FailedWork,
    HeldWork,
    LeasedWork,
    RecoveryWork,
    ValidationFailureWork,
    WorkItem,
    WorkResult,
)

try:
    from utils.batch_pipeline.pump import (
        Pump,
        PUBLICATION_RESTRIKE_BASE_SECONDS,
        PUBLICATION_RESTRIKE_MAX_ATTEMPTS,
        PUBLICATION_RESTRIKE_MAX_SECONDS,
        publication_loss_is_contention,
        publication_restrike_delay,
    )
except ImportError:  # the lane is this suite's subject; the parent fails at runtime (the RED half)
    pass

GATE = 'BATCH_PIPELINE_PUBLICATION_RESTRIKE_ENABLED'
PUMP_LOGGER = 'utils.batch_pipeline.pump'
PUBLICATION_CAP = 3


class SleepRecorder:
    def __init__(self):
        self.delays = []

    async def __call__(self, delay, *args, **kwargs):
        self.delays.append(round(delay, 6))


class StuckSleep:
    def __init__(self):
        self.started = False

    async def __call__(self, delay, *args, **kwargs):
        self.started = True
        await asyncio.Event().wait()


class ScriptScheduler:
    def __init__(self, complete=(), fail=(), defer=(), heartbeat=True):
        self.calls = []
        self.complete_script = list(complete)
        self.fail_script = list(fail)
        self.defer_script = list(defer)
        self.heartbeat_owned = heartbeat

    def _pop(self, script, name, *payload):
        self.calls.append((name, *payload))
        if script:
            step = script.pop(0)
            if callable(step) and not isinstance(step, BaseException):
                return step()
            if isinstance(step, BaseException):
                raise step
            return step
        return True

    def complete(self, result, token, now):
        return self._pop(self.complete_script, 'complete', result.segment_id, token)

    def fail(self, segment_id, token, now, **kwargs):
        return self._pop(self.fail_script, 'fail', segment_id, token, kwargs)

    def defer(self, segment_id, token, now, retry_after=None, **kwargs):
        return self._pop(self.defer_script, 'defer', segment_id, token, retry_after, kwargs)

    def heartbeat(self, segment_id, token, now):
        self.calls.append(('heartbeat', segment_id, token))
        return self.heartbeat_owned


class DrainMerge:
    def __init__(self, script=None):
        self.drained = []
        self.script = list(script or [])

    def commit_next(self, owner_id, now):
        self.drained.append(owner_id)
        if self.script:
            step = self.script.pop(0)
            if isinstance(step, BaseException):
                raise step
        return None


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


def contention_loss(tag='synthetic'):
    try:
        raise Aborted(f'{tag} commit race')
    except Aborted as cause:
        error = FirestoreContentionExhausted(f'Firestore transaction contention exhausted for {tag}')
        error.__cause__ = cause
        return error


def make_pump(scheduler=None, merge=None, **overrides):
    pump = Pump(
        types.SimpleNamespace(),
        types.SimpleNamespace(),
        merge=merge if merge is not None else types.SimpleNamespace(),
        publish_concurrency=overrides.pop('publish_concurrency', 1),
    )
    pump.scheduler = scheduler or ScriptScheduler()
    sleeps = SleepRecorder()
    pump._publication_sleep = sleeps
    pump.sleeps = sleeps
    for name, value in overrides.items():
        setattr(pump, name, value)
    return pump


def events(caplog, token):
    return [r.getMessage() for r in caplog.records if token in r.getMessage()]


def error_lines(caplog):
    return [r for r in caplog.records if 'event=batch_completion outcome=retry' in r.getMessage()]


@pytest.fixture(autouse=True)
def _inline_blocking(monkeypatch):
    async def passthrough(executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(pump_module, 'run_blocking', passthrough)


async def test_wait_line_position_1_exact(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), True])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert (
        events(caplog, 'outcome=restrike_wait')[0]
        == 'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted'
    )


async def test_wait_line_position_2_exact(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), True])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert (
        events(caplog, 'outcome=restrike_wait')[1]
        == 'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted'
    )


async def test_wait_line_position_3_exact(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), contention_loss('c'), True])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert (
        events(caplog, 'outcome=restrike_wait')[2]
        == 'event=batch_publication outcome=restrike_wait attempt=3 delay_ms=1000 exception_type=FirestoreContentionExhausted'
    )


async def test_committed_line_attempt_1_accepted_true(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), True])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=1 accepted=true'
    ]


async def test_committed_line_attempt_1_accepted_false(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=1 accepted=false'
    ]


async def test_committed_line_attempt_2_accepted_true(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), True])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=2 accepted=true'
    ]


async def test_committed_line_attempt_2_accepted_false(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=2 accepted=false'
    ]


async def test_committed_line_attempt_3_accepted_true(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), contention_loss('c'), True])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=3 accepted=true'
    ]


async def test_committed_line_attempt_3_accepted_false(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=3 accepted=false'
    ]


async def test_lane_events_are_info_level_with_the_pump_logger(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    lane_records = [r for r in caplog.records if 'restrike' in r.getMessage()]
    assert lane_records
    for record in lane_records:
        assert record.levelno == logging.INFO
        assert record.name == PUMP_LOGGER


async def test_wait_precedes_its_committed_line(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    tokens = [r.getMessage() for r in caplog.records if 'restrike' in r.getMessage()]
    assert tokens.index(
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted'
    ) < tokens.index('event=batch_publication outcome=restrike_committed attempt=1 accepted=true')


async def test_clean_publication_emits_no_lane_events(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    pump = make_pump(ScriptScheduler())
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert events(caplog, 'restrike') == []


async def test_non_contention_terminal_emits_no_lane_events(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    pump = make_pump(ScriptScheduler(complete=[ValueError('revoked')]))
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert events(caplog, 'restrike') == []


async def test_flag_off_terminal_emits_no_lane_events(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    pump = make_pump(ScriptScheduler(complete=[contention_loss('a')]))
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert events(caplog, 'restrike') == []


async def test_terminal_loss_keeps_the_error_line_and_drops_committed(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    pump = make_pump(ScriptScheduler(complete=[contention_loss(n) for n in ('a', 'b', 'c', 'd')]))
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert len(events(caplog, 'outcome=restrike_wait')) == 3
    assert events(caplog, 'outcome=restrike_committed') == []
    assert len(error_lines(caplog)) == 1


async def test_mixed_loss_wait_names_the_contention_then_the_line_names_valueerror(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    pump = make_pump(ScriptScheduler(complete=[contention_loss('a'), ValueError('revoked')]))
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted'
    ]
    assert [r.getMessage() for r in error_lines(caplog)] == [
        'event=batch_completion outcome=retry exception_type=ValueError'
    ]


async def test_direct_aborted_first_loss_names_aborted_in_the_wait_line(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    pump = make_pump(ScriptScheduler(complete=[Aborted('commit race')]))
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=Aborted'
    ]


async def test_wait_lines_carry_the_field_order_contract(caplog):
    import re

    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    pump = make_pump(ScriptScheduler(complete=[contention_loss(n) for n in ('a', 'b', 'c', 'd')]))
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    pattern = re.compile(r'event=batch_publication outcome=restrike_wait attempt=\d+ delay_ms=\d+ exception_type=\w+')
    for message in events(caplog, 'outcome=restrike_wait'):
        assert pattern.fullmatch(message), message


async def test_lane_events_never_carry_a_segment_id(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    pump = make_pump(ScriptScheduler(complete=[contention_loss('a')]))
    await pump._publish(
        make_lease(segment='seg-sensitive-custody'),
        {'seg-sensitive-custody': WorkResult('seg-sensitive-custody', 'gs://r')},
        set(),
    )
    for message in events(caplog, 'restrike'):
        assert 'seg-sensitive-custody' not in message


async def test_full_ordered_sequence_for_complete_lose2(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    pump = make_pump(ScriptScheduler(complete=[contention_loss('a'), contention_loss('b')]))
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    lane = [
        r.getMessage() for r in caplog.records if 'restrike' in r.getMessage() or 'batch_completion' in r.getMessage()
    ]
    assert lane == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_committed attempt=2 accepted=true',
    ]


async def test_reject_lanes_commit_a_false_answer_at_every_position(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert accepted is False
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=1 accepted=false'
    ]


async def test_reject_lanes_commit_a_false_answer_at_position_two(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert accepted is False
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=2 accepted=false'
    ]


async def test_reject_lanes_commit_a_false_answer_at_position_three(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert accepted is False
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=3 accepted=false'
    ]


async def test_telemetry_complete_committed_attempt_is_the_landing_position(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=3 accepted=true'
    ]
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]


async def test_telemetry_fail_validation_committed_attempt_is_the_landing_position(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=3 accepted=true'
    ]
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]


async def test_telemetry_fail_recovery_committed_attempt_is_the_landing_position(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=3 accepted=true'
    ]
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]


async def test_telemetry_fail_failed_committed_attempt_is_the_landing_position(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=3 accepted=true'
    ]
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]


async def test_telemetry_fail_missing_committed_attempt_is_the_landing_position(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=3 accepted=true'
    ]
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]


async def test_telemetry_defer_held_committed_attempt_is_the_landing_position(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=3 accepted=true'
    ]
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
