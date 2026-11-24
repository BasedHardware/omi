# Monthly usage totals

`hourly_usage` remains the source of usage and plan/shadow accounting. A small
`users/{uid}/monthly_usage_totals/{YYYY-MM}` document stores the five root usage
metrics, monthly sums and at most 31 daily subtotals. It contains no content or
credentials. Account erasure already enumerates the complete user subtree.

Every live usage write maintains these sums in the **same transaction** as
the hourly write. Sync once keys and partial-completion receipts govern both
writes; replay does not add a second charge. Ordinary live updates retain their
existing additive behavior. Maintenance adds one write per usage commit.
Ordinary/once/absolute/admin/migration writers also read the existing account
deletion marker, destructive gate and user root in that transaction, before any
receipt or source writes. Previously unfenced commits add three point reads
(once-key replays also check authority); rejected commits do not stamp receipts.
User-facing callers publish through `utils.analytics.record_usage`. If the
fence refuses publication, this helper lets the conversation/transcript/audio
pipeline complete while skipping the entire accounting transaction (including
the once receipt). `omi_fallback_total{component="usage_publication",
from_mode="publish",to_mode="skip",outcome="degraded"}` and its matching bounded log
separate `usage_root_missing` from `usage_fence_blocked`. No UID or content is
included. This includes roots absent before sync admission and roots removed
immediately before publication. Other database failures retain existing retry
semantics. Direct admin/migration writers still raise on refusal. Outside usage
publication, this PR adds no existing-root requirement to a user path: cold
reader rebuilds already return to the hourly query if the root is absent.

Existing projection sessions already read deletion/root/privacy authority in
their transaction, so their added monthly write reuses those checks. No
authority is cached across attempts. Maintenance remains on while the reader
is off. No entitlement or reservation
calculation changes, including Free; no authority checks are cached or removed.

Historical absolute overwrites, operator transcription resets, and historical
usage deletion invalidate `ready` in the same commit as their hourly mutation.
The next enabled read rebuilds from the existing year/month source query. This
transaction reads the monthly document before scanning and replaces its entire
baseline. Every concurrent writer touches that monthly document, so a cold seed,
reset, duplicate receipt, retry or backdated increment cannot silently lose or
double-apply a contribution. There is no periodic scan or background backfill.
An empty month is also a valid baseline. Because initialization materializes
derived user data, it takes the existing transactional `external_write_fence`
and requires an existing user root. Deletion/destructive-operation authorities
are read before the monthly counter and source query, so deletion cannot
inventory the subtree before the new counter lands. A blocked initialization
retains the old read path. Initialization adds five point reads to the old source
scan (outer total, transaction authorities/user/total); warm reads use one
document regardless of hour count.

Since-date reads retain the existing UTC **day** cutoff (even if the supplied
date includes hours/minutes). A prior-month cutoff includes the entire month;
a later-month cutoff returns zero. Seeding validates canonical stored IDs and
document names. Missing/mismatched/noncanonical legacy IDs, malformed counters,
or read/transaction failures use the original hourly query. No legacy rows are
omitted to populate a total. Current-hour and late/backdated source writes update
the same day and month atomically. Existing Redis caching and invalidation remain
independent of the durable total; Redis failure cannot turn a cache into authority.

## Reader rollout and rollback

`FIRESTORE_READ_LEVERS.usage_month_total` gates readers only. It originally
shipped at **0** because an old instance can write hourly usage without
maintaining totals. A mixed-writer rollout would undercount paid/Free allowance.
This accounting risk requires writer qualification before adding reader scope.

Source declaration at preparation of the usage-month qualification PR (not live attestation):

| Reader surface | Enable percent | `FSR_USAGE_MONTH_TOTAL_EPOCH` |
| --- | --- | --- |
| Prod Cloud Run backend, backend-sync-backfill, backend-integration | 0 (intentional WQ31 exclusions retained) | `c2fs_20261026_r1` (inactive) |
| Prod Cloud Run backend-sync | 100 (sync-only restoration, `3eaf4ccf`) | `c2fs_20261026_r1` |
| Base, listen/pusher in both environments, jobs, desktop backend, all dev services | 0 | `v1` (inactive) |

