# Failure-Class: FC-empty-ladder-recovery-handoff-misclassified-as-worker-fault
"""The pump routing and hand-off contracts that feed the demoted channels.

``RecoveryWork`` still fails the unit quarantined with the structured
assemble_words fault, the padded token, and the VAD evidence;
``ValidationFailureWork`` still fails evidence-only; ``HeldWork`` still
defers with admission refused; plain ``FailedWork`` still carries its
diagnosis as ladder evidence; ``WorkResult`` still completes. Every
dataclass field and default the routing reads is pinned next to it.
"""

import dataclasses
from pathlib import Path

from utils.batch_pipeline.contracts import FailedWork, HeldWork, RecoveryWork, ValidationFailureWork, WorkResult
import pytest


def _fields(cls):
    return [f.name for f in dataclasses.fields(cls)]


def _defaults(cls):
    return {f.name: f.default for f in dataclasses.fields(cls) if f.default is not dataclasses._MISSING_TYPE}


def test_RecoveryWork_field_segment_id_exists():
    assert "segment_id" in _fields(RecoveryWork)


def test_RecoveryWork_field_padded_retry_empty_exists():
    assert "padded_retry_empty" in _fields(RecoveryWork)


def test_RecoveryWork_field_padded_retry_exists():
    assert "padded_retry" in _fields(RecoveryWork)


def test_RecoveryWork_field_reason_exists():
    assert "reason" in _fields(RecoveryWork)


def test_RecoveryWork_field_measured_held_vad_speech_seconds_exists():
    assert "measured_held_vad_speech_seconds" in _fields(RecoveryWork)


def test_RecoveryWork_field_worker_vad_receipt_exists():
    assert "worker_vad_receipt" in _fields(RecoveryWork)


def test_ValidationFailureWork_field_segment_id_exists():
    assert "segment_id" in _fields(ValidationFailureWork)


def test_ValidationFailureWork_field_stage_exists():
    assert "stage" in _fields(ValidationFailureWork)


def test_ValidationFailureWork_field_reason_exists():
    assert "reason" in _fields(ValidationFailureWork)


def test_ValidationFailureWork_field_measured_held_vad_speech_seconds_exists():
    assert "measured_held_vad_speech_seconds" in _fields(ValidationFailureWork)


def test_ValidationFailureWork_field_worker_vad_receipt_exists():
    assert "worker_vad_receipt" in _fields(ValidationFailureWork)


def test_FailedWork_field_segment_id_exists():
    assert "segment_id" in _fields(FailedWork)


def test_FailedWork_field_measured_held_vad_speech_seconds_exists():
    assert "measured_held_vad_speech_seconds" in _fields(FailedWork)


def test_FailedWork_field_worker_vad_receipt_exists():
    assert "worker_vad_receipt" in _fields(FailedWork)


def test_FailedWork_field_worker_failure_exists():
    assert "worker_failure" in _fields(FailedWork)


def test_HeldWork_field_segment_id_exists():
    assert "segment_id" in _fields(HeldWork)


def test_HeldWork_field_retry_after_exists():
    assert "retry_after" in _fields(HeldWork)


def test_HeldWork_field_reason_exists():
    assert "reason" in _fields(HeldWork)


def test_RecoveryWork_default_padded_retry_empty_is_false():
    assert _defaults(RecoveryWork)["padded_retry_empty"] == False


def test_RecoveryWork_default_padded_retry_is_none():
    assert _defaults(RecoveryWork)["padded_retry"] == None


def test_RecoveryWork_default_reason_is_empty_asr():
    assert _defaults(RecoveryWork)["reason"] == 'empty_asr'


def test_ValidationFailureWork_default_measured_held_vad_speech_seconds_is_none():
    assert _defaults(ValidationFailureWork)["measured_held_vad_speech_seconds"] == None


def test_FailedWork_default_worker_failure_is_none():
    assert _defaults(FailedWork)["worker_failure"] == None


def test_HeldWork_default_retry_after_is_60():
    assert _defaults(HeldWork)["retry_after"] == 60


def test_HeldWork_default_reason_is_():
    assert _defaults(HeldWork)["reason"] == ''


