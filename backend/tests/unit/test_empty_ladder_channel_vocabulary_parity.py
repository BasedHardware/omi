# Failure-Class: FC-empty-ladder-recovery-handoff-misclassified-as-worker-fault
"""The closed vocabularies the empty-ladder family lives in, member-by-member.

``WorkerValidationReason`` and ``WorkerValidationStage`` members, the
``reason_values`` exclusion of ``unknown``, the family and guard sets'
membership and disjointness, the store validator surfaces
(``validate_worker_failure`` / ``validate_worker_failure_evidence``) that
admit exactly the shapes the demotion predicate accepts, and the metric-label
round-trip for the family tokens.
"""

import pytest

from utils.batch_pipeline.errors import (
    EMPTY_LADDER_RECOVERY_REASONS,
    LANGUAGE_GUARD_REDRIVE_REASONS,
    validate_worker_failure,
    validate_worker_failure_evidence,
)
from utils.observability.reasons import (
    REASON_VALUE_MAX_LENGTH,
    RecoveryFailureReason,
    ReasonFamily,
    WorkerValidationReason,
    WorkerValidationStage,
    reason_label,
    reason_values,
)

STAGES = ('fetch_decode', 'vad_windows', 'word_clocks', 'assemble_words', 'asr_recovery')
REASONS = (
    'staged_audio_invalid',
    'retained_audio_invalid',
    'decoded_duration_mismatch',
    'word_shape',
    'word_clock',
    'word_sequence',
    'vad_nonfinite',
    'vad_order',
    'vad_bounds',
    'empty_asr',
    'no_owned_words',
    'unsupported_language',
    'outside_admitted_source',
    'unknown',
)


def test_worker_validation_reason_member_UNKNOWN():
    assert WorkerValidationReason.UNKNOWN.value == "unknown"


def test_worker_validation_reason_member_STAGED_AUDIO_INVALID():
    assert WorkerValidationReason.STAGED_AUDIO_INVALID.value == "staged_audio_invalid"


def test_worker_validation_reason_member_RETAINED_AUDIO_INVALID():
    assert WorkerValidationReason.RETAINED_AUDIO_INVALID.value == "retained_audio_invalid"


def test_worker_validation_reason_member_DECODED_DURATION_MISMATCH():
    assert WorkerValidationReason.DECODED_DURATION_MISMATCH.value == "decoded_duration_mismatch"


def test_worker_validation_reason_member_WORD_SHAPE():
    assert WorkerValidationReason.WORD_SHAPE.value == "word_shape"


def test_worker_validation_reason_member_WORD_CLOCK():
    assert WorkerValidationReason.WORD_CLOCK.value == "word_clock"


def test_worker_validation_reason_member_WORD_SEQUENCE():
    assert WorkerValidationReason.WORD_SEQUENCE.value == "word_sequence"


def test_worker_validation_reason_member_VAD_NONFINITE():
    assert WorkerValidationReason.VAD_NONFINITE.value == "vad_nonfinite"


def test_worker_validation_reason_member_VAD_ORDER():
    assert WorkerValidationReason.VAD_ORDER.value == "vad_order"


def test_worker_validation_reason_member_VAD_BOUNDS():
    assert WorkerValidationReason.VAD_BOUNDS.value == "vad_bounds"


def test_worker_validation_reason_member_EMPTY_ASR():
    assert WorkerValidationReason.EMPTY_ASR.value == "empty_asr"


def test_worker_validation_reason_member_NO_OWNED_WORDS():
    assert WorkerValidationReason.NO_OWNED_WORDS.value == "no_owned_words"


def test_worker_validation_reason_member_UNSUPPORTED_LANGUAGE():
    assert WorkerValidationReason.UNSUPPORTED_LANGUAGE.value == "unsupported_language"


def test_worker_validation_reason_member_OUTSIDE_ADMITTED_SOURCE():
    assert WorkerValidationReason.OUTSIDE_ADMITTED_SOURCE.value == "outside_admitted_source"


def test_worker_validation_stage_member_UNKNOWN():
    assert WorkerValidationStage.UNKNOWN.value == "unknown"


def test_worker_validation_stage_member_FETCH_DECODE():
    assert WorkerValidationStage.FETCH_DECODE.value == "fetch_decode"


def test_worker_validation_stage_member_VAD_WINDOWS():
    assert WorkerValidationStage.VAD_WINDOWS.value == "vad_windows"


