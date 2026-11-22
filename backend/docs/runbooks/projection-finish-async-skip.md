# Async receipts and the projection finish sweep

SCA-2280 removes repeated finish-sweep reads of async-policy receipts. This is
option 2 from the issue, using the existing finish clock as a durable ownership
hint rather than adding a new indexed policy field. Follow-up discovery remains
independent of finish clocks (the scheduling safety required by option 3).

The pinned projection policy on a job is authoritative. A session with that
policy writes `projection_finish_due_at = -1` when it persists or acknowledges
an async receipt. Synchronous receipts retain their current clock and backoff.
Historical async receipts are read and classified once: a transaction rereads
both pinned policy and result state before changing only the clock. It never
changes payload, receipt, privacy, custody, ordering, usage or client state.
Recovery writers that cannot classify a receipt continue to stamp it due now;
that receipt remains eligible for bounded classification on later finish passes.

After the existing version-1 finish-clock backfill marker is complete, the finish
page adds `projection_finish_due_at >= 0` to its existing clock query. With
finish backoff off, the upper bound is positive infinity (all sync clocks);
with it on, the upper bound stays the current time. Before the marker, the
legacy unfiltered page stays active so unstamped sync obligations remain visible.
Moving to the clock ordering even when backoff is off is intentional. It
relies on the stamping marker: the cost lead reported it complete with zero
missing clocks at 12:46Z on November 14. Before that marker, ordering stays
legacy. There is no new maintenance pass or production action in this PR.

Each finish sweep also probes persisted/ready receipts with a clock at or below
`-1`, using `limit=1` and the same existing index. A result keeps
`has_async_followups` true even when all async receipts are excluded from the
finish page. Sync-only rows cannot wake extra follow-up discovery. Positive-clock
async rows from older writers remain on the ordinary finish page; seeing one
keeps the drain scheduled and transactionally classifies it. No extra fallback
page or per-job scan runs for synchronous-only work. Follow-up discovery is
independent of the finish clock. Main's separately admitted follow-up-clock
rollout stamps `projection_followup_due_at` alongside the negative finish hint
and can use that independent clock after its own writer/backfill marker is
complete. Until then it keeps unfiltered discovery. Neither query mode filters
negative finish hints from follow-up work. Finish and follow-up clocks cannot
share a cursor; switching modes resets it. Under the infinite finish ceiling,
stripe seeds remain finite by clamping their seed horizon to wall time.
Claims, privacy fences, readiness, retries and completion transactions retain
their contracts; this composition does not authorize follow-up-clock rollout.

`BATCH_PROJECTION_FINISH_ASYNC_SKIP_ENABLED` defaults on. Set it to `false` to
remove the lower bound and restore the former finish discovery, preserving the
separate finish-backoff switch. Negative clocks are already due under that
query, so rollback requires no data repair. Older binaries also see them as due.
Mixed fleets may write an ordinary clock again on a state change; newer sweep
readers reclassify it safely. No new clock delays transcript assignment or async
follow-up execution.

## Ready-state writer coverage (SCA-2280 follow-up)

The November 16 production verification found 569,250 finish rows read in the
04:00-05:00Z hour versus the corrected 502,606/hour baseline. Positive-clock
stock fell by only about 3.5-4k/hour while classification retired about 21k/hour;
60 sampled positive-clock jobs all had async policy. These observations do not
prove which writer accounts for all replenishment.

Held-ready settlement, durable sibling completion, privacy resume and ghost
settlement previously stamped positive finish clocks even for pinned async jobs.
These paths now pass the pinned policy to the existing clock primitive.
Sibling transitions use each sibling's policy from the job already read in the
transaction, rather than inheriting the initiating segment's policy. Missing
policies remain positive for later classification. Whole-document privacy
resume now accepts the same async hint as patch writes. Both forms continue to
stamp the independent follow-up clock due now; no receipt or effect is skipped.

This correction adds no document reads, write operations, index, marker, rollout
setting or classification budget. It prevents replenishment from these known
writers; existing positive-clock rows still require bounded classification.
After a source-containing ordinary release, measure net positive-clock drain
against classification throughput, then a full hour of finish reads below the
502,606 baseline. The 14,400/hour example below is an empty-page asymptote, not a
production result or an immediate target. Keep savings unbooked until the cost
owner reads both caller counters and Quality supplies matched p50/p90.

