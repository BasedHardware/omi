# Batch stuck-state census

The census answers one question for every stock the batch pipeline can strand a
unit in: **how many rows are there, and how old is the oldest one?** It exists
because a registry entry and a CI check do not measure production, and because
several stocks (outboxes, over-cap holds, live admission, committed-but-hidden,
deep backlog, allowance holds) had no age reading at all.

Owner: batch pipeline. Scheduled endpoint: `POST /v2/batch-census/run`
(`backend/deploy/scheduler/jobs.yaml`, job `batch-stock-census`, every 10
minutes on `backend-sync`). Dashboard: `omi-batch-stuck-census`. Alarms:
`backend/charts/monitoring/alerts/batch-census.json`, rendered from the registry
by `backend/scripts/generate_batch_census_alerts.py`.

## Signal

| series | meaning |
|---|---|
| `omi_batch_pipeline_census_state_units{machine,state}` | exact count of the stock |
| `omi_batch_pipeline_census_state_oldest_age_seconds{machine,state}` | age of the oldest row from the stock's declared clock; `-1` = rows exist but none carries an ageable clock; `0` = the stock is empty |
| `omi_batch_pipeline_census_state_observed_at_seconds{machine,state}` | when this state was last sampled successfully |
| `omi_batch_pipeline_census_snapshot_timestamp_seconds` | when the whole pass last completed |
| `omi_batch_pipeline_census_registered_stocks` | stocks declared by this build |
| `omi_batch_pipeline_census_sample_failures_total{machine,state}` | per-stock sample failures; the previous reading is retained and its observation is not refreshed |

Labels are the registry's fixed `(machine, state)` vocabulary. Nothing reads
document content: one `count()` aggregation plus, when the stock has a clock, one
oldest-row projection of that clock field. No transcript, audio reference, uid,
email or conversation id is read or exported.

## Reading it correctly

- **Read the replica whose snapshot timestamp is newest.** Series exist only on
  the process that ran the pass; other replicas export nothing for these
  families. Do not `sum()` or `max()` a gauge across replicas without first
  selecting the newest snapshot.
- **`-1` is not an age.** The stock has rows, but the oldest-row projection
  returned nothing: the entry declares no clock, the only rows miss the clock
  field, or the clock is not orderable. `0` is the only healthy zero.
- **A missing state is unmeasured, not empty.** The blind alarms
  (`omi-census-snapshot-blind`, `omi-census-stocks-blind`) fire when a pass does
  not complete or a registered stock has no fresh observation.
- **An age alarm reads one source, and only the newest one.** Each per-state
  rule keeps the age series whose own `observed_at` equals the fleet maximum and
  is younger than 30 minutes; the freshness and the age come from that same
  series. A replica that sampled once and then idled therefore cannot hold a
  page open with its last reading.
- **Age is dwell from acceptance, never from a stamped deadline.** The age clock
  is `enqueued_at` for job states and `committed_at` for result projections. A
  deadline (`record_dead_letter_deadline_at`, `held_deadline_at`, `lease_until`)
  is in the future for the whole legitimate wait; using it as an age reads `0`
  and hides the stock. Deadlines stay in the entry's `Custody`, which is a
  horizon guarantee, not a measurement.
- **Age is not lateness for every stock.** `provider_pending` may legitimately be
  days old while the provider backlog drains; `cap_hold:held` can be months old
  because it waits on credits. Those stocks are measured (and the deep-backlog
  stock is banded at 7 days) but not paged. `memory_outbox` is aged from
  `available_at`, a due/backoff clock: its reading is overdue-ness, not dwell.
- **A few stocks are visibility-only.** `batch:deep_backlog`, `batch:allowance_held`,
  `batch:leased`, `batch:dead`, `batch:partial_retired`, `cap_hold:held` /
  `retained` / `batch_admitted` and the terminal projection states have a count
  and an age but no rule: they are terminal, actively owned, or durable by
  design. The complete thresholds are in the generated alert export.

## Stocks and thresholds

The registry is the source of truth (`backend/config/batch_census.py`); the
generator renders one rule per stock that sets `age_alarm_seconds`.

| machine | stocks |
|---|---|
| `batch` | every job state (`record_pending` … `dead`, provider trio, `record_recovery_waiting`) plus `committed_hidden`, `ready_parked`, `allowance_held`, `deep_backlog` |
| `batch_projection` | result projection states (`pending`, `persisted`, `ready`, `quarantine_held`, `completed`, `erased`, `claimed`) |
| `batch_recovery` | recovery intents (`held`, `prepared`, `running`, `failed_held`, `recovered`, `cancelled`) |
| `provider_outbox` | `open`, `closed` |
| `memory_outbox` | `pending`, `processing`, `delivered`, `retryable_failure`, `dead_letter` |
| `enrichment_outbox` | `pending`, `parked`, `sync_hold` (`sync_reprocess_outbox`) |
| `speaker_outbox` | `open`, `terminal_pending` (`batch_pipeline_{stage}_speaker_final_pass_outbox`) |
| `cap_hold` | over-cap holds: `held`, `staging`, `sealing`, `retained`, `batch_admitted` (`stt_cap_holds`) |
| `pipeline_ledger` | live admission and later stages: `capturing`, `sealed`, `transcribed`, `noted` |

