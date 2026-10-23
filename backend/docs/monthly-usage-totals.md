# Monthly usage totals

`hourly_usage` remains the source of usage and plan/shadow accounting. A small
`users/{uid}/monthly_usage_totals/{YYYY-MM}` document stores the five root usage
metrics, monthly sums and at most 31 daily subtotals. It contains no content or
credentials. Account erasure already enumerates the complete user subtree.

Every live usage write maintains these sums in the **same batch/transaction** as
the hourly write. Sync once keys and partial-completion receipts govern both
writes; replay does not add a second charge. Ordinary live updates retain their
existing additive behavior. Maintenance adds one write and zero reads per usage
commit. It remains on while the reader is off. No entitlement or reservation
calculation changes, including Free; no authority checks are cached or removed.

Historical absolute overwrites, operator transcription resets, and historical
usage deletion invalidate `ready` in the same commit as their hourly mutation.
The next enabled read rebuilds from the existing year/month source query. This
transaction reads the monthly document before scanning and replaces its entire
baseline. Every concurrent writer touches that monthly document, so a cold seed,
reset, duplicate receipt, retry or backdated increment cannot silently lose or
double-apply a contribution. There is no periodic scan or background backfill.
An empty month is also a valid baseline. The initialization scan is the old read
plus two document lookups; warm reads use one document regardless of hour count.

Since-date reads retain the existing UTC **day** cutoff (even if the supplied
date includes hours/minutes). A prior-month cutoff includes the entire month;
a later-month cutoff returns zero. Seeding validates canonical stored IDs and
document names. Missing/mismatched/noncanonical legacy IDs, malformed counters,
or read/transaction failures use the original hourly query. No legacy rows are
omitted to populate a total. Current-hour and late/backdated source writes update
the same day and month atomically. Existing Redis caching and invalidation remain
independent of the durable total; Redis failure cannot turn a cache into authority.

## Reader rollout and rollback

`FIRESTORE_READ_LEVERS.usage_month_total` gates readers only. It is initially **0**
because an old instance can write hourly usage without maintaining totals. A
mixed-writer rollout would undercount paid/Free allowance. This accounting risk
is why the reader has a ramp instead of shipping immediately at 100%.

The rollout lead and reads loop own this sequence:

1. T2 (2026-10-23): deploy this writer contract to **every** source writer:
   listen, pusher, backend, sync, backfill, integration, desktop backend Python
   helpers and operator/migration tooling. Verify the actual serving artifacts,
   traffic and drained old revisions/jobs before enabling any reader. Cached
   totals must not be initialized against mixed-version writers.
2. Choose one `FSR_USAGE_MONTH_TOTAL_EPOCH` on all reader services (default `v1`).
   Enable `usage_month_total:5` after the writer gate; run the loopback/synthetic
   equivalence scenarios on that artifact, require zero mismatches, no 5xx or
   p95 regression and no contention errors for two hours. Check the new origin
   series and fallback rate. Full rollout is due by T3, **2026-10-24 08:00Z**;
   the lead reports a blocker if writer coverage or the gate delays it.
3. The reads loop expands to 100%, measures matched full-day windows and D+2
   billing, and includes added writes/initialization reads in net economics.

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
cost is one small write per accounting commit, a once-per-active-month seed,
and another seed after explicit correction/epoch changes. Measure actual write
rate and contention before considering shards or booking savings.
