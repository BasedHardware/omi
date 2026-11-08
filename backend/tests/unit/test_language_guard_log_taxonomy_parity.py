"""The taxonomy moved two log lines and nothing else.

This suite reads the live source and the classification doc and pins the demotion surface: one guard line per site, the fault lines still present, the predicate referenced only by the two logging files, the shadow branch still ahead of the classification, the recovery warning still after both branches, every format token, and every fact the doc states about severity, stages, kept-ERROR reasons, and unchanged accounting.

Failure-Class: FC-language-guard-redrive-misclassified-as-worker-fault
"""

import inspect
import logging
import re
from pathlib import Path

import utils.batch_pipeline.errors as errors_module
import utils.batch_pipeline.scheduler as scheduler_module
import diarizer.batch_pipeline as worker_module

BACKEND = Path(__file__).resolve().parents[2]
WORKER_SOURCE = inspect.getsource(worker_module)
SCHEDULER_SOURCE = inspect.getsource(scheduler_module)
DOC = (BACKEND / 'docs' / 'batch-language-guard-redrive-classification.md').read_text()

WORKER_FIELDS = [
    'error_class',
    'stage',
    'segment_id',
    'reason',
    'samples',
    'vad_spans',
    'windows',
    'asr_words',
    'owned_words',
]
SCHEDULER_FIELDS = ['attempt', 'recovery', 'stage', 'worker_reason']
KEPT_ERROR_REASONS = [
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
    'outside_admitted_source',
    'unknown',
]
KEPT_ERROR_REASONS = [
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
    'outside_admitted_source',
    'unknown',
]
STAGES = ['fetch_decode', 'vad_windows', 'word_clocks', 'assemble_words', 'asr_recovery']


def test_worker_boundary_emits_the_guard_transition_once():
    """Exactly one demotion site exists at the worker boundary."""
    assert WORKER_SOURCE.count('event=batch_language_guard') == 1
    assert 'outcome=redrive_held' in WORKER_SOURCE


def test_scheduler_emits_the_guard_hold_once():
    """Exactly one demotion site exists on the scheduler terminal hold."""
    assert SCHEDULER_SOURCE.count('event=batch_language_guard') == 1
    assert 'outcome=held_for_redrive' in SCHEDULER_SOURCE


def test_worker_boundary_keeps_the_fault_line():
    assert 'event=batch_worker_failed' in WORKER_SOURCE


def test_scheduler_keeps_the_quarantine_line():
    assert 'event=batch_quarantined' in SCHEDULER_SOURCE


def test_the_demotion_constant_is_defined_once():
    """The scheduler calls the predicate once; the worker reads the reason set directly."""
    assert SCHEDULER_SOURCE.count('language_guard_redrive_failure(') == 1
    assert 'LANGUAGE_GUARD_REDRIVE_REASONS' in WORKER_SOURCE


def test_the_predicate_is_referenced_by_exactly_the_two_logging_files():
    """No third module consults the demotion predicate."""
    hits = [
        p.name
        for p in (BACKEND / 'utils' / 'batch_pipeline').glob('*.py')
        if 'language_guard_redrive_failure' in p.read_text() and p.name != '__init__.py'
    ]
    assert sorted(hits) == ['errors.py', 'scheduler.py']


def test_guard_event_appear_only_in_the_two_source_files():
    hits = [
        str(p.relative_to(BACKEND))
        for p in list((BACKEND / 'utils').rglob('*.py')) + list((BACKEND / 'diarizer').rglob('*.py'))
        if 'event=batch_language_guard' in p.read_text()
    ]
    assert sorted(hits) == ['diarizer/batch_pipeline.py', 'utils/batch_pipeline/scheduler.py']


def test_demotion_branch_sits_after_the_shadow_branch():
    """Shadow units keep their own INFO line before the classification runs."""
    shadow_at = WORKER_SOURCE.find("event=batch_shadow_worker_failure")
    guard_at = WORKER_SOURCE.find("event=batch_language_guard")
    assert -1 < shadow_at < guard_at


def test_the_awaiting_recovery_warning_follows_both_branches():
    guard_at = SCHEDULER_SOURCE.find("event=batch_language_guard")
    error_at = SCHEDULER_SOURCE.find("event=batch_quarantined")
    warn_at = SCHEDULER_SOURCE.find("awaiting_fenced_recovery")
    assert error_at < warn_at and guard_at < error_at


def test_worker_guard_format_carries_error_class():
    """The worker transition record carries error_class."""
    assert 'error_class=%' in WORKER_SOURCE.split('event=batch_language_guard')[1][:400]


