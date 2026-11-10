"""Contract parity for the deferred-drain storm-window alignment.



The docs page is the contract of record for the alignment; these pins fail

when code and contract drift apart in either direction. Literal extraction

reads the real module sources and the real page - nothing is hard-coded

twice.



Failure-Class: FC-deferred-drain-restrike-collides-inside-the-armed-storm-window

"""

import inspect

import re

from pathlib import Path


import utils.batch_pipeline.pump as pump_module

from database import batch_pipeline_store as storage

from database import firestore_transaction_retry as retry_module

DOCS = Path(__file__).resolve().parents[2] / 'docs' / 'batch-merge-deferred-drain-convergence.md'

PUMP_SOURCE = inspect.getsource(pump_module)

STORE_SOURCE = inspect.getsource(storage)

RETRY_SOURCE = inspect.getsource(retry_module)

FC = 'FC-deferred-drain-restrike-collides-inside-the-armed-storm-window'


def docs_text():

    return DOCS.read_text()


def test_parity_doc_storm_window_alignment():
    assert 'Storm-window alignment' in docs_text()


def test_parity_doc_firestorecontentionexhausted_retry_after():
    assert 'FirestoreContentionExhausted.retry_after' in docs_text()


def test_parity_doc_fc_deferred_drain_restrike_collides_inside_the_a():
    assert 'FC-deferred-drain-restrike-collides-inside-the-armed-storm-window' in docs_text()


def test_parity_doc_due_at_now_max_documented_backoff_step_retry_aft():
    assert 'due_at = now + max(documented backoff step, retry_after)' in docs_text()


def test_parity_doc_clamped_to():
    assert 'clamped to' in docs_text()


def test_parity_doc_drain_retry_max_seconds():
    assert 'DRAIN_RETRY_MAX_SECONDS' in docs_text()


def test_parity_doc_non_contention_loss():
    assert 'non-contention loss' in docs_text()


def test_parity_doc_foreign_exception():
    assert 'foreign exception' in docs_text()


def test_parity_doc_legacy_schedule():
    assert 'legacy schedule' in docs_text()


def test_parity_doc_continuation_re_offer():
    assert 'continuation re-offer' in docs_text()


def test_parity_doc_attempt_cap():
    assert 'attempt cap' in docs_text()


def test_parity_doc_burned_all_five_attempts():
    assert 'burned all five attempts' in docs_text()


def test_parity_doc_lockstep_burn():
    assert 'lockstep burn' in docs_text()


def test_parity_doc_six_attempt_budget():
    assert 'six-attempt budget' in docs_text()


def test_parity_doc_error_line_fired():
    assert 'ERROR line fired' in docs_text()


def test_parity_doc_consult_in():
    assert 'consult in' in docs_text()


def test_parity_doc_storm_damper():
    assert 'storm damper' in docs_text()


def test_parity_doc_armed_window():
    assert 'armed window' in docs_text()


def test_parity_doc_event_batch_merge_outcome_retry():
    assert 'event=batch_merge outcome=retry' in docs_text()


def test_parity_doc_event_batch_merge_drain_outcome_deferred():
    assert 'event=batch_merge_drain outcome=deferred' in docs_text()


def test_parity_doc_event_batch_merge_drain_outcome_converged():
    assert 'event=batch_merge_drain outcome=converged' in docs_text()


def test_parity_doc_maintenance_sweep_backstop():
    assert 'maintenance-sweep backstop' in docs_text()


def test_parity_doc_the_lane_is_an_accelerator_in_front_of_the_durab():
    assert 'the lane is an accelerator in front of the durable backstop' in docs_text()


def test_parity_doc_fc_publication_drain_contention_exhaustion_left_():
    assert 'FC-publication-drain-contention-exhaustion-left-without-a-convergence-owner' in docs_text()


def test_parity_doc_deferred_publication_drain_lane():
    assert 'deferred publication-drain lane' in docs_text()


def test_parity_doc_0_5s_1s_2s_4s_then_8s_capped():
    assert '0.5s, 1s, 2s, 4s, then 8s capped' in docs_text()


def test_parity_doc_drain_retry_ledger_cap():
    assert 'DRAIN_RETRY_LEDGER_CAP' in docs_text()


def test_parity_doc_drain_backlog_continuation_attempts():
    assert 'DRAIN_BACKLOG_CONTINUATION_ATTEMPTS' in docs_text()


def test_parity_doc_drain_retry_max_attempts():
    assert 'DRAIN_RETRY_MAX_ATTEMPTS' in docs_text()


def test_parity_doc_bounded_exponential_backoff():
    assert 'bounded exponential backoff' in docs_text()


def test_parity_doc_oldest_armed_first_eviction():
    assert 'oldest-armed-first eviction' in docs_text()


def test_parity_doc_flushes_every_armed_owner():
    assert 'flushes every armed owner' in docs_text()


def test_parity_doc_never_widens_publication_ordering():
    assert 'never widens publication ordering' in docs_text()


def test_parity_doc_per_owner_serial_lock():
    assert 'per-owner serial lock' in docs_text()


def test_parity_doc_no_feature_flag():
    assert 'No feature flag' in docs_text()


def test_parity_doc_what_changed():
    assert 'What changed' in docs_text()


