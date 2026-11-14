# Projection finish clock backfill

The finish-backoff lever only filters after the versioned marker in
`<namespace>_control/projection_finish_clock_v1` is complete. Before that,
serving uses the legacy page without adding per-row stamp transactions. Negative
marker lookups are cached for 60 seconds; completion is trusted for the process
lifetime. The marker uses one existing control document per namespace: at
most one read per process per minute before completion and one per process
lifetime afterward; the read flag off performs no marker reads. New replicas read that same marker and filter on their first tick.

Deploy this code to **every writer first**, including backend-listen
(`BATCH_PIPELINE_SERVING_ENABLED=false`, `BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED=true`). The
shared `projection_finish_state_fields` and `projection_finish_entry_fields`
helpers now stamp persisted/ready transitions regardless of the read lever.
Writer audit: ordinary and multipart persistence/receipt transitions go through
`ProjectionSession`; quarantine release, recovery, and ready transitions use
`ProjectionStore` / `batch_pipeline_projection_release`; privacy restore uses
`batch_pipeline_projection_privacy`; the ghost-hold repair script also uses the
shared helper. Merge creates pending rows; purge only creates erased rows.
Do not finish the pass while any old writer binary is still active: it could
insert an unstamped row behind the checkpoint. Post-marker rollback of the read
flag is safe; rollback of writer code requires repeating maintenance with a new
marker version before enabling filtering again.

The Store contract includes marker readiness for every backend. Postgres and
simulation stores read the versioned marker from their own namespaced control
store; the Postgres simulation delegates to Postgres. A missing or wrong-version
marker keeps legacy discovery active. The stamping CLI in this runbook operates
on Firestore only: its completion does not certify a different store's result
population or authorize native Postgres filtering.

## Re-enable bar (2026-11-13 agreement)

Keep `BATCH_PROJECTION_FINISH_BACKOFF_ENABLED=false` until **all** conditions hold:

1. The per-process survey has been replaced by the one-time stamping pass and
   shared completion marker, and the pass has completed after every writer deploy.
2. #25145 / SCA-1799 is merged **and deployed**, and both
   `omi_batch_projection_finish_reads_total` and
   `omi_batch_projection_finish_completed_total` read **nonzero in GMP**.
3. Every persisted/ready writer maintains the clock, including backend-listen,
   Cloud Run jobs, and operator scripts. Review the attached source evidence in
   [projection-finish-writer-audit.md](projection-finish-writer-audit.md), and
   confirm the admitted writer revision is deployed on all hosts before stamping.

All production rolls and re-enable decisions go through the rollout lead.
The lead reported 37 listen pods and the integration flag off since
2026-11-13 17:31:30Z (img5); those are supplied rollout facts, not measurements
made by this code-only task. Flags remaining on non-sweeping services do not
satisfy this bar. Repo disablement is owned by SCA-1993.

Use the approved read-only/operator identity for the selected stage. This PR
performs no production writes. Example operator commands from `backend/`:

```bash
# Bounded read-only preview at the current durable checkpoint (one page).
GCP_AGENT_TIER=ro-prod python scripts/batch_pipeline_projection_finish_backfill.py --stage prod
# Separate authorized operator action, after all writers have been deployed.
GCP_AGENT_TIER=prod-operator python scripts/batch_pipeline_projection_finish_backfill.py --stage prod --apply --confirm-writers-deployed --max-pages 1000
```

Each invocation reads at most `--max-pages * --page-size` rows (page size is
capped at 200) plus transactional fences. Repeat the apply command until output
reports `complete: true`. Every page atomically commits missing clocks and its
shared cursor. Errors leave that page retryable. Concurrent operators cannot
commit a stale checkpoint. Existing clocks, projection state and payloads are
preserved. The script prints aggregate counts only. Dry-run neither stamps nor
advances the cursor and is a bounded preview, not a whole-population census.
An exactly full last page requires one further empty page to mark completion.

After completion, enable `BATCH_PROJECTION_FINISH_BACKOFF_ENABLED=true`.
The filtered query's existing Firestore index must be ready. Keep the lever off
until #25145 exports the guard counters. Compare a matched 24-hour flag-off/on
window: `omi_batch_projection_finish_reads_total` per completion and Firestore
reads attributed to `database.batch_pipeline_projection:*` must fall. Independently
scan persisted/ready rows and count absent `projection_finish_due_at` fields;
Firestore inequality filters cannot find absent fields. That count must remain
zero after maintenance and as backend-listen continues writing. These production
checks are deployment acceptance, not claimed by local tests.

Kill switch: `BATCH_PROJECTION_FINISH_BACKOFF_ENABLED=false` restores the legacy
query immediately and stops no-change deferral transactions. Additive clock
writes on state transitions continue, keeping a later re-enable safe.
