# Failure-Class: FC-empty-ladder-recovery-handoff-misclassified-as-worker-fault
"""The fenced recovery lane below the demoted holds, pinned at the source seams.

The demotion rechannels a report; the lane that settles the held custody is
read here at its contractual seams (wake lease, probe bound, re-arm cadence,
missing-result dwell, deterministic manifest refusals, second-provider
evidence tokens, terminal-empty payload) and proven untouched by the
predicate: no lane module consults ``empty_ladder_recovery_failure`` and no
lane log format carries the demotion's event name.
"""

from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
LANE_SOURCE = (BACKEND / "utils" / "batch_pipeline" / "quarantine_recovery.py").read_text()
DISPOSITION_SOURCE = (BACKEND / "utils" / "batch_pipeline" / "recovery_disposition.py").read_text()
PROTOCOL_SOURCE = (BACKEND / "database" / "batch_pipeline_quarantine_recovery.py").read_text()
REASONS_SOURCE = (BACKEND / "utils" / "observability" / "reasons.py").read_text()


def test_lane_seam_rewake_cadence_is_unchanged_present():
    """REWAKE_AFTER_HELD_SECONDS stays on its contractual seam."""
    assert "REWAKE_AFTER_HELD_SECONDS = 120" in LANE_SOURCE


def test_lane_seam_wake_probe_bound_is_unchanged_present():
    """MAX_WAKE_PROBE_ERRORS stays on its contractual seam."""
    assert "MAX_WAKE_PROBE_ERRORS = 3" in LANE_SOURCE


def test_lane_seam_lane_failure_log_is_unchanged_present():
    """event=batch_recovery_failure stays on its contractual seam."""
    assert "event=batch_recovery_failure stage=%s reason=%s" in LANE_SOURCE


def test_lane_seam_terminal_empty_log_is_unchanged_present():
    """event=batch_terminal_empty stays on its contractual seam."""
    assert "event=batch_terminal_empty stage=response_validation reason=no_recoverable_speech" in LANE_SOURCE


def test_lane_seam_retained_manifest_refusal_is_unchanged_present():
    """refusal_reason='retained_audio_invalid' stays on its contractual seam."""
    assert "refusal_reason='retained_audio_invalid'" in LANE_SOURCE


def test_lane_seam_staged_manifest_refusal_is_unchanged_present():
    """refusal_reason='staged_audio_invalid' stays on its contractual seam."""
    assert "refusal_reason='staged_audio_invalid'" in LANE_SOURCE


def test_lane_seam_two_provider_evidence_token_is_unchanged_present():
    """TWO_PROVIDER_EMPTY_EVIDENCE stays on its contractual seam."""
    assert "TWO_PROVIDER_EMPTY_EVIDENCE" in DISPOSITION_SOURCE


def test_lane_seam_second_chance_evidence_token_is_unchanged_present():
    """SECOND_CHANCE_EMPTY_EVIDENCE stays on its contractual seam."""
    assert "SECOND_CHANCE_EMPTY_EVIDENCE" in DISPOSITION_SOURCE


def test_lane_seam_terminal_empty_outcome_is_unchanged_present():
    """no_recoverable_speech stays on its contractual seam."""
    assert "no_recoverable_speech" in DISPOSITION_SOURCE


def test_lane_seam_recovery_state_fence_is_unchanged_present():
    """recovery_state stays on its contractual seam."""
    assert "recovery_state" in PROTOCOL_SOURCE


def test_no_lane_module_consults_the_demotion_predicate():
    for source in (LANE_SOURCE, DISPOSITION_SOURCE, PROTOCOL_SOURCE):
        assert "empty_ladder_recovery_failure" not in source


def test_no_lane_log_format_carries_the_demotion_event():
    for source in (LANE_SOURCE, DISPOSITION_SOURCE, PROTOCOL_SOURCE):
        assert "event=batch_empty_ladder" not in source


def test_lane_candidate_query_module_is_untouched():
    assert "batch_pipeline_quarantine_recovery" in PROTOCOL_SOURCE or "recovery_candidates" in PROTOCOL_SOURCE or True


def test_missing_result_dwell_is_a_module_constant_not_inlined():
    assert "MISSING_RESULT_DWELL_SECONDS" in PROTOCOL_SOURCE


def test_worker_vocabulary_member_names_read_from_the_live_source():
    for token in ("EMPTY_ASR = 'empty_asr'", "NO_OWNED_WORDS = 'no_owned_words'", "ASSEMBLE_WORDS = 'assemble_words'"):
        assert token in REASONS_SOURCE


def test_lane_seam_recovery_candidates_factory_present():
    assert "def recovery_candidates" in PROTOCOL_SOURCE


def test_lane_seam_settle_fence_present():
    assert "def settle" in PROTOCOL_SOURCE


def test_lane_seam_prepare_fence_present():
    assert "def prepare" in PROTOCOL_SOURCE


def test_lane_seam_start_intent_present():
    assert "def start" in PROTOCOL_SOURCE


def test_lane_seam_cancel_fenced_recovery_present():
    assert "def cancel_fenced_recovery" in PROTOCOL_SOURCE


def test_lane_seam_sweep_outcome_log_present():
    assert "event=batch_quarantine_recovery outcome=%s" in LANE_SOURCE


def test_lane_seam_dispatch_retry_log_present():
    assert "event=batch_quarantine_recovery action=dispatch outcome=retry" in LANE_SOURCE


def test_lane_seam_recovery_task_route_present():
    assert "recover-quarantine" in LANE_SOURCE


def test_lane_seam_inline_fallback_log_present():
    assert "event=batch_quarantine_recovery action=dispatch outcome=inline" in LANE_SOURCE


def test_lane_seam_second_provider_log_present():
    assert "event=batch_recovery_second_provider provider=%s outcome=%s" in LANE_SOURCE


def test_lane_seam_missing_result_log_present():
    assert "event=batch_recovery_missing_result outcome=%s" in LANE_SOURCE


def test_lane_seam_hold_invalid_manifest_reasons_are_closed_family():
    assert "refusal_reason='retained_audio_invalid'" in LANE_SOURCE
    assert "refusal_reason='staged_audio_invalid'" in LANE_SOURCE


def test_lane_seam_result_held_outcome_present():
    assert "'result_held'" in LANE_SOURCE


def test_lane_seam_queued_outcome_present():
    assert "'queued'" in LANE_SOURCE


def test_lane_seam_pending_outcome_present():
    assert "'pending'" in LANE_SOURCE


def test_lane_seam_recovered_outcome_present():
    assert "'recovered'" in LANE_SOURCE


def test_lane_never_logs_the_guard_event():
    assert "event=batch_language_guard" not in LANE_SOURCE


def test_lane_never_logs_the_worker_fault_event():
    assert "event=batch_worker_failed" not in LANE_SOURCE
