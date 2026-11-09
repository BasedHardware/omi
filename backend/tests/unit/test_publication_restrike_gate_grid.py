"""Kill-switch and registration grid for BATCH_PIPELINE_PUBLICATION_RESTRIKE_ENABLED.

The gate is read at call time through the batch config module, defaults on, tolerates env noise like every sibling batch kill switch, and is registered in the pipeline flag budget under the batch record lane owner. With the gate off the publication catch site runs the legacy immediate fallback byte for byte.

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


from config.batch_pipeline import publication_restrike_enabled

ENV_CASES = [
    ('', True),
    ('true', True),
    ('True', True),
    ('TRUE', True),
    (' ', True),
    ('1', True),
    ('0', True),
    ('on', True),
    ('off', True),
    ('garbage', True),
    ('false', False),
    ('False', False),
    ('FALSE', False),
]


@pytest.mark.parametrize('value,expected', ENV_CASES)
def test_gate_env_value_matrix(monkeypatch, value, expected):
    monkeypatch.setenv(GATE, value)
    assert publication_restrike_enabled() is expected


def test_gate_defaults_on_when_unset(monkeypatch):
    monkeypatch.delenv(GATE, raising=False)
    assert publication_restrike_enabled() is True


def test_gate_is_stable_across_calls(monkeypatch):
    monkeypatch.setenv(GATE, 'false')
    assert publication_restrike_enabled() is False
    assert publication_restrike_enabled() is False


async def test_gate_off_complete_falls_back_immediately(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setenv(GATE, 'false')
    scheduler = ScriptScheduler(complete=[contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://result')}, lost)
    assert accepted is False
    assert lost == {"seg-1"}
    assert pump.sleeps.delays == []
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 1


async def test_gate_off_fail_validation_falls_back_immediately(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setenv(GATE, 'false')
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})},
        lost,
    )
    assert accepted is False
    assert lost == {"seg-1"}
    assert pump.sleeps.delays == []
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1


async def test_gate_off_fail_recovery_falls_back_immediately(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setenv(GATE, 'false')
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(), {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}, lost
    )
    assert accepted is False
    assert lost == {"seg-1"}
    assert pump.sleeps.delays == []
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1


async def test_gate_off_fail_failed_falls_back_immediately(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setenv(GATE, 'false')
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(
        make_lease(),
        {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})},
        lost,
    )
    assert accepted is False
    assert lost == {"seg-1"}
    assert pump.sleeps.delays == []
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1


async def test_gate_off_fail_missing_falls_back_immediately(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setenv(GATE, 'false')
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {}, lost)
    assert accepted is False
    assert lost == {"seg-1"}
    assert pump.sleeps.delays == []
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 1


async def test_gate_off_defer_held_falls_back_immediately(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    monkeypatch.setenv(GATE, 'false')
    scheduler = ScriptScheduler(defer=[contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}, lost)
    assert accepted is False
    assert lost == {"seg-1"}
    assert pump.sleeps.delays == []
    assert len([c for c in scheduler.calls if c[0] == 'defer']) == 1


def test_flag_budget_registers_the_gate_name():
    import json
    from pathlib import Path

    data = json.loads((Path(__file__).resolve().parents[2] / 'config' / 'flag_budget.json').read_text())
    assert GATE in data['names']


def test_flag_budget_entry_names_the_batch_lane_owner():
    import json
    import datetime
    from pathlib import Path

    data = json.loads((Path(__file__).resolve().parents[2] / 'config' / 'flag_budget.json').read_text())
    entry = data['names'][GATE]
    assert entry.get('owner') == 'batch record lane / rollout lead'
    review_by = datetime.date.fromisoformat(entry['review_by'])
    assert review_by >= datetime.date.today()


def test_flag_budget_count_matches_names():
    import json
    from pathlib import Path

    data = json.loads((Path(__file__).resolve().parents[2] / 'config' / 'flag_budget.json').read_text())
    assert data['count'] == len(data['names'])


def test_flag_budget_slots_match_the_budget():
    import json
    from pathlib import Path

    data = json.loads((Path(__file__).resolve().parents[2] / 'config' / 'flag_budget.json').read_text())
    slots = sum(1 for entry in data['names'].values() if 'seeded' in entry or 'replaces' in entry)
    assert slots == data['budget']


def test_config_source_reads_the_gate_name():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / 'config' / 'batch_pipeline.py').read_text()
    assert GATE in source
    assert 'FC-publication-contention-discards-completed-gpu-results' in source


def test_config_knob_wraps_rollout_default_on():
    import inspect

    source = inspect.getsource(publication_restrike_enabled)
    assert 'rollout_default_on' in source


def test_gate_is_deterministic_for_a_frozen_env(monkeypatch):
    monkeypatch.setenv(GATE, 'false')
    monkeypatch.setattr('config.batch_pipeline.rollout_default_on', lambda name, value: value)
    assert publication_restrike_enabled() is False


def test_pump_module_imports_the_knob():
    assert hasattr(pump_module, 'publication_restrike_enabled')


def test_gate_name_is_not_a_helper_kill_switch():
    import json
    from pathlib import Path

    data = json.loads((Path(__file__).resolve().parents[2] / 'config' / 'flag_budget.json').read_text())
    assert not data['names'][GATE].get('registry')


def test_gate_env_empty_value_reads_as_true_at_the_pump(monkeypatch):
    monkeypatch.setenv(GATE, '')
    assert pump_module.publication_restrike_enabled() is True


def test_gate_env_true_value_reads_as_true_at_the_pump(monkeypatch):
    monkeypatch.setenv(GATE, 'true')
    assert pump_module.publication_restrike_enabled() is True


def test_gate_env_true_value_reads_as_true_at_the_pump(monkeypatch):
    monkeypatch.setenv(GATE, 'True')
    assert pump_module.publication_restrike_enabled() is True


def test_gate_env_true_value_reads_as_true_at_the_pump(monkeypatch):
    monkeypatch.setenv(GATE, 'TRUE')
    assert pump_module.publication_restrike_enabled() is True


def test_gate_env_empty_value_reads_as_true_at_the_pump(monkeypatch):
    monkeypatch.setenv(GATE, ' ')
    assert pump_module.publication_restrike_enabled() is True


def test_gate_env_1_value_reads_as_true_at_the_pump(monkeypatch):
    monkeypatch.setenv(GATE, '1')
    assert pump_module.publication_restrike_enabled() is True


def test_gate_env_0_value_reads_as_true_at_the_pump(monkeypatch):
    monkeypatch.setenv(GATE, '0')
    assert pump_module.publication_restrike_enabled() is True


def test_gate_env_on_value_reads_as_true_at_the_pump(monkeypatch):
    monkeypatch.setenv(GATE, 'on')
    assert pump_module.publication_restrike_enabled() is True


def test_gate_env_off_value_reads_as_true_at_the_pump(monkeypatch):
    monkeypatch.setenv(GATE, 'off')
    assert pump_module.publication_restrike_enabled() is True


def test_gate_env_garbage_value_reads_as_true_at_the_pump(monkeypatch):
    monkeypatch.setenv(GATE, 'garbage')
    assert pump_module.publication_restrike_enabled() is True


def test_gate_env_false_value_reads_as_false_at_the_pump(monkeypatch):
    monkeypatch.setenv(GATE, 'false')
    assert pump_module.publication_restrike_enabled() is False


def test_gate_env_false_value_reads_as_false_at_the_pump(monkeypatch):
    monkeypatch.setenv(GATE, 'False')
    assert pump_module.publication_restrike_enabled() is False


def test_gate_env_false_value_reads_as_false_at_the_pump(monkeypatch):
    monkeypatch.setenv(GATE, 'FALSE')
    assert pump_module.publication_restrike_enabled() is False
