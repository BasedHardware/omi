"""Real batch-lane module pins for the async-blocker gate.

These cells run the real scanner over the real production batch-lane
modules (``utils/batch_pipeline`` plus
``database/firestore_transaction_retry.py``) and pin, per function, whether
it is gate-clean, in the fixed posture and with the pure-classifier
resolution ablated. The ablated column is the blackout regression surface:
``pump._restrike_publication`` was the finding that failed the manifest
check on every candidate PR (FC-async-blocker-gate-false-positive-on-pure-db-classifiers); the ablation pins exactly which
functions the exemption keeps clean so any new blocking call in the lane
still surfaces.

Two module-scoped scans run once; every cell asserts literals against the
cached results.

Failure-Class: FC-async-blocker-gate-false-positive-on-pure-db-classifiers
"""

import pytest

from scripts.scan_async_blockers import scan_dirs

import tests.support.async_gate_real_lane_fixture as fixture


def test_pump_async__drain_task_fixed_is_clean() -> None:
    """pump._drain_task: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', '_drain_task') is None


def test_pump_async__drain_task_ablated_verdict() -> None:
    """pump._drain_task: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', '_drain_task') is None


def test_pump_async_run_fixed_is_clean() -> None:
    """pump.run: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', 'run') is None


def test_pump_async_run_ablated_verdict() -> None:
    """pump.run: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', 'run') is None


def test_pump_async__maintain_loop_fixed_is_clean() -> None:
    """pump._maintain_loop: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', '_maintain_loop') is None


def test_pump_async__maintain_loop_ablated_verdict() -> None:
    """pump._maintain_loop: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', '_maintain_loop') is None


def test_pump_async__lane_fixed_is_clean() -> None:
    """pump._lane: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', '_lane') is None


def test_pump_async__lane_ablated_verdict() -> None:
    """pump._lane: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', '_lane') is None


def test_pump_async__renew_fixed_is_clean() -> None:
    """pump._renew: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', '_renew') is None


def test_pump_async__renew_ablated_verdict() -> None:
    """pump._renew: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', '_renew') is None


def test_pump_async__run_blocking_fixed_is_clean() -> None:
    """pump._run_blocking: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', '_run_blocking') is None


def test_pump_async__run_blocking_ablated_verdict() -> None:
    """pump._run_blocking: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', '_run_blocking') is None


def test_pump_async_run_once_fixed_is_clean() -> None:
    """pump.run_once: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', 'run_once') is None


def test_pump_async_run_once_ablated_verdict() -> None:
    """pump.run_once: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', 'run_once') is None


def test_pump_async__maintain_fixed_is_clean() -> None:
    """pump._maintain: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', '_maintain') is None


def test_pump_async__maintain_ablated_verdict() -> None:
    """pump._maintain: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', '_maintain') is None


def test_pump_async__maintenance_step_fixed_is_clean() -> None:
    """pump._maintenance_step: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', '_maintenance_step') is None


def test_pump_async__maintenance_step_ablated_verdict() -> None:
    """pump._maintenance_step: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', '_maintenance_step') is None


def test_pump_async__maintain_leader_steps_fixed_is_clean() -> None:
    """pump._maintain_leader_steps: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', '_maintain_leader_steps') is None


def test_pump_async__maintain_leader_steps_ablated_verdict() -> None:
    """pump._maintain_leader_steps: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', '_maintain_leader_steps') is None


def test_pump_async__authorize_flight_timed_fixed_is_clean() -> None:
    """pump._authorize_flight_timed: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', '_authorize_flight_timed') is None


def test_pump_async__authorize_flight_timed_ablated_verdict() -> None:
    """pump._authorize_flight_timed: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', '_authorize_flight_timed') is None


def test_pump_async__authorize_flight_fixed_is_clean() -> None:
    """pump._authorize_flight: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', '_authorize_flight') is None


def test_pump_async__authorize_flight_ablated_verdict() -> None:
    """pump._authorize_flight: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', '_authorize_flight') is None


def test_pump_async__flight_fixed_is_clean() -> None:
    """pump._flight: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', '_flight') is None


def test_pump_async__flight_ablated_verdict() -> None:
    """pump._flight: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', '_flight') is None


def test_pump_async__release_fixed_is_clean() -> None:
    """pump._release: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', '_release') is None


def test_pump_async__release_ablated_verdict() -> None:
    """pump._release: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', '_release') is None


def test_pump_async__owner_serial_fixed_is_clean() -> None:
    """pump._owner_serial: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', '_owner_serial') is None


def test_pump_async__owner_serial_ablated_verdict() -> None:
    """pump._owner_serial: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', '_owner_serial') is None


def test_pump_async__bounded_map_fixed_is_clean() -> None:
    """pump._bounded_map: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', '_bounded_map') is None


def test_pump_async__bounded_map_ablated_verdict() -> None:
    """pump._bounded_map: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', '_bounded_map') is None


def test_pump_async__drain_ready_owners_fixed_is_clean() -> None:
    """pump._drain_ready_owners: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', '_drain_ready_owners') is None


def test_pump_async__drain_ready_owners_ablated_verdict() -> None:
    """pump._drain_ready_owners: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', '_drain_ready_owners') is None


def test_pump_async__publish_fixed_is_clean() -> None:
    """pump._publish: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', '_publish') is None


def test_pump_async__publish_ablated_verdict() -> None:
    """pump._publish: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', '_publish') is None


def test_pump_async__publish_transition_fixed_is_clean() -> None:
    """pump._publish_transition: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', '_publish_transition') is None


def test_pump_async__publish_transition_ablated_verdict() -> None:
    """pump._publish_transition: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', '_publish_transition') is None


def test_pump_async__restrike_publication_fixed_is_clean() -> None:
    """pump._restrike_publication: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', '_restrike_publication') is None


def test_pump_async__restrike_publication_ablated_verdict() -> None:
    """pump._restrike_publication: with pure resolution ablated, flagged=True."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', '_restrike_publication') is not None


def test_pump_async__drain_after_publication_fixed_is_clean() -> None:
    """pump._drain_after_publication: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', '_drain_after_publication') is None


def test_pump_async__drain_after_publication_ablated_verdict() -> None:
    """pump._drain_after_publication: ablation flags the pure db classifier it now calls."""
    finding = fixture.finding_for(fixture.ABLATED, 'pump.py', '_drain_after_publication')
    assert finding is not None
    assert any('is_transaction_contention' in call['call'] for call in finding['db_calls'])


def test_pump_async__publish_flight_fixed_is_clean() -> None:
    """pump._publish_flight: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', '_publish_flight') is None


def test_pump_async__publish_flight_ablated_verdict() -> None:
    """pump._publish_flight: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', '_publish_flight') is None


def test_pump_async__drain_deferred_due_fixed_is_clean() -> None:
    """pump._drain_deferred_due: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', '_drain_deferred_due') is None


def test_pump_async__drain_deferred_due_ablated_verdict() -> None:
    """pump._drain_deferred_due: ablation flags the pure db classifier it now calls."""
    finding = fixture.finding_for(fixture.ABLATED, 'pump.py', '_drain_deferred_due')
    assert finding is not None
    assert any('is_transaction_contention' in call['call'] for call in finding['db_calls'])


def test_pump_async__deferred_drain_lane_fixed_is_clean() -> None:
    """pump._deferred_drain_lane: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', '_deferred_drain_lane') is None


def test_pump_async__deferred_drain_lane_ablated_verdict() -> None:
    """pump._deferred_drain_lane: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', '_deferred_drain_lane') is None


def test_pump_async_flush_deferred_drains_fixed_is_clean() -> None:
    """pump.flush_deferred_drains: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', 'flush_deferred_drains') is None


def test_pump_async_flush_deferred_drains_ablated_verdict() -> None:
    """pump.flush_deferred_drains: ablation flags the pure db classifier it now calls."""
    finding = fixture.finding_for(fixture.ABLATED, 'pump.py', 'flush_deferred_drains')
    assert finding is not None
    assert any('is_transaction_contention' in call['call'] for call in finding['db_calls'])


def test_pump_async_sample_metrics_fixed_is_clean() -> None:
    """pump.sample_metrics: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', 'sample_metrics') is None


def test_pump_async_sample_metrics_ablated_verdict() -> None:
    """pump.sample_metrics: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', 'sample_metrics') is None


def test_pump_async_drain_owner_fixed_is_clean() -> None:
    """pump.drain_owner: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', 'drain_owner') is None


def test_pump_async_drain_owner_ablated_verdict() -> None:
    """pump.drain_owner: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', 'drain_owner') is None


def test_pump_async_relay_fixed_is_clean() -> None:
    """pump.relay: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', 'relay') is None


def test_pump_async_relay_ablated_verdict() -> None:
    """pump.relay: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', 'relay') is None


def test_pump_async_one_fixed_is_clean() -> None:
    """pump.one: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', 'one') is None


def test_pump_async_one_ablated_verdict() -> None:
    """pump.one: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', 'one') is None


def test_pump_async_owner_of_fixed_is_clean() -> None:
    """pump.owner_of: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', 'owner_of') is None


def test_pump_async_owner_of_ablated_verdict() -> None:
    """pump.owner_of: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', 'owner_of') is None


def test_pump_async_publish_one_fixed_is_clean() -> None:
    """pump.publish_one: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', 'publish_one') is None


def test_pump_async_publish_one_ablated_verdict() -> None:
    """pump.publish_one: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', 'publish_one') is None


def test_pump_async_publish_owner_fixed_is_clean() -> None:
    """pump.publish_owner: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', 'publish_owner') is None


def test_pump_async_publish_owner_ablated_verdict() -> None:
    """pump.publish_owner: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', 'publish_owner') is None


def test_pump_async_renew_one_fixed_is_clean() -> None:
    """pump.renew_one: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', 'renew_one') is None


def test_pump_async_renew_one_ablated_verdict() -> None:
    """pump.renew_one: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', 'renew_one') is None


def test_pump_async_discard_invalid_preparation_fixed_is_clean() -> None:
    """pump.discard_invalid_preparation: fixed posture gate-clean=True."""
    assert fixture.finding_for(fixture.FIXED, 'pump.py', 'discard_invalid_preparation') is None


def test_pump_async_discard_invalid_preparation_ablated_verdict() -> None:
    """pump.discard_invalid_preparation: with pure resolution ablated, flagged=False."""
    assert fixture.finding_for(fixture.ABLATED, 'pump.py', 'discard_invalid_preparation') is None


def test_sync_defs_utils_batch_pipeline_admission_admitted_as_byok_effects() -> None:
    """utils/batch_pipeline/admission.py::admitted_as_byok: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/admission.py', 'admitted_as_byok') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/admission.py', 'admitted_as_byok') == ()


def test_sync_defs_utils_batch_pipeline_admission_deadline_seconds_effects() -> None:
    """utils/batch_pipeline/admission.py::deadline_seconds: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/admission.py', 'deadline_seconds') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/admission.py', 'deadline_seconds') == ()


def test_sync_defs_utils_batch_pipeline_admission_batch_admission_effects() -> None:
    """utils/batch_pipeline/admission.py::batch_admission: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/admission.py', 'batch_admission') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/admission.py', 'batch_admission') == ()


def test_sync_defs_utils_batch_pipeline_artifact_missing_record_effects() -> None:
    """utils/batch_pipeline/artifact_missing.py::record: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/artifact_missing.py', 'record') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/artifact_missing.py', 'record') == ()


def test_sync_defs_utils_batch_pipeline_artifact_policy_artifacts_for_effects() -> None:
    """utils/batch_pipeline/artifact_policy.py::artifacts_for: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/artifact_policy.py', 'artifacts_for') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/artifact_policy.py', 'artifacts_for') == ()


def test_sync_defs_utils_batch_pipeline_artifact_policy_create_artifact_store_effects() -> None:
    """utils/batch_pipeline/artifact_policy.py::create_artifact_store: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/artifact_policy.py', 'create_artifact_store') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/artifact_policy.py', 'create_artifact_store') == ()


def test_sync_defs_utils_batch_pipeline_artifact_policy__shadow_projection_client_effects() -> None:
    """utils/batch_pipeline/artifact_policy.py::_shadow_projection_client: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/artifact_policy.py', '_shadow_projection_client') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/artifact_policy.py', '_shadow_projection_client') == ()


def test_sync_defs_utils_batch_pipeline_artifact_policy_shadow_result_effects() -> None:
    """utils/batch_pipeline/artifact_policy.py::shadow_result: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/artifact_policy.py', 'shadow_result') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/artifact_policy.py', 'shadow_result') == ('db_calls',)


def test_sync_defs_utils_batch_pipeline_artifact_reupload__repair_plan_effects() -> None:
    """utils/batch_pipeline/artifact_reupload.py::_repair_plan: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/artifact_reupload.py', '_repair_plan') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/artifact_reupload.py', '_repair_plan') == ('db_calls',)


def test_sync_defs_utils_batch_pipeline_artifact_reupload__hold_effects() -> None:
    """utils/batch_pipeline/artifact_reupload.py::_hold: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/artifact_reupload.py', '_hold') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/artifact_reupload.py', '_hold') == ('db_calls',)


def test_sync_defs_utils_batch_pipeline_artifact_reupload__repair_evidence_effects() -> None:
    """utils/batch_pipeline/artifact_reupload.py::_repair_evidence: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/artifact_reupload.py', '_repair_evidence') == (
        'db_calls',
    )
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/artifact_reupload.py', '_repair_evidence') == (
        'db_calls',
    )


def test_sync_defs_utils_batch_pipeline_artifact_reupload__original_unit_effects() -> None:
    """utils/batch_pipeline/artifact_reupload.py::_original_unit: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/artifact_reupload.py', '_original_unit') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/artifact_reupload.py', '_original_unit') == (
        'db_calls',
    )


def test_sync_defs_utils_batch_pipeline_artifact_reupload__commit_restore_effects() -> None:
    """utils/batch_pipeline/artifact_reupload.py::_commit_restore: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/artifact_reupload.py', '_commit_restore') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/artifact_reupload.py', '_commit_restore') == (
        'db_calls',
    )


def test_sync_defs_utils_batch_pipeline_audio_audio_unit_effects() -> None:
    """utils/batch_pipeline/audio.py::audio_unit: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/audio.py', 'audio_unit') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/audio.py', 'audio_unit') == ()


def test_sync_defs_utils_batch_pipeline_audio_with_context_effects() -> None:
    """utils/batch_pipeline/audio.py::with_context: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/audio.py', 'with_context') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/audio.py', 'with_context') == ()


