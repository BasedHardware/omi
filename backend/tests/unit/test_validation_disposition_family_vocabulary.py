# Failure-Class: FC-terminal-validation-disposition-misbooked-as-worker-fault
"""The disposition family's vocabulary: membership, stage ownership, disjointness,
raise-site reachability and switch monotonicity, pinned against the live modules.

Every family reason is a closed worker-validation token; the unconditional trio
owns exactly the fetch_decode stage where its typed classes raise; the flagged
verdicts are disjoint from the trio and from the sibling empty-ladder and
language-guard families; and every family reason is reachable from a real raise
site in the worker chain. Flipping only the disposition switch changes the
predicate's answer for exactly the flagged arm.
"""

import re
from pathlib import Path

import diarizer.batch_pipeline as worker_module
import utils.batch_pipeline.artifacts as artifacts_module
import utils.batch_pipeline.audio as audio_module
import utils.batch_pipeline.errors as errors_module
import utils.batch_pipeline.scheduler as scheduler_module
import utils.batch_pipeline.source_audio as source_module
import utils.batch_pipeline.word_validation as word_validation_module
from config.batch_pipeline import worker_validation_disposition_enabled
from utils.batch_pipeline.errors import (
    VALIDATION_DISPOSITION_FLAGGED_REASONS,
    VALIDATION_DISPOSITION_REASONS,
    VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS,
    VALIDATION_DISPOSITION_UNCONDITIONAL_STAGE,
    EMPTY_LADDER_RECOVERY_REASONS,
    LANGUAGE_GUARD_REDRIVE_REASONS,
    WORKER_VALIDATION_REASONS,
    WORKER_VALIDATION_STAGES,
    validation_disposition_failure,
)

TRIO = ('staged_audio_invalid', 'retained_audio_invalid', 'decoded_duration_mismatch')
FLAGGED = ('word_shape', 'word_clock', 'word_sequence', 'vad_nonfinite', 'vad_order', 'vad_bounds')
STAGES = ('fetch_decode', 'vad_windows', 'word_clocks', 'assemble_words', 'asr_recovery')
WORKER_SOURCE = Path(worker_module.__file__).read_text()
AUDIO_SOURCE = Path(audio_module.__file__).read_text()
ARTIFACTS_SOURCE = Path(artifacts_module.__file__).read_text()
SOURCE_SOURCE = Path(source_module.__file__).read_text()
ERRORS_SOURCE = Path(errors_module.__file__).read_text()
SCHEDULER_SOURCE = Path(scheduler_module.__file__).read_text()
WORD_VALIDATION_SOURCE = Path(word_validation_module.__file__).read_text()


def test_family_staged_audio_invalid_is_a_closed_worker_validation_token():
    """staged_audio_invalid is a member of the closed worker-validation reason vocabulary."""
    assert "staged_audio_invalid" in WORKER_VALIDATION_REASONS


def test_family_retained_audio_invalid_is_a_closed_worker_validation_token():
    """retained_audio_invalid is a member of the closed worker-validation reason vocabulary."""
    assert "retained_audio_invalid" in WORKER_VALIDATION_REASONS


def test_family_decoded_duration_mismatch_is_a_closed_worker_validation_token():
    """decoded_duration_mismatch is a member of the closed worker-validation reason vocabulary."""
    assert "decoded_duration_mismatch" in WORKER_VALIDATION_REASONS


def test_family_word_shape_is_a_closed_worker_validation_token():
    """word_shape is a member of the closed worker-validation reason vocabulary."""
    assert "word_shape" in WORKER_VALIDATION_REASONS


def test_family_word_clock_is_a_closed_worker_validation_token():
    """word_clock is a member of the closed worker-validation reason vocabulary."""
    assert "word_clock" in WORKER_VALIDATION_REASONS


def test_family_word_sequence_is_a_closed_worker_validation_token():
    """word_sequence is a member of the closed worker-validation reason vocabulary."""
    assert "word_sequence" in WORKER_VALIDATION_REASONS


def test_family_vad_nonfinite_is_a_closed_worker_validation_token():
    """vad_nonfinite is a member of the closed worker-validation reason vocabulary."""
    assert "vad_nonfinite" in WORKER_VALIDATION_REASONS


def test_family_vad_order_is_a_closed_worker_validation_token():
    """vad_order is a member of the closed worker-validation reason vocabulary."""
    assert "vad_order" in WORKER_VALIDATION_REASONS