def test_recovery_work_rejects_unclosed_empty_reason():
    with pytest.raises(ValueError, match="closed empty worker reason required"):
        RecoveryWork("a", reason="mystery")


def test_recovery_work_accepts_the_no_owned_words_family_member():
    held = RecoveryWork("a", reason="no_owned_words", padded_retry="empty", padded_retry_empty=True)
    assert held.reason == "no_owned_words"


def test_recovery_work_normalizes_none_token_with_empty_flag():
    assert RecoveryWork("a", padded_retry_empty=True).padded_retry == "empty"


def test_recovery_work_normalizes_empty_token_with_false_flag():
    assert RecoveryWork("a", padded_retry="empty").padded_retry_empty is True


def test_recovery_work_rejects_conflicting_token_and_flag():
    with pytest.raises(ValueError, match="conflicting padded retry evidence"):
        RecoveryWork("a", padded_retry="skipped_oversize", padded_retry_empty=True)


def test_recovery_work_rejects_unknown_padded_token():
    with pytest.raises(ValueError, match="unsupported padded retry evidence"):
        RecoveryWork("a", padded_retry="identical")


def test_validation_failure_work_validates_its_closed_shape():
    with pytest.raises(ValueError, match="closed worker validation failure required"):
        ValidationFailureWork("a", "assemble_words", "mystery")


def test_failed_work_validates_its_evidence():
    with pytest.raises(ValueError, match="closed worker failure evidence required"):
        FailedWork("a", worker_failure={"stage": "assemble_words", "reason": "mystery"})


def test_work_outcome_vocabulary_is_untouched():
    from utils.observability.reasons import WorkOutcome

    assert WorkOutcome.SILENCE.value == "silence"
    assert WorkOutcome.NO_RECOVERABLE_SPEECH.value == "no_recoverable_speech"


def test_disposition_source_keeps_result_outcome_resolver():
    source = (Path(__file__).resolve().parents[2] / "utils" / "batch_pipeline" / "recovery_disposition.py").read_text()
    assert "def result_outcome" in source


def test_disposition_source_keeps_the_independent_silence_provider_token():
    source = (Path(__file__).resolve().parents[2] / "utils" / "batch_pipeline" / "recovery_disposition.py").read_text()
    assert "independent_empty_strict_vad" in source


def test_disposition_source_keeps_the_words_provider_key():
    source = (Path(__file__).resolve().parents[2] / "utils" / "batch_pipeline" / "recovery_disposition.py").read_text()
    assert "words_provider" in source


def test_pump_source_keeps_the_publication_pool_name():
    source = Path(__file__).resolve().parents[2].joinpath("utils", "batch_pipeline", "pump.py").read_text()
    assert "'publication'" in source


def test_pump_source_keeps_the_scheduler_delegate():
    source = Path(__file__).resolve().parents[2].joinpath("utils", "batch_pipeline", "pump.py").read_text()
    assert "self.scheduler.defer" in source


def test_pump_source_has_no_ladder_predicate_import():
    source = Path(__file__).resolve().parents[2].joinpath("utils", "batch_pipeline", "pump.py").read_text()
    assert "empty_ladder_recovery_failure" not in source


def test_pump_source_has_no_guard_predicate_import():
    source = Path(__file__).resolve().parents[2].joinpath("utils", "batch_pipeline", "pump.py").read_text()
    assert "language_guard_redrive_failure" not in source


def test_pump_source_has_no_empty_ladder_event():
    source = Path(__file__).resolve().parents[2].joinpath("utils", "batch_pipeline", "pump.py").read_text()
    assert "event=batch_empty_ladder" not in source


def test_pump_source_has_no_language_guard_event():
    source = Path(__file__).resolve().parents[2].joinpath("utils", "batch_pipeline", "pump.py").read_text()
    assert "event=batch_language_guard" not in source


def test_pump_source_has_no_quarantine_terminal_event():
    source = Path(__file__).resolve().parents[2].joinpath("utils", "batch_pipeline", "pump.py").read_text()
    assert "event=batch_quarantined" not in source
