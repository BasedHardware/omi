"""Shared cell harness for the purge storm-gate grids.

Each grid cell drives one real boundary — ``run_purge_transaction``'s storm
gate (entry consult, mid-ladder peek/wave spacing, exhaustion stamp, success
clearing) behind the injected damper — and freezes the observables the grid
tests compare as literals. The engine under test is the production one —
``run_with_transaction_contention_retry`` — with only the wall-clock edges
pinned (sleep is recorded, never slept; the equal-jitter draw is pinned to
0.5), so rung waits are exact floats. The purge helper imports the engine at
call time, so pinning the engine module attribute binds every lane.

``model_cell`` is the independent hand-transcribed expectation walk: it
predicts every observable from the source predicates and the retry engine's
documented accounting (one fresh transaction per outer attempt; equal-jitter
rungs at the pinned draw; the gate consults once per rung that will be
retried and never before the first attempt; the wave wait engages from the
third failed attempt and never shortens a deeper residual; a hostile damper
answer collapses the rung to the bare schedule; the entry consult sleeps
through the damper's own sleeper, outside the engine's recorder; the attempt
cap raises the typed exhaustion and stamps the damper's arm window onto
``retry_after``; a success clears the ladder with the entry generation; a
dormant damper leaves every observable on the bare ladder). The emitter that
generated the grid files aborted unless the model and the real boundary
agreed on every cell, so each frozen literal is cross-verified.

Failure-Class: FC-privacy-purge-chain-collides-inside-armed-storm-window
"""

import logging
from unittest.mock import Mock

from google.api_core.exceptions import Aborted

from database import batch_pipeline_store as storage
from database import firestore_transaction_retry as engine
from database.batch_pipeline_purge import (
    PURGE_JOB_UNLINK_LABEL,
    PURGE_OWNER_FAIRNESS_LABEL,
    PURGE_RESULT_ERASE_LABEL,
    run_purge_transaction,
)
from database.firestore_transaction_retry import FirestoreContentionExhausted

WAVE_ENGAGEMENT_ATTEMPT = storage.FirestoreStore.WAVE_ENGAGEMENT_ATTEMPT
STORM_DAMPER_CAP_SECONDS = storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS
STORM_DAMPER_BASE_SECONDS = storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS
DEFAULT_ARM_WINDOW_SECONDS = 1.25
PINNED_JITTER_DRAW = 0.5
PURGE_LOGGER = 'database.batch_pipeline_purge'


class ScriptedStormDamper(storage._ContentionStormDamper):
    """The real damper class with every boundary answer scripted.

    The gate arithmetic under test reads only ``consult``, ``peek``,
    ``wave_rung_wait``, ``arm`` and ``note_success``; scripting those pins
    the lane boundary exactly like the store suite's injected dampers while
    keeping the production gate code real. ``consult`` honours the damper
    contract — it sleeps its own wait through the injected sleeper before
    returning — so the engine's recorder sees only rung waits.
    """

    def __init__(
        self,
        *,
        residual_schedule,
        wave_wait,
        generation,
        entry_wait,
        hostile_peek=False,
        arm_window=DEFAULT_ARM_WINDOW_SECONDS,
    ):
        self.slept = []
        super().__init__(sleeper=self._record_sleep)
        self.residual_schedule = list(residual_schedule)
        self.wave_wait = wave_wait
        self.generation = generation
        self.entry_wait = entry_wait
        self.hostile_peek = hostile_peek
        self.arm_wait = arm_window
        self.events = []
        self.peek_clients = []
        self.consult_clients = []
        self.arm_clients = []
        self.note_success_args = []

    def _record_sleep(self, seconds):
        self.slept.append(round(seconds, 9))

    def consult(self, label, *, client=None):
        self.events.append(['consult', label, self.entry_wait])
        self.consult_clients.append(client)
        if self.entry_wait > 0.0:
            self._sleeper(self.entry_wait)
        return self.entry_wait, self.generation

    def peek(self, label, *, client=None):
        rung = len(self.peek_clients) + 1
        residual = self.residual_schedule[min(rung, len(self.residual_schedule)) - 1]
        self.events.append(['peek', label, residual])
        self.peek_clients.append(client)
        if self.hostile_peek:
            raise RuntimeError('hostile damper peek')
        return residual, self.generation

    def wave_rung_wait(self, failed_attempt):
        self.events.append(['wave', failed_attempt, self.wave_wait])
        return self.wave_wait

    def arm(self, label, *, client=None):
        self.events.append(['arm', label, self.arm_wait])
        self.arm_clients.append(client)
        return self.arm_wait

    def note_success(self, label, generation):
        self.events.append(['note_success', label, generation])
        self.note_success_args.append([label, generation])


class ChainSleepRecorder:
    """Records every per-rung wait the retry engine asks for."""

    def __init__(self):
        self.sleeps = []

    def __call__(self, seconds):
        self.sleeps.append(round(seconds, 9))


def make_client():
    """A Mock Firestore client whose transactions commit on the first try."""

    class AbortThenCommitTx:
        _max_attempts = 1
        _read_only = False
        _id = None

        def __init__(self):
            self.commits = 0

        def _clean_up(self):
            self._id = None

        def _begin(self, retry_id=None):
            self._id = b'synthetic'

        def _commit(self):
            self.commits += 1
            self._id = None

        def _rollback(self):
            self._id = None

    client = Mock()
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx()
    return client


