#!/usr/bin/env python3
"""A persist-tail privacy refusal ends the chain with typed custody.

``BatchPrivacyBlocked`` is the transactional privacy authority's verdict that
an owner's account, data-protection setting, privacy generation or
conversation state stopped accepting server results for a unit. It raises
inside the persist register's transaction — after decode, VAD, diarization
and ASR are all done — and it is deterministic on identical input: the fence
reads the same live documents every replay's identity fields name. The
boundary used to fall through every persist loss classifier with it (a
non-Google custody class skips the re-strike lane by design), book
``error_class=BatchPrivacyBlocked stage=persist reason=unclassified`` on the
ERROR fault channels, walk the job ladder for every remaining attempt against
the same fence, and hand the exhausted unit to a recovery re-run that feeds
the same fence the same audio. The boundary now books the typed
``persist_privacy_refused`` custody handoff the ``persist_payload_invalid``
refusal rides — the chain ends at the first occurrence and every fault
channel demotes to the designed transition report — and the pump lanes that
can meet the same fence mid-pass report ``outcome=privacy_blocked`` on INFO
instead of re-reporting the user-intent decision on the ERROR retry line
forever.

Failure-Class: FC-privacy-refusal-at-persist-walks-gpu-retry-ladder-as-unclassified-worker-fault
"""

import asyncio
import logging

import pytest
from google.api_core.exceptions import Aborted, InvalidArgument

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from diarizer import batch_pipeline as bp
from diarizer.batch_pipeline import persist_loss_is_privacy_refusal
from utils.batch_pipeline.errors import (
    VALIDATION_DISPOSITION_PERSIST_REASONS,
    VALIDATION_DISPOSITION_PERSIST_STAGE,
    report_terminal_quarantine,
    validate_worker_failure,
    validate_worker_failure_evidence,
    validation_disposition_failure,
)
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason
from utils.observability.reasons import WorkerValidationReason

from tests.unit.persist_lane_harness import (
    PerSegmentPersist,
    ScriptedPersist,
    WORKER_LOGGER,
    contention,
    exhaust_script,
    item,
    run_lane,
    run_two_units,
)

FC = 'FC-privacy-refusal-at-persist-walks-gpu-retry-ladder-as-unclassified-worker-fault'
PUMP_LOGGER = 'utils.batch_pipeline.pump'

PRIVACY_REASONS = (
    'account_deleted',
    'account_missing',
    'data_protection_changed',
    'privacy_generation_changed',
    'conversation_redirect_cycle',
    'conversation_fence_budget',
    'conversation_deleted',
    'recording_privacy_changed',
    'conversation_redirect_missing',
)


# --- The classifier verdict -------------------------------------------------------


@pytest.mark.parametrize('token', PRIVACY_REASONS)
def test_the_classifier_answers_for_every_documented_refusal_reason(token):
    assert persist_loss_is_privacy_refusal(BatchPrivacyBlocked(token)) is True


def test_the_classifier_answers_for_the_conversation_ride_along():
    assert persist_loss_is_privacy_refusal(BatchPrivacyBlocked('conversation_deleted', conversation_id='c1')) is True


def test_the_classifier_reads_the_type_never_the_message():
    # A hostile or unknown refusal text is still the fence: the verdict is
    # type-based, so wording cannot drift the split.
    for text in ('totally-custom-refusal', 'account_deleted', '', 'agree; please proceed'):
        assert persist_loss_is_privacy_refusal(BatchPrivacyBlocked(text)) is True
    # A plain RuntimeError carrying a privacy-shaped message is not the fence.
    assert persist_loss_is_privacy_refusal(RuntimeError('account_deleted')) is False


@pytest.mark.parametrize(
    'fault',
    (
        InvalidArgument('burst'),
        InvalidArgument('400 The referenced transaction has expired or is no longer valid'),
        Aborted('row locked'),
        None,  # the contention stamp, built below
        TimeoutError('burst'),
        OSError('socket dropped'),
        ValueError('bad payload'),
        BatchValidationError(ValidationReason.WORD_CLOCK),
    ),
)
def test_the_classifier_defers_every_other_persist_family(fault):
    assert persist_loss_is_privacy_refusal(contention() if fault is None else fault) is False


@pytest.mark.parametrize('hostile', (None, 7, 'burst', True, object()))
def test_the_classifier_never_raises_on_hostile_input(hostile):
    assert persist_loss_is_privacy_refusal(hostile) is False