`batch:ready` counts every row in the state, including parked holds, because a
single Firestore query cannot exclude a field and still order by the acceptance
clock. The split is published beside it: `batch:ready_runnable` is the
admissible stock (`compute_decision.outcome` unattempted or allowed),
`batch:ready_parked` is the policy/capacity-refused stock aged from its refusal
clock, and `batch:allowance_held` is the spend-gate subset (durable until the
plan changes, so measured and not paged).

Job and projection thresholds, all on dwell from acceptance: `ready_runnable` /
`result_ready` / `committed_hidden` / projection `ready` 2 h; `retry` 6 h;
`leased` none (a live lease is owned, not stuck); `record_pending` 13 days (the
barrier-approach page one day before the 14-day record deadline);
`quarantined`, `privacy_blocked`, `vendor_held`, `record_recovery_waiting`,
`quarantine_held` 24 h; `provider_running` 6 h; `provider_pending` 7 days;
`cap_hold:staging` / `sealing` 1 h; `pipeline_ledger` 6 h / 1 h / 30 min / 30 min;
`speaker_outbox:open` 6 h and `:terminal_pending` 24 h; `enrichment_outbox:pending`
24 h; `provider_outbox:open` 24 h; `memory_outbox` 24 h pending/retryable, 1 h
processing. This paragraph is illustrative, not exhaustive (projection
`pending` / `persisted` and the recovery stocks also have thresholds).
The complete list is `backend/charts/monitoring/alerts/batch-census.json`,
generated from the registry's `age_alarm_seconds`.

## Cost

A pass costs one `count()` aggregation per stock plus at most one oldest-row
pointer read. Firestore bills a count at one read per 1,000 matched index
entries (minimum one), so a pass is bounded by roughly the registry's declared
ceilings divided by 1,000: about 25k reads at today's ceilings, about 3.6M
reads/day at the 10-minute cadence (on the order of a dollar a day), and much
less in practice because the ceilings are upper bounds. Record the measured
first production pass here; if it is materially above that bound, lower the
cadence rather than removing stocks.

## Responding to a breach

1. Confirm the sample is fresh: `omi_batch_pipeline_census_state_observed_at_seconds`
   for that state must be newer than 30 minutes. If it is not, fix the census
   first; do not count by hand and do not widen the alarm.
2. Read the exact count on the dashboard next to the age. One ancient undated
   row and ten thousand fresh ones need different responses.
3. Follow the state's owning runbook. Batch job and projection states:
   `backend/docs/runbooks/batch-projection-repair.md`,
   `batch-held-dead-letter.md`, `batch-language-recovery.md`. Provider stock:
   `batch-vendor-routing-capacity.md`. Held audio: `cap-hold-durability.md`.
   Memory outbox: `enrichment-age-gate.md`.
4. Never delete staged audio, held content or a lease to silence a stock. A
   stuck row is evidence, not garbage.

## Deploying a change

Code in this repository never creates a Firestore index and never applies an
alert or dashboard to production.

1. Merge the index declarations. The release owner applies
   `firestore.indexes.json` (regenerated from `database/firestore_index_registry.py`
   through `backend/database/batch_pipeline_indexes.py`). The exporter's count
   queries need no composite; each oldest-age query needs the
   `(state, clock)` composite for its stock, and `stt_cap_holds` /
   `pipeline_ledger` / `memory_outbox` need their collection-group twins.
2. Apply the scheduler job `batch-stock-census` (enabled every 10 minutes).
3. Apply the Grafana alert export and the `omi-batch-stuck-census` dashboard
   through the normal monitoring workflow.
4. Read back one pass: the dashboard's "last completed census pass" is under
   10 minutes and the "stocks with a fresh sample" count equals
   `omi_batch_pipeline_census_registered_stocks`.

## Kill switch and rollback

`BATCH_CENSUS_EXPORT_ENABLED=false` on `backend-sync` makes the endpoint return
`disabled` without sampling; existing series then go stale and the snapshot
blind alarm fires, which is the intended signal. Removing the scheduler job is a
complete rollback: nothing else reads this signal. The metric families are
additive and no existing gauge, alarm or threshold changes meaning.