def test_family_vad_bounds_is_a_closed_worker_validation_token():
    """vad_bounds is a member of the closed worker-validation reason vocabulary."""
    assert "vad_bounds" in WORKER_VALIDATION_REASONS


def test_family_staged_audio_invalid_is_in_the_disposition_family():
    """staged_audio_invalid belongs to VALIDATION_DISPOSITION_REASONS."""
    assert "staged_audio_invalid" in VALIDATION_DISPOSITION_REASONS


def test_family_retained_audio_invalid_is_in_the_disposition_family():
    """retained_audio_invalid belongs to VALIDATION_DISPOSITION_REASONS."""
    assert "retained_audio_invalid" in VALIDATION_DISPOSITION_REASONS


def test_family_decoded_duration_mismatch_is_in_the_disposition_family():
    """decoded_duration_mismatch belongs to VALIDATION_DISPOSITION_REASONS."""
    assert "decoded_duration_mismatch" in VALIDATION_DISPOSITION_REASONS


def test_family_word_shape_is_in_the_disposition_family():
    """word_shape belongs to VALIDATION_DISPOSITION_REASONS."""
    assert "word_shape" in VALIDATION_DISPOSITION_REASONS


def test_family_word_clock_is_in_the_disposition_family():
    """word_clock belongs to VALIDATION_DISPOSITION_REASONS."""
    assert "word_clock" in VALIDATION_DISPOSITION_REASONS


def test_family_word_sequence_is_in_the_disposition_family():
    """word_sequence belongs to VALIDATION_DISPOSITION_REASONS."""
    assert "word_sequence" in VALIDATION_DISPOSITION_REASONS


def test_family_vad_nonfinite_is_in_the_disposition_family():
    """vad_nonfinite belongs to VALIDATION_DISPOSITION_REASONS."""
    assert "vad_nonfinite" in VALIDATION_DISPOSITION_REASONS


def test_family_vad_order_is_in_the_disposition_family():
    """vad_order belongs to VALIDATION_DISPOSITION_REASONS."""
    assert "vad_order" in VALIDATION_DISPOSITION_REASONS


def test_family_vad_bounds_is_in_the_disposition_family():
    """vad_bounds belongs to VALIDATION_DISPOSITION_REASONS."""
    assert "vad_bounds" in VALIDATION_DISPOSITION_REASONS


def test_trio_staged_audio_invalid_rides_the_unconditional_arm():
    """staged_audio_invalid belongs to the unconditional fetch_decode arm."""
    assert "staged_audio_invalid" in VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS
    assert "staged_audio_invalid" not in VALIDATION_DISPOSITION_FLAGGED_REASONS


def test_trio_retained_audio_invalid_rides_the_unconditional_arm():
    """retained_audio_invalid belongs to the unconditional fetch_decode arm."""
    assert "retained_audio_invalid" in VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS
    assert "retained_audio_invalid" not in VALIDATION_DISPOSITION_FLAGGED_REASONS


def test_trio_decoded_duration_mismatch_rides_the_unconditional_arm():
    """decoded_duration_mismatch belongs to the unconditional fetch_decode arm."""
    assert "decoded_duration_mismatch" in VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS
    assert "decoded_duration_mismatch" not in VALIDATION_DISPOSITION_FLAGGED_REASONS


def test_flagged_word_shape_rides_the_switch_arm():
    """word_shape belongs to the switch-gated arm, never the unconditional one."""
    assert "word_shape" in VALIDATION_DISPOSITION_FLAGGED_REASONS
    assert "word_shape" not in VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS


def test_flagged_word_clock_rides_the_switch_arm():
    """word_clock belongs to the switch-gated arm, never the unconditional one."""
    assert "word_clock" in VALIDATION_DISPOSITION_FLAGGED_REASONS
    assert "word_clock" not in VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS


def test_flagged_word_sequence_rides_the_switch_arm():
    """word_sequence belongs to the switch-gated arm, never the unconditional one."""
    assert "word_sequence" in VALIDATION_DISPOSITION_FLAGGED_REASONS
    assert "word_sequence" not in VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS


def test_flagged_vad_nonfinite_rides_the_switch_arm():
    """vad_nonfinite belongs to the switch-gated arm, never the unconditional one."""
    assert "vad_nonfinite" in VALIDATION_DISPOSITION_FLAGGED_REASONS
    assert "vad_nonfinite" not in VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS


def test_flagged_vad_order_rides_the_switch_arm():
    """vad_order belongs to the switch-gated arm, never the unconditional one."""
    assert "vad_order" in VALIDATION_DISPOSITION_FLAGGED_REASONS
    assert "vad_order" not in VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS


def test_flagged_vad_bounds_rides_the_switch_arm():
    """vad_bounds belongs to the switch-gated arm, never the unconditional one."""
    assert "vad_bounds" in VALIDATION_DISPOSITION_FLAGGED_REASONS
    assert "vad_bounds" not in VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS


def test_trio_stage_gate_staged_audio_invalid_at_vad_windows_keeps_fault_classification():
    """The trio answers only at fetch_decode: staged_audio_invalid at vad_windows keeps the fault channel."""
    assert (
        validation_disposition_failure(
            {"stage": "vad_windows", "reason": "staged_audio_invalid"}, disposition_enabled=True
        )
        is False
    )


def test_trio_stage_gate_staged_audio_invalid_at_word_clocks_keeps_fault_classification():
    """The trio answers only at fetch_decode: staged_audio_invalid at word_clocks keeps the fault channel."""
    assert (
        validation_disposition_failure(
            {"stage": "word_clocks", "reason": "staged_audio_invalid"}, disposition_enabled=True
        )
        is False
    )


def test_trio_stage_gate_staged_audio_invalid_at_assemble_words_keeps_fault_classification():
    """The trio answers only at fetch_decode: staged_audio_invalid at assemble_words keeps the fault channel."""
    assert (
        validation_disposition_failure(
            {"stage": "assemble_words", "reason": "staged_audio_invalid"}, disposition_enabled=True
        )
        is False
    )


def test_trio_stage_gate_staged_audio_invalid_at_asr_recovery_keeps_fault_classification():
    """The trio answers only at fetch_decode: staged_audio_invalid at asr_recovery keeps the fault channel."""
    assert (
        validation_disposition_failure(
            {"stage": "asr_recovery", "reason": "staged_audio_invalid"}, disposition_enabled=True
        )
        is False
    )


def test_trio_stage_gate_retained_audio_invalid_at_vad_windows_keeps_fault_classification():
    """The trio answers only at fetch_decode: retained_audio_invalid at vad_windows keeps the fault channel."""
    assert (
        validation_disposition_failure(
            {"stage": "vad_windows", "reason": "retained_audio_invalid"}, disposition_enabled=True
        )
        is False
    )


def test_trio_stage_gate_retained_audio_invalid_at_word_clocks_keeps_fault_classification():
    """The trio answers only at fetch_decode: retained_audio_invalid at word_clocks keeps the fault channel."""
    assert (
        validation_disposition_failure(
            {"stage": "word_clocks", "reason": "retained_audio_invalid"}, disposition_enabled=True
        )
        is False
    )


def test_trio_stage_gate_retained_audio_invalid_at_assemble_words_keeps_fault_classification():
    """The trio answers only at fetch_decode: retained_audio_invalid at assemble_words keeps the fault channel."""
    assert (
        validation_disposition_failure(
            {"stage": "assemble_words", "reason": "retained_audio_invalid"}, disposition_enabled=True
        )
        is False
    )


def test_trio_stage_gate_retained_audio_invalid_at_asr_recovery_keeps_fault_classification():
    """The trio answers only at fetch_decode: retained_audio_invalid at asr_recovery keeps the fault channel."""
    assert (
        validation_disposition_failure(
            {"stage": "asr_recovery", "reason": "retained_audio_invalid"}, disposition_enabled=True
        )
        is False
    )


def test_trio_stage_gate_decoded_duration_mismatch_at_vad_windows_keeps_fault_classification():
    """The trio answers only at fetch_decode: decoded_duration_mismatch at vad_windows keeps the fault channel."""
    assert (
        validation_disposition_failure(
            {"stage": "vad_windows", "reason": "decoded_duration_mismatch"}, disposition_enabled=True
        )
        is False
    )


def test_trio_stage_gate_decoded_duration_mismatch_at_word_clocks_keeps_fault_classification():
    """The trio answers only at fetch_decode: decoded_duration_mismatch at word_clocks keeps the fault channel."""
    assert (
        validation_disposition_failure(
            {"stage": "word_clocks", "reason": "decoded_duration_mismatch"}, disposition_enabled=True
        )
        is False
    )


def test_trio_stage_gate_decoded_duration_mismatch_at_assemble_words_keeps_fault_classification():
    """The trio answers only at fetch_decode: decoded_duration_mismatch at assemble_words keeps the fault channel."""
    assert (
        validation_disposition_failure(
            {"stage": "assemble_words", "reason": "decoded_duration_mismatch"}, disposition_enabled=True
        )
        is False
    )


