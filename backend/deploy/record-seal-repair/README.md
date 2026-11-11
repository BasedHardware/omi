# Independent in-cluster seal repair

The CronJob is retained **suspended by default** for rollback. The continuous CPU
path and evening overlap procedure are in
[`record-seal-workers.md`](../../docs/runbooks/record-seal-workers.md).

Owner: two-lane lead. Deploy only through the approved worker release train.
The host-side repair loop remains an operator fallback. This job reuses the
worker image, KSA/GSA and encryption-secret reference. It runs on CPU nodes,
independently of the unchanged 240-second sweeper. No GPU is allocated.

When unsuspended: 16 disposable row processes (production values), 270 seconds per row (configurable
1–270), 1500 seconds per cycle, 1680-second Kubernetes Job ceiling, every five
minutes with `concurrencyPolicy: Forbid`. Rows that exhaust a budget are counted
and skipped; all other rows continue. A timed-out transaction might have
committed: the next canonical plan reconciles the row instead of blindly
replaying a write. The controller kills/reaps each row's process group, including
decoder descendants, even when the row leader already exited and on TERM.

Discovery pages completed `batch_live_v1` / `batch_sync_v1` metadata by
`finished_at, __name__` descending (newest first) within each pass, skipping already-closed rows, with hard caps
of 10,000 metadata reads / 1024 unsealed candidates and 60 seconds. The added
collection-group composite index must be READY before deployment. Discovery
reads only finish/closed metadata. Lead ruling `f79d45` authorizes a maintenance
read/write per apply cycle; ruling `4cbd2a` extends this to two encrypted
point writes on the same document and key at
`batch_pipeline_prod_maintenance/record_seal_repair_cursor_v2`. The cursor's
finish time and private path are authenticated/encrypted with a domain-separated
key derived from the existing job encryption secret; no plaintext identities or
cursor payloads are logged. Firestore nanoseconds round-trip without truncation.
It advances **before** slow work and wraps at the end of the pass, so a refused
prefix or closed-row scan cap cannot monopolize every run. Interrupted/deferred
rows are revisited. The initial checkpoint covers the first worker group. After the cycle, a
second checkpoint advances past the last row actually attempted, including
refusals, exhausted budgets and launch failures, but never past deferred rows.
The first checkpoint survives interruption; the next completed pass wraps to
revisit interrupted and oldest rows. No per-row retry state is persisted. `mode=plan` reads but never advances state.
No new IAM, secret or index is required for the maintenance point read/write.
Each pass freezes its upper `finished_at` boundary in that encrypted cursor;
newer inflow waits for the next pass, so it cannot prevent wrapping back to the
oldest refusals. Existing cursors without a boundary start one on their next
read. The discovery query uses the same finish/name index.
Both absent and explicit-false seals are discovered. Each row gets a fresh,
complete, TLS-verified in-cluster pusher PodList, then canonical singleton
`plan_backfill/apply_backfill` (no job) or `plan_seals/apply_seals` (canonical
record job). Apply authority and transaction checks remain unchanged. Before the full
retained-object walk, repair checks the final chunk with the same tail
predicate and a conservative sample-rounding allowance. A clearly short tail
refuses early; an eligible or rounding-ambiguous row still gets the complete
existing overlap, decoding, checksum, unit-budget and frozen/current finish
proof. Metadata loading reuses the reader's generation-pinned GET.

Unknown/refused/failed rows never grant write authority. PodList continuation,
missing inventory, stale proof after tail download, privacy changes, bare/live
producer tokens and upload failures remain refusals. Sync-owned rows without a
canonical record job are refused by the existing no-job planner. No seal rules,
privacy defaults, audio deletion or notification paths change.

These caps do not prove the 30-minute SLO: long/failed proofs, live producers,
refused privacy or an over-budget backlog can still leave old rows. Lead must
measure actual in-cluster plan/apply throughput and the full age census before
the batch ramp. `discovery_saturated`, `deferred`, `budget_exhausted` and error
counts must be investigated. Cursor fairness avoids permanent prefix starvation;
newest-first priority within a pass is still no guarantee of settlement.

## Deploy and refresh policy without restarting workers