def test_sync_defs_utils_batch_pipeline_audio_read_context_effects() -> None:
    """utils/batch_pipeline/audio.py::read_context: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/audio.py', 'read_context') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/audio.py', 'read_context') == ()


def test_sync_defs_utils_batch_pipeline_cap_hold_admission_held_content_id_effects() -> None:
    """utils/batch_pipeline/cap_hold_admission.py::held_content_id: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/cap_hold_admission.py', 'held_content_id') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/cap_hold_admission.py', 'held_content_id') == ()


def test_sync_defs_utils_batch_pipeline_cap_hold_admission_handoff_projected_effects() -> None:
    """utils/batch_pipeline/cap_hold_admission.py::handoff_projected: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/cap_hold_admission.py', 'handoff_projected') == (
        'db_calls',
    )
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/cap_hold_admission.py', 'handoff_projected') == (
        'db_calls',
    )


def test_sync_defs_utils_batch_pipeline_cap_hold_admission_eligible_effects() -> None:
    """utils/batch_pipeline/cap_hold_admission.py::eligible: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/cap_hold_admission.py', 'eligible') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/cap_hold_admission.py', 'eligible') == ()


def test_sync_defs_utils_batch_pipeline_cap_hold_admission_enabled_for_effects() -> None:
    """utils/batch_pipeline/cap_hold_admission.py::enabled_for: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/cap_hold_admission.py', 'enabled_for') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/cap_hold_admission.py', 'enabled_for') == ()


def test_sync_defs_utils_batch_pipeline_cap_hold_admission_wav_units_effects() -> None:
    """utils/batch_pipeline/cap_hold_admission.py::wav_units: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/cap_hold_admission.py', 'wav_units') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/cap_hold_admission.py', 'wav_units') == ()


def test_sync_defs_utils_batch_pipeline_cap_hold_admission__body_effects() -> None:
    """utils/batch_pipeline/cap_hold_admission.py::_body: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/cap_hold_admission.py', '_body') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/cap_hold_admission.py', '_body') == ()


def test_sync_defs_utils_batch_pipeline_cap_hold_admission__code_effects() -> None:
    """utils/batch_pipeline/cap_hold_admission.py::_code: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/cap_hold_admission.py', '_code') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/cap_hold_admission.py', '_code') == ()


def test_sync_defs_utils_batch_pipeline_capacity_within_unit_ceiling_effects() -> None:
    """utils/batch_pipeline/capacity.py::within_unit_ceiling: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/capacity.py', 'within_unit_ceiling') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/capacity.py', 'within_unit_ceiling') == ()


def test_sync_defs_utils_batch_pipeline_capture_decode__frame_count_effects() -> None:
    """utils/batch_pipeline/capture_decode.py::_frame_count: effects fixed=('file_io',) ablated=('file_io',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/capture_decode.py', '_frame_count') == ('file_io',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/capture_decode.py', '_frame_count') == ('file_io',)


def test_sync_defs_utils_batch_pipeline_capture_decode__canonical_effects() -> None:
    """utils/batch_pipeline/capture_decode.py::_canonical: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/capture_decode.py', '_canonical') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/capture_decode.py', '_canonical') == ()


def test_sync_defs_utils_batch_pipeline_capture_decode_decode_units_effects() -> None:
    """utils/batch_pipeline/capture_decode.py::decode_units: effects fixed=('file_io',) ablated=('file_io',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/capture_decode.py', 'decode_units') == ('file_io',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/capture_decode.py', 'decode_units') == ('file_io',)


def test_sync_defs_utils_batch_pipeline_compute_client_failure_outcome_effects() -> None:
    """utils/batch_pipeline/compute_client.py::failure_outcome: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/compute_client.py', 'failure_outcome') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/compute_client.py', 'failure_outcome') == ()


def test_sync_defs_utils_batch_pipeline_compute_client_from_env_effects() -> None:
    """utils/batch_pipeline/compute_client.py::from_env: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/compute_client.py', 'from_env') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/compute_client.py', 'from_env') == ()


def test_sync_defs_utils_batch_pipeline_compute_client_shadow_from_env_effects() -> None:
    """utils/batch_pipeline/compute_client.py::shadow_from_env: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/compute_client.py', 'shadow_from_env') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/compute_client.py', 'shadow_from_env') == ()


def test_sync_defs_utils_batch_pipeline_context__blocked_effects() -> None:
    """utils/batch_pipeline/context.py::_blocked: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/context.py', '_blocked') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/context.py', '_blocked') == ('db_calls',)


def test_sync_defs_utils_batch_pipeline_context_require_repair_manifest_effects() -> None:
    """utils/batch_pipeline/context.py::require_repair_manifest: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/context.py', 'require_repair_manifest') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/context.py', 'require_repair_manifest') == ('db_calls',)


def test_sync_defs_utils_batch_pipeline_context_resolve_context_effects() -> None:
    """utils/batch_pipeline/context.py::resolve_context: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/context.py', 'resolve_context') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/context.py', 'resolve_context') == ('db_calls',)


def test_sync_defs_utils_batch_pipeline_contracts_projection_speech_spans_effects() -> None:
    """utils/batch_pipeline/contracts.py::projection_speech_spans: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/contracts.py', 'projection_speech_spans') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/contracts.py', 'projection_speech_spans') == ()


def test_sync_defs_utils_batch_pipeline_contracts_validate_measured_vad_effects() -> None:
    """utils/batch_pipeline/contracts.py::validate_measured_vad: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/contracts.py', 'validate_measured_vad') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/contracts.py', 'validate_measured_vad') == ()


def test_sync_defs_utils_batch_pipeline_contracts_held_vad_census_effects() -> None:
    """utils/batch_pipeline/contracts.py::held_vad_census: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/contracts.py', 'held_vad_census') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/contracts.py', 'held_vad_census') == ()


def test_sync_defs_utils_batch_pipeline_contracts_held_silence_allowed_effects() -> None:
    """utils/batch_pipeline/contracts.py::held_silence_allowed: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/contracts.py', 'held_silence_allowed') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/contracts.py', 'held_silence_allowed') == ()


def test_sync_defs_utils_batch_pipeline_contracts_held_result_allowed_effects() -> None:
    """utils/batch_pipeline/contracts.py::held_result_allowed: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/contracts.py', 'held_result_allowed') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/contracts.py', 'held_result_allowed') == ()


def test_sync_defs_utils_batch_pipeline_contracts_vad_receipt_effects() -> None:
    """utils/batch_pipeline/contracts.py::vad_receipt: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/contracts.py', 'vad_receipt') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/contracts.py', 'vad_receipt') == ()


def test_sync_defs_utils_batch_pipeline_contracts_bound_vad_receipt_effects() -> None:
    """utils/batch_pipeline/contracts.py::bound_vad_receipt: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/contracts.py', 'bound_vad_receipt') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/contracts.py', 'bound_vad_receipt') == ()


def test_sync_defs_utils_batch_pipeline_contracts_worker_vad_speech_effects() -> None:
    """utils/batch_pipeline/contracts.py::worker_vad_speech: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/contracts.py', 'worker_vad_speech') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/contracts.py', 'worker_vad_speech') == ()


def test_sync_defs_utils_batch_pipeline_contracts_worker_vad_word_spans_effects() -> None:
    """utils/batch_pipeline/contracts.py::worker_vad_word_spans: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/contracts.py', 'worker_vad_word_spans') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/contracts.py', 'worker_vad_word_spans') == ()


def test_sync_defs_utils_batch_pipeline_contracts_attach_held_vad_effects() -> None:
    """utils/batch_pipeline/contracts.py::attach_held_vad: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/contracts.py', 'attach_held_vad') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/contracts.py', 'attach_held_vad') == ()


def test_sync_defs_utils_batch_pipeline_control_field_effects() -> None:
    """utils/batch_pipeline/control.py::field: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/control.py', 'field') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/control.py', 'field') == ()


def test_sync_defs_utils_batch_pipeline_control_read_control_effects() -> None:
    """utils/batch_pipeline/control.py::read_control: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/control.py', 'read_control') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/control.py', 'read_control') == ()


def test_sync_defs_utils_batch_pipeline_control_activation_surface_effects() -> None:
    """utils/batch_pipeline/control.py::activation_surface: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/control.py', 'activation_surface') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/control.py', 'activation_surface') == ()


def test_sync_defs_utils_batch_pipeline_control_activate_effects() -> None:
    """utils/batch_pipeline/control.py::activate: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/control.py', 'activate') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/control.py', 'activate') == ()


def test_sync_defs_utils_batch_pipeline_control_migrate_legacy_effects() -> None:
    """utils/batch_pipeline/control.py::migrate_legacy: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/control.py', 'migrate_legacy') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/control.py', 'migrate_legacy') == ()


def test_sync_defs_utils_batch_pipeline_correctness_metrics_record_conflict_hold_effects() -> None:
    """utils/batch_pipeline/correctness_metrics.py::record_conflict_hold: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/correctness_metrics.py', 'record_conflict_hold') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/correctness_metrics.py', 'record_conflict_hold') == ()


def test_sync_defs_utils_batch_pipeline_correctness_metrics_enabled_effects() -> None:
    """utils/batch_pipeline/correctness_metrics.py::enabled: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/correctness_metrics.py', 'enabled') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/correctness_metrics.py', 'enabled') == ()


def test_sync_defs_utils_batch_pipeline_correctness_metrics_record_effects() -> None:
    """utils/batch_pipeline/correctness_metrics.py::record: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/correctness_metrics.py', 'record') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/correctness_metrics.py', 'record') == ()


def test_sync_defs_utils_batch_pipeline_correctness_metrics_record_labels_effects() -> None:
    """utils/batch_pipeline/correctness_metrics.py::record_labels: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/correctness_metrics.py', 'record_labels') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/correctness_metrics.py', 'record_labels') == ()


def test_sync_defs_utils_batch_pipeline_diarization_gate__finite_pair_effects() -> None:
    """utils/batch_pipeline/diarization_gate.py::_finite_pair: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/diarization_gate.py', '_finite_pair') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/diarization_gate.py', '_finite_pair') == ()


def test_sync_defs_utils_batch_pipeline_diarization_gate_speech_regions_effects() -> None:
    """utils/batch_pipeline/diarization_gate.py::speech_regions: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/diarization_gate.py', 'speech_regions') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/diarization_gate.py', 'speech_regions') == ()


def test_sync_defs_utils_batch_pipeline_diarization_gate_short_single_region_effects() -> None:
    """utils/batch_pipeline/diarization_gate.py::short_single_region: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/diarization_gate.py', 'short_single_region') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/diarization_gate.py', 'short_single_region') == ()


def test_sync_defs_utils_batch_pipeline_diarization_gate_plan_compaction_effects() -> None:
    """utils/batch_pipeline/diarization_gate.py::plan_compaction: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/diarization_gate.py', 'plan_compaction') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/diarization_gate.py', 'plan_compaction') == ()


def test_sync_defs_utils_batch_pipeline_diarization_gate_compact_effects() -> None:
    """utils/batch_pipeline/diarization_gate.py::compact: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/diarization_gate.py', 'compact') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/diarization_gate.py', 'compact') == ()


def test_sync_defs_utils_batch_pipeline_diarization_gate_map_back_effects() -> None:
    """utils/batch_pipeline/diarization_gate.py::map_back: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/diarization_gate.py', 'map_back') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/diarization_gate.py', 'map_back') == ()


def test_sync_defs_utils_batch_pipeline_diarization_gate_unassigned_word_count_effects() -> None:
    """utils/batch_pipeline/diarization_gate.py::unassigned_word_count: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/diarization_gate.py', 'unassigned_word_count') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/diarization_gate.py', 'unassigned_word_count') == ()


def test_sync_defs_utils_batch_pipeline_enrichment_run_enrichment_effects() -> None:
    """utils/batch_pipeline/enrichment.py::run_enrichment: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/enrichment.py', 'run_enrichment') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/enrichment.py', 'run_enrichment') == ()


def test_sync_defs_utils_batch_pipeline_errors_error_site_field_effects() -> None:
    """utils/batch_pipeline/errors.py::error_site_field: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/errors.py', 'error_site_field') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/errors.py', 'error_site_field') == ()


def test_sync_defs_utils_batch_pipeline_errors_validate_worker_failure_effects() -> None:
    """utils/batch_pipeline/errors.py::validate_worker_failure: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/errors.py', 'validate_worker_failure') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/errors.py', 'validate_worker_failure') == ()


def test_sync_defs_utils_batch_pipeline_errors_language_guard_redrive_failure_effects() -> None:
    """utils/batch_pipeline/errors.py::language_guard_redrive_failure: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/errors.py', 'language_guard_redrive_failure') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/errors.py', 'language_guard_redrive_failure') == ()


def test_sync_defs_utils_batch_pipeline_errors_empty_ladder_recovery_failure_effects() -> None:
    """utils/batch_pipeline/errors.py::empty_ladder_recovery_failure: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/errors.py', 'empty_ladder_recovery_failure') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/errors.py', 'empty_ladder_recovery_failure') == ()


def test_sync_defs_utils_batch_pipeline_errors_validation_disposition_failure_effects() -> None:
    """utils/batch_pipeline/errors.py::validation_disposition_failure: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/errors.py', 'validation_disposition_failure') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/errors.py', 'validation_disposition_failure') == ()


def test_sync_defs_utils_batch_pipeline_errors_validate_worker_failure_evidence_effects() -> None:
    """utils/batch_pipeline/errors.py::validate_worker_failure_evidence: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/errors.py', 'validate_worker_failure_evidence') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/errors.py', 'validate_worker_failure_evidence') == ()


def test_sync_defs_utils_batch_pipeline_gpu_overflow__submit_effects() -> None:
    """utils/batch_pipeline/gpu_overflow.py::_submit: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/gpu_overflow.py', '_submit') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/gpu_overflow.py', '_submit') == ()


def test_sync_defs_utils_batch_pipeline_gpu_overflow__fresh_sample_effects() -> None:
    """utils/batch_pipeline/gpu_overflow.py::_fresh_sample: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/gpu_overflow.py', '_fresh_sample') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/gpu_overflow.py', '_fresh_sample') == ()


def test_sync_defs_utils_batch_pipeline_gpu_overflow_saturated_effects() -> None:
    """utils/batch_pipeline/gpu_overflow.py::saturated: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/gpu_overflow.py', 'saturated') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/gpu_overflow.py', 'saturated') == ()


def test_sync_defs_utils_batch_pipeline_gpu_skip_metrics_register_on_effects() -> None:
    """utils/batch_pipeline/gpu_skip_metrics.py::register_on: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/gpu_skip_metrics.py', 'register_on') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/gpu_skip_metrics.py', 'register_on') == ()


def test_sync_defs_utils_batch_pipeline_gpu_skip_metrics_record_decision_effects() -> None:
    """utils/batch_pipeline/gpu_skip_metrics.py::record_decision: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/gpu_skip_metrics.py', 'record_decision') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/gpu_skip_metrics.py', 'record_decision') == ()


