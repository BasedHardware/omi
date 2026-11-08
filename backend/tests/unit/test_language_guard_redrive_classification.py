"""The language-guard redrive predicate is the only demotion key.

A terminal diagnosis demotes to the language-guard transition exactly when it is a closed worker-failure shape whose reason is unsupported_language. Every other closed reason, every anonymous shape, and every malformed input keeps its fault classification. This suite pins the predicate cell by cell over the full closed stage and reason vocabulary.

Failure-Class: FC-language-guard-redrive-misclassified-as-worker-fault
"""

import pytest

from types import SimpleNamespace

from config.prerecorded_language import language_class
from utils.batch_pipeline.errors import (
    LANGUAGE_GUARD_REDRIVE_REASONS,
    WORKER_VALIDATION_REASONS,
    WORKER_VALIDATION_STAGES,
    language_guard_redrive_failure,
    validate_worker_failure,
    validate_worker_failure_evidence,
)
from utils.batch_pipeline.word_validation import ValidationReason
from utils.observability.reasons import WorkerValidationReason, WorkerValidationStage


def test_guard_reason_at_fetch_decode_demotes():
    """fetch_decode carrying the guard reason is the redrive transition."""
    assert language_guard_redrive_failure({"stage": "fetch_decode", "reason": "unsupported_language"}) is True


def test_guard_reason_at_vad_windows_demotes():
    """vad_windows carrying the guard reason is the redrive transition."""
    assert language_guard_redrive_failure({"stage": "vad_windows", "reason": "unsupported_language"}) is True


def test_guard_reason_at_word_clocks_demotes():
    """word_clocks carrying the guard reason is the redrive transition."""
    assert language_guard_redrive_failure({"stage": "word_clocks", "reason": "unsupported_language"}) is True


def test_guard_reason_at_assemble_words_demotes():
    """assemble_words carrying the guard reason is the redrive transition."""
    assert language_guard_redrive_failure({"stage": "assemble_words", "reason": "unsupported_language"}) is True


def test_guard_reason_at_asr_recovery_demotes():
    """asr_recovery carrying the guard reason is the redrive transition."""
    assert language_guard_redrive_failure({"stage": "asr_recovery", "reason": "unsupported_language"}) is True