Lead rulings `d1dabd` / `9c0230` require explicit serving-role flags in
`recordSealRepair.serverFlags`. An absent/invalid map refuses before cloud
access; laptop ambient flags are never used. Use the existing operator flag
collector against **all positive-traffic serving revisions**, require agreement,
and copy only its admission-policy allowlist into a private Helm values file:

```yaml
recordSealRepair:
  serverFlags:
    K_SERVICE: backend
    BATCH_PIPELINE_ENABLED: "true"
    BATCH_PIPELINE_PERCENT: "0"
    BATCH_PIPELINE_LIVE_ADMISSION_ENABLED: "true"
    BATCH_LIVE_STT_RETIRE_PERCENT: "0"
    # Also preserve the collected final-pass policy inputs and cohort allowlists.
```

This is a shape example, not current production flags. Never commit or print
cohort allowlists. At each ramp rung, lead refreshes the map with the same
already-deployed chart/image and retained release values:

```sh
helm upgrade prod-omi-batch-pipeline-worker backend/charts/batch-pipeline-worker \
  --namespace prod-omi-backend --reuse-values \
  --values /private/repair-flags.yaml --wait --timeout 15m
```

Render before apply and require that only `CronJob/record-seal-repair` changes.
The offline chart regression compares 0% and 100% maps and proves identical
worker Deployments, sweeper and RBAC. No rollout/restart is needed per rung.
Existing repair Jobs retain their startup map for at most 1680 seconds; new Jobs
use the refreshed map. Lead should settle/stop the old repair Job before the
next rung if that overlap is unacceptable.

When live `_ramp` values override revision env defaults, use those effective
percentages in the repair map. Copying only revision env fallbacks is stale.

`register_recording` forces batch/live admission enabled for an already-owned
capture. Tests prove registration succeeds at both 0% and 100%; however its
immutable job policy records different `batch_percent`, `retire_percent`,
`live_stt_retired` and `policy_id`. During the minutes between a rung and the
refresh (or while the previous Job finishes), repaired registrations can freeze
the earlier values. The refresh prevents extending that drift to new Jobs; it
does not rewrite already-created policies. Final-pass inputs must also match
the serving role. Existing pending jobs retain their original admission policy.

## RBAC, metrics and rollback

Both jobs share the existing namespace-only `record-seal-sweeper` Role/Binding:
**pods:list only** for the worker KSA, retained if either job is enabled. No new
IAM/GSA permission is added. Lead must verify the deployer can bind that exact
permission before Helm applies (the existing ci-deployer pods:list grant may
already cover it). No workload YAML/env or PodList is logged or stored.

Counts-only structured JSON rows (`record_seal_repair_row`) contain a closed
disposition, count=1, and seal age in seconds (zero for refusals). Invalid-clock
rows omit seal age and are excluded from both summary age maxima;
`invalid_clock_rows` counts those attempted rows without changing repair eligibility. Proof
refusals also carry a closed `proof_reason`: `tail_lagging`,
`tail_lost_or_unproven`, `overlap_conflict`, `decode_or_checksum`, `budget_limit`,
`finish_missing`, `registration_refused`, or `other`. Tail lagging is a
necessary-condition failure, not proof that an upload will recover or is lost.
No terminal marker or age-gate exemption is written. Summaries
include dispositions, observed oldest age, invalid-clock attempts, saturation and deferred rows. Native
SDK stdout/stderr is suppressed; IDs, exceptions, paths and plan digests are
never output. `log-metrics.json` defines rows by disposition and seal-age
distribution and proof-reason counts; lead installs these metrics through the normal monitoring path.
Metric filters/labels are allowlisted and fixture-tested against private tokens.

Rollback: set `recordSealRepair.runtimeEnabled=false` (registered env kill
switch `RECORD_SEAL_REPAIR_ENABLED=false`), or remove only this job with
`recordSealRepair.enabled=false`. Active Jobs retain their initial settings;
lead stops the active repair Job for immediate cessation. `mode=plan` retains
proof reads but performs no writes. The sweeper and host fallback remain usable.

## Aged pending discovery and proof-gated exits

