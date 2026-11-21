# Reach and reconcile projection holds

Held release now scans committed jobs with `recovery_state=held` as well as
results with `projection_state=quarantine_held`. Multipart results can still be
`persisted` while their summary or a part is quarantined with
`disposition=ambiguous_generation`. Both discovery legs have independent durable
cursors and share the existing per-pass row and time budgets; their first turn
alternates durably. The assignment leg uses the existing, default-on
`BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED` switch. Turning it off also
restores the former result-state admission gate. Target restorability, the
three-release attempt cap, privacy refusal and operator-intent fences still apply;
proven multipart suffixes and their follow-ups survive release.

`hold_for_quarantine` now settles ready siblings' discovery hints to `ready`
when `BATCH_PIPELINE_PROJECTION_FOLLOWUP_PAGE_ENABLED` is on (the default); when
it is off, only the current row's hint is settled. A sibling's quarantine does
not make a completed receipt held. Existing ghost
hints can be repaired separately with
`backend/scripts/reconcile_batch_projection_ghost_holds.py`. The script defaults
to `--dry-run`, requires an explicit project/namespace, prints aggregate counts
only, and bounds page size, total rows and RPC time by a deadline. `--apply`
updates only the hint with a snapshot-update-time precondition. It skips real
summary/part quarantines and concurrent changes, and is idempotent. This change
does not run the script or change any environment.

Contract: [batch pipeline](../../listen_pusher_pipeline.mdx).
Evidence: regression tests in `test_batch_pipeline_projection_release.py`,
`test_batch_pipeline_quarantine.py` and `test_reconcile_batch_projection_ghost_holds.py`.