## Bounded classification and progress

`BATCH_PROJECTION_FINISH_CLASSIFY_PAGE_LIMIT` defaults to **8 attempts per page**;
0 pauses classification, 1-16 are accepted, and malformed/out-of-range values
keep 8. Pages on different executor threads have separate caps but share a
locked process budget. That budget refills only 20 seconds after its last
attempt finishes; in-flight transactions prevent a refill. There is no sleep,
new queue or delay imposed on transcript/follow-up delivery by the limiter.
Failures consume budget, increment a dedicated counter, and leave the row
eligible without incrementing the sweep's generic error count or deferring it.
A state/policy race returning false is neither a success nor a failure.

At the reported approximately 42 processes, eight per process permits at most
**336 classification writes in a synchronized one-second burst**, and at most
**16.8 writes/s averaged over the cooldown**. These are incremental
classification bounds only. Ordinary result writes are additional; their
combined peak has not been measured here, so this does not establish headroom
under the 500 writes/s index limit or cap all result writers.
The nominal 518k-row pass is at least **8.6 hours** at that maximum successful
rate (9.0 hours at 40 processes). Overlap, failures, slower sweep cadence and
other work make it longer; new async session writes avoid migration entirely.
Expect gradual read reduction during that window rather than an immediate cut.
The cost lead may raise the setting by environment only after the first hour
of production readings if classification failures remain zero. Before raising
it, include ordinary writes and fleet size in the total peak write budget;
recalculate `processes × limit`. Do not raise it to meet a train deadline.

Read `omi_batch_projection_finish_classified_total` for acknowledged successful
clock updates and `omi_batch_projection_finish_classification_failures_total`
for exceptions, including contention. Both have no labels and survive the
sync GMP keep rule; both scrape tests pin their sample names. A lost commit
reply can undercount successful writes and increment failures, so compare these
with remaining work and the Firestore/caller counters rather than treating
process-local counters as a complete durable census.

## Index and delivery risk

The unchanged ascending result index is `projection_state`,
`projection_finish_due_at`, `committed_at`, `__name__`, on both
`batch_pipeline_prod_results` and `batch_pipeline_dev_results`. The lower bound
uses the same indexed range field. No index deployment is required. The issue's
17:11Z production backoff rollout and completed stamping marker report that this
index is already serving on backend-integration; this PR makes no fresh
production access or independent fleet-wide readiness claim.

Risk is bounded to discovery hints and a one-time classification write. Ship on
the next ordinary train after review; use Train 2 only if its captain accepts
the verification evidence. Check follow-up completions and upload-to-transcript
p50/p90 against 92 s / 455 s, along with finish row reads and both caller read
counters. The code adds no async wait and changes no projection effects, but
local tests cannot establish production latency or dollar savings.

## Read estimate

The observed baseline is about 800,000 full finish-row reads/hour, with roughly
6M reads/hour attributed to the two projection callers for this loop. An
async-only, classified finish page now performs zero full row reads: one
one-row async-clock query plus an empty bounded clock query per sweep, and at most
one marker read per process until it observes completion. For N sweep calls/hour,
budget about 2N document reads (plus bounded initial stripe queries), independent
of async backlog size. Existing follow-up discovery/processing reads remain.

For example, 40 processes sweeping every 20 seconds gives N=7,200 and about
14,400 finish-discovery reads/hour, versus at least 2.4M baseline reads/hour
(800k result-page documents plus at least two fetches per full read), before
policy/privacy amplification. The reported 6M/hour is the potential affected
pool, not a proven saving from this PR. The production owner must separate
unchanged follow-up reads from eliminated finish reads.

For the approximately 518k historical rows, a nominal single classification
pass adds about 1.036M transaction document reads and 518k clock-only writes,
in addition to ordinary discovery/reads while rows await classification. Concurrent discoveries,
transaction retries and later state transitions can add reads or reclassification;
an already-classified row is never rewritten merely because another replica
discovers it. Unclassified rows remain on ordinary pages until admitted by the
budget; follow-up delivery does not wait for classification. New async session writes need no classification read or extra write. Completion and reclassification races are transactionally
fenced; a failed classification remains eligible and retries.