def test_sync_defs_utils_batch_pipeline_gpu_skip_metrics_record_compacted_unassigned_effects() -> None:
    """utils/batch_pipeline/gpu_skip_metrics.py::record_compacted_unassigned: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/gpu_skip_metrics.py', 'record_compacted_unassigned') == ()
    assert (
        fixture.ABLATED_effect_summary('utils/batch_pipeline/gpu_skip_metrics.py', 'record_compacted_unassigned') == ()
    )


def test_sync_defs_utils_batch_pipeline_gpu_skip_metrics_record_unit_diarization_effects() -> None:
    """utils/batch_pipeline/gpu_skip_metrics.py::record_unit_diarization: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/gpu_skip_metrics.py', 'record_unit_diarization') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/gpu_skip_metrics.py', 'record_unit_diarization') == ()


def test_sync_defs_utils_batch_pipeline_held_coverage_native_units_effects() -> None:
    """utils/batch_pipeline/held_coverage.py::native_units: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/held_coverage.py', 'native_units') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/held_coverage.py', 'native_units') == ()


def test_sync_defs_utils_batch_pipeline_intake__speech_windows_effects() -> None:
    """utils/batch_pipeline/intake.py::_speech_windows: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/intake.py', '_speech_windows') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/intake.py', '_speech_windows') == ()


def test_sync_defs_utils_batch_pipeline_intake__sampled_refusal_effects() -> None:
    """utils/batch_pipeline/intake.py::_sampled_refusal: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/intake.py', '_sampled_refusal') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/intake.py', '_sampled_refusal') == ()


def test_sync_defs_utils_batch_pipeline_intake__next_unit_effects() -> None:
    """utils/batch_pipeline/intake.py::_next_unit: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/intake.py', '_next_unit') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/intake.py', '_next_unit') == ()


def test_sync_defs_utils_batch_pipeline_intake__private_sample_paths_effects() -> None:
    """utils/batch_pipeline/intake.py::_private_sample_paths: effects fixed=('file_io',) ablated=('file_io',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/intake.py', '_private_sample_paths') == ('file_io',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/intake.py', '_private_sample_paths') == ('file_io',)


def test_sync_defs_utils_batch_pipeline_intake__open_operator_intent_effects() -> None:
    """utils/batch_pipeline/intake.py::_open_operator_intent: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/intake.py', '_open_operator_intent') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/intake.py', '_open_operator_intent') == ()


def test_sync_defs_utils_batch_pipeline_intake__terminally_held_effects() -> None:
    """utils/batch_pipeline/intake.py::_terminally_held: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/intake.py', '_terminally_held') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/intake.py', '_terminally_held') == ()


def test_sync_defs_utils_batch_pipeline_intake__held_status_effects() -> None:
    """utils/batch_pipeline/intake.py::_held_status: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/intake.py', '_held_status') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/intake.py', '_held_status') == ()


def test_sync_defs_utils_batch_pipeline_intake__deleted_conversation_status_effects() -> None:
    """utils/batch_pipeline/intake.py::_deleted_conversation_status: effects fixed=() ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/intake.py', '_deleted_conversation_status') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/intake.py', '_deleted_conversation_status') == (
        'db_calls',
    )


def test_sync_defs_utils_batch_pipeline_intake__only_deleted_total_effects() -> None:
    """utils/batch_pipeline/intake.py::_only_deleted_total: effects fixed=() ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/intake.py', '_only_deleted_total') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/intake.py', '_only_deleted_total') == ('db_calls',)


def test_sync_defs_utils_batch_pipeline_intake_durable_status_effects() -> None:
    """utils/batch_pipeline/intake.py::durable_status: effects fixed=() ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/intake.py', 'durable_status') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/intake.py', 'durable_status') == ('db_calls',)


def test_sync_defs_utils_batch_pipeline_intake_start_response_effects() -> None:
    """utils/batch_pipeline/intake.py::start_response: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/intake.py', 'start_response') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/intake.py', 'start_response') == ()


def test_sync_defs_utils_batch_pipeline_intake_stranded_adopter_effects() -> None:
    """utils/batch_pipeline/intake.py::stranded_adopter: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/intake.py', 'stranded_adopter') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/intake.py', 'stranded_adopter') == ()


def test_sync_defs_utils_batch_pipeline_intake_privacy_blocked_response_effects() -> None:
    """utils/batch_pipeline/intake.py::privacy_blocked_response: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/intake.py', 'privacy_blocked_response') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/intake.py', 'privacy_blocked_response') == ()


def test_sync_defs_utils_batch_pipeline_intake__repair_owner_matches_effects() -> None:
    """utils/batch_pipeline/intake.py::_repair_owner_matches: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/intake.py', '_repair_owner_matches') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/intake.py', '_repair_owner_matches') == ()


def test_sync_defs_utils_batch_pipeline_intake_repair_upload_owner_matches_effects() -> None:
    """utils/batch_pipeline/intake.py::repair_upload_owner_matches: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/intake.py', 'repair_upload_owner_matches') == (
        'db_calls',
    )
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/intake.py', 'repair_upload_owner_matches') == (
        'db_calls',
    )


def test_sync_defs_utils_batch_pipeline_intake_get_durable_job_status_effects() -> None:
    """utils/batch_pipeline/intake.py::get_durable_job_status: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/intake.py', 'get_durable_job_status') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/intake.py', 'get_durable_job_status') == ('db_calls',)


def test_sync_defs_utils_batch_pipeline_intake_outcome_record_upload_outcome_effects() -> None:
    """utils/batch_pipeline/intake_outcome.py::record_upload_outcome: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/intake_outcome.py', 'record_upload_outcome') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/intake_outcome.py', 'record_upload_outcome') == ()


def test_sync_defs_utils_batch_pipeline_intake_outcome_legacy_landing_outcome_effects() -> None:
    """utils/batch_pipeline/intake_outcome.py::legacy_landing_outcome: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/intake_outcome.py', 'legacy_landing_outcome') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/intake_outcome.py', 'legacy_landing_outcome') == ()


def test_sync_defs_utils_batch_pipeline_language_metrics_record_sample_window_effects() -> None:
    """utils/batch_pipeline/language_metrics.py::record_sample_window: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/language_metrics.py', 'record_sample_window') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/language_metrics.py', 'record_sample_window') == ()


def test_sync_defs_utils_batch_pipeline_language_metrics_record_route_effects() -> None:
    """utils/batch_pipeline/language_metrics.py::record_route: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/language_metrics.py', 'record_route') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/language_metrics.py', 'record_route') == ()


def test_sync_defs_utils_batch_pipeline_language_metrics_record_admission_exclusion_effects() -> None:
    """utils/batch_pipeline/language_metrics.py::record_admission_exclusion: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/language_metrics.py', 'record_admission_exclusion') == ()
    assert (
        fixture.ABLATED_effect_summary('utils/batch_pipeline/language_metrics.py', 'record_admission_exclusion') == ()
    )


def test_sync_defs_utils_batch_pipeline_language_receipt_bounded_language_effects() -> None:
    """utils/batch_pipeline/language_receipt.py::bounded_language: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/language_receipt.py', 'bounded_language') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/language_receipt.py', 'bounded_language') == ()


def test_sync_defs_utils_batch_pipeline_language_receipt_expected_script_effects() -> None:
    """utils/batch_pipeline/language_receipt.py::expected_script: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/language_receipt.py', 'expected_script') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/language_receipt.py', 'expected_script') == ()


def test_sync_defs_utils_batch_pipeline_language_receipt_script_counts_effects() -> None:
    """utils/batch_pipeline/language_receipt.py::script_counts: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/language_receipt.py', 'script_counts') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/language_receipt.py', 'script_counts') == ()


def test_sync_defs_utils_batch_pipeline_language_receipt_observation_effects() -> None:
    """utils/batch_pipeline/language_receipt.py::observation: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/language_receipt.py', 'observation') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/language_receipt.py', 'observation') == ()


def test_sync_defs_utils_batch_pipeline_language_receipt_admission_effects() -> None:
    """utils/batch_pipeline/language_receipt.py::admission: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/language_receipt.py', 'admission') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/language_receipt.py', 'admission') == ()


def test_sync_defs_utils_batch_pipeline_language_receipt_auto_language_cohort_effects() -> None:
    """utils/batch_pipeline/language_receipt.py::auto_language_cohort: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/language_receipt.py', 'auto_language_cohort') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/language_receipt.py', 'auto_language_cohort') == ()


def test_sync_defs_utils_batch_pipeline_language_receipt_validate_admission_effects() -> None:
    """utils/batch_pipeline/language_receipt.py::validate_admission: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/language_receipt.py', 'validate_admission') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/language_receipt.py', 'validate_admission') == ()


def test_sync_defs_utils_batch_pipeline_language_receipt_validate_effects() -> None:
    """utils/batch_pipeline/language_receipt.py::validate: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/language_receipt.py', 'validate') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/language_receipt.py', 'validate') == ()


def test_sync_defs_utils_batch_pipeline_language_shadow_first_unit_effects() -> None:
    """utils/batch_pipeline/language_shadow.py::first_unit: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/language_shadow.py', 'first_unit') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/language_shadow.py', 'first_unit') == ()


def test_sync_defs_utils_batch_pipeline_language_shadow_compare_effects() -> None:
    """utils/batch_pipeline/language_shadow.py::compare: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/language_shadow.py', 'compare') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/language_shadow.py', 'compare') == ()


def test_sync_defs_utils_batch_pipeline_leaf_timings_active_effects() -> None:
    """utils/batch_pipeline/leaf_timings.py::active: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/leaf_timings.py', 'active') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/leaf_timings.py', 'active') == ()


def test_sync_defs_utils_batch_pipeline_leaf_timings_measure_effects() -> None:
    """utils/batch_pipeline/leaf_timings.py::measure: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/leaf_timings.py', 'measure') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/leaf_timings.py', 'measure') == ()


def test_sync_defs_utils_batch_pipeline_leaf_timings_call_effects() -> None:
    """utils/batch_pipeline/leaf_timings.py::call: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/leaf_timings.py', 'call') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/leaf_timings.py', 'call') == ()


def test_sync_defs_utils_batch_pipeline_leaf_timings_embedding_hook_effects() -> None:
    """utils/batch_pipeline/leaf_timings.py::embedding_hook: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/leaf_timings.py', 'embedding_hook') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/leaf_timings.py', 'embedding_hook') == ()


def test_sync_defs_utils_batch_pipeline_live_reserve_recording_effects() -> None:
    """utils/batch_pipeline/live.py::reserve_recording: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/live.py', 'reserve_recording') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/live.py', 'reserve_recording') == ('db_calls',)


def test_sync_defs_utils_batch_pipeline_live_register_recording_effects() -> None:
    """utils/batch_pipeline/live.py::register_recording: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/live.py', 'register_recording') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/live.py', 'register_recording') == ('db_calls',)


def test_sync_defs_utils_batch_pipeline_live_retained_record_units_effects() -> None:
    """utils/batch_pipeline/live.py::retained_record_units: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/live.py', 'retained_record_units') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/live.py', 'retained_record_units') == ()


def test_sync_defs_utils_batch_pipeline_live_projection_replace_record_effects() -> None:
    """utils/batch_pipeline/live_projection.py::replace_record: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/live_projection.py', 'replace_record') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/live_projection.py', 'replace_record') == ()


def test_sync_defs_utils_batch_pipeline_live_projection__placed_effects() -> None:
    """utils/batch_pipeline/live_projection.py::_placed: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/live_projection.py', '_placed') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/live_projection.py', '_placed') == ()


def test_sync_defs_utils_batch_pipeline_live_projection__has_refs_effects() -> None:
    """utils/batch_pipeline/live_projection.py::_has_refs: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/live_projection.py', '_has_refs') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/live_projection.py', '_has_refs') == ()


def test_sync_defs_utils_batch_pipeline_live_upload__pending_effects() -> None:
    """utils/batch_pipeline/live_upload.py::_pending: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/live_upload.py', '_pending') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/live_upload.py', '_pending') == ()


def test_sync_defs_utils_batch_pipeline_live_upload__pcm_effects() -> None:
    """utils/batch_pipeline/live_upload.py::_pcm: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/live_upload.py', '_pcm') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/live_upload.py', '_pcm') == ()


def test_sync_defs_utils_batch_pipeline_live_upload__covered_effects() -> None:
    """utils/batch_pipeline/live_upload.py::_covered: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/live_upload.py', '_covered') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/live_upload.py', '_covered') == ()


def test_sync_defs_utils_batch_pipeline_merge__wait_bucket_effects() -> None:
    """utils/batch_pipeline/merge.py::_wait_bucket: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/merge.py', '_wait_bucket') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/merge.py', '_wait_bucket') == ()


def test_sync_defs_utils_batch_pipeline_merge__catch_up_effects() -> None:
    """utils/batch_pipeline/merge.py::_catch_up: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/merge.py', '_catch_up') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/merge.py', '_catch_up') == ()


def test_sync_defs_utils_batch_pipeline_merge__fresh_pick_effects() -> None:
    """utils/batch_pipeline/merge.py::_fresh_pick: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/merge.py', '_fresh_pick') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/merge.py', '_fresh_pick') == ()


def test_sync_defs_utils_batch_pipeline_merge__unprojected_effects() -> None:
    """utils/batch_pipeline/merge.py::_unprojected: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/merge.py', '_unprojected') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/merge.py', '_unprojected') == ()


def test_sync_defs_utils_batch_pipeline_merge__awaiting_projection_effects() -> None:
    """utils/batch_pipeline/merge.py::_awaiting_projection: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/merge.py', '_awaiting_projection') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/merge.py', '_awaiting_projection') == ()


def test_sync_defs_utils_batch_pipeline_merge__append_committed_entry_effects() -> None:
    """utils/batch_pipeline/merge.py::_append_committed_entry: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/merge.py', '_append_committed_entry') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/merge.py', '_append_committed_entry') == ()


def test_sync_defs_utils_batch_pipeline_metrics_age_seconds_effects() -> None:
    """utils/batch_pipeline/metrics.py::age_seconds: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/metrics.py', 'age_seconds') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/metrics.py', 'age_seconds') == ()


def test_sync_defs_utils_batch_pipeline_projection_error_type_effects() -> None:
    """utils/batch_pipeline/projection.py::error_type: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/projection.py', 'error_type') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/projection.py', 'error_type') == ()


def test_sync_defs_utils_batch_pipeline_projection_fence_reason_field_effects() -> None:
    """utils/batch_pipeline/projection.py::fence_reason_field: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/projection.py', 'fence_reason_field') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/projection.py', 'fence_reason_field') == ()


