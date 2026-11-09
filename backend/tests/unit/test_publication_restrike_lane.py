"""The bounded publication re-strike lane (``batch_completion`` contention family).

A publication transition that exhausts its store-level five-attempt contention
budget used to discard a completed GPU result: the pump marked the segment
lost, the lease expired, and lease recovery re-leased the unit for a full GPU
re-run — the prod signature ``event=batch_completion outcome=retry
exception_type=FirestoreContentionExhausted`` (x27/30m) plus the wasted
inference pass behind each line. The lane (``Pump._restrike_publication``)
replays the same lease-fenced transition with the documented doubling backoff
before that fallback.

This suite pins the lane end to end: landing a lost completion, the delay
schedule, the attempt cap, the contention-only gate, lease-fence rejections,
every transition kind, flag-off parity, and the log taxonomy.

Failure-Class: FC-publication-contention-discards-completed-gpu-results
"""

import logging
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
from utils.batch_pipeline.contracts import (
    FailedWork,
    HeldWork,
    LeasedWork,
    RecoveryWork,
    ValidationFailureWork,
    WorkItem,
    WorkResult,
)
from utils.batch_pipeline.pump import Pump, publication_loss_is_contention, publication_restrike_delay

try:
    from utils.batch_pipeline.pump import (
        PUBLICATION_RESTRIKE_BASE_SECONDS,
        PUBLICATION_RESTRIKE_MAX_ATTEMPTS,
        PUBLICATION_RESTRIKE_MAX_SECONDS,
    )
except ImportError:  # parent revisions without the lane fail at runtime — the RED half
    pass

GATE = 'BATCH_PIPELINE_PUBLICATION_RESTRIKE_ENABLED'
PUMP_LOGGER = 'utils.batch_pipeline.pump'


# ---------------------------------------------------------------------------
# Harnesses
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


def make_pump(scheduler=None, **overrides):
    pump = Pump(
        types.SimpleNamespace(),
        types.SimpleNamespace(),
        merge=types.SimpleNamespace(),
        publish_concurrency=overrides.pop('publish_concurrency', 1),
    )
    pump.scheduler = scheduler or ScriptScheduler()
    sleeps = SleepRecorder()
    pump._publication_sleep = sleeps
    pump.sleeps = sleeps
    for name, value in overrides.items():
        setattr(pump, name, value)
    return pump


def contention_loss(tag='synthetic_publication'):
    """A FirestoreContentionExhausted chained to a real Aborted.

    The same shape the store's retry chain raises after its budget spends:
    the lane must classify the instance and its cause chain identically.
    """

    try:
        raise Aborted(f'{tag} commit race')
    except Aborted as cause:
        error = FirestoreContentionExhausted(f'Firestore transaction contention exhausted for {tag}')
        error.__cause__ = cause
        return error


def chain_exhaustion(operation_name='synthetic_publication'):
    """Raise a real FirestoreContentionExhausted from the production retry chain.

    Used as a callable script step: the exhaustion must propagate with its
    traceback ending in ``firestore_transaction_retry.py`` so classification
    is exercised against the real raise site, not a hand-built instance.
    """

    def operation(tx):
        raise Aborted(f'{operation_name} commit contention')

    run_with_transaction_contention_retry(
        lambda: object(), operation, operation_name=operation_name, max_attempts=1, sleep=lambda seconds: None
    )


def events(caplog, token):
    return [r.getMessage() for r in caplog.records if token in r.getMessage()]


def error_lines(caplog):
    return [r for r in caplog.records if 'event=batch_completion outcome=retry' in r.getMessage()]


# ---------------------------------------------------------------------------
# The lane lands a lost completion
# ---------------------------------------------------------------------------