`RECORD_SEAL_REPAIR_JOBS` defaults on; only `off` disables the added discovery
leg. With `RECORD_SEAL_REPAIR_AGE_ORDER` on (the default), it first scans up to
128 pending jobs in the final 24 hours of their stored
`record_dead_letter_deadline_at`, in deadline/name ascending order. It then
fills remaining job places from up to 128 pending jobs in enqueue/name descending
order (newest first). Both select jobs aged at least the existing 30-minute
partial wait. Enqueue age never fabricates a deadline. The required deadline
and recency composite indexes must be READY before image deployment; the
`gcp_diarizer.yml` batch-pipeline-worker path runs the shared readiness gate.
A missing/building urgent index skips only the urgent leg and emits a
content-free `record_seal_repair_urgent` / `index_unavailable` event; ordinary
and conversation discovery continue. Ordinary recency discovery falls back to
hash order if its index is unavailable. Setting `RECORD_SEAL_REPAIR_AGE_ORDER=off`
skips urgency and restores the original document-order jobs query.

The jobs frontiers are encrypted maintenance documents at
`batch_pipeline_prod_maintenance/record_seal_repair_jobs_cursor_v2` (recency)
and `batch_pipeline_prod_maintenance/record_seal_repair_urgent_cursor_v1`
(deadline). The urgent cursor's `enqueued_at` payload slot carries the raw ordered deadline
value as an encrypted scalar scan position, including skipped malformed clocks.
Eligibility still requires a finite positive stored deadline. The query's
`> 0` floor excludes non-positive deadlines; local rejection advances past
any malformed returned row and adds it to `invalid_clock_rows`. A saturated
malformed page therefore cannot pin valid work behind it. The same existing
state/deadline/name index serves both range bounds. Recency
freezes an enqueue horizon; urgency recomputes its window on each run. Old v1
recency/conversation documents remain for code rollback and are not advanced.

Urgent and ordinary jobs together occupy at most half the first worker group
(one for a single-worker run); conversations keep their existing reservation.
Ordinary discovery runs every enabled run within the shared discovery budget.
For job allocation `A = max(1, workers // 2)`, it reserves `max(1, A // 4)`
places when candidates exist; urgency gets the rest, including unused ordinary
reserve. With 16 workers, ordinary work retains 2 of the 8 job places under
continuous urgency; an empty ordinary pass allows 8 urgent jobs. Urgent jobs
still run in deadline order before ordinary attempts. Unused urgent places
return to ordinary candidates without advancing past held ordinary work.
This is a one-run discovery starvation bound, not a settlement-time guarantee;
see the [priority change note](../../docs/listen_pusher_pipeline/changes/2026-11-10-record-seal-priority.md).
All three legs share the existing discovery deadline, aggregate scan cap, row
cap, worker cap and run deadline. Preview writes none of the three frontiers.
Resolution happens inside the existing disposable row budget.

Producer-token, upload-failed and closed-but-pending rows run the existing
same-digest planner/apply path. Closed rows must pass the full retained-tail proof
against both current and frozen finish times; their job state is never advanced
by repair. Admission remains the owner of that transition. Discovery includes
conversations that never completed, but `not_completed` remains a refusal:
repair does not assume finalization authority from age or producer absence.

A valid partial barrier is re-attemptable after the existing one-hour inventory
poll interval, measured from its last repair or initial partial finish. Fresh
producer and transactional privacy proof is required by `finish_partial`; the
barrier and its generations remain intact, and no complete seal is written.
Aged retired coordinators may also reopen through this same fresh-proof transaction.

After seven days (seven existing inventory-idle windows), a missing conversation
may terminally cancel its canonical pending job. A single transaction rechecks
absence, identity, numeric age and privacy. Like `cancel_fenced_recovery`, a
privacy refusal permits only revocation of work; erasure owns all content and
artifact deletion. Cancellation writes no speech receipt, TTL or conversation.

Row events include a closed `blocker` and `disposition`; the aggregate
`blocker_outcomes` counts their combinations. `log-metrics.json` registers
`omi_record_seal_repair_blocker_outcomes` for the Kubernetes CronJob. This repair
is not served on Cloud Run; the `omi_.*` GMP keep list also covers the metric
name. Set `recordSealRepair.jobsDiscovery=off` to pass `RECORD_SEAL_REPAIR_JOBS=off`
to the CronJob and restore the prior discovery and partial-retry behavior. Existing
custody owners stay unchanged.
