"""The persist tail joins the closed worker-validation stage vocabulary.

The worker attributes every persist fault — the settle path and the serial
persist tail — with ``fail(item, exc, 'persist')``, but ``persist`` was not a
member of the shared ``WorkerValidationStage`` vocabulary the evidence chain
routes on. ``transient_failure_evidence`` therefore refused the stage and the
``FailedWork`` handoff crossed the pump evidence-less on every attempt, the
scheduler stored no diagnosis, and a unit whose ladder exhausted on persist
faults terminal-quarantined as ``stage=unknown worker_reason=unclassified``
even though the worker's own ERROR line already named ``stage=persist``. A
persist-stage typed verdict also raised ``ValueError`` out of
``validate_worker_failure`` and crashed the publication transition it rode.

This suite pins the joined vocabulary end to end: the token and its
consumers, the evidence extraction, both store gates, the scheduler's
ladder/terminal behavior over persist diagnoses (including the preserved
diagnosis across evidence-less attempts and the designed demotion arms'
persist isolation), the pump's evidence forwarding, the worker boundary, and
the doc claims. Generic persist faults close ``{'stage': 'persist',
'reason': 'unknown'}``; typed reasons pass through; untyped provider stages
stay unevidenced; persist faults stay on the ERROR fault channel because a
storage/register outage is a real fault, not a designed handoff.

Failure-Class: FC-persist-stage-failure-quarantines-anonymous-without-stage-evidence
"""

import logging
import re
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from config.batch_pipeline import worker_validation_disposition_enabled
from diarizer.batch_pipeline import transient_failure_evidence
from utils.batch_pipeline.scheduler import Scheduler
from tests.unit.test_batch_exhaustion_publication_contract_matrix import lease, make_pump
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import item, setup_worker
from utils.batch_pipeline.contracts import FailedWork, WorkResult
from utils.batch_pipeline.errors import (
    WORKER_VALIDATION_REASON_TOKENS,
    WORKER_VALIDATION_REASONS,
    WORKER_VALIDATION_STAGES,
    empty_ladder_recovery_failure,
    language_guard_redrive_failure,
    validate_worker_failure,
    validate_worker_failure_evidence,
    validation_disposition_failure,
)
from utils.observability.reasons import WorkerValidationReason, WorkerValidationStage, reason_values

FC = 'FC-persist-stage-failure-quarantines-anonymous-without-stage-evidence'
PERSIST_EVIDENCE = {'stage': 'persist', 'reason': 'unknown'}
TYPED_REASONS = tuple(member.value for member in WorkerValidationReason if member.value != 'unknown')
NEAR_MISS_STAGES = ('persis', 'persistx', 'Persist', 'PERSIST', ' persist', 'persist ', 'persist\t', 'persist_')

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _evidence_pipeline(monkeypatch):
    # The ordinary-failure handoff requires the safety net; the disposition
    # flag default is pinned per-test where the demotion arms are under test.
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')


def _quarantined(store):
    return store.rows['jobs', 'a']


def _drive_scheduler(store, **kwargs):
    queue = Scheduler(store)
    queue.enqueue(item(), 1000.0)
    lease_token = queue.pull(1000.0)[0].token
    return queue, queue.fail('a', lease_token, 1000.0, **kwargs)


def _terminal_lines(caplog):
    return [record for record in caplog.records if 'event=batch_quarantined' in record.getMessage()]


# --- The vocabulary member and its consumers ------------------------------------


def test_persist_is_the_shared_enum_member():
    assert WorkerValidationStage.PERSIST.value == 'persist'


def test_str_of_the_token_is_its_value():
    assert str(WorkerValidationStage.PERSIST) == 'persist'


def test_persist_joins_the_closed_stage_set():
    assert 'persist' in WORKER_VALIDATION_STAGES
    assert WORKER_VALIDATION_STAGES == reason_values(WorkerValidationStage)


def test_the_closed_stage_set_counts_six_members():
    # unknown is the legacy default, never a closed stage: reason_values
    # excludes it, so the vocabulary is the five GPU stages plus persist.
    assert sorted(reason_values(WorkerValidationStage)) == [
        'asr_recovery',
        'assemble_words',
        'fetch_decode',
        'persist',
        'vad_windows',
        'word_clocks',
    ]


def test_the_worker_attribute_sites_use_the_persist_token():
    source = (BACKEND_ROOT / 'diarizer' / 'batch_pipeline.py').read_text()
    assert len(re.findall(r"fail\(item, exc, 'persist'\)", source)) == 1, 'settle_persist attributes with the token'
    assert re.search(r"stage\s*=\s*'persist'", source) is not None, 'the serial persist tail names the stage'


def test_stage_timings_already_times_the_persist_tail():
    from utils.batch_pipeline.stage_timings import STAGES

    assert 'persist' in STAGES and 'persist_settle' in STAGES


