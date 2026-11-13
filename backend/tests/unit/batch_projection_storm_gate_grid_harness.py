"""Shared cell harness for the projection storm-gate grids.

Each grid cell drives one real boundary — ``ProjectionStore.run``'s storm
gate (entry consult, mid-ladder peek/wave spacing, exhaustion stamp, success
clearing) behind ``FirestoreStore.contention_storm_damper`` — and freezes the
observables the grid tests compare as literals. The engine under test is the
production one — ``run_with_transaction_contention_retry`` — with only the
wall-clock edges pinned (sleep is recorded, never slept; the equal-jitter
draw is pinned to 0.5; deadline cells script the monotonic clock), so rung
waits are exact floats.

``model_cell`` is the independent hand-transcribed expectation walk: it
predicts every observable from the source predicates and the retry engine's
documented accounting (one fresh transaction per outer attempt; equal-jitter
rungs at the pinned draw; the gate consults once per rung that will be
retried and never before the first attempt; the wave wait engages from the
third failed attempt and never shortens a residual; a hostile damper answer
collapses the rung to the bare schedule; the entry consult sleeps through the
damper's own sleeper, outside the engine's recorder; the attempt cap raises
the typed exhaustion and stamps the damper's arm window onto ``retry_after``;
a success clears the ladder with the entry generation). The emitter that
generated the grid files aborted unless the model and the real boundary
agreed on every cell, so each frozen literal is cross-verified.

Failure-Class: FC-projection-contention-chain-collides-inside-armed-storm-window
"""

import logging
import os
from types import SimpleNamespace
from unittest.mock import Mock

from google.api_core.exceptions import Aborted, InvalidArgument

from database import batch_pipeline_projection as projection_module
from database import batch_pipeline_store as storage
from database.firestore_transaction_retry import FirestoreContentionExhausted

PROJECTION_LABEL = 'batch_projection'
WAVE_ENGAGEMENT_ATTEMPT = storage.FirestoreStore.WAVE_ENGAGEMENT_ATTEMPT
STORM_DAMPER_CAP_SECONDS = storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS
ARM_WINDOW_SECONDS = 1.25
PINNED_JITTER_DRAW = 0.5
EXPIRED_TRANSACTION_MESSAGE = 'The referenced transaction has expired or is no longer valid'


class AbortThenCommitTx:
    """Minimal firestore_v1.Transaction; commits never abort here."""

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


class ScriptedStormDamper(storage._ContentionStormDamper):
    """The real damper class with every boundary answer scripted.

    The gate arithmetic under test reads only ``consult``, ``peek``,
    ``wave_rung_wait``, ``arm`` and ``note_success``; scripting those pins
    the lane boundary exactly like the store suite's injected dampers while
    keeping the production gate code real. ``consult`` honours the damper
    contract — it sleeps its own wait through the injected sleeper before
    returning — so the engine's recorder sees only rung waits.
    """

    def __init__(self, *, residual_schedule, wave_wait, generation, entry_wait, hostile_peek=False):
        self.slept = []
        super().__init__(sleeper=self._record_sleep)
        self.residual_schedule = list(residual_schedule)
        self.wave_wait = wave_wait
        self.generation = generation
        self.entry_wait = entry_wait
        self.hostile_peek = hostile_peek
        self.arm_wait = ARM_WINDOW_SECONDS
        self.events = []
        self.peek_clients = []
        self.consult_clients = []
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


class SimulatedPrimary:
    """A non-FirestoreStore primary: the bare-ladder shape must survive it."""

    def __init__(self, client):
        self.client = client
        self.namespace = 'batch_pipeline_dev'


def make_client():
    client = Mock()
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx()
    return client


def silence_and_pin_chain(monkeypatch, recorder, monotonic=None):
    from database import firestore_transaction_retry as engine

    actual = engine.run_with_transaction_contention_retry

    def factory(*args, **kwargs):
        kwargs.setdefault('sleep', recorder)
        kwargs.setdefault('random_value', lambda: PINNED_JITTER_DRAW)
        if monotonic is not None:
            kwargs.setdefault('monotonic', monotonic)
        return actual(*args, **kwargs)

    monkeypatch.setattr(engine, 'run_with_transaction_contention_retry', factory)
    # The store lane imported the engine into its own namespace at import
    # time; pin that binding too so both lanes run the recorded chain.
    if hasattr(storage, 'run_with_transaction_contention_retry'):
        monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', factory)