def test_sync_defs_utils_batch_pipeline_projection_projection_block_reason_effects() -> None:
    """utils/batch_pipeline/projection.py::projection_block_reason: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/projection.py', 'projection_block_reason') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/projection.py', 'projection_block_reason') == ()


def test_sync_defs_utils_batch_pipeline_projection_projection_exception_transient_effects() -> None:
    """utils/batch_pipeline/projection.py::projection_exception_transient: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/projection.py', 'projection_exception_transient') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/projection.py', 'projection_exception_transient') == ()


def test_sync_defs_utils_batch_pipeline_projection_payload_contract_violation_effects() -> None:
    """utils/batch_pipeline/projection.py::payload_contract_violation: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/projection.py', 'payload_contract_violation') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/projection.py', 'payload_contract_violation') == ()


def test_sync_defs_utils_batch_pipeline_projection_head_holds_without_retry_effects() -> None:
    """utils/batch_pipeline/projection.py::head_holds_without_retry: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/projection.py', 'head_holds_without_retry') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/projection.py', 'head_holds_without_retry') == ()


def test_sync_defs_utils_batch_pipeline_projection_head_retry_bound_exceeded_effects() -> None:
    """utils/batch_pipeline/projection.py::head_retry_bound_exceeded: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/projection.py', 'head_retry_bound_exceeded') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/projection.py', 'head_retry_bound_exceeded') == ()


def test_sync_defs_utils_batch_pipeline_projection_projection_phase_effects() -> None:
    """utils/batch_pipeline/projection.py::projection_phase: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/projection.py', 'projection_phase') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/projection.py', 'projection_phase') == ()


def test_sync_defs_utils_batch_pipeline_projection_build_incoming_effects() -> None:
    """utils/batch_pipeline/projection.py::build_incoming: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/projection.py', 'build_incoming') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/projection.py', 'build_incoming') == ()


def test_sync_defs_utils_batch_pipeline_projection_publish_client_completion_effects() -> None:
    """utils/batch_pipeline/projection.py::publish_client_completion: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/projection.py', 'publish_client_completion') == (
        'db_calls',
    )
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/projection.py', 'publish_client_completion') == (
        'db_calls',
    )


def test_sync_defs_utils_batch_pipeline_projection_record_speech_step_effects() -> None:
    """utils/batch_pipeline/projection.py::record_speech_step: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/projection.py', 'record_speech_step') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/projection.py', 'record_speech_step') == ()


def test_sync_defs_utils_batch_pipeline_projection_reissue_window_seconds_effects() -> None:
    """utils/batch_pipeline/projection.py::reissue_window_seconds: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/projection.py', 'reissue_window_seconds') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/projection.py', 'reissue_window_seconds') == ()


def test_sync_defs_utils_batch_pipeline_projection_record_speech_steps_effects() -> None:
    """utils/batch_pipeline/projection.py::record_speech_steps: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/projection.py', 'record_speech_steps') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/projection.py', 'record_speech_steps') == ()


def test_sync_defs_utils_batch_pipeline_projection_record_speech_effects() -> None:
    """utils/batch_pipeline/projection.py::record_speech: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/projection.py', 'record_speech') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/projection.py', 'record_speech') == ()


def test_sync_defs_utils_batch_pipeline_projection_disposition_mirror_assignment_effects() -> None:
    """utils/batch_pipeline/projection_disposition.py::mirror_assignment: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/projection_disposition.py', 'mirror_assignment') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/projection_disposition.py', 'mirror_assignment') == ()


def test_sync_defs_utils_batch_pipeline_projection_disposition_persist_disposition_effects() -> None:
    """utils/batch_pipeline/projection_disposition.py::persist_disposition: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/projection_disposition.py', 'persist_disposition') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/projection_disposition.py', 'persist_disposition') == ()


def test_sync_defs_utils_batch_pipeline_projection_hold_policy_quarantines_assignment_conflict_effects() -> None:
    """utils/batch_pipeline/projection_hold_policy.py::quarantines_assignment_conflict: effects fixed=() ablated=()."""
    assert (
        fixture.FIXED_effect_summary(
            'utils/batch_pipeline/projection_hold_policy.py', 'quarantines_assignment_conflict'
        )
        == ()
    )
    assert (
        fixture.ABLATED_effect_summary(
            'utils/batch_pipeline/projection_hold_policy.py', 'quarantines_assignment_conflict'
        )
        == ()
    )


def test_sync_defs_utils_batch_pipeline_projection_hold_policy_log_conflict_hold_effects() -> None:
    """utils/batch_pipeline/projection_hold_policy.py::log_conflict_hold: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/projection_hold_policy.py', 'log_conflict_hold') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/projection_hold_policy.py', 'log_conflict_hold') == ()


def test_sync_defs_utils_batch_pipeline_projection_parts_stamp_speaker_effects() -> None:
    """utils/batch_pipeline/projection_parts.py::stamp_speaker: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/projection_parts.py', 'stamp_speaker') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/projection_parts.py', 'stamp_speaker') == ()


def test_sync_defs_utils_batch_pipeline_projection_parts_bounded_projection_words_effects() -> None:
    """utils/batch_pipeline/projection_parts.py::bounded_projection_words: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/projection_parts.py', 'bounded_projection_words') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/projection_parts.py', 'bounded_projection_words') == ()


def test_sync_defs_utils_batch_pipeline_projection_parts_align_projection_words_effects() -> None:
    """utils/batch_pipeline/projection_parts.py::align_projection_words: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/projection_parts.py', 'align_projection_words') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/projection_parts.py', 'align_projection_words') == ()


def test_sync_defs_utils_batch_pipeline_projection_parts_split_result_effects() -> None:
    """utils/batch_pipeline/projection_parts.py::split_result: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/projection_parts.py', 'split_result') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/projection_parts.py', 'split_result') == ()


def test_sync_defs_utils_batch_pipeline_projection_privacy_settle_refusals_effects() -> None:
    """utils/batch_pipeline/projection_privacy.py::settle_refusals: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/projection_privacy.py', 'settle_refusals') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/projection_privacy.py', 'settle_refusals') == ()


def test_sync_defs_utils_batch_pipeline_projection_repair_plan_owner_effects() -> None:
    """utils/batch_pipeline/projection_repair.py::plan_owner: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/projection_repair.py', 'plan_owner') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/projection_repair.py', 'plan_owner') == ('db_calls',)


def test_sync_defs_utils_batch_pipeline_projection_repair_apply_owner_effects() -> None:
    """utils/batch_pipeline/projection_repair.py::apply_owner: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/projection_repair.py', 'apply_owner') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/projection_repair.py', 'apply_owner') == ('db_calls',)


def test_sync_defs_utils_batch_pipeline_projection_segments_projection_segments_effects() -> None:
    """utils/batch_pipeline/projection_segments.py::projection_segments: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/projection_segments.py', 'projection_segments') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/projection_segments.py', 'projection_segments') == ()


def test_sync_defs_utils_batch_pipeline_provider_stt_attempts_of_effects() -> None:
    """utils/batch_pipeline/provider_stt.py::attempts_of: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/provider_stt.py', 'attempts_of') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/provider_stt.py', 'attempts_of') == ()


def test_sync_defs_utils_batch_pipeline_provider_stt__exhausted_recovery_state_effects() -> None:
    """utils/batch_pipeline/provider_stt.py::_exhausted_recovery_state: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/provider_stt.py', '_exhausted_recovery_state') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/provider_stt.py', '_exhausted_recovery_state') == ()


def test_sync_defs_utils_batch_pipeline_provider_stt_bounding_attempts_effects() -> None:
    """utils/batch_pipeline/provider_stt.py::bounding_attempts: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/provider_stt.py', 'bounding_attempts') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/provider_stt.py', 'bounding_attempts') == ()


def test_sync_defs_utils_batch_pipeline_provider_stt__can_attempt_effects() -> None:
    """utils/batch_pipeline/provider_stt.py::_can_attempt: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/provider_stt.py', '_can_attempt') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/provider_stt.py', '_can_attempt') == ()


def test_sync_defs_utils_batch_pipeline_provider_stt__settled_effects() -> None:
    """utils/batch_pipeline/provider_stt.py::_settled: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/provider_stt.py', '_settled') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/provider_stt.py', '_settled') == ()


def test_sync_defs_utils_batch_pipeline_provider_stt_attempt_outcome_for_effects() -> None:
    """utils/batch_pipeline/provider_stt.py::attempt_outcome_for: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/provider_stt.py', 'attempt_outcome_for') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/provider_stt.py', 'attempt_outcome_for') == ()


def test_sync_defs_utils_batch_pipeline_provider_stt__record_held_vad_effects() -> None:
    """utils/batch_pipeline/provider_stt.py::_record_held_vad: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/provider_stt.py', '_record_held_vad') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/provider_stt.py', '_record_held_vad') == ()


def test_sync_defs_utils_batch_pipeline_provider_stt__speech_seconds_effects() -> None:
    """utils/batch_pipeline/provider_stt.py::_speech_seconds: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/provider_stt.py', '_speech_seconds') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/provider_stt.py', '_speech_seconds') == ()


def test_sync_defs_utils_batch_pipeline_provider_stt__wav_effects() -> None:
    """utils/batch_pipeline/provider_stt.py::_wav: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/provider_stt.py', '_wav') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/provider_stt.py', '_wav') == ()


def test_sync_defs_utils_batch_pipeline_provider_stt_vendor_turns_effects() -> None:
    """utils/batch_pipeline/provider_stt.py::vendor_turns: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/provider_stt.py', 'vendor_turns') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/provider_stt.py', 'vendor_turns') == ()


def test_sync_defs_utils_batch_pipeline_provider_stt_transcribe_effects() -> None:
    """utils/batch_pipeline/provider_stt.py::transcribe: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/provider_stt.py', 'transcribe') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/provider_stt.py', 'transcribe') == ()


def test_sync_defs_utils_batch_pipeline_provider_stt__default_allowed_effects() -> None:
    """utils/batch_pipeline/provider_stt.py::_default_allowed: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/provider_stt.py', '_default_allowed') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/provider_stt.py', '_default_allowed') == ()


def test_sync_defs_utils_batch_pipeline_provider_stt__default_health_effects() -> None:
    """utils/batch_pipeline/provider_stt.py::_default_health: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/provider_stt.py', '_default_health') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/provider_stt.py', '_default_health') == ()


def test_sync_defs_utils_batch_pipeline_provider_stt__default_armed_effects() -> None:
    """utils/batch_pipeline/provider_stt.py::_default_armed: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/provider_stt.py', '_default_armed') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/provider_stt.py', '_default_armed') == ()


def test_sync_defs_utils_batch_pipeline_provider_stt__default_failover_routes_effects() -> None:
    """utils/batch_pipeline/provider_stt.py::_default_failover_routes: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/provider_stt.py', '_default_failover_routes') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/provider_stt.py', '_default_failover_routes') == ()


def test_sync_defs_utils_batch_pipeline_provider_stt__service_stage_effects() -> None:
    """utils/batch_pipeline/provider_stt.py::_service_stage: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/provider_stt.py', '_service_stage') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/provider_stt.py', '_service_stage') == ('db_calls',)


def test_sync_defs_utils_batch_pipeline_provider_stt_admission_resolve_route_effects() -> None:
    """utils/batch_pipeline/provider_stt_admission.py::resolve_route: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/provider_stt_admission.py', 'resolve_route') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/provider_stt_admission.py', 'resolve_route') == ()


def test_sync_defs_utils_batch_pipeline_provider_stt_admission_enqueue_in_transaction_effects() -> None:
    """utils/batch_pipeline/provider_stt_admission.py::enqueue_in_transaction: effects fixed=() ablated=()."""
    assert (
        fixture.FIXED_effect_summary('utils/batch_pipeline/provider_stt_admission.py', 'enqueue_in_transaction') == ()
    )
    assert (
        fixture.ABLATED_effect_summary('utils/batch_pipeline/provider_stt_admission.py', 'enqueue_in_transaction') == ()
    )


def test_sync_defs_utils_batch_pipeline_provider_stt_admission_provider_enqueue_effects() -> None:
    """utils/batch_pipeline/provider_stt_admission.py::provider_enqueue: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/provider_stt_admission.py', 'provider_enqueue') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/provider_stt_admission.py', 'provider_enqueue') == ()


def test_sync_defs_utils_batch_pipeline_pump_deferred_drain_delay_effects() -> None:
    """utils/batch_pipeline/pump.py::deferred_drain_delay: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/pump.py', 'deferred_drain_delay') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/pump.py', 'deferred_drain_delay') == ()


def test_sync_defs_utils_batch_pipeline_pump_contention_retry_after_effects() -> None:
    """utils/batch_pipeline/pump.py::contention_retry_after: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/pump.py', 'contention_retry_after') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/pump.py', 'contention_retry_after') == ()


def test_sync_defs_utils_batch_pipeline_pump_publication_restrike_delay_effects() -> None:
    """utils/batch_pipeline/pump.py::publication_restrike_delay: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/pump.py', 'publication_restrike_delay') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/pump.py', 'publication_restrike_delay') == ()


def test_sync_defs_utils_batch_pipeline_pump_publication_loss_is_contention_effects() -> None:
    """utils/batch_pipeline/pump.py::publication_loss_is_contention: effects fixed=() ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/pump.py', 'publication_loss_is_contention') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/pump.py', 'publication_loss_is_contention') == (
        'db_calls',
    )


def test_sync_defs_utils_batch_pipeline_quarantine_recovery_log_failure_effects() -> None:
    """utils/batch_pipeline/quarantine_recovery.py::log_failure: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/quarantine_recovery.py', 'log_failure') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/quarantine_recovery.py', 'log_failure') == ()


def test_sync_defs_utils_batch_pipeline_quarantine_recovery_log_terminal_empty_effects() -> None:
    """utils/batch_pipeline/quarantine_recovery.py::log_terminal_empty: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/quarantine_recovery.py', 'log_terminal_empty') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/quarantine_recovery.py', 'log_terminal_empty') == ()


def test_sync_defs_utils_batch_pipeline_quarantine_recovery_metered_effects() -> None:
    """utils/batch_pipeline/quarantine_recovery.py::metered: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/quarantine_recovery.py', 'metered') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/quarantine_recovery.py', 'metered') == ()


def test_sync_defs_utils_batch_pipeline_quarantine_recovery_record_accepted_effects() -> None:
    """utils/batch_pipeline/quarantine_recovery.py::record_accepted: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/quarantine_recovery.py', 'record_accepted') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/quarantine_recovery.py', 'record_accepted') == ()


def test_sync_defs_utils_batch_pipeline_quarantine_recovery_second_provider_eligible_effects() -> None:
    """utils/batch_pipeline/quarantine_recovery.py::second_provider_eligible: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/quarantine_recovery.py', 'second_provider_eligible') == ()
    assert (
        fixture.ABLATED_effect_summary('utils/batch_pipeline/quarantine_recovery.py', 'second_provider_eligible') == ()
    )


