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

Current source declaration for the **2026-10-27 #23797 train**:

| Reader surface | Enable percent | `FSR_USAGE_MONTH_TOTAL_EPOCH` |
| --- | --- | --- |
| Prod Cloud Run backend, backend-sync, backend-sync-backfill, backend-integration | 100 | `c2fs_20261026_r1` |
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