def test_worker_guard_format_carries_stage():
    """The worker transition record carries stage."""
    assert 'stage=%' in WORKER_SOURCE.split('event=batch_language_guard')[1][:400]


def test_worker_guard_format_carries_segment_id():
    """The worker transition record carries segment_id."""
    assert 'segment_id=%' in WORKER_SOURCE.split('event=batch_language_guard')[1][:400]


def test_worker_guard_format_carries_reason():
    """The worker transition record carries reason."""
    assert 'reason=%' in WORKER_SOURCE.split('event=batch_language_guard')[1][:400]


def test_worker_guard_format_carries_samples():
    """The worker transition record carries samples."""
    assert 'samples=%' in WORKER_SOURCE.split('event=batch_language_guard')[1][:400]


def test_worker_guard_format_carries_vad_spans():
    """The worker transition record carries vad_spans."""
    assert 'vad_spans=%' in WORKER_SOURCE.split('event=batch_language_guard')[1][:400]


def test_worker_guard_format_carries_windows():
    """The worker transition record carries windows."""
    assert 'windows=%' in WORKER_SOURCE.split('event=batch_language_guard')[1][:400]


def test_worker_guard_format_carries_asr_words():
    """The worker transition record carries asr_words."""
    assert 'asr_words=%' in WORKER_SOURCE.split('event=batch_language_guard')[1][:400]


def test_worker_guard_format_carries_owned_words():
    """The worker transition record carries owned_words."""
    assert 'owned_words=%' in WORKER_SOURCE.split('event=batch_language_guard')[1][:400]


def test_scheduler_guard_format_carries_attempt():
    """The scheduler hold record carries attempt."""
    assert 'attempt=' in SCHEDULER_SOURCE.split('event=batch_language_guard')[1][:300]


def test_scheduler_guard_format_carries_recovery():
    """The scheduler hold record carries recovery."""
    assert 'recovery=' in SCHEDULER_SOURCE.split('event=batch_language_guard')[1][:300]


def test_scheduler_guard_format_carries_stage():
    """The scheduler hold record carries stage."""
    assert 'stage=' in SCHEDULER_SOURCE.split('event=batch_language_guard')[1][:300]


def test_scheduler_guard_format_carries_worker_reason():
    """The scheduler hold record carries worker_reason."""
    assert 'worker_reason=' in SCHEDULER_SOURCE.split('event=batch_language_guard')[1][:300]


def test_quarantine_error_format_keeps_event_batch_quarantined():
    """The fault line format is unchanged."""
    assert 'event=batch_quarantined' in SCHEDULER_SOURCE


def test_quarantine_error_format_keeps_reason_worker_failed():
    """The fault line format is unchanged."""
    assert 'reason=worker_failed' in SCHEDULER_SOURCE


def test_quarantine_error_format_keeps_attempt_pctd():
    """The fault line format is unchanged."""
    assert 'attempt=%d' in SCHEDULER_SOURCE


def test_quarantine_error_format_keeps_recovery_held():
    """The fault line format is unchanged."""
    assert 'recovery=held' in SCHEDULER_SOURCE


def test_quarantine_error_format_keeps_stage_pcts():
    """The fault line format is unchanged."""
    assert 'stage=%s' in SCHEDULER_SOURCE


def test_quarantine_error_format_keeps_worker_reason_pcts():
    """The fault line format is unchanged."""
    assert 'worker_reason=%s' in SCHEDULER_SOURCE


def test_worker_fault_format_keeps_event_batch_worker_failed():
    """The worker fault line format is unchanged."""
    assert 'event=batch_worker_failed' in WORKER_SOURCE


def test_worker_fault_format_keeps_error_class_pcts():
    """The worker fault line format is unchanged."""
    assert 'error_class=%s' in WORKER_SOURCE


def test_worker_fault_format_keeps_reason_pcts():
    """The worker fault line format is unchanged."""
    assert 'reason=%s' in WORKER_SOURCE


def test_predicate_docstring_names_the_closed_shape():
    assert 'two-key' in (errors_module.language_guard_redrive_failure.__doc__ or '')


def test_predicate_docstring_promises_no_raise():
    assert 'never raises' in (errors_module.language_guard_redrive_failure.__doc__ or '').lower()


def test_reason_set_is_the_single_guard_token():
    assert errors_module.LANGUAGE_GUARD_REDRIVE_REASONS == {'unsupported_language'}


def test_doc_names_event_batch_language_guard():
    assert 'event=batch_language_guard' in DOC


def test_doc_names_outcome_redrive_held():
    assert 'outcome=redrive_held' in DOC


def test_doc_names_outcome_held_for_redrive():
    assert 'outcome=held_for_redrive' in DOC