def enable_switches(monkeypatch, *, damper_enabled=True):
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: True)
    monkeypatch.setattr(storage, 'contention_storm_damper_enabled', lambda: damper_enabled)


def equal_jitter_pinned(attempt):
    """The engine's rung wait at the pinned 0.5 draw: the band midpoint."""
    high = min(0.2 * (2 ** (attempt - 1)), 4.0)
    low = high / 2
    return round(low + (high - low) * PINNED_JITTER_DRAW, 9)


def gate_at(residual_schedule, rung, wave_wait, hostile_peek):
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
    residual_schedule,
    wave_wait,
    damper_mode,
    generation,
    log_mode,
    entry_wait,
    aborts,
    hostile_peek=False,
    deadline_margin=None,
    abort_kind='aborted',
    lane='projection',
    store_label='batch_claim',
):
    enable_switches(monkeypatch, damper_enabled=(damper_mode != 'dormant_switch'))
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    damper = ScriptedStormDamper(
        residual_schedule=residual_schedule,
        wave_wait=wave_wait,
        generation=generation,
        entry_wait=entry_wait,
        hostile_peek=hostile_peek,
    )
    client = make_client()
    if damper_mode == 'absent_store' and lane == 'projection':
        store = projection_module.ProjectionStore(SimulatedPrimary(client))
    elif lane == 'store':
        store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=client, storm_damper=damper)
    else:
        inner = storage.FirestoreStore('batch_pipeline_dev', firestore_client=client, storm_damper=damper)
        store = projection_module.ProjectionStore(inner)
    recorder = ChainSleepRecorder()
    monotonic = None
    now = 1000.0
    if deadline_margin is not None:

        class PinnedClock:
            def monotonic(self):
                return now

        monotonic = PinnedClock().monotonic
    silence_and_pin_chain(monkeypatch, recorder, monotonic=monotonic)
    if log_mode == 'info':
        caplog.set_level(logging.INFO, logger='database.batch_pipeline_projection')
        caplog.set_level(logging.INFO, logger='database.batch_pipeline_store')
    else:
        caplog.set_level(logging.WARNING, logger='database.batch_pipeline_projection')
        caplog.set_level(logging.WARNING, logger='database.batch_pipeline_store')

    calls = []

    def body(transaction):
        calls.append(len(calls) + 1)
        if len(calls) <= aborts:
            if abort_kind == 'expired':
                raise InvalidArgument(EXPIRED_TRANSACTION_MESSAGE)
            raise Aborted('synthetic read contention')
        return 'projected'

    outcome = {
        'result': None,
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [],
        'sleeps': [],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }

    def run_once():
        if lane == 'store':
            if deadline_margin is None:
                return store.run(body, operation=store_label)
            from database.firestore_transaction_retry import transaction_retry_deadline_scope

            with transaction_retry_deadline_scope(now + deadline_margin):
                return store.run(body, operation=store_label)
        if deadline_margin is None:
            return store.run(body, policy=SimpleNamespace(projection_contention=True))
        from database.firestore_transaction_retry import transaction_retry_deadline_scope

        with transaction_retry_deadline_scope(now + deadline_margin):
            return store.run(body, policy=SimpleNamespace(projection_contention=True))

    try:
        outcome['result'] = run_once()
    except FirestoreContentionExhausted as error:
        outcome['raised'] = error.reason
        outcome['retry_after'] = round(error.retry_after, 9)
    outcome['body_calls'] = list(calls)
    outcome['sleeps'] = list(recorder.sleeps)
    if damper_mode == 'live':
        outcome['damper_slept'] = list(damper.slept)
        outcome['events'] = [event for event in damper.events if event[0] != 'note_success']
        outcome['note_success'] = list(damper.note_success_args)
        outcome['peek_count'] = len(damper.peek_clients)
        outcome['consult_count'] = len(damper.consult_clients)
        outcome['clients_consistent'] = all(value is client for value in damper.peek_clients + damper.consult_clients)
    outcome['records'] = [
        record.getMessage()
        for record in caplog.records
        if 'backoff' in record.getMessage()
        and 'batch_projection' in record.getMessage()
        or 'batch_store_backoff' in record.getMessage()
    ]
    return outcome


