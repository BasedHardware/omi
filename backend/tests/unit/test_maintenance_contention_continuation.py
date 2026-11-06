"""Maintenance contention continuation (x180/30m ``batch_maintenance`` starvation family).

The worker's maintenance tick (``utils/batch_pipeline/pump.py`` ``_maintain``)
and the lease-expiry recovery loop it drives
(``utils/batch_pipeline/scheduler.py`` ``recover``) run independent steps and
per-item transactions in a fixed order. Before this suite's subject, the first
exhausted contention budget aborted the whole sweep at the failing step: the
prod signature ``event=batch_maintenance outcome=retry
exception_type=FirestoreContentionExhausted site=firestore_transaction_retry.py:``
(x180/30m) fired once per aborted sweep, and every abort meant the
``result_ready`` drain, the durable hold markers and every expired lease behind
the failing item were skipped for that tick — then re-struck 1 second later
from the top of the sweep while the hot document was still hot.

This suite pins the continuation contract:

1. Each leader-gated sweep step (projection, recover, the ``result_ready``
   page probe, its drain, the marked-hold page) runs under its own outcome: a
   lost step logs ``event=batch_maintenance outcome=retry step=<name>
   exception_type=<class> site=<file:line>`` and the remaining steps still run
   this sweep.
2. ``recover`` continues past a lost item: the item logs
   ``event=batch_recover outcome=retry scope=item ...`` and the leases behind
   it recover this pass; the legacy pre-loop migration logs ``scope=migrate``.
   Any non-contention exception still aborts the pass (fail-noisy).
3. The sweep cadence contract: the leader block completes even when steps
   lose, so ``_last_recovery`` updates and the next sweep waits out the
   5-second recovery interval instead of the legacy 1-second full-sweep
   re-strike. Metrics sampling keeps its own 15-second cadence.
4. ``BATCH_PIPELINE_MAINTENANCE_CONTINUATION_ENABLED=false`` restores the
   legacy behavior byte-for-byte: first failure aborts the sweep, the
   exception propagates, and ``_last_recovery`` stays unupdated.

Failure-Class: FC-immediate-retry-loses-shared-cas
"""

import ast
import copy
import datetime
import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.api_core.exceptions import Aborted

from config import batch_pipeline as config_batch_pipeline
from database.firestore_transaction_retry import (
    FirestoreContentionExhausted,
    run_with_transaction_contention_retry,
)
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.scheduler import Scheduler, owner_key
from utils.executors import db_executor

BACKEND = Path(__file__).resolve().parents[2]
GATE = 'BATCH_PIPELINE_MAINTENANCE_CONTINUATION_ENABLED'
STEP_LOSS_PATTERN = r'event=batch_maintenance outcome=retry step=(\S+) exception_type=(\w+) site=\w+\.py:\d+'
STEP_NAMES = ('projection', 'recover', 'ready_due', 'marked_page')


# --------------------------------------------------------------------------
# Harnesses
# --------------------------------------------------------------------------


def chain_exhaustion(operation_name='synthetic_chain'):
    """Raise a real FirestoreContentionExhausted from the production retry chain.

    Deliberately no try/except here: the exhaustion must propagate with its
    traceback ending in ``firestore_transaction_retry.py`` so the log site
    attribution contract is exercised against the real raise site.
    """

    def operation(tx):
        raise Aborted('synthetic commit contention')

    run_with_transaction_contention_retry(
        lambda: object(), operation, operation_name=operation_name, max_attempts=1, sleep=lambda seconds: None
    )


class ScriptStore:
    """Fake ``scheduler.store`` exposing the probe/due maintenance surface."""

    def __init__(self):
        self.due_calls = []
        self.due_script = []
        self.jobs = {}
        self.probe_calls = 0

    def due(self, state, now, limit):
        self.due_calls.append((state, now, limit))
        if self.due_script:
            step = self.due_script.pop(0)
            if isinstance(step, Exception):
                raise step
            return step
        return []

    def probe(self, table, key):
        self.probe_calls += 1
        value = self.jobs.get(key, {})
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)


class ScriptScheduler:
    """Fake scheduler with a scripted ``recover``."""

    def __init__(self, store=None):
        self.store = store or ScriptStore()
        self.recover_calls = 0
        self.recover_script = []
        self.recover_now = None

    def recover(self, now, limit=100):
        self.recover_calls += 1
        self.recover_now = now
        if self.recover_script:
            step = self.recover_script.pop(0)
            if isinstance(step, Exception):
                raise step
        return 0


class ChainScheduler(ScriptScheduler):
    """Loses exactly one recover call through the real production retry chain."""

    def __init__(self, store=None):
        super().__init__(store)
        self.losses_left = 1

    def recover(self, now, limit=100):
        self.recover_calls += 1
        self.recover_now = now
        if self.losses_left:
            self.losses_left -= 1
            chain_exhaustion('synthetic_batch_recover')
        return 0


class ScriptMerge:
    """Fake ordered merge exposing the hold-marker and drain surfaces."""

    def __init__(self):
        self.held_owners = set()
        self.drained = []
        self.marked_calls = []
        self.marked_script = []
        self.released = []
        self.commit_script = {}

    def marked_page(self, limit=50):
        self.marked_calls.append(limit)
        if self.marked_script:
            step = self.marked_script.pop(0)
            if isinstance(step, Exception):
                raise step
            return step
        return []

    def release_hold(self, key, *, force=False):
        self.released.append((key, force))

    def commit_next(self, owner_id, now):
        self.drained.append(owner_id)
        script = self.commit_script.get(owner_id) or []
        if script:
            step = script.pop(0)
            if isinstance(step, Exception):
                raise step
            return step
        return None


class ScriptLeader:
    def __init__(self, results=(), errors=()):
        self.calls = 0
        self.results = list(results)
        self.errors = list(errors)

    def acquire(self):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return self.results.pop(0) if self.results else True


class ScriptMetrics:
    def __init__(self):
        self.refreshes = 0

    def refresh(self, store, now):
        self.refreshes += 1


class ScriptShadow:
    def __init__(self, errors=()):
        self.calls = 0
        self.errors = list(errors)

    async def maintain(self):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)


class ScriptStep:
    """Callable step body with a scripted failure schedule."""

    def __init__(self, errors=()):
        self.calls = 0
        self.errors = list(errors)

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)


def make_pump(**overrides):
    scheduler = overrides.pop('scheduler', None) or ScriptScheduler()
    merge = overrides.pop('merge', None) or ScriptMerge()
    pump = Pump(
        scheduler,
        SimpleNamespace(),
        merge=merge,
        metrics=overrides.pop('metrics', None),
        project_pending=overrides.pop('project_pending', None),
        leader=overrides.pop('leader', None),
        inline_metrics=overrides.pop('inline_metrics', True),
        publish_concurrency=overrides.pop('publish_concurrency', 1),
        shadow=overrides.pop('shadow', None),
    )
    pump.merge.held_owners = set(overrides.pop('held_owners', ()))
    for name, value in overrides.items():
        setattr(pump, name, value)
    return pump


def continuation_env(monkeypatch, enabled):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'off')
    if enabled:
        monkeypatch.delenv(GATE, raising=False)
    else:
        monkeypatch.setenv(GATE, 'false')


@pytest.fixture(autouse=True)
def legacy_ring_append(monkeypatch):
    # Recover's requeue append has two queue encodings; pin the legacy ring so
    # these state-machine tests never depend on the FIFO-array conversion gate.
    monkeypatch.setattr('utils.batch_pipeline.scheduler.fifo_array_link_enabled', lambda: False)


# --------------------------------------------------------------------------
# Recover store harness: snapshot tx surface + per-run-ordinal failure script
# --------------------------------------------------------------------------


class RecoverTx:
    def __init__(self, rows):
        self.rows = rows

    def get(self, table, key):
        return copy.deepcopy(self.rows.get((table, key), {}))

    def put(self, table, key, value):
        self.rows[(table, key)] = copy.deepcopy(value)

    def patch(self, table, key, fields):
        self.rows.setdefault((table, key), {}).update(copy.deepcopy(fields))

    def check_privacy(self, uid, conversation_ids=(), expected_generation=None):
        return expected_generation or 0

    def service_frontier(self, priority):
        return 0.0


class RecoverStore:
    """Snapshot store over recover's tx surface; run ordinal k fails when scripted.

    ``fail_calls`` ordinals raise through the real production contention chain
    (so log site attribution points at ``firestore_transaction_retry.py``),
    unless ``fail_errors`` maps the ordinal to a different exception for the
    fail-noisy contracts.
    """

    def __init__(self):
        self.rows = {}
        self.fail_calls = set()
        self.fail_errors = {}
        self.run_calls = 0
        self.run_operations = []
        self.quarantined_fenced = []

    def run(self, body, *, operation=None):
        ordinal = self.run_calls
        self.run_calls += 1
        self.run_operations.append(operation)
        if ordinal in self.fail_calls:
            if ordinal in self.fail_errors:
                raise self.fail_errors[ordinal]
            chain_exhaustion(f'synthetic_ordinal_{ordinal}')
        snapshot = copy.deepcopy(self.rows)
        result = body(RecoverTx(snapshot))
        self.rows = snapshot
        return result

    def due(self, state, now, limit):
        field = 'lease_until' if state == 'leased' else 'available_at'
        return [
            key
            for (table, key), value in self.rows.items()
            if table == 'jobs' and value.get('state') == state and value.get(field, 0) <= now
        ][:limit]

    def probe(self, table, key):
        return copy.deepcopy(self.rows.get((table, key), {}))

    def quarantine_fenced(self, segment_id, now):
        self.quarantined_fenced.append(segment_id)


def retry_job(segment, owner='owner-a', available_at=0, priority=1):
    return {
        'segment_id': segment,
        'owner_id': owner,
        'owner_key': owner_key(owner),
        'state': 'retry',
        'available_at': available_at,
        'priority': priority,
        'duration_seconds': 3.0,
        'capture_at': 0.0,
        'attempt': 0,
    }


def leased_job(segment, owner='owner-a', lease_until=0, attempt=0):
    return {
        'segment_id': segment,
        'owner_id': owner,
        'owner_key': owner_key(owner),
        'state': 'leased',
        'lease_until': lease_until,
        'priority': 1,
        'duration_seconds': 3.0,
        'capture_at': 0.0,
        'attempt': attempt,
    }


def seed(store, *jobs):
    for job in jobs:
        store.rows[('jobs', job['segment_id'])] = copy.deepcopy(job)


def make_scheduler(store=None):
    return Scheduler(store or RecoverStore())


def recover_sweep(monkeypatch, enabled=True):
    continuation_env(monkeypatch, enabled)


# --------------------------------------------------------------------------
# Section 1: flag semantics
# --------------------------------------------------------------------------


def test_gate_defaults_on_without_env(monkeypatch):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'off')
    monkeypatch.delenv(GATE, raising=False)
    assert config_batch_pipeline.maintenance_contention_continuation_enabled() is True


@pytest.mark.parametrize('value', ['false', 'False', ' false ', 'FALSE'])
def test_gate_off_tokens(monkeypatch, value):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'off')
    monkeypatch.setenv(GATE, value)
    assert config_batch_pipeline.maintenance_contention_continuation_enabled() is False


@pytest.mark.parametrize('value', ['true', 'True', '0', 'yes', ' TRUE '])
def test_gate_on_tokens(monkeypatch, value):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'off')
    monkeypatch.setenv(GATE, value)
    assert config_batch_pipeline.maintenance_contention_continuation_enabled() is True


def test_gate_reads_env_at_call_time(monkeypatch):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'off')
    monkeypatch.delenv(GATE, raising=False)
    assert config_batch_pipeline.maintenance_contention_continuation_enabled() is True
    monkeypatch.setenv(GATE, 'false')
    assert config_batch_pipeline.maintenance_contention_continuation_enabled() is False
    monkeypatch.setenv(GATE, 'true')
    assert config_batch_pipeline.maintenance_contention_continuation_enabled() is True


def test_gate_helper_matches_the_damper_convention():
    source = (BACKEND / 'config' / 'batch_pipeline.py').read_text()
    assert ".strip().lower() != 'false'" in source


def test_flag_budget_declares_the_gate():
    data = json.loads((BACKEND / 'config' / 'flag_budget.json').read_text())
    entry = data['names'][GATE]
    assert entry.get('owner') == 'batch record lane / rollout lead'


def test_flag_budget_review_by_is_in_the_future():
    entry = json.loads((BACKEND / 'config' / 'flag_budget.json').read_text())['names'][GATE]
    assert datetime.date.fromisoformat(entry['review_by']) > datetime.date.today()


def test_flag_budget_count_matches_names():
    data = json.loads((BACKEND / 'config' / 'flag_budget.json').read_text())
    assert data['count'] == len(data['names'])


