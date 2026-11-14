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
that receipt is safely classified on its next finish pass.

After the existing version-1 finish-clock backfill marker is complete, the finish
page adds `projection_finish_due_at >= 0` to its existing clock query. With
finish backoff off, the upper bound is positive infinity (all sync clocks);
with it on, the upper bound stays the current time. Before the marker, the
legacy unfiltered page stays active so unstamped sync obligations remain visible.
There is no new maintenance pass or production action in this PR.

Each finish sweep also probes persisted/ready receipts with a clock at or below
`-1`, using `limit=1` and the same existing index. A result keeps
`has_async_followups` true even when all async receipts are excluded from the
finish page. Sync-only rows cannot wake extra follow-up discovery. Positive-clock
async rows from older writers remain on the ordinary finish page; seeing one
keeps the drain scheduled and transactionally classifies it. No extra fallback
page or per-job scan runs for synchronous-only work. The follow-up drain keeps
its existing unfiltered discovery, claims, privacy fences, readiness, retries
and completion transactions.

`BATCH_PROJECTION_FINISH_ASYNC_SKIP_ENABLED` defaults on. Set it to `false` to
remove the lower bound and restore the former finish discovery, preserving the
separate finish-backoff switch. Negative clocks are already due under that
query, so rollback requires no data repair. Older binaries also see them as due.
Mixed fleets may write an ordinary clock again on a state change; newer sweep
readers reclassify it safely. No new clock delays transcript assignment or async
follow-up execution.

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
in addition to one final legacy page/read pass. Concurrent discoveries,
transaction retries and later state transitions can add reads or reclassification;
an already-classified row is never rewritten merely because another replica
discovers it. New async session writes need no classification read or extra write. Completion and reclassification races are transactionally
fenced; a failed classification remains eligible and retries.