def model_cell(
    *,
    residual_schedule,
    wave_wait,
    damper_mode,
    generation,
    log_mode,
    entry_wait,
    aborts,
    hostile_peek=False,
    deadline_margin=None,
    abort_kind='aborted',
    lane='projection',
    store_label='batch_claim',
):
    """The independent doctrine walk: every observable, from source predicates."""
    live = damper_mode == 'live'
    label = PROJECTION_LABEL if lane == 'projection' else store_label
    prefix = 'batch_projection_backoff' if lane == 'projection' else 'batch_store_backoff'
    expired = abort_kind == 'expired'
    ceiling_exhausts = expired and deadline_margin is None and aborts >= 3
    # The expired-chain ceiling (three fresh chains with no deadline in
    # scope) retires the chain after the third expired attempt — even when
    # a success was scheduled behind it; under a deadline the ceiling is
    # bypassed and the reserve gate rules instead.
    if ceiling_exhausts:
        aborts = 5
    rungs = aborts if aborts < 5 else 4
    rung_cap = rungs
    if ceiling_exhausts:
        # The ceiling retires the chain when attempt 3 fails: rungs 1 and 2
        # slept, attempt 3's failure raises before any further rung.
        rungs = min(rungs, 2)
    if deadline_margin is not None and deadline_margin < 30.0:
        rung_cap = 1
    outcome = {
        'result': 'projected' if aborts < 5 else None,
        'raised': None if aborts < 5 else 'attempts_exhausted',
        'retry_after': round(ARM_WINDOW_SECONDS, 9) if (aborts >= 5 and live) else 0.0,
        'body_calls': list(range(1, aborts + 2)) if aborts < 5 else [1, 2, 3, 4, 5],
        'sleeps': [],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'peek_count': 0,
        'consult_count': 0,
        'clients_consistent': True,
        'records': [],
    }
    if ceiling_exhausts:
        outcome['body_calls'] = [1, 2, 3]
        outcome['raised'] = 'attempts_exhausted'
        outcome['result'] = None
        outcome['retry_after'] = round(ARM_WINDOW_SECONDS, 9) if live else 0.0
    if deadline_margin is not None and deadline_margin < 30.0:
        # Rung 1 always runs and sleeps (the deadline never gates the first
        # attempt and never shortens a sleep), then the reserve gate refuses
        # attempt 2: remaining cannot cover the 30 s reserve floor.
        outcome['raised'] = 'deadline_exhausted'
        outcome['result'] = None
        outcome['body_calls'] = [1]
        outcome['retry_after'] = round(ARM_WINDOW_SECONDS, 9) if live else 0.0
    if live:
        outcome['damper_slept'] = [round(entry_wait, 9)] if entry_wait > 0.0 else []
        outcome['events'].append(['consult', label, entry_wait])
        outcome['consult_count'] = 1
        if entry_wait > 0.0:
            outcome['records'].append(f'event={prefix} operation={label} waited_ms={round(entry_wait * 1000)}')
        for rung in range(1, rungs + 1):
            if deadline_margin is not None and deadline_margin < 30.0 and rung > rung_cap:
                break
            gate = gate_at(residual_schedule, rung, wave_wait, hostile_peek)
            residual = residual_schedule[min(rung, len(residual_schedule)) - 1]
            outcome['events'].append(['peek', label, residual])
            outcome['peek_count'] += 1
            if gate > 0.0:
                outcome['records'].append(
                    f'event={prefix} scope=mid_ladder operation={label} '
                    f'attempt={rung} waited_ms={round(gate * 1000)}'
                )
            if rung >= WAVE_ENGAGEMENT_ATTEMPT and not hostile_peek:
                outcome['events'].append(['wave', rung, wave_wait])
            outcome['sleeps'].append(round(equal_jitter_pinned(rung) + gate, 9))
        if outcome['raised'] is not None and live:
            outcome['events'].append(['arm', label, ARM_WINDOW_SECONDS])
        elif outcome['raised'] is None:
            outcome['note_success'] = [[label, generation]]
    else:
        outcome['sleeps'] = [round(equal_jitter_pinned(rung), 9) for rung in range(1, rungs + 1)]
        if deadline_margin is not None and deadline_margin < 30.0:
            outcome['sleeps'] = [round(equal_jitter_pinned(1), 9)]
    if log_mode != 'info' or not live:
        outcome['records'] = []
    return outcome
