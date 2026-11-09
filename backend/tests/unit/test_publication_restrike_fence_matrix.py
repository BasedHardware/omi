"""Lease-fence matrix: the production fence decides every lane answer.

The lane replays the real lease-fenced ``batch_complete`` transaction against a fake store, across every job state the fence can answer: live and expired leases, wrong and absent tokens, foreign states, the idempotent ``result_ready``/``committed`` replays, the compute-admission token fence, and the missing document. A re-strike that lands on a fence rejection is the durable ``False`` answer — settled, never a lost marker — and only a live lease accepts. The ``heartbeat`` fence behind the pre-lost gate obeys the same table.

Failure-Class: FC-publication-contention-discards-completed-gpu-results
"""

import copy
import logging
import time
import types

import pytest
from google.api_core.exceptions import Aborted

import utils.batch_pipeline.pump as pump_module
from config.batch_pipeline import Priority
from database.firestore_transaction_retry import FirestoreContentionExhausted
from utils.batch_pipeline.contracts import LeasedWork, WorkItem, WorkResult
from utils.batch_pipeline.scheduler import LEASE_SECONDS, Scheduler

try:
    from utils.batch_pipeline.pump import Pump
except ImportError:
    pass

PUMP_LOGGER = 'utils.batch_pipeline.pump'
GATE = 'BATCH_PIPELINE_PUBLICATION_RESTRIKE_ENABLED'

WORK = WorkResult('seg-1', 'gs://result')
OTHER = WorkResult('seg-1', 'gs://other')


def contention(tag='fence'):
    try:
        raise Aborted(f'{tag} commit race')
    except Aborted as cause:
        error = FirestoreContentionExhausted(f'Firestore transaction contention exhausted for {tag}')
        error.__cause__ = cause
        return error


class SleepRecorder:
    def __init__(self):
        self.delays = []

    async def __call__(self, delay, *args, **kwargs):
        self.delays.append(round(delay, 6))


class FakeTx:
    def __init__(self, jobs):
        self._jobs = jobs

    def get(self, table, key):
        return copy.deepcopy(self._jobs.get(key, {}))

    def put(self, table, key, value):
        self._jobs[key] = value


class FakeStore:
    """Runs each commit against the live job dict; the script raises before a commit."""

    def __init__(self, jobs=None, script=()):
        self.jobs = jobs if jobs is not None else {}
        self.script = list(script)

    def run(self, commit):
        if self.script:
            step = self.script.pop(0)
            if isinstance(step, BaseException):
                raise step
        return commit(FakeTx(self.jobs))


def base_job(**over):
    job = {
        'state': 'leased',
        'token': 'tok-1',
        'lease_until': time.time() + LEASE_SECONDS / 2,
        'attempt': 0,
        'duration_seconds': 3.0,
    }
    job.update(over)
    return job


# (key, overrides, direct_same, direct_other)
FENCE_STATES = [
    ('leased_valid', {}, True, True),
    ('lease_dead_past', {'lease_until': time.time() - 5.0}, False, False),
    ('lease_boundary_eq', {'lease_until': time.time()}, False, False),
    ('wrong_token', {'token': 'other'}, False, False),
    ('state_retry', {'state': 'retry', 'token': ''}, False, False),
    ('state_queued', {'state': 'queued', 'token': ''}, False, False),
    ('state_quarantined', {'state': 'quarantined'}, False, False),
    ('result_ready_same', {'state': 'result_ready', 'result': WORK.to_dict()}, True, False),
    ('result_ready_other', {'state': 'result_ready', 'result': OTHER.to_dict()}, False, True),
    ('committed_same', {'state': 'committed', 'result': WORK.to_dict()}, True, False),
    ('committed_other', {'state': 'committed', 'result': OTHER.to_dict()}, False, True),
    ('missing_job', None, False, False),
    ('compute_mismatch', {'requires_compute_admission': True, 'compute_admission_token': 'other'}, False, False),
    ('compute_match', {'requires_compute_admission': True, 'compute_admission_token': 'tok-1'}, True, True),
    ('no_token_field', {'token': None, '_drop_token': True}, False, False),
]

REJECT_STATES = [key for key, _, same, _ in FENCE_STATES if not same]


