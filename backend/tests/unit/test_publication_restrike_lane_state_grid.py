"""Lane state grid: every transition kind through every scripted loss schedule.

For each publication transition (``batch_complete``, the three ``batch_fail`` shapes, the
missing-result ``batch_fail``, and the held ``batch_defer``) and each scripted loss
schedule, this grid pins the full outcome tuple as literals: the accepted answer, the
lost-set membership, the exact sleep schedule, the exact re-strike event strings and
the legacy terminal ERROR line. The flag-off half pins byte-for-byte legacy parity:
one call, no lane, immediate fallback.

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


async def test_state_complete_land_first_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is True
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 1
    assert pump.sleeps.delays == []
    assert len(events(caplog, 'outcome=restrike_wait')) == 0
    assert len(events(caplog, 'outcome=restrike_committed')) == 0
    assert len(error_lines(caplog)) == 0


async def test_state_complete_land_first_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(complete=[])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is True
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_complete_lose1_land_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is True
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 2
    assert pump.sleeps.delays == [0.25]
    assert len(events(caplog, 'outcome=restrike_wait')) == 1
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_complete_lose1_land_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted'
    ]


async def test_state_complete_lose1_land_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=1 accepted=true'
    ]


async def test_state_complete_lose1_land_on_payload_identity():
    scheduler = ScriptScheduler(complete=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'complete']
    assert payloads == [('seg-1', 'tok-1')] * 2


async def test_state_complete_lose1_land_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(complete=[contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_complete_lose2_land_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is True
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 3
    assert pump.sleeps.delays == [0.25, 0.5]
    assert len(events(caplog, 'outcome=restrike_wait')) == 2
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_complete_lose2_land_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_complete_lose2_land_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=2 accepted=true'
    ]


async def test_state_complete_lose2_land_on_payload_identity():
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'complete']
    assert payloads == [('seg-1', 'tok-1')] * 3


async def test_state_complete_lose2_land_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_complete_lose3_land_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is True
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 4
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(events(caplog, 'outcome=restrike_wait')) == 3
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_complete_lose3_land_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=3 delay_ms=1000 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_complete_lose3_land_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=3 accepted=true'
    ]


async def test_state_complete_lose3_land_on_payload_identity():
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'complete']
    assert payloads == [('seg-1', 'tok-1')] * 4


async def test_state_complete_lose3_land_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_complete_exhaust4_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(
        complete=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 4
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(events(caplog, 'outcome=restrike_wait')) == 3
    assert len(events(caplog, 'outcome=restrike_committed')) == 0
    assert len(error_lines(caplog)) == 1


async def test_state_complete_exhaust4_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(
        complete=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=3 delay_ms=1000 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_complete_exhaust4_on_payload_identity():
    scheduler = ScriptScheduler(
        complete=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'complete']
    assert payloads == [('seg-1', 'tok-1')] * 4


async def test_state_complete_exhaust4_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(
        complete=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_complete_exhaust4_on_terminal_line_exact(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(
        complete=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    assert [r.getMessage() for r in error_lines(caplog)] == [
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    ]


async def test_state_complete_reject1_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is False
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 2
    assert pump.sleeps.delays == [0.25]
    assert len(events(caplog, 'outcome=restrike_wait')) == 1
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_complete_reject1_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted'
    ]


async def test_state_complete_reject1_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=1 accepted=false'
    ]


async def test_state_complete_reject1_on_payload_identity():
    scheduler = ScriptScheduler(complete=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'complete']
    assert payloads == [('seg-1', 'tok-1')] * 2


async def test_state_complete_reject1_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_complete_reject2_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is False
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 3
    assert pump.sleeps.delays == [0.25, 0.5]
    assert len(events(caplog, 'outcome=restrike_wait')) == 2
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_complete_reject2_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_complete_reject2_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=2 accepted=false'
    ]


async def test_state_complete_reject2_on_payload_identity():
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'complete']
    assert payloads == [('seg-1', 'tok-1')] * 3


async def test_state_complete_reject2_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_complete_reject3_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is False
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 4
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(events(caplog, 'outcome=restrike_wait')) == 3
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_complete_reject3_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=3 delay_ms=1000 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_complete_reject3_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=3 accepted=false'
    ]


async def test_state_complete_reject3_on_payload_identity():
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'complete']
    assert payloads == [('seg-1', 'tok-1')] * 4


async def test_state_complete_reject3_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_complete_mixed1_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 2
    assert pump.sleeps.delays == [0.25]
    assert len(events(caplog, 'outcome=restrike_wait')) == 1
    assert len(events(caplog, 'outcome=restrike_committed')) == 0
    assert len(error_lines(caplog)) == 1


async def test_state_complete_mixed1_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted'
    ]


async def test_state_complete_mixed1_on_payload_identity():
    scheduler = ScriptScheduler(complete=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'complete']
    assert payloads == [('seg-1', 'tok-1')] * 2


async def test_state_complete_mixed1_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_complete_mixed1_on_terminal_line_exact(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    assert [r.getMessage() for r in error_lines(caplog)] == [
        'event=batch_completion outcome=retry exception_type=ValueError'
    ]


async def test_state_complete_mixed2_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[ValueError('revoked'), contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 1
    assert pump.sleeps.delays == []
    assert len(events(caplog, 'outcome=restrike_wait')) == 0
    assert len(events(caplog, 'outcome=restrike_committed')) == 0
    assert len(error_lines(caplog)) == 1


async def test_state_complete_mixed2_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(complete=[ValueError('revoked'), contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_complete_mixed2_on_terminal_line_exact(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[ValueError('revoked'), contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    assert [r.getMessage() for r in error_lines(caplog)] == [
        'event=batch_completion outcome=retry exception_type=ValueError'
    ]


async def test_state_fail_validation_land_first_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        lost,
    )
    assert accepted is True
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert len(events(caplog, 'outcome=restrike_wait')) == 0
    assert len(events(caplog, 'outcome=restrike_committed')) == 0
    assert len(error_lines(caplog)) == 0


async def test_state_fail_validation_land_first_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        lost,
    )
    assert accepted is True
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_validation_lose1_land_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        lost,
    )
    assert accepted is True
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 2
    assert pump.sleeps.delays == [0.25]
    assert len(events(caplog, 'outcome=restrike_wait')) == 1
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_fail_validation_lose1_land_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted'
    ]


async def test_state_fail_validation_lose1_land_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=1 accepted=true'
    ]


async def test_state_fail_validation_lose1_land_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {
                    'worker_failure': {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'},
                    'measured_held_vad_speech_seconds': 1.5,
                    'worker_vad_receipt': {'v': 1},
                },
            )
        ]
        * 2
    )


async def test_state_fail_validation_lose1_land_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        lost,
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_validation_lose2_land_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        lost,
    )
    assert accepted is True
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 3
    assert pump.sleeps.delays == [0.25, 0.5]
    assert len(events(caplog, 'outcome=restrike_wait')) == 2
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_fail_validation_lose2_land_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_fail_validation_lose2_land_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=2 accepted=true'
    ]


async def test_state_fail_validation_lose2_land_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {
                    'worker_failure': {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'},
                    'measured_held_vad_speech_seconds': 1.5,
                    'worker_vad_receipt': {'v': 1},
                },
            )
        ]
        * 3
    )


async def test_state_fail_validation_lose2_land_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        lost,
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_validation_lose3_land_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        lost,
    )
    assert accepted is True
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 4
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(events(caplog, 'outcome=restrike_wait')) == 3
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_fail_validation_lose3_land_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=3 delay_ms=1000 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_fail_validation_lose3_land_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=3 accepted=true'
    ]


async def test_state_fail_validation_lose3_land_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {
                    'worker_failure': {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'},
                    'measured_held_vad_speech_seconds': 1.5,
                    'worker_vad_receipt': {'v': 1},
                },
            )
        ]
        * 4
    )


async def test_state_fail_validation_lose3_land_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        lost,
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_validation_exhaust4_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(
        fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        lost,
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 4
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(events(caplog, 'outcome=restrike_wait')) == 3
    assert len(events(caplog, 'outcome=restrike_committed')) == 0
    assert len(error_lines(caplog)) == 1


async def test_state_fail_validation_exhaust4_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(
        fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=3 delay_ms=1000 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_fail_validation_exhaust4_on_payload_identity():
    scheduler = ScriptScheduler(
        fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {
                    'worker_failure': {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'},
                    'measured_held_vad_speech_seconds': 1.5,
                    'worker_vad_receipt': {'v': 1},
                },
            )
        ]
        * 4
    )


async def test_state_fail_validation_exhaust4_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(
        fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        lost,
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_validation_exhaust4_on_terminal_line_exact(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(
        fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    assert [r.getMessage() for r in error_lines(caplog)] == [
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    ]


async def test_state_fail_validation_reject1_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        lost,
    )
    assert accepted is False
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 2
    assert pump.sleeps.delays == [0.25]
    assert len(events(caplog, 'outcome=restrike_wait')) == 1
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_fail_validation_reject1_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted'
    ]


async def test_state_fail_validation_reject1_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=1 accepted=false'
    ]


async def test_state_fail_validation_reject1_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {
                    'worker_failure': {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'},
                    'measured_held_vad_speech_seconds': 1.5,
                    'worker_vad_receipt': {'v': 1},
                },
            )
        ]
        * 2
    )


async def test_state_fail_validation_reject1_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        lost,
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_validation_reject2_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        lost,
    )
    assert accepted is False
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 3
    assert pump.sleeps.delays == [0.25, 0.5]
    assert len(events(caplog, 'outcome=restrike_wait')) == 2
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_fail_validation_reject2_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_fail_validation_reject2_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=2 accepted=false'
    ]


async def test_state_fail_validation_reject2_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {
                    'worker_failure': {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'},
                    'measured_held_vad_speech_seconds': 1.5,
                    'worker_vad_receipt': {'v': 1},
                },
            )
        ]
        * 3
    )


async def test_state_fail_validation_reject2_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        lost,
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_validation_reject3_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        lost,
    )
    assert accepted is False
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 4
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(events(caplog, 'outcome=restrike_wait')) == 3
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_fail_validation_reject3_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=3 delay_ms=1000 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_fail_validation_reject3_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=3 accepted=false'
    ]


async def test_state_fail_validation_reject3_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {
                    'worker_failure': {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'},
                    'measured_held_vad_speech_seconds': 1.5,
                    'worker_vad_receipt': {'v': 1},
                },
            )
        ]
        * 4
    )


async def test_state_fail_validation_reject3_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        lost,
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_validation_mixed1_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        lost,
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 2
    assert pump.sleeps.delays == [0.25]
    assert len(events(caplog, 'outcome=restrike_wait')) == 1
    assert len(events(caplog, 'outcome=restrike_committed')) == 0
    assert len(error_lines(caplog)) == 1


async def test_state_fail_validation_mixed1_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted'
    ]


async def test_state_fail_validation_mixed1_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {
                    'worker_failure': {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'},
                    'measured_held_vad_speech_seconds': 1.5,
                    'worker_vad_receipt': {'v': 1},
                },
            )
        ]
        * 2
    )


async def test_state_fail_validation_mixed1_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        lost,
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_validation_mixed1_on_terminal_line_exact(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    assert [r.getMessage() for r in error_lines(caplog)] == [
        'event=batch_completion outcome=retry exception_type=ValueError'
    ]


async def test_state_fail_validation_mixed2_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[ValueError('revoked'), contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        lost,
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert len(events(caplog, 'outcome=restrike_wait')) == 0
    assert len(events(caplog, 'outcome=restrike_committed')) == 0
    assert len(error_lines(caplog)) == 1


async def test_state_fail_validation_mixed2_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[ValueError('revoked'), contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        lost,
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_validation_mixed2_on_terminal_line_exact(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[ValueError('revoked'), contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    assert [r.getMessage() for r in error_lines(caplog)] == [
        'event=batch_completion outcome=retry exception_type=ValueError'
    ]


async def test_state_fail_recovery_land_first_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, lost
    )
    assert accepted is True
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert len(events(caplog, 'outcome=restrike_wait')) == 0
    assert len(events(caplog, 'outcome=restrike_committed')) == 0
    assert len(error_lines(caplog)) == 0


async def test_state_fail_recovery_land_first_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, lost
    )
    assert accepted is True
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_recovery_lose1_land_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, lost
    )
    assert accepted is True
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 2
    assert pump.sleeps.delays == [0.25]
    assert len(events(caplog, 'outcome=restrike_wait')) == 1
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_fail_recovery_lose1_land_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted'
    ]


async def test_state_fail_recovery_lose1_land_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=1 accepted=true'
    ]


async def test_state_fail_recovery_lose1_land_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {
                    'quarantine': True,
                    'padded_retry_empty': False,
                    'padded_retry': None,
                    'worker_failure': {'stage': 'assemble_words', 'reason': 'empty_asr'},
                    'measured_held_vad_speech_seconds': 2.0,
                    'worker_vad_receipt': None,
                },
            )
        ]
        * 2
    )


async def test_state_fail_recovery_lose1_land_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, lost
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_recovery_lose2_land_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, lost
    )
    assert accepted is True
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 3
    assert pump.sleeps.delays == [0.25, 0.5]
    assert len(events(caplog, 'outcome=restrike_wait')) == 2
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_fail_recovery_lose2_land_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_fail_recovery_lose2_land_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=2 accepted=true'
    ]


async def test_state_fail_recovery_lose2_land_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {
                    'quarantine': True,
                    'padded_retry_empty': False,
                    'padded_retry': None,
                    'worker_failure': {'stage': 'assemble_words', 'reason': 'empty_asr'},
                    'measured_held_vad_speech_seconds': 2.0,
                    'worker_vad_receipt': None,
                },
            )
        ]
        * 3
    )


async def test_state_fail_recovery_lose2_land_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, lost
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_recovery_lose3_land_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, lost
    )
    assert accepted is True
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 4
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(events(caplog, 'outcome=restrike_wait')) == 3
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_fail_recovery_lose3_land_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=3 delay_ms=1000 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_fail_recovery_lose3_land_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=3 accepted=true'
    ]


async def test_state_fail_recovery_lose3_land_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {
                    'quarantine': True,
                    'padded_retry_empty': False,
                    'padded_retry': None,
                    'worker_failure': {'stage': 'assemble_words', 'reason': 'empty_asr'},
                    'measured_held_vad_speech_seconds': 2.0,
                    'worker_vad_receipt': None,
                },
            )
        ]
        * 4
    )


async def test_state_fail_recovery_lose3_land_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, lost
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_recovery_exhaust4_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(
        fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, lost
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 4
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(events(caplog, 'outcome=restrike_wait')) == 3
    assert len(events(caplog, 'outcome=restrike_committed')) == 0
    assert len(error_lines(caplog)) == 1


async def test_state_fail_recovery_exhaust4_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(
        fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=3 delay_ms=1000 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_fail_recovery_exhaust4_on_payload_identity():
    scheduler = ScriptScheduler(
        fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {
                    'quarantine': True,
                    'padded_retry_empty': False,
                    'padded_retry': None,
                    'worker_failure': {'stage': 'assemble_words', 'reason': 'empty_asr'},
                    'measured_held_vad_speech_seconds': 2.0,
                    'worker_vad_receipt': None,
                },
            )
        ]
        * 4
    )


async def test_state_fail_recovery_exhaust4_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(
        fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, lost
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_recovery_exhaust4_on_terminal_line_exact(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(
        fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    assert [r.getMessage() for r in error_lines(caplog)] == [
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    ]


async def test_state_fail_recovery_reject1_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, lost
    )
    assert accepted is False
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 2
    assert pump.sleeps.delays == [0.25]
    assert len(events(caplog, 'outcome=restrike_wait')) == 1
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_fail_recovery_reject1_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted'
    ]


async def test_state_fail_recovery_reject1_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=1 accepted=false'
    ]


async def test_state_fail_recovery_reject1_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {
                    'quarantine': True,
                    'padded_retry_empty': False,
                    'padded_retry': None,
                    'worker_failure': {'stage': 'assemble_words', 'reason': 'empty_asr'},
                    'measured_held_vad_speech_seconds': 2.0,
                    'worker_vad_receipt': None,
                },
            )
        ]
        * 2
    )


async def test_state_fail_recovery_reject1_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, lost
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_recovery_reject2_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, lost
    )
    assert accepted is False
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 3
    assert pump.sleeps.delays == [0.25, 0.5]
    assert len(events(caplog, 'outcome=restrike_wait')) == 2
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_fail_recovery_reject2_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_fail_recovery_reject2_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=2 accepted=false'
    ]


async def test_state_fail_recovery_reject2_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {
                    'quarantine': True,
                    'padded_retry_empty': False,
                    'padded_retry': None,
                    'worker_failure': {'stage': 'assemble_words', 'reason': 'empty_asr'},
                    'measured_held_vad_speech_seconds': 2.0,
                    'worker_vad_receipt': None,
                },
            )
        ]
        * 3
    )


async def test_state_fail_recovery_reject2_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, lost
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_recovery_reject3_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, lost
    )
    assert accepted is False
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 4
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(events(caplog, 'outcome=restrike_wait')) == 3
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_fail_recovery_reject3_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=3 delay_ms=1000 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_fail_recovery_reject3_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=3 accepted=false'
    ]


async def test_state_fail_recovery_reject3_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {
                    'quarantine': True,
                    'padded_retry_empty': False,
                    'padded_retry': None,
                    'worker_failure': {'stage': 'assemble_words', 'reason': 'empty_asr'},
                    'measured_held_vad_speech_seconds': 2.0,
                    'worker_vad_receipt': None,
                },
            )
        ]
        * 4
    )


async def test_state_fail_recovery_reject3_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, lost
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_recovery_mixed1_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, lost
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 2
    assert pump.sleeps.delays == [0.25]
    assert len(events(caplog, 'outcome=restrike_wait')) == 1
    assert len(events(caplog, 'outcome=restrike_committed')) == 0
    assert len(error_lines(caplog)) == 1


async def test_state_fail_recovery_mixed1_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted'
    ]


async def test_state_fail_recovery_mixed1_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {
                    'quarantine': True,
                    'padded_retry_empty': False,
                    'padded_retry': None,
                    'worker_failure': {'stage': 'assemble_words', 'reason': 'empty_asr'},
                    'measured_held_vad_speech_seconds': 2.0,
                    'worker_vad_receipt': None,
                },
            )
        ]
        * 2
    )


async def test_state_fail_recovery_mixed1_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, lost
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_recovery_mixed1_on_terminal_line_exact(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    assert [r.getMessage() for r in error_lines(caplog)] == [
        'event=batch_completion outcome=retry exception_type=ValueError'
    ]


async def test_state_fail_recovery_mixed2_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[ValueError('revoked'), contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, lost
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert len(events(caplog, 'outcome=restrike_wait')) == 0
    assert len(events(caplog, 'outcome=restrike_committed')) == 0
    assert len(error_lines(caplog)) == 1


async def test_state_fail_recovery_mixed2_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[ValueError('revoked'), contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, lost
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_recovery_mixed2_on_terminal_line_exact(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[ValueError('revoked'), contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    assert [r.getMessage() for r in error_lines(caplog)] == [
        'event=batch_completion outcome=retry exception_type=ValueError'
    ]


async def test_state_fail_failed_land_first_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        lost,
    )
    assert accepted is True
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert len(events(caplog, 'outcome=restrike_wait')) == 0
    assert len(events(caplog, 'outcome=restrike_committed')) == 0
    assert len(error_lines(caplog)) == 0


async def test_state_fail_failed_land_first_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        lost,
    )
    assert accepted is True
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_failed_lose1_land_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        lost,
    )
    assert accepted is True
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 2
    assert pump.sleeps.delays == [0.25]
    assert len(events(caplog, 'outcome=restrike_wait')) == 1
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_fail_failed_lose1_land_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted'
    ]


async def test_state_fail_failed_lose1_land_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=1 accepted=true'
    ]


async def test_state_fail_failed_lose1_land_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {
                    'measured_held_vad_speech_seconds': 1.0,
                    'worker_vad_receipt': {'v': 1},
                    'worker_failure_evidence': {'stage': 'vad_windows', 'reason': 'vad_bounds'},
                },
            )
        ]
        * 2
    )


async def test_state_fail_failed_lose1_land_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        lost,
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_failed_lose2_land_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        lost,
    )
    assert accepted is True
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 3
    assert pump.sleeps.delays == [0.25, 0.5]
    assert len(events(caplog, 'outcome=restrike_wait')) == 2
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_fail_failed_lose2_land_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_fail_failed_lose2_land_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=2 accepted=true'
    ]


async def test_state_fail_failed_lose2_land_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {
                    'measured_held_vad_speech_seconds': 1.0,
                    'worker_vad_receipt': {'v': 1},
                    'worker_failure_evidence': {'stage': 'vad_windows', 'reason': 'vad_bounds'},
                },
            )
        ]
        * 3
    )


async def test_state_fail_failed_lose2_land_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        lost,
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_failed_lose3_land_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        lost,
    )
    assert accepted is True
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 4
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(events(caplog, 'outcome=restrike_wait')) == 3
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_fail_failed_lose3_land_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=3 delay_ms=1000 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_fail_failed_lose3_land_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=3 accepted=true'
    ]


async def test_state_fail_failed_lose3_land_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {
                    'measured_held_vad_speech_seconds': 1.0,
                    'worker_vad_receipt': {'v': 1},
                    'worker_failure_evidence': {'stage': 'vad_windows', 'reason': 'vad_bounds'},
                },
            )
        ]
        * 4
    )


async def test_state_fail_failed_lose3_land_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        lost,
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_failed_exhaust4_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(
        fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        lost,
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 4
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(events(caplog, 'outcome=restrike_wait')) == 3
    assert len(events(caplog, 'outcome=restrike_committed')) == 0
    assert len(error_lines(caplog)) == 1


async def test_state_fail_failed_exhaust4_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(
        fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=3 delay_ms=1000 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_fail_failed_exhaust4_on_payload_identity():
    scheduler = ScriptScheduler(
        fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {
                    'measured_held_vad_speech_seconds': 1.0,
                    'worker_vad_receipt': {'v': 1},
                    'worker_failure_evidence': {'stage': 'vad_windows', 'reason': 'vad_bounds'},
                },
            )
        ]
        * 4
    )


async def test_state_fail_failed_exhaust4_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(
        fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        lost,
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_failed_exhaust4_on_terminal_line_exact(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(
        fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    assert [r.getMessage() for r in error_lines(caplog)] == [
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    ]


async def test_state_fail_failed_reject1_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        lost,
    )
    assert accepted is False
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 2
    assert pump.sleeps.delays == [0.25]
    assert len(events(caplog, 'outcome=restrike_wait')) == 1
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_fail_failed_reject1_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted'
    ]


async def test_state_fail_failed_reject1_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=1 accepted=false'
    ]


async def test_state_fail_failed_reject1_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {
                    'measured_held_vad_speech_seconds': 1.0,
                    'worker_vad_receipt': {'v': 1},
                    'worker_failure_evidence': {'stage': 'vad_windows', 'reason': 'vad_bounds'},
                },
            )
        ]
        * 2
    )


async def test_state_fail_failed_reject1_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        lost,
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_failed_reject2_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        lost,
    )
    assert accepted is False
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 3
    assert pump.sleeps.delays == [0.25, 0.5]
    assert len(events(caplog, 'outcome=restrike_wait')) == 2
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_fail_failed_reject2_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_fail_failed_reject2_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=2 accepted=false'
    ]


async def test_state_fail_failed_reject2_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {
                    'measured_held_vad_speech_seconds': 1.0,
                    'worker_vad_receipt': {'v': 1},
                    'worker_failure_evidence': {'stage': 'vad_windows', 'reason': 'vad_bounds'},
                },
            )
        ]
        * 3
    )


async def test_state_fail_failed_reject2_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        lost,
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_failed_reject3_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        lost,
    )
    assert accepted is False
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 4
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(events(caplog, 'outcome=restrike_wait')) == 3
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_fail_failed_reject3_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=3 delay_ms=1000 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_fail_failed_reject3_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=3 accepted=false'
    ]


async def test_state_fail_failed_reject3_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {
                    'measured_held_vad_speech_seconds': 1.0,
                    'worker_vad_receipt': {'v': 1},
                    'worker_failure_evidence': {'stage': 'vad_windows', 'reason': 'vad_bounds'},
                },
            )
        ]
        * 4
    )


async def test_state_fail_failed_reject3_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        lost,
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_failed_mixed1_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        lost,
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 2
    assert pump.sleeps.delays == [0.25]
    assert len(events(caplog, 'outcome=restrike_wait')) == 1
    assert len(events(caplog, 'outcome=restrike_committed')) == 0
    assert len(error_lines(caplog)) == 1


async def test_state_fail_failed_mixed1_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted'
    ]


async def test_state_fail_failed_mixed1_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {
                    'measured_held_vad_speech_seconds': 1.0,
                    'worker_vad_receipt': {'v': 1},
                    'worker_failure_evidence': {'stage': 'vad_windows', 'reason': 'vad_bounds'},
                },
            )
        ]
        * 2
    )


async def test_state_fail_failed_mixed1_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        lost,
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_failed_mixed1_on_terminal_line_exact(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    assert [r.getMessage() for r in error_lines(caplog)] == [
        'event=batch_completion outcome=retry exception_type=ValueError'
    ]


async def test_state_fail_failed_mixed2_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[ValueError('revoked'), contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        lost,
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert len(events(caplog, 'outcome=restrike_wait')) == 0
    assert len(events(caplog, 'outcome=restrike_committed')) == 0
    assert len(error_lines(caplog)) == 1


async def test_state_fail_failed_mixed2_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[ValueError('revoked'), contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        lost,
    )
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_failed_mixed2_on_terminal_line_exact(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[ValueError('revoked'), contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    assert [r.getMessage() for r in error_lines(caplog)] == [
        'event=batch_completion outcome=retry exception_type=ValueError'
    ]


async def test_state_fail_missing_land_first_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {}, lost)
    assert accepted is True
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert len(events(caplog, 'outcome=restrike_wait')) == 0
    assert len(events(caplog, 'outcome=restrike_committed')) == 0
    assert len(error_lines(caplog)) == 0


async def test_state_fail_missing_land_first_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {}, lost)
    assert accepted is True
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_missing_lose1_land_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {}, lost)
    assert accepted is True
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 2
    assert pump.sleeps.delays == [0.25]
    assert len(events(caplog, 'outcome=restrike_wait')) == 1
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_fail_missing_lose1_land_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted'
    ]


async def test_state_fail_missing_lose1_land_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=1 accepted=true'
    ]


async def test_state_fail_missing_lose1_land_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {'measured_held_vad_speech_seconds': None, 'worker_vad_receipt': None, 'worker_failure_evidence': None},
            )
        ]
        * 2
    )


async def test_state_fail_missing_lose1_land_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_missing_lose2_land_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {}, lost)
    assert accepted is True
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 3
    assert pump.sleeps.delays == [0.25, 0.5]
    assert len(events(caplog, 'outcome=restrike_wait')) == 2
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_fail_missing_lose2_land_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_fail_missing_lose2_land_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=2 accepted=true'
    ]


async def test_state_fail_missing_lose2_land_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {'measured_held_vad_speech_seconds': None, 'worker_vad_receipt': None, 'worker_failure_evidence': None},
            )
        ]
        * 3
    )


async def test_state_fail_missing_lose2_land_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_missing_lose3_land_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {}, lost)
    assert accepted is True
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 4
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(events(caplog, 'outcome=restrike_wait')) == 3
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_fail_missing_lose3_land_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=3 delay_ms=1000 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_fail_missing_lose3_land_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=3 accepted=true'
    ]


async def test_state_fail_missing_lose3_land_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {'measured_held_vad_speech_seconds': None, 'worker_vad_receipt': None, 'worker_failure_evidence': None},
            )
        ]
        * 4
    )


async def test_state_fail_missing_lose3_land_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_missing_exhaust4_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(
        fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 4
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(events(caplog, 'outcome=restrike_wait')) == 3
    assert len(events(caplog, 'outcome=restrike_committed')) == 0
    assert len(error_lines(caplog)) == 1


async def test_state_fail_missing_exhaust4_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(
        fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=3 delay_ms=1000 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_fail_missing_exhaust4_on_payload_identity():
    scheduler = ScriptScheduler(
        fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {'measured_held_vad_speech_seconds': None, 'worker_vad_receipt': None, 'worker_failure_evidence': None},
            )
        ]
        * 4
    )


async def test_state_fail_missing_exhaust4_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(
        fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_missing_exhaust4_on_terminal_line_exact(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(
        fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    assert [r.getMessage() for r in error_lines(caplog)] == [
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    ]


async def test_state_fail_missing_reject1_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {}, lost)
    assert accepted is False
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 2
    assert pump.sleeps.delays == [0.25]
    assert len(events(caplog, 'outcome=restrike_wait')) == 1
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_fail_missing_reject1_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted'
    ]


async def test_state_fail_missing_reject1_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=1 accepted=false'
    ]


async def test_state_fail_missing_reject1_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {'measured_held_vad_speech_seconds': None, 'worker_vad_receipt': None, 'worker_failure_evidence': None},
            )
        ]
        * 2
    )


async def test_state_fail_missing_reject1_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_missing_reject2_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {}, lost)
    assert accepted is False
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 3
    assert pump.sleeps.delays == [0.25, 0.5]
    assert len(events(caplog, 'outcome=restrike_wait')) == 2
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_fail_missing_reject2_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_fail_missing_reject2_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=2 accepted=false'
    ]


async def test_state_fail_missing_reject2_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {'measured_held_vad_speech_seconds': None, 'worker_vad_receipt': None, 'worker_failure_evidence': None},
            )
        ]
        * 3
    )


async def test_state_fail_missing_reject2_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_missing_reject3_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {}, lost)
    assert accepted is False
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 4
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(events(caplog, 'outcome=restrike_wait')) == 3
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_fail_missing_reject3_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=3 delay_ms=1000 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_fail_missing_reject3_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=3 accepted=false'
    ]


async def test_state_fail_missing_reject3_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {'measured_held_vad_speech_seconds': None, 'worker_vad_receipt': None, 'worker_failure_evidence': None},
            )
        ]
        * 4
    )


async def test_state_fail_missing_reject3_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_missing_mixed1_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 2
    assert pump.sleeps.delays == [0.25]
    assert len(events(caplog, 'outcome=restrike_wait')) == 1
    assert len(events(caplog, 'outcome=restrike_committed')) == 0
    assert len(error_lines(caplog)) == 1


async def test_state_fail_missing_mixed1_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted'
    ]


async def test_state_fail_missing_mixed1_on_payload_identity():
    scheduler = ScriptScheduler(fail=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'fail']
    assert (
        payloads
        == [
            (
                'seg-1',
                'tok-1',
                {'measured_held_vad_speech_seconds': None, 'worker_vad_receipt': None, 'worker_failure_evidence': None},
            )
        ]
        * 2
    )


async def test_state_fail_missing_mixed1_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_missing_mixed1_on_terminal_line_exact(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    assert [r.getMessage() for r in error_lines(caplog)] == [
        'event=batch_completion outcome=retry exception_type=ValueError'
    ]


async def test_state_fail_missing_mixed2_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[ValueError('revoked'), contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert len(events(caplog, 'outcome=restrike_wait')) == 0
    assert len(events(caplog, 'outcome=restrike_committed')) == 0
    assert len(error_lines(caplog)) == 1


async def test_state_fail_missing_mixed2_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(fail=[ValueError('revoked'), contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_fail_missing_mixed2_on_terminal_line_exact(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[ValueError('revoked'), contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    assert [r.getMessage() for r in error_lines(caplog)] == [
        'event=batch_completion outcome=retry exception_type=ValueError'
    ]


async def test_state_defer_held_land_first_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, lost)
    assert accepted is False
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'defer']) == 1
    assert pump.sleeps.delays == []
    assert len(events(caplog, 'outcome=restrike_wait')) == 0
    assert len(events(caplog, 'outcome=restrike_committed')) == 0
    assert len(error_lines(caplog)) == 0


async def test_state_defer_held_land_first_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(defer=[])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, lost)
    assert accepted is False
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'defer']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_defer_held_lose1_land_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, lost)
    assert accepted is False
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'defer']) == 2
    assert pump.sleeps.delays == [0.25]
    assert len(events(caplog, 'outcome=restrike_wait')) == 1
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_defer_held_lose1_land_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted'
    ]


async def test_state_defer_held_lose1_land_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=1 accepted=false'
    ]


async def test_state_defer_held_lose1_land_on_payload_identity():
    scheduler = ScriptScheduler(defer=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'defer']
    assert payloads == [('seg-1', 'tok-1', 60, {'held_reason': 'cap_hold', 'admission_refused': True})] * 2


async def test_state_defer_held_lose1_land_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(defer=[contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'defer']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_defer_held_lose2_land_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, lost)
    assert accepted is False
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'defer']) == 3
    assert pump.sleeps.delays == [0.25, 0.5]
    assert len(events(caplog, 'outcome=restrike_wait')) == 2
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_defer_held_lose2_land_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_defer_held_lose2_land_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=2 accepted=false'
    ]


async def test_state_defer_held_lose2_land_on_payload_identity():
    scheduler = ScriptScheduler(defer=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'defer']
    assert payloads == [('seg-1', 'tok-1', 60, {'held_reason': 'cap_hold', 'admission_refused': True})] * 3


async def test_state_defer_held_lose2_land_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(defer=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'defer']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_defer_held_lose3_land_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, lost)
    assert accepted is False
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'defer']) == 4
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(events(caplog, 'outcome=restrike_wait')) == 3
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_defer_held_lose3_land_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=3 delay_ms=1000 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_defer_held_lose3_land_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=3 accepted=false'
    ]


async def test_state_defer_held_lose3_land_on_payload_identity():
    scheduler = ScriptScheduler(defer=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'defer']
    assert payloads == [('seg-1', 'tok-1', 60, {'held_reason': 'cap_hold', 'admission_refused': True})] * 4


async def test_state_defer_held_lose3_land_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(defer=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'defer']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_defer_held_exhaust4_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(
        defer=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'defer']) == 4
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(events(caplog, 'outcome=restrike_wait')) == 3
    assert len(events(caplog, 'outcome=restrike_committed')) == 0
    assert len(error_lines(caplog)) == 1


async def test_state_defer_held_exhaust4_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(
        defer=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=3 delay_ms=1000 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_defer_held_exhaust4_on_payload_identity():
    scheduler = ScriptScheduler(
        defer=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'defer']
    assert payloads == [('seg-1', 'tok-1', 60, {'held_reason': 'cap_hold', 'admission_refused': True})] * 4


async def test_state_defer_held_exhaust4_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(
        defer=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'defer']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_defer_held_exhaust4_on_terminal_line_exact(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(
        defer=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    assert [r.getMessage() for r in error_lines(caplog)] == [
        'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'
    ]


async def test_state_defer_held_reject1_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, lost)
    assert accepted is False
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'defer']) == 2
    assert pump.sleeps.delays == [0.25]
    assert len(events(caplog, 'outcome=restrike_wait')) == 1
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_defer_held_reject1_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted'
    ]


async def test_state_defer_held_reject1_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=1 accepted=false'
    ]


async def test_state_defer_held_reject1_on_payload_identity():
    scheduler = ScriptScheduler(defer=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'defer']
    assert payloads == [('seg-1', 'tok-1', 60, {'held_reason': 'cap_hold', 'admission_refused': True})] * 2


async def test_state_defer_held_reject1_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(defer=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'defer']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_defer_held_reject2_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, lost)
    assert accepted is False
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'defer']) == 3
    assert pump.sleeps.delays == [0.25, 0.5]
    assert len(events(caplog, 'outcome=restrike_wait')) == 2
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_defer_held_reject2_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_defer_held_reject2_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=2 accepted=false'
    ]


async def test_state_defer_held_reject2_on_payload_identity():
    scheduler = ScriptScheduler(defer=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'defer']
    assert payloads == [('seg-1', 'tok-1', 60, {'held_reason': 'cap_hold', 'admission_refused': True})] * 3


async def test_state_defer_held_reject2_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(defer=[contention_loss('a'), contention_loss('b'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'defer']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_defer_held_reject3_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, lost)
    assert accepted is False
    assert lost == set()
    assert len([c for c in scheduler.calls if c[0] == 'defer']) == 4
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(events(caplog, 'outcome=restrike_wait')) == 3
    assert len(events(caplog, 'outcome=restrike_committed')) == 1
    assert len(error_lines(caplog)) == 0


async def test_state_defer_held_reject3_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=3 delay_ms=1000 exception_type=FirestoreContentionExhausted',
    ]


async def test_state_defer_held_reject3_on_committed_string(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=3 accepted=false'
    ]


async def test_state_defer_held_reject3_on_payload_identity():
    scheduler = ScriptScheduler(defer=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'defer']
    assert payloads == [('seg-1', 'tok-1', 60, {'held_reason': 'cap_hold', 'admission_refused': True})] * 4


async def test_state_defer_held_reject3_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(defer=[contention_loss('a'), contention_loss('b'), contention_loss('c'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'defer']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_defer_held_mixed1_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'defer']) == 2
    assert pump.sleeps.delays == [0.25]
    assert len(events(caplog, 'outcome=restrike_wait')) == 1
    assert len(events(caplog, 'outcome=restrike_committed')) == 0
    assert len(error_lines(caplog)) == 1


async def test_state_defer_held_mixed1_on_wait_strings(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    assert events(caplog, 'outcome=restrike_wait') == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted'
    ]


async def test_state_defer_held_mixed1_on_payload_identity():
    scheduler = ScriptScheduler(defer=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    payloads = [c[1:] for c in scheduler.calls if c[0] == 'defer']
    assert payloads == [('seg-1', 'tok-1', 60, {'held_reason': 'cap_hold', 'admission_refused': True})] * 2


async def test_state_defer_held_mixed1_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(defer=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'defer']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_defer_held_mixed1_on_terminal_line_exact(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a'), ValueError('revoked')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    assert [r.getMessage() for r in error_lines(caplog)] == [
        'event=batch_completion outcome=retry exception_type=ValueError'
    ]


async def test_state_defer_held_mixed2_on_outcome(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[ValueError('revoked'), contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'defer']) == 1
    assert pump.sleeps.delays == []
    assert len(events(caplog, 'outcome=restrike_wait')) == 0
    assert len(events(caplog, 'outcome=restrike_committed')) == 0
    assert len(error_lines(caplog)) == 1


async def test_state_defer_held_mixed2_off_parity(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)
    scheduler = ScriptScheduler(defer=[ValueError('revoked'), contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'defer']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_state_defer_held_mixed2_on_terminal_line_exact(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[ValueError('revoked'), contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    assert [r.getMessage() for r in error_lines(caplog)] == [
        'event=batch_completion outcome=retry exception_type=ValueError'
    ]


async def test_state_prelost_gate_land_first_heartbeat_live(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[])
    pump = make_pump(scheduler)
    lost = {'seg-1'}
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert ('heartbeat', 'seg-1', 'tok-1') in scheduler.calls
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 1
    assert accepted is True
    assert lost == set()


async def test_state_prelost_gate_land_first_heartbeat_dead(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[], heartbeat=False)
    pump = make_pump(scheduler)
    lost = {'seg-1'}
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert [c for c in scheduler.calls if c[0] == 'complete'] == []


async def test_state_prelost_gate_lose1_land_heartbeat_live(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a')])
    pump = make_pump(scheduler)
    lost = {'seg-1'}
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert ('heartbeat', 'seg-1', 'tok-1') in scheduler.calls
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 2
    assert accepted is True
    assert lost == set()


async def test_state_prelost_gate_lose1_land_heartbeat_dead(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a')], heartbeat=False)
    pump = make_pump(scheduler)
    lost = {'seg-1'}
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert [c for c in scheduler.calls if c[0] == 'complete'] == []


async def test_state_prelost_gate_exhaust4_heartbeat_live(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(
        complete=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')]
    )
    pump = make_pump(scheduler)
    lost = {'seg-1'}
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert ('heartbeat', 'seg-1', 'tok-1') in scheduler.calls
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 4
    assert accepted is False
    assert lost == {'seg-1'}


async def test_state_prelost_gate_exhaust4_heartbeat_dead(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(
        complete=[contention_loss('a'), contention_loss('b'), contention_loss('c'), contention_loss('d')],
        heartbeat=False,
    )
    pump = make_pump(scheduler)
    lost = {'seg-1'}
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert [c for c in scheduler.calls if c[0] == 'complete'] == []


async def test_state_prelost_gate_mixed2_heartbeat_live(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[ValueError('revoked'), contention_loss('a')])
    pump = make_pump(scheduler)
    lost = {'seg-1'}
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert ('heartbeat', 'seg-1', 'tok-1') in scheduler.calls
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 1
    assert accepted is False
    assert lost == {'seg-1'}


async def test_state_prelost_gate_mixed2_heartbeat_dead(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[ValueError('revoked'), contention_loss('a')], heartbeat=False)
    pump = make_pump(scheduler)
    lost = {'seg-1'}
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert [c for c in scheduler.calls if c[0] == 'complete'] == []


async def test_flight_lose1_land_owners_1_concurrency_1(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    steps = [contention_loss('f0'), True]
    scheduler = ScriptScheduler(complete=steps)
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge, publish_concurrency=1)
    leases = [make_lease(segment=f'seg-{n}', owner=f'owner-{n}') for n in range(1)]
    result_map = {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r') for lease in leases}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert lost == set([])
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 2
    assert merge.drained == ['owner-0']


async def test_flight_lose1_land_owners_1_concurrency_4(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    steps = [contention_loss('f0'), True]
    scheduler = ScriptScheduler(complete=steps)
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge, publish_concurrency=4)
    leases = [make_lease(segment=f'seg-{n}', owner=f'owner-{n}') for n in range(1)]
    result_map = {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r') for lease in leases}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert lost == set([])
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 2
    assert merge.drained == ['owner-0']


async def test_flight_lose1_land_owners_2_concurrency_1(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    steps = [contention_loss('f0'), True, contention_loss('f2'), True]
    scheduler = ScriptScheduler(complete=steps)
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge, publish_concurrency=1)
    leases = [make_lease(segment=f'seg-{n}', owner=f'owner-{n}') for n in range(2)]
    result_map = {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r') for lease in leases}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert lost == set([])
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 4
    assert merge.drained == ['owner-0', 'owner-1']


async def test_flight_lose1_land_owners_2_concurrency_4(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    steps = [contention_loss('f0'), True, contention_loss('f2'), True]
    scheduler = ScriptScheduler(complete=steps)
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge, publish_concurrency=4)
    leases = [make_lease(segment=f'seg-{n}', owner=f'owner-{n}') for n in range(2)]
    result_map = {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r') for lease in leases}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert lost == set([])
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 4
    assert merge.drained == ['owner-0', 'owner-1']


async def test_flight_lose1_land_owners_3_concurrency_1(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    steps = [contention_loss('f0'), True, contention_loss('f2'), True, contention_loss('f4'), True]
    scheduler = ScriptScheduler(complete=steps)
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge, publish_concurrency=1)
    leases = [make_lease(segment=f'seg-{n}', owner=f'owner-{n}') for n in range(3)]
    result_map = {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r') for lease in leases}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert lost == set([])
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 6
    assert merge.drained == ['owner-0', 'owner-1', 'owner-2']


async def test_flight_lose1_land_owners_3_concurrency_4(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    steps = [contention_loss('f0'), True, contention_loss('f2'), True, contention_loss('f4'), True]
    scheduler = ScriptScheduler(complete=steps)
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge, publish_concurrency=4)
    leases = [make_lease(segment=f'seg-{n}', owner=f'owner-{n}') for n in range(3)]
    result_map = {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r') for lease in leases}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert lost == set([])
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 6
    assert merge.drained == ['owner-0', 'owner-1', 'owner-2']


async def test_flight_lose2_land_owners_1_concurrency_1(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    steps = [contention_loss('f0'), contention_loss('f1'), True]
    scheduler = ScriptScheduler(complete=steps)
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge, publish_concurrency=1)
    leases = [make_lease(segment=f'seg-{n}', owner=f'owner-{n}') for n in range(1)]
    result_map = {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r') for lease in leases}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert lost == set([])
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 3
    assert merge.drained == ['owner-0']


async def test_flight_lose2_land_owners_1_concurrency_4(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    steps = [contention_loss('f0'), contention_loss('f1'), True]
    scheduler = ScriptScheduler(complete=steps)
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge, publish_concurrency=4)
    leases = [make_lease(segment=f'seg-{n}', owner=f'owner-{n}') for n in range(1)]
    result_map = {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r') for lease in leases}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert lost == set([])
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 3
    assert merge.drained == ['owner-0']


async def test_flight_lose2_land_owners_2_concurrency_1(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    steps = [contention_loss('f0'), contention_loss('f1'), True, contention_loss('f3'), contention_loss('f4'), True]
    scheduler = ScriptScheduler(complete=steps)
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge, publish_concurrency=1)
    leases = [make_lease(segment=f'seg-{n}', owner=f'owner-{n}') for n in range(2)]
    result_map = {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r') for lease in leases}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert lost == set([])
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 6
    assert merge.drained == ['owner-0', 'owner-1']


async def test_flight_lose2_land_owners_2_concurrency_4(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    steps = [contention_loss('f0'), contention_loss('f1'), True, contention_loss('f3'), contention_loss('f4'), True]
    scheduler = ScriptScheduler(complete=steps)
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge, publish_concurrency=4)
    leases = [make_lease(segment=f'seg-{n}', owner=f'owner-{n}') for n in range(2)]
    result_map = {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r') for lease in leases}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert lost == set([])
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 6
    assert merge.drained == ['owner-0', 'owner-1']


async def test_flight_lose2_land_owners_3_concurrency_1(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    steps = [
        contention_loss('f0'),
        contention_loss('f1'),
        True,
        contention_loss('f3'),
        contention_loss('f4'),
        True,
        contention_loss('f6'),
        contention_loss('f7'),
        True,
    ]
    scheduler = ScriptScheduler(complete=steps)
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge, publish_concurrency=1)
    leases = [make_lease(segment=f'seg-{n}', owner=f'owner-{n}') for n in range(3)]
    result_map = {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r') for lease in leases}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert lost == set([])
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 9
    assert merge.drained == ['owner-0', 'owner-1', 'owner-2']


async def test_flight_lose2_land_owners_3_concurrency_4(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    steps = [
        contention_loss('f0'),
        contention_loss('f1'),
        True,
        contention_loss('f3'),
        contention_loss('f4'),
        True,
        contention_loss('f6'),
        contention_loss('f7'),
        True,
    ]
    scheduler = ScriptScheduler(complete=steps)
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge, publish_concurrency=4)
    leases = [make_lease(segment=f'seg-{n}', owner=f'owner-{n}') for n in range(3)]
    result_map = {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r') for lease in leases}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert lost == set([])
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 9
    assert merge.drained == ['owner-0', 'owner-1', 'owner-2']


async def test_flight_exhaust4_owners_1_concurrency_1(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    steps = [contention_loss('f0'), contention_loss('f1'), contention_loss('f2'), contention_loss('f3')]
    scheduler = ScriptScheduler(complete=steps)
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge, publish_concurrency=1)
    leases = [make_lease(segment=f'seg-{n}', owner=f'owner-{n}') for n in range(1)]
    result_map = {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r') for lease in leases}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert lost == set(['seg-0'])
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 4
    assert merge.drained == []


async def test_flight_exhaust4_owners_1_concurrency_4(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    steps = [contention_loss('f0'), contention_loss('f1'), contention_loss('f2'), contention_loss('f3')]
    scheduler = ScriptScheduler(complete=steps)
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge, publish_concurrency=4)
    leases = [make_lease(segment=f'seg-{n}', owner=f'owner-{n}') for n in range(1)]
    result_map = {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r') for lease in leases}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert lost == set(['seg-0'])
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 4
    assert merge.drained == []


async def test_flight_exhaust4_owners_2_concurrency_1(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    steps = [
        contention_loss('f0'),
        contention_loss('f1'),
        contention_loss('f2'),
        contention_loss('f3'),
        contention_loss('f4'),
        contention_loss('f5'),
        contention_loss('f6'),
        contention_loss('f7'),
    ]
    scheduler = ScriptScheduler(complete=steps)
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge, publish_concurrency=1)
    leases = [make_lease(segment=f'seg-{n}', owner=f'owner-{n}') for n in range(2)]
    result_map = {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r') for lease in leases}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert lost == set(['seg-0', 'seg-1'])
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 8
    assert merge.drained == []


async def test_flight_exhaust4_owners_2_concurrency_4(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    steps = [
        contention_loss('f0'),
        contention_loss('f1'),
        contention_loss('f2'),
        contention_loss('f3'),
        contention_loss('f4'),
        contention_loss('f5'),
        contention_loss('f6'),
        contention_loss('f7'),
    ]
    scheduler = ScriptScheduler(complete=steps)
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge, publish_concurrency=4)
    leases = [make_lease(segment=f'seg-{n}', owner=f'owner-{n}') for n in range(2)]
    result_map = {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r') for lease in leases}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert lost == set(['seg-0', 'seg-1'])
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 8
    assert merge.drained == []


async def test_flight_exhaust4_owners_3_concurrency_1(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    steps = [
        contention_loss('f0'),
        contention_loss('f1'),
        contention_loss('f2'),
        contention_loss('f3'),
        contention_loss('f4'),
        contention_loss('f5'),
        contention_loss('f6'),
        contention_loss('f7'),
        contention_loss('f8'),
        contention_loss('f9'),
        contention_loss('f10'),
        contention_loss('f11'),
    ]
    scheduler = ScriptScheduler(complete=steps)
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge, publish_concurrency=1)
    leases = [make_lease(segment=f'seg-{n}', owner=f'owner-{n}') for n in range(3)]
    result_map = {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r') for lease in leases}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert lost == set(['seg-0', 'seg-1', 'seg-2'])
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 12
    assert merge.drained == []


async def test_flight_exhaust4_owners_3_concurrency_4(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    steps = [
        contention_loss('f0'),
        contention_loss('f1'),
        contention_loss('f2'),
        contention_loss('f3'),
        contention_loss('f4'),
        contention_loss('f5'),
        contention_loss('f6'),
        contention_loss('f7'),
        contention_loss('f8'),
        contention_loss('f9'),
        contention_loss('f10'),
        contention_loss('f11'),
    ]
    scheduler = ScriptScheduler(complete=steps)
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge, publish_concurrency=4)
    leases = [make_lease(segment=f'seg-{n}', owner=f'owner-{n}') for n in range(3)]
    result_map = {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r') for lease in leases}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert lost == set(['seg-0', 'seg-1', 'seg-2'])
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 12
    assert merge.drained == []


async def test_flight_mixed1_owners_1_concurrency_1(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    steps = [contention_loss('f0'), ValueError('revoked')]
    scheduler = ScriptScheduler(complete=steps)
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge, publish_concurrency=1)
    leases = [make_lease(segment=f'seg-{n}', owner=f'owner-{n}') for n in range(1)]
    result_map = {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r') for lease in leases}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert lost == set(['seg-0'])
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 2
    assert merge.drained == []


async def test_flight_mixed1_owners_1_concurrency_4(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    steps = [contention_loss('f0'), ValueError('revoked')]
    scheduler = ScriptScheduler(complete=steps)
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge, publish_concurrency=4)
    leases = [make_lease(segment=f'seg-{n}', owner=f'owner-{n}') for n in range(1)]
    result_map = {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r') for lease in leases}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert lost == set(['seg-0'])
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 2
    assert merge.drained == []


async def test_flight_mixed1_owners_2_concurrency_1(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    steps = [contention_loss('f0'), ValueError('revoked'), contention_loss('f2'), ValueError('revoked')]
    scheduler = ScriptScheduler(complete=steps)
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge, publish_concurrency=1)
    leases = [make_lease(segment=f'seg-{n}', owner=f'owner-{n}') for n in range(2)]
    result_map = {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r') for lease in leases}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert lost == set(['seg-0', 'seg-1'])
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 4
    assert merge.drained == []


async def test_flight_mixed1_owners_2_concurrency_4(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    steps = [contention_loss('f0'), ValueError('revoked'), contention_loss('f2'), ValueError('revoked')]
    scheduler = ScriptScheduler(complete=steps)
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge, publish_concurrency=4)
    leases = [make_lease(segment=f'seg-{n}', owner=f'owner-{n}') for n in range(2)]
    result_map = {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r') for lease in leases}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert lost == set(['seg-0', 'seg-1'])
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 4
    assert merge.drained == []


async def test_flight_mixed1_owners_3_concurrency_1(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    steps = [
        contention_loss('f0'),
        ValueError('revoked'),
        contention_loss('f2'),
        ValueError('revoked'),
        contention_loss('f4'),
        ValueError('revoked'),
    ]
    scheduler = ScriptScheduler(complete=steps)
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge, publish_concurrency=1)
    leases = [make_lease(segment=f'seg-{n}', owner=f'owner-{n}') for n in range(3)]
    result_map = {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r') for lease in leases}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert lost == set(['seg-0', 'seg-1', 'seg-2'])
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 6
    assert merge.drained == []


async def test_flight_mixed1_owners_3_concurrency_4(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    steps = [
        contention_loss('f0'),
        ValueError('revoked'),
        contention_loss('f2'),
        ValueError('revoked'),
        contention_loss('f4'),
        ValueError('revoked'),
    ]
    scheduler = ScriptScheduler(complete=steps)
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge, publish_concurrency=4)
    leases = [make_lease(segment=f'seg-{n}', owner=f'owner-{n}') for n in range(3)]
    result_map = {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r') for lease in leases}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert lost == set(['seg-0', 'seg-1', 'seg-2'])
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 6
    assert merge.drained == []


async def test_drain_interplay_complete_landing_restrike_drains_once(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a')])
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge)
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    await pump._drain_after_publication('owner-1')
    assert accepted is True
    assert merge.drained == ['owner-1']
    assert pump._deferred_drains == {}


async def test_drain_interplay_complete_contended_drain_arms_the_owner(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a')])
    merge = DrainMerge(script=[contention_loss('drain')])
    pump = make_pump(scheduler, merge=merge)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    await pump._drain_after_publication('owner-1')
    armed = pump._deferred_drains.get('owner-1')
    assert armed is not None and armed['attempts'] == 1


async def test_drain_interplay_fail_validation_landing_restrike_drains_once(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge)
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    await pump._drain_after_publication('owner-1')
    assert accepted is True
    assert merge.drained == ['owner-1']
    assert pump._deferred_drains == {}


async def test_drain_interplay_fail_validation_contended_drain_arms_the_owner(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    merge = DrainMerge(script=[contention_loss('drain')])
    pump = make_pump(scheduler, merge=merge)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    await pump._drain_after_publication('owner-1')
    armed = pump._deferred_drains.get('owner-1')
    assert armed is not None and armed['attempts'] == 1


async def test_drain_interplay_fail_recovery_landing_restrike_drains_once(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge)
    accepted = await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    await pump._drain_after_publication('owner-1')
    assert accepted is True
    assert merge.drained == ['owner-1']
    assert pump._deferred_drains == {}


async def test_drain_interplay_fail_recovery_contended_drain_arms_the_owner(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    merge = DrainMerge(script=[contention_loss('drain')])
    pump = make_pump(scheduler, merge=merge)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    await pump._drain_after_publication('owner-1')
    armed = pump._deferred_drains.get('owner-1')
    assert armed is not None and armed['attempts'] == 1


async def test_drain_interplay_fail_failed_landing_restrike_drains_once(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge)
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    await pump._drain_after_publication('owner-1')
    assert accepted is True
    assert merge.drained == ['owner-1']
    assert pump._deferred_drains == {}


async def test_drain_interplay_fail_failed_contended_drain_arms_the_owner(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    merge = DrainMerge(script=[contention_loss('drain')])
    pump = make_pump(scheduler, merge=merge)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    await pump._drain_after_publication('owner-1')
    armed = pump._deferred_drains.get('owner-1')
    assert armed is not None and armed['attempts'] == 1


async def test_drain_interplay_fail_missing_landing_restrike_drains_once(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge)
    accepted = await pump._publish(make_lease(), {}, set())
    await pump._drain_after_publication('owner-1')
    assert accepted is True
    assert merge.drained == ['owner-1']
    assert pump._deferred_drains == {}


async def test_drain_interplay_fail_missing_contended_drain_arms_the_owner(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    merge = DrainMerge(script=[contention_loss('drain')])
    pump = make_pump(scheduler, merge=merge)
    await pump._publish(make_lease(), {}, set())
    await pump._drain_after_publication('owner-1')
    armed = pump._deferred_drains.get('owner-1')
    assert armed is not None and armed['attempts'] == 1


async def test_drain_interplay_defer_held_landing_restrike_drains_once(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a')])
    merge = DrainMerge()
    pump = make_pump(scheduler, merge=merge)
    accepted = await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    await pump._drain_after_publication('owner-1')
    assert accepted is False
    assert merge.drained == ['owner-1']
    assert pump._deferred_drains == {}


async def test_drain_interplay_defer_held_contended_drain_arms_the_owner(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a')])
    merge = DrainMerge(script=[contention_loss('drain')])
    pump = make_pump(scheduler, merge=merge)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    await pump._drain_after_publication('owner-1')
    armed = pump._deferred_drains.get('owner-1')
    assert armed is not None and armed['attempts'] == 1


async def test_cancel_during_complete_lane_sleep_leaves_no_lost_marker(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a')])
    pump = make_pump(scheduler)
    stuck = StuckSleep()
    pump._publication_sleep = stuck
    lost = set()
    task = asyncio.ensure_future(pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost))
    for _ in range(50):
        if stuck.started:
            break
        await asyncio.sleep(0)
    assert stuck.started
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert lost == set()
    assert error_lines(caplog) == []


async def test_cancel_during_fail_validation_lane_sleep_leaves_no_lost_marker(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    stuck = StuckSleep()
    pump._publication_sleep = stuck
    lost = set()
    task = asyncio.ensure_future(
        pump._publish(
            make_lease(),
            {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
            lost,
        )
    )
    for _ in range(50):
        if stuck.started:
            break
        await asyncio.sleep(0)
    assert stuck.started
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert lost == set()
    assert error_lines(caplog) == []


async def test_cancel_during_fail_recovery_lane_sleep_leaves_no_lost_marker(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    stuck = StuckSleep()
    pump._publication_sleep = stuck
    lost = set()
    task = asyncio.ensure_future(
        pump._publish(
            make_lease(),
            {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)},
            lost,
        )
    )
    for _ in range(50):
        if stuck.started:
            break
        await asyncio.sleep(0)
    assert stuck.started
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert lost == set()
    assert error_lines(caplog) == []


async def test_cancel_during_fail_failed_lane_sleep_leaves_no_lost_marker(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    stuck = StuckSleep()
    pump._publication_sleep = stuck
    lost = set()
    task = asyncio.ensure_future(
        pump._publish(
            make_lease(),
            {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
            lost,
        )
    )
    for _ in range(50):
        if stuck.started:
            break
        await asyncio.sleep(0)
    assert stuck.started
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert lost == set()
    assert error_lines(caplog) == []


async def test_cancel_during_fail_missing_lane_sleep_leaves_no_lost_marker(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    stuck = StuckSleep()
    pump._publication_sleep = stuck
    lost = set()
    task = asyncio.ensure_future(pump._publish(make_lease(), {}, lost))
    for _ in range(50):
        if stuck.started:
            break
        await asyncio.sleep(0)
    assert stuck.started
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert lost == set()
    assert error_lines(caplog) == []


async def test_cancel_during_defer_held_lane_sleep_leaves_no_lost_marker(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a')])
    pump = make_pump(scheduler)
    stuck = StuckSleep()
    pump._publication_sleep = stuck
    lost = set()
    task = asyncio.ensure_future(
        pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, lost)
    )
    for _ in range(50):
        if stuck.started:
            break
        await asyncio.sleep(0)
    assert stuck.started
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert lost == set()
    assert error_lines(caplog) == []


async def test_plumbing_complete_success_uri_short_restricks_and_lands(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a')])
    pump = make_pump(scheduler)
    result = WorkResult('seg-1', 'gs://result', outcome='success')
    accepted = await pump._publish(make_lease(), {'seg-1': result}, set())
    assert accepted is True
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 2
    assert pump.sleeps.delays == [0.25]


async def test_plumbing_complete_success_uri_maxlen_restricks_and_lands(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a')])
    pump = make_pump(scheduler)
    result = WorkResult(
        'seg-1',
        'gs://b/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        outcome='success',
    )
    accepted = await pump._publish(make_lease(), {'seg-1': result}, set())
    assert accepted is True
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 2
    assert pump.sleeps.delays == [0.25]


async def test_plumbing_complete_silence_uri_short_restricks_and_lands(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a')])
    pump = make_pump(scheduler)
    result = WorkResult('seg-1', 'gs://result', outcome='silence')
    accepted = await pump._publish(make_lease(), {'seg-1': result}, set())
    assert accepted is True
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 2
    assert pump.sleeps.delays == [0.25]


async def test_plumbing_complete_silence_uri_maxlen_restricks_and_lands(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a')])
    pump = make_pump(scheduler)
    result = WorkResult(
        'seg-1',
        'gs://b/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        outcome='silence',
    )
    accepted = await pump._publish(make_lease(), {'seg-1': result}, set())
    assert accepted is True
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 2
    assert pump.sleeps.delays == [0.25]


async def test_state_complete_real_chain_loss_restricks_and_lands(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[chain_exhaustion])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is True
    assert lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [r for r in caplog.records if r.levelno == logging.ERROR and r.name == PUMP_LOGGER] == []


async def test_state_complete_real_chain_lane_cap_keeps_the_terminal_line(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[chain_exhaustion] * 4)
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is False
    assert lost == {"seg-1"}
    assert [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR and r.name == PUMP_LOGGER] == [
        "event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted"
    ]


async def test_state_complete_lane_events_are_info_only(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    restrikes = [r for r in caplog.records if 'restrike' in r.getMessage()]
    assert restrikes
    assert all(r.levelno == logging.INFO for r in restrikes)


async def test_state_complete_clean_publication_never_heartbeats(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    assert [c for c in scheduler.calls if c[0] == 'heartbeat'] == []


async def test_state_fail_validation_real_chain_loss_restricks_and_lands(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[chain_exhaustion])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        lost,
    )
    assert accepted is True
    assert lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [r for r in caplog.records if r.levelno == logging.ERROR and r.name == PUMP_LOGGER] == []


async def test_state_fail_validation_real_chain_lane_cap_keeps_the_terminal_line(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[chain_exhaustion] * 4)
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        lost,
    )
    assert accepted is False
    assert lost == {"seg-1"}
    assert [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR and r.name == PUMP_LOGGER] == [
        "event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted"
    ]


async def test_state_fail_validation_lane_events_are_info_only(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    restrikes = [r for r in caplog.records if 'restrike' in r.getMessage()]
    assert restrikes
    assert all(r.levelno == logging.INFO for r in restrikes)


async def test_state_fail_validation_clean_publication_never_heartbeats(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        set(),
    )
    assert [c for c in scheduler.calls if c[0] == 'heartbeat'] == []


async def test_state_fail_recovery_real_chain_loss_restricks_and_lands(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[chain_exhaustion])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, lost
    )
    assert accepted is True
    assert lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [r for r in caplog.records if r.levelno == logging.ERROR and r.name == PUMP_LOGGER] == []


async def test_state_fail_recovery_real_chain_lane_cap_keeps_the_terminal_line(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[chain_exhaustion] * 4)
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, lost
    )
    assert accepted is False
    assert lost == {"seg-1"}
    assert [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR and r.name == PUMP_LOGGER] == [
        "event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted"
    ]


async def test_state_fail_recovery_lane_events_are_info_only(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    restrikes = [r for r in caplog.records if 'restrike' in r.getMessage()]
    assert restrikes
    assert all(r.levelno == logging.INFO for r in restrikes)


async def test_state_fail_recovery_clean_publication_never_heartbeats(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, set()
    )
    assert [c for c in scheduler.calls if c[0] == 'heartbeat'] == []


async def test_state_fail_failed_real_chain_loss_restricks_and_lands(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[chain_exhaustion])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        lost,
    )
    assert accepted is True
    assert lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [r for r in caplog.records if r.levelno == logging.ERROR and r.name == PUMP_LOGGER] == []


async def test_state_fail_failed_real_chain_lane_cap_keeps_the_terminal_line(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[chain_exhaustion] * 4)
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        lost,
    )
    assert accepted is False
    assert lost == {"seg-1"}
    assert [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR and r.name == PUMP_LOGGER] == [
        "event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted"
    ]


async def test_state_fail_failed_lane_events_are_info_only(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    restrikes = [r for r in caplog.records if 'restrike' in r.getMessage()]
    assert restrikes
    assert all(r.levelno == logging.INFO for r in restrikes)


async def test_state_fail_failed_clean_publication_never_heartbeats(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[])
    pump = make_pump(scheduler)
    await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        set(),
    )
    assert [c for c in scheduler.calls if c[0] == 'heartbeat'] == []


async def test_state_fail_missing_real_chain_loss_restricks_and_lands(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[chain_exhaustion])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {}, lost)
    assert accepted is True
    assert lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [r for r in caplog.records if r.levelno == logging.ERROR and r.name == PUMP_LOGGER] == []


async def test_state_fail_missing_real_chain_lane_cap_keeps_the_terminal_line(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[chain_exhaustion] * 4)
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {}, lost)
    assert accepted is False
    assert lost == {"seg-1"}
    assert [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR and r.name == PUMP_LOGGER] == [
        "event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted"
    ]


async def test_state_fail_missing_lane_events_are_info_only(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    restrikes = [r for r in caplog.records if 'restrike' in r.getMessage()]
    assert restrikes
    assert all(r.levelno == logging.INFO for r in restrikes)


async def test_state_fail_missing_clean_publication_never_heartbeats(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {}, set())
    assert [c for c in scheduler.calls if c[0] == 'heartbeat'] == []


async def test_state_defer_held_real_chain_loss_restricks_and_lands(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[chain_exhaustion])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, lost)
    assert accepted is False
    assert lost == set()
    assert pump.sleeps.delays == [0.25]
    assert [r for r in caplog.records if r.levelno == logging.ERROR and r.name == PUMP_LOGGER] == []


async def test_state_defer_held_real_chain_lane_cap_keeps_the_terminal_line(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[chain_exhaustion] * 4)
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, lost)
    assert accepted is False
    assert lost == {"seg-1"}
    assert [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR and r.name == PUMP_LOGGER] == [
        "event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted"
    ]


async def test_state_defer_held_lane_events_are_info_only(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    restrikes = [r for r in caplog.records if 'restrike' in r.getMessage()]
    assert restrikes
    assert all(r.levelno == logging.INFO for r in restrikes)


async def test_state_defer_held_clean_publication_never_heartbeats(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, set())
    assert [c for c in scheduler.calls if c[0] == 'heartbeat'] == []


def chain_exhaustion(operation_name='synthetic_publication'):
    from database.firestore_transaction_retry import run_with_transaction_contention_retry

    def operation(tx):
        raise Aborted(f'{operation_name} commit contention')

    run_with_transaction_contention_retry(
        lambda: object(), operation, operation_name=operation_name, max_attempts=1, sleep=lambda seconds: None
    )
