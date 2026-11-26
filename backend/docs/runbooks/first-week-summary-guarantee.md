# First-week summary guarantee

SCA-4790. A conversation created by a new paid subscription inside the first
`FIRST_WEEK_SUMMARY_DEADLINE_HOURS` (default `168` = 7 days, `0` disables) keeps
its first-summary obligation open until that stored window ends. It is not
closed by the 72 h historical age gate, by the repair scan's 72 h bound, or by
the 30-minute fresh-lane demotion.

The window is a stored record, not a wall-clock rule. At intake the conversation
gets

```
first_week_summary = {policy_id, paid_since, window_end_at, interval}
first_week_outcome = null        # the close-out counting key
```

`paid_since` is the commercial first-paid epoch (`subscription.paid_since`), set
once on the free->paid transition and never moved by a renewal. `current_period_start`
moves on every renewal, so it is never used for this. A row that predates
`paid_since` has no epoch and is never covered: the guarantee starts with paid
starts after the deploy. `interval` is `monthly`/`yearly`/`unknown` from the paid
period length. Referral promotions never stamp a window; the read is the
commercial subscription.

## Keys

| Key | Default | Meaning |
| --- | --- | --- |
| `FIRST_WEEK_SUMMARY_GUARANTEE_ENABLED` | on | One kill switch: deadline, lane and counter |
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

- `summarized`: a usable summary was durable by the window end.
- `attempt_failed`: an attempt landed but produced no usable summary
  (empty-output budget, BYOK block).
- `no_attempt`: none at the window end.

A summary that lands after the close is not counted retroactively. The counter
is the mechanism number; `infra/metrics/churn/first_month.py` remains the
acceptance number. Read at least 14 days after serving (the first complete
cohort closes between +7d and +14d) and name the cohort.

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