def silence_and_pin_chain(monkeypatch, recorder):
    """Drive the real engine with the wall-clock edges pinned.

    The purge helper imports the engine from the module at call time, so one
    binding covers every lane.
    """
    actual = engine.run_with_transaction_contention_retry

    def factory(*args, **kwargs):
        kwargs.setdefault('sleep', recorder)
        kwargs.setdefault('random_value', lambda: PINNED_JITTER_DRAW)
        return actual(*args, **kwargs)

    monkeypatch.setattr(engine, 'run_with_transaction_contention_retry', factory)


def equal_jitter_pinned(attempt):
    """The engine's rung wait at the pinned draw: the band midpoint."""

    high = min(0.2 * (2 ** (attempt - 1)), 4.0)
    low = high / 2
    return round(low + (high - low) * PINNED_JITTER_DRAW, 9)


def gate_at(residual_schedule, rung, wave_wait, hostile_peek):
    """The gate answer production computes for one failed rung."""

    if hostile_peek:
        return 0.0
    residual = residual_schedule[min(rung, len(residual_schedule)) - 1]
    if rung >= WAVE_ENGAGEMENT_ATTEMPT:
        return max(residual, wave_wait)
    return residual


def drive_cell(
    monkeypatch,
    caplog,
    *,
    label=PURGE_JOB_UNLINK_LABEL,
    aborts=0,
    entry_wait=0.0,
    residual_schedule=(0.0,),
    wave_wait=0.5,
    generation=0,
    hostile_peek=False,
    damper_mode='live',
    log_mode='info',
    arm_window=DEFAULT_ARM_WINDOW_SECONDS,
):
    """Drive one purge chain and freeze every observable."""

    scripted = None
    if damper_mode == 'live':
        scripted = ScriptedStormDamper(
            residual_schedule=list(residual_schedule),
            wave_wait=wave_wait,
            generation=generation,
            entry_wait=entry_wait,
            hostile_peek=hostile_peek,
            arm_window=arm_window,
        )
    client = make_client()
    recorder = ChainSleepRecorder()
    silence_and_pin_chain(monkeypatch, recorder)
    level = logging.INFO if log_mode == 'info' else logging.WARNING
    caplog.set_level(level, logger=PURGE_LOGGER)

    calls = []

    def body(transaction):
        calls.append(len(calls) + 1)
        if len(calls) <= aborts:
            raise Aborted('synthetic read contention')
        return 'erased'

    outcome = {
        'result': None,
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [],
        'sleeps': [],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'consult_count': 0,
        'peek_count': 0,
        'records': [],
    }
    try:
        outcome['result'] = run_purge_transaction(client, body, operation_name=label, storm_damper=scripted)
    except FirestoreContentionExhausted as error:
        outcome['raised'] = error.reason
        outcome['retry_after'] = round(error.retry_after, 9)
    outcome['body_calls'] = list(calls)
    outcome['sleeps'] = list(recorder.sleeps)
    if scripted is not None:
        outcome['damper_slept'] = list(scripted.slept)
        outcome['events'] = [event for event in scripted.events if event[0] != 'note_success']
        outcome['note_success'] = list(scripted.note_success_args)
        outcome['consult_count'] = len(scripted.consult_clients)
        outcome['peek_count'] = len(scripted.peek_clients)
    outcome['records'] = [record.getMessage() for record in caplog.records if '_backoff' in record.getMessage()]
    return outcome


def model_cell(
    *,
    label=PURGE_JOB_UNLINK_LABEL,
    aborts=0,
    entry_wait=0.0,
    residual_schedule=(0.0,),
    wave_wait=0.5,
    generation=0,
    hostile_peek=False,
    damper_mode='live',
    log_mode='info',
    arm_window=DEFAULT_ARM_WINDOW_SECONDS,
):
    """The independent doctrine walk: every observable, from source predicates."""

    live = damper_mode == 'live'
    rungs = aborts if aborts < 5 else 4
    exhausted = aborts >= 5
    outcome = {
        'result': None if exhausted else 'erased',
        'raised': 'attempts_exhausted' if exhausted else None,
        'retry_after': round(arm_window, 9) if (exhausted and live) else 0.0,
        'body_calls': [1, 2, 3, 4, 5] if exhausted else list(range(1, aborts + 2)),
        'sleeps': [],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'consult_count': 0,
        'peek_count': 0,
        'records': [],
    }
    if not live:
        outcome['sleeps'] = [round(equal_jitter_pinned(rung), 9) for rung in range(1, rungs + 1)]
        return outcome
    outcome['damper_slept'] = [round(entry_wait, 9)] if entry_wait > 0.0 else []
    outcome['events'].append(['consult', label, entry_wait])
    outcome['consult_count'] = 1
    if entry_wait > 0.0:
        outcome['records'].append(f'event={label}_backoff operation={label} waited_ms={round(entry_wait * 1000)}')
    for rung in range(1, rungs + 1):
        gate = gate_at(residual_schedule, rung, wave_wait, hostile_peek)
        residual = residual_schedule[min(rung, len(residual_schedule)) - 1]
        outcome['events'].append(['peek', label, residual])
        outcome['peek_count'] += 1
        if gate > 0.0:
            outcome['records'].append(
                f'event={label}_backoff scope=mid_ladder operation={label} '
                f'attempt={rung} waited_ms={round(gate * 1000)}'
            )
        if rung >= WAVE_ENGAGEMENT_ATTEMPT and not hostile_peek:
            outcome['events'].append(['wave', rung, wave_wait])
        outcome['sleeps'].append(round(equal_jitter_pinned(rung) + gate, 9))
    if exhausted:
        outcome['events'].append(['arm', label, arm_window])
    else:
        outcome['note_success'] = [[label, generation]]
    if log_mode != 'info':
        outcome['records'] = []
    return outcome