# --- The boundary booking ---------------------------------------------------------


def test_a_privacy_refusal_books_the_typed_custody_handoff(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([BatchPrivacyBlocked('account_deleted')], default='OK'))
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    assert run['results'][0].segment_id == 'a'
    assert run['results'][0].stage == 'persist'
    assert run['results'][0].reason == 'persist_privacy_refused'


def test_the_handoff_ends_the_chain_at_the_first_occurrence(monkeypatch):
    # Deterministic on identical input: one persist call, no re-strike
    # sleeps, one GPU pass — the ladder never walks.
    run = run_lane(monkeypatch, ScriptedPersist([BatchPrivacyBlocked('privacy_generation_changed')], default='OK'))
    assert len(run['persist'].calls) == 1 and run['sleeps'].delays == []
    assert run['meta']['decoded'] == ['a']
    assert run['worker'].counts['items'] == 1


@pytest.mark.parametrize(
    ('gate', 'safety'), (('false', 'false'), ('true', 'true'), ('true', 'false'), ('false', 'true'))
)
def test_the_handoff_is_independent_of_the_gate_and_safety_net(monkeypatch, gate, safety):
    script = ScriptedPersist([BatchPrivacyBlocked('data_protection_changed')], default='OK')
    run = run_lane(monkeypatch, script, gate=gate, safety_net=safety)
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    assert run['results'][0].reason == 'persist_privacy_refused'


def test_the_handoff_keeps_the_failure_callback_contract(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([BatchPrivacyBlocked('account_deleted')], default='OK'))
    assert run['meta']['failures'] == [('a', 'BatchPrivacyBlocked')]


def test_a_custom_refusal_wording_books_the_same_handoff(monkeypatch):
    run = run_lane(monkeypatch, ScriptedPersist([BatchPrivacyBlocked('totally-custom-refusal')], default='OK'))
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    assert run['results'][0].reason == 'persist_privacy_refused'


def test_a_sibling_refusal_does_not_poison_its_neighbor(monkeypatch):
    def refuse(work, payload):
        raise BatchPrivacyBlocked('account_deleted')

    routes = {'a': refuse, 'b': lambda work, payload: 'stored://b'}
    run = run_two_units(monkeypatch, PerSegmentPersist(routes))
    by_id = {r.segment_id: type(r).__name__ for r in run['results']}
    assert by_id == {'a': 'ValidationFailureWork', 'b': 'WorkResult'}


def test_a_plain_runtime_error_is_not_the_fence(monkeypatch):
    # The split reads the type: a privacy-shaped message on a foreign class
    # keeps the legacy retryable booking and its anonymous evidence.
    run = run_lane(monkeypatch, ScriptedPersist([RuntimeError('account_deleted')], default='OK'), safety_net='true')
    assert [type(r).__name__ for r in run['results']] == ['FailedWork']
    assert run['results'][0].worker_failure == {'stage': 'persist', 'reason': 'unknown'}


def test_every_other_persist_family_keeps_its_verdict(monkeypatch):
    # Non-interference: the payload refusal still books its own typed
    # handoff, and a transport exhaustion still books the retryable fault.
    run = run_lane(monkeypatch, exhaust_script())
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    assert run['results'][0].reason == 'persist_payload_invalid'
    run = run_lane(monkeypatch, ScriptedPersist([TimeoutError('burst')] * 3, default='OK'), safety_net='true')
    assert [type(r).__name__ for r in run['results']] == ['FailedWork']


# --- The fault channels demote together -------------------------------------------


def test_the_worker_fault_line_reports_the_transition_not_the_fault(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, WORKER_LOGGER)
    run_lane(monkeypatch, ScriptedPersist([BatchPrivacyBlocked('account_deleted')], default='OK'))
    text = caplog.text
    assert 'event=batch_worker_failed error_class=BatchPrivacyBlocked' not in text
    assert 'event=batch_validation_disposition outcome=recovery_handoff' in text
    assert 'stage=persist' in text and 'reason=persist_privacy_refused' in text