def test_sync_defs_utils_batch_pipeline_record_barrier_validate_record_tail_effects() -> None:
    """utils/batch_pipeline/record_barrier.py::validate_record_tail: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_barrier.py', 'validate_record_tail') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_barrier.py', 'validate_record_tail') == ()


def test_sync_defs_utils_batch_pipeline_record_language_classify_probe_effects() -> None:
    """utils/batch_pipeline/record_language.py::classify_probe: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_language.py', 'classify_probe') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_language.py', 'classify_probe') == ()


def test_sync_defs_utils_batch_pipeline_record_partial_event_effects() -> None:
    """utils/batch_pipeline/record_partial.py::event: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_partial.py', 'event') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_partial.py', 'event') == ()


def test_sync_defs_utils_batch_pipeline_record_partial_record_failure_effects() -> None:
    """utils/batch_pipeline/record_partial.py::record_failure: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_partial.py', 'record_failure') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_partial.py', 'record_failure') == ()


def test_sync_defs_utils_batch_pipeline_record_partial_seed_for_effects() -> None:
    """utils/batch_pipeline/record_partial.py::seed_for: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_partial.py', 'seed_for') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_partial.py', 'seed_for') == ()


def test_sync_defs_utils_batch_pipeline_record_partial_page_content_effects() -> None:
    """utils/batch_pipeline/record_partial.py::page_content: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_partial.py', 'page_content') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_partial.py', 'page_content') == ()


def test_sync_defs_utils_batch_pipeline_record_partial_unit_coverage_effects() -> None:
    """utils/batch_pipeline/record_partial.py::unit_coverage: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_partial.py', 'unit_coverage') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_partial.py', 'unit_coverage') == ()


def test_sync_defs_utils_batch_pipeline_record_partial_audio_digest_effects() -> None:
    """utils/batch_pipeline/record_partial_audio.py::digest: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_partial_audio.py', 'digest') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_partial_audio.py', 'digest') == ()


def test_sync_defs_utils_batch_pipeline_record_partial_audio_inventory_digest_effects() -> None:
    """utils/batch_pipeline/record_partial_audio.py::inventory_digest: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_partial_audio.py', 'inventory_digest') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_partial_audio.py', 'inventory_digest') == ()


def test_sync_defs_utils_batch_pipeline_record_partial_audio_union_effects() -> None:
    """utils/batch_pipeline/record_partial_audio.py::union: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_partial_audio.py', 'union') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_partial_audio.py', 'union') == ()


def test_sync_defs_utils_batch_pipeline_record_partial_audio_missing_units_effects() -> None:
    """utils/batch_pipeline/record_partial_audio.py::missing_units: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_partial_audio.py', 'missing_units') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_partial_audio.py', 'missing_units') == ()


def test_sync_defs_utils_batch_pipeline_record_producer_proof__timestamp_effects() -> None:
    """utils/batch_pipeline/record_producer_proof.py::_timestamp: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_producer_proof.py', '_timestamp') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_producer_proof.py', '_timestamp') == ()


def test_sync_defs_utils_batch_pipeline_record_producer_proof_load_pusher_pod_proof_effects() -> None:
    """utils/batch_pipeline/record_producer_proof.py::load_pusher_pod_proof: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_producer_proof.py', 'load_pusher_pod_proof') == ()
    assert (
        fixture.ABLATED_effect_summary('utils/batch_pipeline/record_producer_proof.py', 'load_pusher_pod_proof') == ()
    )


def test_sync_defs_utils_batch_pipeline_record_producer_proof_parse_pusher_pod_proof_effects() -> None:
    """utils/batch_pipeline/record_producer_proof.py::parse_pusher_pod_proof: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_producer_proof.py', 'parse_pusher_pod_proof') == ()
    assert (
        fixture.ABLATED_effect_summary('utils/batch_pipeline/record_producer_proof.py', 'parse_pusher_pod_proof') == ()
    )


def test_sync_defs_utils_batch_pipeline_record_producer_proof_producer_tokens_dead_effects() -> None:
    """utils/batch_pipeline/record_producer_proof.py::producer_tokens_dead: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_producer_proof.py', 'producer_tokens_dead') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_producer_proof.py', 'producer_tokens_dead') == ()


def test_sync_defs_utils_batch_pipeline_record_provider_admit_record_units_effects() -> None:
    """utils/batch_pipeline/record_provider.py::admit_record_units: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_provider.py', 'admit_record_units') == (
        'db_calls',
    )
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_provider.py', 'admit_record_units') == (
        'db_calls',
    )


def test_sync_defs_utils_batch_pipeline_record_seal_cluster_repair_silent_dependencies_effects() -> None:
    """utils/batch_pipeline/record_seal_cluster_repair.py::silent_dependencies: effects fixed=('file_io',) ablated=('file_io',)."""
    assert fixture.FIXED_effect_summary(
        'utils/batch_pipeline/record_seal_cluster_repair.py', 'silent_dependencies'
    ) == ('file_io',)
    assert fixture.ABLATED_effect_summary(
        'utils/batch_pipeline/record_seal_cluster_repair.py', 'silent_dependencies'
    ) == ('file_io',)


def test_sync_defs_utils_batch_pipeline_record_seal_cluster_repair_repair_one_effects() -> None:
    """utils/batch_pipeline/record_seal_cluster_repair.py::repair_one: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_cluster_repair.py', 'repair_one') == (
        'db_calls',
    )
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_cluster_repair.py', 'repair_one') == (
        'db_calls',
    )


def test_sync_defs_utils_batch_pipeline_record_seal_cluster_repair_discover_effects() -> None:
    """utils/batch_pipeline/record_seal_cluster_repair.py::discover: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_cluster_repair.py', 'discover') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_cluster_repair.py', 'discover') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_cluster_repair_launch_row_effects() -> None:
    """utils/batch_pipeline/record_seal_cluster_repair.py::launch_row: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_cluster_repair.py', 'launch_row') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_cluster_repair.py', 'launch_row') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_cluster_repair_stop_effects() -> None:
    """utils/batch_pipeline/record_seal_cluster_repair.py::stop: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_cluster_repair.py', 'stop') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_cluster_repair.py', 'stop') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_cluster_repair_coordinate_effects() -> None:
    """utils/batch_pipeline/record_seal_cluster_repair.py::coordinate: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_cluster_repair.py', 'coordinate') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_cluster_repair.py', 'coordinate') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_cluster_repair_row_main_effects() -> None:
    """utils/batch_pipeline/record_seal_cluster_repair.py::row_main: effects fixed=('db_calls', 'file_io') ablated=('db_calls', 'file_io')."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_cluster_repair.py', 'row_main') == (
        'db_calls',
        'file_io',
    )
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_cluster_repair.py', 'row_main') == (
        'db_calls',
        'file_io',
    )


def test_sync_defs_utils_batch_pipeline_record_seal_cluster_repair_run_effects() -> None:
    """utils/batch_pipeline/record_seal_cluster_repair.py::run: effects fixed=('db_calls', 'file_io') ablated=('db_calls', 'file_io')."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_cluster_repair.py', 'run') == (
        'db_calls',
        'file_io',
    )
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_cluster_repair.py', 'run') == (
        'db_calls',
        'file_io',
    )


def test_sync_defs_utils_batch_pipeline_record_seal_nojob_validate_server_flags_effects() -> None:
    """utils/batch_pipeline/record_seal_nojob.py::validate_server_flags: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_nojob.py', 'validate_server_flags') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_nojob.py', 'validate_server_flags') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_nojob_row_state_effects() -> None:
    """utils/batch_pipeline/record_seal_nojob.py::row_state: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_nojob.py', 'row_state') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_nojob.py', 'row_state') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_nojob_conversation_path_effects() -> None:
    """utils/batch_pipeline/record_seal_nojob.py::conversation_path: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_nojob.py', 'conversation_path') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_nojob.py', 'conversation_path') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_nojob_discover_effects() -> None:
    """utils/batch_pipeline/record_seal_nojob.py::discover: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_nojob.py', 'discover') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_nojob.py', 'discover') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_nojob_refusal_effects() -> None:
    """utils/batch_pipeline/record_seal_nojob.py::refusal: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_nojob.py', 'refusal') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_nojob.py', 'refusal') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_nojob_registration_effects() -> None:
    """utils/batch_pipeline/record_seal_nojob.py::registration: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_nojob.py', 'registration') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_nojob.py', 'registration') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_nojob_plan_backfill_effects() -> None:
    """utils/batch_pipeline/record_seal_nojob.py::plan_backfill: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_nojob.py', 'plan_backfill') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_nojob.py', 'plan_backfill') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_nojob_apply_backfill_effects() -> None:
    """utils/batch_pipeline/record_seal_nojob.py::apply_backfill: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_nojob.py', 'apply_backfill') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_nojob.py', 'apply_backfill') == (
        'db_calls',
    )


def test_sync_defs_utils_batch_pipeline_record_seal_nojob_summary_effects() -> None:
    """utils/batch_pipeline/record_seal_nojob.py::summary: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_nojob.py', 'summary') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_nojob.py', 'summary') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_reasons_tail_gap_bucket_effects() -> None:
    """utils/batch_pipeline/record_seal_reasons.py::tail_gap_bucket: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_reasons.py', 'tail_gap_bucket') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_reasons.py', 'tail_gap_bucket') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_reasons_proof_reason_effects() -> None:
    """utils/batch_pipeline/record_seal_reasons.py::proof_reason: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_reasons.py', 'proof_reason') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_reasons.py', 'proof_reason') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_reasons_proof_diagnostics_effects() -> None:
    """utils/batch_pipeline/record_seal_reasons.py::proof_diagnostics: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_reasons.py', 'proof_diagnostics') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_reasons.py', 'proof_diagnostics') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_repair_seal_row_state_effects() -> None:
    """utils/batch_pipeline/record_seal_repair.py::seal_row_state: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_repair.py', 'seal_row_state') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_repair.py', 'seal_row_state') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_repair__job_state_effects() -> None:
    """utils/batch_pipeline/record_seal_repair.py::_job_state: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_repair.py', '_job_state') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_repair.py', '_job_state') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_repair_plan_digest_effects() -> None:
    """utils/batch_pipeline/record_seal_repair.py::plan_digest: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_repair.py', 'plan_digest') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_repair.py', 'plan_digest') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_repair_seal_refusal_effects() -> None:
    """utils/batch_pipeline/record_seal_repair.py::seal_refusal: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_repair.py', 'seal_refusal') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_repair.py', 'seal_refusal') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_repair_retained_tail_proof_effects() -> None:
    """utils/batch_pipeline/record_seal_repair.py::retained_tail_proof: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_repair.py', 'retained_tail_proof') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_repair.py', 'retained_tail_proof') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_repair_validate_repair_tail_effects() -> None:
    """utils/batch_pipeline/record_seal_repair.py::validate_repair_tail: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_repair.py', 'validate_repair_tail') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_repair.py', 'validate_repair_tail') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_repair_precheck_record_tail_effects() -> None:
    """utils/batch_pipeline/record_seal_repair.py::precheck_record_tail: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_repair.py', 'precheck_record_tail') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_repair.py', 'precheck_record_tail') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_repair_plan_seals_effects() -> None:
    """utils/batch_pipeline/record_seal_repair.py::plan_seals: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_repair.py', 'plan_seals') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_repair.py', 'plan_seals') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_repair_apply_seals_effects() -> None:
    """utils/batch_pipeline/record_seal_repair.py::apply_seals: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_repair.py', 'apply_seals') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_repair.py', 'apply_seals') == ('db_calls',)


def test_sync_defs_utils_batch_pipeline_record_seal_repair_plan_summary_effects() -> None:
    """utils/batch_pipeline/record_seal_repair.py::plan_summary: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_repair.py', 'plan_summary') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_repair.py', 'plan_summary') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_sweeper_read_pusher_pod_proof_effects() -> None:
    """utils/batch_pipeline/record_seal_sweeper.py::read_pusher_pod_proof: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_sweeper.py', 'read_pusher_pod_proof') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_sweeper.py', 'read_pusher_pod_proof') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_sweeper_discover_pending_effects() -> None:
    """utils/batch_pipeline/record_seal_sweeper.py::discover_pending: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_sweeper.py', 'discover_pending') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_sweeper.py', 'discover_pending') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_sweeper_require_fresh_proof_effects() -> None:
    """utils/batch_pipeline/record_seal_sweeper.py::require_fresh_proof: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_sweeper.py', 'require_fresh_proof') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_sweeper.py', 'require_fresh_proof') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_sweeper_sweep_effects() -> None:
    """utils/batch_pipeline/record_seal_sweeper.py::sweep: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_sweeper.py', 'sweep') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_sweeper.py', 'sweep') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_sweeper_run_effects() -> None:
    """utils/batch_pipeline/record_seal_sweeper.py::run: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_sweeper.py', 'run') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_sweeper.py', 'run') == ('db_calls',)


def test_sync_defs_utils_batch_pipeline_record_seal_worker_enabled_effects() -> None:
    """utils/batch_pipeline/record_seal_worker.py::enabled: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_worker.py', 'enabled') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_worker.py', 'enabled') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_worker_row_result_effects() -> None:
    """utils/batch_pipeline/record_seal_worker.py::row_result: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_worker.py', 'row_result') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_worker.py', 'row_result') == ()


def test_sync_defs_utils_batch_pipeline_record_seal_worker_run_effects() -> None:
    """utils/batch_pipeline/record_seal_worker.py::run: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/record_seal_worker.py', 'run') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/record_seal_worker.py', 'run') == ('db_calls',)


def test_sync_defs_utils_batch_pipeline_recovery_disposition_log_result_held_effects() -> None:
    """utils/batch_pipeline/recovery_disposition.py::log_result_held: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'log_result_held') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'log_result_held') == ()


def test_sync_defs_utils_batch_pipeline_recovery_disposition_stage_failure_effects() -> None:
    """utils/batch_pipeline/recovery_disposition.py::stage_failure: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'stage_failure') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'stage_failure') == ()


def test_sync_defs_utils_batch_pipeline_recovery_disposition_at_stage_effects() -> None:
    """utils/batch_pipeline/recovery_disposition.py::at_stage: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'at_stage') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'at_stage') == ()


def test_sync_defs_utils_batch_pipeline_recovery_disposition_inspect_audio_effects() -> None:
    """utils/batch_pipeline/recovery_disposition.py::inspect_audio: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'inspect_audio') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'inspect_audio') == ()


def test_sync_defs_utils_batch_pipeline_recovery_disposition_silence_payload_effects() -> None:
    """utils/batch_pipeline/recovery_disposition.py::silence_payload: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'silence_payload') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'silence_payload') == ()


