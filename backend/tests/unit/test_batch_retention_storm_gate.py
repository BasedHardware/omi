"""The retention lane joins the process contention storm damper.

``run_retention_transaction`` drives the bounded contention engine for both
retention-phase transactions — the completion sweep (``batch_retention``) and
persist-phase artifact registration (``batch_artifact_register``) — and both
write the same hot ``jobs``/``results`` rows the batch-store labels storm on.
Until now the lane rode the bare equal-jitter ladder with no entry consult,
no mid-ladder gate, no exhaustion stamp and no success clearing, so a chain
entering a storm window the store (or a sibling pod) had armed re-fired every
rung inside it and re-derived a storm the fleet had already measured.

These tests pin the joined contract on the real damper class: the entry
consult sleeps out the label's residual window through the damper's own
sleeper, every retry rung re-peeks the residual and adds it to the rung's
equal-jitter wait (from the third failed rung also the capped wave ladder),
an exhaustion arms the label and stamps the applied window onto
``retry_after``, a success clears the ladder with the latest observed
generation, and a dormant damper (``None``) leaves the bare ladder
byte-for-byte. The lane-level tests drive the public entry points with a real
``FirestoreStore`` so the resolver, the kill switches and the two call sites
stay honest.

Failure-Class: FC-retention-contention-chain-collides-inside-armed-storm-window
"""

import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Aborted

from database import batch_pipeline_store as storage
from database import firestore_transaction_retry as engine
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline import retention as retention_module
from utils.batch_pipeline.retention import (
    expire_completed_segment,
    register_batch_artifact,
    run_retention_transaction,
)

PINNED_JITTER_DRAW = 0.5
ARM_WINDOW_SECONDS = 1.25
WAVE_ENGAGEMENT_ATTEMPT = storage.FirestoreStore.WAVE_ENGAGEMENT_ATTEMPT
STORM_DAMPER_CAP_SECONDS = storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS
STORM_DAMPER_BASE_SECONDS = storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS


class ScriptedStormDamper(storage._ContentionStormDamper):
    """The real damper class with every boundary answer scripted.

    The retention gate reads only ``consult``, ``peek``, ``wave_rung_wait``,
    ``arm`` and ``note_success``; scripting those keeps the production gate
    code real while the wall-clock edges stay recorded and deterministic.
    ``consult`` honours the damper contract — it sleeps its own wait through
    the injected sleeper — so the engine's recorder sees only rung waits.
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


def silence_and_pin_chain(monkeypatch, recorder):
    """Drive the real engine with the wall-clock edges pinned."""

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


def wave_ladder_pinned(failed_attempt):
    """The damper's wave rung at the pinned draw: the ladder midpoint."""

    maximum = min(STORM_DAMPER_CAP_SECONDS, STORM_DAMPER_BASE_SECONDS * (2 ** min(failed_attempt - 1, 4)))
    return round(maximum * (0.5 + 0.5 * PINNED_JITTER_DRAW), 9)


def drive_helper(
    monkeypatch,
    caplog,
    *,
    label='batch_retention',
    aborts=0,
    entry_wait=0.0,
    residual_schedule=(0.0,),
    wave_wait=0.5,
    generation=0,
    hostile_peek=False,
    damper=True,
    log_level=logging.INFO,
):
    """Drive one retention chain and freeze every observable."""

    monkeypatch.setattr(retention_module, 'contention_retry_enabled', lambda: True, raising=False)
    if damper:
        scripted = ScriptedStormDamper(
            residual_schedule=list(residual_schedule),
            wave_wait=wave_wait,
            generation=generation,
            entry_wait=entry_wait,
            hostile_peek=hostile_peek,
        )
    else:
        scripted = None
    client = Mock()
    recorder = ChainSleepRecorder()
    silence_and_pin_chain(monkeypatch, recorder)
    caplog.set_level(log_level, logger='utils.batch_pipeline.retention')

    calls = []

    def body(transaction):
        calls.append(len(calls) + 1)
        if len(calls) <= aborts:
            raise Aborted('synthetic read contention')
        return 'retained'

    outcome = {
        'result': None,
        'raised': None,
        'retry_after': 0.0,
        'body_calls': [],
        'sleeps': [],
        'damper_slept': [],
        'events': [],
        'note_success': [],
        'consult_clients': [],
        'arm_clients': [],
        'records': [],
    }
    try:
        outcome['result'] = run_retention_transaction(client, body, operation_name=label, storm_damper=scripted)
    except engine.FirestoreContentionExhausted as error:
        outcome['raised'] = error.reason
        outcome['retry_after'] = round(error.retry_after, 9)
    outcome['body_calls'] = list(calls)
    outcome['sleeps'] = list(recorder.sleeps)
    if scripted is not None:
        outcome['damper_slept'] = list(scripted.slept)
        outcome['events'] = [event for event in scripted.events if event[0] != 'note_success']
        outcome['note_success'] = list(scripted.note_success_args)
        outcome['consult_clients'] = list(scripted.consult_clients)
        outcome['arm_clients'] = list(scripted.arm_clients)
    outcome['records'] = [record.getMessage() for record in caplog.records if '_backoff' in record.getMessage()]
    return outcome