def test_a_real_persist_fault_keeps_the_error_channel(monkeypatch, caplog):
    # A transport exhaustion books the legacy retryable fault and keeps the
    # attributed ERROR line — only the privacy refusal demotes.
    caplog.set_level(logging.DEBUG, WORKER_LOGGER)
    run_lane(
        monkeypatch, ScriptedPersist([TimeoutError('burst')] * 3, default=TimeoutError('burst')), safety_net='true'
    )
    assert 'event=batch_worker_failed error_class=TimeoutError' in caplog.text
    assert 'event=batch_worker_failed error_class=BatchPrivacyBlocked' not in caplog.text


class RecordingLogger:
    """Minimal logger double capturing level and event per call."""

    def __init__(self):
        self.calls = []

    def _book(self, level, message, *args):
        self.calls.append((level, message % args if args else message))

    def info(self, message, *args):
        self._book(logging.INFO, message, *args)

    def warning(self, message, *args):
        self._book(logging.WARNING, message, *args)

    def error(self, message, *args):
        self._book(logging.ERROR, message, *args)


def _first_event(logger, event):
    for level, text in logger.calls:
        if text.startswith(event):
            return level, text
    return None, None


def test_the_terminal_quarantine_demotes_the_refusal_at_both_terminals():
    diagnosis = {'stage': 'persist', 'reason': 'persist_privacy_refused'}
    for _ in range(2):  # the verdict and expiry terminals share the helper
        logger = RecordingLogger()
        report_terminal_quarantine(logger, attempt=1, diagnosis=diagnosis)
        level, text = _first_event(logger, 'event=batch_validation_disposition')
        assert level == logging.INFO and 'outcome=held_for_disposition' in text
        assert 'worker_reason=persist_privacy_refused' in text
        assert all(level != logging.ERROR or 'batch_quarantined' not in text for level, text in logger.calls)
        assert _first_event(logger, 'event=batch_recovery outcome=held reason=awaiting_fenced_recovery')[0] == (
            logging.WARNING
        )


def test_an_anonymous_diagnosis_keeps_the_error_terminal():
    logger = RecordingLogger()
    report_terminal_quarantine(logger, attempt=5, diagnosis={'stage': 'persist', 'reason': 'unclassified'})
    level, _ = _first_event(logger, 'event=batch_quarantined')
    assert level == logging.ERROR


# --- The closed vocabulary and family scoping -------------------------------------


def test_the_closed_validators_admit_the_typed_pair():
    validate_worker_failure({'stage': 'persist', 'reason': 'persist_privacy_refused'})
    validate_worker_failure_evidence({'stage': 'persist', 'reason': 'persist_privacy_refused'})


def test_the_family_answers_at_persist_under_both_switch_states():
    diagnosis = {'stage': 'persist', 'reason': 'persist_privacy_refused'}
    assert validation_disposition_failure(diagnosis, disposition_enabled=True) is True
    assert validation_disposition_failure(diagnosis, disposition_enabled=False) is True


@pytest.mark.parametrize('stage', ('fetch_decode', 'assemble_words', 'vad_windows', 'word_clocks'))
def test_the_family_is_stage_scoped_like_the_payload_refusal(stage):
    assert (
        validation_disposition_failure({'stage': stage, 'reason': 'persist_privacy_refused'}, disposition_enabled=True)
        is False
    )


@pytest.mark.parametrize(
    'hostile',
    (
        None,
        {},
        {'stage': 'persist'},
        {'reason': 'persist_privacy_refused'},
        {'stage': 'persist', 'reason': 'persist_privacy_refused', 'extra': 1},
        {'stage': 7, 'reason': 'persist_privacy_refused'},
        {'stage': 'persist', 'reason': 7},
        {'stage': 'persist', 'reason': 'account_deleted'},
        {'stage': 'unknown', 'reason': 'unknown'},
    ),
)
def test_foreign_shapes_are_not_the_family(hostile):
    assert validation_disposition_failure(hostile, disposition_enabled=True) is False


def test_the_persist_disposition_pair_carries_both_refusals():
    assert VALIDATION_DISPOSITION_PERSIST_STAGE == 'persist'
    assert WorkerValidationReason.PERSIST_PRIVACY_REFUSED.value in VALIDATION_DISPOSITION_PERSIST_REASONS
    assert WorkerValidationReason.PERSIST_PAYLOAD_INVALID.value in VALIDATION_DISPOSITION_PERSIST_REASONS


# --- The pump lanes report the designed outcome, never the ERROR retry ------------


