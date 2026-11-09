# Failure-Class: FC-empty-ladder-recovery-handoff-misclassified-as-worker-fault
"""Everything the demotion must not move, pinned next to the new classification.

The worker's failure-record field order, the closed-evidence mapping, the
shadow-worker handoff comment and branch, the pump's publication retry
swallow, and the demotion's own argument purity: the rechannel is a report
change, and this suite holds every adjacent surface still.
"""

import inspect
from pathlib import Path

import diarizer.batch_pipeline as worker_module
from config.batch_pipeline_empty_asr import empty_ladder_handoff, safety_net_enabled
from diarizer.batch_pipeline import transient_failure_evidence
from utils.batch_pipeline.errors import (
    empty_ladder_recovery_failure,
    validate_worker_failure_evidence,
)
from utils.observability.reasons import RecoveryFailureReason, WorkerValidationReason

WORKER_SOURCE = inspect.getsource(worker_module)
PUMP_SOURCE = (Path(__file__).resolve().parents[2] / "utils" / "batch_pipeline" / "pump.py").read_text()
SHADOW_SOURCE = (Path(__file__).resolve().parents[2] / "utils" / "batch_pipeline" / "shadow_worker.py").read_text()

RECORD_FIELDS = [
    "type(exc).__name__",
    "stage",
    "item.segment_id",
    "reason",
    "shape['samples']",
    "shape['vad_spans']",
    "shape['windows']",
    "shape['asr_words']",
    "owned",
]


def test_worker_failure_record_keeps_its_nine_field_order():
    """The demoted INFO call passes the identical argument tuple the fault call passed."""
    for field in RECORD_FIELDS:
        assert field in WORKER_SOURCE


def test_worker_counts_failed_increments_once_per_failed_unit():
    assert "self.counts['failed'] += 1" in WORKER_SOURCE


def test_worker_failure_callback_receives_the_class_name_only():
    assert "self.on_failure(item, type(exc).__name__)" in WORKER_SOURCE


def test_worker_failure_callback_is_guarded_against_callback_errors():
    assert "batch_failure_callback_failed exception_type=%s" in WORKER_SOURCE


def test_evidence_mapping_empty_asr_is_closed():
    assert transient_failure_evidence("assemble_words", "empty_asr") == {
        "stage": "assemble_words",
        "reason": "empty_asr",
    }


def test_evidence_mapping_no_owned_words_is_closed():
    assert transient_failure_evidence("assemble_words", "no_owned_words") == {
        "stage": "assemble_words",
        "reason": "no_owned_words",
    }


def test_evidence_mapping_vad_bounds_is_closed():
    assert transient_failure_evidence("vad_windows", "vad_bounds") == {"stage": "vad_windows", "reason": "vad_bounds"}


def test_evidence_mapping_word_clock_is_closed():
    assert transient_failure_evidence("word_clocks", "word_clock") == {"stage": "word_clocks", "reason": "word_clock"}


def test_evidence_mapping_unclassified_folds_to_unknown():
    assert transient_failure_evidence("assemble_words", "mystery") == {"stage": "assemble_words", "reason": "unknown"}


def test_evidence_mapping_non_worker_stage_is_none():
    assert transient_failure_evidence("provider", "empty_asr") is None


def test_evidence_mapping_accepts_the_enum_members_too():
    assert transient_failure_evidence("assemble_words", WorkerValidationReason.EMPTY_ASR) == {
        "stage": "assemble_words",
        "reason": "empty_asr",
    }


def test_shadow_worker_keeps_the_deliberate_handoff_comment():
    assert "Empty recognition takes its deliberate RecoveryWork handoff." in SHADOW_SOURCE


def test_shadow_worker_branch_handles_recovery_and_validation_failure_work():
    assert "isinstance(results[0], (RecoveryWork, ValidationFailureWork))" not in SHADOW_SOURCE or (
        "RecoveryWork, ValidationFailureWork" in SHADOW_SOURCE
    )


def test_pump_routes_recovery_work_to_a_quarantined_fail():
    assert "isinstance(result, RecoveryWork)" in PUMP_SOURCE


def test_pump_recovery_work_fail_pins_the_quarantine_flag():
    assert "quarantine=True," in PUMP_SOURCE


