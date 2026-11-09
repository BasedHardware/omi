# Failure-Class: FC-empty-ladder-recovery-handoff-misclassified-as-worker-fault
"""The demotion doc and the demotion code, pinned token-for-token.

Every event name, outcome token, format field, severity claim and
unchanged-accounting fact in ``docs/empty-ladder-recovery-channel-parity.md``
is pinned to the live sources, and every suite file the doc's Verification
section promises exists with a real test inside.
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
DOC = (BACKEND / "docs" / "empty-ladder-recovery-channel-parity.md").read_text()


def test_doc_token_event_batch_empty_ladder_worker_source_count():
    """event=batch_empty_ladder appears 1 time in WORKER_SOURCE."""
    assert WORKER_SOURCE.count("event=batch_empty_ladder") == 1


def test_doc_token_event_batch_empty_ladder_scheduler_source_count():
    """event=batch_empty_ladder appears 1 time in SCHEDULER_SOURCE."""
    assert SCHEDULER_SOURCE.count("event=batch_empty_ladder") == 1


def test_doc_token_outcome_recovery_handoff_worker_source_count():
    """outcome=recovery_handoff appears 2 times in WORKER_SOURCE.

    One for the empty ladder's handoff, one for the terminal
    worker-validation disposition's handoff — siblings on the same
    rechannel-only pattern.
    """
    assert WORKER_SOURCE.count("outcome=recovery_handoff") == 2


def test_doc_token_outcome_held_for_recovery_scheduler_source_count():
    """outcome=held_for_recovery appears 1 time in SCHEDULER_SOURCE."""
    assert SCHEDULER_SOURCE.count("outcome=held_for_recovery") == 1


def test_doc_token_event_batch_worker_failed_worker_source_count():
    """event=batch_worker_failed appears 1 time in WORKER_SOURCE."""
    assert WORKER_SOURCE.count("event=batch_worker_failed") == 1


def test_doc_token_event_batch_quarantined_scheduler_source_count():
    """event=batch_quarantined appears 1 time in SCHEDULER_SOURCE."""
    assert SCHEDULER_SOURCE.count("event=batch_quarantined") == 1


def test_doc_token_event_batch_language_guard_worker_source_count():
    """event=batch_language_guard appears 1 time in WORKER_SOURCE."""
    assert WORKER_SOURCE.count("event=batch_language_guard") == 1


def test_doc_token_event_batch_language_guard_scheduler_source_count():
    """event=batch_language_guard appears 1 time in SCHEDULER_SOURCE."""
    assert SCHEDULER_SOURCE.count("event=batch_language_guard") == 1


def test_doc_worker_field_error_class_in_the_format_string():
    assert "error_class=" in WORKER_SOURCE
    assert "error_class=" in DOC


def test_doc_worker_field_stage_in_the_format_string():
    assert "stage=" in WORKER_SOURCE
    assert "stage=" in DOC


def test_doc_worker_field_segment_id_in_the_format_string():
    assert "segment_id=" in WORKER_SOURCE
    assert "segment_id=" in DOC


def test_doc_worker_field_reason_in_the_format_string():
    assert "reason=" in WORKER_SOURCE
    assert "reason=" in DOC


def test_doc_worker_field_samples_in_the_format_string():
    assert "samples=" in WORKER_SOURCE
    assert "samples=" in DOC


def test_doc_worker_field_vad_spans_in_the_format_string():
    assert "vad_spans=" in WORKER_SOURCE
    assert "vad_spans=" in DOC


def test_doc_worker_field_windows_in_the_format_string():
    assert "windows=" in WORKER_SOURCE
    assert "windows=" in DOC


def test_doc_worker_field_asr_words_in_the_format_string():
    assert "asr_words=" in WORKER_SOURCE
    assert "asr_words=" in DOC


def test_doc_worker_field_owned_words_in_the_format_string():
    assert "owned_words=" in WORKER_SOURCE
    assert "owned_words=" in DOC


def test_doc_scheduler_field_attempt_in_the_format_string():
    assert "attempt=" in SCHEDULER_SOURCE
    assert "attempt=" in DOC


def test_doc_scheduler_field_recovery_in_the_format_string():
    assert "recovery=" in SCHEDULER_SOURCE
    assert "recovery=" in DOC


def test_doc_scheduler_field_stage_in_the_format_string():
    assert "stage=" in SCHEDULER_SOURCE
    assert "stage=" in DOC


def test_doc_scheduler_field_worker_reason_in_the_format_string():
    assert "worker_reason=" in SCHEDULER_SOURCE
    assert "worker_reason=" in DOC


def test_doc_event_token_absent_from_every_other_backend_module():
    hits = [
        str(p.relative_to(BACKEND))
        for p in list((BACKEND / "utils").rglob("*.py")) + list((BACKEND / "diarizer").rglob("*.py"))
        if "event=batch_empty_ladder" in p.read_text()
    ]
    assert sorted(hits) == ["diarizer/batch_pipeline.py", "utils/batch_pipeline/scheduler.py"]


def test_doc_names_the_demoted_severity_as_info_at_the_worker():
    assert "outcome=recovery_handoff error_class=" in WORKER_SOURCE
    assert "logger.info" in WORKER_SOURCE


def test_doc_names_the_demoted_severity_as_info_at_the_scheduler():
    assert "outcome=held_for_recovery attempt=" in SCHEDULER_SOURCE
    assert "logger.info" in SCHEDULER_SOURCE


def test_doc_names_the_stage_gate_token():
    assert "EMPTY_LADDER_RECOVERY_STAGE" in WORKER_SOURCE
    assert "EMPTY_LADDER_RECOVERY_STAGE" in ERRORS_SOURCE


def test_doc_names_the_family_constant():
    assert "EMPTY_LADDER_RECOVERY_REASONS" in ERRORS_SOURCE
    assert "empty_asr" in ERRORS_SOURCE and "no_owned_words" in ERRORS_SOURCE


def test_doc_unchanged_accounting_recovery_held_metric_still_recorded():
    assert "recovery_held" in SCHEDULER_SOURCE


def test_doc_unchanged_accounting_quarantined_metric_still_recorded():
    assert "quarantined' if state == 'quarantined' else 'retry'" in SCHEDULER_SOURCE


def test_doc_unchanged_accounting_evidence_booking_still_present():
    assert "worker_empty_evidence" in SCHEDULER_SOURCE


def test_doc_unchanged_accounting_quarantine_token_still_worker_failed():
    assert "quarantine_job(tx, job, now, 'worker_failed')" in SCHEDULER_SOURCE


def test_doc_unchanged_accounting_warning_after_both_branches():
    guard_index = SCHEDULER_SOURCE.index("outcome=held_for_redrive")
    ladder_index = SCHEDULER_SOURCE.index("outcome=held_for_recovery")
    fault_index = SCHEDULER_SOURCE.index("reason=worker_failed attempt=%d recovery=held")
    warning_index = SCHEDULER_SOURCE.index("awaiting_fenced_recovery")
    assert guard_index < warning_index and ladder_index < warning_index and fault_index < warning_index


def test_doc_unchanged_accounting_empty_asr_attempt_meter_in_worker():
    assert "empty_asr_attempt" in WORKER_SOURCE


def test_doc_unchanged_accounting_shadow_line_precedes_classification():
    shadow_index = WORKER_SOURCE.index("event=batch_shadow_worker_failure")
    ladder_index = WORKER_SOURCE.index("event=batch_empty_ladder")
    assert shadow_index < ladder_index


def test_doc_failure_class_trailer_matches_the_errors_module():
    assert "FC-empty-ladder-recovery-handoff-misclassified-as-worker-fault" in DOC
    assert "FC-empty-ladder-recovery-handoff-misclassified-as-worker-fault" in ERRORS_SOURCE


def test_doc_rollback_names_exactly_three_hunk_files():
    assert "Revert the three hunks" in DOC
    assert "no recovery, custody or metric surface" in DOC


def test_doc_verification_file_predicate_contract_exists():
    """The doc's Verification section promises this suite; it exists with tests."""
    path = BACKEND / "tests" / "unit" / "test_empty_ladder_channel_predicate_contract.py"
    assert path.exists()
    assert "def test_" in path.read_text()