def test_reason_staged_audio_invalid_at_fetch_decode_stays_a_fault():
    """staged_audio_invalid at fetch_decode is not the guard: it stays on the fault channels."""
    shape = {"stage": "fetch_decode", "reason": "staged_audio_invalid"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_retained_audio_invalid_at_fetch_decode_stays_a_fault():
    """retained_audio_invalid at fetch_decode is not the guard: it stays on the fault channels."""
    shape = {"stage": "fetch_decode", "reason": "retained_audio_invalid"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_decoded_duration_mismatch_at_fetch_decode_stays_a_fault():
    """decoded_duration_mismatch at fetch_decode is not the guard: it stays on the fault channels."""
    shape = {"stage": "fetch_decode", "reason": "decoded_duration_mismatch"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_word_shape_at_fetch_decode_stays_a_fault():
    """word_shape at fetch_decode is not the guard: it stays on the fault channels."""
    shape = {"stage": "fetch_decode", "reason": "word_shape"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_word_clock_at_fetch_decode_stays_a_fault():
    """word_clock at fetch_decode is not the guard: it stays on the fault channels."""
    shape = {"stage": "fetch_decode", "reason": "word_clock"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_word_sequence_at_fetch_decode_stays_a_fault():
    """word_sequence at fetch_decode is not the guard: it stays on the fault channels."""
    shape = {"stage": "fetch_decode", "reason": "word_sequence"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_vad_nonfinite_at_fetch_decode_stays_a_fault():
    """vad_nonfinite at fetch_decode is not the guard: it stays on the fault channels."""
    shape = {"stage": "fetch_decode", "reason": "vad_nonfinite"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_vad_order_at_fetch_decode_stays_a_fault():
    """vad_order at fetch_decode is not the guard: it stays on the fault channels."""
    shape = {"stage": "fetch_decode", "reason": "vad_order"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_vad_bounds_at_fetch_decode_stays_a_fault():
    """vad_bounds at fetch_decode is not the guard: it stays on the fault channels."""
    shape = {"stage": "fetch_decode", "reason": "vad_bounds"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_empty_asr_at_fetch_decode_stays_a_fault():
    """empty_asr at fetch_decode is not the guard: it stays on the fault channels."""
    shape = {"stage": "fetch_decode", "reason": "empty_asr"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_no_owned_words_at_fetch_decode_stays_a_fault():
    """no_owned_words at fetch_decode is not the guard: it stays on the fault channels."""
    shape = {"stage": "fetch_decode", "reason": "no_owned_words"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_outside_admitted_source_at_fetch_decode_stays_a_fault():
    """outside_admitted_source at fetch_decode is not the guard: it stays on the fault channels."""
    shape = {"stage": "fetch_decode", "reason": "outside_admitted_source"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_staged_audio_invalid_at_vad_windows_stays_a_fault():
    """staged_audio_invalid at vad_windows is not the guard: it stays on the fault channels."""
    shape = {"stage": "vad_windows", "reason": "staged_audio_invalid"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_retained_audio_invalid_at_vad_windows_stays_a_fault():
    """retained_audio_invalid at vad_windows is not the guard: it stays on the fault channels."""
    shape = {"stage": "vad_windows", "reason": "retained_audio_invalid"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_decoded_duration_mismatch_at_vad_windows_stays_a_fault():
    """decoded_duration_mismatch at vad_windows is not the guard: it stays on the fault channels."""
    shape = {"stage": "vad_windows", "reason": "decoded_duration_mismatch"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_word_shape_at_vad_windows_stays_a_fault():
    """word_shape at vad_windows is not the guard: it stays on the fault channels."""
    shape = {"stage": "vad_windows", "reason": "word_shape"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_word_clock_at_vad_windows_stays_a_fault():
    """word_clock at vad_windows is not the guard: it stays on the fault channels."""
    shape = {"stage": "vad_windows", "reason": "word_clock"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_word_sequence_at_vad_windows_stays_a_fault():
    """word_sequence at vad_windows is not the guard: it stays on the fault channels."""
    shape = {"stage": "vad_windows", "reason": "word_sequence"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_vad_nonfinite_at_vad_windows_stays_a_fault():
    """vad_nonfinite at vad_windows is not the guard: it stays on the fault channels."""
    shape = {"stage": "vad_windows", "reason": "vad_nonfinite"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_vad_order_at_vad_windows_stays_a_fault():
    """vad_order at vad_windows is not the guard: it stays on the fault channels."""
    shape = {"stage": "vad_windows", "reason": "vad_order"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_vad_bounds_at_vad_windows_stays_a_fault():
    """vad_bounds at vad_windows is not the guard: it stays on the fault channels."""
    shape = {"stage": "vad_windows", "reason": "vad_bounds"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_empty_asr_at_vad_windows_stays_a_fault():
    """empty_asr at vad_windows is not the guard: it stays on the fault channels."""
    shape = {"stage": "vad_windows", "reason": "empty_asr"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_no_owned_words_at_vad_windows_stays_a_fault():
    """no_owned_words at vad_windows is not the guard: it stays on the fault channels."""
    shape = {"stage": "vad_windows", "reason": "no_owned_words"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_outside_admitted_source_at_vad_windows_stays_a_fault():
    """outside_admitted_source at vad_windows is not the guard: it stays on the fault channels."""
    shape = {"stage": "vad_windows", "reason": "outside_admitted_source"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_staged_audio_invalid_at_word_clocks_stays_a_fault():
    """staged_audio_invalid at word_clocks is not the guard: it stays on the fault channels."""
    shape = {"stage": "word_clocks", "reason": "staged_audio_invalid"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_retained_audio_invalid_at_word_clocks_stays_a_fault():
    """retained_audio_invalid at word_clocks is not the guard: it stays on the fault channels."""
    shape = {"stage": "word_clocks", "reason": "retained_audio_invalid"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_decoded_duration_mismatch_at_word_clocks_stays_a_fault():
    """decoded_duration_mismatch at word_clocks is not the guard: it stays on the fault channels."""
    shape = {"stage": "word_clocks", "reason": "decoded_duration_mismatch"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_word_shape_at_word_clocks_stays_a_fault():
    """word_shape at word_clocks is not the guard: it stays on the fault channels."""
    shape = {"stage": "word_clocks", "reason": "word_shape"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_word_clock_at_word_clocks_stays_a_fault():
    """word_clock at word_clocks is not the guard: it stays on the fault channels."""
    shape = {"stage": "word_clocks", "reason": "word_clock"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_word_sequence_at_word_clocks_stays_a_fault():
    """word_sequence at word_clocks is not the guard: it stays on the fault channels."""
    shape = {"stage": "word_clocks", "reason": "word_sequence"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_vad_nonfinite_at_word_clocks_stays_a_fault():
    """vad_nonfinite at word_clocks is not the guard: it stays on the fault channels."""
    shape = {"stage": "word_clocks", "reason": "vad_nonfinite"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_vad_order_at_word_clocks_stays_a_fault():
    """vad_order at word_clocks is not the guard: it stays on the fault channels."""
    shape = {"stage": "word_clocks", "reason": "vad_order"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_vad_bounds_at_word_clocks_stays_a_fault():
    """vad_bounds at word_clocks is not the guard: it stays on the fault channels."""
    shape = {"stage": "word_clocks", "reason": "vad_bounds"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_empty_asr_at_word_clocks_stays_a_fault():
    """empty_asr at word_clocks is not the guard: it stays on the fault channels."""
    shape = {"stage": "word_clocks", "reason": "empty_asr"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_no_owned_words_at_word_clocks_stays_a_fault():
    """no_owned_words at word_clocks is not the guard: it stays on the fault channels."""
    shape = {"stage": "word_clocks", "reason": "no_owned_words"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_outside_admitted_source_at_word_clocks_stays_a_fault():
    """outside_admitted_source at word_clocks is not the guard: it stays on the fault channels."""
    shape = {"stage": "word_clocks", "reason": "outside_admitted_source"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_staged_audio_invalid_at_assemble_words_stays_a_fault():
    """staged_audio_invalid at assemble_words is not the guard: it stays on the fault channels."""
    shape = {"stage": "assemble_words", "reason": "staged_audio_invalid"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_retained_audio_invalid_at_assemble_words_stays_a_fault():
    """retained_audio_invalid at assemble_words is not the guard: it stays on the fault channels."""
    shape = {"stage": "assemble_words", "reason": "retained_audio_invalid"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_decoded_duration_mismatch_at_assemble_words_stays_a_fault():
    """decoded_duration_mismatch at assemble_words is not the guard: it stays on the fault channels."""
    shape = {"stage": "assemble_words", "reason": "decoded_duration_mismatch"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_word_shape_at_assemble_words_stays_a_fault():
    """word_shape at assemble_words is not the guard: it stays on the fault channels."""
    shape = {"stage": "assemble_words", "reason": "word_shape"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_word_clock_at_assemble_words_stays_a_fault():
    """word_clock at assemble_words is not the guard: it stays on the fault channels."""
    shape = {"stage": "assemble_words", "reason": "word_clock"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_word_sequence_at_assemble_words_stays_a_fault():
    """word_sequence at assemble_words is not the guard: it stays on the fault channels."""
    shape = {"stage": "assemble_words", "reason": "word_sequence"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_vad_nonfinite_at_assemble_words_stays_a_fault():
    """vad_nonfinite at assemble_words is not the guard: it stays on the fault channels."""
    shape = {"stage": "assemble_words", "reason": "vad_nonfinite"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_vad_order_at_assemble_words_stays_a_fault():
    """vad_order at assemble_words is not the guard: it stays on the fault channels."""
    shape = {"stage": "assemble_words", "reason": "vad_order"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_vad_bounds_at_assemble_words_stays_a_fault():
    """vad_bounds at assemble_words is not the guard: it stays on the fault channels."""
    shape = {"stage": "assemble_words", "reason": "vad_bounds"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_empty_asr_at_assemble_words_stays_a_fault():
    """empty_asr at assemble_words is not the guard: it stays on the fault channels."""
    shape = {"stage": "assemble_words", "reason": "empty_asr"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_no_owned_words_at_assemble_words_stays_a_fault():
    """no_owned_words at assemble_words is not the guard: it stays on the fault channels."""
    shape = {"stage": "assemble_words", "reason": "no_owned_words"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_outside_admitted_source_at_assemble_words_stays_a_fault():
    """outside_admitted_source at assemble_words is not the guard: it stays on the fault channels."""
    shape = {"stage": "assemble_words", "reason": "outside_admitted_source"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_staged_audio_invalid_at_asr_recovery_stays_a_fault():
    """staged_audio_invalid at asr_recovery is not the guard: it stays on the fault channels."""
    shape = {"stage": "asr_recovery", "reason": "staged_audio_invalid"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_retained_audio_invalid_at_asr_recovery_stays_a_fault():
    """retained_audio_invalid at asr_recovery is not the guard: it stays on the fault channels."""
    shape = {"stage": "asr_recovery", "reason": "retained_audio_invalid"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_decoded_duration_mismatch_at_asr_recovery_stays_a_fault():
    """decoded_duration_mismatch at asr_recovery is not the guard: it stays on the fault channels."""
    shape = {"stage": "asr_recovery", "reason": "decoded_duration_mismatch"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_word_shape_at_asr_recovery_stays_a_fault():
    """word_shape at asr_recovery is not the guard: it stays on the fault channels."""
    shape = {"stage": "asr_recovery", "reason": "word_shape"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_word_clock_at_asr_recovery_stays_a_fault():
    """word_clock at asr_recovery is not the guard: it stays on the fault channels."""
    shape = {"stage": "asr_recovery", "reason": "word_clock"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_word_sequence_at_asr_recovery_stays_a_fault():
    """word_sequence at asr_recovery is not the guard: it stays on the fault channels."""
    shape = {"stage": "asr_recovery", "reason": "word_sequence"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_vad_nonfinite_at_asr_recovery_stays_a_fault():
    """vad_nonfinite at asr_recovery is not the guard: it stays on the fault channels."""
    shape = {"stage": "asr_recovery", "reason": "vad_nonfinite"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_vad_order_at_asr_recovery_stays_a_fault():
    """vad_order at asr_recovery is not the guard: it stays on the fault channels."""
    shape = {"stage": "asr_recovery", "reason": "vad_order"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_vad_bounds_at_asr_recovery_stays_a_fault():
    """vad_bounds at asr_recovery is not the guard: it stays on the fault channels."""
    shape = {"stage": "asr_recovery", "reason": "vad_bounds"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_empty_asr_at_asr_recovery_stays_a_fault():
    """empty_asr at asr_recovery is not the guard: it stays on the fault channels."""
    shape = {"stage": "asr_recovery", "reason": "empty_asr"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_no_owned_words_at_asr_recovery_stays_a_fault():
    """no_owned_words at asr_recovery is not the guard: it stays on the fault channels."""
    shape = {"stage": "asr_recovery", "reason": "no_owned_words"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_reason_outside_admitted_source_at_asr_recovery_stays_a_fault():
    """outside_admitted_source at asr_recovery is not the guard: it stays on the fault channels."""
    shape = {"stage": "asr_recovery", "reason": "outside_admitted_source"}
    assert language_guard_redrive_failure(shape) is False
    validate_worker_failure(shape)  # closed shape the fault channels keep


def test_off_vocabulary_stage_0_never_demotes():
    """A stage outside the closed vocabulary never demotes."""
    assert language_guard_redrive_failure({"stage": '', "reason": "unsupported_language"}) is False


def test_off_vocabulary_stage_1_never_demotes():
    """A stage outside the closed vocabulary never demotes."""
    assert language_guard_redrive_failure({"stage": 'mystery', "reason": "unsupported_language"}) is False


def test_off_vocabulary_stage_2_never_demotes():
    """A stage outside the closed vocabulary never demotes."""
    assert language_guard_redrive_failure({"stage": 'VAD_WINDOWS', "reason": "unsupported_language"}) is False


def test_none_stage_never_demotes():
    assert language_guard_redrive_failure({"stage": None, "reason": "unsupported_language"}) is False


def test_malformed_none_input_never_demotes():
    """None is not a diagnosis."""
    assert language_guard_redrive_failure(None) is False


def test_malformed_list_input_never_demotes():
    """A list is not a diagnosis."""
    assert language_guard_redrive_failure([]) is False


def test_malformed_tuple_input_never_demotes():
    """A tuple is not a diagnosis."""
    assert language_guard_redrive_failure(()) is False


def test_malformed_empty_dict_never_demotes():
    """The anonymous shape stays a fault."""
    assert language_guard_redrive_failure({}) is False


def test_malformed_int_input_never_demotes():
    """Scalars never classify."""
    assert language_guard_redrive_failure(42) is False


def test_malformed_plain_string_never_demotes():
    """A bare token is not a diagnosis shape."""
    assert language_guard_redrive_failure("unsupported_language") is False


def test_malformed_reason_only_never_demotes():
    """A reason without a stage is not the closed shape."""
    assert language_guard_redrive_failure({"reason": "unsupported_language"}) is False


def test_malformed_stage_only_never_demotes():
    """A stage without a reason is not the closed shape."""
    assert language_guard_redrive_failure({"stage": "vad_windows"}) is False


def test_malformed_extra_field_never_demotes():
    """Extra fields break the closed shape."""
    assert (
        language_guard_redrive_failure({"stage": "vad_windows", "reason": "unsupported_language", "detail": "x"})
        is False
    )


def test_malformed_reason_int_never_demotes():
    """Non-token reasons never demote."""
    assert language_guard_redrive_failure({"stage": "vad_windows", "reason": 7}) is False


def test_malformed_reason_none_never_demotes():
    """None reasons never demote."""
    assert language_guard_redrive_failure({"stage": "vad_windows", "reason": None}) is False


def test_malformed_reason_list_never_demotes():
    """List reasons never demote."""
    assert language_guard_redrive_failure({"stage": "vad_windows", "reason": ["unsupported_language"]}) is False


def test_malformed_stage_int_never_demotes():
    """Non-token stages never demote."""
    assert language_guard_redrive_failure({"stage": 3, "reason": "unsupported_language"}) is False


def test_attribute_bag_never_demotes():
    """Attribute bags are not diagnoses."""
    assert language_guard_redrive_failure(SimpleNamespace(stage="vad_windows")) is False


def test_plain_object_never_demotes():
    assert language_guard_redrive_failure(object()) is False


def test_store_accepts_guard_shape_at_fetch_decode():
    """The durable store accepts the guard shape at every closed stage."""
    validate_worker_failure({"stage": "fetch_decode", "reason": "unsupported_language"})


def test_evidence_accepts_guard_shape_at_fetch_decode():
    """Evidence-only diagnostics accept the guard shape too."""
    validate_worker_failure_evidence({"stage": "fetch_decode", "reason": "unsupported_language"})


def test_store_accepts_guard_shape_at_vad_windows():
    """The durable store accepts the guard shape at every closed stage."""
    validate_worker_failure({"stage": "vad_windows", "reason": "unsupported_language"})


def test_evidence_accepts_guard_shape_at_vad_windows():
    """Evidence-only diagnostics accept the guard shape too."""
    validate_worker_failure_evidence({"stage": "vad_windows", "reason": "unsupported_language"})


def test_store_accepts_guard_shape_at_word_clocks():
    """The durable store accepts the guard shape at every closed stage."""
    validate_worker_failure({"stage": "word_clocks", "reason": "unsupported_language"})


def test_evidence_accepts_guard_shape_at_word_clocks():
    """Evidence-only diagnostics accept the guard shape too."""
    validate_worker_failure_evidence({"stage": "word_clocks", "reason": "unsupported_language"})


def test_store_accepts_guard_shape_at_assemble_words():
    """The durable store accepts the guard shape at every closed stage."""
    validate_worker_failure({"stage": "assemble_words", "reason": "unsupported_language"})


def test_evidence_accepts_guard_shape_at_assemble_words():
    """Evidence-only diagnostics accept the guard shape too."""
    validate_worker_failure_evidence({"stage": "assemble_words", "reason": "unsupported_language"})


def test_store_accepts_guard_shape_at_asr_recovery():
    """The durable store accepts the guard shape at every closed stage."""
    validate_worker_failure({"stage": "asr_recovery", "reason": "unsupported_language"})


def test_evidence_accepts_guard_shape_at_asr_recovery():
    """Evidence-only diagnostics accept the guard shape too."""
    validate_worker_failure_evidence({"stage": "asr_recovery", "reason": "unsupported_language"})


def test_closed_shape_rejects_extra_field():
    """Closed shapes stay closed."""
    with pytest.raises(ValueError):
        validate_worker_failure({"stage": "vad_windows", "reason": "unsupported_language", "note": "x"})


def test_closed_shape_rejects_off_vocabulary_stage():
    """Off-vocabulary stages are refused by the store validator."""
    with pytest.raises(ValueError):
        validate_worker_failure({"stage": "not_a_stage", "reason": "unsupported_language"})


def test_reason_set_holds_exactly_the_guard_token():
    """The demotion key is exactly one closed reason."""
    assert LANGUAGE_GUARD_REDRIVE_REASONS == {"unsupported_language"}


def test_reason_set_is_frozen():
    """The demotion key is immutable."""
    assert isinstance(LANGUAGE_GUARD_REDRIVE_REASONS, frozenset)


def test_reason_set_matches_the_typed_validation_reason():
    """The worker raise site and the demotion key agree."""
    assert ValidationReason.UNSUPPORTED_LANGUAGE.value in LANGUAGE_GUARD_REDRIVE_REASONS


def test_reason_set_matches_the_observability_reason():
    """The stored closed code and the demotion key agree."""
    assert WorkerValidationReason.UNSUPPORTED_LANGUAGE.value in LANGUAGE_GUARD_REDRIVE_REASONS


def test_payload_bearing_three_key_shape_is_not_the_closed_shape():
    """The stored shape is exactly two keys; anything wider keeps the fault channel."""
    shape = {"stage": "vad_windows", "reason": "unsupported_language", "payload": "secret"}
    assert language_guard_redrive_failure(shape) is False


def test_predicate_classifies_purely_on_the_two_closed_tokens():
    """The predicate reads the closed tokens, never a payload."""
    shape = {"reason": "unsupported_language", "stage": "fetch_decode"}
    assert language_guard_redrive_failure(shape) is True
    assert "payload" not in LANGUAGE_GUARD_REDRIVE_REASONS


def test_closed_stage_vocabulary_excludes_unknown():
    """The anonymous stage never joins the closed shapes (legacy exclusion)."""
    assert "unknown" not in WORKER_VALIDATION_STAGES


def test_closed_stage_vocabulary_has_fetch_decode():
    """The stage vocabulary and the observable enum agree."""
    assert "fetch_decode" in WORKER_VALIDATION_STAGES


def test_closed_stage_vocabulary_has_vad_windows():
    """The stage vocabulary and the observable enum agree."""
    assert "vad_windows" in WORKER_VALIDATION_STAGES


def test_closed_stage_vocabulary_has_word_clocks():
    """The stage vocabulary and the observable enum agree."""
    assert "word_clocks" in WORKER_VALIDATION_STAGES


def test_closed_stage_vocabulary_has_assemble_words():
    """The stage vocabulary and the observable enum agree."""
    assert "assemble_words" in WORKER_VALIDATION_STAGES


def test_closed_stage_vocabulary_has_asr_recovery():
    """The stage vocabulary and the observable enum agree."""
    assert "asr_recovery" in WORKER_VALIDATION_STAGES


def test_closed_reason_vocabulary_excludes_unknown():
    """The anonymous reason never joins the closed shapes."""
    assert "unknown" not in WORKER_VALIDATION_REASONS


def test_closed_reason_vocabulary_has_staged_audio_invalid():
    """The reason vocabulary and the observable enum agree."""
    assert "staged_audio_invalid" in WORKER_VALIDATION_REASONS


def test_closed_reason_vocabulary_has_retained_audio_invalid():
    """The reason vocabulary and the observable enum agree."""
    assert "retained_audio_invalid" in WORKER_VALIDATION_REASONS


def test_closed_reason_vocabulary_has_decoded_duration_mismatch():
    """The reason vocabulary and the observable enum agree."""
    assert "decoded_duration_mismatch" in WORKER_VALIDATION_REASONS


def test_closed_reason_vocabulary_has_word_shape():
    """The reason vocabulary and the observable enum agree."""
    assert "word_shape" in WORKER_VALIDATION_REASONS


def test_closed_reason_vocabulary_has_word_clock():
    """The reason vocabulary and the observable enum agree."""
    assert "word_clock" in WORKER_VALIDATION_REASONS


def test_closed_reason_vocabulary_has_word_sequence():
    """The reason vocabulary and the observable enum agree."""
    assert "word_sequence" in WORKER_VALIDATION_REASONS


def test_closed_reason_vocabulary_has_vad_nonfinite():
    """The reason vocabulary and the observable enum agree."""
    assert "vad_nonfinite" in WORKER_VALIDATION_REASONS


def test_closed_reason_vocabulary_has_vad_order():
    """The reason vocabulary and the observable enum agree."""
    assert "vad_order" in WORKER_VALIDATION_REASONS


def test_closed_reason_vocabulary_has_vad_bounds():
    """The reason vocabulary and the observable enum agree."""
    assert "vad_bounds" in WORKER_VALIDATION_REASONS


def test_closed_reason_vocabulary_has_empty_asr():
    """The reason vocabulary and the observable enum agree."""
    assert "empty_asr" in WORKER_VALIDATION_REASONS


def test_closed_reason_vocabulary_has_no_owned_words():
    """The reason vocabulary and the observable enum agree."""
    assert "no_owned_words" in WORKER_VALIDATION_REASONS


def test_closed_reason_vocabulary_has_unsupported_language():
    """The reason vocabulary and the observable enum agree."""
    assert "unsupported_language" in WORKER_VALIDATION_REASONS


def test_closed_reason_vocabulary_has_outside_admitted_source():
    """The reason vocabulary and the observable enum agree."""
    assert "outside_admitted_source" in WORKER_VALIDATION_REASONS


def test_unknown_stage_never_demotes_and_stays_unclosable():
    """The anonymous stage keeps the fault channel and cannot be stored as a closed shape."""
    shape = {"stage": "unknown", "reason": "unsupported_language"}
    assert language_guard_redrive_failure(shape) is False
    with pytest.raises(ValueError):
        validate_worker_failure(shape)


def test_unknown_reason_never_demotes_and_stays_unclosable():
    """The anonymous reason keeps the fault channel and cannot be stored as a closed shape."""
    shape = {"stage": "vad_windows", "reason": "unknown"}
    assert language_guard_redrive_failure(shape) is False
    with pytest.raises(ValueError):
        validate_worker_failure(shape)


def test_validation_reason_UNSUPPORTED_LANGUAGE_keeps_token_unsupported_language():
    """The typed raise-site enum keeps its closed token."""
    assert ValidationReason.UNSUPPORTED_LANGUAGE.value == "unsupported_language"


def test_validation_reason_WORD_SHAPE_keeps_token_word_shape():
    """The typed raise-site enum keeps its closed token."""
    assert ValidationReason.WORD_SHAPE.value == "word_shape"


def test_validation_reason_WORD_CLOCK_keeps_token_word_clock():
    """The typed raise-site enum keeps its closed token."""
    assert ValidationReason.WORD_CLOCK.value == "word_clock"


def test_validation_reason_WORD_SEQUENCE_keeps_token_word_sequence():
    """The typed raise-site enum keeps its closed token."""
    assert ValidationReason.WORD_SEQUENCE.value == "word_sequence"


def test_validation_reason_VAD_NONFINITE_keeps_token_vad_nonfinite():
    """The typed raise-site enum keeps its closed token."""
    assert ValidationReason.VAD_NONFINITE.value == "vad_nonfinite"


def test_validation_reason_VAD_ORDER_keeps_token_vad_order():
    """The typed raise-site enum keeps its closed token."""
    assert ValidationReason.VAD_ORDER.value == "vad_order"


def test_validation_reason_VAD_BOUNDS_keeps_token_vad_bounds():
    """The typed raise-site enum keeps its closed token."""
    assert ValidationReason.VAD_BOUNDS.value == "vad_bounds"


def test_validation_reason_EMPTY_ASR_keeps_token_empty_asr():
    """The typed raise-site enum keeps its closed token."""
    assert ValidationReason.EMPTY_ASR.value == "empty_asr"


def test_validation_reason_NO_OWNED_WORDS_keeps_token_no_owned_words():
    """The typed raise-site enum keeps its closed token."""
    assert ValidationReason.NO_OWNED_WORDS.value == "no_owned_words"


def test_language_class_english_is_supported():
    assert language_class("en") == "supported"


def test_language_class_vietnamese_is_not_supported():
    """A parakeet-unsupported code feeds the guard."""
    assert language_class("vi") != "supported"


def test_language_class_none_is_not_supported():
    assert language_class(None) != "supported"


def test_language_class_empty_is_not_supported():
    assert language_class("") != "supported"


def test_language_class_und_is_not_supported():
    assert language_class("und") != "supported"


def test_language_class_multi_is_not_supported():
    assert language_class("multi") != "supported"


def test_language_class_unknown_token_is_not_supported():
    assert language_class("unknown") != "supported"