def test_pump_recovery_work_fail_pins_the_padded_empty_flag():
    assert "padded_retry_empty=result.padded_retry_empty," in PUMP_SOURCE


def test_pump_recovery_work_fail_pins_the_padded_token():
    assert "padded_retry=result.padded_retry," in PUMP_SOURCE


def test_pump_recovery_work_fail_pins_the_structured_fault():
    assert "worker_failure={'stage': 'assemble_words', 'reason': result.reason}," in PUMP_SOURCE


def test_pump_recovery_work_fail_passes_the_measured_vad_through():
    assert "measured_held_vad_speech_seconds=result.measured_held_vad_speech_seconds," in PUMP_SOURCE


def test_pump_recovery_work_fail_passes_the_receipt_through():
    assert "worker_vad_receipt=result.worker_vad_receipt," in PUMP_SOURCE


def test_pump_holds_work_defer_with_the_held_reason():
    assert "held_reason=result.reason or None," in PUMP_SOURCE
    assert "admission_refused=True," in PUMP_SOURCE


def test_pump_validation_failure_work_fail_carries_evidence_only():
    assert "worker_failure={'stage': result.stage, 'reason': result.reason}," in PUMP_SOURCE


def test_pump_failed_work_keeps_its_diagnosis_as_evidence():
    assert "worker_failure_evidence=result.worker_failure if isinstance(result, FailedWork) else None," in PUMP_SOURCE


def test_pump_success_routes_to_complete():
    assert "self.scheduler.complete, result, lease.token, time.time()" in PUMP_SOURCE


def test_pump_one_revoked_owner_never_suppresses_sibling_results():
    assert "lost.add(segment)" in PUMP_SOURCE
    assert "event=batch_completion outcome=retry exception_type=%s" in PUMP_SOURCE


def test_pump_reoffers_the_owner_after_publication():
    assert "drain_owner(owner_id)" in PUMP_SOURCE


def test_predicate_never_raises_on_the_recovery_failure_vocabulary():
    """A recovery-lane failure shape (stage outside worker stages) is not the ladder."""
    assert empty_ladder_recovery_failure({"stage": "provider", "reason": "empty_asr"}) is False
    assert empty_ladder_recovery_failure({"stage": "response_validation", "reason": "empty_asr"}) is False


def test_recovery_failure_reason_empty_asr_stays_a_distinct_surface():
    assert RecoveryFailureReason.EMPTY_ASR.value == "empty_asr"


def test_safety_net_default_reads_the_kill_switch_per_call():
    assert (
        "os.getenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')"
        in (Path(__file__).resolve().parents[2] / "config" / "batch_pipeline_empty_asr.py").read_text()
    )


def test_work_result_fields_are_untouched():
    import dataclasses

    from utils.batch_pipeline.contracts import WorkResult

    assert [f.name for f in dataclasses.fields(WorkResult)] == [
        "segment_id",
        "result_uri",
        "outcome",
        "language_receipt",
    ]


def test_error_site_field_emits_a_static_site_token():
    from utils.batch_pipeline.errors import error_site_field

    try:
        raise ValueError("probe")
    except ValueError as probe:
        site = error_site_field(probe)
    assert site.startswith(" site=")
    assert "probe" not in site
    assert ":" in site


def test_worker_vad_receipt_helper_is_read_from_contracts():
    assert "def vad_receipt(" in WORKER_SOURCE or "worker_vad_receipt=receipt" in WORKER_SOURCE


def test_rekor_of_empty_ladder_absent_from_recovery_steps():
    steps_source = (Path(__file__).resolve().parents[2] / "utils" / "batch_pipeline" / "recovery_steps.py").read_text()
    assert "event=batch_empty_ladder" not in steps_source


def test_rekor_of_empty_ladder_absent_from_recovery_recognizers():
    recognizers_source = (
        Path(__file__).resolve().parents[2] / "utils" / "batch_pipeline" / "recovery_recognizers.py"
    ).read_text()
    assert "event=batch_empty_ladder" not in recognizers_source


def test_rekor_of_empty_ladder_absent_from_recovery_disposition():
    disposition_source = (
        Path(__file__).resolve().parents[2] / "utils" / "batch_pipeline" / "recovery_disposition.py"
    ).read_text()
    assert "event=batch_empty_ladder" not in disposition_source


