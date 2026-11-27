# First-week summary guarantee

SCA-4790. When enabled, a conversation created by a new paid subscription
inside the first `FIRST_WEEK_SUMMARY_DEADLINE_HOURS` (default `168` = 7 days,
`0` disables) keeps its first-summary obligation open until that stored window
ends. It is not closed by the 72 h historical age gate, by the repair scan's
72 h bound, or by the 30-minute fresh-lane demotion.

The window is a stored record, not a wall-clock rule. At intake the conversation
gets

```
first_week_summary = {policy_id, paid_since, window_end_at, interval}
first_week_outcome = null        # the close-out counting key
```

`paid_since` is the commercial first-paid epoch stored at the user document's
top level beside `subscription`, set once on a confirmed free-to-paid transition
and never moved by a renewal. It comes from the provider's paid-period start,
not webhook processing time. Stripe trials and prepaid subscriptions do not set
it; Stripe trial conversion uses the paid-period start. An active entitlement
projection without provider payment evidence does not set it. Play trial
eligibility remains a pre-activation gate until paid-period evidence is covered;
keep the production flag off for every workload during that review. A row that
predates `paid_since` has no epoch and is never covered. Production has no
preactivation backfill, so
the first-week conversation cohort begins when the runtime flag is enabled;
existing paid users without `paid_since` remain outside it. `interval` is
`monthly`/`yearly`/`unknown` from the paid period length. Referral promotions
never stamp a window; the read is the commercial subscription.

## Keys

| Key | Default | Meaning |
| --- | --- | --- |
| `FIRST_WEEK_SUMMARY_GUARANTEE_ENABLED` | off | Explicit opt-in for the deadline, lane and counter |
| `FIRST_WEEK_SUMMARY_DEADLINE_HOURS` | `168` | Stored window length; `0` disables stamping |
| `ENRICHMENT_FIRST_WEEK_TASKS_QUEUE` | `enrichment-first-week` | Reserved lane; empty falls back to `enrichment-fresh` |

Readers: `config/summary_guarantee.py` (window and stamp),
`utils/conversations/summary_delivery.py` (stamp, deadline, projection age gate),
`utils/enrichment/outbox.py` (row copy, deadline, dispatch, sweep promotion),
`utils/enrichment/age_gate.py`, `utils/enrichment/fresh_demotion.py`,
`services/first_week_summary_closeout.py`.

## Lane capacity

`enrichment-first-week` is additional capacity (prod 4 concurrent / 2 per
second, `backend/deploy/ops/prod.yaml`), not a re-partition: `enrichment-fresh`
(30/10) and the primary queue (300/25) keep every slot. The queue must exist
before activation; `staging-enrichment-first-week` mirrors 4/2. With the queue
key empty, first-week rows bind to `enrichment-fresh` exactly as today and the
demotion skip is what protects them for the rest of the window.

## Counter and readback

`omi_first_week_summary_outcome_total{outcome,interval}` counts each stamped
conversation once, at its window close, from the 2-minute `first_week_summary_closeout`
phase on backend-integration. It has its own lease, scan budget and query, so a
slow or unindexed page fails only this phase and never the repair phases.

The first-week stamp preserves the existing 60–120 second first-summary dispatch
and repair deadline. It changes age-gate and lane-demotion eligibility only;
historical processing rows are excluded. A continuous capture therefore keeps
its ordinary first-summary dispatch while its first-week obligation remains open.
The close-out pass processes at most 25 rows and stops starting work after 15 s.
Its budget is 410 reads/tick at the retry bound: up to 25 query-row reads,
10 lease reads across claim/release, and 375 outcome-transaction reads (25 rows
times three documents—conversation, outbox and aggregate count—times five
transaction attempts). At 720 ticks/day that is 295,200 reads/day, plus at most
9 reads for one bounded durable-count readback/day.

Each outcome transaction also increments one of the bounded durable aggregate
documents under `maintenance/first_week_summary_outcomes/counts`, keyed by
`{interval}_{outcome}`. The conversation outcome stamp and aggregate increment
commit atomically. Use these durable counts for the production readback; the
Prometheus counter is the live operational signal and can miss the final update
if a process exits after the Firestore transaction.