def test_the_evidence_gate_and_the_terminal_gate_share_the_stage_set():
    assert WORKER_VALIDATION_STAGES == reason_values(WorkerValidationStage)
    assert WORKER_VALIDATION_REASON_TOKENS >= WORKER_VALIDATION_REASONS
    assert 'unknown' in WORKER_VALIDATION_REASON_TOKENS and 'unknown' not in WORKER_VALIDATION_REASONS


# --- Evidence extraction --------------------------------------------------------


def test_generic_persist_fault_closes_to_stage_and_unknown():
    assert transient_failure_evidence('persist', 'unclassified') == PERSIST_EVIDENCE


def test_typed_persist_reason_passes_through():
    assert transient_failure_evidence('persist', 'word_clock') == {'stage': 'persist', 'reason': 'word_clock'}


def test_every_closed_reason_passes_through_at_persist():
    for reason in TYPED_REASONS:
        assert transient_failure_evidence('persist', reason) == {'stage': 'persist', 'reason': reason}


def test_off_vocabulary_persist_reason_collapses_to_unknown():
    assert transient_failure_evidence('persist', 'gibberish_payload') == PERSIST_EVIDENCE


def test_exception_text_never_reaches_persist_evidence():
    evidence = transient_failure_evidence('persist', 'synthetic-private-marker')
    assert evidence == PERSIST_EVIDENCE
    assert 'synthetic-private-marker' not in str(evidence)


def test_untyped_provider_stages_stay_unevidenced():
    assert transient_failure_evidence('asr', 'unclassified') is None
    assert transient_failure_evidence('diarize', 'word_clock') is None


def test_unknown_stays_a_non_stage_for_the_extraction():
    assert transient_failure_evidence('unknown', 'unknown') is None


def test_persist_evidence_shape_is_the_two_key_dict():
    assert set(PERSIST_EVIDENCE) == {'stage', 'reason'}


# --- The store gates ------------------------------------------------------------


def test_terminal_gate_accepts_typed_persist_diagnosis():
    validate_worker_failure({'stage': 'persist', 'reason': 'staged_audio_invalid'})


def test_terminal_gate_accepts_every_typed_reason_at_persist():
    for reason in TYPED_REASONS:
        validate_worker_failure({'stage': 'persist', 'reason': reason})


def test_terminal_gate_still_rejects_unknown_at_persist():
    with pytest.raises(ValueError, match='closed worker validation failure required'):
        validate_worker_failure(PERSIST_EVIDENCE)


@pytest.mark.parametrize('stage', NEAR_MISS_STAGES)
def test_terminal_gate_rejects_near_miss_persist_stages(stage):
    with pytest.raises(ValueError):
        validate_worker_failure({'stage': stage, 'reason': 'word_clock'})


def test_terminal_gate_rejects_malformed_shapes_at_persist():
    for bad in (
        {'stage': 'persist'},
        {'reason': 'word_clock'},
        {'stage': 'persist', 'reason': 'word_clock', 'extra': 1},
        {},
        ['persist', 'word_clock'],
        ('persist', 'word_clock'),
        'persist',
        None,
        7,
        True,
    ):
        with pytest.raises(ValueError):
            validate_worker_failure(bad)


def test_terminal_gate_message_carries_no_payload_text():
    with pytest.raises(ValueError) as raised:
        validate_worker_failure({'stage': 'persist', 'reason': 'synthetic-private-marker'})
    assert 'synthetic-private-marker' not in str(raised.value)


def test_evidence_gate_accepts_persist_with_unknown():
    assert validate_worker_failure_evidence(PERSIST_EVIDENCE) is None


def test_evidence_gate_accepts_every_typed_reason_at_persist():
    for reason in TYPED_REASONS:
        assert validate_worker_failure_evidence({'stage': 'persist', 'reason': reason}) is None


def test_evidence_gate_rejects_gibberish_and_near_misses_at_persist():
    with pytest.raises(ValueError):
        validate_worker_failure_evidence({'stage': 'persist', 'reason': 'synthetic-private-marker'})
    for stage in NEAR_MISS_STAGES:
        with pytest.raises(ValueError):
            validate_worker_failure_evidence({'stage': stage, 'reason': 'unknown'})


# --- Scheduler ladder and terminal record ---------------------------------------


def test_fail_accepts_persist_stage_evidence():
    store = MemoryStore()
    queue, accepted = _drive_scheduler(store, worker_failure_evidence=PERSIST_EVIDENCE)
    assert accepted is True


def test_fail_stores_the_persist_diagnosis_on_the_job():
    store = MemoryStore()
    _drive_scheduler(store, worker_failure_evidence=PERSIST_EVIDENCE)
    assert _quarantined(store)['worker_failure_evidence'] == PERSIST_EVIDENCE