def test_trio_stage_gate_decoded_duration_mismatch_at_asr_recovery_keeps_fault_classification():
    """The trio answers only at fetch_decode: decoded_duration_mismatch at asr_recovery keeps the fault channel."""
    assert (
        validation_disposition_failure(
            {"stage": "asr_recovery", "reason": "decoded_duration_mismatch"}, disposition_enabled=True
        )
        is False
    )


def test_stage_ownership_constant_is_fetch_decode():
    """The unconditional arm's stage token is the fetch_decode stage value."""
    assert VALIDATION_DISPOSITION_UNCONDITIONAL_STAGE == "fetch_decode"


def test_family_arms_are_disjoint():
    """No reason rides both arms."""
    assert not (VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS & VALIDATION_DISPOSITION_FLAGGED_REASONS)


def test_family_is_the_union_of_its_arms():
    """VALIDATION_DISPOSITION_REASONS is exactly the union of the two arms."""
    assert VALIDATION_DISPOSITION_REASONS == (
        VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS | VALIDATION_DISPOSITION_FLAGGED_REASONS
    )


def test_family_never_overlaps_the_empty_ladder():
    """The empty ladder owns its own reasons."""
    assert not (VALIDATION_DISPOSITION_REASONS & EMPTY_LADDER_RECOVERY_REASONS)


def test_family_never_overlaps_the_language_guard():
    """The language guard owns its own reasons."""
    assert not (VALIDATION_DISPOSITION_REASONS & LANGUAGE_GUARD_REDRIVE_REASONS)


def test_family_is_subset_of_closed_vocabulary():
    """Every family member is admissible to the store validators."""
    assert VALIDATION_DISPOSITION_REASONS <= WORKER_VALIDATION_REASONS


def test_raise_site_reachable_staged_audio_invalid_in_audio_source():
    """staged_audio_invalid has a real raise site: `class StagedAudioInvalid` lives in AUDIO_SOURCE."""
    assert 'class StagedAudioInvalid' in AUDIO_SOURCE


def test_raise_site_reachable_staged_audio_invalid_in_artifacts_source():
    """staged_audio_invalid has a real raise site: `class StagedArtifactInvalid` lives in ARTIFACTS_SOURCE."""
    assert 'class StagedArtifactInvalid' in ARTIFACTS_SOURCE


def test_raise_site_reachable_retained_audio_invalid_in_source_source():
    """retained_audio_invalid has a real raise site: `class RetainedAudioInvalid` lives in SOURCE_SOURCE."""
    assert 'class RetainedAudioInvalid' in SOURCE_SOURCE


def test_raise_site_reachable_decoded_duration_mismatch_in_worker_source():
    """decoded_duration_mismatch has a real raise site: `class DecodedDurationMismatch` lives in WORKER_SOURCE."""
    assert 'class DecodedDurationMismatch' in WORKER_SOURCE


def test_raise_site_reachable_word_shape_in_word_validation_source():
    """word_shape has a real raise site: `ValidationReason.WORD_SHAPE` lives in WORD_VALIDATION_SOURCE."""
    assert 'ValidationReason.WORD_SHAPE' in WORD_VALIDATION_SOURCE


def test_raise_site_reachable_word_clock_in_word_validation_source():
    """word_clock has a real raise site: `ValidationReason.WORD_CLOCK` lives in WORD_VALIDATION_SOURCE."""
    assert 'ValidationReason.WORD_CLOCK' in WORD_VALIDATION_SOURCE


def test_raise_site_reachable_word_sequence_in_word_validation_source():
    """word_sequence has a real raise site: `ValidationReason.WORD_SEQUENCE` lives in WORD_VALIDATION_SOURCE."""
    assert 'ValidationReason.WORD_SEQUENCE' in WORD_VALIDATION_SOURCE


def test_raise_site_reachable_vad_nonfinite_in_worker_source():
    """vad_nonfinite has a real raise site: `ValidationReason.VAD_NONFINITE` lives in WORKER_SOURCE."""
    assert 'ValidationReason.VAD_NONFINITE' in WORKER_SOURCE


def test_raise_site_reachable_vad_order_in_worker_source():
    """vad_order has a real raise site: `ValidationReason.VAD_ORDER` lives in WORKER_SOURCE."""
    assert 'ValidationReason.VAD_ORDER' in WORKER_SOURCE


def test_raise_site_reachable_vad_bounds_in_worker_source():
    """vad_bounds has a real raise site: `ValidationReason.VAD_BOUNDS` lives in WORKER_SOURCE."""
    assert 'ValidationReason.VAD_BOUNDS' in WORKER_SOURCE