- `summarized`: a usable summary was durable by the window end.
- `attempt_failed`: an admitted generation attempt produced no usable summary
  (for example, the empty-output budget was exhausted).
- `no_attempt`: none at the window end.

`blocked_byok` is `no_attempt`: no generation attempt was admitted. Attempt
failure classification uses the durable `first_week_attempts` and
`first_week_last_class` receipts written with the consumer's lease outcome,
not inferred from the summary-empty counter.

A summary that lands after the close is not counted retroactively. The counter
documents are the mechanism number; `infra/metrics/churn/first_month.py` remains
the acceptance number. Read at least 14 days after activation (the first
complete post-activation cohort closes between +7d and +14d), and name the
activation-bounded cohort.

## Read and generation budget before activation

The code default, production overlay, and `batch-pipeline-worker` chart keep
`FIRST_WEEK_SUMMARY_GUARANTEE_ENABLED=false` until the approved read-only census
records the eligible workload. The chart binds the flag off on the GPU
deployment and its record-seal worker, sweeper, and repair jobs. While disabled, the added
production reads and summary attempts are zero. Before enabling, record the
census-backed expected extra summaries/day and reads/day, including:

- one conversation scheduling-metadata read per first-week-enabled outbox mark
  (`finished_at`, `created_at`, `started_at`, the processing tier, and the stored window);
- at most one `created_at` point read per inspected due row in each enrichment
  sweep, capped by its 100-row scan limit. Rows whose pending clock already
  proves age and rows with an open first-week window use no conversation read;
- at most one conversation scheduling-metadata read when a producer creates a
  new first-summary outbox row without a copied stamp. Existing rows and payloads
  that carry the stored stamp use no such read;
- one `sync_reprocess_outbox` point read for each first-week window closed, to
  copy its durable attempt receipt into the closeout classification transaction;
- closeout worst case is 410 reads/tick, or 295,209 reads/day including the
  bounded post-cohort readback; the same per-row transaction reads the
  conversation and durable aggregate count as well as the outbox row;
- the commercial subscription read when an existing conversation stamp is
  absent: at most one Firestore user read per cache miss, with same-user reads
  shared for up to 60 seconds when the subscription cache is available (a cold
  or unavailable cache can make this one read per eligible mark);
- one existing-user read for each campaign-off subscription update while the
  feature is enabled, to distinguish a first paid transition from a renewal;
  this read is skipped while the production flag is false, and the campaign-on
  writer already reads the user in its transaction;
- the census-derived eligible conversation count and forced-attempt split owned
  by the separate child issue.

If the estimate exceeds 10M additional Firestore reads/day, stop for the margin
owner. Do not turn the production flag on until the numeric estimate and the
owner's activation decision are recorded. Verify the `enrichment-first-week`
queue and `first_week_summary_closeout` collection-group index are deployed on
the target service before the runtime flag is enabled; the source declarations
are not production-readiness evidence.

## Rollback

Set `FIRST_WEEK_SUMMARY_GUARANTEE_ENABLED=false`. Intake stops stamping and every
reader ignores an existing stamp, restoring the 60/120 s deadline, the 30-minute
demotion and the 72 h park for new rows. Rows already bound to
`enrichment-first-week` keep that binding and drain there, so leave the queue
provisioned until they do. Nothing is migrated or deleted. The recorded
pre-change values are `FIRST_SUMMARY_DEADLINE_SECONDS=60` (backend), the unset
fresh promotion/demotion keys (30 minutes) and `ENRICHMENT_MAX_AGE_HOURS=72`.

## Known bounds

- `services/summary_debt_repair` still discovers conversations only inside the
  72 h window. Older first-week rows are re-woken by the enrichment sweep; a
  first-week phase for that repair is a follow-up.
- The forced attempt for a row that never reaches a lane (desktop capture
  deferral, budget waiting) is the split child issue, not this change.
