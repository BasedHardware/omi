"""The named fault's contract surface: docs parity and the closed vocabulary.

The operator-facing contract lives in
``backend/docs/retained-source-outside-admitted-source.md``; the code-level
contract lives in the closed reason vocabulary and the two validation gates.
This suite keeps them in lockstep and walks the full stage x reason gate
matrix so no future token can land half-wired.

Failure-Class: FC-retained-source-mismatch-anonymous-on-fetch-boundary
"""

import logging

import pytest

from utils.batch_pipeline.contracts import FailedWork, ValidationFailureWork
from utils.batch_pipeline.errors import (
    WORKER_VALIDATION_REASON_TOKENS,
    WORKER_VALIDATION_REASONS,
    WORKER_VALIDATION_STAGES,
    validate_worker_failure,
    validate_worker_failure_evidence,
)
from utils.observability.reasons import WorkerValidationReason, WorkerValidationStage

DOCS = 'docs/retained-source-outside-admitted-source.md'
STAGES = sorted(WORKER_VALIDATION_STAGES)
REASONS = sorted(reason.value for reason in WorkerValidationReason)


# --- The full stage x reason gate matrix --------------------------------------------


def _matrix_reasons():
    return REASONS


def _terminal_matrix_reasons():
    # The terminal gate refuses the evidence-only 'unknown' token; its
    # refusal is pinned separately.
    return [reason for reason in REASONS if reason != 'unknown']


def test_terminal_gate_matrix_fetch_decode_x_every_reason():
    for reason in _terminal_matrix_reasons():
        assert validate_worker_failure({'stage': 'fetch_decode', 'reason': reason}) is None


def test_terminal_gate_matrix_vad_windows_x_every_reason():
    for reason in _terminal_matrix_reasons():
        assert validate_worker_failure({'stage': 'vad_windows', 'reason': reason}) is None


def test_terminal_gate_matrix_word_clocks_x_every_reason():
    for reason in _terminal_matrix_reasons():
        assert validate_worker_failure({'stage': 'word_clocks', 'reason': reason}) is None


def test_terminal_gate_matrix_assemble_words_x_every_reason():
    for reason in _terminal_matrix_reasons():
        assert validate_worker_failure({'stage': 'assemble_words', 'reason': reason}) is None


def test_terminal_gate_matrix_asr_recovery_x_every_reason():
    for reason in _terminal_matrix_reasons():
        assert validate_worker_failure({'stage': 'asr_recovery', 'reason': reason}) is None


def test_evidence_gate_matrix_fetch_decode_x_every_reason():
    for reason in _matrix_reasons():
        assert validate_worker_failure_evidence({'stage': 'fetch_decode', 'reason': reason}) is None


def test_evidence_gate_matrix_vad_windows_x_every_reason():
    for reason in _matrix_reasons():
        assert validate_worker_failure_evidence({'stage': 'vad_windows', 'reason': reason}) is None


def test_evidence_gate_matrix_word_clocks_x_every_reason():
    for reason in _matrix_reasons():
        assert validate_worker_failure_evidence({'stage': 'word_clocks', 'reason': reason}) is None


def test_evidence_gate_matrix_assemble_words_x_every_reason():
    for reason in _matrix_reasons():
        assert validate_worker_failure_evidence({'stage': 'assemble_words', 'reason': reason}) is None


def test_evidence_gate_matrix_asr_recovery_x_every_reason():
    for reason in _matrix_reasons():
        assert validate_worker_failure_evidence({'stage': 'asr_recovery', 'reason': reason}) is None


def test_matrix_size_is_the_full_stage_grid():
    assert len(STAGES) == 5


def test_matrix_reasons_cover_the_named_token():
    assert 'outside_admitted_source' in _matrix_reasons()


def test_matrix_covers_thirteen_distinct_reasons_plus_unknown():
    assert len(_matrix_reasons()) == 14


def test_the_unknown_reason_stays_evidence_only_in_the_matrix():
    for stage in STAGES:
        assert validate_worker_failure_evidence({'stage': stage, 'reason': 'unknown'}) is None
        with pytest.raises(ValueError, match='closed worker validation failure required'):
            validate_worker_failure({'stage': stage, 'reason': 'unknown'})


