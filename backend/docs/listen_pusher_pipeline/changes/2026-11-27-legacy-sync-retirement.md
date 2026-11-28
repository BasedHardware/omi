# Legacy sync retirement

[Legacy-dark runbook](../../runbooks/legacy-dark.md) · [#26537 containment](https://github.com/BasedHardware/omi/pull/26537) ·
[#26549 deletion](https://github.com/BasedHardware/omi/pull/26549) · SCA-2965

## Containment (#26537)

Legacy sync has been dark in production since 2026-11-04 (`rollout_cohorts/_ramp` `legacy_sync=dark`), but
a failed `_ramp` read made `legacy_sync_mode()` fall back to `on`. Every decline in batch intake is gated on
`on`, so those uploads still created legacy jobs. The mode now keeps the last-known-good value on a read
error: a process that already read `dark` stays dark. A process whose first read is still pending or has
failed still serves `on` until one read succeeds.

The `sync-backfill-uid-sequencer` Scheduler job and its three alerts left `jobs.yaml` and the
`sync-backfill-lifecycle` action. Reconcile never deletes, so Release deletes the job and disables the alerts
by hand once the change serves (runbook, "Retiring the sequencer Scheduler job").

## Deletion (#26549)

The legacy executor, sequencer, worker and redrive code are deleted; batch serves every sync upload.
`legacy_dark.current_mode()` always returns `dark`. The ownership fence stays because legacy ledger rows
and `legacy_final_pass_v1` owners outlive the code.

- Stranded, capped or refused uploads get 409 `sync_content_in_progress` with `job_id: null` and
  `Retry-After: 60`. Released apps treat a job-less in-progress 409 as an account-wide upload cooldown, so
  the hint is never the capped recording's remaining repeat-failure pause.
- `legacy_segment_core.py` keeps the segment code that cap-hold recovery still calls, until the C11 rehome.
- The 9 retired sync env keys are `forbidden_env` on `backend-sync` and `backend-sync-backfill`, so the next
  deploy removes them.
- The sync-backfill queues and the `backend-sync-backfill` service stay: stored `sync_reprocess` bindings and
  the dream-agent sweep still use them.

## Rollout and evidence

No flag. Merge #26537 first; #26549 merges after a 6 h soak with `omi_legacy_sync_admissions_total` flat at 0,
a zero drain census and the sequencer job deleted. Rollback is reverting the PR; after the soak, legacy has served no new
admissions. The readback is on SCA-2965.