async def test_contention_loss_is_restruck_and_lands(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    first = contention_loss('first_attempt')
    scheduler = ScriptScheduler(complete=[first])
    pump = make_pump(scheduler)
    lease = make_lease()
    accepted = await pump._publish(lease, {'seg-1': WorkResult('seg-1', 'gs://result')}, set())
    assert accepted is True
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 2
    assert pump.sleeps.delays == [0.25]


async def test_landed_restrike_drains_the_owner_like_any_accepted_publication(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('attempt_one')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, lost)
    assert accepted is True
    assert lost == set()


async def test_second_restrike_lands_with_doubled_delays(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b')])
    pump = make_pump(scheduler)
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert accepted is True
    assert pump.sleeps.delays == [0.25, 0.5]


async def test_third_restrike_lands_with_the_third_delay(caplog):
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert accepted is True
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]


async def test_lane_cap_falls_back_to_the_legacy_catch_site(caplog, capsys):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    losses = [contention_loss(f'attempt_{n}') for n in range(4)]
    scheduler = ScriptScheduler(complete=list(losses))
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 4  # initial + cap re-strikes
    assert pump.sleeps.delays == [0.25, 0.5, 1.0]
    assert len(error_lines(caplog)) == 1


async def test_terminal_error_line_keeps_the_legacy_event_and_last_exception(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    losses = [contention_loss(tag) for tag in ('a', 'b', 'c', 'd')]
    scheduler = ScriptScheduler(complete=losses)
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    message = error_lines(caplog)[0].getMessage()
    assert message == 'event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted'


async def test_no_restrike_events_on_a_clean_publication(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler()
    pump = make_pump(scheduler)
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert accepted is True
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


# ---------------------------------------------------------------------------
# The contention-only gate
# ---------------------------------------------------------------------------


async def test_non_contention_loss_never_restrikes(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[ValueError('revoked')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 1
    assert pump.sleeps.delays == []
    assert events(caplog, 'restrike') == []


async def test_non_contention_on_the_first_restrike_aborts_the_lane(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), ValueError('revoked_later')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 2
    message = error_lines(caplog)[0].getMessage()
    assert 'exception_type=ValueError' in message


async def test_chained_aborted_contention_classifies_and_restrikes(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('chained')])
    pump = make_pump(scheduler)
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert accepted is True


async def test_postgres_job_store_exhaustion_classifies_and_restrikes():
    scheduler = ScriptScheduler(complete=[JobStoreContentionExhausted('pg budget spent')])
    pump = make_pump(scheduler)
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert accepted is True


# ---------------------------------------------------------------------------
# The lease fence decides, not the lane
# ---------------------------------------------------------------------------


async def test_restrike_rejected_by_a_dead_lease_is_the_durable_answer():
    scheduler = ScriptScheduler(complete=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, lost)
    assert accepted is False
    assert lost == set()  # the fence said no; no lost marker, recovery owns it


async def test_restrike_rejection_commits_the_false_answer(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), False])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    committed = [m for m in events(caplog, 'restrike_committed') if 'accepted=false' in m]
    assert len(committed) == 1


async def test_restrike_uses_the_same_segment_and_token_as_the_lost_attempt():
    scheduler = ScriptScheduler(complete=[contention_loss('a')])
    pump = make_pump(scheduler)
    lease = make_lease(segment='seg-9', token='tok-9')
    await pump._publish(lease, {'seg-9': WorkResult('seg-9', 'gs://r')}, set())
    completes = [c for c in scheduler.calls if c[0] == 'complete']
    assert completes == [('complete', 'seg-9', 'tok-9'), ('complete', 'seg-9', 'tok-9')]


# ---------------------------------------------------------------------------
# Every transition kind rides the lane
# ---------------------------------------------------------------------------


async def test_held_defer_restrikes_and_keeps_the_false_answer(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(defer=[contention_loss('a')])
    pump = make_pump(scheduler)
    result_map = {'seg-1': HeldWork('seg-1', retry_after=60, reason='cap_hold')}
    accepted = await pump._publish(make_lease(), result_map, set())
    assert accepted is False  # HeldWork publishes False on success, like the legacy path
    assert len([c for c in scheduler.calls if c[0] == 'defer']) == 2


async def test_validation_failure_restrike_lands(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    result_map = {'seg-1': ValidationFailureWork('seg-1', 'fetch_decode', 'staged_audio_invalid', 1.5, {'v': 1})}
    accepted = await pump._publish(make_lease(), result_map, set())
    assert accepted is True
    calls = [c for c in scheduler.calls if c[0] == 'fail']
    assert len(calls) == 2
    assert calls[0][3]['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}


async def test_recovery_handoff_restrike_lands(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    result_map = {'seg-1': RecoveryWork('seg-1', reason='empty_asr', measured_held_vad_speech_seconds=2.0)}
    accepted = await pump._publish(make_lease(), result_map, set())
    assert accepted is True
    calls = [c for c in scheduler.calls if c[0] == 'fail']
    assert calls[0][3]['quarantine'] is True
    assert calls[0][3]['worker_failure'] == {'stage': 'assemble_words', 'reason': 'empty_asr'}


async def test_failed_work_restrike_lands(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    result_map = {'seg-1': FailedWork('seg-1', 1.0, {'v': 1}, {'stage': 'vad_windows', 'reason': 'vad_bounds'})}
    accepted = await pump._publish(make_lease(), result_map, set())
    assert accepted is True
    calls = [c for c in scheduler.calls if c[0] == 'fail']
    assert calls[0][3]['worker_failure_evidence'] == {'stage': 'vad_windows', 'reason': 'vad_bounds'}


async def test_missing_result_restrike_lands(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(fail=[contention_loss('a')])
    pump = make_pump(scheduler)
    accepted = await pump._publish(make_lease(), {}, set())
    assert accepted is True
    assert len([c for c in scheduler.calls if c[0] == 'fail']) == 2


async def test_lane_cap_on_a_failure_transition_keeps_the_legacy_catch(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    losses = [contention_loss(f'a{n}') for n in range(4)]
    scheduler = ScriptScheduler(fail=list(losses))
    pump = make_pump(scheduler)
    lost = set()
    result_map = {'seg-1': FailedWork('seg-1')}
    accepted = await pump._publish(make_lease(), result_map, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len(error_lines(caplog)) == 1


# ---------------------------------------------------------------------------
# Flag-off parity: the legacy catch site, byte for byte
# ---------------------------------------------------------------------------


@pytest.fixture
def gate_off(monkeypatch):
    monkeypatch.setenv(GATE, 'false')
    monkeypatch.setattr(pump_module, 'publication_restrike_enabled', lambda: False)


async def test_flag_off_contention_loss_is_immediately_lost(gate_off, caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert len([c for c in scheduler.calls if c[0] == 'complete']) == 1
    assert pump.sleeps.delays == []


async def test_flag_off_logs_no_restrike_events(gate_off, caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert events(caplog, 'restrike') == []
    assert len(error_lines(caplog)) == 1


async def test_flag_off_non_contention_parity(gate_off, caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[KeyError('boom')])
    pump = make_pump(scheduler)
    lost = set()
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    message = error_lines(caplog)[0].getMessage()
    assert message == 'event=batch_completion outcome=retry exception_type=KeyError'


# ---------------------------------------------------------------------------
# The lost-set pre-check keeps its legacy shape
# ---------------------------------------------------------------------------


async def test_prelost_segment_with_a_live_heartbeat_publishes_after_the_gate():
    scheduler = ScriptScheduler()
    pump = make_pump(scheduler)
    lost = {'seg-1'}
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, lost)
    assert accepted is True
    assert lost == set()
    assert ('heartbeat', 'seg-1', 'tok-1') in scheduler.calls


async def test_prelost_segment_with_a_dead_heartbeat_returns_false_before_publishing():
    scheduler = ScriptScheduler(heartbeat=False)
    pump = make_pump(scheduler)
    lost = {'seg-1'}
    accepted = await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}
    assert [c for c in scheduler.calls if c[0] == 'complete'] == []


# ---------------------------------------------------------------------------
# Delay schedule and constants
# ---------------------------------------------------------------------------


def test_delay_constants_are_the_documented_lane_shape():
    assert PUBLICATION_RESTRIKE_BASE_SECONDS == 0.25
    assert PUBLICATION_RESTRIKE_MAX_SECONDS == 2.0
    assert PUBLICATION_RESTRIKE_MAX_ATTEMPTS == 3


def test_delay_ladder_is_doubling_and_capped():
    assert [publication_restrike_delay(n) for n in (1, 2, 3)] == [0.25, 0.5, 1.0]
    assert publication_restrike_delay(4) == 2.0
    assert publication_restrike_delay(99) == 2.0


def test_whole_lane_stays_under_the_lease_window():
    from utils.batch_pipeline.scheduler import LEASE_SECONDS

    total = sum(publication_restrike_delay(n) for n in range(1, PUBLICATION_RESTRIKE_MAX_ATTEMPTS + 1))
    assert total < LEASE_SECONDS / 10


def test_gate_defaults_on_without_env(monkeypatch):
    monkeypatch.delenv(GATE, raising=False)
    assert pump_module.publication_restrike_enabled() is True


def test_gate_false_is_the_kill_switch(monkeypatch):
    monkeypatch.setenv(GATE, 'false')
    assert pump_module.publication_restrike_enabled() is False


def test_gate_tolerant_of_env_noise(monkeypatch):
    for value, expected in (
        ('', True),
        ('true', True),
        ('TRUE', True),
        ('1', True),
        ('0', True),
        ('false', False),
        ('False', False),
    ):
        monkeypatch.setenv(GATE, value)
        assert pump_module.publication_restrike_enabled() is expected, value


# ---------------------------------------------------------------------------
# Classification matrix (spot checks; the grid file pins the full taxonomy)
# ---------------------------------------------------------------------------


def test_classification_accepts_the_budget_exception():
    assert publication_loss_is_contention(FirestoreContentionExhausted('spent')) is True


def test_classification_accepts_the_postgres_subclass():
    assert publication_loss_is_contention(JobStoreContentionExhausted('spent')) is True


def test_classification_accepts_a_chained_aborted():
    assert publication_loss_is_contention(contention_loss('chained')) is True


def test_classification_accepts_a_direct_aborted():
    assert publication_loss_is_contention(Aborted('commit race')) is True


def test_classification_refuses_everyday_exceptions():
    assert publication_loss_is_contention(ValueError('no')) is False
    assert publication_loss_is_contention(KeyError('no')) is False
    assert publication_loss_is_contention(RuntimeError('no')) is False


def test_classification_refuses_a_plain_timeout_error():
    assert publication_loss_is_contention(TimeoutError('slow')) is False


# ---------------------------------------------------------------------------
# Lane telemetry shape
# ---------------------------------------------------------------------------


async def test_restrike_wait_carries_attempt_delay_and_exception(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a'), contention_loss('b'), contention_loss('c')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    waits = events(caplog, 'outcome=restrike_wait')
    assert waits == [
        'event=batch_publication outcome=restrike_wait attempt=1 delay_ms=250 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=2 delay_ms=500 exception_type=FirestoreContentionExhausted',
        'event=batch_publication outcome=restrike_wait attempt=3 delay_ms=1000 exception_type=FirestoreContentionExhausted',
    ]


async def test_restrike_committed_reports_attempt_and_acceptance(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert events(caplog, 'outcome=restrike_committed') == [
        'event=batch_publication outcome=restrike_committed attempt=1 accepted=true'
    ]


async def test_terminal_loss_emits_no_committed_event(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss(f'n{n}') for n in range(4)])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    assert events(caplog, 'outcome=restrike_committed') == []


async def test_lane_events_are_info_severity(caplog):
    import logging as logging_module

    caplog.set_level(logging_module.INFO, logger=PUMP_LOGGER)
    scheduler = ScriptScheduler(complete=[contention_loss('a')])
    pump = make_pump(scheduler)
    await pump._publish(make_lease(), {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    restrikes = [r for r in caplog.records if 'restrike' in r.getMessage()]
    assert restrikes
    assert all(r.levelno == logging_module.INFO for r in restrikes)


# ---------------------------------------------------------------------------
# The lane inside a flight
# ---------------------------------------------------------------------------


async def test_publish_flight_drains_after_a_restruck_publication(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)

    class DrainMerge:
        def __init__(self):
            self.drained = []

        def commit_next(self, owner_id, now):
            self.drained.append(owner_id)
            return None

    merge = DrainMerge()
    scheduler = ScriptScheduler(complete=[contention_loss('a')])
    pump = make_pump(scheduler, merge=merge)
    pump.merge = merge
    lease = make_lease()
    await pump._publish_flight([lease], {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r')}, set())
    assert merge.drained == ['owner-1']


async def test_publish_flight_does_not_drain_a_terminal_lane_loss(caplog):
    caplog.set_level(logging.INFO, logger=PUMP_LOGGER)

    class DrainMerge:
        def __init__(self):
            self.drained = []

        def commit_next(self, owner_id, now):
            self.drained.append(owner_id)
            return None

    merge = DrainMerge()
    scheduler = ScriptScheduler(complete=[contention_loss(f'n{n}') for n in range(4)])
    pump = make_pump(scheduler, merge=merge)
    pump.merge = merge
    lease = make_lease()
    lost = set()
    await pump._publish_flight([lease], {lease.item.segment_id: WorkResult(lease.item.segment_id, 'gs://r')}, lost)
    assert merge.drained == []
    assert lost == {'seg-1'}
