# Episode log round 4: committed writes with queued capture

Measured locally on m5-mbp, 2026-11-05, for PR #24607 (`lane/epbatch2`),
starting from `4bbf3f7ac5673dd62ec6546e0d28565850250bfa`. These are unit and
loopback-emulator results, not production acceptance. No GCP tier, human cloud
credentials, production data, TTL apply, merge or deploy was used.

## Mechanism and cost

A committed episode write can leave its capture in the background queue. The
append watermark and dirty token alone cannot detect that write. Full gap repair
now records source document paths and Firestore `update_time` values, including
receipt archives, then re-reads those sources inside the publishing transaction
before any writes. An edit, insertion, deletion or archive change rejects stale
publication, retaining dirty and legacy Home routing. Later source writes
serialize against the transactional recheck. Receipt archive events retain their
parent conversation ID.

This implements requested option (b). Serving-path delta is **zero reads,
writes, fields or RPCs**. A full repair adds at most 128 source-document reads
and their transaction locks, plus minimum charges for empty collection queries;
ordinary drains do not run this recheck. The initial repair remains bounded to
128 documents including prior projections. No new index is needed; the query
contract driver registers the shared source read.

Capture admission precedes the periodic guard and client construction; the guard
also checks admission directly. Capture off plus inactive TTL makes zero
`episode_facts` queries. The query-shape driver explicitly admits capture to
exercise the enabled guard. The older guard-off expectation now asserts that
neither the data client nor the guard is called.

The overflow invalidation remains synchronous: two document reads (account
marker and owner), one owner write, at most two SDK commit attempts and no outer
retry. Submission failure normally requires all four workers and 64 queued slots
to be occupied; cancellation also fences. Accepted capture remains asynchronous.
Re-enqueuing invalidation into the saturated pool would not fence readiness.
These are operation/retry bounds; SDK/network latency still applies on failure.

## Qualification

All commands below were routed through
`/Users/dazheng/workspace/omi/bin/omi-heavy run --`, with
`GOOGLE_APPLICATION_CREDENTIALS` and all `CLOUDSDK_*` variables removed. Unit
files ran in separate processes through `backend/test.sh`, retaining its timing
guard. No skips, hook bypasses, concurrency reductions inside a proof, or retry
budget changes were used.

- The same 85-file round-3 acceptance selection plus the new round-4 file:
  **2,957 passed**, including round-2/3 regressions and the policy-entry race.
- Focused log selection: **139 passed** across nine isolated test files,
  including all round-2/3 suites and six new round-4 cases.
- The same 17 round-3 CI regression files: **127 passed**.
- `firebase emulators:exec --only firestore --project demo-omi-isolated-tests
  'backend/.venv/bin/python -m pytest -q
  backend/tests/integration/test_episode_log_emulator.py'`: **19/19 passed**.
  This includes a real serving close committed after the reconciliation snapshot
  with its capture queued. At 100% read admission the actual Home route uses
  legacy; delivery alone leaves dirty, then successful reconciliation publishes
  the closed state and permits log routing. Separate proofs reject source edits,
  inserts, deletes and archive edits atomically, preserving dirty/checkpoint state.
- Combined log + recorded-timeline emulator command: **45 passed, 2 failed**.
  Both failures are in unchanged timeline contention tests:
  `test_simultaneous_late_devices_converge_on_one_closed_episode` and
  `test_concurrent_live_and_recorded_attachments_preserve_timeline`, exhausting
  existing transaction attempts after `409 Transaction lock timeout`. All 19 log
  proofs pass in this combined run too. This is an unresolved contention signal;
  the combined emulator suite is not green. Both owned emulator runs shut down.
- Initial preflight found the new query helper missing its driver and the old
  TTL driver no longer reaching the guarded query. Both drivers were corrected.
  Initial focused validation found the superseded guard-off expectation;
  that assertion was corrected to the new zero-query contract.

- Final `OMI_CHECKS_JOBS=1 BACKEND_PYTEST_WORKERS=1
  OMI_PR_BODY_FILE=<round-4-body> make preflight`: **70/70 checks passed**
  in 336.78 seconds, including the complete Firestore query contract.

The [runbook](../runbooks/episode-log.md) retains the separately authorized
TTL → capture → soak → read-ramp train and its rollback requirements.

<details>
<summary>Acceptance selection (backend/test.sh file-list input)</summary>

