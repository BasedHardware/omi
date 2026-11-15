# Production jobstore mirror: source contract and release prerequisites

Status: **production copying remains closed**. The owner-aware admission helper
is preparation for the index-first production mirror; existing namespace-only
factory and refresh callers still refuse `batch_pipeline_prod` in production.
This document establishes no deployment, retained production copy, live parity,
serving acceptance or savings. No production data or credentials were read for
this preparation.

The source baseline is `6a0fe352db1220059456488b2ac752420ebd1c44`, inspected
2026-11-15 in `BasedHardware/omi`, branch `lane/jobstore-index-mode`. The later
production-mirror ruling is recorded in the owning omi-workspace record
`data/run-2026-11-14-jobstore-index/lead-state.md` (David's 2026-11-14 rulings).
It approves starting `prod-jobs` for a sampled production mirror once source is
ready to deploy. The release executor still owns deploys and flag changes.
It does not authorize Postgres serving authority, new privacy enforcement or
unfreezing PR #25215.

## Separate admission paths

[The dark-mirror contract](jobstore-dark-parity.md) describes package C's
staging-only boundary under L02-2. That path remains unchanged: an explicitly
listed `batch_pipeline_prod` is admitted with `OMI_DEPLOYMENT=staging` and
`FIRESTORE_DATABASE_ID=staging`. Setting production-mirror controls cannot let
a staging deployment reach the production database. The boot-time staging
isolation fence is unchanged.

`utils.staging_fence.jobstore_production_mirror_configured(env=None)` validates
the proposed production configuration. It is only a pure configuration check.
It does not construct a client, establish actual identity or select any row.
It requires all of the following, with exact values and no inferred defaults:

| Setting | Required value |
| --- | --- |
| `OMI_DEPLOYMENT` | `prod` |
| `OMI_ENV_STAGE` | `prod` |
| `GOOGLE_CLOUD_PROJECT` | `based-hardware` |
| `OMI_CUSTOMER_DATA_PROJECT` | `based-hardware` |
| `OMI_FIRESTORE_DATA_PLANE_PROJECT` | `based-hardware` |
| `FIRESTORE_DATABASE_ID` | `(default)` |
| `JOBSTORE_SHADOW_NAMESPACES` | Exact entry `batch_pipeline_prod`; no wildcard |
| `JOBSTORE_PG_HOST`, `JOBSTORE_PG_DATABASE`, `JOBSTORE_PG_USER` | All explicitly nonempty |
| `JOBSTORE_PRODUCTION_MIRROR` | Exact `on`; unset, `off` and every other value refuse |
| `JOBSTORE_PRODUCTION_MIRROR_SAMPLE_BPS` | Canonical ASCII integer `1` through `10000` |

`FIRESTORE_EMULATOR_HOST` must be unset or empty. Present project aliases
`GCLOUD_PROJECT`, `GCP_PROJECT` and `FIREBASE_PROJECT_ID` must also name
`based-hardware`. Whitespace does not normalize a production context or owner
into an accepted value. Existing comma-separated namespace entries retain their
existing whitespace handling; the caller's namespace itself is exact.

The two new configuration keys are `JOBSTORE_PRODUCTION_MIRROR` (default `off`)
and `JOBSTORE_PRODUCTION_MIRROR_SAMPLE_BPS` (default `0`, refusing admission).
Missing, zero, negative, decimal, signed, leading-zero, whitespace, non-ASCII
or out-of-range sample values refuse admission. These declarations must enter
the owning flag registry/budget before release; this helper does not edit
runtime manifests or enable either setting. The normal `BATCH_JOBSTORE_MODE`
and `JOBSTORE_SHADOW_WRITES` gates continue to apply in their owning paths.

`jobstore_shadow_admits(namespace, env=None, *, owner_key=None)` additionally
requires a canonical `privacy_owner_key`: exactly 64 lowercase hexadecimal
characters. Raw UIDs, unknown owners and whitespace-padded keys refuse. The
cohort bucket is stable across processes, restarts and rows of the same owner:

```text
int(sha256("omi:jobstore-production-mirror:v1:" + owner_key).hexdigest(), 16) % 10000
```

The owner is selected only when its bucket is less than the configured basis
points. Increasing the threshold adds owners without resampling existing ones.
Explicit `10000` supports a later release-owned full-cohort ramp; it is not a
sampled-cohort approval. Even at `10000`, a namespace-only call returns false.
Keep the sample domain stable when changing thresholds.

## Source work required before opening the production factory

Sampling belongs at the current-document copy boundary in
`database/jobstore/dual_store.py`, not at namespace construction. Live writes,
post-commit refreshes and backfill converge on `DualStore.copy_current`; its
advisory key locks, primary re-read and namespace purge barrier must remain.
A namespace declaration does not sample owners.

The integration owner must complete and test these contracts before a factory
uses `jobstore_production_mirror_configured` to build any production copy:

1. Resolve ownership from the freshly re-read document and its table/key
   contract, checking any `owner_id` against `owner_key`. Owner-keyed `owners`,
   `merge_holds` and `allowance_holds` can lack an owner field; queues use
   `<priority>_<owner_key>`. Missing, conflicting or malformed ownership cannot
   authorize an upsert. Do not sample segment IDs or individual rows.
2. Apply `jobstore_shadow_admits(..., owner_key=resolved_owner)` before every
   production upsert, including direct refresh, claim refresh and backfill.
   A missing primary document must still delete its copy. Exclusion, malformed
   ownership or a reduced cohort must retire a pre-existing copy rather than
   skip and retain it. Test a queued copy across a cohort change.
3. Classify every mirrored table: `jobs`, `results`, `owners`, `queues`,
   `control`, `intakes`, `artifacts`, `allowance_holds`, `merge_holds`, `gpus`
   and `pull_claims`. Scheduler control rings contain multiple owners; GPU and
   pull-claim rows are shared; global control markers have no owner. Omit a
   shared row from the initial production mirror unless an explicit projection
   can prove it contains only selected owners and recomputes derived fields
   consistently. Never admit the entire shard because one owner is selected.
4. Filter captured transaction reads, convergence rechecks and diagnostics
   consistently. A raw pre-image may include excluded owners before the
   copy-time filter. Sampled discovery results are incomplete by design;
   whole-population Firestore-vs-PG queries must not claim a match or raise an
   actionable divergence from an intentionally partial index. Add a common
   cohort projection or decline those observations explicitly. Query parity
   remains off until that contract is implemented.
5. Preserve synchronous erasure independently of cohort, mode, namespace
   admission and write kill switches. Shrinking the cohort or turning mirroring
   off must not suppress deletion, leak a retained shared row or recreate an
   excluded owner's full document during reconciliation.
6. Make the initial census/backfill cohort-aware, bounded and resumable, with
   explicit read/copy budgets and counts for selected, excluded, unknown-owner,
   stale and deleted rows. The current `python -m database.jobstore backfill`
   explicitly refuses every non-staging deployment. Do not remove that guard
   as a shortcut: its whole-table census, `seen`/PG key sets and counts are not
   a bounded production sampled backfill. A live mirror alone leaves older
   unchanged rows absent; a dropped queue item remains a coverage gap.

## Retention and erasure blockers

Production retention is a source prerequisite even while Firestore owns all
claims and transactions. A non-authoritative database can still retain
customer data after it should have been erased.

The current mirror omits `repair_lineage` and `gpus.segment_id`. Keep both
omissions. They do not settle retention of the rest of a document.
`utils/batch_pipeline/retention.py` stamps Firestore `expires_at` on completed
jobs, results, intake receipts and cleaned artifact metadata, and schedules a
best-effort refresh of that state. Firestore's later TTL deletion does not run
that Python hook. Migrations `0001` through `0008` and `PostgresStore` contain
no copy-expiry sweep. The staging backfill counts PG-only rows but does not
delete them. Without an additional retirement mechanism, a production mirror
can retain an expired row indefinitely.

Before real rows are copied, the release packet needs the owning retention
contract for each table and evidence of copy retirement after primary TTL,
including a dropped final refresh and an unavailable PG target. Derive erasure
from the authoritative source and existing retention/legal-hold rules; this
preparation defines no new TTL, custody rule or authority fence. Any retained
copy and backup lifetime must satisfy the same approved contract. This gap
cannot be cleared by admission tests or by omitting lineage alone.

### Minimal bounded copy-retirement design (not implemented)

Use a release-owned, resumable reconciliation pass scoped to the registered
production target and exact `batch_pipeline_prod` namespace. Bound each run by
row count, primary-read count, PG statements and a hard deadline; checkpoint
only committed pages using an opaque cursor in approved operator state. A due
expiry index can prioritize work, but a rotating key-ordered census must also
visit rows with missing/stale expiry metadata: the final expiry-stamping refresh
may have been dropped. Do not allocate the current backfill's whole-table key
sets. Publish counts, cursor progress, last successful coverage and oldest
unresolved candidate without customer payloads or raw keys.

Maintain an audited per-table classification of existing retention fields.
Firestore datetime `expires_at` values are encoded by `codec.py` as
`{"$datetime": ...}`; numeric `pull_claims.expires_at` is a lease deadline,
not a document-retention deadline. Do not infer a TTL from a similarly named
field, row age, terminal state or a missing clock. No new interval is needed.

For each candidate, acquire the existing shared namespace purge barrier and
per-key lock, then re-read its authoritative primary document. An absent primary
must retire the copy under the applicable approved hold contract. A present
primary with changed or removed expiry refreshes the copy's classification
through the same cohort/projection policy. A valid, current retention deadline
can retire only the copy when the owning table contract permits it; never
delete or advance Firestore state. Confirm legal-hold precedence and the
authoritative hold lookup with the retention owner before implementing this
step. An unresolved hold is an explicit blocker, not permission to expire or
retain production data indefinitely.

Unknown-owner, malformed-clock and legacy rows need a bounded reconciliation
route and named disposition. Re-read by exact primary key, never guess an
owner or extend retention. Missing clocks require the rotating census; missing
ownership cannot authorize a new upsert. Cohort shrink must retire excluded
copies using the same locks and must not strand them behind an admission
refusal. If legacy or hold semantics cannot be resolved, keep production
admission closed rather than calling quarantine a completed retirement.

Retirement and synchronous privacy erasure must run independently of mirror
write enablement, owner sampling and cached writer handles. Keep target
configuration and service reachability until both have no retained obligations.
Required emulator/PG tests include dropped expiry refresh, Firestore TTL removal,
expiry extended/removed before reread, legal hold, unknown owner, malformed or
missing clock, legacy row, cohort shrink, copy/purge concurrency, PG failure
and resumed pages. A run deadline or PG outage leaves an explicit retryable
obligation; it cannot publish successful full coverage. The release packet must
set and measure the maximum retirement lag against the existing retention
contract before any real production copy is admitted.

Existing deletion seams to preserve and exercise are:

- `database/batch_pipeline_purge.py::purge_batch_owner`: visits both stage
  namespaces on the customer data plane and calls `purge_jobstore_owner`
  before declaring privacy purge complete.
- `database/batch_pipeline_conversation_purge.py`: the resumable `shadow`
  phase calls the same synchronous erasure path and retains its obligation
  on failure.
- `database/jobstore/dual_store.py::purge_owner`: reaches cached or configured
  cold copies with mirroring disabled; partial target configuration, missing
  driver or PG failure raises into retry. Keep target configuration and PG
  reachability in every deletion executor until all retained copies retire.
- `DualStore.purge_owner_now`: reconciles owner-linked and owner-keyed rows
  plus shared scheduler/pull-claim/GPU state under the purge barrier. Its
  second scan covers only an old copier that finishes within its bounded
  settle window. It does not prove arbitrary old binaries cannot recreate data.

`tests/integration/test_jobstore_purge_postgres.py` exercises account and
conversation cold-copy erasure, dropped refreshes, shared rows and copy/purge
races. Its synthetic primary with real PG is source evidence, not live
production acceptance. Run an updated emulator/PG cohort matrix before review.

The release owner must inventory actual serving writer revisions and drain all
old production copy producers before admission. Include CPU intake/live/provider
callers, serving timers, GPU workers, successful claim CAS, projection and
quarantine/recovery writers, projection-finish backfill, retention cleanup,
account purge and resumable conversation purge. Trace `shadow_from_env` and
`mirror_refresh` in the current source as well as direct Firestore writers.
`tests/support/lifecycle_writer_inventory.py` and
`tests/support/terminal_writer_inventory.py` are source writer ratchets; they
do not establish which binaries are running or complete mirror-hook coverage.
The frozen authoritative-store/privacy-fence program is not an implementation
dependency to revive for this mirror; the existing erasure and retention
obligations still apply.

## Future release-owner sequence

1. Pin the reviewed source head and complete terminal CI for the dark mirror
   and the separate production cohort/retirement integration. Record the
   approved source scope, actual producer inventory and deletion executors.
   Resolve every source blocker above. There is no time-only soak gate.
2. Through the release executor, verify the intended `based-hardware`
   `prod-jobs` instance, database name, private host and runtime IAM database
   user from current control-plane evidence. Start it only when source is
   ready to deploy, under David's recorded startup ruling. Do not infer the
   database name or privileges from this source document. IAM or credentials
   changes require their own specific approval.
3. Against that exact `JOBSTORE_PG_*` target, apply the released build's
   `python -m database.jobstore migrate`, then `status`. The current source
   requires all contiguous migrations `0001_doc_mode_store.sql` through
   `0008_allowance_holds.sql`, with matching recorded checksums. No fence,
   journal or authoritative-store migrations from frozen PR #25215 are
   admitted by this packet. The only production mirror namespace is
   `batch_pipeline_prod`; database migrations themselves are schema-wide.
4. Deploy via the ordinary train. Verify release SHA or digest on every
   serving revision/pod in the writer inventory, traffic distribution and a
   new metric/log from that artifact. Configure every deletion executor with
   the retained-copy target before the first production copy, and prove its
   failure/retry and mode-off erasure behavior.
5. Record a specific initial BPS threshold, absolute read/write/connection and
   spend budgets, named release guard, expansion owner and next evidence review
   time. Begin a small deterministic production cohort only after owner-resolved
   filtering, backfill and copy retirement are verified. Keep Firestore as
   the sole writer/claimant and `BATCH_JOBSTORE_MODE=shadow`; index reads need
   their own source and release packet. Start parity only after comparisons
   share the cohort contract.
6. Review fresh cohort coverage, dropped/error/timeout observations,
   convergence, copy expiry, erasure completion, PG capacity and attributable
   extra Firestore reads. A missing, unknown or dropped observation is not a
   pass. Expand only on those measurements and the owning approval; `10000`
   requires an explicit complete-population release decision. No arbitrary
   elapsed interval substitutes for these prerequisites.

Rollback new work with `JOBSTORE_SHADOW_WRITES=off`,
`JOBSTORE_PRODUCTION_MIRROR=off`, or `BATCH_JOBSTORE_MODE=firestore` through the
release owner. Verify queued work stops as specified by the integrated copy
path; cached copy handles must not bypass the live opt-out. Preserve
`JOBSTORE_PG_*`, database availability and deletion-executor access while copies
remain. Rollback does not erase retained rows. Retire copies using the proven
erasure/retention path before removing the target or stopping `prod-jobs`;
never trade a new-mirror rollback for broken privacy deletion.

## Local admission verification

From `backend/` in the task worktree, using that worktree's own virtualenv:

```bash
/Users/dazheng/workspace/omi/bin/omi-heavy run -- .venv/bin/python -m pytest -q \
  tests/unit/test_jobstore_production_mirror_admission.py tests/unit/test_staging_fence.py
```

These tests measure the pure admission contract, live environment rereads and
unchanged staging isolation. They do not exercise production copying, backfill,
retirement, running artifacts or the live data plane. No GCP tier was used.