def test_sync_defs_utils_batch_pipeline_recovery_disposition_result_outcome_effects() -> None:
    """utils/batch_pipeline/recovery_disposition.py::result_outcome: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'result_outcome') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'result_outcome') == ()


def test_sync_defs_utils_batch_pipeline_recovery_disposition_validate_independent_silence_effects() -> None:
    """utils/batch_pipeline/recovery_disposition.py::validate_independent_silence: effects fixed=() ablated=()."""
    assert (
        fixture.FIXED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'validate_independent_silence')
        == ()
    )
    assert (
        fixture.ABLATED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'validate_independent_silence')
        == ()
    )


def test_sync_defs_utils_batch_pipeline_recovery_disposition_result_vad_evidence_effects() -> None:
    """utils/batch_pipeline/recovery_disposition.py::result_vad_evidence: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'result_vad_evidence') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'result_vad_evidence') == ()


def test_sync_defs_utils_batch_pipeline_recovery_disposition_independent_silence_payload_effects() -> None:
    """utils/batch_pipeline/recovery_disposition.py::independent_silence_payload: effects fixed=() ablated=()."""
    assert (
        fixture.FIXED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'independent_silence_payload')
        == ()
    )
    assert (
        fixture.ABLATED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'independent_silence_payload')
        == ()
    )


def test_sync_defs_utils_batch_pipeline_recovery_disposition_padded_empty_effects() -> None:
    """utils/batch_pipeline/recovery_disposition.py::padded_empty: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'padded_empty') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'padded_empty') == ()


def test_sync_defs_utils_batch_pipeline_recovery_disposition_padded_skipped_effects() -> None:
    """utils/batch_pipeline/recovery_disposition.py::padded_skipped: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'padded_skipped') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'padded_skipped') == ()


def test_sync_defs_utils_batch_pipeline_recovery_disposition_padded_long_speech_effects() -> None:
    """utils/batch_pipeline/recovery_disposition.py::padded_long_speech: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'padded_long_speech') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'padded_long_speech') == ()


def test_sync_defs_utils_batch_pipeline_recovery_disposition_terminal_empty_payload_effects() -> None:
    """utils/batch_pipeline/recovery_disposition.py::terminal_empty_payload: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'terminal_empty_payload') == ()
    assert (
        fixture.ABLATED_effect_summary('utils/batch_pipeline/recovery_disposition.py', 'terminal_empty_payload') == ()
    )


def test_sync_defs_utils_batch_pipeline_recovery_recognizers_recognizer_attempt_effects() -> None:
    """utils/batch_pipeline/recovery_recognizers.py::recognizer_attempt: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/recovery_recognizers.py', 'recognizer_attempt') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/recovery_recognizers.py', 'recognizer_attempt') == ()


def test_sync_defs_utils_batch_pipeline_recovery_recognizers_independent_ready_effects() -> None:
    """utils/batch_pipeline/recovery_recognizers.py::independent_ready: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/recovery_recognizers.py', 'independent_ready') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/recovery_recognizers.py', 'independent_ready') == ()


def test_sync_defs_utils_batch_pipeline_recovery_recognizers_transcribe_effects() -> None:
    """utils/batch_pipeline/recovery_recognizers.py::transcribe: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/recovery_recognizers.py', 'transcribe') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/recovery_recognizers.py', 'transcribe') == ()


def test_sync_defs_utils_batch_pipeline_recovery_recognizers_second_transcribe_effects() -> None:
    """utils/batch_pipeline/recovery_recognizers.py::second_transcribe: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/recovery_recognizers.py', 'second_transcribe') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/recovery_recognizers.py', 'second_transcribe') == ()


def test_sync_defs_utils_batch_pipeline_recovery_recognizers_independent_audio_effects() -> None:
    """utils/batch_pipeline/recovery_recognizers.py::independent_audio: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/recovery_recognizers.py', 'independent_audio') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/recovery_recognizers.py', 'independent_audio') == ()


def test_sync_defs_utils_batch_pipeline_recovery_recognizers_independent_payload_effects() -> None:
    """utils/batch_pipeline/recovery_recognizers.py::independent_payload: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/recovery_recognizers.py', 'independent_payload') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/recovery_recognizers.py', 'independent_payload') == ()


def test_sync_defs_utils_batch_pipeline_recovery_recognizers_canonical_wav_effects() -> None:
    """utils/batch_pipeline/recovery_recognizers.py::canonical_wav: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/recovery_recognizers.py', 'canonical_wav') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/recovery_recognizers.py', 'canonical_wav') == ()


def test_sync_defs_utils_batch_pipeline_recovery_recognizers_recovery_audio_effects() -> None:
    """utils/batch_pipeline/recovery_recognizers.py::recovery_audio: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/recovery_recognizers.py', 'recovery_audio') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/recovery_recognizers.py', 'recovery_audio') == ()


def test_sync_defs_utils_batch_pipeline_recovery_recognizers_validate_response_effects() -> None:
    """utils/batch_pipeline/recovery_recognizers.py::validate_response: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/recovery_recognizers.py', 'validate_response') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/recovery_recognizers.py', 'validate_response') == ()


def test_sync_defs_utils_batch_pipeline_recovery_recognizers_words_payload_effects() -> None:
    """utils/batch_pipeline/recovery_recognizers.py::words_payload: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/recovery_recognizers.py', 'words_payload') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/recovery_recognizers.py', 'words_payload') == ()


def test_sync_defs_utils_batch_pipeline_recovery_steps_advance_effects() -> None:
    """utils/batch_pipeline/recovery_steps.py::advance: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/recovery_steps.py', 'advance') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/recovery_steps.py', 'advance') == ()


def test_sync_defs_utils_batch_pipeline_recovery_steps_run_sync_effects() -> None:
    """utils/batch_pipeline/recovery_steps.py::run_sync: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/recovery_steps.py', 'run_sync') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/recovery_steps.py', 'run_sync') == ()


def test_sync_defs_utils_batch_pipeline_redrive_scope_require_effects() -> None:
    """utils/batch_pipeline/redrive_scope.py::require: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/redrive_scope.py', 'require') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/redrive_scope.py', 'require') == ()


def test_sync_defs_utils_batch_pipeline_redrive_scope_digest_effects() -> None:
    """utils/batch_pipeline/redrive_scope.py::digest: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/redrive_scope.py', 'digest') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/redrive_scope.py', 'digest') == ()


def test_sync_defs_utils_batch_pipeline_redrive_scope_owner_jobs_effects() -> None:
    """utils/batch_pipeline/redrive_scope.py::owner_jobs: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/redrive_scope.py', 'owner_jobs') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/redrive_scope.py', 'owner_jobs') == ()


def test_sync_defs_utils_batch_pipeline_redrive_scope_eligible_effects() -> None:
    """utils/batch_pipeline/redrive_scope.py::eligible: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/redrive_scope.py', 'eligible') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/redrive_scope.py', 'eligible') == ()


def test_sync_defs_utils_batch_pipeline_redrive_scope_unit_ids_effects() -> None:
    """utils/batch_pipeline/redrive_scope.py::unit_ids: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/redrive_scope.py', 'unit_ids') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/redrive_scope.py', 'unit_ids') == ()


def test_sync_defs_utils_batch_pipeline_redrive_scope_read_json_effects() -> None:
    """utils/batch_pipeline/redrive_scope.py::read_json: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/redrive_scope.py', 'read_json') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/redrive_scope.py', 'read_json') == ()


def test_sync_defs_utils_batch_pipeline_redrive_scope_scope_body_effects() -> None:
    """utils/batch_pipeline/redrive_scope.py::scope_body: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/redrive_scope.py', 'scope_body') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/redrive_scope.py', 'scope_body') == ()


def test_sync_defs_utils_batch_pipeline_redrive_scope_load_effects() -> None:
    """utils/batch_pipeline/redrive_scope.py::load: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/redrive_scope.py', 'load') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/redrive_scope.py', 'load') == ()


def test_sync_defs_utils_batch_pipeline_redrive_scope_write_effects() -> None:
    """utils/batch_pipeline/redrive_scope.py::write: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/redrive_scope.py', 'write') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/redrive_scope.py', 'write') == ()


def test_sync_defs_utils_batch_pipeline_redrive_scope_successful_effects() -> None:
    """utils/batch_pipeline/redrive_scope.py::successful: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/redrive_scope.py', 'successful') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/redrive_scope.py', 'successful') == ()


def test_sync_defs_utils_batch_pipeline_refused_attestation_utc_effects() -> None:
    """utils/batch_pipeline/refused_attestation.py::utc: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/refused_attestation.py', 'utc') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/refused_attestation.py', 'utc') == ()


def test_sync_defs_utils_batch_pipeline_refused_attestation_checked_proof_effects() -> None:
    """utils/batch_pipeline/refused_attestation.py::checked_proof: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/refused_attestation.py', 'checked_proof') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/refused_attestation.py', 'checked_proof') == ()


def test_sync_defs_utils_batch_pipeline_refused_attestation_refused_candidate_effects() -> None:
    """utils/batch_pipeline/refused_attestation.py::refused_candidate: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/refused_attestation.py', 'refused_candidate') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/refused_attestation.py', 'refused_candidate') == ()


def test_sync_defs_utils_batch_pipeline_repair_lineage_lineage_record_effects() -> None:
    """utils/batch_pipeline/repair_lineage.py::lineage_record: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/repair_lineage.py', 'lineage_record') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/repair_lineage.py', 'lineage_record') == ()


def test_sync_defs_utils_batch_pipeline_repair_lineage_recorded_lineage_effects() -> None:
    """utils/batch_pipeline/repair_lineage.py::recorded_lineage: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/repair_lineage.py', 'recorded_lineage') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/repair_lineage.py', 'recorded_lineage') == ()


def test_sync_defs_utils_batch_pipeline_repair_lineage_language_proof_effects() -> None:
    """utils/batch_pipeline/repair_lineage.py::language_proof: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/repair_lineage.py', 'language_proof') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/repair_lineage.py', 'language_proof') == ()


def test_sync_defs_utils_batch_pipeline_retention_delete_batch_object_effects() -> None:
    """utils/batch_pipeline/retention.py::delete_batch_object: effects fixed=() ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/retention.py', 'delete_batch_object') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/retention.py', 'delete_batch_object') == ('db_calls',)


def test_sync_defs_utils_batch_pipeline_retention_register_batch_artifact_effects() -> None:
    """utils/batch_pipeline/retention.py::register_batch_artifact: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/retention.py', 'register_batch_artifact') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/retention.py', 'register_batch_artifact') == (
        'db_calls',
    )


def test_sync_defs_utils_batch_pipeline_retention_expire_completed_segment_effects() -> None:
    """utils/batch_pipeline/retention.py::expire_completed_segment: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/retention.py', 'expire_completed_segment') == (
        'db_calls',
    )
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/retention.py', 'expire_completed_segment') == (
        'db_calls',
    )


def test_sync_defs_utils_batch_pipeline_retention_run_retention_transaction_effects() -> None:
    """utils/batch_pipeline/retention.py::run_retention_transaction: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/retention.py', 'run_retention_transaction') == (
        'db_calls',
    )
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/retention.py', 'run_retention_transaction') == (
        'db_calls',
    )


def test_sync_defs_utils_batch_pipeline_retention__flag_invalid_cleanup_receipt_effects() -> None:
    """utils/batch_pipeline/retention.py::_flag_invalid_cleanup_receipt: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/retention.py', '_flag_invalid_cleanup_receipt') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/retention.py', '_flag_invalid_cleanup_receipt') == ()


def test_sync_defs_utils_batch_pipeline_retention_cleanup_completed_artifacts_effects() -> None:
    """utils/batch_pipeline/retention.py::cleanup_completed_artifacts: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/retention.py', 'cleanup_completed_artifacts') == (
        'db_calls',
    )
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/retention.py', 'cleanup_completed_artifacts') == (
        'db_calls',
    )


def test_sync_defs_utils_batch_pipeline_retention_batch_artifact_authorize_effects() -> None:
    """utils/batch_pipeline/retention.py::batch_artifact_authorize: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/retention.py', 'batch_artifact_authorize') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/retention.py', 'batch_artifact_authorize') == ()


def test_sync_defs_utils_batch_pipeline_retention_batch_artifact_register_effects() -> None:
    """utils/batch_pipeline/retention.py::batch_artifact_register: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/retention.py', 'batch_artifact_register') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/retention.py', 'batch_artifact_register') == (
        'db_calls',
    )


def test_sync_defs_utils_batch_pipeline_retention_purge_batch_storage_owner_effects() -> None:
    """utils/batch_pipeline/retention.py::purge_batch_storage_owner: effects fixed=() ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/retention.py', 'purge_batch_storage_owner') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/retention.py', 'purge_batch_storage_owner') == (
        'db_calls',
    )


def test_sync_defs_utils_batch_pipeline_retry_policy_quarantine_job_effects() -> None:
    """utils/batch_pipeline/retry_policy.py::quarantine_job: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/retry_policy.py', 'quarantine_job') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/retry_policy.py', 'quarantine_job') == ()


def test_sync_defs_utils_batch_pipeline_retry_policy_expire_lease_effects() -> None:
    """utils/batch_pipeline/retry_policy.py::expire_lease: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/retry_policy.py', 'expire_lease') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/retry_policy.py', 'expire_lease') == ()


def test_sync_defs_utils_batch_pipeline_retry_policy_observe_recovery_effects() -> None:
    """utils/batch_pipeline/retry_policy.py::observe_recovery: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/retry_policy.py', 'observe_recovery') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/retry_policy.py', 'observe_recovery') == ()


def test_sync_defs_utils_batch_pipeline_route_selection_configure_health_effects() -> None:
    """utils/batch_pipeline/route_selection.py::configure_health: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/route_selection.py', 'configure_health') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/route_selection.py', 'configure_health') == ()


def test_sync_defs_utils_batch_pipeline_route_selection_serving_health_effects() -> None:
    """utils/batch_pipeline/route_selection.py::serving_health: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/route_selection.py', 'serving_health') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/route_selection.py', 'serving_health') == ()


def test_sync_defs_utils_batch_pipeline_route_selection_current_table_effects() -> None:
    """utils/batch_pipeline/route_selection.py::current_table: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/route_selection.py', 'current_table') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/route_selection.py', 'current_table') == ()


def test_sync_defs_utils_batch_pipeline_route_selection_route_allowed_effects() -> None:
    """utils/batch_pipeline/route_selection.py::route_allowed: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/route_selection.py', 'route_allowed') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/route_selection.py', 'route_allowed') == ()


def test_sync_defs_utils_batch_pipeline_route_selection__builtin_effects() -> None:
    """utils/batch_pipeline/route_selection.py::_builtin: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/route_selection.py', '_builtin') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/route_selection.py', '_builtin') == ()


def test_sync_defs_utils_batch_pipeline_route_selection__as_stt_route_effects() -> None:
    """utils/batch_pipeline/route_selection.py::_as_stt_route: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/route_selection.py', '_as_stt_route') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/route_selection.py', '_as_stt_route') == ()


