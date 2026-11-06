"""Worker failure evidence: the closed vocabulary and the FailedWork contract.

An ordinary retryable worker failure (FailedWork) used to drop its diagnosis at
the worker->pump->scheduler boundary, so the bounded retry ladder's terminal
quarantine recorded ``stage=unknown worker_reason=unclassified`` and operators
could not tell which stage burned the ladder. FailedWork now carries the
worker's closed-code evidence ({'stage', 'reason'}), validated by a dedicated
evidence gate: the stage vocabulary is the shared closed set, and the reason
may additionally be the enum's own ``unknown`` token because evidence never
decides a transition. This suite pins that vocabulary split and the
FailedWork contract that carries it.

Failure-Class: FC-batch-transient-worker-failure-quarantines-blind-without-stage-or-reason-evidence
"""

import dataclasses

import pytest

from utils.batch_pipeline.contracts import FailedWork, HeldWork, RecoveryWork, ValidationFailureWork
from utils.batch_pipeline.errors import (
    WORKER_VALIDATION_REASON_TOKENS,
    WORKER_VALIDATION_REASONS,
    WORKER_VALIDATION_STAGES,
    validate_worker_failure,
    validate_worker_failure_evidence,
)
from utils.observability.reasons import WorkerValidationReason, WorkerValidationStage

# --- Closed vocabulary split ----------------------------------------------------


def test_evidence_stage_vocabulary_is_the_shared_worker_stage_set():
    # reason_values drops the unknown token from both enums: evidence stages
    # are the five real work stages, never the unknown placeholder.
    assert WORKER_VALIDATION_STAGES == frozenset(
        stage.value for stage in WorkerValidationStage if stage.value != 'unknown'
    )
    assert 'unknown' not in WORKER_VALIDATION_STAGES


def test_evidence_reason_tokens_are_the_full_worker_reason_enum():
    assert WORKER_VALIDATION_REASON_TOKENS == frozenset(reason.value for reason in WorkerValidationReason)


def test_terminal_reason_gate_still_excludes_the_unknown_token():
    assert 'unknown' not in WORKER_VALIDATION_REASONS


def test_evidence_reason_gate_is_a_strict_superset_of_the_terminal_gate():
    assert WORKER_VALIDATION_REASONS < WORKER_VALIDATION_REASON_TOKENS
    assert WORKER_VALIDATION_REASON_TOKENS - WORKER_VALIDATION_REASONS == {'unknown'}


def test_evidence_gate_and_terminal_gate_share_one_stage_vocabulary():
    # Both gates accept exactly the same closed stage set; only the reason
    # vocabulary differs, and only by the evidence-only unknown token.
    good = {'reason': 'word_clock'}
    assert validate_worker_failure({'stage': 'fetch_decode', **good}) is None
    assert validate_worker_failure_evidence({'stage': 'fetch_decode', **good}) is None


def test_unknown_is_the_only_evidence_only_reason_token():
    assert validate_worker_failure_evidence({'stage': 'fetch_decode', 'reason': 'unknown'}) is None
    with pytest.raises(ValueError, match='closed worker validation failure required'):
        validate_worker_failure({'stage': 'fetch_decode', 'reason': 'unknown'})


def test_evidence_gate_never_accepts_an_open_reason():
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        validate_worker_failure_evidence({'stage': 'fetch_decode', 'reason': 'unclassified'})


def test_evidence_gate_never_accepts_an_open_stage():
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        validate_worker_failure_evidence({'stage': 'asr', 'reason': 'word_clock'})


def test_evidence_gate_rejects_a_non_dict_payload():
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        validate_worker_failure_evidence('fetch_decode/word_clock')


def test_evidence_gate_rejects_a_truncated_pair():
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        validate_worker_failure_evidence({'stage': 'fetch_decode'})


def test_evidence_gate_rejects_extra_keys():
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        validate_worker_failure_evidence({'stage': 'fetch_decode', 'reason': 'word_clock', 'detail': 'x'})


def test_terminal_gate_rejects_a_truncated_pair():
    with pytest.raises(ValueError, match='closed worker validation failure required'):
        validate_worker_failure({'reason': 'word_clock'})


def test_terminal_gate_rejects_extra_keys():
    with pytest.raises(ValueError, match='closed worker validation failure required'):
        validate_worker_failure({'stage': 'fetch_decode', 'reason': 'word_clock', 'site': 'a.py:1'})