def retention_rows(namespace, uid, owner_key, segment_id):
    """The minimal completed-segment read set for the completion sweep."""

    return {
        (f'{namespace}_jobs', segment_id): {'owner_id': uid},
        (f'{namespace}_results', segment_id): {
            'projection_state': 'ready',
            'owner_key': owner_key,
            'expires_at': 1.0,
        },
    }


def make_store(rows, damper):
    """A real FirestoreStore with a private scripted damper and a strict client."""

    return storage.FirestoreStore('batch_pipeline_dev', firestore_client=StrictFirestore(rows), storm_damper=damper)


def test_entry_consult_sleeps_out_an_armed_window(monkeypatch, caplog):
    outcome = drive_helper(monkeypatch, caplog, entry_wait=0.4, aborts=1)
    assert outcome['damper_slept'] == [0.4]
    assert outcome['events'][0] == ['consult', 'batch_retention', 0.4]
    assert outcome['records'][0] == 'event=batch_retention_backoff operation=batch_retention waited_ms=400'
    assert outcome['result'] == 'retained'
    assert outcome['body_calls'] == [1, 2]


def test_entry_consult_runs_before_the_first_attempt_and_carries_the_client(monkeypatch, caplog):
    outcome = drive_helper(monkeypatch, caplog, entry_wait=0.6, aborts=0)
    assert outcome['events'][0] == ['consult', 'batch_retention', 0.6]
    assert len(outcome['consult_clients']) == 1
    assert outcome['consult_clients'][0] is not None
    assert outcome['body_calls'] == [1]


def test_cold_entry_records_no_wait_and_no_log(monkeypatch, caplog):
    outcome = drive_helper(monkeypatch, caplog, entry_wait=0.0, aborts=1)
    assert outcome['damper_slept'] == []
    assert outcome['events'][0] == ['consult', 'batch_retention', 0.0]
    assert outcome['records'] == []
    assert outcome['sleeps'] == [equal_jitter_pinned(1)]


def test_mid_ladder_rungs_peek_the_residual_and_add_it_to_the_wait(monkeypatch, caplog):
    outcome = drive_helper(monkeypatch, caplog, aborts=3, residual_schedule=[0.0, 0.4, 0.9])
    assert outcome['sleeps'] == [
        round(equal_jitter_pinned(1) + 0.0, 9),
        round(equal_jitter_pinned(2) + 0.4, 9),
        round(equal_jitter_pinned(3) + 0.9, 9),
    ]
    assert outcome['events'][1:] == [
        ['peek', 'batch_retention', 0.0],
        ['peek', 'batch_retention', 0.4],
        ['peek', 'batch_retention', 0.9],
        ['wave', 3, 0.5],
    ]
    assert outcome['records'] == [
        'event=batch_retention_backoff scope=mid_ladder operation=batch_retention attempt=2 waited_ms=400',
        'event=batch_retention_backoff scope=mid_ladder operation=batch_retention attempt=3 waited_ms=900',
    ]


def test_wave_rung_engages_from_the_third_failed_attempt(monkeypatch, caplog):
    deep_wave = wave_ladder_pinned(3)
    outcome = drive_helper(monkeypatch, caplog, aborts=3, residual_schedule=[0.0, 0.0, 0.0], wave_wait=deep_wave)
    assert outcome['sleeps'] == [
        equal_jitter_pinned(1),
        equal_jitter_pinned(2),
        round(equal_jitter_pinned(3) + deep_wave, 9),
    ]
    assert ['wave', 3, deep_wave] in outcome['events']
    assert ['wave', 2, deep_wave] not in outcome['events']