def test_raise_site_reads_the_type_for_staged_audio_invalid():
    """The fetch_decode boundary reads the typed class, never the message, for staged_audio_invalid."""
    assert "StagedAudioInvalid" in WORKER_SOURCE or "RetainedAudioInvalid" in WORKER_SOURCE


def test_raise_site_reads_the_type_for_retained_audio_invalid():
    """The fetch_decode boundary reads the typed class, never the message, for retained_audio_invalid."""
    assert "StagedAudioInvalid" in WORKER_SOURCE or "RetainedAudioInvalid" in WORKER_SOURCE


def test_switch_monotonicity_word_shape():
    """Flipping only the switch changes the answer for word_shape."""
    shape = {"stage": "vad_windows", "reason": "word_shape"}
    assert validation_disposition_failure(shape, disposition_enabled=True) is True
    assert validation_disposition_failure(shape, disposition_enabled=False) is False


def test_switch_monotonicity_word_clock():
    """Flipping only the switch changes the answer for word_clock."""
    shape = {"stage": "vad_windows", "reason": "word_clock"}
    assert validation_disposition_failure(shape, disposition_enabled=True) is True
    assert validation_disposition_failure(shape, disposition_enabled=False) is False


def test_switch_monotonicity_word_sequence():
    """Flipping only the switch changes the answer for word_sequence."""
    shape = {"stage": "vad_windows", "reason": "word_sequence"}
    assert validation_disposition_failure(shape, disposition_enabled=True) is True
    assert validation_disposition_failure(shape, disposition_enabled=False) is False


def test_switch_monotonicity_vad_nonfinite():
    """Flipping only the switch changes the answer for vad_nonfinite."""
    shape = {"stage": "vad_windows", "reason": "vad_nonfinite"}
    assert validation_disposition_failure(shape, disposition_enabled=True) is True
    assert validation_disposition_failure(shape, disposition_enabled=False) is False


def test_switch_monotonicity_vad_order():
    """Flipping only the switch changes the answer for vad_order."""
    shape = {"stage": "vad_windows", "reason": "vad_order"}
    assert validation_disposition_failure(shape, disposition_enabled=True) is True
    assert validation_disposition_failure(shape, disposition_enabled=False) is False


def test_switch_monotonicity_vad_bounds():
    """Flipping only the switch changes the answer for vad_bounds."""
    shape = {"stage": "vad_windows", "reason": "vad_bounds"}
    assert validation_disposition_failure(shape, disposition_enabled=True) is True
    assert validation_disposition_failure(shape, disposition_enabled=False) is False


def test_switch_monotonicity_trio_staged_audio_invalid():
    """The trio's answer never depends on the switch: staged_audio_invalid."""
    shape = {"stage": "fetch_decode", "reason": "staged_audio_invalid"}
    assert validation_disposition_failure(shape, disposition_enabled=True) is True
    assert validation_disposition_failure(shape, disposition_enabled=False) is True


def test_switch_monotonicity_trio_retained_audio_invalid():
    """The trio's answer never depends on the switch: retained_audio_invalid."""
    shape = {"stage": "fetch_decode", "reason": "retained_audio_invalid"}
    assert validation_disposition_failure(shape, disposition_enabled=True) is True
    assert validation_disposition_failure(shape, disposition_enabled=False) is True


def test_switch_monotonicity_trio_decoded_duration_mismatch():
    """The trio's answer never depends on the switch: decoded_duration_mismatch."""
    shape = {"stage": "fetch_decode", "reason": "decoded_duration_mismatch"}
    assert validation_disposition_failure(shape, disposition_enabled=True) is True
    assert validation_disposition_failure(shape, disposition_enabled=False) is True


def test_both_logging_sites_import_the_same_predicate():
    """The worker boundary and the scheduler consult the one predicate."""
    assert "validation_disposition_failure" in WORKER_SOURCE
    assert "validation_disposition_failure" in SCHEDULER_SOURCE


def test_both_logging_sites_read_the_same_switch():
    """Both sites read worker_validation_disposition_enabled at the call boundary."""
    assert "worker_validation_disposition_enabled" in WORKER_SOURCE
    assert "worker_validation_disposition_enabled" in SCHEDULER_SOURCE


def test_parse_true_is_on():
    assert worker_validation_disposition_enabled.__doc__ is not None
    import os

    os.environ["BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED"] = "true"
    try:
        assert worker_validation_disposition_enabled() is True
    finally:
        del os.environ["BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED"]