```text
tests/unit/episode_log_support/__init__.py
tests/unit/episode_log_support/facts.py
tests/unit/episode_log_support/oracle.py
tests/unit/test_app_roles_route_census.py
tests/unit/test_attach_cloud_run_gmp_sidecar.py
tests/unit/test_batch_pipeline_shadow.py
tests/unit/test_batch_pipeline_shadow_projection.py
tests/unit/test_capture_groups.py
tests/unit/test_conversation_discard_revival.py
tests/unit/test_conversation_persistence_transaction_expiry.py
tests/unit/test_conversation_revision_contract.py
tests/unit/test_conversation_smart_merge.py
tests/unit/test_conversation_smart_merge_audit.py
tests/unit/test_conversation_smart_merge_audit_sdk.py
tests/unit/test_conversation_smart_merge_finalizer.py
tests/unit/test_conversation_smart_merge_flatten.py
tests/unit/test_conversation_smart_merge_flatten_ancestry.py
tests/unit/test_conversation_smart_merge_flatten_runtime.py
tests/unit/test_conversation_smart_merge_flatten_sdk.py
tests/unit/test_conversation_smart_merge_intervening_discarded.py
tests/unit/test_conversation_smart_merge_metrics.py
tests/unit/test_conversation_smart_merge_policy.py
tests/unit/test_conversation_smart_merge_state.py
tests/unit/test_conversation_smart_merge_wallclock.py
tests/unit/test_conversation_smart_merge_wallclock_policy.py
tests/unit/test_conversation_summary_mutation.py
tests/unit/test_conversation_typesense_index.py
tests/unit/test_episode_attach_cost.py
tests/unit/test_episode_attach_review.py
tests/unit/test_episode_batch_audio_close.py
tests/unit/test_episode_batch_pending_alert.py
tests/unit/test_episode_boundary_evidence.py
tests/unit/test_episode_claim_read_validation.py
tests/unit/test_episode_closed_skip.py
tests/unit/test_episode_composer.py
tests/unit/test_episode_eval_arms.py
tests/unit/test_episode_eval_resilience.py
tests/unit/test_episode_evidence.py
tests/unit/test_episode_experiments.py
tests/unit/test_episode_finalize_owed.py
tests/unit/test_episode_gateway_parity.py
tests/unit/test_episode_home_read.py
tests/unit/test_episode_live_integrity.py
tests/unit/test_episode_log_api.py
tests/unit/test_episode_log_backfill_cli.py
tests/unit/test_episode_log_projector.py
tests/unit/test_episode_log_review.py
tests/unit/test_episode_log_telemetry.py
tests/unit/test_episode_log_worker.py
tests/unit/test_episode_notes_eval.py
tests/unit/test_episode_notes_scale.py
tests/unit/test_episode_output_language.py
tests/unit/test_episode_receipts.py
tests/unit/test_episode_segment_claim_invalidation.py
tests/unit/test_episode_writer.py
tests/unit/test_episode_writer_runtime.py
tests/unit/test_episodes_client_gate.py
tests/unit/test_episodes_finalize_paths.py
tests/unit/test_episodes_finalizer_hook.py
tests/unit/test_episodes_incremental_live.py
tests/unit/test_episodes_metrics_export.py
tests/unit/test_episodes_policy_state.py
tests/unit/test_episodes_router.py
tests/unit/test_episodes_service.py
tests/unit/test_firestore_field_indexes.py
tests/unit/test_homesettle.py
tests/unit/test_lifecycle_state_table_writers.py
tests/unit/test_monitoring_telemetry_contract.py
tests/unit/test_omi_flags.py
tests/unit/test_pusher_audio_projection.py
tests/unit/test_reason_label_enums.py
tests/unit/test_reconcile_firestore_field_exemptions.py
tests/unit/test_recorded_span.py
tests/unit/test_route_policy_inventory.py
tests/unit/test_route_policy_preflight.py
tests/unit/test_strict_firestore_transaction.py
tests/unit/test_summary_persistence.py
tests/unit/test_sync_assignment_contention_retry.py
tests/unit/test_sync_assignment_recovery.py
tests/unit/test_sync_cross_job_assignment.py
tests/unit/test_sync_fragment_visibility.py
tests/unit/test_sync_reprocess_coalesce.py
tests/unit/test_sync_silent_failure.py
tests/unit/test_episode_log_round2.py
tests/unit/test_episode_log_round3.py
tests/unit/test_episode_log_round4.py
```

</details>

<details>
<summary>Round-3 CI regression selection (backend/test.sh file-list input)</summary>

```text
tests/unit/test_advice_update_missing_doc_guard.py
tests/unit/test_static_map_error_sanitization.py
tests/unit/test_screen_activity_search_utc.py
tests/unit/test_goals_wrapped_firmware_hardening.py
tests/unit/test_file_tools_sanitization.py
tests/unit/test_delete_account_stripe_cancel.py
tests/unit/test_calendar_timezone.py
tests/unit/test_screen_activity_tool_result_bound.py
tests/unit/test_integration_base_sanitization.py
tests/unit/test_folder_assignment_category.py
tests/unit/test_apple_health_tools_sanitization.py
tests/unit/test_gmail_tools_sanitization.py
tests/unit/test_delete_account_purge_storage.py
tests/unit/test_omi_product_tool_failsoft.py
tests/unit/test_calendar_tools_sanitization.py
tests/unit/test_advice_deserialization_resilience.py
tests/unit/test_omi_tools_resilience.py
```

</details>
