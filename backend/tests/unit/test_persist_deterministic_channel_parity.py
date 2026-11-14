#!/usr/bin/env python3
"""The persist refusal's typed handoff demotes both fault channels together.

The chain-ending custody handoff is designed platform behavior, so the
worker's ``batch_worker_failed`` ERROR line and the scheduler's terminal
``batch_quarantined`` ERROR line report ``event=batch_validation_disposition``
instead — keeping every diagnostic field — while the persist transport and
contention families keep their real-fault ERROR lines. This suite pins the
demotion at both logging sites, the immediate terminal economics the typed
handoff buys (one attempt, no ladder), the vocabulary admission gates, and
the hostile-input contract of the disposition arm.

Failure-Class: FC-deterministic-persist-refusal-walks-gpu-retry-ladder-as-unclassified-invalidargument
"""

import logging
import time
from pathlib import Path

import pytest
from google.api_core.exceptions import InvalidArgument

from tests.unit.persist_lane_harness import (
    GATE,
    ScriptedPersist,
    SleepRecorder,
    WORKER_LOGGER,
    build_worker,
    exhaust_script,
    item,
    pin_full_gpu_stages,
    run_lane,
)
from tests.unit.test_batch_exhaustion_publication_contract_matrix import lease, make_pump
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import setup_worker
from utils.batch_pipeline.contracts import ValidationFailureWork
from utils.batch_pipeline.errors import (
    VALIDATION_DISPOSITION_PERSIST_REASONS,
    VALIDATION_DISPOSITION_PERSIST_STAGE,
    WORKER_VALIDATION_REASONS,
    validate_worker_failure,
    validate_worker_failure_evidence,
    validation_disposition_failure,
)
from utils.batch_pipeline.scheduler import Scheduler
from utils.observability.reasons import WorkerValidationReason, WorkerValidationStage

FC = 'FC-deterministic-persist-refusal-walks-gpu-retry-ladder-as-unclassified-invalidargument'
REFUSAL = {'stage': 'persist', 'reason': 'persist_payload_invalid'}


@pytest.fixture(autouse=True)
def _pin_env(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')


# --- Worker fault channel ---------------------------------------------------------


def test_the_exhausted_refusal_logs_the_designed_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, exhaust_script())
    demoted = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert demoted and demoted[0].levelno == logging.INFO
    line = demoted[0].getMessage()
    assert 'error_class=InvalidArgument stage=persist' in line
    assert 'reason=persist_payload_invalid' in line
    assert ' site=' not in line


def test_the_exhausted_refusal_logs_no_worker_fault_line(monkeypatch, caplog):
    run = run_lane(monkeypatch, exhaust_script())
    assert not [r for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]


def test_the_gate_off_refusal_demotes_the_same_way(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=WORKER_LOGGER)
    run = run_lane(monkeypatch, exhaust_script(), gate='false')
    demoted = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert demoted and 'reason=persist_payload_invalid' in demoted[0].getMessage()
    assert not [r for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]


def test_a_transport_exhaustion_keeps_the_worker_fault_line(monkeypatch, caplog):
    run = run_lane(monkeypatch, exhaust_script(TimeoutError))
    faults = [r for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]
    assert faults and faults[0].levelno == logging.ERROR
    assert 'error_class=TimeoutError stage=persist' in faults[0].getMessage()


def test_the_demoted_line_names_no_exception_message(monkeypatch, caplog):
    secret = 'uid-secret-payload-poison'
    run = run_lane(monkeypatch, ScriptedPersist([InvalidArgument(secret)] * 3, default=InvalidArgument(secret)))
    assert [type(r).__name__ for r in run['results']] == ['ValidationFailureWork']
    for record in caplog.records:
        assert secret not in record.getMessage()


# --- Scheduler terminal channel and economics -------------------------------------


def _terminal_lines(caplog):
    return [record for record in caplog.records if 'event=batch_quarantined' in record.getMessage()]


def _drive_publication(monkeypatch, caplog, work):
    store = MemoryStore()
    pump = make_pump(scheduler=Scheduler(store))
    now = time.time()
    pump.scheduler.enqueue(item(), now)
    lease_ = pump.scheduler.pull(now)[0]
    with caplog.at_level(logging.INFO):
        accepted = __import__('asyncio').run(pump._publish(lease_, {'a': work}, set()))
    return store, accepted


def test_the_refusal_handoff_quarantines_at_its_first_attempt(monkeypatch, caplog):
    store, accepted = _drive_publication(
        monkeypatch, caplog, ValidationFailureWork('a', 'persist', 'persist_payload_invalid')
    )
    assert accepted is True
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined'
    assert job['worker_failure'] == REFUSAL


def test_the_refusal_terminal_logs_the_designed_line_not_the_quarantine(monkeypatch, caplog):
    store, accepted = _drive_publication(
        monkeypatch, caplog, ValidationFailureWork('a', 'persist', 'persist_payload_invalid')
    )
    assert accepted is True
    assert not _terminal_lines(caplog)
    demoted = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert demoted and demoted[0].levelno == logging.INFO
    assert 'stage=persist worker_reason=persist_payload_invalid' in demoted[0].getMessage()