def test_pump_module_resolves_the_config_helper():
    source = (BACKEND / 'utils' / 'batch_pipeline' / 'pump.py').read_text()
    assert 'maintenance_contention_continuation_enabled' in source
    tree = ast.parse(source)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert 'maintenance_contention_continuation_enabled' in names


def test_scheduler_module_resolves_the_config_helper():
    source = (BACKEND / 'utils' / 'batch_pipeline' / 'scheduler.py').read_text()
    assert 'maintenance_contention_continuation_enabled' in source
    tree = ast.parse(source)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert 'maintenance_contention_continuation_enabled' in names


def test_worker_modules_never_read_the_gate_env_directly():
    for relative in ('utils/batch_pipeline/pump.py', 'utils/batch_pipeline/scheduler.py'):
        source = (BACKEND / relative).read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'getenv':
                assert GATE not in ast.literal_eval(node.args[0]), relative


# --------------------------------------------------------------------------
# Section 2: pump step isolation (gate on) — a lost step never suppresses siblings
# --------------------------------------------------------------------------


async def _sweep_with(pump):
    pump._last_recovery = 0.0
    await pump._maintain()


def step_losses(caplog):
    matched = []
    for record in caplog.records:
        match = re.search(STEP_LOSS_PATTERN, record.getMessage())
        if match:
            matched.append(match)
    return matched


async def test_recover_loss_leaves_the_ready_probe_running(monkeypatch, caplog):
    continuation_env(monkeypatch, True)
    pump = make_pump(scheduler=ChainScheduler())
    await _sweep_with(pump)
    assert len(pump.scheduler.store.due_calls) == 1


async def test_recover_loss_leaves_the_marked_page_running(monkeypatch, caplog):
    continuation_env(monkeypatch, True)
    pump = make_pump(scheduler=ChainScheduler())
    await _sweep_with(pump)
    assert pump.merge.marked_calls == [50]


async def test_recover_loss_leaves_the_held_reoffer_running(monkeypatch, caplog):
    continuation_env(monkeypatch, True)
    pump = make_pump(scheduler=ChainScheduler(), held_owners=('owner-x',))
    await _sweep_with(pump)
    assert pump.merge.drained == ['owner-x']


@pytest.mark.parametrize('error', [FirestoreContentionExhausted('storm'), TimeoutError('slow'), ValueError('bad')])
async def test_due_loss_leaves_recover_and_markers_running(monkeypatch, caplog, error):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    store.due_script = [error]
    pump = make_pump(scheduler=ScriptScheduler(store))
    await _sweep_with(pump)
    assert pump.scheduler.recover_calls == 1
    assert pump.merge.marked_calls == [50]
    assert [match.group(1) for match in step_losses(caplog)] == ['ready_due']


async def test_due_loss_skips_only_the_page_drain(monkeypatch, caplog):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    store.due_script = [FirestoreContentionExhausted('storm')]
    pump = make_pump(scheduler=ScriptScheduler(store))
    await _sweep_with(pump)
    assert store.probe_calls == 0
    assert pump.merge.marked_calls == [50]


@pytest.mark.parametrize('error', [FirestoreContentionExhausted('storm'), RuntimeError('boom')])
async def test_marked_page_loss_leaves_the_held_reoffer_running(monkeypatch, caplog, error):
    continuation_env(monkeypatch, True)
    pump = make_pump(held_owners=('owner-y',))
    pump.merge.marked_script = [error]
    await _sweep_with(pump)
    assert pump.merge.drained == ['owner-y']
    assert pump.merge.released == []


@pytest.mark.parametrize('error', [FirestoreContentionExhausted('storm'), KeyError('gone')])
async def test_projection_loss_leaves_recover_and_markers_running(monkeypatch, caplog, error):
    continuation_env(monkeypatch, True)
    pump = make_pump(project_pending=ScriptStep(errors=[error]))
    await _sweep_with(pump)
    assert pump.scheduler.recover_calls == 1
    assert pump.merge.marked_calls == [50]
    assert [match.group(1) for match in step_losses(caplog)] == ['projection']


async def test_marker_loss_leaves_later_markers_running(monkeypatch, caplog):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    pump.merge.marked_script = [[('key-1', 'owner-1'), ('key-2', None)]]
    pump.merge.commit_script['owner-1'] = [FirestoreContentionExhausted('hot owner doc')]
    await _sweep_with(pump)
    assert ('key-1', False) not in pump.merge.released
    assert ('key-2', True) in pump.merge.released


async def test_marker_drain_loss_keeps_the_release_unattempted_but_sweep_alive(monkeypatch, caplog):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    pump.merge.marked_script = [[('key-1', 'owner-1')]]
    pump.merge.commit_script['owner-1'] = [FirestoreContentionExhausted('hot owner doc')]
    await _sweep_with(pump)
    assert pump.merge.released == []
    records = [r for r in caplog.records if 'held_reoffer' in r.getMessage()]
    assert len(records) == 1
    assert 'scope=marker' in records[0].getMessage()


async def test_page_drain_loss_keeps_the_marked_page_running(monkeypatch, caplog):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    store.due_script = [['seg-1', 'seg-2']]
    store.jobs['seg-1'] = {'owner_id': 'owner-1'}
    store.jobs['seg-2'] = {'owner_id': 'owner-2'}
    pump = make_pump(scheduler=ScriptScheduler(store))
    pump.merge.commit_script['owner-1'] = [FirestoreContentionExhausted('hot')]
    await _sweep_with(pump)
    assert pump.merge.marked_calls == [50]
    records = [r for r in caplog.records if 'held_reoffer' in r.getMessage()]
    assert any('scope=ready_page' in r.getMessage() for r in records)


async def test_shadow_loss_never_touches_the_leader_steps(monkeypatch, caplog):
    continuation_env(monkeypatch, True)
    shadow = ScriptShadow(errors=[RuntimeError('shadow noise')])
    step = ScriptStep()
    pump = make_pump(shadow=shadow, project_pending=step)
    await _sweep_with(pump)
    assert shadow.calls == 1
    assert step.calls == 1
    assert pump.scheduler.recover_calls == 1


async def test_leader_acquire_loss_fails_the_tick_but_not_a_step_failure(monkeypatch):
    continuation_env(monkeypatch, True)
    leader = ScriptLeader(errors=[FirestoreContentionExhausted('lease lost')])
    step = ScriptStep()
    pump = make_pump(leader=leader, project_pending=step)
    with pytest.raises(FirestoreContentionExhausted):
        await _sweep_with(pump)
    # The gate itself is not a step behind the gate: the gated steps never ran.
    assert step.calls == 0
    assert pump.scheduler.recover_calls == 0


async def test_leader_decline_skips_gated_steps_but_reoffers_held_owners(monkeypatch):
    continuation_env(monkeypatch, True)
    leader = ScriptLeader(results=[False])
    step = ScriptStep()
    pump = make_pump(leader=leader, project_pending=step, held_owners=('owner-z',))
    await _sweep_with(pump)
    assert step.calls == 0
    assert pump.scheduler.recover_calls == 0
    assert pump.merge.drained == ['owner-z']
    assert pump._last_recovery > 0


async def test_every_step_losing_still_completes_the_sweep(monkeypatch, caplog):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    store.due_script = [FirestoreContentionExhausted('a')]
    pump = make_pump(
        scheduler=ScriptScheduler(store),
        project_pending=ScriptStep(errors=[RuntimeError('p')]),
        held_owners=('owner-w',),
    )
    pump.scheduler.recover_script = [FirestoreContentionExhausted('r')]
    pump.merge.marked_script = [ValueError('m')]
    await _sweep_with(pump)
    assert pump.merge.drained == ['owner-w']
    assert pump._last_recovery > 0
    assert [match.group(1) for match in step_losses(caplog)] == list(STEP_NAMES)


# --------------------------------------------------------------------------
# Section 3: step telemetry contracts
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('step_name', 'error'),
    [
        ('projection', RuntimeError('p')),
        ('recover', FirestoreContentionExhausted('r')),
        ('ready_due', TimeoutError('d')),
        ('marked_page', ValueError('m')),
    ],
)
async def test_step_loss_message_names_the_step_and_exception(monkeypatch, caplog, step_name, error):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    pump = make_pump(scheduler=ScriptScheduler(store), project_pending=ScriptStep())
    if step_name == 'projection':
        pump.project_pending.errors = [error]
    elif step_name == 'recover':
        pump.scheduler.recover_script = [error]
    elif step_name == 'ready_due':
        store.due_script = [error]
    else:
        pump.merge.marked_script = [error]
    await _sweep_with(pump)
    matched = [match for match in step_losses(caplog) if match.group(1) == step_name]
    assert len(matched) == 1
    assert matched[0].group(2) == type(error).__name__


def test_step_names_are_the_documented_closed_set():
    assert STEP_NAMES == ('projection', 'recover', 'ready_due', 'marked_page')


@pytest.mark.parametrize(
    'error',
    [FirestoreContentionExhausted('storm'), TimeoutError('slow'), ValueError('bad'), RuntimeError('boom')],
)
async def test_step_loss_reports_the_exception_class(monkeypatch, caplog, error):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    pump.scheduler.recover_script = [error]
    await _sweep_with(pump)
    records = [r for r in caplog.records if 'step=recover' in r.getMessage()]
    assert len(records) == 1
    assert f'exception_type={type(error).__name__}' in records[0].getMessage()
    assert records[0].levelname == 'ERROR'


async def test_step_loss_carries_a_static_site_field(monkeypatch, caplog):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    pump.scheduler.recover_script = [FirestoreContentionExhausted('storm')]
    await _sweep_with(pump)
    record = [r for r in caplog.records if 'step=recover' in r.getMessage()][0]
    assert re.search(r'site=\w+\.py:\d+', record.getMessage())


async def test_contention_loss_sites_point_into_the_retry_chain(monkeypatch, caplog):
    continuation_env(monkeypatch, True)
    pump = make_pump(scheduler=ChainScheduler())
    await _sweep_with(pump)
    record = [r for r in caplog.records if 'step=recover' in r.getMessage()][0]
    assert 'site=firestore_transaction_retry.py:' in record.getMessage()


async def test_successful_steps_log_nothing(monkeypatch, caplog):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    pump = make_pump(scheduler=ScriptScheduler(store), project_pending=ScriptStep())
    await _sweep_with(pump)
    batch_records = [r for r in caplog.records if 'event=batch_maintenance' in r.getMessage()]
    assert batch_records == []


async def test_step_loss_logs_carry_no_segment_or_owner_data(monkeypatch, caplog):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    store.due_script = [['secret-segment-id']]
    store.jobs['secret-segment-id'] = {'owner_id': 'secret-owner'}
    pump = make_pump(scheduler=ScriptScheduler(store))
    pump.scheduler.recover_script = [FirestoreContentionExhausted('storm')]
    await _sweep_with(pump)
    for record in caplog.records:
        if 'event=batch_maintenance' in record.getMessage():
            assert 'secret-segment-id' not in record.getMessage()
            assert 'secret-owner' not in record.getMessage()


async def test_step_loss_never_reaches_the_loop_level_log(monkeypatch, caplog):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    pump.scheduler.recover_script = [FirestoreContentionExhausted('storm')]
    await _sweep_with(pump)
    legacy = [
        r.getMessage()
        for r in caplog.records
        if 'event=batch_maintenance outcome=retry' in r.getMessage() and 'step=' not in r.getMessage()
    ]
    assert legacy == []


@pytest.mark.parametrize('step_name', STEP_NAMES)
async def test_each_isolated_step_has_its_own_stable_name(monkeypatch, caplog, step_name):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    pump = make_pump(scheduler=ScriptScheduler(store), project_pending=ScriptStep())
    if step_name == 'projection':
        pump.project_pending.errors = [RuntimeError('p')]
    elif step_name == 'recover':
        pump.scheduler.recover_script = [RuntimeError('r')]
    elif step_name == 'ready_due':
        store.due_script = [RuntimeError('d')]
    else:
        pump.merge.marked_script = [RuntimeError('m')]
    await _sweep_with(pump)
    assert [match.group(1) for match in step_losses(caplog)] == [step_name]


# --------------------------------------------------------------------------
# Section 4: sweep cadence and _last_recovery
# --------------------------------------------------------------------------


async def test_completed_sweep_updates_the_recovery_clock_even_when_steps_lost(monkeypatch):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    pump.scheduler.recover_script = [FirestoreContentionExhausted('storm')]
    await _sweep_with(pump)
    assert pump._last_recovery > 0


