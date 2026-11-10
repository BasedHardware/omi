# Privacy plan-group attribution verification (2026-11-10)

Baseline: `origin/main` at `85de1985f0fb4fddd05e0de4b36c1ac68108d81e`, fetched
before implementation. `privacy_check_metrics.py` declared reads with
`family,mode,result` and checks with `family,mode,reason`.

`batch_pipeline_privacy.py` already reads `users/{uid}` for privacy authority;
its `subscription.plan` is available without another lookup. Batch job-store
records have no subscription field. `firestore_tier_context.current_tier`
provides an existing process-local request observation, with no loader or I/O;
privacy call sites now require its UID to match the checked owner.

`plan_group` uses `PAID_PLAN_TYPES` and `PlanType.basic` from
`backend/config/plan_catalog.py`, generated from `config/plan_catalog.json`.
The paid set includes `unlimited_v2`, `unlimited`, `plus`, `operator`, `architect`.
The legacy `free` spelling follows `database/users.py` normalization to basic.
This measures stored plan identity, not a new entitlement decision.

Code-based unknown estimates (not measured production percentages):

| Path | Plan source; unknown share |
| --- | --- |
| Batch live/preflight/snapshot export/memo miss/shadow walk | Existing user snapshot; 0% when recognized, 100% when absent/unrecognized. Earlier reads are counted at check exit using that snapshot. |
| Batch attempt/process memo hit | Matching request tier; 100% without it (background job records have no plan). Prior cached decisions never carry a plan forward. |
| Batch stop/error before user snapshot | Matching request tier; otherwise 100%. |
| External/tombstone/deletion-marker, including certificate reads | Matching request tier; otherwise 100% for cold, expired, closed, foreign-owner or background contexts. |
| Retention's standalone batch user read | Matching request tier; otherwise 100%. |

Both GMP keep regexes (`cloud_run_gmp_sidecar.yaml`, `cloud_run_gmp_sync.yaml`)
match the unchanged metric names. `metric-inventory.prod.json` records names,
not labels; both names already exist. No inventory/sidecar change is required.

Zero added Firestore or Redis reads: tests assert the exact original physical
read sequences and that label-only operations leave the client mocks untouched.

Validation through `bin/omi-heavy`: the file-isolated `backend/test.sh` privacy,
worker-metric and request-context selection passed 263 tests in ten files.
`OMI_PR_BODY_FILE=<body> make preflight` passed all 38 selected checks.
