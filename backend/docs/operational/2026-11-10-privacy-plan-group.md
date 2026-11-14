# Privacy plan-group attribution verification (2026-11-10)

Baseline: `origin/main` at `85de1985f0fb4fddd05e0de4b36c1ac68108d81e`, fetched
before implementation. `privacy_check_metrics.py` declared reads with
`family,mode,result` and checks with `family,mode,reason`.

`batch_pipeline_privacy.py` already reads `users/{uid}` for privacy authority;
its `subscription.plan` is available without another lookup. Batch job-store
records have no subscription field. `firestore_tier_context.current_tier`
provides an existing process-local request observation, with no loader or I/O;
privacy call sites now require its UID to match the checked owner.

`plan_group` explicitly projects the existing meter's `split.segments` mapping
(`omi-workspace/infra/finops/margin/margin_core.py:segment_rollup`, backed by
`omi-knowledge-base/projects/admin-omi-tv-dashboard/margin-basis.json`): basic
(and legacy free) → free; architect/operator/plus/unlimited → paid;
unlimited_v2 → unlimited_v2; anything else → unattributed. It uses the backend
`PlanType` constants. This is telemetry only, with no privacy behavior change.

Code-based unattributed estimates (not measured production percentages):

| Path | Plan source; unattributed share |
| --- | --- |
| Batch live/preflight/snapshot export/memo miss/shadow walk | Existing user snapshot; 0% when recognized, 100% when absent/unrecognized. Earlier reads are counted at check exit using that snapshot. |
| Batch attempt/process memo hit | Matching request tier; 100% without it (background job records have no plan). Prior cached decisions never carry a plan forward. |
| Batch stop/error before user snapshot | Matching request tier; otherwise 100%. |
| External/tombstone/deletion-marker, including certificate reads | Matching request tier; otherwise 100% for cold, expired, closed, foreign-owner or background contexts. |
| Retention's standalone batch user read | Matching request tier; otherwise 100%. |

Both GMP keep regexes (`cloud_run_gmp_sidecar.yaml`, `cloud_run_gmp_sync.yaml`)
match the unchanged metric names. `metric-inventory.prod.json` records names,
not labels; both names already exist. No inventory/sidecar change is required.

Zero added reads: `test_batch_labels_all_existing_reads_and_decision`,
`test_memo_hit_uses_only_matching_request_plan`, and
`test_nonbatch_paths_use_only_live_matching_request_context` assert exact read
sequences. Batch counters flush at check exit; a hard kill mid-check drops that
check's buffered reads. Unit output and CI verdicts are recorded in PR #25076.