The October 24 initial rollout schedule is superseded by this scope and sequence.
The four Cloud Run declarations preserve the existing reader scope; this is a
source contract, not fresh attestation of serving writer coverage. Other readers
stay off and cannot seed/restamp totals. Do not enable a `v1` reader against the
shared production totals. See [the runtime train](../deploy/runtime_env/README.md)
for the complete replacement-literal policy and the independent people ramp.

The Infra Rollout Coordinator owns the next qualification and expansion:

1. Ship #23797's config in **listen → pusher → Cloud Run** order only after
   the 10-27 batch entry/soak (~11:30Z) and lead admission. Verify each actual
   serving artifact and complete literal/epoch before advancing. Preserve the
   monthly reader split throughout; people starts at 5 independently.
2. Before any additional monthly reader, attest the writer contract on **every**
   source writer: listen, pusher, backend, sync, backfill, integration, desktop
   backend Python helpers and operator/migration tooling. Verify actual serving
   artifacts, traffic and drained old revisions/jobs. Cached totals must never
   be initialized against mixed-version writers. By **2026-10-28 12:00Z**,
   either establish this gate or record the blocker and leave new readers off.
3. Align qualified new readers to the existing production epoch
   **`c2fs_20261026_r1` while still at 0**, then enable 5. Default `v1` is not an
   approved production reader epoch. If old writers have run since initialization,
   keep all affected readers off, requalify all writers, and select a **new common
   epoch** before enabling any scope instead of reusing potentially stale totals.
4. Run synthetic/loopback equivalence on that artifact: require zero mismatches,
   no accounting/Free allowance, 5xx or live-p95 regression, and no contention
   errors for **two hours**; watch origin series and fallback rate. Only then may
   the lead expand the qualified scope to 100, targeted by **2026-10-29 12:00Z**.
   A failed gate is a blocker, not authorization to expand at the deadline.
5. Measure matched full-day windows against 10-24/25 and confirm **D+1 billing**,
   including added writes, initialization reads and fallbacks in net economics.

Kill switch: set `usage_month_total:0` (preserve every other lever). This restores
hourly reads and leaves maintenance on. If any old-writer code ran after a total
was initialized, keep readers off until all writers are upgraded **and change
the epoch before re-enabling**. A new epoch forces a transactional rebuild on
first use; simply toggling the lever back on is unsafe after an old-writer
rollback. Malformed/empty epoch values disable total reads.

## Offline qualification and pending expansion

`python backend/scripts/qualify_usage_month.py [--evidence receipt.json]` reports
`usage_month_cache` and `usage_month_total` qualification separately for backend,
backend-integration and backend-sync-backfill. Exit 1 means at least one blocker;
without evidence all six results are blocked. It reads local files only. A report
never changes configuration or authorizes activation: **lead2 must rule**.

The input is an operator attestation with links to the owning records. It must be
refreshed against actual serving artifacts/traffic; this checker validates the
declared gates, not the authenticity of external records. Do not treat local
unit tests or this PR as writer qualification or live health evidence.

JSON input fields (missing evidence fails closed):

- `common_epoch`: the qualified production epoch, never `v1`.
  `old_writers_since_initialization`: explicitly false only when established.
  If true or unknown, `previous_epoch` must name the old epoch and differ from
  the new common epoch. Requalify every writer and align readers at 0 before use.
  The pending patch preserves the existing epoch; it cannot perform this repair.
- `writers`: entries for `listen`, `pusher`, `backend`, `sync`, `backfill`,
  `integration`, `desktop`, `operator`, `migration`. Each names `artifact`, `ref`,
  `started_at`, `ended_at`, `valid_until` (timezone-aware ISO timestamps),
  `old_revisions_jobs_drained: true`, and the relevant contract:
  `maintains_totals: true` for total, `invalidates_cache: true` for cache. Writer
  qualification/drain observations must end before the soak begins.
- `services`: an entry for each target service plus the already-enabled
  `backend-sync` reader. Attest its serving identity, traffic and observation
  window, and confirm its epoch matches `common_epoch`; it needs no new-reader
  soak. Each service names `artifact`, `source_sha`
  (full Git SHA), `ref` (serving traffic receipt), `traffic_verified: true`, the
  same observation-window fields and `epoch`. Each target service also needs
  `cache_freshness_accepted: true` only after its admission scope accepts the
  existing 60-second TTL.