async def test_lost_steps_wait_for_the_next_sweep_instead_of_a_1s_restrike(monkeypatch):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    pump.scheduler.recover_script = [FirestoreContentionExhausted('storm')]
    await _sweep_with(pump)
    first_clock = pump._last_recovery
    await pump._maintain()  # a loop tick inside the 5s recovery interval
    assert pump.scheduler.recover_calls == 1
    assert pump._last_recovery == first_clock


async def test_failed_step_reruns_at_the_next_sweep(monkeypatch):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    pump.scheduler.recover_script = [FirestoreContentionExhausted('storm')]
    await _sweep_with(pump)
    pump._last_recovery = 0.0  # >=5s elapsed
    await pump._maintain()
    assert pump.scheduler.recover_calls == 2


async def test_metrics_cadence_is_independent_of_step_losses(monkeypatch):
    continuation_env(monkeypatch, True)
    metrics = ScriptMetrics()
    pump = make_pump(metrics=metrics)
    pump.scheduler.recover_script = [FirestoreContentionExhausted('storm')]
    pump._last_metrics = 0.0
    await pump._maintain()
    assert metrics.refreshes == 1
    assert pump._last_metrics > 0


async def test_metrics_cadence_holds_its_own_15s_interval(monkeypatch):
    continuation_env(monkeypatch, True)
    metrics = ScriptMetrics()
    pump = make_pump(metrics=metrics)
    pump._last_metrics = 0.0
    await pump._maintain()
    first = pump._last_metrics
    await pump._maintain()  # inside the 15s metrics interval
    assert metrics.refreshes == 1
    assert pump._last_metrics == first


async def test_inline_metrics_off_never_samples(monkeypatch):
    continuation_env(monkeypatch, True)
    metrics = ScriptMetrics()
    pump = make_pump(metrics=metrics, inline_metrics=False)
    pump._last_metrics = 0.0
    await pump._maintain()
    assert metrics.refreshes == 0


async def test_recovery_interval_gates_the_whole_leader_block(monkeypatch):
    continuation_env(monkeypatch, True)
    step = ScriptStep()
    pump = make_pump(project_pending=step)
    await _sweep_with(pump)
    assert step.calls == 1
    await pump._maintain()  # inside the 5s interval
    assert step.calls == 1


async def test_legacy_abort_keeps_the_recovery_clock_unupdated(monkeypatch):
    continuation_env(monkeypatch, False)
    pump = make_pump()
    pump.scheduler.recover_script = [FirestoreContentionExhausted('storm')]
    with pytest.raises(FirestoreContentionExhausted):
        await _sweep_with(pump)
    assert pump._last_recovery == 0.0


async def test_legacy_success_updates_the_recovery_clock(monkeypatch):
    continuation_env(monkeypatch, False)
    pump = make_pump()
    await _sweep_with(pump)
    assert pump._last_recovery > 0


# --------------------------------------------------------------------------
# Section 5: legacy parity (gate off) — abort-at-first-failure semantics
# --------------------------------------------------------------------------


@pytest.mark.parametrize('error', [FirestoreContentionExhausted('storm'), ValueError('bug')])
async def test_legacy_projection_loss_aborts_before_recover(monkeypatch, error):
    continuation_env(monkeypatch, False)
    pump = make_pump(project_pending=ScriptStep(errors=[error]))
    with pytest.raises(Exception) as excinfo:
        await _sweep_with(pump)
    assert excinfo.value is error
    assert pump.scheduler.recover_calls == 0
    assert pump.merge.marked_calls == []


async def test_legacy_recover_loss_aborts_before_the_ready_probe(monkeypatch):
    continuation_env(monkeypatch, False)
    pump = make_pump()
    pump.scheduler.recover_script = [FirestoreContentionExhausted('storm')]
    with pytest.raises(FirestoreContentionExhausted):
        await _sweep_with(pump)
    assert pump.scheduler.store.due_calls == []
    assert pump.merge.marked_calls == []


async def test_legacy_due_loss_aborts_before_the_marked_page(monkeypatch):
    continuation_env(monkeypatch, False)
    store = ScriptStore()
    store.due_script = [FirestoreContentionExhausted('storm')]
    pump = make_pump(scheduler=ScriptScheduler(store))
    with pytest.raises(FirestoreContentionExhausted):
        await _sweep_with(pump)
    assert pump.merge.marked_calls == []
    assert pump.merge.drained == []


@pytest.mark.parametrize('error', [FirestoreContentionExhausted('storm'), KeyError('gone')])
async def test_legacy_marked_page_loss_aborts_before_the_held_reoffer(monkeypatch, error):
    continuation_env(monkeypatch, False)
    pump = make_pump(held_owners=('owner-q',))
    pump.merge.marked_script = [error]
    with pytest.raises(Exception) as excinfo:
        await _sweep_with(pump)
    assert excinfo.value is error
    assert pump.merge.drained == []


async def test_legacy_marker_loss_stays_scoped_to_its_marker(monkeypatch):
    continuation_env(monkeypatch, False)
    pump = make_pump()
    pump.merge.marked_script = [[('key-1', 'owner-1'), ('key-2', None)]]
    pump.merge.commit_script['owner-1'] = [FirestoreContentionExhausted('hot')]
    await _sweep_with(pump)
    assert ('key-2', True) in pump.merge.released


async def test_legacy_and_continuation_run_the_same_step_order_without_failures(monkeypatch):
    for enabled in (True, False):
        continuation_env(monkeypatch, enabled)
        order = []

        class OrderedScheduler(ScriptScheduler):
            def recover(self, now, limit=100):
                order.append('recover')
                return 0

        store = ScriptStore()
        merge = ScriptMerge()
        merge.marked_script = [[('key-1', None)]]
        pump = make_pump(
            scheduler=OrderedScheduler(store),
            merge=merge,
            project_pending=ScriptStep(),
            held_owners=('owner-h',),
        )
        await _sweep_with(pump)
        assert order == ['recover']
        assert merge.drained == ['owner-h']


async def test_gate_flip_midflight_switches_the_abort_contract(monkeypatch):
    pump = make_pump()
    continuation_env(monkeypatch, True)
    pump.scheduler.recover_script = [FirestoreContentionExhausted('storm')]
    await _sweep_with(pump)
    assert pump.scheduler.store.due_calls
    continuation_env(monkeypatch, False)
    pump.scheduler.recover_script = [FirestoreContentionExhausted('storm again')]
    pump.scheduler.store.due_calls.clear()
    with pytest.raises(FirestoreContentionExhausted):
        await _sweep_with(pump)
    assert pump.scheduler.store.due_calls == []


# --------------------------------------------------------------------------
# Section 6: recover continuation (gate on)
# --------------------------------------------------------------------------


async def test_recover_continues_past_a_lost_middle_item(monkeypatch, caplog):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a'), retry_job('b'), retry_job('c'), retry_job('d'))
    store.fail_calls = {2}  # item 'b': run call 0 is the migration
    assert make_scheduler(store).recover(100) == 3
    assert store.rows[('jobs', 'b')]['state'] == 'retry'
    for segment in ('a', 'c', 'd'):
        assert store.rows[('jobs', segment)]['state'] == 'ready'
    warnings = [r.getMessage() for r in caplog.records if 'event=batch_recover outcome=retry' in r.getMessage()]
    assert len(warnings) == 1
    assert 'scope=item' in warnings[0]