def test_rekor_of_empty_ladder_absent_from_worker_silence():
    silence_source = (
        Path(__file__).resolve().parents[2] / "utils" / "batch_pipeline" / "worker_silence.py"
    ).read_text()
    assert "event=batch_empty_ladder" not in silence_source


def test_rekor_of_empty_ladder_absent_from_quarantine_recovery():
    lane_source = (
        Path(__file__).resolve().parents[2] / "utils" / "batch_pipeline" / "quarantine_recovery.py"
    ).read_text()
    assert "event=batch_empty_ladder" not in lane_source


def test_rekor_of_empty_ladder_absent_from_pump():
    pump_source = (Path(__file__).resolve().parents[2] / "utils" / "batch_pipeline" / "pump.py").read_text()
    assert "event=batch_empty_ladder" not in pump_source


def test_rekor_of_empty_ladder_absent_from_shadow_worker():
    shadow_source = (Path(__file__).resolve().parents[2] / "utils" / "batch_pipeline" / "shadow_worker.py").read_text()
    assert "event=batch_empty_ladder" not in shadow_source


def test_rekor_of_empty_ladder_absent_from_projection_drain():
    drain_source = (
        Path(__file__).resolve().parents[2] / "utils" / "batch_pipeline" / "projection_drain.py"
    ).read_text()
    assert "event=batch_empty_ladder" not in drain_source


def test_rekor_of_empty_ladder_absent_from_intake():
    intake_source = (Path(__file__).resolve().parents[2] / "utils" / "batch_pipeline" / "intake.py").read_text()
    assert "event=batch_empty_ladder" not in intake_source


def test_rekor_of_empty_ladder_absent_from_merge():
    merge_source = (Path(__file__).resolve().parents[2] / "utils" / "batch_pipeline" / "merge.py").read_text()
    assert "event=batch_empty_ladder" not in merge_source


def test_rekor_of_empty_ladder_absent_from_admission():
    admission_source = (Path(__file__).resolve().parents[2] / "utils" / "batch_pipeline" / "admission.py").read_text()
    assert "event=batch_empty_ladder" not in admission_source


def test_rekor_of_empty_ladder_absent_from_live():
    live_source = (Path(__file__).resolve().parents[2] / "utils" / "batch_pipeline" / "live.py").read_text()
    assert "event=batch_empty_ladder" not in live_source


def test_rekor_of_empty_ladder_absent_from_control():
    control_source = (Path(__file__).resolve().parents[2] / "utils" / "batch_pipeline" / "control.py").read_text()
    assert "event=batch_empty_ladder" not in control_source


def test_rekor_of_empty_ladder_absent_from_retention():
    retention_source = (Path(__file__).resolve().parents[2] / "utils" / "batch_pipeline" / "retention.py").read_text()
    assert "event=batch_empty_ladder" not in retention_source


def test_rekor_of_empty_ladder_absent_from_word_validation():
    word_source = (Path(__file__).resolve().parents[2] / "utils" / "batch_pipeline" / "word_validation.py").read_text()
    assert "event=batch_empty_ladder" not in word_source


def test_rekor_of_empty_ladder_absent_from_gpu_overflow():
    overflow_source = (Path(__file__).resolve().parents[2] / "utils" / "batch_pipeline" / "gpu_overflow.py").read_text()
    assert "event=batch_empty_ladder" not in overflow_source


def test_rekor_of_empty_ladder_absent_from_capacity():
    capacity_source = (Path(__file__).resolve().parents[2] / "utils" / "batch_pipeline" / "capacity.py").read_text()
    assert "event=batch_empty_ladder" not in capacity_source


def test_rekor_of_empty_ladder_absent_from_artifacts():
    artifacts_source = (Path(__file__).resolve().parents[2] / "utils" / "batch_pipeline" / "artifacts.py").read_text()
    assert "event=batch_empty_ladder" not in artifacts_source


def test_rekor_of_empty_ladder_absent_from_projection():
    projection_source = (Path(__file__).resolve().parents[2] / "utils" / "batch_pipeline" / "projection.py").read_text()
    assert "event=batch_empty_ladder" not in projection_source
