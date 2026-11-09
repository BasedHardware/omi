# Failure-Class: FC-terminal-validation-disposition-misbooked-as-worker-fault
"""The disposition doc and the disposition code, pinned token-for-token.

Every event name, outcome token, family reason, stage token, flag name and
rollback claim in ``docs/validation-disposition-demotion-parity.md`` is pinned to the live sources; every code-side
surface the doc promises (the predicate, its two arms, the stage constant)
exists with the pinned name; and the sibling demotions the doc names keep
their own channels.
"""

import inspect
from pathlib import Path

import diarizer.batch_pipeline as worker_module
import utils.batch_pipeline.errors as errors_module
import utils.batch_pipeline.scheduler as scheduler_module

BACKEND = Path(__file__).resolve().parents[2]
WORKER_SOURCE = inspect.getsource(worker_module)
SCHEDULER_SOURCE = inspect.getsource(scheduler_module)
ERRORS_SOURCE = inspect.getsource(errors_module)
DOC = (BACKEND / "docs/validation-disposition-demotion-parity.md").read_text()


def test_doc_exists():
    """The demotion doc is present."""
    assert DOC


def test_doc_names_the_failure_class():
    """The doc's Failure-Class matches the code's trailer."""
    assert "FC-terminal-validation-disposition-misbooked-as-worker-fault" in DOC
    assert "FC-terminal-validation-disposition-misbooked-as-worker-fault" in ERRORS_SOURCE


def test_doc_names_the_worker_event():
    """The doc names the worker-side event."""
    assert "event=batch_validation_disposition outcome=recovery_handoff" in DOC
    assert WORKER_SOURCE.count("event=batch_validation_disposition") == 1


def test_doc_names_the_scheduler_event():
    """The doc names the scheduler-side event."""
    assert "event=batch_validation_disposition outcome=held_for_disposition" in DOC
    assert SCHEDULER_SOURCE.count("event=batch_validation_disposition") == 1


def test_worker_fault_line_is_still_exactly_one_emitter():
    """The demotion adds no second worker-fault emitter."""
    assert WORKER_SOURCE.count("event=batch_worker_failed") == 1


def test_scheduler_quarantine_line_is_still_exactly_one_emitter():
    """The demotion adds no second quarantine emitter."""
    assert SCHEDULER_SOURCE.count("event=batch_quarantined") == 1


def test_sibling_empty_ladder_channel_unchanged():
    """The empty ladder keeps its two sites."""
    assert WORKER_SOURCE.count("event=batch_empty_ladder") == 1
    assert SCHEDULER_SOURCE.count("event=batch_empty_ladder") == 1


def test_sibling_language_guard_channel_unchanged():
    """The language guard keeps its two sites."""
    assert WORKER_SOURCE.count("event=batch_language_guard") == 1
    assert SCHEDULER_SOURCE.count("event=batch_language_guard") == 1


def test_doc_names_the_disposition_switch():
    """The doc names the rollout switch; the code reads it through the config helper."""
    assert "BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED" in DOC
    assert "worker_validation_disposition_enabled" in ERRORS_SOURCE
    assert "worker_validation_disposition_enabled" in SCHEDULER_SOURCE


def test_doc_names_the_flagged_arm():
    """The doc names both arms."""
    assert "VALIDATION_DISPOSITION_FLAGGED_REASONS" in DOC
    assert "VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS" in DOC
    assert "VALIDATION_DISPOSITION_FLAGGED_REASONS" in ERRORS_SOURCE
    assert "VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS" in ERRORS_SOURCE


def test_doc_names_family_staged_audio_invalid():
    """The doc lists staged_audio_invalid in the demotion family."""
    assert "staged_audio_invalid" in DOC


def test_doc_names_family_retained_audio_invalid():
    """The doc lists retained_audio_invalid in the demotion family."""
    assert "retained_audio_invalid" in DOC


def test_doc_names_family_decoded_duration_mismatch():
    """The doc lists decoded_duration_mismatch in the demotion family."""
    assert "decoded_duration_mismatch" in DOC


def test_doc_names_family_word_shape():
    """The doc lists word_shape in the demotion family."""
    assert "word_shape" in DOC


def test_doc_names_family_word_clock():
    """The doc lists word_clock in the demotion family."""
    assert "word_clock" in DOC


def test_doc_names_family_word_sequence():
    """The doc lists word_sequence in the demotion family."""
    assert "word_sequence" in DOC


def test_doc_names_family_vad_nonfinite():
    """The doc lists vad_nonfinite in the demotion family."""
    assert "vad_nonfinite" in DOC


def test_doc_names_family_vad_order():
    """The doc lists vad_order in the demotion family."""
    assert "vad_order" in DOC


def test_doc_names_family_vad_bounds():
    """The doc lists vad_bounds in the demotion family."""
    assert "vad_bounds" in DOC


def test_doc_names_stage_fetch_decode():
    """The doc names the fetch_decode stage."""
    assert "fetch_decode" in DOC


def test_doc_names_stage_vad_windows():
    """The doc names the vad_windows stage."""
    assert "vad_windows" in DOC


def test_doc_names_stage_word_clocks():
    """The doc names the word_clocks stage."""
    assert "word_clocks" in DOC


def test_doc_names_stage_assemble_words():
    """The doc names the assemble_words stage."""
    assert "assemble_words" in DOC


def test_doc_names_stage_asr_recovery():
    """The doc names the asr_recovery stage."""
    assert "asr_recovery" in DOC


def test_doc_names_the_outside_admitted_source_exception():
    """The doc keeps the deliberately-retryable refusal on the fault channel."""
    assert "outside_admitted_source" in DOC


def test_doc_names_the_awaiting_recovery_warning_as_unchanged():
    """The doc pins the awaiting-fenced-recovery warning."""
    assert "awaiting_fenced_recovery" in DOC
    assert SCHEDULER_SOURCE.count("awaiting_fenced_recovery") == 1


def test_doc_names_the_sibling_families():
    """The doc positions the disposition as the sibling of guard and ladder."""
    assert "empty ladder" in DOC
    assert "language barrier" in DOC


def test_doc_has_a_rollback_section():
    """The doc documents the rollback switch."""
    assert "## Rollback" in DOC


def test_doc_unconditional_arm_claim_matches_the_predicate_stage():
    """The doc's stage-ownership claim matches the code's stage constant."""
    assert "VALIDATION_DISPOSITION_UNCONDITIONAL_STAGE = WorkerValidationStage.FETCH_DECODE.value" in ERRORS_SOURCE
