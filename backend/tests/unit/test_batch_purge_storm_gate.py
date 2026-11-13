"""The privacy-purge lane joins the process contention storm damper.

``run_purge_transaction`` drives the bounded contention engine for the three
privacy-purge transactions — the per-job unlink (``batch_purge_job_unlink``),
the owner fairness sweep (``batch_purge_owner_fairness``) and the erased-result
watermark write (``batch_purge_result_erase``) — and all three write the same
hot ``control``/``queues``/``owners``/``jobs``/``results`` rows the batch-store
labels storm on. Until now the lane handed each body to a bare
``client.transaction()``, so contention went to the SDK's same-id commit loop:
one transaction id replayed inside a storm window the store lane had already
measured, an expiry retirement the SDK never retries, and an anonymous
exhaustion with no label, no window and no fleet view.

These tests pin the joined contract on the real damper class: the entry
consult sleeps out the label's residual window through the damper's own
sleeper, every retry rung re-peeks the residual and adds it to the rung's
equal-jitter wait (from the third failed rung also the capped wave ladder),
an exhaustion arms the label and stamps the applied window onto
``retry_after``, a success clears the ladder with the latest observed
generation, a dormant damper (``None``) leaves the bare bounded ladder
byte-for-byte, and the three call sites resolve the namespace's shared
damper per call through ``_purge_storm_damper`` so both kill switches stay
live. The site-level tests drive the real purge bodies over the strict
Firestore fixture so the unlink, fairness and erased-result row effects
stay pinned alongside the gate.

Failure-Class: FC-privacy-purge-chain-collides-inside-armed-storm-window
"""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from google.api_core.exceptions import Aborted

from config.batch_pipeline import scheduler_control_key
from database import batch_pipeline_store as storage
from database import batch_pipeline_purge as purge_module
from database import firestore_transaction_retry as engine
from database.batch_pipeline_purge import (
    PURGE_JOB_UNLINK_LABEL,
    PURGE_OWNER_FAIRNESS_LABEL,
    PURGE_RESULT_ERASE_LABEL,
    _delete_job,
    _erase_result,
    _purge_storm_damper,
    _purge_owner_fairness,
    run_purge_transaction,
)
from database.batch_pipeline_privacy import privacy_owner_key
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

PINNED_JITTER_DRAW = 0.5
ARM_WINDOW_SECONDS = 1.25
WAVE_ENGAGEMENT_ATTEMPT = storage.FirestoreStore.WAVE_ENGAGEMENT_ATTEMPT
STORM_DAMPER_CAP_SECONDS = storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS
STORM_DAMPER_BASE_SECONDS = storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS
PURGE_LOGGER = 'database.batch_pipeline_purge'
SITE_NAMESPACE = 'batch_pipeline_test_unit'