def test_wave_rung_never_shortens_a_deeper_residual(monkeypatch, caplog):
    deep_wave = wave_ladder_pinned(4)
    outcome = drive_helper(monkeypatch, caplog, aborts=4, residual_schedule=[0.0, 0.0, 2.0, 0.1], wave_wait=deep_wave)
    assert outcome['sleeps'][2] == round(equal_jitter_pinned(3) + 2.0, 9)
    assert outcome['sleeps'][3] == round(equal_jitter_pinned(4) + deep_wave, 9)


def test_hostile_peek_collapses_the_rung_to_the_bare_ladder(monkeypatch, caplog):
    outcome = drive_helper(monkeypatch, caplog, aborts=3, residual_schedule=[0.4, 0.9, 2.0], hostile_peek=True)
    assert outcome['sleeps'] == [equal_jitter_pinned(1), equal_jitter_pinned(2), equal_jitter_pinned(3)]
    assert outcome['records'][1:] == []
    assert outcome['result'] == 'retained'


def test_exhaustion_stamps_the_armed_window_onto_retry_after(monkeypatch, caplog):
    outcome = drive_helper(monkeypatch, caplog, aborts=5, entry_wait=0.2)
    assert outcome['raised'] == 'attempts_exhausted'
    assert outcome['retry_after'] == ARM_WINDOW_SECONDS
    assert outcome['events'][-1] == ['arm', 'batch_retention', ARM_WINDOW_SECONDS]
    assert len(outcome['arm_clients']) == 1
    assert outcome['note_success'] == []
    assert outcome['body_calls'] == [1, 2, 3, 4, 5]


def test_success_clears_the_ladder_with_the_entry_generation(monkeypatch, caplog):
    outcome = drive_helper(monkeypatch, caplog, aborts=1, generation=3)
    assert outcome['result'] == 'retained'
    assert outcome['note_success'] == [['batch_retention', 3]]
    assert outcome['events'] == [['consult', 'batch_retention', 0.0], ['peek', 'batch_retention', 0.0]]


def test_late_generation_from_the_gate_reaches_the_success_clear(monkeypatch, caplog):
    outcome = drive_helper(monkeypatch, caplog, aborts=2, generation=1)
    assert outcome['note_success'] == [['batch_retention', 1]]


def test_dormant_helper_keeps_the_bare_ladder_byte_for_byte(monkeypatch, caplog):
    outcome = drive_helper(monkeypatch, caplog, aborts=2, damper=False)
    assert outcome['sleeps'] == [equal_jitter_pinned(1), equal_jitter_pinned(2)]
    assert outcome['events'] == []
    assert outcome['damper_slept'] == []
    assert outcome['note_success'] == []
    assert outcome['records'] == []
    assert outcome['retry_after'] == 0.0
    assert outcome['result'] == 'retained'


def test_register_label_spaces_itself_under_its_own_label(monkeypatch, caplog):
    outcome = drive_helper(monkeypatch, caplog, label='batch_artifact_register', aborts=2, entry_wait=0.3)
    assert outcome['events'][0] == ['consult', 'batch_artifact_register', 0.3]
    assert outcome['records'][0] == (
        'event=batch_artifact_register_backoff operation=batch_artifact_register waited_ms=300'
    )
    assert outcome['note_success'] == [['batch_artifact_register', 0]]


def test_expire_completed_segment_joins_the_store_damper(monkeypatch, caplog):
    from database.batch_pipeline_privacy import privacy_owner_key

    uid = 'synthetic-retention-owner'
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    scripted = ScriptedStormDamper(
        residual_schedule=[0.0],
        wave_wait=0.5,
        generation=2,
        entry_wait=0.5,
    )
    store = make_store(retention_rows('batch_pipeline_dev', uid, privacy_owner_key(uid), 'retention-segment'), scripted)
    monkeypatch.setattr(retention_module.queries, 'segment_artifacts', lambda *args, **kwargs: [])
    recorder = ChainSleepRecorder()
    silence_and_pin_chain(monkeypatch, recorder)
    caplog.set_level(logging.INFO, logger='utils.batch_pipeline.retention')

    assert expire_completed_segment(store, uid, 'retention-segment', 1000.0) is True
    assert scripted.events[0] == ['consult', 'batch_retention', 0.5]
    assert scripted.slept == [0.5]
    assert scripted.note_success_args == [['batch_retention', 2]]
    assert any(
        'event=batch_retention_backoff operation=batch_retention waited_ms=500' in record.getMessage()
        for record in caplog.records
    )


