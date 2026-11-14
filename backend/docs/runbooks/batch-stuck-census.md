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
- **An age alarm requires a fresh sample.** Each per-state rule evaluates
  `oldest age > threshold` only while that state's observation is younger than
  30 minutes, so a broken sample cannot page as a real breach.
- **Age is not lateness for every stock.** `provider_pending` may legitimately be
  days old while the provider backlog drains; `cap_hold:held` can be months old
  because it waits on credits. Those stocks are measured (and the deep-backlog
  stock is banded at 7 days) but not paged.

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