- Each target service's `soak` names that same `artifact`, `ref`, and observation-window
  fields covering at least two hours of synthetic/loopback equivalence, entirely
  within the verified serving-traffic window. Explicit
  integer zeros are required for `mismatches`, `accounting_regressions`,
  `free_allowance_regressions`, `http_5xx_regressions`, `live_p95_regressions`,
  `contention_errors`; `origins_reviewed` and `fallback_rate_reviewed` must be true.
- Each target service's `equivalence.cache` and `equivalence.total` names `source_sha`
  matching the serving source, `ref` to the test receipt, and `junit` (a path or
  list of paths relative to this JSON file). Use the existing suites below,
  from that source/artifact;
  the checker requires their existing equivalence test families and rejects
  reports containing skips, failures or errors. It adds no usage comparator.

Existing proof commands, run from the product root through the workspace's
`bin/omi-heavy run --` (JUnit artifacts are local, never committed):

```sh
backend/.venv/bin/python -m pytest backend/tests/unit/test_fsr_s4_caches.py --junitxml=/path/to/cache.xml
backend/.venv/bin/python -m pytest backend/tests/unit/test_monthly_usage_totals.py --junitxml=/path/to/total.xml
# Loopback Firestore emulator required; absent emulator must not count as PASS.
backend/.venv/bin/python -m pytest backend/tests/integration/test_monthly_usage_totals_firestore.py --junitxml=/path/to/transactional.xml
```

Use a separate pytest process for each file, per the backend test contract.
For `cache`, supply `"junit": "cache.xml"`; for `total`, supply
`"junit": ["total.xml", "transactional.xml"]`. The checker aggregates only their
existing results; it does not rerun usage arithmetic. This is source equivalence
evidence, separate from the service's two-hour soak receipt. Do not fabricate a
PASS report to fill an unavailable proof.

The single unapplied config change is
`backend/deploy/runtime_env/pending/usage-month-enable-5.patch`. It changes only
`usage_month_cache` and `usage_month_total` from 0 to **5** in the three production
Cloud Run service literals, preserving every other lever and epoch and leaving
backend-sync at 100/100. It is outside the composer's input files. After lead2's
ruling and qualification, the lead may apply it and regenerate the manifest:

```sh
git apply --check backend/deploy/runtime_env/pending/usage-month-enable-5.patch
git apply backend/deploy/runtime_env/pending/usage-month-enable-5.patch
python backend/deploy/compose_runtime_env.py
```

Re-review against current main if the patch no longer applies. Activation is a
separate reviewed config commit and release; neither is performed by this PR.
The runbook's clean two-hour gate precedes any lead expansion from 5 to 100.
Rollback changes only these six percentages back to 0 and recomposes, preserving
epochs, backend-sync, and all other levers. No savings are claimed by qualification.

## Attribution and expected economics

Existing billed-read counters carry constant origins:
`job:usage_month_total_read`, `job:usage_month_total_rebuild`, and
`job:usage_month_total_fallback`. Track them **together**, along with the original
monthly-stat callers; a moved caller is not a saving. Fallbacks also record
`omi_fallback_total{component="firestore_read",from_mode="monthly_total",
to_mode="hourly_query",reason="unavailable"}`.

The sprint report's latest-hour pool was 43.84M/day and its conditional target
was 40M/day. Those are a modeled budget, not measured savings from this change.
The separate funded `read_month` closed-bucket session and plan/shadow readers
remain on their existing paths; do not claim their disappearance. Replacement
cost is one small write per accounting commit, three authority reads per
previously unfenced commit attempt, a once-per-active-month seed, and another
seed after explicit correction/epoch changes. If W is the daily count of those
commit/replay attempts, subtract 3W from the modeled reader reduction, plus
seed scans, point reads and fallbacks; account separately for added writes.
Measure the original writer caller origins as well as all three reader origins.
For example, 1M such attempts/day adds 3M reads/day; the modeled 40M/day gross
reader reduction would then be at most 37M/day before seeds/fallbacks/retries.
Neither W nor the net saving is measured yet. Measure actual rates and
contention before considering shards or booking savings.