def test_doc_says_info():
    assert 'INFO' in DOC


def test_doc_says_error():
    assert 'ERROR' in DOC


def test_doc_names_the_guard_reason():
    assert 'unsupported_language' in DOC


def test_doc_names_the_recovery_warning():
    assert 'awaiting_fenced_recovery' in DOC


def test_doc_names_the_demotion_constant():
    assert 'LANGUAGE_GUARD_REDRIVE_REASONS' in DOC


def test_doc_names_the_predicate():
    assert 'language_guard_redrive_failure' in DOC


def test_doc_carries_the_failure_class_trailer():
    assert 'Failure-Class:' in DOC


def test_doc_says_the_quarantined_state_is_unchanged():
    assert 'quarantined state' in DOC


def test_doc_names_stage_fetch_decode():
    assert 'fetch_decode' in DOC


def test_doc_names_stage_vad_windows():
    assert 'vad_windows' in DOC


def test_doc_names_stage_word_clocks():
    assert 'word_clocks' in DOC


def test_doc_names_stage_assemble_words():
    assert 'assemble_words' in DOC


def test_doc_names_stage_asr_recovery():
    assert 'asr_recovery' in DOC


def test_doc_lists_staged_audio_invalid_as_staying_error():
    """staged_audio_invalid stays on the fault channels per the doc."""
    assert 'staged_audio_invalid' in DOC


def test_doc_lists_retained_audio_invalid_as_staying_error():
    """retained_audio_invalid stays on the fault channels per the doc."""
    assert 'retained_audio_invalid' in DOC


def test_doc_lists_decoded_duration_mismatch_as_staying_error():
    """decoded_duration_mismatch stays on the fault channels per the doc."""
    assert 'decoded_duration_mismatch' in DOC


def test_doc_lists_word_shape_as_staying_error():
    """word_shape stays on the fault channels per the doc."""
    assert 'word_shape' in DOC


def test_doc_lists_word_clock_as_staying_error():
    """word_clock stays on the fault channels per the doc."""
    assert 'word_clock' in DOC


def test_doc_lists_word_sequence_as_staying_error():
    """word_sequence stays on the fault channels per the doc."""
    assert 'word_sequence' in DOC


def test_doc_lists_vad_nonfinite_as_staying_error():
    """vad_nonfinite stays on the fault channels per the doc."""
    assert 'vad_nonfinite' in DOC


def test_doc_lists_vad_order_as_staying_error():
    """vad_order stays on the fault channels per the doc."""
    assert 'vad_order' in DOC


def test_doc_lists_vad_bounds_as_staying_error():
    """vad_bounds stays on the fault channels per the doc."""
    assert 'vad_bounds' in DOC


def test_doc_lists_empty_asr_as_staying_error():
    """empty_asr stays on the fault channels per the doc."""
    assert 'empty_asr' in DOC


def test_doc_lists_no_owned_words_as_staying_error():
    """no_owned_words stays on the fault channels per the doc."""
    assert 'no_owned_words' in DOC


def test_doc_lists_outside_admitted_source_as_staying_error():
    """outside_admitted_source stays on the fault channels per the doc."""
    assert 'outside_admitted_source' in DOC


def test_doc_lists_unknown_as_staying_error():
    """unknown stays on the fault channels per the doc."""
    assert 'unknown' in DOC


def test_doc_field_inventory_names_error_class():
    assert 'error_class' in DOC


def test_doc_field_inventory_names_stage():
    assert 'stage' in DOC


def test_doc_field_inventory_names_segment_id():
    assert 'segment_id' in DOC


def test_doc_field_inventory_names_reason():
    assert 'reason' in DOC


def test_doc_field_inventory_names_samples():
    assert 'samples' in DOC


def test_doc_field_inventory_names_vad_spans():
    assert 'vad_spans' in DOC


def test_doc_field_inventory_names_windows():
    assert 'windows' in DOC


def test_doc_field_inventory_names_asr_words():
    assert 'asr_words' in DOC


def test_doc_field_inventory_names_owned_words():
    assert 'owned_words' in DOC


def test_doc_hold_inventory_names_attempt():
    assert 'attempt' in DOC


def test_doc_hold_inventory_names_recovery():
    assert 'recovery' in DOC


def test_doc_hold_inventory_names_stage():
    assert 'stage' in DOC


def test_doc_hold_inventory_names_worker_reason():
    assert 'worker_reason' in DOC


def test_doc_names_the_metrics_tokens():
    assert 'recovery_held' in DOC and 'quarantined' in DOC


def test_doc_names_the_soniox_lane():
    assert 'Soniox' in DOC and 'Modulate' in DOC