def test_sync_defs_utils_batch_pipeline_route_selection__price_effects() -> None:
    """utils/batch_pipeline/route_selection.py::_price: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/route_selection.py', '_price') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/route_selection.py', '_price') == ()


def test_sync_defs_utils_batch_pipeline_route_selection__primary_effects() -> None:
    """utils/batch_pipeline/route_selection.py::_primary: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/route_selection.py', '_primary') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/route_selection.py', '_primary') == ()


def test_sync_defs_utils_batch_pipeline_route_selection_decide_effects() -> None:
    """utils/batch_pipeline/route_selection.py::decide: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/route_selection.py', 'decide') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/route_selection.py', 'decide') == ()


def test_sync_defs_utils_batch_pipeline_route_selection_failover_vendors_effects() -> None:
    """utils/batch_pipeline/route_selection.py::failover_vendors: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/route_selection.py', 'failover_vendors') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/route_selection.py', 'failover_vendors') == ()


def test_sync_defs_utils_batch_pipeline_route_selection__in_cohort_effects() -> None:
    """utils/batch_pipeline/route_selection.py::_in_cohort: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/route_selection.py', '_in_cohort') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/route_selection.py', '_in_cohort') == ()


def test_sync_defs_utils_batch_pipeline_route_selection__table_decision_effects() -> None:
    """utils/batch_pipeline/route_selection.py::_table_decision: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/route_selection.py', '_table_decision') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/route_selection.py', '_table_decision') == ()


def test_sync_defs_utils_batch_pipeline_route_selection_select_route_effects() -> None:
    """utils/batch_pipeline/route_selection.py::select_route: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/route_selection.py', 'select_route') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/route_selection.py', 'select_route') == ()


def test_sync_defs_utils_batch_pipeline_route_selection__log_shadow_effects() -> None:
    """utils/batch_pipeline/route_selection.py::_log_shadow: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/route_selection.py', '_log_shadow') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/route_selection.py', '_log_shadow') == ()


def test_sync_defs_utils_batch_pipeline_route_selection_route_decision_fields_effects() -> None:
    """utils/batch_pipeline/route_selection.py::route_decision_fields: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/route_selection.py', 'route_decision_fields') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/route_selection.py', 'route_decision_fields') == ()


def test_sync_defs_utils_batch_pipeline_scheduler__admission_retry_delay_effects() -> None:
    """utils/batch_pipeline/scheduler.py::_admission_retry_delay: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/scheduler.py', '_admission_retry_delay') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/scheduler.py', '_admission_retry_delay') == ()


def test_sync_defs_utils_batch_pipeline_scheduler_owner_key_effects() -> None:
    """utils/batch_pipeline/scheduler.py::owner_key: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/scheduler.py', 'owner_key') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/scheduler.py', 'owner_key') == ()


def test_sync_defs_utils_batch_pipeline_scheduler_rejoin_frontiers_effects() -> None:
    """utils/batch_pipeline/scheduler.py::rejoin_frontiers: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/scheduler.py', 'rejoin_frontiers') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/scheduler.py', 'rejoin_frontiers') == ()


def test_sync_defs_utils_batch_pipeline_scheduler__fifo_read_chain_effects() -> None:
    """utils/batch_pipeline/scheduler.py::_fifo_read_chain: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/scheduler.py', '_fifo_read_chain') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/scheduler.py', '_fifo_read_chain') == ()


def test_sync_defs_utils_batch_pipeline_scheduler__fifo_absorb_strays_effects() -> None:
    """utils/batch_pipeline/scheduler.py::_fifo_absorb_strays: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/scheduler.py', '_fifo_absorb_strays') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/scheduler.py', '_fifo_absorb_strays') == ()


def test_sync_defs_utils_batch_pipeline_scheduler__append_fifo_array_effects() -> None:
    """utils/batch_pipeline/scheduler.py::_append_fifo_array: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/scheduler.py', '_append_fifo_array') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/scheduler.py', '_append_fifo_array') == ()


def test_sync_defs_utils_batch_pipeline_scheduler__append_effects() -> None:
    """utils/batch_pipeline/scheduler.py::_append: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/scheduler.py', '_append') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/scheduler.py', '_append') == ()


def test_sync_defs_utils_batch_pipeline_scheduler__pool_allows_effects() -> None:
    """utils/batch_pipeline/scheduler.py::_pool_allows: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/scheduler.py', '_pool_allows') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/scheduler.py', '_pool_allows') == ()


def test_sync_defs_utils_batch_pipeline_scheduler__park_reason_effects() -> None:
    """utils/batch_pipeline/scheduler.py::_park_reason: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/scheduler.py', '_park_reason') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/scheduler.py', '_park_reason') == ()


def test_sync_defs_utils_batch_pipeline_scheduler__prefer_merge_head_effects() -> None:
    """utils/batch_pipeline/scheduler.py::_prefer_merge_head: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/scheduler.py', '_prefer_merge_head') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/scheduler.py', '_prefer_merge_head') == ('db_calls',)


def test_sync_defs_utils_batch_pipeline_scheduler_owns_lease_effects() -> None:
    """utils/batch_pipeline/scheduler.py::owns_lease: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/scheduler.py', 'owns_lease') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/scheduler.py', 'owns_lease') == ()


def test_sync_defs_utils_batch_pipeline_scheduler__defer_effects() -> None:
    """utils/batch_pipeline/scheduler.py::_defer: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/scheduler.py', '_defer') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/scheduler.py', '_defer') == ()


def test_sync_defs_utils_batch_pipeline_serving_serving_for_stage_effects() -> None:
    """utils/batch_pipeline/serving.py::serving_for_stage: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/serving.py', 'serving_for_stage') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/serving.py', 'serving_for_stage') == ('db_calls',)


def test_sync_defs_utils_batch_pipeline_serving__metrics_effects() -> None:
    """utils/batch_pipeline/serving.py::_metrics: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/serving.py', '_metrics') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/serving.py', '_metrics') == ()


def test_sync_defs_utils_batch_pipeline_serving_start_serving_from_env_effects() -> None:
    """utils/batch_pipeline/serving.py::start_serving_from_env: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/serving.py', 'start_serving_from_env') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/serving.py', 'start_serving_from_env') == ()


def test_sync_defs_utils_batch_pipeline_shadow_intake__next_unit_effects() -> None:
    """utils/batch_pipeline/shadow_intake.py::_next_unit: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/shadow_intake.py', '_next_unit') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/shadow_intake.py', '_next_unit') == ()


def test_sync_defs_utils_batch_pipeline_shadow_intake_copy_paths_effects() -> None:
    """utils/batch_pipeline/shadow_intake.py::copy_paths: effects fixed=('file_io',) ablated=('file_io',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/shadow_intake.py', 'copy_paths') == ('file_io',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/shadow_intake.py', 'copy_paths') == ('file_io',)


def test_sync_defs_utils_batch_pipeline_shadow_intake_repository_for_stage_effects() -> None:
    """utils/batch_pipeline/shadow_intake.py::repository_for_stage: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/shadow_intake.py', 'repository_for_stage') == (
        'db_calls',
    )
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/shadow_intake.py', 'repository_for_stage') == (
        'db_calls',
    )


def test_sync_defs_utils_batch_pipeline_shadow_metrics_record_effects() -> None:
    """utils/batch_pipeline/shadow_metrics.py::record: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/shadow_metrics.py', 'record') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/shadow_metrics.py', 'record') == ()


def test_sync_defs_utils_batch_pipeline_shadow_projection_plan_effects() -> None:
    """utils/batch_pipeline/shadow_projection.py::plan: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/shadow_projection.py', 'plan') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/shadow_projection.py', 'plan') == ()


def test_sync_defs_utils_batch_pipeline_shadow_projection_run_effects() -> None:
    """utils/batch_pipeline/shadow_projection.py::run: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/shadow_projection.py', 'run') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/shadow_projection.py', 'run') == ('db_calls',)


def test_sync_defs_utils_batch_pipeline_shadow_recovery_guarded_recovery_effects() -> None:
    """utils/batch_pipeline/shadow_recovery.py::guarded_recovery: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/shadow_recovery.py', 'guarded_recovery') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/shadow_recovery.py', 'guarded_recovery') == ()


def test_sync_defs_utils_batch_pipeline_shadow_recovery_recover_effects() -> None:
    """utils/batch_pipeline/shadow_recovery.py::recover: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/shadow_recovery.py', 'recover') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/shadow_recovery.py', 'recover') == ()


def test_sync_defs_utils_batch_pipeline_shadow_recovery__recover_steps_effects() -> None:
    """utils/batch_pipeline/shadow_recovery.py::_recover_steps: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/shadow_recovery.py', '_recover_steps') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/shadow_recovery.py', '_recover_steps') == ()


def test_sync_defs_utils_batch_pipeline_source_audio_batch_timing_store_effects() -> None:
    """utils/batch_pipeline/source_audio.py::batch_timing_store: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/source_audio.py', 'batch_timing_store') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/source_audio.py', 'batch_timing_store') == ()


def test_sync_defs_utils_batch_pipeline_source_audio_decoder_fault_types_effects() -> None:
    """utils/batch_pipeline/source_audio.py::decoder_fault_types: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/source_audio.py', 'decoder_fault_types') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/source_audio.py', 'decoder_fault_types') == ()


def test_sync_defs_utils_batch_pipeline_source_audio_decode_source_effects() -> None:
    """utils/batch_pipeline/source_audio.py::decode_source: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/source_audio.py', 'decode_source') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/source_audio.py', 'decode_source') == ()


def test_sync_defs_utils_batch_pipeline_source_audio_validate_reference_effects() -> None:
    """utils/batch_pipeline/source_audio.py::validate_reference: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/source_audio.py', 'validate_reference') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/source_audio.py', 'validate_reference') == ()


def test_sync_defs_utils_batch_pipeline_source_audio_read_reference_effects() -> None:
    """utils/batch_pipeline/source_audio.py::read_reference: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/source_audio.py', 'read_reference') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/source_audio.py', 'read_reference') == ()


def test_sync_defs_utils_batch_pipeline_source_audio__well_formed_effects() -> None:
    """utils/batch_pipeline/source_audio.py::_well_formed: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/source_audio.py', '_well_formed') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/source_audio.py', '_well_formed') == ()


def test_sync_defs_utils_batch_pipeline_source_audio_materialize_effects() -> None:
    """utils/batch_pipeline/source_audio.py::materialize: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/source_audio.py', 'materialize') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/source_audio.py', 'materialize') == ()


def test_sync_defs_utils_batch_pipeline_speech_redrive_speech_preflight_effects() -> None:
    """utils/batch_pipeline/speech_redrive.py::speech_preflight: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/speech_redrive.py', 'speech_preflight') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/speech_redrive.py', 'speech_preflight') == ()


def test_sync_defs_utils_batch_pipeline_speech_redrive_redrive_one_effects() -> None:
    """utils/batch_pipeline/speech_redrive.py::redrive_one: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/speech_redrive.py', 'redrive_one') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/speech_redrive.py', 'redrive_one') == ('db_calls',)


def test_sync_defs_utils_batch_pipeline_speech_redrive_prepared_independent_one_effects() -> None:
    """utils/batch_pipeline/speech_redrive.py::prepared_independent_one: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/speech_redrive.py', 'prepared_independent_one') == (
        'db_calls',
    )
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/speech_redrive.py', 'prepared_independent_one') == (
        'db_calls',
    )


def test_sync_defs_utils_batch_pipeline_vendor_health__provider_effects() -> None:
    """utils/batch_pipeline/vendor_health.py::_provider: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_health.py', '_provider') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_health.py', '_provider') == ()


def test_sync_defs_utils_batch_pipeline_vendor_health_increments_effects() -> None:
    """utils/batch_pipeline/vendor_health.py::increments: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_health.py', 'increments') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_health.py', 'increments') == ()


def test_sync_defs_utils_batch_pipeline_vendor_health_window_effects() -> None:
    """utils/batch_pipeline/vendor_health.py::window: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_health.py', 'window') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_health.py', 'window') == ()


def test_sync_defs_utils_batch_pipeline_vendor_health__rate_effects() -> None:
    """utils/batch_pipeline/vendor_health.py::_rate: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_health.py', '_rate') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_health.py', '_rate') == ()


def test_sync_defs_utils_batch_pipeline_vendor_health_assess_effects() -> None:
    """utils/batch_pipeline/vendor_health.py::assess: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_health.py', 'assess') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_health.py', 'assess') == ()


def test_sync_defs_utils_batch_pipeline_vendor_health_advance_effects() -> None:
    """utils/batch_pipeline/vendor_health.py::advance: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_health.py', 'advance') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_health.py', 'advance') == ()


def test_sync_defs_utils_batch_pipeline_vendor_health__day_effects() -> None:
    """utils/batch_pipeline/vendor_health.py::_day: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_health.py', '_day') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_health.py', '_day') == ()


def test_sync_defs_utils_batch_pipeline_vendor_health__month_effects() -> None:
    """utils/batch_pipeline/vendor_health.py::_month: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_health.py', '_month') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_health.py', '_month') == ()


def test_sync_defs_utils_batch_pipeline_vendor_health__hours_effects() -> None:
    """utils/batch_pipeline/vendor_health.py::_hours: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_health.py', '_hours') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_health.py', '_hours') == ()


def test_sync_defs_utils_batch_pipeline_vendor_health__text_effects() -> None:
    """utils/batch_pipeline/vendor_health.py::_text: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_health.py', '_text') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_health.py', '_text') == ()


def test_sync_defs_utils_batch_pipeline_vendor_health__over_effects() -> None:
    """utils/batch_pipeline/vendor_health.py::_over: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_health.py', '_over') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_health.py', '_over') == ()


def test_sync_defs_utils_batch_pipeline_vendor_health__builtin_routes_effects() -> None:
    """utils/batch_pipeline/vendor_health.py::_builtin_routes: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_health.py', '_builtin_routes') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_health.py', '_builtin_routes') == ()


def test_sync_defs_utils_batch_pipeline_vendor_health__admitted_effects() -> None:
    """utils/batch_pipeline/vendor_health.py::_admitted: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_health.py', '_admitted') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_health.py', '_admitted') == ()


def test_sync_defs_utils_batch_pipeline_vendor_health__legacy_view_effects() -> None:
    """utils/batch_pipeline/vendor_health.py::_legacy_view: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_health.py', '_legacy_view') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_health.py', '_legacy_view') == ()


def test_sync_defs_utils_batch_pipeline_vendor_health_get_vendor_health_effects() -> None:
    """utils/batch_pipeline/vendor_health.py::get_vendor_health: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_health.py', 'get_vendor_health') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_health.py', 'get_vendor_health') == ('db_calls',)