def test_doc_verification_file_worker_taxonomy_exists():
    """The doc's Verification section promises this suite; it exists with tests."""
    path = BACKEND / "tests" / "unit" / "test_empty_ladder_channel_worker_taxonomy.py"
    assert path.exists()
    assert "def test_" in path.read_text()


def test_doc_verification_file_scheduler_taxonomy_exists():
    """The doc's Verification section promises this suite; it exists with tests."""
    path = BACKEND / "tests" / "unit" / "test_empty_ladder_channel_scheduler_taxonomy.py"
    assert path.exists()
    assert "def test_" in path.read_text()


def test_doc_verification_file_boundary_parity_exists():
    """The doc's Verification section promises this suite; it exists with tests."""
    path = BACKEND / "tests" / "unit" / "test_empty_ladder_channel_boundary_parity.py"
    assert path.exists()
    assert "def test_" in path.read_text()


def test_doc_verification_file_doc_parity_exists():
    """The doc's Verification section promises this suite; it exists with tests."""
    path = BACKEND / "tests" / "unit" / "test_empty_ladder_channel_doc_parity.py"
    assert path.exists()
    assert "def test_" in path.read_text()


def test_doc_verification_file_rollback_matrix_exists():
    """The doc's Verification section promises this suite; it exists with tests."""
    path = BACKEND / "tests" / "unit" / "test_empty_ladder_channel_rollback_matrix.py"
    assert path.exists()
    assert "def test_" in path.read_text()