# Every closed stage may carry every closed evidence reason, including unknown.
def test_failed_work_accepts_evidence_fetch_decode_staged_audio_invalid():
    evidence = {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_fetch_decode_retained_audio_invalid():
    evidence = {'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_fetch_decode_decoded_duration_mismatch():
    evidence = {'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_fetch_decode_word_shape():
    evidence = {'stage': 'fetch_decode', 'reason': 'word_shape'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_fetch_decode_word_clock():
    evidence = {'stage': 'fetch_decode', 'reason': 'word_clock'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_fetch_decode_word_sequence():
    evidence = {'stage': 'fetch_decode', 'reason': 'word_sequence'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_fetch_decode_vad_nonfinite():
    evidence = {'stage': 'fetch_decode', 'reason': 'vad_nonfinite'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_fetch_decode_vad_order():
    evidence = {'stage': 'fetch_decode', 'reason': 'vad_order'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_fetch_decode_vad_bounds():
    evidence = {'stage': 'fetch_decode', 'reason': 'vad_bounds'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_fetch_decode_empty_asr():
    evidence = {'stage': 'fetch_decode', 'reason': 'empty_asr'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_fetch_decode_no_owned_words():
    evidence = {'stage': 'fetch_decode', 'reason': 'no_owned_words'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_fetch_decode_unsupported_language():
    evidence = {'stage': 'fetch_decode', 'reason': 'unsupported_language'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_fetch_decode_unknown():
    evidence = {'stage': 'fetch_decode', 'reason': 'unknown'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


# Every closed stage may carry every closed evidence reason, including unknown.
def test_failed_work_accepts_evidence_vad_windows_staged_audio_invalid():
    evidence = {'stage': 'vad_windows', 'reason': 'staged_audio_invalid'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_vad_windows_retained_audio_invalid():
    evidence = {'stage': 'vad_windows', 'reason': 'retained_audio_invalid'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_vad_windows_decoded_duration_mismatch():
    evidence = {'stage': 'vad_windows', 'reason': 'decoded_duration_mismatch'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_vad_windows_word_shape():
    evidence = {'stage': 'vad_windows', 'reason': 'word_shape'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_vad_windows_word_clock():
    evidence = {'stage': 'vad_windows', 'reason': 'word_clock'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_vad_windows_word_sequence():
    evidence = {'stage': 'vad_windows', 'reason': 'word_sequence'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_vad_windows_vad_nonfinite():
    evidence = {'stage': 'vad_windows', 'reason': 'vad_nonfinite'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_vad_windows_vad_order():
    evidence = {'stage': 'vad_windows', 'reason': 'vad_order'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_vad_windows_vad_bounds():
    evidence = {'stage': 'vad_windows', 'reason': 'vad_bounds'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_vad_windows_empty_asr():
    evidence = {'stage': 'vad_windows', 'reason': 'empty_asr'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_vad_windows_no_owned_words():
    evidence = {'stage': 'vad_windows', 'reason': 'no_owned_words'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_vad_windows_unsupported_language():
    evidence = {'stage': 'vad_windows', 'reason': 'unsupported_language'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_vad_windows_unknown():
    evidence = {'stage': 'vad_windows', 'reason': 'unknown'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


# Every closed stage may carry every closed evidence reason, including unknown.
def test_failed_work_accepts_evidence_word_clocks_staged_audio_invalid():
    evidence = {'stage': 'word_clocks', 'reason': 'staged_audio_invalid'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_word_clocks_retained_audio_invalid():
    evidence = {'stage': 'word_clocks', 'reason': 'retained_audio_invalid'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_word_clocks_decoded_duration_mismatch():
    evidence = {'stage': 'word_clocks', 'reason': 'decoded_duration_mismatch'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_word_clocks_word_shape():
    evidence = {'stage': 'word_clocks', 'reason': 'word_shape'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_word_clocks_word_clock():
    evidence = {'stage': 'word_clocks', 'reason': 'word_clock'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_word_clocks_word_sequence():
    evidence = {'stage': 'word_clocks', 'reason': 'word_sequence'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_word_clocks_vad_nonfinite():
    evidence = {'stage': 'word_clocks', 'reason': 'vad_nonfinite'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_word_clocks_vad_order():
    evidence = {'stage': 'word_clocks', 'reason': 'vad_order'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_word_clocks_vad_bounds():
    evidence = {'stage': 'word_clocks', 'reason': 'vad_bounds'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_word_clocks_empty_asr():
    evidence = {'stage': 'word_clocks', 'reason': 'empty_asr'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_word_clocks_no_owned_words():
    evidence = {'stage': 'word_clocks', 'reason': 'no_owned_words'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_word_clocks_unsupported_language():
    evidence = {'stage': 'word_clocks', 'reason': 'unsupported_language'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_word_clocks_unknown():
    evidence = {'stage': 'word_clocks', 'reason': 'unknown'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


# Every closed stage may carry every closed evidence reason, including unknown.
def test_failed_work_accepts_evidence_assemble_words_staged_audio_invalid():
    evidence = {'stage': 'assemble_words', 'reason': 'staged_audio_invalid'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_assemble_words_retained_audio_invalid():
    evidence = {'stage': 'assemble_words', 'reason': 'retained_audio_invalid'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_assemble_words_decoded_duration_mismatch():
    evidence = {'stage': 'assemble_words', 'reason': 'decoded_duration_mismatch'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_assemble_words_word_shape():
    evidence = {'stage': 'assemble_words', 'reason': 'word_shape'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_assemble_words_word_clock():
    evidence = {'stage': 'assemble_words', 'reason': 'word_clock'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_assemble_words_word_sequence():
    evidence = {'stage': 'assemble_words', 'reason': 'word_sequence'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_assemble_words_vad_nonfinite():
    evidence = {'stage': 'assemble_words', 'reason': 'vad_nonfinite'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_assemble_words_vad_order():
    evidence = {'stage': 'assemble_words', 'reason': 'vad_order'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_assemble_words_vad_bounds():
    evidence = {'stage': 'assemble_words', 'reason': 'vad_bounds'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_assemble_words_empty_asr():
    evidence = {'stage': 'assemble_words', 'reason': 'empty_asr'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_assemble_words_no_owned_words():
    evidence = {'stage': 'assemble_words', 'reason': 'no_owned_words'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_assemble_words_unsupported_language():
    evidence = {'stage': 'assemble_words', 'reason': 'unsupported_language'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_assemble_words_unknown():
    evidence = {'stage': 'assemble_words', 'reason': 'unknown'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


# Every closed stage may carry every closed evidence reason, including unknown.
def test_failed_work_accepts_evidence_asr_recovery_staged_audio_invalid():
    evidence = {'stage': 'asr_recovery', 'reason': 'staged_audio_invalid'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_asr_recovery_retained_audio_invalid():
    evidence = {'stage': 'asr_recovery', 'reason': 'retained_audio_invalid'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_asr_recovery_decoded_duration_mismatch():
    evidence = {'stage': 'asr_recovery', 'reason': 'decoded_duration_mismatch'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_asr_recovery_word_shape():
    evidence = {'stage': 'asr_recovery', 'reason': 'word_shape'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_asr_recovery_word_clock():
    evidence = {'stage': 'asr_recovery', 'reason': 'word_clock'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_asr_recovery_word_sequence():
    evidence = {'stage': 'asr_recovery', 'reason': 'word_sequence'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_asr_recovery_vad_nonfinite():
    evidence = {'stage': 'asr_recovery', 'reason': 'vad_nonfinite'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_asr_recovery_vad_order():
    evidence = {'stage': 'asr_recovery', 'reason': 'vad_order'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_asr_recovery_vad_bounds():
    evidence = {'stage': 'asr_recovery', 'reason': 'vad_bounds'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_asr_recovery_empty_asr():
    evidence = {'stage': 'asr_recovery', 'reason': 'empty_asr'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_asr_recovery_no_owned_words():
    evidence = {'stage': 'asr_recovery', 'reason': 'no_owned_words'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_asr_recovery_unsupported_language():
    evidence = {'stage': 'asr_recovery', 'reason': 'unsupported_language'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


def test_failed_work_accepts_evidence_asr_recovery_unknown():
    evidence = {'stage': 'asr_recovery', 'reason': 'unknown'}
    assert FailedWork('a', None, None, worker_failure=evidence).worker_failure == evidence


# --- FailedWork shape and backwards compatibility -------------------------------


def test_failed_work_defaults_to_no_evidence():
    assert FailedWork('a').worker_failure is None
    assert FailedWork('a', 1.5).worker_failure is None
    assert FailedWork('a', 1.5, {'vad': 'receipt'}).worker_failure is None


def test_failed_work_keeps_positional_construction_with_evidence():
    work = FailedWork('a', 2.0, {'vad': 'receipt'}, {'stage': 'vad_windows', 'reason': 'unknown'})
    assert work.segment_id == 'a'
    assert work.measured_held_vad_speech_seconds == 2.0
    assert work.worker_vad_receipt == {'vad': 'receipt'}
    assert work.worker_failure == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_failed_work_without_evidence_still_validates_measured_vad():
    assert FailedWork('a', 0.0, None).measured_held_vad_speech_seconds == 0.0
    with pytest.raises(ValueError):
        FailedWork('a', -1.0, None)


def test_failed_work_with_evidence_still_validates_measured_vad():
    with pytest.raises(ValueError):
        FailedWork('a', -1.0, None, {'stage': 'fetch_decode', 'reason': 'unknown'})


def test_failed_work_is_frozen():
    work = FailedWork('a', None, None, {'stage': 'fetch_decode', 'reason': 'unknown'})
    with pytest.raises(dataclasses.FrozenInstanceError):
        work.worker_failure = None


def test_failed_work_evidence_participates_in_equality():
    evidence = {'stage': 'fetch_decode', 'reason': 'unknown'}
    assert FailedWork('a', None, None, evidence) == FailedWork('a', None, None, evidence)
    assert FailedWork('a', None, None, evidence) != FailedWork('a', None, None, None)
    assert FailedWork('a', None, None, evidence) != FailedWork(
        'a', None, None, {'stage': 'asr_recovery', 'reason': 'unknown'}
    )


def test_failed_work_holds_the_evidence_by_reference():
    # Same aliasing contract as the sibling VAD receipt field: the producer
    # builds an immutable-by-convention dict and never mutates it afterwards.
    evidence = {'stage': 'fetch_decode', 'reason': 'unknown'}
    assert FailedWork('a', None, None, evidence).worker_failure is evidence


def test_failed_work_evidence_with_unknown_reason_is_the_generic_exception_contract():
    work = FailedWork('a', None, None, {'stage': 'fetch_decode', 'reason': 'unknown'})
    assert work.worker_failure['reason'] == WorkerValidationReason.UNKNOWN.value


def test_failed_work_evidence_with_closed_reason_passes_the_terminal_gate_too():
    # A closed reason is valid for both gates; FailedWork accepts a subset of
    # what the scheduler's terminal path accepts.
    evidence = {'stage': 'word_clocks', 'reason': 'word_clock'}
    validate_worker_failure_evidence(evidence)
    validate_worker_failure(evidence)
    assert FailedWork('a', None, None, evidence).worker_failure == evidence


# --- Sibling work types stay on the terminal gate -------------------------------


def test_validation_failure_work_still_rejects_the_unknown_reason():
    with pytest.raises(ValueError):
        ValidationFailureWork('a', 'fetch_decode', 'unknown')


def test_validation_failure_work_still_rejects_an_open_stage():
    with pytest.raises(ValueError):
        ValidationFailureWork('a', 'asr', 'word_clock')


def test_validation_failure_work_still_accepts_the_closed_matrix():
    work = ValidationFailureWork('a', 'assemble_words', 'no_owned_words')
    assert (work.stage, work.reason) == ('assemble_words', 'no_owned_words')


def test_recovery_work_contract_is_untouched():
    work = RecoveryWork('a')
    assert work.reason == 'empty_asr' and work.padded_retry is None


def test_recovery_work_still_rejects_an_open_reason():
    with pytest.raises(ValueError):
        RecoveryWork('a', reason='word_clock')


def test_held_work_reason_stays_a_free_form_hold_label():
    work = HeldWork('a', 60, 'capacity')
    assert work.reason == 'capacity'


# --- Scheduler-side evidence validation guard -----------------------------------


def _queue():
    from tests.unit.test_batch_pipeline_scheduler import MemoryStore
    from utils.batch_pipeline.scheduler import Scheduler

    return Scheduler(MemoryStore())


def test_scheduler_fail_validates_evidence_before_any_transaction():
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        _queue().fail('missing', 'token', 0.0, worker_failure_evidence={'stage': 'asr', 'reason': 'word_clock'})


def test_scheduler_fail_validates_evidence_stage_before_any_transaction():
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        _queue().fail('missing', 'token', 0.0, worker_failure_evidence={'stage': 'persist', 'reason': 'unknown'})


def test_scheduler_fail_validates_evidence_reason_before_any_transaction():
    with pytest.raises(ValueError, match='closed worker failure evidence required'):
        _queue().fail(
            'missing', 'token', 0.0, worker_failure_evidence={'stage': 'fetch_decode', 'reason': 'unclassified'}
        )


def test_scheduler_fail_still_validates_the_typed_worker_failure():
    with pytest.raises(ValueError, match='closed worker validation failure required'):
        _queue().fail('missing', 'token', 0.0, worker_failure={'stage': 'fetch_decode', 'reason': 'unknown'})


def test_scheduler_fail_accepts_evidence_with_the_unknown_reason_at_the_gate():
    # The gate raises only for closed-set violations; an unknown-reason
    # evidence reaches the transaction (where lease ownership decides).
    assert (
        _queue().fail('missing', 'token', 0.0, worker_failure_evidence={'stage': 'fetch_decode', 'reason': 'unknown'})
        is False
    )


def test_scheduler_fail_accepts_typed_worker_failure_at_the_gate():
    assert (
        _queue().fail('missing', 'token', 0.0, worker_failure={'stage': 'fetch_decode', 'reason': 'word_clock'})
        is False
    )


# --- Every closed reason validates on both gates -------------------------------------


def test_closed_reason_word_shape_validates_on_both_gates():
    evidence = {'stage': 'fetch_decode', 'reason': 'word_shape'}
    validate_worker_failure_evidence(evidence)
    validate_worker_failure(evidence)


def test_closed_reason_word_clock_validates_on_both_gates():
    evidence = {'stage': 'fetch_decode', 'reason': 'word_clock'}
    validate_worker_failure_evidence(evidence)
    validate_worker_failure(evidence)


def test_closed_reason_word_sequence_validates_on_both_gates():
    evidence = {'stage': 'fetch_decode', 'reason': 'word_sequence'}
    validate_worker_failure_evidence(evidence)
    validate_worker_failure(evidence)


def test_closed_reason_vad_nonfinite_validates_on_both_gates():
    evidence = {'stage': 'vad_windows', 'reason': 'vad_nonfinite'}
    validate_worker_failure_evidence(evidence)
    validate_worker_failure(evidence)


def test_closed_reason_vad_order_validates_on_both_gates():
    evidence = {'stage': 'vad_windows', 'reason': 'vad_order'}
    validate_worker_failure_evidence(evidence)
    validate_worker_failure(evidence)


def test_closed_reason_vad_bounds_validates_on_both_gates():
    evidence = {'stage': 'vad_windows', 'reason': 'vad_bounds'}
    validate_worker_failure_evidence(evidence)
    validate_worker_failure(evidence)


def test_closed_reason_staged_audio_invalid_validates_on_both_gates():
    evidence = {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}
    validate_worker_failure_evidence(evidence)
    validate_worker_failure(evidence)


def test_closed_reason_retained_audio_invalid_validates_on_both_gates():
    evidence = {'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}
    validate_worker_failure_evidence(evidence)
    validate_worker_failure(evidence)


def test_closed_reason_decoded_duration_mismatch_validates_on_both_gates():
    evidence = {'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}
    validate_worker_failure_evidence(evidence)
    validate_worker_failure(evidence)


def test_closed_reason_empty_asr_validates_on_both_gates():
    evidence = {'stage': 'assemble_words', 'reason': 'empty_asr'}
    validate_worker_failure_evidence(evidence)
    validate_worker_failure(evidence)


def test_closed_reason_no_owned_words_validates_on_both_gates():
    evidence = {'stage': 'assemble_words', 'reason': 'no_owned_words'}
    validate_worker_failure_evidence(evidence)
    validate_worker_failure(evidence)


def test_closed_reason_unsupported_language_validates_on_both_gates():
    evidence = {'stage': 'vad_windows', 'reason': 'unsupported_language'}
    validate_worker_failure_evidence(evidence)
    validate_worker_failure(evidence)