def test_typed_persist_verdict_no_longer_crashes_the_transition():
    store = MemoryStore()
    queue, accepted = _drive_scheduler(store, worker_failure={'stage': 'persist', 'reason': 'staged_audio_invalid'})
    assert accepted is True
    assert _quarantined(store)['worker_failure'] == {'stage': 'persist', 'reason': 'staged_audio_invalid'}


def test_exhausting_typed_persist_verdict_names_persist_in_the_terminal_record(caplog):
    store = MemoryStore()
    with caplog.at_level(logging.INFO):
        _drive_scheduler(store, worker_failure={'stage': 'persist', 'reason': 'staged_audio_invalid'})
    lines = [record.getMessage() for record in _terminal_lines(caplog)]
    assert lines and 'stage=persist worker_reason=staged_audio_invalid' in lines[-1]


def test_persist_terminal_record_stays_on_the_error_channel(caplog):
    store = MemoryStore()
    with caplog.at_level(logging.INFO):
        _drive_scheduler(store, worker_failure={'stage': 'persist', 'reason': 'staged_audio_invalid'})
    terminal = [record for record in _terminal_lines(caplog) if 'stage=persist' in record.getMessage()]
    assert terminal and terminal[-1].levelno == logging.ERROR


def test_evidence_only_persist_diagnosis_survives_evidence_less_attempts(caplog):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), 1000.0)
    with caplog.at_level(logging.INFO):
        # Attempt 1 carries the persist evidence and defers; the terminal
        # rung arrives evidence-less (the lease rows restored the way the
        # production re-lease would) and must still name the preserved
        # diagnosis, not the anonymous shape.
        lease_ = queue.pull(1000.0)[0]
        assert queue.fail('a', lease_.token, 1000.0, worker_failure_evidence=PERSIST_EVIDENCE) is True
        job = store.rows['jobs', 'a']
        assert job['worker_failure_evidence'] == PERSIST_EVIDENCE
        job.update(state='leased', token=lease_.token, lease_until=10.0**12)
        assert queue.fail('a', lease_.token, 1000.0, quarantine=True, worker_failure_evidence=None) is True
    assert _quarantined(store)['state'] == 'quarantined'
    lines = [record.getMessage() for record in _terminal_lines(caplog)]
    assert lines and 'stage=persist worker_reason=unknown' in lines[-1]


def test_a_non_flagged_typed_persist_reason_stays_on_the_error_channel_with_disposition_on(caplog):
    # The unconditional disposition arm is fetch_decode-bound: a staged-audio
    # verdict at persist is a real fault line, not the designed handoff, even
    # with the disposition switch on.
    monkey_disposition = pytest.MonkeyPatch()
    monkey_disposition.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    try:
        store = MemoryStore()
        with caplog.at_level(logging.INFO):
            _drive_scheduler(store, worker_failure={'stage': 'persist', 'reason': 'staged_audio_invalid'})
        assert _terminal_lines(caplog)
    finally:
        monkey_disposition.undo()


def test_flagged_persist_verdict_demotes_only_with_the_disposition_switch_on(caplog):
    # The flagged arm mirrors the boundary's stage-agnostic disposition: with
    # the switch that decided the durable chain end on, a closed vad/word
    # verdict at persist is the designed hold; with it off the fault line
    # stays ERROR.
    switch = pytest.MonkeyPatch()
    switch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    try:
        assert worker_validation_disposition_enabled() is True
        assert validation_disposition_failure({'stage': 'persist', 'reason': 'word_clock'}, disposition_enabled=True)
    finally:
        switch.undo()
    assert (
        validation_disposition_failure({'stage': 'persist', 'reason': 'word_clock'}, disposition_enabled=False) is False
    )


def test_terminal_record_defaults_stay_for_never_diagnosed_units(caplog):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), 1000.0)
    with caplog.at_level(logging.INFO):
        # No attempt ever carries evidence: the terminal rung keeps the
        # historical anonymous default for a never-diagnosed unit.
        lease_ = queue.pull(1000.0)[0]
        assert queue.fail('a', lease_.token, 1000.0, quarantine=True) is True
    assert _quarantined(store)['state'] == 'quarantined'
    lines = [record.getMessage() for record in _terminal_lines(caplog)]
    assert lines and 'stage=unknown worker_reason=unclassified' in lines[-1]


def test_deferred_persist_attempt_logs_the_ladder_not_the_terminal(caplog):
    store = MemoryStore()
    with caplog.at_level(logging.INFO):
        _drive_scheduler(store, worker_failure_evidence=PERSIST_EVIDENCE)
    assert not _terminal_lines(caplog)
    assert any('event=batch_retry reason=worker_failed outcome=deferred' in r.getMessage() for r in caplog.records)


