# Production jobstore mirror: source contract and release prerequisites

Status: **activation requires the release packet below**. Explicit production
configuration constructs a lazy handle; owner resolution and live cohort policy
are enforced on every freshly reread document before any production upsert.
This document establishes no deployment, retained production copy, live parity,
serving acceptance or savings. No production data or credentials were read for
this preparation.

The source is maintained in `BasedHardware/omi`, branch
`lane/jobstore-index-mode`, with the exact reviewed candidate pinned in the PR. The later
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
the production configuration. It is only a pure configuration check.
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

The two production configuration keys are `JOBSTORE_PRODUCTION_MIRROR` (default `off`)
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

## Enforced copy policy

`jobstore_mirror_factory_admits` may construct a lazy handle for an explicitly
configured production target. It does not admit a document. Every live write,
claim refresh, outside-transaction refresh and operator backfill goes through
`DualStore.copy_current`: shared namespace purge barrier, sorted per-key locks,
then a fresh authoritative read and `cohort.project_document`.

| Tables | Owner resolution / production policy |
| --- | --- |
| jobs, results, intakes, artifacts | Current `owner_id` hash and/or canonical `owner_key`; present claims must agree |
| owners, merge_holds, allowance_holds | Canonical document key plus every explicit owner claim must agree |
| queues | `<priority>_<owner_key>`, priority 0..2; explicit owner/priority fields must agree |
| control, gpus, pull_claims | Shared/global rows are excluded entirely |

Unknown/malformed/conflicting ownership cannot authorize an upsert. Every copy
rereads the live sample and write kill. Missing primary documents, excluded
owners, killed cohorts and unknown owners retire a retained copy under the same
locks. No owner decision is cached in a queued work item. Firestore retains all
transactions, claims, privacy and paid-routing authority. `repair_lineage` and
`gpus.segment_id` remain omitted from every copy.

Captured transaction pre-images are filtered before queueing. Read comparisons,
convergence and diagnostics reapply the live cohort; intentionally excluded rows
do not become whole-population divergences. Production discovery observations
support only `due` leased/retry/result_ready. Other methods return UNKNOWN.

`cohort_due_parity` proves a bounded selected prefix: selected rows from the
primary's existing due prefix must appear in the PG hints, in order; every PG
hint must equal its freshly read, selected primary document and remain due.
Valid selected hints beyond the global primary prefix are permitted. Two stable
observations must agree within one warm-connection SQL/socket/RPC deadline.
No selected traffic is UNKNOWN. The metric's query labels are `due_leased`,
`due_retry`, `due_result_ready`, so traffic cannot be conflated across states.
This proof does not establish complete backlog coverage. Existing Firestore
safety reads and rotating census remain necessary.

## Bounded backfill and copy retirement

`python -m database.jobstore reconcile-page` runs one bounded primary-source
backfill page or copy-source retirement page. The old `backfill` command remains
staging-only; its unbounded key-set census is never a production shortcut.

The operator supplies explicit row, primary-document-read, SQL-statement and
wall-time budgets. Key-ordered pages never allocate whole-table sets. A copy
page revisits existing rows even when their last expiry-stamping refresh was
dropped. Each key is freshly reread under the existing copy/purge locks.

The retirement engine **never deletes from a clock or lease deadline**. A
present document, including a legal hold, removed/extended expiry, unknown clock
or legacy shape, follows its current primary and cohort policy. Only primary
absence or exclusion retires a copy. Firestore's existing retention/hold rules
therefore remain authoritative; no new TTL or deletion rule is introduced.
No Firestore document is mutated by these commands.

The one-page transaction uses a warm-only pool, SQL/lock and transport deadlines.
Cold IAM auth/connection startup is a separate phase; the supervising operator
job must impose a hard whole-process deadline as well. Failure rolls back the
page and does not advance its checkpoint. Successful retries are idempotent.
An end-of-pass observation while writers are active is not a snapshot or proof
of complete coverage; the release owner schedules repeated rotations.

Checkpoint files are private operator state, bound to target, namespace, source,
table and apply/dry-run mode. Their opaque base64 cursors are not encryption;
never publish them. Counts-only reports omit cursor, target, payloads and keys.
Use separate state files for each source/table/mode. Atomic replacement advances
only after PG commit. Keep operator state/writers outside sweepable worktrees.

Example template (budgets shown are command arguments, not approved production
operating thresholds):

```bash
python -m database.jobstore reconcile-page batch_pipeline_prod \
  --source copy --table jobs --apply \
  --state-file /approved/private/state/jobs-copy.json \
  --max-rows <rows> --max-primary-reads <reads> \
  --max-statements <statements> --page-seconds <seconds>
```

Production primary-source backfill requires complete production-mirror
configuration. Copy-source retirement requires exact production data-plane
context and the complete retained target, independently of mirror mode, sample,
namespace allowlist and write kills. Turning mirroring off does not erase copies
or turn off retirement. Keep every deletion executor's target/reachability until
all retained obligations have retired.

Before copying real rows, the release owner must configure the supervised
rotation, maximum accepted retirement lag, per-pass budgets and failure alert,
and measure a complete rotation within that bound. Confirm the target's backup
retention against the owning deletion contract. Source tests do not establish
those operating conditions or permit production copying without them.

The environment-selected copy handles share process-owned pools across all
namespaces and cold erasure calls: two normal sessions for mirror/parity/index
work, plus one session reserved for synchronous erasure. Saturating the normal
pool cannot consume the erasure slot. Cold calls borrow these pools rather than
creating and closing one per invocation; errors still propagate for durable
retry. A different PG host/database/principal requires a process restart rather
than creating another allowance. These are per-process source ceilings, not a
fleet cap or approved operating budget. Count every target-enabled process and
maximum replica, including deletion executors, before accepting a fleet bound.

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
   Verify the integrated copy, cohort and reconciliation tests above. There is no time-only soak gate.
2. Through the release executor, verify the intended `based-hardware`
   `prod-jobs` instance, database name, private host and runtime IAM database
   user from current control-plane evidence. Start it only when source is
   ready to deploy, under David's recorded startup ruling. Do not infer the
   database name or privileges from this source document. IAM or credentials
   changes require their own specific approval.
3. Before any separately approved schema action, record the exact released
   build's contiguous migration version/name/checksum vector and compare it
   with the intended target. Do not run `migrate` as a readiness probe or
   repeat completed initialization. The frozen operator source `97074e78`
   expects `0001_doc_mode_store.sql` through `0008_allowance_holds.sql`.
   For a fresh target, the release executor must first complete a separately
   approved schema-initialization action using the pinned build's migration
   command and retain its apply/status receipt; readiness cannot initialize it.
   If initialization is already complete, verify that receipt and the current
   catalog instead of applying it again. Never use this sequence to authorize
   another startup, IAM change or schema application implicitly.
   This source tree additionally contains expand-only `0009_protected_share.sql`
   for a separately reviewed PostgreSQL-primary worker roll; its presence is
   not permission to apply it during operator readiness. No fence,
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