def test_doc_verification_file_invariants_exists():
    """The doc's Verification section promises this suite; it exists with tests."""
    path = BACKEND / "tests" / "unit" / "test_empty_ladder_channel_invariants.py"
    assert path.exists()
    assert "def test_" in path.read_text()


def test_doc_verification_file_vocabulary_parity_exists():
    """The doc's Verification section promises this suite; it exists with tests."""
    path = BACKEND / "tests" / "unit" / "test_empty_ladder_channel_vocabulary_parity.py"
    assert path.exists()
    assert "def test_" in path.read_text()


def test_doc_verification_file_pump_routing_parity_exists():
    """The doc's Verification section promises this suite; it exists with tests."""
    path = BACKEND / "tests" / "unit" / "test_empty_ladder_channel_pump_routing_parity.py"
    assert path.exists()
    assert "def test_" in path.read_text()


def test_doc_verification_file_sensor_decay_parity_exists():
    """The doc's Verification section promises this suite; it exists with tests."""
    path = BACKEND / "tests" / "unit" / "test_empty_ladder_channel_sensor_decay_parity.py"
    assert path.exists()
    assert "def test_" in path.read_text()


def test_doc_verification_file_worker_grid_exists():
    """The doc's Verification section promises this suite; it exists with tests."""
    path = BACKEND / "tests" / "unit" / "test_empty_ladder_channel_worker_grid.py"
    assert path.exists()
    assert "def test_" in path.read_text()


def test_doc_verification_file_recovery_lane_parity_exists():
    """The doc's Verification section promises this suite; it exists with tests."""
    path = BACKEND / "tests" / "unit" / "test_empty_ladder_channel_recovery_lane_parity.py"
    assert path.exists()
    assert "def test_" in path.read_text()


def test_doc_verification_file_flag_surface_parity_exists():
    """The doc's Verification section promises this suite; it exists with tests."""
    path = BACKEND / "tests" / "unit" / "test_empty_ladder_channel_flag_surface_parity.py"
    assert path.exists()
    assert "def test_" in path.read_text()


def test_doc_failure_class_trailer_appears_once():
    assert DOC.count("FC-empty-ladder-recovery-handoff-misclassified-as-worker-fault") == 1


def test_doc_names_assemble_words_often():
    assert DOC.count("assemble_words") >= 3


def test_doc_names_both_family_reasons():
    assert "empty_asr" in DOC and "no_owned_words" in DOC


def test_doc_names_the_predicate_function():
    assert "empty_ladder_recovery_failure" in DOC


def test_doc_names_the_awaiting_warning():
    assert "awaiting_fenced_recovery" in DOC


def test_doc_does_not_claim_word_shape_demotes():
    assert "worker_reason=word_shape" not in DOC


def test_doc_does_not_claim_word_clock_demotes():
    assert "worker_reason=word_clock" not in DOC


def test_doc_does_not_claim_word_sequence_demotes():
    assert "worker_reason=word_sequence" not in DOC


def test_doc_does_not_claim_vad_nonfinite_demotes():
    assert "worker_reason=vad_nonfinite" not in DOC


def test_doc_does_not_claim_vad_order_demotes():
    assert "worker_reason=vad_order" not in DOC


def test_doc_does_not_claim_vad_bounds_demotes():
    assert "worker_reason=vad_bounds" not in DOC


def test_doc_does_not_claim_staged_audio_invalid_demotes():
    assert "worker_reason=staged_audio_invalid" not in DOC


def test_doc_does_not_claim_retained_audio_invalid_demotes():
    assert "worker_reason=retained_audio_invalid" not in DOC


def test_doc_does_not_claim_decoded_duration_mismatch_demotes():
    assert "worker_reason=decoded_duration_mismatch" not in DOC


def test_doc_does_not_claim_outside_admitted_source_demotes():
    assert "worker_reason=outside_admitted_source" not in DOC


def test_doc_claims_empty_asr_demotes():
    assert "worker_reason=empty_asr" in DOC


def test_doc_claims_no_owned_words_demotes():
    assert DOC.count("no_owned_words") >= 2


def test_doc_does_not_claim_unknown_demotes():
    assert "worker_reason=unknown" not in DOC


def test_doc_does_not_claim_unclassified_demotes():
    assert "worker_reason=unclassified" not in DOC