def test_designed_handoff_families_never_claim_persist():
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')
        for diagnosis in (PERSIST_EVIDENCE, {'stage': 'persist', 'reason': 'empty_asr'}):
            assert empty_ladder_recovery_failure(diagnosis) is False
            assert language_guard_redrive_failure(diagnosis) is False
            assert validation_disposition_failure(diagnosis, disposition_enabled=False) is False


# --- Pump forward ---------------------------------------------------------------


def test_failed_work_persist_evidence_rides_the_publication_transition():
    store = MemoryStore()
    pump = make_pump(scheduler=Scheduler(store))
    now = time.time()
    pump.scheduler.enqueue(item(), now)
    lease_ = pump.scheduler.pull(now)[0]
    accepted = __import__('asyncio').run(
        pump._publish(lease_, {'a': FailedWork('a', worker_failure=PERSIST_EVIDENCE)}, set())
    )
    assert accepted is True
    assert store.rows['jobs', 'a']['worker_failure_evidence'] == PERSIST_EVIDENCE


def test_pump_forwards_the_persist_pair_byte_for_byte():
    pump = make_pump()
    seen = {}

    def fail(segment_id, token, now, **kwargs):
        seen.update(kwargs)
        return True

    pump.scheduler.fail = fail
    lease_ = lease()
    __import__('asyncio').run(
        pump._publish(
            lease_, {lease_.item.segment_id: FailedWork(lease_.item.segment_id, worker_failure=PERSIST_EVIDENCE)}, set()
        )
    )
    assert seen['worker_failure_evidence'] == PERSIST_EVIDENCE


# --- Worker boundary ------------------------------------------------------------


def test_settle_persist_fault_books_the_closed_evidence():
    worker, *_ = setup_worker(persist=Mock(side_effect=OSError('upload failed')))
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].worker_failure == PERSIST_EVIDENCE


def test_typed_persist_validation_books_the_typed_pair():
    from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason

    worker, *_ = setup_worker(persist=Mock(side_effect=BatchValidationError(ValidationReason.WORD_CLOCK)))
    results = worker.process_batch([item()])
    assert isinstance(results[0], FailedWork)
    assert results[0].worker_failure == {'stage': 'persist', 'reason': 'word_clock'}


def test_worker_fault_line_still_names_persist(caplog):
    worker, *_ = setup_worker(persist=Mock(side_effect=OSError('upload failed')))
    with caplog.at_level(logging.ERROR):
        worker.process_batch([item()])
    lines = [record.getMessage() for record in caplog.records if 'event=batch_worker_failed' in record.getMessage()]
    assert lines and 'stage=persist' in lines[0]


def test_persist_fault_takes_the_transient_arm_not_the_typed_terminal_arms():
    worker, *_ = setup_worker(persist=Mock(side_effect=OSError('upload failed')))
    results = worker.process_batch([item()])
    assert isinstance(results[0], FailedWork)
    assert not isinstance(results[0], WorkResult)


def test_successful_persist_books_no_evidence():
    worker, *_ = setup_worker()
    results = worker.process_batch([item()])
    assert isinstance(results[0], WorkResult)


def test_safety_net_off_persist_fault_books_no_handoff(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, *_ = setup_worker(persist=Mock(side_effect=OSError('upload failed')))
    results = worker.process_batch([item()])
    assert not [r for r in results if isinstance(r, FailedWork)]


# --- Doc and trailer parity -----------------------------------------------------


def test_the_reasons_module_carries_the_failure_class_trailer():
    source = (BACKEND_ROOT / 'utils' / 'observability' / 'reasons.py').read_text()
    assert f'Failure-Class: {FC}' in source


def test_the_enum_docstring_states_the_attribution_contract():
    source = (BACKEND_ROOT / 'utils' / 'observability' / 'reasons.py').read_text()
    marker = source.index('PERSIST = ')
    block = source[max(0, marker - 2400) : marker]
    assert 'stage=unknown worker_reason=unclassified' in block
    assert 'validate_worker_failure' in block


def test_the_doc_names_the_family_and_both_channels():
    doc = BACKEND_ROOT / 'docs' / 'batch-persist-stage-evidence.md'
    assert doc.exists()
    text = doc.read_text()
    assert FC in text
    assert 'stage=persist' in text and 'stage=unknown worker_reason=unclassified' in text


def test_errors_module_imports_the_shared_vocabulary():
    source = (BACKEND_ROOT / 'utils' / 'batch_pipeline' / 'errors.py').read_text()
    assert 'from utils.observability.reasons import WorkerValidationReason, WorkerValidationStage' in source


def test_the_salvage_grid_closed_set_tracks_the_vocabulary():
    from tests.unit.test_batch_worker_salvage_evidence_grid import CLOSED_STAGES

    assert sorted(CLOSED_STAGES) == sorted(WORKER_VALIDATION_STAGES)