def _pump_with(monkeypatch, run_once=None, maintain=None):
    from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401  (env pins)

    from tests.unit.test_batch_pipeline_scheduler import MemoryStore
    from utils.batch_pipeline.contracts import PoolCapacity
    from utils.batch_pipeline.scheduler import Scheduler

    store = MemoryStore()
    pump = Pump(Scheduler(store), _IdleWorker(), capacity=lambda: PoolCapacity(0.0, 8), poll_seconds=0.05)
    if run_once is not None:
        monkeypatch.setattr(pump, 'run_once', run_once)
    if maintain is not None:
        monkeypatch.setattr(pump, '_maintain', maintain)
    return pump


class _IdleWorker:
    def process_batch(self, items):
        return []


async def test_the_lane_reports_a_privacy_refusal_without_the_error_channel(monkeypatch, caplog):
    stop = asyncio.Event()
    passes = []

    async def run_once(*, stop_event=None, maintain=True):
        passes.append(1)
        if len(passes) == 1:
            stop_event.set()  # end the lane after the refused pass
            raise BatchPrivacyBlocked('account_deleted')
        return 0

    caplog.set_level(logging.DEBUG, PUMP_LOGGER)
    pump = _pump_with(monkeypatch, run_once=run_once)
    await pump._lane(stop)
    assert 'event=batch_pump outcome=privacy_blocked exception_type=BatchPrivacyBlocked' in caplog.text
    assert 'event=batch_pump outcome=retry' not in caplog.text


async def test_the_lane_survives_a_refused_pass_and_keeps_serving(monkeypatch):
    stop = asyncio.Event()
    passes = []

    async def run_once(*, stop_event=None, maintain=True):
        passes.append(1)
        if len(passes) == 1:
            raise BatchPrivacyBlocked('privacy_generation_changed')
        stop_event.set()  # second pass runs: the lane did not stall on the refusal
        return 0

    pump = _pump_with(monkeypatch, run_once=run_once)
    await asyncio.wait_for(pump._lane(stop), 5)
    assert len(passes) == 2


async def test_a_real_lane_fault_keeps_the_error_retry_line(monkeypatch, caplog):
    stop = asyncio.Event()

    async def run_once(*, stop_event=None, maintain=True):
        stop_event.set()
        raise RuntimeError('store exploded')

    caplog.set_level(logging.DEBUG, PUMP_LOGGER)
    pump = _pump_with(monkeypatch, run_once=run_once)
    await pump._lane(stop)
    assert 'event=batch_pump outcome=retry exception_type=RuntimeError' in caplog.text
    assert 'event=batch_pump outcome=privacy_blocked' not in caplog.text


async def test_the_maintenance_loop_reports_a_refusal_without_the_error_channel(monkeypatch, caplog):
    stop = asyncio.Event()
    sweeps = []

    async def maintain():
        sweeps.append(1)
        if len(sweeps) == 1:
            stop.set()
            raise BatchPrivacyBlocked('conversation_deleted')

    caplog.set_level(logging.DEBUG, PUMP_LOGGER)
    pump = _pump_with(monkeypatch, maintain=maintain)
    await pump._maintain_loop(stop)
    assert 'event=batch_maintenance outcome=privacy_blocked exception_type=BatchPrivacyBlocked' in caplog.text
    assert 'event=batch_maintenance outcome=retry' not in caplog.text


async def test_the_maintenance_loop_survives_a_refused_sweep(monkeypatch):
    stop = asyncio.Event()
    sweeps = []

    async def maintain():
        sweeps.append(1)
        if len(sweeps) == 1:
            raise BatchPrivacyBlocked('account_missing')
        stop.set()  # second sweep runs: the loop did not stall on the refusal

    pump = _pump_with(monkeypatch, maintain=maintain)
    await asyncio.wait_for(pump._maintain_loop(stop), 5)
    assert len(sweeps) == 2


async def test_a_real_maintenance_fault_keeps_the_error_retry_line(monkeypatch, caplog):
    stop = asyncio.Event()

    async def maintain():
        stop.set()
        raise TimeoutError('store exploded')

    caplog.set_level(logging.DEBUG, PUMP_LOGGER)
    pump = _pump_with(monkeypatch, maintain=maintain)
    await pump._maintain_loop(stop)
    assert 'event=batch_maintenance outcome=retry exception_type=TimeoutError' in caplog.text
    assert 'event=batch_maintenance outcome=privacy_blocked' not in caplog.text