def test_worker_validation_stage_member_WORD_CLOCKS():
    assert WorkerValidationStage.WORD_CLOCKS.value == "word_clocks"


def test_worker_validation_stage_member_ASSEMBLE_WORDS():
    assert WorkerValidationStage.ASSEMBLE_WORDS.value == "assemble_words"


def test_worker_validation_stage_member_ASR_RECOVERY():
    assert WorkerValidationStage.ASR_RECOVERY.value == "asr_recovery"


def test_recovery_failure_reason_member_UNKNOWN():
    assert RecoveryFailureReason.UNKNOWN.value == "unknown"


def test_recovery_failure_reason_member_INVALID_AUDIO():
    assert RecoveryFailureReason.INVALID_AUDIO.value == "invalid_audio"


def test_recovery_failure_reason_member_VAD_FAILED():
    assert RecoveryFailureReason.VAD_FAILED.value == "vad_failed"


def test_recovery_failure_reason_member_INVALID_VAD():
    assert RecoveryFailureReason.INVALID_VAD.value == "invalid_vad"


def test_recovery_failure_reason_member_NO_SPEECH():
    assert RecoveryFailureReason.NO_SPEECH.value == "no_speech"


def test_recovery_failure_reason_member_PROVIDER_FAILED():
    assert RecoveryFailureReason.PROVIDER_FAILED.value == "provider_failed"


def test_recovery_failure_reason_member_INVALID_RESPONSE():
    assert RecoveryFailureReason.INVALID_RESPONSE.value == "invalid_response"


def test_recovery_failure_reason_member_EMPTY_ASR():
    assert RecoveryFailureReason.EMPTY_ASR.value == "empty_asr"


def test_recovery_failure_reason_member_INVALID_PAYLOAD():
    assert RecoveryFailureReason.INVALID_PAYLOAD.value == "invalid_payload"


def test_recovery_failure_reason_member_OPERATION_FAILED():
    assert RecoveryFailureReason.OPERATION_FAILED.value == "operation_failed"


def test_recovery_failure_reason_member_ABANDONED_RUNNING():
    assert RecoveryFailureReason.ABANDONED_RUNNING.value == "abandoned_running"


def test_reason_values_excludes_unknown_for_stages():
    assert "unknown" not in reason_values(WorkerValidationStage)


def test_reason_values_excludes_unknown_for_reasons():
    assert "unknown" not in reason_values(WorkerValidationReason)


def test_family_subset_of_closed_reasons():
    assert EMPTY_LADDER_RECOVERY_REASONS <= reason_values(WorkerValidationReason)


def test_guard_subset_of_closed_reasons():
    assert LANGUAGE_GUARD_REDRIVE_REASONS <= reason_values(WorkerValidationReason)


def test_family_and_guard_are_disjoint():
    assert EMPTY_LADDER_RECOVERY_REASONS.isdisjoint(LANGUAGE_GUARD_REDRIVE_REASONS)


def test_unknown_reason_value_repeats_across_families():
    assert RecoveryFailureReason.UNKNOWN.value == WorkerValidationReason.UNKNOWN.value == "unknown"


def test_reason_value_max_length_bounds_every_token():
    for token in reason_values(WorkerValidationReason) | reason_values(WorkerValidationStage):
        assert len(token) <= REASON_VALUE_MAX_LENGTH


def test_family_tokens_are_lower_snake():
    for token in EMPTY_LADDER_RECOVERY_REASONS:
        assert token == token.lower() and "_" in token


def test_reason_label_round_trips_empty_asr():
    assert reason_label(ReasonFamily.WORKER_VALIDATION, "empty_asr", WorkerValidationReason) == "empty_asr"


def test_reason_label_round_trips_no_owned_words():
    assert reason_label(ReasonFamily.WORKER_VALIDATION, "no_owned_words", WorkerValidationReason) == "no_owned_words"


def test_reason_label_folds_foreign_reason_to_unknown():
    assert reason_label(ReasonFamily.WORKER_VALIDATION, "mystery", WorkerValidationReason) == "unknown"


def test_validator_accepts_empty_asr_shape():
    validate_worker_failure({"stage": "assemble_words", "reason": "empty_asr"})


def test_validator_accepts_no_owned_words_shape():
    validate_worker_failure({"stage": "assemble_words", "reason": "no_owned_words"})


def test_validator_accepts_guard_shape():
    validate_worker_failure({"stage": "vad_windows", "reason": "unsupported_language"})