def test_register_batch_artifact_joins_the_store_damper(monkeypatch, caplog):
    from utils.batch_pipeline.contracts import Priority, WorkItem

    uid = 'synthetic-register-owner'
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    scripted = ScriptedStormDamper(
        residual_schedule=[0.0],
        wave_wait=0.5,
        generation=0,
        entry_wait=0.35,
    )
    store = make_store({}, scripted)
    monkeypatch.setattr(retention_module, 'assert_batch_write_allowed', lambda *args, **kwargs: 0)
    monkeypatch.setattr(retention_module, 'mirror_refresh', lambda *args, **kwargs: None)
    recorder = ChainSleepRecorder()
    silence_and_pin_chain(monkeypatch, recorder)
    caplog.set_level(logging.INFO, logger='utils.batch_pipeline.retention')
    item = WorkItem(
        'register-segment',
        uid,
        100.0,
        'gs://synthetic/register/audio.enc',
        10.0,
        Priority.FRESH,
        conversation_id='register-conversation',
        privacy_generation=0,
    )

    artifact_id = register_batch_artifact(
        store, uid, 'register-segment', 'gs://synthetic/register/audio.enc', 'audio', 0, item=item
    )
    assert artifact_id
    assert scripted.events[0] == ['consult', 'batch_artifact_register', 0.35]
    assert scripted.slept == [0.35]
    assert scripted.note_success_args == [['batch_artifact_register', 0]]


def test_dormant_switches_keep_the_lane_on_the_bare_ladder(monkeypatch, caplog):
    from database.batch_pipeline_privacy import privacy_owner_key

    uid = 'synthetic-dormant-owner'
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    scripted = ScriptedStormDamper(residual_schedule=[0.0], wave_wait=0.5, generation=0, entry_wait=0.9)
    store = make_store(retention_rows('batch_pipeline_dev', uid, privacy_owner_key(uid), 'dormant-segment'), scripted)
    monkeypatch.setattr(retention_module.queries, 'segment_artifacts', lambda *args, **kwargs: [])
    monkeypatch.setattr(storage, 'contention_storm_damper_enabled', lambda: False)
    recorder = ChainSleepRecorder()
    silence_and_pin_chain(monkeypatch, recorder)
    caplog.set_level(logging.INFO, logger='utils.batch_pipeline.retention')

    assert expire_completed_segment(store, uid, 'dormant-segment', 1000.0) is True
    assert scripted.events == []
    assert scripted.slept == []
    assert recorder.sleeps == []


def test_non_store_primary_keeps_the_lane_on_the_bare_ladder(monkeypatch, caplog):
    from database.batch_pipeline_privacy import privacy_owner_key

    uid = 'synthetic-simulator-owner'
    scripted = ScriptedStormDamper(residual_schedule=[0.0], wave_wait=0.5, generation=0, entry_wait=0.9)
    client = StrictFirestore(retention_rows('batch_pipeline_dev', uid, privacy_owner_key(uid), 'simulator-segment'))
    monkeypatch.setattr(retention_module.queries, 'segment_artifacts', lambda *args, **kwargs: [])
    store = SimpleNamespace(client=client, namespace='batch_pipeline_dev')
    recorder = ChainSleepRecorder()
    silence_and_pin_chain(monkeypatch, recorder)
    caplog.set_level(logging.INFO, logger='utils.batch_pipeline.retention')

    assert expire_completed_segment(store, uid, 'simulator-segment', 1000.0) is True
    assert scripted.events == []
    assert recorder.sleeps == []


def test_docs_page_names_the_retention_gate():
    from pathlib import Path

    docs = Path(__file__).resolve().parents[2] / 'docs' / 'batch-retention-storm-gate.md'
    assert docs.exists(), 'the retention storm-gate contract must be documented'
    text = docs.read_text(encoding='utf-8')
    assert 'FC-retention-contention-chain-collides-inside-armed-storm-window' in text
    assert 'batch_retention_backoff' in text
    assert 'batch_artifact_register' in text