def test_sync_defs_utils_batch_pipeline_vendor_route_contracts_normalized_language_effects() -> None:
    """utils/batch_pipeline/vendor_route_contracts.py::normalized_language: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_route_contracts.py', 'normalized_language') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_route_contracts.py', 'normalized_language') == ()


def test_sync_defs_utils_batch_pipeline_vendor_route_contracts_route_capable_effects() -> None:
    """utils/batch_pipeline/vendor_route_contracts.py::route_capable: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_route_contracts.py', 'route_capable') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_route_contracts.py', 'route_capable') == ()


def test_sync_defs_utils_batch_pipeline_vendor_route_contracts__finite_effects() -> None:
    """utils/batch_pipeline/vendor_route_contracts.py::_finite: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_route_contracts.py', '_finite') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_route_contracts.py', '_finite') == ()


def test_sync_defs_utils_batch_pipeline_vendor_route_contracts__exact_keys_effects() -> None:
    """utils/batch_pipeline/vendor_route_contracts.py::_exact_keys: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_route_contracts.py', '_exact_keys') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_route_contracts.py', '_exact_keys') == ()


def test_sync_defs_utils_batch_pipeline_vendor_route_contracts_capable_options_effects() -> None:
    """utils/batch_pipeline/vendor_route_contracts.py::capable_options: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_route_contracts.py', 'capable_options') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_route_contracts.py', 'capable_options') == ()


def test_sync_defs_utils_batch_pipeline_vendor_route_contracts_check_new_attempt_effects() -> None:
    """utils/batch_pipeline/vendor_route_contracts.py::check_new_attempt: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_route_contracts.py', 'check_new_attempt') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_route_contracts.py', 'check_new_attempt') == ()


def test_sync_defs_utils_batch_pipeline_vendor_route_contracts_is_vendor_policy_hold_effects() -> None:
    """utils/batch_pipeline/vendor_route_contracts.py::is_vendor_policy_hold: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_route_contracts.py', 'is_vendor_policy_hold') == ()
    assert (
        fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_route_contracts.py', 'is_vendor_policy_hold') == ()
    )


def test_sync_defs_utils_batch_pipeline_vendor_route_metrics__route_effects() -> None:
    """utils/batch_pipeline/vendor_route_metrics.py::_route: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', '_route') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', '_route') == ()


def test_sync_defs_utils_batch_pipeline_vendor_route_metrics__vendor_effects() -> None:
    """utils/batch_pipeline/vendor_route_metrics.py::_vendor: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', '_vendor') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', '_vendor') == ()


def test_sync_defs_utils_batch_pipeline_vendor_route_metrics__late_outcome_effects() -> None:
    """utils/batch_pipeline/vendor_route_metrics.py::_late_outcome: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', '_late_outcome') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', '_late_outcome') == ()


def test_sync_defs_utils_batch_pipeline_vendor_route_metrics_route_decision_effects() -> None:
    """utils/batch_pipeline/vendor_route_metrics.py::route_decision: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'route_decision') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'route_decision') == ()


def test_sync_defs_utils_batch_pipeline_vendor_route_metrics_table_load_effects() -> None:
    """utils/batch_pipeline/vendor_route_metrics.py::table_load: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'table_load') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'table_load') == ()


def test_sync_defs_utils_batch_pipeline_vendor_route_metrics_gpu_overflow_effects() -> None:
    """utils/batch_pipeline/vendor_route_metrics.py::gpu_overflow: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'gpu_overflow') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'gpu_overflow') == ()


def test_sync_defs_utils_batch_pipeline_vendor_route_metrics_attempt_effects() -> None:
    """utils/batch_pipeline/vendor_route_metrics.py::attempt: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'attempt') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'attempt') == ()


def test_sync_defs_utils_batch_pipeline_vendor_route_metrics_failover_effects() -> None:
    """utils/batch_pipeline/vendor_route_metrics.py::failover: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'failover') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'failover') == ()


def test_sync_defs_utils_batch_pipeline_vendor_route_metrics_late_result_effects() -> None:
    """utils/batch_pipeline/vendor_route_metrics.py::late_result: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'late_result') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'late_result') == ()


def test_sync_defs_utils_batch_pipeline_vendor_route_metrics_paid_intent_violation_effects() -> None:
    """utils/batch_pipeline/vendor_route_metrics.py::paid_intent_violation: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'paid_intent_violation') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'paid_intent_violation') == ()


def test_sync_defs_utils_batch_pipeline_vendor_route_metrics_hold_transition_effects() -> None:
    """utils/batch_pipeline/vendor_route_metrics.py::hold_transition: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'hold_transition') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'hold_transition') == ()


def test_sync_defs_utils_batch_pipeline_vendor_route_metrics_held_units_effects() -> None:
    """utils/batch_pipeline/vendor_route_metrics.py::held_units: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'held_units') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'held_units') == ()


def test_sync_defs_utils_batch_pipeline_vendor_route_metrics_health_decision_effects() -> None:
    """utils/batch_pipeline/vendor_route_metrics.py::health_decision: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'health_decision') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'health_decision') == ()


def test_sync_defs_utils_batch_pipeline_vendor_route_metrics_breaker_state_effects() -> None:
    """utils/batch_pipeline/vendor_route_metrics.py::breaker_state: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'breaker_state') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'breaker_state') == ()


def test_sync_defs_utils_batch_pipeline_vendor_route_metrics_audio_hours_effects() -> None:
    """utils/batch_pipeline/vendor_route_metrics.py::audio_hours: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'audio_hours') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'audio_hours') == ()


def test_sync_defs_utils_batch_pipeline_vendor_route_metrics_cap_hit_effects() -> None:
    """utils/batch_pipeline/vendor_route_metrics.py::cap_hit: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'cap_hit') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/vendor_route_metrics.py', 'cap_hit') == ()


def test_sync_defs_utils_batch_pipeline_voice_centroids_deadline_effects() -> None:
    """utils/batch_pipeline/voice_centroids.py::deadline: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/voice_centroids.py', 'deadline') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/voice_centroids.py', 'deadline') == ()


def test_sync_defs_utils_batch_pipeline_voice_centroids_encode_effects() -> None:
    """utils/batch_pipeline/voice_centroids.py::encode: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/voice_centroids.py', 'encode') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/voice_centroids.py', 'encode') == ()


def test_sync_defs_utils_batch_pipeline_voice_centroids_decode_effects() -> None:
    """utils/batch_pipeline/voice_centroids.py::decode: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/voice_centroids.py', 'decode') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/voice_centroids.py', 'decode') == ()


def test_sync_defs_utils_batch_pipeline_voice_centroids_extract_effects() -> None:
    """utils/batch_pipeline/voice_centroids.py::extract: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/voice_centroids.py', 'extract') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/voice_centroids.py', 'extract') == ()


def test_sync_defs_utils_batch_pipeline_voice_evidence_unavailable_effects() -> None:
    """utils/batch_pipeline/voice_evidence.py::unavailable: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/voice_evidence.py', 'unavailable') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/voice_evidence.py', 'unavailable') == ()


def test_sync_defs_utils_batch_pipeline_voice_evidence_prepare_effects() -> None:
    """utils/batch_pipeline/voice_evidence.py::prepare: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/voice_evidence.py', 'prepare') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/voice_evidence.py', 'prepare') == ('db_calls',)


def test_sync_defs_utils_batch_pipeline_voice_evidence_load_vectors_effects() -> None:
    """utils/batch_pipeline/voice_evidence.py::load_vectors: effects fixed=('db_calls',) ablated=('db_calls',)."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/voice_evidence.py', 'load_vectors') == ('db_calls',)
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/voice_evidence.py', 'load_vectors') == ('db_calls',)


def test_sync_defs_utils_batch_pipeline_word_validation_bounded_window_words_effects() -> None:
    """utils/batch_pipeline/word_validation.py::bounded_window_words: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/word_validation.py', 'bounded_window_words') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/word_validation.py', 'bounded_window_words') == ()


def test_sync_defs_utils_batch_pipeline_word_validation_validate_words_effects() -> None:
    """utils/batch_pipeline/word_validation.py::validate_words: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/word_validation.py', 'validate_words') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/word_validation.py', 'validate_words') == ()


def test_sync_defs_utils_batch_pipeline_worker_metrics_admission_effects() -> None:
    """utils/batch_pipeline/worker_metrics.py::admission: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/worker_metrics.py', 'admission') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/worker_metrics.py', 'admission') == ()


def test_sync_defs_utils_batch_pipeline_worker_metrics_strict_vad_effects() -> None:
    """utils/batch_pipeline/worker_metrics.py::strict_vad: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/worker_metrics.py', 'strict_vad') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/worker_metrics.py', 'strict_vad') == ()


def test_sync_defs_utils_batch_pipeline_worker_silence_inspect_worker_vad_effects() -> None:
    """utils/batch_pipeline/worker_silence.py::inspect_worker_vad: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/worker_silence.py', 'inspect_worker_vad') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/worker_silence.py', 'inspect_worker_vad') == ()


def test_sync_defs_utils_batch_pipeline_worker_silence_inspect_worker_silence_effects() -> None:
    """utils/batch_pipeline/worker_silence.py::inspect_worker_silence: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('utils/batch_pipeline/worker_silence.py', 'inspect_worker_silence') == ()
    assert fixture.ABLATED_effect_summary('utils/batch_pipeline/worker_silence.py', 'inspect_worker_silence') == ()


def test_sync_defs_database_firestore_transaction_retry__is_expired_transaction_effects() -> None:
    """database/firestore_transaction_retry.py::_is_expired_transaction: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('database/firestore_transaction_retry.py', '_is_expired_transaction') == ()
    assert fixture.ABLATED_effect_summary('database/firestore_transaction_retry.py', '_is_expired_transaction') == ()


def test_sync_defs_database_firestore_transaction_retry__is_transaction_contention_effects() -> None:
    """database/firestore_transaction_retry.py::_is_transaction_contention: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('database/firestore_transaction_retry.py', '_is_transaction_contention') == ()
    assert fixture.ABLATED_effect_summary('database/firestore_transaction_retry.py', '_is_transaction_contention') == ()


def test_sync_defs_database_firestore_transaction_retry_transaction_retry_deadline_scope_effects() -> None:
    """database/firestore_transaction_retry.py::transaction_retry_deadline_scope: effects fixed=() ablated=()."""
    assert (
        fixture.FIXED_effect_summary('database/firestore_transaction_retry.py', 'transaction_retry_deadline_scope')
        == ()
    )
    assert (
        fixture.ABLATED_effect_summary('database/firestore_transaction_retry.py', 'transaction_retry_deadline_scope')
        == ()
    )


def test_sync_defs_database_firestore_transaction_retry_normalized_gate_seconds_effects() -> None:
    """database/firestore_transaction_retry.py::normalized_gate_seconds: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('database/firestore_transaction_retry.py', 'normalized_gate_seconds') == ()
    assert fixture.ABLATED_effect_summary('database/firestore_transaction_retry.py', 'normalized_gate_seconds') == ()


def test_sync_defs_database_firestore_transaction_retry_equal_jitter_delay_effects() -> None:
    """database/firestore_transaction_retry.py::equal_jitter_delay: effects fixed=() ablated=()."""
    assert fixture.FIXED_effect_summary('database/firestore_transaction_retry.py', 'equal_jitter_delay') == ()
    assert fixture.ABLATED_effect_summary('database/firestore_transaction_retry.py', 'equal_jitter_delay') == ()


def test_sync_defs_database_firestore_transaction_retry_run_with_transaction_contention_retry_effects() -> None:
    """database/firestore_transaction_retry.py::run_with_transaction_contention_retry: effects fixed=() ablated=()."""
    assert (
        fixture.FIXED_effect_summary('database/firestore_transaction_retry.py', 'run_with_transaction_contention_retry')
        == ()
    )
    assert (
        fixture.ABLATED_effect_summary(
            'database/firestore_transaction_retry.py', 'run_with_transaction_contention_retry'
        )
        == ()
    )


def test_pump_db_import_FirestoreContentionExhausted_resolver_membership() -> None:
    """pump imports database name FirestoreContentionExhausted: pure-exempt=False cm-exempt=False."""
    assert fixture.pump_pure_exempt_names() == ['is_transaction_contention', 'with_batch_privacy_attempt']
    assert fixture.pump_cm_exempt_names() == []


def test_pump_db_import_is_transaction_contention_resolver_membership() -> None:
    """pump imports database name is_transaction_contention: pure-exempt=True cm-exempt=False."""
    assert fixture.pump_pure_exempt_names() == ['is_transaction_contention', 'with_batch_privacy_attempt']
    assert fixture.pump_cm_exempt_names() == []


def test_pump_db_import_with_batch_privacy_attempt_resolver_membership() -> None:
    """pump imports database name with_batch_privacy_attempt: pure-exempt=True cm-exempt=False."""
    assert fixture.pump_pure_exempt_names() == ['is_transaction_contention', 'with_batch_privacy_attempt']
    assert fixture.pump_cm_exempt_names() == []


def test_restrike_publication_ablated_is_the_blackout_regression() -> None:
    """Ablating the pure resolution re-flags exactly the pure-db-classifier callers.

    The contention loss classification (``publication_loss_is_contention`` ->
    ``is_transaction_contention``) is provably pure, so the fixed posture
    keeps every caller clean; ablating that resolution flags exactly the
    lane functions that classify a loss — the re-strike lane and the three
    deferred-drain terminals that share its reporting posture.
    """
    assert fixture.ablated_flagged_functions() == [
        '_drain_after_publication',
        '_drain_deferred_due',
        '_restrike_publication',
        'flush_deferred_drains',
    ]


def test_fixed_scan_flagged_functions() -> None:
    """The fixed posture keeps the re-strike lane clean (the PR-unblock)."""
    assert fixture.fixed_flagged_functions() == []


def test_scanner_carries_the_failure_class_token() -> None:
    """The FC token lives in the scanner and both grid registries."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2]
    scanner_text = (root / 'scripts' / 'scan_async_blockers.py').read_text(encoding='utf-8')
    assert 'FC-async-blocker-gate-false-positive-on-pure-db-classifiers' in scanner_text
    grid_a = (root / 'tests' / 'unit' / 'test_async_gate_pure_classifier_resolution_grid.py').read_text(
        encoding='utf-8'
    )
    assert 'FC-async-blocker-gate-false-positive-on-pure-db-classifiers' in grid_a
    grid_b = (root / 'tests' / 'unit' / 'test_async_gate_context_manager_resolution_grid.py').read_text(
        encoding='utf-8'
    )
    assert 'FC-async-blocker-gate-false-positive-on-pure-db-classifiers' in grid_b