class ScriptedStormDamper(storage._ContentionStormDamper):
    """The real damper class with every boundary answer scripted.

    The purge gate reads only ``consult``, ``peek``, ``wave_rung_wait``,
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
    label=PURGE_JOB_UNLINK_LABEL,
    aborts=0,
    entry_wait=0.0,
    residual_schedule=(0.0,),
    wave_wait=0.5,
    generation=0,
    hostile_peek=False,
    damper=True,
    log_level=logging.INFO,
):
    """Drive one purge chain and freeze every observable."""

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
    caplog.set_level(log_level, logger=PURGE_LOGGER)

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
        'consult_clients': [],
        'arm_clients': [],
        'transaction_calls': [],
        'records': [],
    }
    try:
        outcome['result'] = run_purge_transaction(client, body, operation_name=label, storm_damper=scripted)
    except engine.FirestoreContentionExhausted as error:
        outcome['raised'] = error.reason
        outcome['retry_after'] = round(error.retry_after, 9)
    outcome['body_calls'] = list(calls)
    outcome['sleeps'] = list(recorder.sleeps)
    outcome['transaction_calls'] = [(call.args, dict(call.kwargs)) for call in client.transaction.call_args_list]
    if scripted is not None:
        outcome['damper_slept'] = list(scripted.slept)
        outcome['events'] = [event for event in scripted.events if event[0] != 'note_success']
        outcome['note_success'] = list(scripted.note_success_args)
        outcome['consult_clients'] = list(scripted.consult_clients)
        outcome['arm_clients'] = list(scripted.arm_clients)
    outcome['records'] = [record.getMessage() for record in caplog.records if '_backoff' in record.getMessage()]
    return outcome


def purge_rows(namespace, owner_key, segment_id, priority=1):
    """The minimal fifo-queue unlink read set for one owned job."""

    return {
        (f'{namespace}_jobs', segment_id): {'owner_key': owner_key, 'priority': priority, 'next': ''},
        (f'{namespace}_results', segment_id): {
            'owner_key': owner_key,
            'projection_state': 'ready',
            'log_sequence': 5,
        },
        (f'{namespace}_owners', owner_key): {'projection_watermark': segment_id},
        (f'{namespace}_control', scheduler_control_key(owner_key)): {'rings': {}},
        (f'{namespace}_queues', f'{priority}_{owner_key}'): {
            'link_mode': 'fifo_array',
            'items': [segment_id],
            'head': segment_id,
            'tail': segment_id,
        },
    }


class AbortOnceReference:
    """A reference proxy whose first transactional read aborts, then commits."""

    def __init__(self, inner):
        self._inner = inner
        self._reads = 0
        self.id = inner.id

    def get(self, transaction=None, **kwargs):
        self._reads += 1
        if self._reads == 1:
            raise Aborted('synthetic read contention')
        return self._inner.get(transaction=transaction, **kwargs)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def make_site(monkeypatch, rows, scripted):
    """A strict client, a scripted damper wired through the purge resolver, silenced engine."""

    monkeypatch.setattr(purge_module, 'mirror_refresh', MagicMock())
    monkeypatch.setattr(purge_module, '_purge_storm_damper', lambda namespace: scripted)
    client = StrictFirestore(rows)
    recorder = ChainSleepRecorder()
    silence_and_pin_chain(monkeypatch, recorder)
    return client, recorder


def test_entry_consult_sleeps_out_an_armed_window(monkeypatch, caplog):
    outcome = drive_helper(monkeypatch, caplog, entry_wait=0.4, aborts=1)
    assert outcome['damper_slept'] == [0.4]
    assert outcome['events'][0] == ['consult', PURGE_JOB_UNLINK_LABEL, 0.4]
    assert outcome['records'][0] == (
        f'event={PURGE_JOB_UNLINK_LABEL}_backoff operation={PURGE_JOB_UNLINK_LABEL} waited_ms=400'
    )
    assert outcome['result'] == 'erased'
    assert outcome['body_calls'] == [1, 2]


def test_entry_consult_runs_before_the_first_attempt_and_carries_the_client(monkeypatch, caplog):
    outcome = drive_helper(monkeypatch, caplog, entry_wait=0.6, aborts=0)
    assert outcome['events'][0] == ['consult', PURGE_JOB_UNLINK_LABEL, 0.6]
    assert len(outcome['consult_clients']) == 1
    assert outcome['consult_clients'][0] is not None
    assert outcome['body_calls'] == [1]


def test_cold_entry_records_no_wait_and_no_log(monkeypatch, caplog):
    outcome = drive_helper(monkeypatch, caplog, entry_wait=0.0, aborts=1)
    assert outcome['damper_slept'] == []
    assert outcome['events'][0] == ['consult', PURGE_JOB_UNLINK_LABEL, 0.0]
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
        ['peek', PURGE_JOB_UNLINK_LABEL, 0.0],
        ['peek', PURGE_JOB_UNLINK_LABEL, 0.4],
        ['peek', PURGE_JOB_UNLINK_LABEL, 0.9],
        ['wave', 3, 0.5],
    ]
    assert outcome['records'] == [
        f'event={PURGE_JOB_UNLINK_LABEL}_backoff scope=mid_ladder '
        f'operation={PURGE_JOB_UNLINK_LABEL} attempt=2 waited_ms=400',
        f'event={PURGE_JOB_UNLINK_LABEL}_backoff scope=mid_ladder '
        f'operation={PURGE_JOB_UNLINK_LABEL} attempt=3 waited_ms=900',
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
    assert outcome['result'] == 'erased'


def test_exhaustion_stamps_the_armed_window_onto_retry_after(monkeypatch, caplog):
    outcome = drive_helper(monkeypatch, caplog, aborts=5, entry_wait=0.2)
    assert outcome['raised'] == 'attempts_exhausted'
    assert outcome['retry_after'] == ARM_WINDOW_SECONDS
    assert outcome['events'][-1] == ['arm', PURGE_JOB_UNLINK_LABEL, ARM_WINDOW_SECONDS]
    assert len(outcome['arm_clients']) == 1
    assert outcome['note_success'] == []
    assert outcome['body_calls'] == [1, 2, 3, 4, 5]


def test_success_clears_the_ladder_with_the_entry_generation(monkeypatch, caplog):
    outcome = drive_helper(monkeypatch, caplog, aborts=1, generation=3)
    assert outcome['result'] == 'erased'
    assert outcome['note_success'] == [[PURGE_JOB_UNLINK_LABEL, 3]]
    assert outcome['events'] == [
        ['consult', PURGE_JOB_UNLINK_LABEL, 0.0],
        ['peek', PURGE_JOB_UNLINK_LABEL, 0.0],
    ]


def test_late_generation_from_the_gate_reaches_the_success_clear(monkeypatch, caplog):
    outcome = drive_helper(monkeypatch, caplog, aborts=2, generation=1)
    assert outcome['note_success'] == [[PURGE_JOB_UNLINK_LABEL, 1]]


def test_dormant_helper_keeps_the_bare_ladder_byte_for_byte(monkeypatch, caplog):
    outcome = drive_helper(monkeypatch, caplog, aborts=2, damper=False)
    assert outcome['sleeps'] == [equal_jitter_pinned(1), equal_jitter_pinned(2)]
    assert outcome['events'] == []
    assert outcome['damper_slept'] == []
    assert outcome['note_success'] == []
    assert outcome['records'] == []
    assert outcome['retry_after'] == 0.0
    assert outcome['result'] == 'erased'


def test_each_purge_label_spaces_itself_under_its_own_label(monkeypatch, caplog):
    for label in (PURGE_JOB_UNLINK_LABEL, PURGE_OWNER_FAIRNESS_LABEL, PURGE_RESULT_ERASE_LABEL):
        caplog.clear()
        outcome = drive_helper(monkeypatch, caplog, label=label, aborts=1, entry_wait=0.3)
        assert outcome['events'][0] == ['consult', label, 0.3]
        assert outcome['records'] == [f'event={label}_backoff operation={label} waited_ms=300']
        assert outcome['note_success'] == [[label, 0]]


def test_one_fresh_transaction_per_rung_not_a_replayed_id(monkeypatch):
    frozen_caplog = Mock()
    frozen_caplog.records = []
    outcome = drive_helper(monkeypatch, frozen_caplog, aborts=2)
    assert outcome['body_calls'] == [1, 2, 3]
    assert len(outcome['transaction_calls']) == 3
    assert all(kwargs.get('max_attempts') == 1 for _args, kwargs in outcome['transaction_calls'])


def test_non_contention_error_propagates_without_arm_or_success(monkeypatch, caplog):
    client = Mock()
    recorder = ChainSleepRecorder()
    silence_and_pin_chain(monkeypatch, recorder)
    caplog.set_level(logging.INFO, logger=PURGE_LOGGER)
    scripted = ScriptedStormDamper(residual_schedule=[0.0], wave_wait=0.5, generation=0, entry_wait=0.0)

    def body(transaction):
        raise ValueError('not contention')

    with pytest.raises(ValueError):
        run_purge_transaction(client, body, operation_name=PURGE_RESULT_ERASE_LABEL, storm_damper=scripted)
    assert scripted.events == [['consult', PURGE_RESULT_ERASE_LABEL, 0.0]]
    assert scripted.note_success_args == []
    assert scripted.arm_clients == []


def test_delete_job_site_rides_the_namespace_storm_gate(monkeypatch):
    owner_key = privacy_owner_key('synthetic-purge-owner')
    rows = purge_rows(SITE_NAMESPACE, owner_key, 'purge-segment')
    scripted = ScriptedStormDamper(residual_schedule=[0.0], wave_wait=0.5, generation=2, entry_wait=0.25)
    client, _recorder = make_site(monkeypatch, rows, scripted)
    snapshot = SimpleNamespace(
        id='purge-segment', reference=client.collection(f'{SITE_NAMESPACE}_jobs').document('purge-segment')
    )

    _delete_job(client, SITE_NAMESPACE, snapshot, retain_ordering=False)

    assert scripted.events[0] == ['consult', PURGE_JOB_UNLINK_LABEL, 0.25]
    assert scripted.slept == [0.25]
    assert scripted.note_success_args == [[PURGE_JOB_UNLINK_LABEL, 2]]
    assert (f'{SITE_NAMESPACE}_jobs', 'purge-segment') not in client.rows
    assert (f'{SITE_NAMESPACE}_results', 'purge-segment') not in client.rows
    assert (f'{SITE_NAMESPACE}_queues', f'1_{owner_key}') not in client.rows
    assert (f'{SITE_NAMESPACE}_owners', owner_key) in client.rows
    purge_module.mirror_refresh.assert_called_once()


def test_delete_job_site_spaces_a_measured_collision_and_recovers(monkeypatch):
    owner_key = privacy_owner_key('synthetic-purge-owner')
    rows = purge_rows(SITE_NAMESPACE, owner_key, 'purge-segment')
    scripted = ScriptedStormDamper(residual_schedule=[0.4, 0.0], wave_wait=0.5, generation=0, entry_wait=0.0)
    client, recorder = make_site(monkeypatch, rows, scripted)
    jobs_reference = AbortOnceReference(client.collection(f'{SITE_NAMESPACE}_jobs').document('purge-segment'))
    snapshot = SimpleNamespace(id='purge-segment', reference=jobs_reference)

    _delete_job(client, SITE_NAMESPACE, snapshot, retain_ordering=False)

    assert recorder.sleeps == [round(equal_jitter_pinned(1) + 0.4, 9)]
    assert scripted.events == [
        ['consult', PURGE_JOB_UNLINK_LABEL, 0.0],
        ['peek', PURGE_JOB_UNLINK_LABEL, 0.4],
        ['note_success', PURGE_JOB_UNLINK_LABEL, 0],
    ]
    assert scripted.note_success_args == [[PURGE_JOB_UNLINK_LABEL, 0]]
    assert (f'{SITE_NAMESPACE}_jobs', 'purge-segment') not in client.rows


def test_purge_owner_fairness_site_rides_the_namespace_storm_gate(monkeypatch):
    owner_key = privacy_owner_key('synthetic-fairness-owner')
    control_id = scheduler_control_key(owner_key)
    rows = {
        (f'{SITE_NAMESPACE}_control', control_id): {
            'rings': {'0': [f'0_{owner_key}', 'keep-me'], '1': [], '2': [f'2_{owner_key}']}
        },
        (f'{SITE_NAMESPACE}_queues', f'0_{owner_key}'): {'link_mode': 'fifo_array', 'items': []},
        (f'{SITE_NAMESPACE}_owners', owner_key): {},
        (f'{SITE_NAMESPACE}_merge_holds', owner_key): {'held': True},
    }
    scripted = ScriptedStormDamper(residual_schedule=[0.0], wave_wait=0.5, generation=4, entry_wait=0.15)
    client, _recorder = make_site(monkeypatch, rows, scripted)

    _purge_owner_fairness(client, SITE_NAMESPACE, owner_key)

    assert scripted.events[0] == ['consult', PURGE_OWNER_FAIRNESS_LABEL, 0.15]
    assert scripted.note_success_args == [[PURGE_OWNER_FAIRNESS_LABEL, 4]]
    assert client.rows[(f'{SITE_NAMESPACE}_control', control_id)]['rings']['0'] == ['keep-me']
    assert (f'{SITE_NAMESPACE}_owners', owner_key) not in client.rows
    assert (f'{SITE_NAMESPACE}_merge_holds', owner_key) not in client.rows
    assert (f'{SITE_NAMESPACE}_queues', f'0_{owner_key}') not in client.rows


def test_purge_result_erase_site_rides_the_namespace_storm_gate(monkeypatch):
    owner_key = privacy_owner_key('synthetic-erase-owner')
    result_row = {
        'owner_key': owner_key,
        'segment_id': 'erase-segment',
        'capture_at': 100.0,
        'protocol_version': 1,
        'log_sequence': 42,
        'projection_state': 'ready',
        'result_uri': 'gs://synthetic/erase/segment.enc',
    }
    rows = {
        (f'{SITE_NAMESPACE}_results', 'erase-segment'): dict(result_row),
        (f'{SITE_NAMESPACE}_owners', owner_key): {'projection_watermark': 'erase-segment'},
    }
    scripted = ScriptedStormDamper(residual_schedule=[0.0], wave_wait=0.5, generation=1, entry_wait=0.05)
    client, _recorder = make_site(monkeypatch, rows, scripted)
    snapshot = SimpleNamespace(
        id='erase-segment',
        reference=client.collection(f'{SITE_NAMESPACE}_results').document('erase-segment'),
        to_dict=lambda: dict(result_row),
    )

    _erase_result(client, SITE_NAMESPACE, snapshot)

    assert scripted.events[0] == ['consult', PURGE_RESULT_ERASE_LABEL, 0.05]
    assert scripted.note_success_args == [[PURGE_RESULT_ERASE_LABEL, 1]]
    erased = client.rows[(f'{SITE_NAMESPACE}_results', 'erase-segment')]
    assert erased['projection_state'] == 'erased'
    assert erased['log_sequence'] == 42
    assert 'result_uri' not in erased
    assert 'expires_at' in erased


def test_resolver_shares_the_namespace_damper():
    resolved = _purge_storm_damper('batch_pipeline_dev')
    assert resolved is storage.shared_storm_damper('batch_pipeline_dev')
    assert resolved is not None


def test_resolver_honours_the_retry_kill_switch(monkeypatch):
    monkeypatch.setattr('config.batch_pipeline.contention_retry_enabled', lambda: False)
    assert _purge_storm_damper('batch_pipeline_dev') is None


def test_resolver_honours_the_damper_kill_switch(monkeypatch):
    monkeypatch.setattr('config.batch_pipeline.contention_storm_damper_enabled', lambda: False)
    assert _purge_storm_damper('batch_pipeline_dev') is None


def test_dormant_switches_keep_the_sites_on_the_bare_ladder(monkeypatch):
    owner_key = privacy_owner_key('synthetic-dormant-owner')
    rows = purge_rows(SITE_NAMESPACE, owner_key, 'dormant-segment')
    scripted = ScriptedStormDamper(residual_schedule=[0.0], wave_wait=0.5, generation=0, entry_wait=0.9)
    monkeypatch.setattr(purge_module, 'mirror_refresh', MagicMock())
    monkeypatch.setattr('config.batch_pipeline.contention_retry_enabled', lambda: False)
    client = StrictFirestore(rows)
    recorder = ChainSleepRecorder()
    silence_and_pin_chain(monkeypatch, recorder)
    snapshot = SimpleNamespace(
        id='dormant-segment',
        reference=client.collection(f'{SITE_NAMESPACE}_jobs').document('dormant-segment'),
    )

    _delete_job(client, SITE_NAMESPACE, snapshot, retain_ordering=False)

    assert scripted.events == []
    assert scripted.slept == []
    assert recorder.sleeps == []
    assert (f'{SITE_NAMESPACE}_jobs', 'dormant-segment') not in client.rows


def test_docs_page_names_the_purge_gate():
    from pathlib import Path

    docs = Path(__file__).resolve().parents[2] / 'docs' / 'batch-purge-storm-gate.md'
    assert docs.exists(), 'the purge storm-gate contract must be documented'
    text = docs.read_text(encoding='utf-8')
    assert 'FC-privacy-purge-chain-collides-inside-armed-storm-window' in text
    assert 'batch_purge_job_unlink_backoff' in text
    assert 'batch_purge_owner_fairness' in text
    assert 'batch_purge_result_erase' in text