def test_parity_doc_what_did_not_change():
    assert 'What did not change' in docs_text()


def test_parity_doc_boundary_notes():
    assert 'Boundary notes' in docs_text()


def test_parity_doc_maintenance_ready_page_remains_its_convergence():
    assert 'maintenance ready page remains its convergence' in docs_text()


def test_parity_doc_100_commit_bound():
    assert '100-commit bound' in docs_text()


def test_parity_pump_declares_the_math_import():
    assert 'import math' in PUMP_SOURCE


def test_parity_pump_defines_the_helper():
    assert 'def contention_retry_after(' in PUMP_SOURCE


def test_parity_pump_helper_rejects_bools():
    assert 'isinstance(value, bool)' in PUMP_SOURCE


def test_parity_pump_helper_rejects_nonfinite():
    assert 'math.isfinite(value)' in PUMP_SOURCE


def test_parity_pump_helper_clamps_at_the_lane_max():
    assert 'min(value, DRAIN_RETRY_MAX_SECONDS)' in PUMP_SOURCE


def test_parity_pump_helper_reads_the_stamped_attribute():
    assert "getattr(error, 'retry_after', None)" in PUMP_SOURCE


def test_parity_pump_defer_drain_takes_the_storm_window():
    assert 'retry_after: float = 0.0' in PUMP_SOURCE


def test_parity_pump_defer_drain_composes_max():
    assert 'max(delay, min(float(retry_after), DRAIN_RETRY_MAX_SECONDS))' in PUMP_SOURCE


def test_parity_pump_publication_catch_carries_the_window():
    assert 'retry_after=contention_retry_after(error)' in PUMP_SOURCE


def test_parity_pump_lane_catch_carries_the_window():
    assert 'retry_after=contention_retry_after(error)' in PUMP_SOURCE


def test_parity_pump_names_the_alignment_comment():
    assert 'Storm alignment: land the re-drain after' in PUMP_SOURCE


def test_parity_pump_names_the_measured_window():
    assert 'measured window' in PUMP_SOURCE


def test_parity_store_stamps_the_applied_window():
    assert 'error.retry_after = damper.arm(label, client=client)' in STORE_SOURCE


def test_parity_store_names_the_carried_window():
    assert 'The window the damper actually applied rides on the exception' in STORE_SOURCE


def test_parity_retry_declares_the_storm_field():
    assert 'retry_after: float = 0.0' in RETRY_SOURCE


def test_parity_retry_coerces_the_storm_field():
    assert 'self.retry_after = float(retry_after)' in RETRY_SOURCE


def test_parity_retry_names_the_damper_stamp():
    assert 'A store-level storm damper that spaces the label' in RETRY_SOURCE


def test_parity_both_rearm_cites_align():
    assert PUMP_SOURCE.count("retry_after=contention_retry_after(error)") == 2


def test_parity_constant_storm_damper_base():
    assert storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS == 0.25


def test_parity_constant_storm_damper_cap():
    assert storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS == 4.0


def test_parity_constant_storm_damper_ladder_steps():
    assert storage.FirestoreStore.STORM_DAMPER_LADDER_STEPS == 4


def test_parity_constant_storm_damper_max_tracked_labels():
    assert storage.FirestoreStore.STORM_DAMPER_MAX_TRACKED_LABELS == 64


def test_parity_constant_drain_retry_base():
    assert pump_module.DRAIN_RETRY_BASE_SECONDS == 0.5


def test_parity_constant_drain_retry_max():
    assert pump_module.DRAIN_RETRY_MAX_SECONDS == 8.0


def test_parity_constant_drain_retry_max_attempts():
    assert pump_module.DRAIN_RETRY_MAX_ATTEMPTS == 6


def test_parity_constant_drain_backlog_continuation_attempts():
    assert pump_module.DRAIN_BACKLOG_CONTINUATION_ATTEMPTS == 4


def test_parity_constant_drain_retry_ledger_cap():
    assert pump_module.DRAIN_RETRY_LEDGER_CAP == 512


def test_parity_schedule_step_1():
    assert pump_module.deferred_drain_delay(1) == 0.5


def test_parity_schedule_step_2():
    assert pump_module.deferred_drain_delay(2) == 1.0


def test_parity_schedule_step_3():
    assert pump_module.deferred_drain_delay(3) == 2.0


def test_parity_schedule_step_4():
    assert pump_module.deferred_drain_delay(4) == 4.0


def test_parity_schedule_step_5():
    assert pump_module.deferred_drain_delay(5) == 8.0


def test_parity_schedule_step_6():
    assert pump_module.deferred_drain_delay(6) == 8.0


def test_parity_failure_class_trailer_in_doc():
    assert FC in docs_text()


def test_parity_failure_class_trailer_in_core_suite():
    core = Path(__file__).resolve().parent / "test_deferred_drain_storm_window_alignment.py"
    assert FC in core.read_text()


def test_parity_failure_class_trailer_in_store_grid():
    grid = Path(__file__).resolve().parent / "test_deferred_drain_storm_store_stamp_grid.py"
    assert FC in grid.read_text()


def test_parity_failure_class_trailer_in_lane_grid():
    grid = Path(__file__).resolve().parent / "test_deferred_drain_storm_lane_alignment_grid.py"
    assert FC in grid.read_text()