def test_the_terminal_demotion_is_unconditional_of_the_disposition_switch(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')
    store, accepted = _drive_publication(
        monkeypatch, caplog, ValidationFailureWork('a', 'persist', 'persist_payload_invalid')
    )
    assert accepted is True
    assert not _terminal_lines(caplog)
    assert [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]


def test_a_transport_diagnosis_keeps_the_quarantine_error_line(monkeypatch, caplog):
    # The generic persist evidence is evidence-only: it rides the ladder and
    # its preserved diagnosis names the terminal ERROR line, never the
    # designed-handoff channel.
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), 1000.0)
    caplog.set_level(logging.INFO)
    lease_ = queue.pull(1000.0)[0]
    assert queue.fail('a', lease_.token, 1000.0, worker_failure_evidence={'stage': 'persist', 'reason': 'unknown'})
    job = store.rows['jobs', 'a']
    job.update(state='leased', token=lease_.token, lease_until=10.0**12)
    assert queue.fail('a', lease_.token, 1000.0, quarantine=True, worker_failure_evidence=None)
    lines = _terminal_lines(caplog)
    assert lines and lines[-1].levelno == logging.ERROR
    assert 'stage=persist worker_reason=unknown' in lines[-1].getMessage()


def test_the_recovery_await_warning_still_fires_for_the_refusal(monkeypatch, caplog):
    store, accepted = _drive_publication(
        monkeypatch, caplog, ValidationFailureWork('a', 'persist', 'persist_payload_invalid')
    )
    assert accepted is True
    assert any(
        'event=batch_recovery outcome=held reason=awaiting_fenced_recovery' in r.getMessage() for r in caplog.records
    )


def test_the_plain_worker_booking_stays_the_retryable_route(monkeypatch):
    worker, *_ = setup_worker(persist=__import__('unittest').mock.Mock(side_effect=OSError('upload failed')))
    results = worker.process_batch([item()])
    assert len(results) == 1 and not isinstance(results[0], ValidationFailureWork)


# --- Vocabulary admission ----------------------------------------------------------


def test_the_refusal_token_joins_the_closed_reasons():
    assert WorkerValidationReason.PERSIST_PAYLOAD_INVALID.value == 'persist_payload_invalid'
    assert 'persist_payload_invalid' in WORKER_VALIDATION_REASONS


def test_the_terminal_gate_admits_the_closed_pair():
    validate_worker_failure(REFUSAL)


def test_the_evidence_gate_admits_the_closed_pair():
    assert validate_worker_failure_evidence(REFUSAL) is None


def test_the_handoff_contract_admits_the_closed_pair():
    work = ValidationFailureWork('a', 'persist', 'persist_payload_invalid')
    assert work.stage == 'persist' and work.reason == 'persist_payload_invalid'


def test_the_disposition_constants_are_stage_scoped():
    assert VALIDATION_DISPOSITION_PERSIST_STAGE == WorkerValidationStage.PERSIST.value
    assert VALIDATION_DISPOSITION_PERSIST_REASONS == {'persist_payload_invalid'}


def test_the_disposition_arm_answers_for_the_closed_pair_at_persist():
    assert validation_disposition_failure(REFUSAL, disposition_enabled=False) is True
    assert validation_disposition_failure(REFUSAL, disposition_enabled=True) is True


@pytest.mark.parametrize('stage', ('fetch_decode', 'vad_windows', 'word_clocks', 'assemble_words', 'asr_recovery'))
def test_the_disposition_arm_is_stage_scoped(stage):
    assert (
        validation_disposition_failure({'stage': stage, 'reason': 'persist_payload_invalid'}, disposition_enabled=True)
        is False
    )


@pytest.mark.parametrize(
    'reason', ('unknown', 'empty_asr', 'unsupported_language', 'staged_audio_invalid', 'unclassified')
)
def test_the_disposition_arm_is_reason_scoped_at_persist(reason):
    # Flagged vad/word verdicts are the stage-agnostic arm's by design (the
    # disposition switch decides them at any closed stage); every non-flagged
    # reason at the persist stage keeps its fault classification.
    expected = reason in ('word_clock', 'word_shape', 'word_sequence', 'vad_nonfinite', 'vad_order', 'vad_bounds')
    assert validation_disposition_failure({'stage': 'persist', 'reason': reason}, disposition_enabled=True) is expected


@pytest.mark.parametrize(
    'hostile',
    (
        None,
        7,
        'persist',
        REFUSAL | {'extra': 1},
        {'stage': 'persist'},
        {'stage': 'persis', 'reason': 'persist_payload_invalid'},
        {'stage': 'persist ', 'reason': 'persist_payload_invalid'},
        {'stage': 'persist', 'reason': 'persist_payload_invalid '},
        {'stage': 7, 'reason': 'persist_payload_invalid'},
        {'stage': 'persist', 'reason': 7},
    ),
)
def test_the_disposition_arm_never_raises_on_hostile_input(hostile):
    assert validation_disposition_failure(hostile, disposition_enabled=True) is False


# --- Source and doc parity ---------------------------------------------------------

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_the_reasons_member_carries_the_failure_class():
    source = (BACKEND_ROOT / 'utils' / 'observability' / 'reasons.py').read_text()
    assert f'Failure-Class: {FC}' in source
    assert 'PERSIST_PAYLOAD_INVALID' in source


def test_the_errors_arm_carries_the_failure_class():
    source = (BACKEND_ROOT / 'utils' / 'batch_pipeline' / 'errors.py').read_text()
    assert f'Failure-Class: {FC}' in source
    assert 'VALIDATION_DISPOSITION_PERSIST_STAGE' in source


def test_the_doc_pins_the_ladder_economics():
    doc = BACKEND_ROOT / 'docs' / 'batch-persist-deterministic-terminal-parity.md'
    assert doc.exists()
    text = doc.read_text()
    assert 'four wasted GPU attempts' in text
    assert 'chain ends at its first occurrence' in text