async def test_recover_continues_past_a_lost_first_item(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a'), retry_job('b'))
    store.fail_calls = {1}
    assert make_scheduler(store).recover(100) == 1
    assert store.rows[('jobs', 'a')]['state'] == 'retry'
    assert store.rows[('jobs', 'b')]['state'] == 'ready'


async def test_recover_continues_past_a_lost_last_item(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a'), retry_job('b'))
    store.fail_calls = {2}
    assert make_scheduler(store).recover(100) == 1
    assert store.rows[('jobs', 'b')]['state'] == 'retry'


async def test_recover_counts_only_landed_transitions(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a'), retry_job('b'), retry_job('c'))
    store.fail_calls = {2}
    assert make_scheduler(store).recover(100) == 2


async def test_recover_skipped_item_stays_due_for_the_next_pass(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a', available_at=0), retry_job('b', available_at=0))
    store.fail_calls = {1}
    make_scheduler(store).recover(100)
    assert store.rows[('jobs', 'a')]['available_at'] == 0
    assert store.due('retry', 100, 100) == ['a']


async def test_recover_migrate_loss_leaves_the_items_running(monkeypatch, caplog):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a'))
    store.fail_calls = {0}
    assert make_scheduler(store).recover(100) == 1
    warnings = [r.getMessage() for r in caplog.records if 'event=batch_recover outcome=retry' in r.getMessage()]
    assert len(warnings) == 1
    assert 'scope=migrate' in warnings[0]


async def test_recover_non_contention_failure_still_aborts_the_pass(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a'), retry_job('b'))
    store.fail_calls = {1}
    store.fail_errors = {1: KeyError('real bug')}
    with pytest.raises(KeyError):
        make_scheduler(store).recover(100)
    assert store.rows[('jobs', 'b')]['state'] == 'retry'


async def test_recover_runs_every_item_under_the_batch_recover_label(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a'), retry_job('b'))
    make_scheduler(store).recover(100)
    # The migration entry passes no explicit operation= and rides the ambient
    # store_operation('batch_recover') label; both item entries are explicit.
    assert store.run_operations == [None, 'batch_recover', 'batch_recover']


async def test_recover_honors_the_due_limit(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, *[retry_job(f's{i}') for i in range(5)])
    make_scheduler(store).recover(100, limit=3)
    landed = [key for (table, key), value in store.rows.items() if table == 'jobs' and value['state'] == 'ready']
    assert len(landed) == 3


async def test_recover_leased_item_loss_skips_only_that_item(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, leased_job('l1'), leased_job('l2'))
    store.fail_calls = {1}
    assert make_scheduler(store).recover(100) == 1
    assert store.rows[('jobs', 'l1')]['state'] == 'leased'
    assert store.rows[('jobs', 'l2')]['state'] != 'leased'


async def test_recover_requeued_retry_item_reaches_the_ready_queue(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a'))
    make_scheduler(store).recover(100)
    job = store.rows[('jobs', 'a')]
    assert job['state'] == 'ready'
    queue = store.rows[('queues', f"1_{job['owner_key']}")]
    assert queue['head'] == 'a'
    assert queue['tail'] == 'a'


async def test_recover_two_owners_append_distinct_queue_heads(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a', owner='owner-1'), retry_job('b', owner='owner-2'))
    make_scheduler(store).recover(100)
    assert store.rows[('queues', f"1_{owner_key('owner-1')}")]['head'] == 'a'
    assert store.rows[('queues', f"1_{owner_key('owner-2')}")]['head'] == 'b'


async def test_recover_second_append_links_the_chain_through_the_tail(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a', owner='owner-1'), retry_job('b', owner='owner-1'))
    make_scheduler(store).recover(100)
    queue = store.rows[('queues', f"1_{owner_key('owner-1')}")]
    assert queue['head'] == 'a'
    assert queue['tail'] == 'b'
    assert store.rows[('jobs', 'a')]['next'] == 'b'
    assert store.rows[('jobs', 'b')]['next'] == ''


async def test_recover_order_is_leased_before_retry(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('r1'), leased_job('l1'))
    seen = []

    class SpyTx(RecoverTx):
        def get(self, table, key):
            if table == 'jobs' and key not in seen:
                seen.append(key)
            return super().get(table, key)

    original_run = RecoverStore.run

    def spy_run(self, body, *, operation=None):
        ordinal = self.run_calls
        self.run_calls += 1
        self.run_operations.append(operation)
        if ordinal in self.fail_calls:
            chain_exhaustion(f'synthetic_ordinal_{ordinal}')
        snapshot = copy.deepcopy(self.rows)
        result = body(SpyTx(snapshot))
        self.rows = snapshot
        return result

    store.run = spy_run.__get__(store, RecoverStore)
    try:
        make_scheduler(store).recover(100)
    finally:
        RecoverStore.run = original_run
    assert seen[0] == 'l1'
    assert seen[1] == 'r1'


async def test_recover_expired_leased_item_defers_into_retry_under_off_mode(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, leased_job('l1', attempt=0))
    make_scheduler(store).recover(100)
    assert store.rows[('jobs', 'l1')]['state'] == 'retry'


async def test_recover_attempt_exhausted_leased_item_quarantines_under_serving_mode(monkeypatch):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    monkeypatch.delenv(GATE, raising=False)
    store = RecoverStore()
    seed(store, leased_job('l1', attempt=99))
    make_scheduler(store).recover(100)
    assert store.rows[('jobs', 'l1')]['state'] == 'quarantined'
    assert store.rows[('jobs', 'l1')]['recovery_state'] == 'held'
    assert store.rows[('jobs', 'l1')]['quarantine_reason'] == 'worker_failed'


async def test_recover_mixed_leased_and_retry_items_recover_across_states(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, leased_job('l1'), retry_job('r1'), leased_job('l2'))
    store.fail_calls = {2}  # the second leased item
    assert make_scheduler(store).recover(100) == 2
    assert store.rows[('jobs', 'l1')]['state'] == 'retry'
    assert store.rows[('jobs', 'l2')]['state'] == 'leased'
    assert store.rows[('jobs', 'r1')]['state'] == 'ready'


# --------------------------------------------------------------------------
# Section 7: recover legacy parity (gate off)
# --------------------------------------------------------------------------


async def test_legacy_recover_item_loss_aborts_the_pass(monkeypatch):
    recover_sweep(monkeypatch, enabled=False)
    store = RecoverStore()
    seed(store, retry_job('a'), retry_job('b'))
    store.fail_calls = {1}
    with pytest.raises(FirestoreContentionExhausted):
        make_scheduler(store).recover(100)
    assert store.rows[('jobs', 'b')]['state'] == 'retry'


async def test_legacy_recover_migrate_loss_aborts_before_any_item(monkeypatch):
    recover_sweep(monkeypatch, enabled=False)
    store = RecoverStore()
    seed(store, retry_job('a'))
    store.fail_calls = {0}
    with pytest.raises(FirestoreContentionExhausted):
        make_scheduler(store).recover(100)
    assert store.run_calls == 1
    assert store.rows[('jobs', 'a')]['state'] == 'retry'


async def test_legacy_recover_without_failures_lands_every_item(monkeypatch):
    recover_sweep(monkeypatch, enabled=False)
    store = RecoverStore()
    seed(store, retry_job('a'), retry_job('b'), retry_job('c'))
    assert make_scheduler(store).recover(100) == 3


# --------------------------------------------------------------------------
# Section 8: recover telemetry
# --------------------------------------------------------------------------


async def test_recover_item_loss_logs_a_warning_with_site(monkeypatch, caplog):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a'), retry_job('b'))
    store.fail_calls = {1}
    make_scheduler(store).recover(100)
    record = [r for r in caplog.records if 'scope=item' in r.getMessage()][0]
    assert record.levelname == 'WARNING'
    assert re.search(r'site=\w+\.py:\d+', record.getMessage())
    assert 'firestore_transaction_retry.py' in record.getMessage()


async def test_recover_item_loss_names_the_exception_class(monkeypatch, caplog):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a'))
    store.fail_calls = {1}
    make_scheduler(store).recover(100)
    record = [r for r in caplog.records if 'scope=item' in r.getMessage()][0]
    assert 'exception_type=FirestoreContentionExhausted' in record.getMessage()


async def test_recover_item_loss_logs_carry_no_segment_identity(monkeypatch, caplog):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('classified-segment'))
    store.fail_calls = {1}
    make_scheduler(store).recover(100)
    for record in caplog.records:
        if 'event=batch_recover outcome=retry' in record.getMessage():
            assert 'classified-segment' not in record.getMessage()


async def test_recover_migrate_and_item_losses_are_distinguishable(monkeypatch, caplog):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a'), retry_job('b'))
    store.fail_calls = {0, 1}
    make_scheduler(store).recover(100)
    scopes = [
        r.getMessage().split('scope=')[1].split()[0]
        for r in caplog.records
        if 'event=batch_recover outcome=retry' in r.getMessage()
    ]
    assert scopes == ['migrate', 'item']


# --------------------------------------------------------------------------
# Section 9: marker / held micro-contracts (continuation on)
# --------------------------------------------------------------------------


async def test_marker_with_owner_drains_before_release(monkeypatch):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    pump.merge.marked_script = [[('key-1', 'owner-1')]]
    await _sweep_with(pump)
    assert pump.merge.drained == ['owner-1']
    assert pump.merge.released == [('key-1', False)]


async def test_marker_without_owner_force_releases_without_a_drain(monkeypatch):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    pump.merge.marked_script = [[('key-1', None)]]
    await _sweep_with(pump)
    assert pump.merge.drained == []
    assert pump.merge.released == [('key-1', True)]


async def test_markers_process_in_page_order(monkeypatch):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    pump.merge.marked_script = [[('k1', 'o1'), ('k2', 'o2'), ('k3', None)]]
    await _sweep_with(pump)
    assert pump.merge.drained == ['o1', 'o2']
    assert pump.merge.released == [('k1', False), ('k2', False), ('k3', True)]


async def test_held_owners_reoffer_drains_each_owner_once(monkeypatch):
    continuation_env(monkeypatch, True)
    pump = make_pump(held_owners=('o1', 'o2'))
    await _sweep_with(pump)
    assert sorted(pump.merge.drained) == ['o1', 'o2']


async def test_held_reoffer_survives_a_drain_loss(monkeypatch, caplog):
    continuation_env(monkeypatch, True)
    pump = make_pump(held_owners=('o1',))
    pump.merge.commit_script['o1'] = [FirestoreContentionExhausted('hot')]
    await _sweep_with(pump)
    records = [r for r in caplog.records if 'held_reoffer' in r.getMessage()]
    assert len(records) == 1
    assert 'scope=held' in records[0].getMessage()


async def test_held_reoffer_snapshot_iterates_even_when_drains_mutate_the_set(monkeypatch):
    continuation_env(monkeypatch, True)

    class MutatingMerge(ScriptMerge):
        def commit_next(self, owner_id, now):
            self.drained.append(owner_id)
            self.held_owners.discard(owner_id)
            return None

    pump = make_pump(merge=MutatingMerge(), held_owners=('o1', 'o2', 'o3'))
    await _sweep_with(pump)
    # The snapshot list is taken up front, so every held owner drains exactly
    # once even though each drain removes itself from the live set.
    assert sorted(pump.merge.drained) == ['o1', 'o2', 'o3']


async def test_ready_page_drains_one_owner_per_first_seen_owner(monkeypatch):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    store.due_script = [['s1', 's2', 's3']]
    store.jobs['s1'] = {'owner_id': 'o1'}
    store.jobs['s2'] = {'owner_id': 'o1'}
    store.jobs['s3'] = {'owner_id': 'o2'}
    pump = make_pump(scheduler=ScriptScheduler(store))
    await _sweep_with(pump)
    assert pump.merge.drained == ['o1', 'o2']


async def test_ready_page_segments_without_an_owner_are_skipped(monkeypatch):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    store.due_script = [['s1']]
    store.jobs['s1'] = {}
    pump = make_pump(scheduler=ScriptScheduler(store))
    await _sweep_with(pump)
    assert pump.merge.drained == []


async def test_ready_drain_reuses_the_owner_memo_across_sweeps(monkeypatch):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    store.due_script = [['s1']]
    store.jobs['s1'] = {'owner_id': 'o1'}
    pump = make_pump(scheduler=ScriptScheduler(store), publish_concurrency=2)
    await _sweep_with(pump)
    probes_after_first = store.probe_calls
    assert probes_after_first == 1
    pump._last_recovery = 0.0
    store.due_script = [['s1']]
    await pump._maintain()
    assert store.probe_calls == probes_after_first


# --------------------------------------------------------------------------
# Section 10: ordering, composition and limits
# --------------------------------------------------------------------------


async def test_step_order_is_recover_due_markers_held(monkeypatch):
    continuation_env(monkeypatch, True)
    order = []

    class OrderedScheduler(ScriptScheduler):
        def recover(self, now, limit=100):
            order.append('recover')
            return 0

    class OrderedStore(ScriptStore):
        def due(self, state, now, limit):
            order.append('due')
            return []

    class OrderedMerge(ScriptMerge):
        def marked_page(self, limit=50):
            order.append('marked')
            return []

        def commit_next(self, owner_id, now):
            order.append('held')
            return None

    pump = make_pump(scheduler=OrderedScheduler(OrderedStore()), merge=OrderedMerge(), held_owners=('o1',))
    await _sweep_with(pump)
    assert order == ['recover', 'due', 'marked', 'held']


async def test_projection_runs_before_recover(monkeypatch):
    continuation_env(monkeypatch, True)
    seen = []

    class SpyScheduler(ScriptScheduler):
        def recover(self, now, limit=100):
            seen.append('recover')
            return 0

    def spy_step():
        seen.append('projection')

    pump = make_pump(scheduler=SpyScheduler(), project_pending=spy_step)
    await _sweep_with(pump)
    assert seen == ['projection', 'recover']


async def test_due_probe_arguments_are_result_ready_with_limit_100(monkeypatch):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    pump = make_pump(scheduler=ScriptScheduler(store))
    await _sweep_with(pump)
    assert len(store.due_calls) == 1
    state, _now, limit = store.due_calls[0]
    assert state == 'result_ready'
    assert limit == 100
    assert isinstance(_now, float)


async def test_marked_page_limit_is_50(monkeypatch):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    await _sweep_with(pump)
    assert pump.merge.marked_calls == [50]


async def test_recover_receives_a_current_wall_clock(monkeypatch):
    import time as time_module

    continuation_env(monkeypatch, True)
    pump = make_pump()
    before = time_module.time()
    await _sweep_with(pump)
    assert before <= pump.scheduler.recover_now <= time_module.time()


async def test_absent_project_pending_skips_the_step_cleanly(monkeypatch):
    continuation_env(monkeypatch, True)
    pump = make_pump(project_pending=None)
    await _sweep_with(pump)
    assert pump.scheduler.recover_calls == 1


async def test_drain_ready_probes_every_due_page_segment(monkeypatch):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    page = ['s1', 's2']
    store.due_script = [page]
    store.jobs['s1'] = {'owner_id': 'o1'}
    store.jobs['s2'] = {'owner_id': 'o2'}
    pump = make_pump(scheduler=ScriptScheduler(store))
    await _sweep_with(pump)
    assert store.probe_calls == len(page)


async def test_maintenance_step_helper_returns_the_step_result(monkeypatch):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    store = ScriptStore()
    store.due_script = [['s1']]
    result = await pump._maintenance_step('ready_due', 'maintenance', None, store.due, 'result_ready', 0, 100)
    assert result == ['s1']


async def test_maintenance_step_helper_returns_none_on_loss(monkeypatch):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    result = await pump._maintenance_step(
        'recover', 'maintenance', None, ScriptStep(errors=[FirestoreContentionExhausted('x')])
    )
    assert result is None


# --------------------------------------------------------------------------
# Section 11: storm schedules
# --------------------------------------------------------------------------


async def test_recover_losing_every_sweep_never_starves_the_ready_drain(monkeypatch):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    for _ in range(5):
        pump._last_recovery = 0.0
        pump.scheduler.recover_script = [FirestoreContentionExhausted('storm')]
        await pump._maintain()
    assert len(pump.scheduler.store.due_calls) == 5
    assert pump.merge.marked_calls == [50] * 5


async def test_alternating_loss_and_recovery_schedule(monkeypatch):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    for sweep in range(4):
        pump._last_recovery = 0.0
        if sweep % 2 == 0:
            pump.scheduler.recover_script = [FirestoreContentionExhausted('storm')]
        await pump._maintain()
    assert pump.scheduler.recover_calls == 4
    assert pump._last_recovery > 0


async def test_two_steps_losing_the_same_sweep_both_get_their_own_outcome(monkeypatch, caplog):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    store.due_script = [TimeoutError('d')]
    pump = make_pump(
        scheduler=ScriptScheduler(store),
        project_pending=ScriptStep(errors=[RuntimeError('p')]),
    )
    pump.scheduler.recover_script = [FirestoreContentionExhausted('r')]
    pump.merge.marked_script = [ValueError('m')]
    await _sweep_with(pump)
    matches = step_losses(caplog)
    assert [match.group(1) for match in matches] == list(STEP_NAMES)
    assert [match.group(2) for match in matches] == [
        'RuntimeError',
        'FirestoreContentionExhausted',
        'TimeoutError',
        'ValueError',
    ]


async def test_marker_storm_never_blocks_the_held_reoffer(monkeypatch):
    continuation_env(monkeypatch, True)
    pump = make_pump(held_owners=('o1',))
    pump.merge.commit_script['o1'] = [FirestoreContentionExhausted('hot')]
    for _ in range(3):
        pump._last_recovery = 0.0
        pump.merge.marked_script = [[('k1', None)]]
        await pump._maintain()
    assert pump.merge.drained == ['o1', 'o1', 'o1']


async def test_sweep_with_everything_healthy_runs_exactly_once(monkeypatch):
    continuation_env(monkeypatch, True)
    step = ScriptStep()
    pump = make_pump(project_pending=step)
    await _sweep_with(pump)
    assert step.calls == 1
    assert pump.scheduler.recover_calls == 1
    assert len(pump.scheduler.store.due_calls) == 1
    assert pump.merge.marked_calls == [50]


async def test_page_drain_losing_one_owner_scopes_the_loss_to_the_page(monkeypatch):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    store.due_script = [['s1', 's2', 's3']]
    store.jobs['s1'] = {'owner_id': 'o1'}
    store.jobs['s2'] = {'owner_id': 'o2'}
    store.jobs['s3'] = {'owner_id': 'o3'}
    pump = make_pump(scheduler=ScriptScheduler(store))
    pump.merge.commit_script['o2'] = [FirestoreContentionExhausted('hot owner')]
    await _sweep_with(pump)
    # Owners before the hot one drained; the loss is scoped to the ready_page
    # log and the owners behind it wait for the next idempotent page probe.
    assert pump.merge.drained == ['o1', 'o2']
    pump._last_recovery = 0.0  # >=5s elapsed: the next sweep re-probes the page
    pump.merge.commit_script.pop('o2')
    store.due_script = [['s1', 's2', 's3']]
    await pump._maintain()
    assert pump.merge.drained == ['o1', 'o2', 'o1', 'o2', 'o3']


# --------------------------------------------------------------------------
# Section 12: scheduler/pump boundary pins
# --------------------------------------------------------------------------


async def test_scheduler_recover_is_called_with_the_default_limit(monkeypatch):
    continuation_env(monkeypatch, True)

    class SpyScheduler(ScriptScheduler):
        def __init__(self, store=None):
            super().__init__(store)
            self.limits = []

        def recover(self, now, limit=100):
            self.recover_calls += 1
            self.recover_now = now
            self.limits.append(limit)
            return 0

    scheduler = SpyScheduler()
    pump = make_pump(scheduler=scheduler)
    await _sweep_with(pump)
    assert scheduler.limits == [100]
    assert scheduler.recover_now is not None


def test_pump_constructor_still_bounds_its_configuration():
    with pytest.raises(ValueError):
        Pump(ScriptScheduler(), SimpleNamespace(), publish_concurrency=0)


def test_pump_default_construction_builds_its_own_merge():
    pump = Pump(ScriptScheduler(), SimpleNamespace(), publish_concurrency=1)
    assert pump.merge is not None
    assert pump.timings is not None


# --------------------------------------------------------------------------
# Section 13: recover store contract pins (the harness's real-code guarantees)
# --------------------------------------------------------------------------


def test_recover_store_due_orders_rows_by_insertion():
    store = RecoverStore()
    seed(store, retry_job('a'), retry_job('b'), retry_job('c'))
    assert store.due('retry', 100, 100) == ['a', 'b', 'c']


def test_recover_store_due_respects_state_and_time():
    store = RecoverStore()
    seed(store, retry_job('a', available_at=0), retry_job('b', available_at=500))
    assert store.due('retry', 100, 100) == ['a']
    assert store.due('retry', 1000, 100) == ['a', 'b']


def test_recover_store_due_honors_the_limit():
    store = RecoverStore()
    seed(store, retry_job('a'), retry_job('b'), retry_job('c'))
    assert store.due('retry', 100, 2) == ['a', 'b']


def test_recover_store_run_applies_the_body_atomically():
    store = RecoverStore()
    seed(store, retry_job('a'))

    def body(tx):
        job = tx.get('jobs', 'a')
        job['state'] = 'ready'
        tx.put('jobs', 'a', job)
        return 'ok'

    assert store.run(body, operation='x') == 'ok'
    assert store.rows[('jobs', 'a')]['state'] == 'ready'


def test_recover_store_records_the_operation_label():
    store = RecoverStore()
    store.run(lambda tx: None, operation='batch_recover')
    assert store.run_operations == ['batch_recover']


def test_chain_exhaustion_helper_raises_from_the_real_chain():
    with pytest.raises(FirestoreContentionExhausted) as excinfo:
        chain_exhaustion('synthetic_helper_check')
    frames = []
    frame = excinfo.value.__traceback__
    while frame is not None:
        frames.append(frame.tb_frame.f_code.co_filename)
        frame = frame.tb_next
    assert any(name.endswith('firestore_transaction_retry.py') for name in frames)


# --------------------------------------------------------------------------
# Section 14: legacy matrix (gate off) — every step aborts, scope paths unchanged
# --------------------------------------------------------------------------


async def test_legacy_recover_timeout_loss_aborts_the_sweep(monkeypatch):
    continuation_env(monkeypatch, False)
    pump = make_pump()
    pump.scheduler.recover_script = [TimeoutError('slow')]
    with pytest.raises(TimeoutError):
        await _sweep_with(pump)
    assert pump.scheduler.store.due_calls == []


async def test_legacy_recover_valueerror_loss_aborts_the_sweep(monkeypatch):
    continuation_env(monkeypatch, False)
    pump = make_pump()
    pump.scheduler.recover_script = [ValueError('bug')]
    with pytest.raises(ValueError):
        await _sweep_with(pump)
    assert pump.merge.marked_calls == []


async def test_legacy_due_timeout_loss_aborts_the_sweep(monkeypatch):
    continuation_env(monkeypatch, False)
    store = ScriptStore()
    store.due_script = [TimeoutError('slow')]
    pump = make_pump(scheduler=ScriptScheduler(store))
    with pytest.raises(TimeoutError):
        await _sweep_with(pump)
    assert pump.merge.drained == []


async def test_legacy_due_runtimeerror_loss_aborts_the_sweep(monkeypatch):
    continuation_env(monkeypatch, False)
    store = ScriptStore()
    store.due_script = [RuntimeError('bug')]
    pump = make_pump(scheduler=ScriptScheduler(store))
    with pytest.raises(RuntimeError):
        await _sweep_with(pump)
    assert pump.merge.marked_calls == []


async def test_legacy_marked_timeout_loss_aborts_the_sweep(monkeypatch):
    continuation_env(monkeypatch, False)
    pump = make_pump()
    pump.merge.marked_script = [TimeoutError('slow')]
    with pytest.raises(TimeoutError):
        await _sweep_with(pump)
    assert pump.merge.drained == []


async def test_legacy_projection_timeout_loss_aborts_the_sweep(monkeypatch):
    continuation_env(monkeypatch, False)
    pump = make_pump(project_pending=ScriptStep(errors=[TimeoutError('slow')]))
    with pytest.raises(TimeoutError):
        await _sweep_with(pump)
    assert pump.scheduler.recover_calls == 0


async def test_legacy_projection_runtimeerror_loss_aborts_the_sweep(monkeypatch):
    continuation_env(monkeypatch, False)
    pump = make_pump(project_pending=ScriptStep(errors=[RuntimeError('bug')]))
    with pytest.raises(RuntimeError):
        await _sweep_with(pump)
    assert pump.scheduler.recover_calls == 0


async def test_legacy_marker_scope_is_unchanged_by_the_gate(monkeypatch):
    continuation_env(monkeypatch, False)
    pump = make_pump()
    pump.merge.marked_script = [[('key-1', 'owner-1'), ('key-2', None)]]
    pump.merge.commit_script['owner-1'] = [FirestoreContentionExhausted('hot')]
    await _sweep_with(pump)
    assert ('key-2', True) in pump.merge.released
    assert pump._last_recovery > 0


async def test_legacy_ready_page_scope_is_unchanged_by_the_gate(monkeypatch):
    continuation_env(monkeypatch, False)
    store = ScriptStore()
    store.due_script = [['s1']]
    store.jobs['s1'] = {'owner_id': 'o1'}
    pump = make_pump(scheduler=ScriptScheduler(store))
    pump.merge.commit_script['o1'] = [FirestoreContentionExhausted('hot')]
    await _sweep_with(pump)
    assert pump.merge.marked_calls == [50]


async def test_legacy_held_scope_is_unchanged_by_the_gate(monkeypatch):
    continuation_env(monkeypatch, False)
    pump = make_pump(held_owners=('o1',))
    pump.merge.commit_script['o1'] = [FirestoreContentionExhausted('hot')]
    await _sweep_with(pump)
    assert pump._last_recovery > 0


async def test_legacy_shadow_scope_is_unchanged_by_the_gate(monkeypatch):
    continuation_env(monkeypatch, False)
    shadow = ScriptShadow(errors=[FirestoreContentionExhausted('storm')])
    pump = make_pump(shadow=shadow)
    await _sweep_with(pump)
    assert pump.scheduler.recover_calls == 1


async def test_legacy_gate_off_due_limit_is_still_100(monkeypatch):
    continuation_env(monkeypatch, False)
    store = ScriptStore()
    pump = make_pump(scheduler=ScriptScheduler(store))
    await _sweep_with(pump)
    assert store.due_calls[0][2] == 100


# --------------------------------------------------------------------------
# Section 15: two-sweep failure schedules (gate on) — every ordered step pair
# --------------------------------------------------------------------------


STEP_FAILURES = {
    'projection': RuntimeError('p'),
    'recover': FirestoreContentionExhausted('r'),
    'ready_due': TimeoutError('d'),
    'marked_page': ValueError('m'),
}


@pytest.mark.parametrize(
    ('first', 'second'),
    [
        ('recover', 'ready_due'),
        ('ready_due', 'recover'),
        ('recover', 'marked_page'),
        ('marked_page', 'recover'),
        ('recover', 'projection'),
        ('projection', 'recover'),
        ('ready_due', 'projection'),
        ('projection', 'ready_due'),
        ('ready_due', 'marked_page'),
        ('marked_page', 'ready_due'),
        ('projection', 'marked_page'),
        ('marked_page', 'projection'),
    ],
)
async def test_two_sweep_loss_schedule_keeps_every_later_step_running(monkeypatch, caplog, first, second):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    pump = make_pump(scheduler=ScriptScheduler(store), project_pending=ScriptStep())

    def fail(step_name):
        if step_name == 'projection':
            pump.project_pending.errors = [STEP_FAILURES[step_name]]
        elif step_name == 'recover':
            pump.scheduler.recover_script = [STEP_FAILURES[step_name]]
        elif step_name == 'ready_due':
            store.due_script = [STEP_FAILURES[step_name]]
        else:
            pump.merge.marked_script = [STEP_FAILURES[step_name]]

    order = list(STEP_NAMES)
    for sweep, loss in enumerate((first, second, None)):
        pump._last_recovery = 0.0
        if loss:
            fail(loss)
        await pump._maintain()
        # The failed step and every step before it in the sweep order ran (or
        # were skipped only because they precede the failure); every step after
        # the failure must have run this sweep.
        after = order[order.index(loss) + 1 :] if loss else []
        for step in after:
            if step == 'recover':
                assert pump.scheduler.recover_calls >= sweep + 1
            elif step == 'ready_due':
                assert len(store.due_calls) >= sweep + 1
            elif step == 'marked_page':
                assert len(pump.merge.marked_calls) >= sweep + 1
    # The healthy third sweep ran every step once more.
    assert pump.scheduler.recover_calls == 3
    assert len(store.due_calls) == 3
    assert pump.merge.marked_calls == [50] * 3


# --------------------------------------------------------------------------
# Section 16: within-sweep continuation for every (lost step, later step) pair
# --------------------------------------------------------------------------


async def test_projection_loss_still_runs_the_ready_probe(monkeypatch):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    pump = make_pump(scheduler=ScriptScheduler(store), project_pending=ScriptStep(errors=[RuntimeError('p')]))
    await _sweep_with(pump)
    assert len(store.due_calls) == 1


async def test_projection_loss_still_drains_the_ready_page(monkeypatch):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    store.due_script = [['s1']]
    store.jobs['s1'] = {'owner_id': 'o1'}
    pump = make_pump(scheduler=ScriptScheduler(store), project_pending=ScriptStep(errors=[RuntimeError('p')]))
    await _sweep_with(pump)
    assert pump.merge.drained == ['o1']


async def test_projection_loss_still_runs_the_markers(monkeypatch):
    continuation_env(monkeypatch, True)
    pump = make_pump(project_pending=ScriptStep(errors=[RuntimeError('p')]))
    pump.merge.marked_script = [[('k1', None)]]
    await _sweep_with(pump)
    assert pump.merge.released == [('k1', True)]


async def test_recover_loss_still_drains_the_ready_page(monkeypatch):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    store.due_script = [['s1']]
    store.jobs['s1'] = {'owner_id': 'o1'}
    pump = make_pump(scheduler=ChainScheduler(store))
    await _sweep_with(pump)
    assert pump.merge.drained == ['o1']


async def test_due_loss_still_reoffers_the_held_owners(monkeypatch):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    store.due_script = [FirestoreContentionExhausted('d')]
    pump = make_pump(scheduler=ScriptScheduler(store), held_owners=('o1',))
    await _sweep_with(pump)
    assert pump.merge.drained == ['o1']


async def test_marked_page_loss_leaves_the_ready_probe_intact(monkeypatch):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    pump = make_pump(scheduler=ScriptScheduler(store))
    pump.merge.marked_script = [ValueError('m')]
    await _sweep_with(pump)
    assert len(store.due_calls) == 1


async def test_marker_loss_still_reoffers_the_held_owners(monkeypatch):
    continuation_env(monkeypatch, True)
    pump = make_pump(held_owners=('o1',))
    pump.merge.marked_script = [[('k1', 'o2')]]
    pump.merge.commit_script['o2'] = [FirestoreContentionExhausted('hot')]
    await _sweep_with(pump)
    assert pump.merge.drained == ['o2', 'o1']


async def test_recover_and_due_losing_still_runs_the_markers(monkeypatch):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    store.due_script = [TimeoutError('d')]
    pump = make_pump(scheduler=ScriptScheduler(store), project_pending=ScriptStep())
    pump.scheduler.recover_script = [FirestoreContentionExhausted('r')]
    pump.merge.marked_script = [[('k1', None)]]
    await _sweep_with(pump)
    assert pump.merge.released == [('k1', True)]


# --------------------------------------------------------------------------
# Section 17: metrics/shadow/leader edge contracts
# --------------------------------------------------------------------------


async def test_sample_metrics_loss_propagates_as_the_loop_net(monkeypatch, caplog):
    continuation_env(monkeypatch, True)

    class ExplodingMetrics(ScriptMetrics):
        def refresh(self, store, now):
            raise FirestoreContentionExhausted('metrics store hot')

    pump = make_pump(metrics=ExplodingMetrics())
    pump._last_metrics = 0.0
    with pytest.raises(FirestoreContentionExhausted):
        await pump._maintain()
    legacy = [
        r.getMessage()
        for r in caplog.records
        if 'event=batch_maintenance outcome=retry' in r.getMessage() and 'step=' not in r.getMessage()
    ]
    assert legacy == []  # the loop-level net logs it; _maintain itself only raises


async def test_sample_metrics_loss_keeps_the_metrics_clock_unupdated(monkeypatch):
    continuation_env(monkeypatch, True)

    class ExplodingMetrics(ScriptMetrics):
        def refresh(self, store, now):
            raise FirestoreContentionExhausted('metrics store hot')

    pump = make_pump(metrics=ExplodingMetrics())
    pump._last_metrics = 0.0
    with pytest.raises(FirestoreContentionExhausted):
        await pump._maintain()
    assert pump._last_metrics == 0.0


async def test_shadow_contention_loss_is_isolated_like_any_shadow_fault(monkeypatch):
    continuation_env(monkeypatch, True)
    shadow = ScriptShadow(errors=[FirestoreContentionExhausted('storm')])
    pump = make_pump(shadow=shadow)
    await _sweep_with(pump)
    assert shadow.calls == 1
    assert pump.scheduler.recover_calls == 1


async def test_shadow_base_exception_is_never_swallowed(monkeypatch):
    continuation_env(monkeypatch, True)

    class InterruptedShadow:
        calls = 0

        async def maintain(self):
            InterruptedShadow.calls += 1
            raise KeyboardInterrupt

    pump = make_pump(shadow=InterruptedShadow())
    with pytest.raises(KeyboardInterrupt):
        await _sweep_with(pump)


async def test_leader_acquire_timeout_loss_propagates(monkeypatch):
    continuation_env(monkeypatch, True)
    leader = ScriptLeader(errors=[TimeoutError('lease timeout')])
    pump = make_pump(leader=leader)
    with pytest.raises(TimeoutError):
        await _sweep_with(pump)


async def test_leader_acquire_acceptance_runs_the_gated_steps(monkeypatch):
    continuation_env(monkeypatch, True)
    leader = ScriptLeader(results=[True])
    step = ScriptStep()
    pump = make_pump(leader=leader, project_pending=step)
    await _sweep_with(pump)
    assert leader.calls == 1
    assert step.calls == 1
    assert pump.scheduler.recover_calls == 1


async def test_leader_decline_skips_the_due_probe(monkeypatch):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    leader = ScriptLeader(results=[False])
    pump = make_pump(scheduler=ScriptScheduler(store), leader=leader)
    await _sweep_with(pump)
    assert store.due_calls == []


# --------------------------------------------------------------------------
# Section 18: drain_owner and the publication-side merge contracts
# --------------------------------------------------------------------------


class EntryMerge(ScriptMerge):
    """commit_next hands out scripted entries before returning None."""

    def __init__(self, entries):
        super().__init__()
        self.entries = list(entries)

    def commit_next(self, owner_id, now):
        self.drained.append(owner_id)
        if self.entries:
            return self.entries.pop(0)
        return None


async def test_drain_owner_stops_at_the_first_none_entry(monkeypatch):
    continuation_env(monkeypatch, True)
    merge = EntryMerge([{'segment_id': 's1'}, None, {'segment_id': 's2'}])
    pump = make_pump(merge=merge)
    await pump.drain_owner('o1')
    assert merge.drained == ['o1', 'o1']


async def test_drain_owner_visits_commit_next_once_per_entry(monkeypatch):
    continuation_env(monkeypatch, True)
    merge = EntryMerge([{'segment_id': 's1'}, {'segment_id': 's2'}, {'segment_id': 's3'}])
    pump = make_pump(merge=merge)
    await pump.drain_owner('o1')
    assert len(merge.drained) == 4  # three entries + the closing None probe


async def test_drain_owner_loss_propagates_to_the_publication_caller(monkeypatch):
    continuation_env(monkeypatch, True)
    merge = ScriptMerge()
    merge.commit_script['o1'] = [FirestoreContentionExhausted('hot')]
    pump = make_pump(merge=merge)
    with pytest.raises(FirestoreContentionExhausted):
        await pump.drain_owner('o1')


async def test_drain_after_publication_swallows_and_logs_the_merge_retry(monkeypatch, caplog):
    continuation_env(monkeypatch, True)
    merge = ScriptMerge()
    merge.commit_script['o1'] = [FirestoreContentionExhausted('hot')]
    pump = make_pump(merge=merge)
    await pump._drain_after_publication('o1')
    records = [r for r in caplog.records if 'event=batch_merge outcome=retry' in r.getMessage()]
    assert len(records) == 1
    assert 'exception_type=FirestoreContentionExhausted' in records[0].getMessage()


async def test_drain_after_publication_logs_nothing_on_a_healthy_drain(monkeypatch, caplog):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    await pump._drain_after_publication('o1')
    assert [r for r in caplog.records if 'event=batch_merge' in r.getMessage()] == []


async def test_drain_owner_bound_is_100_entries(monkeypatch):
    continuation_env(monkeypatch, True)
    merge = ScriptMerge()
    calls = {'n': 0}

    def commit_next(owner_id, now):
        merge.drained.append(owner_id)
        calls['n'] += 1
        return {'segment_id': f's{calls["n"]}'}  # never None

    merge.commit_next = commit_next
    pump = make_pump(merge=merge)
    await pump.drain_owner('o1')
    assert len(merge.drained) == 100


# --------------------------------------------------------------------------
# Section 19: concurrent page drain (publish_concurrency > 1)
# --------------------------------------------------------------------------


async def test_concurrent_page_drain_dedupes_to_one_drain_per_owner(monkeypatch):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    store.due_script = [['s1', 's2']]
    store.jobs['s1'] = {'owner_id': 'o1'}
    store.jobs['s2'] = {'owner_id': 'o1'}
    pump = make_pump(scheduler=ScriptScheduler(store), publish_concurrency=2)
    await _sweep_with(pump)
    assert pump.merge.drained == ['o1']


async def test_concurrent_page_drain_drains_each_first_seen_owner(monkeypatch):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    store.due_script = [['s1', 's2', 's3']]
    store.jobs['s1'] = {'owner_id': 'o2'}
    store.jobs['s2'] = {'owner_id': 'o1'}
    store.jobs['s3'] = {'owner_id': 'o3'}
    pump = make_pump(scheduler=ScriptScheduler(store), publish_concurrency=2)
    await _sweep_with(pump)
    assert sorted(pump.merge.drained) == ['o1', 'o2', 'o3']


async def test_concurrent_page_drain_uses_the_owner_memo_on_the_next_sweep(monkeypatch):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    store.due_script = [['s1']]
    store.jobs['s1'] = {'owner_id': 'o1'}
    pump = make_pump(scheduler=ScriptScheduler(store), publish_concurrency=2)
    await _sweep_with(pump)
    probes_after_first = store.probe_calls
    pump._last_recovery = 0.0
    store.due_script = [['s1']]
    await pump._maintain()
    assert store.probe_calls == probes_after_first
    assert pump.merge.drained == ['o1', 'o1']


# --------------------------------------------------------------------------
# Section 20: recover state-machine contracts (landed transitions)
# --------------------------------------------------------------------------


async def test_recover_leased_not_yet_expired_is_ignored(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, leased_job('l1', lease_until=500))
    assert make_scheduler(store).recover(100) == 0
    assert store.due('leased', 100, 100) == []


async def test_recover_retry_not_yet_available_is_ignored(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a', available_at=500))
    assert make_scheduler(store).recover(100) == 0


async def test_recover_processes_both_states_in_one_pass(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, leased_job('l1'), leased_job('l2'), retry_job('r1'), retry_job('r2'))
    assert make_scheduler(store).recover(100) == 4


async def test_recover_limit_cuts_within_a_state(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, leased_job('l1'), leased_job('l2'))
    assert make_scheduler(store).recover(100, limit=1) == 1


async def test_recover_privacy_blocked_item_quarantines_fenced_and_continues(monkeypatch):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a'), retry_job('b'))
    store.fail_calls = {1}
    store.fail_errors = {1: BatchPrivacyBlocked('owner deleted')}
    assert make_scheduler(store).recover(100) == 1
    assert store.quarantined_fenced == ['a']
    assert store.rows[('jobs', 'b')]['state'] == 'ready'


async def test_recover_privacy_blocked_and_contention_losses_coexist(monkeypatch):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a'), retry_job('b'), retry_job('c'))
    store.fail_calls = {1, 2}
    store.fail_errors = {1: BatchPrivacyBlocked('owner deleted')}
    assert make_scheduler(store).recover(100) == 1
    assert store.quarantined_fenced == ['a']
    assert store.rows[('jobs', 'c')]['state'] == 'ready'


async def test_recover_privacy_blocked_item_is_not_counted_as_recovered(monkeypatch):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a'))
    store.fail_calls = {1}
    store.fail_errors = {1: BatchPrivacyBlocked('owner deleted')}
    assert make_scheduler(store).recover(100) == 0


async def test_recover_quarantine_lands_the_lease_expired_signature(monkeypatch, caplog):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    monkeypatch.delenv(GATE, raising=False)
    store = RecoverStore()
    seed(store, leased_job('l1', attempt=99))
    make_scheduler(store).recover(100)
    messages = [r.getMessage() for r in caplog.records if 'event=batch_quarantined' in r.getMessage()]
    assert any('reason=lease_expired recovery=held' in m for m in messages)


async def test_recover_quarantined_item_counts_as_a_landed_transition(monkeypatch):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    monkeypatch.delenv(GATE, raising=False)
    store = RecoverStore()
    seed(store, leased_job('l1', attempt=99))
    assert make_scheduler(store).recover(100) == 1


async def test_recover_quarantine_records_the_recovery_held_metric(monkeypatch):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    monkeypatch.delenv(GATE, raising=False)

    class RecordingMetrics:
        def __init__(self):
            self.recorded = []

        def record(self, name):
            self.recorded.append(name)

    metrics = RecordingMetrics()
    store = RecoverStore()
    seed(store, leased_job('l1', attempt=99))
    Scheduler(store, metrics=metrics).recover(100)
    assert metrics.recorded == ['quarantined', 'recovery_held']


async def test_recover_requeue_records_the_requeued_metric(monkeypatch):
    recover_sweep(monkeypatch)

    class RecordingMetrics:
        def __init__(self):
            self.recorded = []

        def record(self, name):
            self.recorded.append(name)

    metrics = RecordingMetrics()
    store = RecoverStore()
    seed(store, retry_job('a'))
    Scheduler(store, metrics=metrics).recover(100)
    assert metrics.recorded == ['requeued']


async def test_recover_quarantine_bumps_the_owner_revision(monkeypatch):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    monkeypatch.delenv(GATE, raising=False)
    store = RecoverStore()
    seed(store, leased_job('l1', attempt=99))
    make_scheduler(store).recover(100)
    owner = store.rows[('owners', store.rows[('jobs', 'l1')]['owner_key'])]
    assert owner['revision'] == 1


async def test_recover_quarantine_clears_the_lease_custody_fields(monkeypatch):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    monkeypatch.delenv(GATE, raising=False)
    store = RecoverStore()
    job = leased_job('l1', attempt=99)
    job['token'] = 'tok'
    job['lease_until'] = 50.0
    job['merge_pending'] = True
    seed(store, job)
    make_scheduler(store).recover(100)
    quarantined = store.rows[('jobs', 'l1')]
    assert quarantined['token'] == ''
    assert quarantined['lease_until'] == 0.0
    assert quarantined['merge_pending'] is False
    assert quarantined['quarantined_at'] == 100


async def test_recover_defer_sets_the_retry_backoff_fields(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, leased_job('l1', attempt=2))
    make_scheduler(store).recover(100)
    deferred = store.rows[('jobs', 'l1')]
    assert deferred['state'] == 'retry'
    assert deferred['available_at'] == 100 + 10  # 5 * 2 ** (attempt-1)
    assert deferred['failure'] == 'lease_expired'
    assert deferred['token'] == ''


async def test_recover_defer_of_a_first_attempt_uses_the_base_backoff(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, leased_job('l1', attempt=1))
    make_scheduler(store).recover(100)
    assert store.rows[('jobs', 'l1')]['available_at'] == 100 + 5


async def test_recover_label_context_is_clean_after_a_continued_pass(monkeypatch):
    from database.batch_pipeline_transaction_labels import current_operation

    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a'), retry_job('b'))
    store.fail_calls = {1}
    make_scheduler(store).recover(100)
    assert current_operation() is None


async def test_recover_twice_leaves_the_label_context_clean(monkeypatch):
    from database.batch_pipeline_transaction_labels import current_operation

    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a'))
    scheduler = make_scheduler(store)
    scheduler.recover(100)
    scheduler.recover(100)
    assert current_operation() is None


async def test_recover_records_policy_observations_for_landed_items(monkeypatch):
    recover_sweep(monkeypatch)
    observed = []
    monkeypatch.setattr(
        'utils.batch_pipeline.scheduler.record_policy_observations', lambda observations: observed.append(1)
    )
    store = RecoverStore()
    seed(store, retry_job('a'), retry_job('b'), retry_job('c'))
    store.fail_calls = {2}
    make_scheduler(store).recover(100)
    assert len(observed) == 2


async def test_recover_skips_policy_observations_for_lost_items(monkeypatch):
    recover_sweep(monkeypatch)
    observed = []
    monkeypatch.setattr(
        'utils.batch_pipeline.scheduler.record_policy_observations', lambda observations: observed.append(1)
    )
    store = RecoverStore()
    seed(store, retry_job('a'))
    store.fail_calls = {1}
    make_scheduler(store).recover(100)
    assert observed == []


async def test_recover_limit_zero_runs_only_the_migration(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a'))
    assert make_scheduler(store).recover(100, limit=0) == 0
    assert store.run_calls == 1
    assert store.rows[('jobs', 'a')]['state'] == 'retry'


async def test_recover_healthy_pass_logs_nothing(monkeypatch, caplog):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a'), retry_job('b'))
    make_scheduler(store).recover(100)
    scheduler_records = [r for r in caplog.records if r.name == SCHEDULER_LOGGER]
    assert scheduler_records == []


async def test_recover_item_loss_volume_is_one_warning_per_loss(monkeypatch, caplog):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a'), retry_job('b'), retry_job('c'), retry_job('d'))
    store.fail_calls = {1, 3}
    make_scheduler(store).recover(100)
    warnings = [r for r in caplog.records if 'scope=item' in r.getMessage()]
    assert len(warnings) == 2


async def test_recover_leased_state_loss_does_not_block_the_retry_state_scan(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, leased_job('l1'), retry_job('r1'))
    store.fail_calls = {1}  # the leased item
    assert make_scheduler(store).recover(100) == 1
    assert store.rows[('jobs', 'r1')]['state'] == 'ready'


async def test_recover_multi_owner_pass_lands_one_queue_per_owner(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a', owner='o1'), retry_job('b', owner='o2'), retry_job('c', owner='o3'))
    make_scheduler(store).recover(100)
    for owner in ('o1', 'o2', 'o3'):
        queue = store.rows[('queues', f'1_{owner_key(owner)}')]
        assert queue['tail'] in ('a', 'b', 'c')
        assert queue['head'] == queue['tail']


async def test_recover_same_owner_three_items_form_an_ordered_chain(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a'), retry_job('b'), retry_job('c'))
    make_scheduler(store).recover(100)
    queue = store.rows[('queues', f"1_{owner_key('owner-a')}")]
    assert queue['head'] == 'a'
    assert queue['tail'] == 'c'
    assert store.rows[('jobs', 'a')]['next'] == 'b'
    assert store.rows[('jobs', 'b')]['next'] == 'c'
    assert store.rows[('jobs', 'c')]['next'] == ''


async def test_recover_quarantine_preserves_the_job_duration(monkeypatch):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    monkeypatch.delenv(GATE, raising=False)
    store = RecoverStore()
    seed(store, leased_job('l1', attempt=99))
    make_scheduler(store).recover(100)
    assert store.rows[('jobs', 'l1')]['duration_seconds'] == 3.0


# --------------------------------------------------------------------------
# Section 21: gate semantics under serve mode
# --------------------------------------------------------------------------


def test_gate_serve_mode_defaults_on(monkeypatch):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    monkeypatch.delenv(GATE, raising=False)
    assert config_batch_pipeline.maintenance_contention_continuation_enabled() is True


def test_gate_serve_mode_false_kills(monkeypatch):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    monkeypatch.setenv(GATE, 'false')
    assert config_batch_pipeline.maintenance_contention_continuation_enabled() is False


def test_gate_serve_mode_true_stays_on(monkeypatch):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    monkeypatch.setenv(GATE, 'true')
    assert config_batch_pipeline.maintenance_contention_continuation_enabled() is True


def test_flag_budget_owner_entry_does_not_consume_a_budget_slot():
    data = json.loads((BACKEND / 'config' / 'flag_budget.json').read_text())
    slots = sum(1 for entry in data['names'].values() if 'seeded' in entry or 'replaces' in entry)
    assert slots == data['budget']


# --------------------------------------------------------------------------
# Section 22: source and docs pins
# --------------------------------------------------------------------------


def test_docs_name_the_gate():
    source = (BACKEND / 'docs' / 'batch-maintenance-contention-continuation.md').read_text()
    assert GATE in source


def test_docs_carry_the_failure_class_line():
    source = (BACKEND / 'docs' / 'batch-maintenance-contention-continuation.md').read_text()
    assert 'Failure-Class: FC-immediate-retry-loses-shared-cas' in source


def test_scheduler_source_carries_both_loss_scopes():
    source = (BACKEND / 'utils' / 'batch_pipeline' / 'scheduler.py').read_text()
    assert 'scope=migrate' in source
    assert 'scope=item' in source


def test_pump_source_carries_every_step_name():
    source = (BACKEND / 'utils' / 'batch_pipeline' / 'pump.py').read_text()
    for name in STEP_NAMES:
        assert f"'{name}'" in source


def test_pump_source_formats_the_step_loss_event():
    source = (BACKEND / 'utils' / 'batch_pipeline' / 'pump.py').read_text()
    assert 'event=batch_maintenance outcome=retry step=%s exception_type=%s%s' in source


def test_scheduler_source_formats_the_recover_loss_event():
    source = (BACKEND / 'utils' / 'batch_pipeline' / 'scheduler.py').read_text()
    assert 'event=batch_recover outcome=retry scope=migrate exception_type=%s%s' in source
    assert 'event=batch_recover outcome=retry scope=item exception_type=%s%s' in source


# --------------------------------------------------------------------------
# Section 23: storm schedules, extended
# --------------------------------------------------------------------------


async def test_projection_losing_every_sweep_never_blocks_recovery(monkeypatch):
    continuation_env(monkeypatch, True)
    step = ScriptStep(errors=[RuntimeError('p')])
    pump = make_pump(project_pending=step)
    for _ in range(4):
        pump._last_recovery = 0.0
        pump.project_pending.errors = [RuntimeError('p')]
        await pump._maintain()
    assert pump.scheduler.recover_calls == 4
    assert len(pump.merge.marked_calls) == 4


async def test_due_losing_every_sweep_never_blocks_the_markers(monkeypatch):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    pump = make_pump(scheduler=ScriptScheduler(store))
    for _ in range(4):
        pump._last_recovery = 0.0
        store.due_script = [FirestoreContentionExhausted('d')]
        await pump._maintain()
    assert pump.merge.marked_calls == [50] * 4
    assert pump.scheduler.recover_calls == 4


async def test_marked_page_losing_every_sweep_never_blocks_the_held_reoffer(monkeypatch):
    continuation_env(monkeypatch, True)
    pump = make_pump(held_owners=('o1',))
    for _ in range(4):
        pump._last_recovery = 0.0
        pump.merge.marked_script = [ValueError('m')]
        await pump._maintain()
    assert pump.merge.drained == ['o1'] * 4


async def test_three_steps_losing_leaves_markers_and_held_running(monkeypatch):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    store.due_script = [TimeoutError('d')]
    pump = make_pump(
        scheduler=ScriptScheduler(store),
        project_pending=ScriptStep(errors=[RuntimeError('p')]),
        held_owners=('o1',),
    )
    pump.scheduler.recover_script = [FirestoreContentionExhausted('r')]
    await _sweep_with(pump)
    assert pump.merge.drained == ['o1']
    assert pump._last_recovery > 0


async def test_five_healthy_sweeps_run_exactly_one_recover_each(monkeypatch):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    for _ in range(5):
        pump._last_recovery = 0.0
        await pump._maintain()
    assert pump.scheduler.recover_calls == 5
    assert pump.merge.marked_calls == [50] * 5


# --------------------------------------------------------------------------
# Section 24: cadence boundaries
# --------------------------------------------------------------------------


async def test_recovery_interval_boundary_at_exactly_five_seconds_runs(monkeypatch):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    await _sweep_with(pump)
    pump._last_recovery -= 5.0  # sampled_at - _last_recovery == 5.0
    await pump._maintain()
    assert pump.scheduler.recover_calls == 2


async def test_recovery_interval_just_under_five_seconds_skips(monkeypatch):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    await _sweep_with(pump)
    pump._last_recovery -= 4.9
    await pump._maintain()
    assert pump.scheduler.recover_calls == 1


async def test_metrics_interval_boundary_at_fifteen_seconds_runs(monkeypatch):
    continuation_env(monkeypatch, True)
    metrics = ScriptMetrics()
    pump = make_pump(metrics=metrics)
    pump._last_metrics = 0.0
    await pump._maintain()
    assert metrics.refreshes == 1
    pump._last_metrics -= 15.0
    await pump._maintain()
    assert metrics.refreshes == 2


async def test_step_losses_never_touch_the_metrics_clock(monkeypatch):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    pump.scheduler.recover_script = [FirestoreContentionExhausted('storm')]
    pump._last_metrics = 0.0
    await _sweep_with(pump)
    first = pump._last_metrics
    pump._last_recovery = 0.0
    pump.scheduler.recover_script = [FirestoreContentionExhausted('storm again')]
    await pump._maintain()
    assert pump._last_metrics == first


# --------------------------------------------------------------------------
# Section 25: scope paths under the gate (pin the pre-existing scoped logs)
# --------------------------------------------------------------------------


async def test_marker_owner_drain_loss_logs_marker_scope_gate_off(monkeypatch, caplog):
    continuation_env(monkeypatch, False)
    pump = make_pump()
    pump.merge.marked_script = [[('key-1', 'owner-1')]]
    pump.merge.commit_script['owner-1'] = [FirestoreContentionExhausted('hot')]
    await _sweep_with(pump)
    records = [r for r in caplog.records if 'scope=marker' in r.getMessage()]
    assert len(records) == 1


async def test_ready_page_failure_logs_ready_page_scope_gate_off(monkeypatch, caplog):
    continuation_env(monkeypatch, False)
    store = ScriptStore()
    store.due_script = [['s1']]
    store.jobs['s1'] = {'owner_id': 'o1'}
    pump = make_pump(scheduler=ScriptScheduler(store))
    pump.merge.commit_script['o1'] = [FirestoreContentionExhausted('hot')]
    await _sweep_with(pump)
    records = [r for r in caplog.records if 'scope=ready_page' in r.getMessage()]
    assert len(records) == 1


async def test_probe_with_a_missing_job_row_skips_the_owner(monkeypatch):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    store.due_script = [['ghost-segment']]
    pump = make_pump(scheduler=ScriptScheduler(store))
    await _sweep_with(pump)
    assert pump.merge.drained == []
    assert pump.merge.marked_calls == [50]


async def test_page_drain_probes_never_re_due(monkeypatch):
    continuation_env(monkeypatch, True)
    store = ScriptStore()
    store.due_script = [['s1', 's2']]
    store.jobs['s1'] = {'owner_id': 'o1'}
    store.jobs['s2'] = {'owner_id': 'o2'}
    pump = make_pump(scheduler=ScriptScheduler(store))
    await _sweep_with(pump)
    assert len(store.due_calls) == 1
    assert store.probe_calls == 2


async def test_event_namespaces_stay_separate_under_a_double_loss(monkeypatch, caplog):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    pump.scheduler.recover_script = [FirestoreContentionExhausted('storm')]
    pump.merge.commit_script['held-o'] = [FirestoreContentionExhausted('hot')]
    pump.merge.marked_script = [[('k1', 'held-o')]]
    pump.merge.held_owners = {'held-o'}
    await _sweep_with(pump)
    maintenance = [r for r in caplog.records if r.getMessage().startswith('event=batch_maintenance')]
    recover_events = [r for r in caplog.records if r.getMessage().startswith('event=batch_recover')]
    merge_events = [r for r in caplog.records if r.getMessage().startswith('event=batch_merge')]
    assert len(maintenance) == 1 and 'step=recover' in maintenance[0].getMessage()
    assert len(recover_events) == 0  # the pump-level loss is the recover step's own record
    assert len(merge_events) >= 1 and 'scope=marker' in merge_events[0].getMessage()


# --------------------------------------------------------------------------
# Section 26: the step helper's direct contracts
# --------------------------------------------------------------------------


async def test_step_helper_passes_positional_args_through(monkeypatch):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    seen = []

    def fn(*args):
        seen.append(args)
        return 'ok'

    result = await pump._maintenance_step('ready_due', 'maintenance', db_executor, fn, 'result_ready', 7, 100)
    assert result == 'ok'
    assert seen == [('result_ready', 7, 100)]


async def test_step_helper_returns_none_for_any_exception(monkeypatch):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    result = await pump._maintenance_step('recover', 'maintenance', db_executor, ScriptStep(errors=[TypeError('bad')]))
    assert result is None


async def test_step_helper_logs_the_error_level_for_any_exception(monkeypatch, caplog):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    await pump._maintenance_step('recover', 'maintenance', db_executor, ScriptStep(errors=[TypeError('bad')]))
    record = [r for r in caplog.records if 'step=recover' in r.getMessage()][0]
    assert record.levelname == 'ERROR'
    assert 'exception_type=TypeError' in record.getMessage()


async def test_step_helper_stages_are_valid_worker_timing_stages(monkeypatch):
    continuation_env(monkeypatch, True)
    from utils.batch_pipeline.stage_timings import StageTimings

    pump = make_pump(timings=StageTimings())
    for stage in ('maintenance', 'projection'):
        result = await pump._maintenance_step('recover', stage, db_executor, ScriptStep())
        assert result is None  # ScriptStep() with no errors returns None already


def test_stage_timings_declare_the_maintenance_and_projection_stages():
    from utils.batch_pipeline.stage_timings import STAGES

    assert 'maintenance' in STAGES
    assert 'projection' in STAGES


# --------------------------------------------------------------------------
# Section 27: continuation composition corners
# --------------------------------------------------------------------------


async def test_shadow_and_recover_losing_together_still_run_the_markers(monkeypatch):
    continuation_env(monkeypatch, True)
    shadow = ScriptShadow(errors=[FirestoreContentionExhausted('shadow storm')])
    pump = make_pump(shadow=shadow)
    pump.scheduler.recover_script = [FirestoreContentionExhausted('storm')]
    pump.merge.marked_script = [[('k1', None)]]
    await _sweep_with(pump)
    assert shadow.calls == 1
    assert pump.merge.released == [('k1', True)]


async def test_leader_decline_and_shadow_loss_still_reoffer_the_held_owners(monkeypatch):
    continuation_env(monkeypatch, True)
    leader = ScriptLeader(results=[False])
    shadow = ScriptShadow(errors=[RuntimeError('shadow noise')])
    pump = make_pump(leader=leader, shadow=shadow, held_owners=('o1',))
    await _sweep_with(pump)
    assert pump.merge.drained == ['o1']
    assert pump._last_recovery > 0


async def test_metrics_sample_without_a_recovery_due_tick(monkeypatch):
    continuation_env(monkeypatch, True)
    metrics = ScriptMetrics()
    pump = make_pump(metrics=metrics)
    await _sweep_with(pump)
    first_recovery = pump._last_recovery
    pump._last_metrics = 0.0  # metrics interval due, recovery interval not
    await pump._maintain()
    assert metrics.refreshes == 2
    assert pump._last_recovery == first_recovery


async def test_no_intervals_due_runs_nothing(monkeypatch):
    continuation_env(monkeypatch, True)
    step = ScriptStep()
    pump = make_pump(project_pending=step)
    await _sweep_with(pump)
    calls_after_first = (step.calls, pump.scheduler.recover_calls)
    await pump._maintain()  # inside both intervals
    assert (step.calls, pump.scheduler.recover_calls) == calls_after_first


async def test_step_time_is_monotone_across_the_sweep(monkeypatch):
    import time as time_module

    continuation_env(monkeypatch, True)
    store = ScriptStore()
    stamps = []
    original_time = time_module.time

    def spy_time():
        value = original_time()
        stamps.append(value)
        return value

    monkeypatch.setattr('utils.batch_pipeline.pump.time.time', spy_time)
    pump = make_pump(scheduler=ScriptScheduler(store))
    await _sweep_with(pump)
    assert stamps == sorted(stamps)
    assert len(stamps) >= 2  # one for recover, one for the due probe


async def test_one_step_loss_record_per_lost_step_per_sweep(monkeypatch, caplog):
    continuation_env(monkeypatch, True)
    pump = make_pump()
    pump.scheduler.recover_script = [FirestoreContentionExhausted('storm')]
    await _sweep_with(pump)
    pump._last_recovery = 0.0
    pump.scheduler.recover_script = [FirestoreContentionExhausted('storm again')]
    await pump._maintain()
    records = [r for r in caplog.records if 'step=recover' in r.getMessage()]
    assert len(records) == 2


async def test_held_owner_drains_once_per_sweep_across_sweeps(monkeypatch):
    continuation_env(monkeypatch, True)
    pump = make_pump(held_owners=('o1',))
    await _sweep_with(pump)
    pump._last_recovery = 0.0
    await pump._maintain()
    assert pump.merge.drained == ['o1', 'o1']


# --------------------------------------------------------------------------
# Section 28: recover pass shapes
# --------------------------------------------------------------------------


async def test_recover_migrate_loss_with_no_items_is_a_clean_zero(monkeypatch, caplog):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    store.fail_calls = {0}
    assert make_scheduler(store).recover(100) == 0
    warnings = [r for r in caplog.records if 'scope=migrate' in r.getMessage()]
    assert len(warnings) == 1


async def test_recover_only_leased_items_pass(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, leased_job('l1'), leased_job('l2'))
    assert make_scheduler(store).recover(100) == 2
    assert all(store.rows[('jobs', key)]['state'] == 'retry' for key in ('l1', 'l2'))


async def test_recover_only_retry_items_pass(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('r1'), retry_job('r2'))
    assert make_scheduler(store).recover(100) == 2
    assert all(store.rows[('jobs', key)]['state'] == 'ready' for key in ('r1', 'r2'))


async def test_recover_serve_mode_quarantine_marks_the_worker_failed_reason(monkeypatch):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    monkeypatch.delenv(GATE, raising=False)
    store = RecoverStore()
    seed(store, leased_job('l1', attempt=99))
    make_scheduler(store).recover(100)
    quarantined = store.rows[('jobs', 'l1')]
    assert quarantined['failure'] == 'worker_failed'
    assert quarantined['quarantine_reason'] == 'worker_failed'


async def test_recover_quarantine_defaults_the_held_vad_evidence_to_unknown(monkeypatch):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    monkeypatch.delenv(GATE, raising=False)
    store = RecoverStore()
    seed(store, leased_job('l1', attempt=99))
    make_scheduler(store).recover(100)
    assert store.rows[('jobs', 'l1')]['measured_held_vad_speech_seconds'] is None


async def test_recover_retry_available_exactly_now_is_due(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a', available_at=100))
    assert store.due('retry', 100, 100) == ['a']
    assert make_scheduler(store).recover(100) == 1


async def test_recover_lease_exactly_now_is_expired(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, leased_job('l1', lease_until=100))
    assert store.due('leased', 100, 100) == ['l1']
    assert make_scheduler(store).recover(100) == 1


async def test_recover_leased_loss_does_not_consume_the_retry_state_budget(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, leased_job('l1'), retry_job('r1'))
    store.fail_calls = {1}
    assert make_scheduler(store).recover(100, limit=1) == 1
    assert store.rows[('jobs', 'r1')]['state'] == 'ready'


async def test_recover_every_item_losing_returns_zero_with_three_warnings(monkeypatch, caplog):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a'), retry_job('b'), retry_job('c'))
    store.fail_calls = {1, 2, 3}
    assert make_scheduler(store).recover(100) == 0
    warnings = [r for r in caplog.records if 'scope=item' in r.getMessage()]
    assert len(warnings) == 3


async def test_recover_all_losses_still_attempt_every_item(monkeypatch):
    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a'), retry_job('b'), retry_job('c'))
    store.fail_calls = {1, 2, 3}
    make_scheduler(store).recover(100)
    assert store.run_operations == [None, 'batch_recover', 'batch_recover', 'batch_recover']


async def test_recover_label_context_is_clean_after_a_legacy_abort(monkeypatch):
    from database.batch_pipeline_transaction_labels import current_operation

    recover_sweep(monkeypatch, enabled=False)
    store = RecoverStore()
    seed(store, retry_job('a'), retry_job('b'))
    store.fail_calls = {1}
    with pytest.raises(FirestoreContentionExhausted):
        make_scheduler(store).recover(100)
    assert current_operation() is None


async def test_recover_privacy_blocked_first_then_landed_items(monkeypatch):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    recover_sweep(monkeypatch)
    store = RecoverStore()
    seed(store, retry_job('a'), retry_job('b'))
    store.fail_calls = {1}
    store.fail_errors = {1: BatchPrivacyBlocked('owner deleted')}
    assert make_scheduler(store).recover(100) == 1
    assert store.quarantined_fenced == ['a']
    assert store.rows[('jobs', 'b')]['state'] == 'ready'


# --------------------------------------------------------------------------
# Section 29: flag surface registration pins
# --------------------------------------------------------------------------


def test_flag_budget_scanner_sees_the_gate_in_the_config_surface():
    from tests.unit.test_flag_budget import scan

    found = scan(patterns=('config/batch_pipeline.py',))
    assert GATE in found


def test_worker_modules_add_no_direct_env_reads_for_the_gate():
    from tests.unit.test_flag_budget import scan

    for pattern in ('utils/batch_pipeline/pump.py', 'utils/batch_pipeline/scheduler.py'):
        assert GATE not in scan(patterns=(pattern,))


def test_config_source_declares_the_gate_helper():
    source = (BACKEND / 'config' / 'batch_pipeline.py').read_text()
    assert 'def maintenance_contention_continuation_enabled()' in source


def test_gate_helper_is_importable_and_callable():
    assert callable(config_batch_pipeline.maintenance_contention_continuation_enabled)


# --------------------------------------------------------------------------
# Section 30: healthy-path outcome parity between the gates
# --------------------------------------------------------------------------


async def test_healthy_sweep_states_are_identical_under_both_gates(monkeypatch):
    final_states = []
    for enabled in (True, False):
        recover_sweep(monkeypatch, enabled)
        store = RecoverStore()
        seed(store, retry_job('a'), retry_job('b'))
        assert make_scheduler(store).recover(100) == 2
        final_states.append({key: value['state'] for (table, key), value in store.rows.items() if table == 'jobs'})
    assert final_states[0] == final_states[1]


async def test_healthy_sweep_metrics_and_clocks_identical_under_both_gates(monkeypatch):
    snapshots = []
    for enabled in (True, False):
        continuation_env(monkeypatch, enabled)
        metrics = ScriptMetrics()
        pump = make_pump(metrics=metrics)
        pump._last_metrics = 0.0
        await _sweep_with(pump)
        snapshots.append((metrics.refreshes, pump._last_recovery > 0, pump._last_metrics > 0))
    assert snapshots[0] == snapshots[1]


async def test_marker_and_held_paths_identical_under_both_gates(monkeypatch):
    releases = []
    for enabled in (True, False):
        continuation_env(monkeypatch, enabled)
        pump = make_pump(held_owners=('o1',))
        pump.merge.marked_script = [[('k1', None), ('k2', 'o1')]]
        await _sweep_with(pump)
        releases.append((list(pump.merge.released), list(pump.merge.drained)))
    assert releases[0] == releases[1]