def jobs_for(key, result_dict=None):
    if key == 'missing_job':
        return {}
    over = {}
    for state_key, overrides, _, _ in FENCE_STATES:
        if state_key == key:
            over = dict(overrides)
    if over.pop('_drop_token', False):
        job = base_job()
        job.pop('token', None)
        job.update({k: v for k, v in over.items() if k != '_drop_token'})
        return {'seg-1': job}
    job = base_job(**over)
    return {'seg-1': job}


def make_lease():
    item = WorkItem(
        segment_id='seg-1',
        owner_id='owner-1',
        capture_at=1.0,
        audio_uri='gs://bucket/seg',
        duration_seconds=3.0,
        priority=Priority.FRESH,
    )
    return LeasedWork(item=item, token='tok-1', attempt=1, lease_until=0.0)


def make_pump(store, script=()):
    scheduler = Scheduler(FakeStore(store, script))
    pump = Pump(
        types.SimpleNamespace(),
        types.SimpleNamespace(),
        merge=types.SimpleNamespace(),
        publish_concurrency=1,
    )
    pump.scheduler = scheduler
    sleeps = SleepRecorder()
    pump._publication_sleep = sleeps
    pump.sleeps = sleeps
    return pump


@pytest.fixture(autouse=True)
def _inline_blocking(monkeypatch):
    async def passthrough(executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(pump_module, 'run_blocking', passthrough)


async def test_fence_leased_valid_direct_answer():
    store = jobs_for('leased_valid')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is True


async def test_fence_leased_valid_direct_other_result_answer():
    store = jobs_for('leased_valid')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is True


async def test_fence_leased_valid_restruck_answer_matches_direct():
    store = jobs_for('leased_valid')
    pump = make_pump(store, script=[contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is True
    assert lost == set()  # a settled fence answer is never a lost marker


async def test_fence_leased_valid_restruck_other_result_answer_matches_direct():
    store = jobs_for('leased_valid')
    pump = make_pump(store, script=[contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is True


async def test_fence_lease_dead_past_direct_answer():
    store = jobs_for('lease_dead_past')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_lease_dead_past_direct_other_result_answer():
    store = jobs_for('lease_dead_past')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is False


async def test_fence_lease_dead_past_restruck_answer_matches_direct():
    store = jobs_for('lease_dead_past')
    pump = make_pump(store, script=[contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == set()  # a settled fence answer is never a lost marker


async def test_fence_lease_dead_past_restruck_other_result_answer_matches_direct():
    store = jobs_for('lease_dead_past')
    pump = make_pump(store, script=[contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is False


async def test_fence_lease_boundary_eq_direct_answer():
    store = jobs_for('lease_boundary_eq')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_lease_boundary_eq_direct_other_result_answer():
    store = jobs_for('lease_boundary_eq')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is False


async def test_fence_lease_boundary_eq_restruck_answer_matches_direct():
    store = jobs_for('lease_boundary_eq')
    pump = make_pump(store, script=[contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == set()  # a settled fence answer is never a lost marker


async def test_fence_lease_boundary_eq_restruck_other_result_answer_matches_direct():
    store = jobs_for('lease_boundary_eq')
    pump = make_pump(store, script=[contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is False


async def test_fence_wrong_token_direct_answer():
    store = jobs_for('wrong_token')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_wrong_token_direct_other_result_answer():
    store = jobs_for('wrong_token')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is False


async def test_fence_wrong_token_restruck_answer_matches_direct():
    store = jobs_for('wrong_token')
    pump = make_pump(store, script=[contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == set()  # a settled fence answer is never a lost marker


async def test_fence_wrong_token_restruck_other_result_answer_matches_direct():
    store = jobs_for('wrong_token')
    pump = make_pump(store, script=[contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is False


async def test_fence_state_retry_direct_answer():
    store = jobs_for('state_retry')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_state_retry_direct_other_result_answer():
    store = jobs_for('state_retry')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is False


async def test_fence_state_retry_restruck_answer_matches_direct():
    store = jobs_for('state_retry')
    pump = make_pump(store, script=[contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == set()  # a settled fence answer is never a lost marker


async def test_fence_state_retry_restruck_other_result_answer_matches_direct():
    store = jobs_for('state_retry')
    pump = make_pump(store, script=[contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is False


async def test_fence_state_queued_direct_answer():
    store = jobs_for('state_queued')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_state_queued_direct_other_result_answer():
    store = jobs_for('state_queued')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is False


async def test_fence_state_queued_restruck_answer_matches_direct():
    store = jobs_for('state_queued')
    pump = make_pump(store, script=[contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == set()  # a settled fence answer is never a lost marker


async def test_fence_state_queued_restruck_other_result_answer_matches_direct():
    store = jobs_for('state_queued')
    pump = make_pump(store, script=[contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is False


async def test_fence_state_quarantined_direct_answer():
    store = jobs_for('state_quarantined')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_state_quarantined_direct_other_result_answer():
    store = jobs_for('state_quarantined')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is False


async def test_fence_state_quarantined_restruck_answer_matches_direct():
    store = jobs_for('state_quarantined')
    pump = make_pump(store, script=[contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == set()  # a settled fence answer is never a lost marker


async def test_fence_state_quarantined_restruck_other_result_answer_matches_direct():
    store = jobs_for('state_quarantined')
    pump = make_pump(store, script=[contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is False


async def test_fence_result_ready_same_direct_answer():
    store = jobs_for('result_ready_same')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is True


async def test_fence_result_ready_same_direct_other_result_answer():
    store = jobs_for('result_ready_same')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is False


async def test_fence_result_ready_same_restruck_answer_matches_direct():
    store = jobs_for('result_ready_same')
    pump = make_pump(store, script=[contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is True
    assert lost == set()  # a settled fence answer is never a lost marker


async def test_fence_result_ready_same_restruck_other_result_answer_matches_direct():
    store = jobs_for('result_ready_same')
    pump = make_pump(store, script=[contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is False


async def test_fence_result_ready_other_direct_answer():
    store = jobs_for('result_ready_other')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_result_ready_other_direct_other_result_answer():
    store = jobs_for('result_ready_other')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is True


async def test_fence_result_ready_other_restruck_answer_matches_direct():
    store = jobs_for('result_ready_other')
    pump = make_pump(store, script=[contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == set()  # a settled fence answer is never a lost marker


async def test_fence_result_ready_other_restruck_other_result_answer_matches_direct():
    store = jobs_for('result_ready_other')
    pump = make_pump(store, script=[contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is True


async def test_fence_committed_same_direct_answer():
    store = jobs_for('committed_same')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is True


async def test_fence_committed_same_direct_other_result_answer():
    store = jobs_for('committed_same')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is False


async def test_fence_committed_same_restruck_answer_matches_direct():
    store = jobs_for('committed_same')
    pump = make_pump(store, script=[contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is True
    assert lost == set()  # a settled fence answer is never a lost marker


async def test_fence_committed_same_restruck_other_result_answer_matches_direct():
    store = jobs_for('committed_same')
    pump = make_pump(store, script=[contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is False


async def test_fence_committed_other_direct_answer():
    store = jobs_for('committed_other')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_committed_other_direct_other_result_answer():
    store = jobs_for('committed_other')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is True


async def test_fence_committed_other_restruck_answer_matches_direct():
    store = jobs_for('committed_other')
    pump = make_pump(store, script=[contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == set()  # a settled fence answer is never a lost marker


async def test_fence_committed_other_restruck_other_result_answer_matches_direct():
    store = jobs_for('committed_other')
    pump = make_pump(store, script=[contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is True


async def test_fence_missing_job_direct_answer():
    store = jobs_for('missing_job')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_missing_job_direct_other_result_answer():
    store = jobs_for('missing_job')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is False


async def test_fence_missing_job_restruck_answer_matches_direct():
    store = jobs_for('missing_job')
    pump = make_pump(store, script=[contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == set()  # a settled fence answer is never a lost marker


async def test_fence_missing_job_restruck_other_result_answer_matches_direct():
    store = jobs_for('missing_job')
    pump = make_pump(store, script=[contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is False


async def test_fence_compute_mismatch_direct_answer():
    store = jobs_for('compute_mismatch')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_compute_mismatch_direct_other_result_answer():
    store = jobs_for('compute_mismatch')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is False


async def test_fence_compute_mismatch_restruck_answer_matches_direct():
    store = jobs_for('compute_mismatch')
    pump = make_pump(store, script=[contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == set()  # a settled fence answer is never a lost marker


async def test_fence_compute_mismatch_restruck_other_result_answer_matches_direct():
    store = jobs_for('compute_mismatch')
    pump = make_pump(store, script=[contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is False


async def test_fence_compute_match_direct_answer():
    store = jobs_for('compute_match')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is True


async def test_fence_compute_match_direct_other_result_answer():
    store = jobs_for('compute_match')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is True


async def test_fence_compute_match_restruck_answer_matches_direct():
    store = jobs_for('compute_match')
    pump = make_pump(store, script=[contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is True
    assert lost == set()  # a settled fence answer is never a lost marker


async def test_fence_compute_match_restruck_other_result_answer_matches_direct():
    store = jobs_for('compute_match')
    pump = make_pump(store, script=[contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is True


async def test_fence_no_token_field_direct_answer():
    store = jobs_for('no_token_field')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_no_token_field_direct_other_result_answer():
    store = jobs_for('no_token_field')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is False


async def test_fence_no_token_field_restruck_answer_matches_direct():
    store = jobs_for('no_token_field')
    pump = make_pump(store, script=[contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == set()  # a settled fence answer is never a lost marker


async def test_fence_no_token_field_restruck_other_result_answer_matches_direct():
    store = jobs_for('no_token_field')
    pump = make_pump(store, script=[contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is False


async def test_fence_reject_lease_dead_past_settles_false_at_every_position(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    for script in ([contention()], [contention(), contention()], [contention(), contention(), contention()]):
        caplog.clear()
        store = jobs_for('lease_dead_past')
        pump = make_pump(store, script=list(script))
        lost = set()
        accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
        assert accepted is False
        assert lost == set()
        assert pump.sleeps.delays == [0.25 * (2**n) for n in range(len(script))]


async def test_fence_reject_lease_boundary_eq_settles_false_at_every_position(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    for script in ([contention()], [contention(), contention()], [contention(), contention(), contention()]):
        caplog.clear()
        store = jobs_for('lease_boundary_eq')
        pump = make_pump(store, script=list(script))
        lost = set()
        accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
        assert accepted is False
        assert lost == set()
        assert pump.sleeps.delays == [0.25 * (2**n) for n in range(len(script))]


async def test_fence_reject_wrong_token_settles_false_at_every_position(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    for script in ([contention()], [contention(), contention()], [contention(), contention(), contention()]):
        caplog.clear()
        store = jobs_for('wrong_token')
        pump = make_pump(store, script=list(script))
        lost = set()
        accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
        assert accepted is False
        assert lost == set()
        assert pump.sleeps.delays == [0.25 * (2**n) for n in range(len(script))]


async def test_fence_reject_state_retry_settles_false_at_every_position(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    for script in ([contention()], [contention(), contention()], [contention(), contention(), contention()]):
        caplog.clear()
        store = jobs_for('state_retry')
        pump = make_pump(store, script=list(script))
        lost = set()
        accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
        assert accepted is False
        assert lost == set()
        assert pump.sleeps.delays == [0.25 * (2**n) for n in range(len(script))]


async def test_fence_reject_state_queued_settles_false_at_every_position(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    for script in ([contention()], [contention(), contention()], [contention(), contention(), contention()]):
        caplog.clear()
        store = jobs_for('state_queued')
        pump = make_pump(store, script=list(script))
        lost = set()
        accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
        assert accepted is False
        assert lost == set()
        assert pump.sleeps.delays == [0.25 * (2**n) for n in range(len(script))]


async def test_fence_reject_state_quarantined_settles_false_at_every_position(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    for script in ([contention()], [contention(), contention()], [contention(), contention(), contention()]):
        caplog.clear()
        store = jobs_for('state_quarantined')
        pump = make_pump(store, script=list(script))
        lost = set()
        accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
        assert accepted is False
        assert lost == set()
        assert pump.sleeps.delays == [0.25 * (2**n) for n in range(len(script))]


async def test_fence_reject_result_ready_other_settles_false_at_every_position(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    for script in ([contention()], [contention(), contention()], [contention(), contention(), contention()]):
        caplog.clear()
        store = jobs_for('result_ready_other')
        pump = make_pump(store, script=list(script))
        lost = set()
        accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
        assert accepted is False
        assert lost == set()
        assert pump.sleeps.delays == [0.25 * (2**n) for n in range(len(script))]


async def test_fence_reject_committed_other_settles_false_at_every_position(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    for script in ([contention()], [contention(), contention()], [contention(), contention(), contention()]):
        caplog.clear()
        store = jobs_for('committed_other')
        pump = make_pump(store, script=list(script))
        lost = set()
        accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
        assert accepted is False
        assert lost == set()
        assert pump.sleeps.delays == [0.25 * (2**n) for n in range(len(script))]


async def test_fence_reject_missing_job_settles_false_at_every_position(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    for script in ([contention()], [contention(), contention()], [contention(), contention(), contention()]):
        caplog.clear()
        store = jobs_for('missing_job')
        pump = make_pump(store, script=list(script))
        lost = set()
        accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
        assert accepted is False
        assert lost == set()
        assert pump.sleeps.delays == [0.25 * (2**n) for n in range(len(script))]


async def test_fence_reject_compute_mismatch_settles_false_at_every_position(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    for script in ([contention()], [contention(), contention()], [contention(), contention(), contention()]):
        caplog.clear()
        store = jobs_for('compute_mismatch')
        pump = make_pump(store, script=list(script))
        lost = set()
        accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
        assert accepted is False
        assert lost == set()
        assert pump.sleeps.delays == [0.25 * (2**n) for n in range(len(script))]


async def test_fence_reject_no_token_field_settles_false_at_every_position(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    for script in ([contention()], [contention(), contention()], [contention(), contention(), contention()]):
        caplog.clear()
        store = jobs_for('no_token_field')
        pump = make_pump(store, script=list(script))
        lost = set()
        accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
        assert accepted is False
        assert lost == set()
        assert pump.sleeps.delays == [0.25 * (2**n) for n in range(len(script))]


async def test_fence_reject_state_is_never_written_by_the_lane(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    store = jobs_for('wrong_token')
    original = dict(store['seg-1'])
    pump = make_pump(store, script=[contention()])
    await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert store['seg-1'] == original


async def test_fence_leased_valid_exhausted_lane_marks_lost_and_keeps_the_job():
    store = jobs_for('leased_valid')
    pump = make_pump(store, script=[contention(), contention(), contention(), contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert store['seg-1']['state'] == 'leased'  # the exhausted lane wrote nothing
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]


async def test_fence_accepted_completion_writes_result_ready():
    store = jobs_for('leased_valid')
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is True
    assert store['seg-1']['state'] == 'result_ready'
    assert WORK.matches_persisted(store['seg-1']['result'])


async def test_fence_idempotent_state_is_never_rewritten_by_a_foreign_result():
    store = jobs_for('result_ready_same')
    original = dict(store['seg-1'])
    pump = make_pump(store)
    accepted = await pump._publish(make_lease(), {'seg-1': OTHER}, set())
    assert accepted is False
    assert store['seg-1'] == original


async def test_prelost_gate_heartbeat_live_publishes():
    store = jobs_for('leased_valid')
    pump = make_pump(store)
    lost = {'seg-1'}
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is True
    assert lost == set()


async def test_prelost_gate_heartbeat_dead_leaves_the_segment_lost():
    store = jobs_for('lease_dead_past')
    pump = make_pump(store)
    lost = {'seg-1'}
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == {'seg-1'}


async def test_prelost_gate_heartbeat_refuses_a_foreign_token():
    store = jobs_for('wrong_token')
    pump = make_pump(store)
    lost = {'seg-1'}
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == {'seg-1'}


async def test_prelost_gate_heartbeat_refuses_a_missing_job():
    store = jobs_for('missing_job')
    pump = make_pump(store)
    lost = {'seg-1'}
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == {'seg-1'}


async def test_prelost_gate_heartbeat_extends_the_live_lease():
    store = jobs_for('leased_valid')
    built_at = store['seg-1']['lease_until']
    pump = make_pump(store)
    await pump._publish(make_lease(), {'seg-1': WORK}, {'seg-1'})
    assert store['seg-1']['lease_until'] >= built_at


async def test_fence_leased_valid_exhausted_lane_is_terminal():
    store = jobs_for('leased_valid')
    pump = make_pump(store, script=[contention(), contention(), contention(), contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == {"seg-1"}


async def test_fence_leased_valid_lose2_restruck_answer_matches_direct():
    store = jobs_for('leased_valid')
    pump = make_pump(store, script=[contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is True


async def test_fence_leased_valid_lose3_restruck_answer_matches_direct():
    store = jobs_for('leased_valid')
    pump = make_pump(store, script=[contention(), contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is True


async def test_fence_lease_dead_past_exhausted_lane_is_terminal():
    store = jobs_for('lease_dead_past')
    pump = make_pump(store, script=[contention(), contention(), contention(), contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == {"seg-1"}


async def test_fence_lease_dead_past_lose2_restruck_answer_matches_direct():
    store = jobs_for('lease_dead_past')
    pump = make_pump(store, script=[contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_lease_dead_past_lose3_restruck_answer_matches_direct():
    store = jobs_for('lease_dead_past')
    pump = make_pump(store, script=[contention(), contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_lease_boundary_eq_exhausted_lane_is_terminal():
    store = jobs_for('lease_boundary_eq')
    pump = make_pump(store, script=[contention(), contention(), contention(), contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == {"seg-1"}


async def test_fence_lease_boundary_eq_lose2_restruck_answer_matches_direct():
    store = jobs_for('lease_boundary_eq')
    pump = make_pump(store, script=[contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_lease_boundary_eq_lose3_restruck_answer_matches_direct():
    store = jobs_for('lease_boundary_eq')
    pump = make_pump(store, script=[contention(), contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_wrong_token_exhausted_lane_is_terminal():
    store = jobs_for('wrong_token')
    pump = make_pump(store, script=[contention(), contention(), contention(), contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == {"seg-1"}


async def test_fence_wrong_token_lose2_restruck_answer_matches_direct():
    store = jobs_for('wrong_token')
    pump = make_pump(store, script=[contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_wrong_token_lose3_restruck_answer_matches_direct():
    store = jobs_for('wrong_token')
    pump = make_pump(store, script=[contention(), contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_state_retry_exhausted_lane_is_terminal():
    store = jobs_for('state_retry')
    pump = make_pump(store, script=[contention(), contention(), contention(), contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == {"seg-1"}


async def test_fence_state_retry_lose2_restruck_answer_matches_direct():
    store = jobs_for('state_retry')
    pump = make_pump(store, script=[contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_state_retry_lose3_restruck_answer_matches_direct():
    store = jobs_for('state_retry')
    pump = make_pump(store, script=[contention(), contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_state_queued_exhausted_lane_is_terminal():
    store = jobs_for('state_queued')
    pump = make_pump(store, script=[contention(), contention(), contention(), contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == {"seg-1"}


async def test_fence_state_queued_lose2_restruck_answer_matches_direct():
    store = jobs_for('state_queued')
    pump = make_pump(store, script=[contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_state_queued_lose3_restruck_answer_matches_direct():
    store = jobs_for('state_queued')
    pump = make_pump(store, script=[contention(), contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_state_quarantined_exhausted_lane_is_terminal():
    store = jobs_for('state_quarantined')
    pump = make_pump(store, script=[contention(), contention(), contention(), contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == {"seg-1"}


async def test_fence_state_quarantined_lose2_restruck_answer_matches_direct():
    store = jobs_for('state_quarantined')
    pump = make_pump(store, script=[contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_state_quarantined_lose3_restruck_answer_matches_direct():
    store = jobs_for('state_quarantined')
    pump = make_pump(store, script=[contention(), contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_result_ready_same_exhausted_lane_is_terminal():
    store = jobs_for('result_ready_same')
    pump = make_pump(store, script=[contention(), contention(), contention(), contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == {"seg-1"}


async def test_fence_result_ready_same_lose2_restruck_answer_matches_direct():
    store = jobs_for('result_ready_same')
    pump = make_pump(store, script=[contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is True


async def test_fence_result_ready_same_lose3_restruck_answer_matches_direct():
    store = jobs_for('result_ready_same')
    pump = make_pump(store, script=[contention(), contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is True


async def test_fence_result_ready_other_exhausted_lane_is_terminal():
    store = jobs_for('result_ready_other')
    pump = make_pump(store, script=[contention(), contention(), contention(), contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == {"seg-1"}


async def test_fence_result_ready_other_lose2_restruck_answer_matches_direct():
    store = jobs_for('result_ready_other')
    pump = make_pump(store, script=[contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_result_ready_other_lose3_restruck_answer_matches_direct():
    store = jobs_for('result_ready_other')
    pump = make_pump(store, script=[contention(), contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_committed_same_exhausted_lane_is_terminal():
    store = jobs_for('committed_same')
    pump = make_pump(store, script=[contention(), contention(), contention(), contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == {"seg-1"}


async def test_fence_committed_same_lose2_restruck_answer_matches_direct():
    store = jobs_for('committed_same')
    pump = make_pump(store, script=[contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is True


async def test_fence_committed_same_lose3_restruck_answer_matches_direct():
    store = jobs_for('committed_same')
    pump = make_pump(store, script=[contention(), contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is True


async def test_fence_committed_other_exhausted_lane_is_terminal():
    store = jobs_for('committed_other')
    pump = make_pump(store, script=[contention(), contention(), contention(), contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == {"seg-1"}


async def test_fence_committed_other_lose2_restruck_answer_matches_direct():
    store = jobs_for('committed_other')
    pump = make_pump(store, script=[contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_committed_other_lose3_restruck_answer_matches_direct():
    store = jobs_for('committed_other')
    pump = make_pump(store, script=[contention(), contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_missing_job_exhausted_lane_is_terminal():
    store = jobs_for('missing_job')
    pump = make_pump(store, script=[contention(), contention(), contention(), contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == {"seg-1"}


async def test_fence_missing_job_lose2_restruck_answer_matches_direct():
    store = jobs_for('missing_job')
    pump = make_pump(store, script=[contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_missing_job_lose3_restruck_answer_matches_direct():
    store = jobs_for('missing_job')
    pump = make_pump(store, script=[contention(), contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_compute_mismatch_exhausted_lane_is_terminal():
    store = jobs_for('compute_mismatch')
    pump = make_pump(store, script=[contention(), contention(), contention(), contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == {"seg-1"}


async def test_fence_compute_mismatch_lose2_restruck_answer_matches_direct():
    store = jobs_for('compute_mismatch')
    pump = make_pump(store, script=[contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_compute_mismatch_lose3_restruck_answer_matches_direct():
    store = jobs_for('compute_mismatch')
    pump = make_pump(store, script=[contention(), contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_compute_match_exhausted_lane_is_terminal():
    store = jobs_for('compute_match')
    pump = make_pump(store, script=[contention(), contention(), contention(), contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == {"seg-1"}


async def test_fence_compute_match_lose2_restruck_answer_matches_direct():
    store = jobs_for('compute_match')
    pump = make_pump(store, script=[contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is True


async def test_fence_compute_match_lose3_restruck_answer_matches_direct():
    store = jobs_for('compute_match')
    pump = make_pump(store, script=[contention(), contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is True


async def test_fence_no_token_field_exhausted_lane_is_terminal():
    store = jobs_for('no_token_field')
    pump = make_pump(store, script=[contention(), contention(), contention(), contention()])
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, lost)
    assert accepted is False
    assert lost == {"seg-1"}


async def test_fence_no_token_field_lose2_restruck_answer_matches_direct():
    store = jobs_for('no_token_field')
    pump = make_pump(store, script=[contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False


async def test_fence_no_token_field_lose3_restruck_answer_matches_direct():
    store = jobs_for('no_token_field')
    pump = make_pump(store, script=[contention(), contention(), contention()])
    accepted = await pump._publish(make_lease(), {'seg-1': WORK}, set())
    assert accepted is False