def test_validator_accepts_typed_fault_shapes():
    validate_worker_failure({"stage": "fetch_decode", "reason": "staged_audio_invalid"})
    validate_worker_failure({"stage": "vad_windows", "reason": "vad_bounds"})
    validate_worker_failure({"stage": "word_clocks", "reason": "word_clock"})


def test_validator_rejects_mystery_reason():
    with pytest.raises(ValueError, match="closed worker validation failure required"):
        validate_worker_failure({"stage": "assemble_words", "reason": "mystery"})


def test_validator_rejects_unknown_reason():
    with pytest.raises(ValueError, match="closed worker validation failure required"):
        validate_worker_failure({"stage": "assemble_words", "reason": "unknown"})


def test_validator_rejects_unknown_stage():
    with pytest.raises(ValueError, match="closed worker validation failure required"):
        validate_worker_failure({"stage": "unknown", "reason": "empty_asr"})


def test_validator_rejects_extra_field():
    with pytest.raises(ValueError, match="closed worker validation failure required"):
        validate_worker_failure({"stage": "assemble_words", "reason": "empty_asr", "extra": 1})


def test_validator_rejects_missing_field():
    with pytest.raises(ValueError, match="closed worker validation failure required"):
        validate_worker_failure({"stage": "assemble_words"})


def test_validator_rejects_non_dict():
    with pytest.raises(ValueError, match="closed worker validation failure required"):
        validate_worker_failure("assemble_words")


def test_validator_rejects_non_string_reason():
    with pytest.raises(ValueError, match="closed worker validation failure required"):
        validate_worker_failure({"stage": "assemble_words", "reason": 7})


def test_evidence_accepts_empty_asr_shape():
    validate_worker_failure_evidence({"stage": "assemble_words", "reason": "empty_asr"})


def test_evidence_accepts_no_owned_words_shape():
    validate_worker_failure_evidence({"stage": "assemble_words", "reason": "no_owned_words"})


def test_evidence_accepts_unknown_reason_at_closed_stage():
    validate_worker_failure_evidence({"stage": "fetch_decode", "reason": "unknown"})


def test_evidence_rejects_off_vocabulary_stage():
    with pytest.raises(ValueError, match="closed worker failure evidence required"):
        validate_worker_failure_evidence({"stage": "provider", "reason": "empty_asr"})


def test_evidence_rejects_extra_field():
    with pytest.raises(ValueError, match="closed worker failure evidence required"):
        validate_worker_failure_evidence({"stage": "assemble_words", "reason": "empty_asr", "extra": 1})


def test_recovery_failure_reason_empty_asr_is_a_distinct_family_surface():
    assert RecoveryFailureReason.EMPTY_ASR.value == "empty_asr"
    assert RecoveryFailureReason.EMPTY_ASR is not WorkerValidationReason.EMPTY_ASR


def test_validator_rejects_bytes_stage():
    with pytest.raises(ValueError, match="closed worker validation failure required"):
        validate_worker_failure({"stage": b"assemble_words", "reason": "empty_asr"})


def test_validator_rejects_bytes_reason():
    with pytest.raises(ValueError, match="closed worker validation failure required"):
        validate_worker_failure({"stage": "assemble_words", "reason": b"empty_asr"})


def test_validator_rejects_none_stage():
    with pytest.raises(ValueError, match="closed worker validation failure required"):
        validate_worker_failure({"stage": None, "reason": "empty_asr"})


def test_validator_rejects_none_reason():
    with pytest.raises(ValueError, match="closed worker validation failure required"):
        validate_worker_failure({"stage": "assemble_words", "reason": None})


def test_evidence_rejects_bytes_stage():
    with pytest.raises(ValueError, match="closed worker failure evidence required"):
        validate_worker_failure_evidence({"stage": b"assemble_words", "reason": "empty_asr"})


def test_evidence_rejects_none_reason():
    with pytest.raises(ValueError, match="closed worker failure evidence required"):
        validate_worker_failure_evidence({"stage": "assemble_words", "reason": None})


def test_reason_label_accepts_the_enum_member_instance():
    assert (
        reason_label(ReasonFamily.WORKER_VALIDATION, WorkerValidationReason.EMPTY_ASR, WorkerValidationReason)
        == "empty_asr"
    )


def test_reason_label_accepts_the_no_owned_member_instance():
    assert (
        reason_label(ReasonFamily.WORKER_VALIDATION, WorkerValidationReason.NO_OWNED_WORDS, WorkerValidationReason)
        == "no_owned_words"
    )