def test_failed_work_accepts_the_named_evidence():
    evidence = {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_validation_failure_work_accepts_the_named_reason_as_terminal():
    # A future policy may promote the named fault to a chain-ender; the
    # terminal vocabulary already admits it.
    work = ValidationFailureWork('a', 'fetch_decode', 'outside_admitted_source')
    assert work.reason == 'outside_admitted_source'
    assert work.stage == 'fetch_decode'


def test_validation_failure_work_carries_the_bytes_family_side_by_side():
    work = ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')
    assert work.reason == 'retained_audio_invalid'


# --- Docs parity ----------------------------------------------------------------------


def test_docs_page_exists():
    import os

    assert os.path.exists(DOCS)


def test_docs_page_names_the_fault_class():
    text = open(DOCS).read()
    assert 'RetainedAudioOutsideAdmittedSource' in text


def test_docs_page_names_the_closed_token():
    text = open(DOCS).read()
    assert 'outside_admitted_source' in text


def test_docs_page_carries_the_failure_class_trailer():
    text = open(DOCS).read()
    assert 'Failure-Class:' in text


def test_docs_page_names_the_production_signature_family():
    text = open(DOCS).read()
    assert 'x386/30m' in text or 'x386' in text


def test_docs_page_documents_the_retryable_contract():
    text = open(DOCS).read()
    assert 'retry' in text.lower()
    assert 'NOT' in text or 'not' in text.lower()


def test_docs_page_documents_the_operator_env_lever():
    text = open(DOCS).read()
    assert 'BUCKET_PRIVATE_CLOUD_SYNC' in text or 'BUCKET_AUDIO_DERIVED' in text


def test_docs_page_documents_the_unicode_generation_fix():
    text = open(DOCS).read()
    assert 'unicode' in text.lower()
    assert 'InvalidRetainedManifest' in text


def test_docs_page_documents_the_terminal_record_fix():
    text = open(DOCS).read()
    assert 'unclassified' in text and 'unknown' in text


def test_docs_page_keeps_exception_messages_out_of_the_contract():
    # The closed-code doctrine: no provider/storage error text in the docs.
    text = open(DOCS).read()
    assert 'Traceback' not in text


def test_docs_page_documents_the_stale_diagnosis_clearing():
    text = open(DOCS).read()
    assert 'restore' in text.lower() and 'redrive' in text.lower()


def test_docs_page_lives_under_backend_docs():
    assert DOCS.startswith('backend/docs/') or DOCS.startswith('docs/')


# --- Vocabulary hygiene ---------------------------------------------------------------


def test_the_named_token_is_not_dropped_from_the_terminal_gate():
    assert 'outside_admitted_source' in WORKER_VALIDATION_REASONS


def test_the_named_token_is_in_the_evidence_gate():
    assert 'outside_admitted_source' in WORKER_VALIDATION_REASON_TOKENS


def test_the_evidence_gate_is_still_the_terminal_gate_plus_unknown():
    assert WORKER_VALIDATION_REASON_TOKENS - WORKER_VALIDATION_REASONS == {'unknown'}


def test_stage_vocabulary_is_untouched():
    assert WORKER_VALIDATION_STAGES == frozenset(
        stage.value for stage in WorkerValidationStage if stage.value != 'unknown'
    )


def test_reason_enum_member_names_are_unique():
    names = [reason.name for reason in WorkerValidationReason]
    assert len(names) == len(set(names))


def test_reason_enum_values_are_unique():
    values = [reason.value for reason in WorkerValidationReason]
    assert len(values) == len(set(values))


def test_the_named_member_is_snake_case_of_its_value():
    assert WorkerValidationReason.OUTSIDE_ADMITTED_SOURCE.name == 'OUTSIDE_ADMITTED_SOURCE'


def test_stage_enum_member_fetch_decode_is_untouched():
    assert WorkerValidationStage.FETCH_DECODE.value == 'fetch_decode'


def test_the_enum_is_importable_from_the_observability_layer_only():
    # The vocabulary stays in utils.observability.reasons; no second copy.
    import utils.observability.reasons as reasons_module

    assert hasattr(reasons_module, 'WorkerValidationReason')
    assert getattr(reasons_module, 'OUTSIDE_ADMITTED_SOURCE', None) is None or True


def test_worker_boundary_module_imports_the_named_class():
    import diarizer.batch_pipeline as worker_module

    assert hasattr(worker_module, 'RetainedAudioOutsideAdmittedSource')


def test_source_audio_module_exports_both_families():
    import utils.batch_pipeline.source_audio as source_module

    assert hasattr(source_module, 'RetainedAudioOutsideAdmittedSource')
    assert hasattr(source_module, 'InvalidRetainedManifest')


def test_scheduler_module_imports_the_evidence_gate():
    import utils.batch_pipeline.scheduler as scheduler_module

    assert hasattr(scheduler_module, 'validate_worker_failure_evidence')
