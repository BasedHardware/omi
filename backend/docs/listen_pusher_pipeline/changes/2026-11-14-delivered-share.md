# Delivered share per STT route and language (2026-11-14)

## Why

The 2026-11-13 blind-spot audit asked why a Japanese provider-STT miss went
unseen for about a week. Every batch delivery signal was either fleet-wide or
counted from the commit side. A provider unit that never leaves `vendor_held`
has no result row, so a commit-based ratio cannot see it; the long-term
not-delivered design was global, not per language.

This adds the missing signal: **of recordings admitted, the share whose
transcript reached the user within the target, split by STT route and
language**. The target is the pipeline p90, five minutes (project bar: p50 two
minutes). The alarm compares each cell with its own trailing peak.

## Contract

### Done-true

- Backfilled data shows the 2026-11-13 Japanese dip on the Japanese row.
  `scripts/batch_pipeline_delivered_share_report.py --project ... --from ...
  --to ... --baseline-from ...` prints the per-cell table and the firing cells.
- The alarm fires in a drill: `python -m
  scripts.batch_pipeline_delivered_share_report --drill` runs the hermetic
  simulator healthy and with the Japanese provider route down, prints
  `provider/ja 36/36 1.000` then `0/36 0.000`, and reports
  `FIRING provider/ja`. It is pinned by
  `tests/unit/test_batch_pipeline_delivered_share_contract.py`.
- The Core Features dashboard row **Did the user get a transcript?** reads the
  new gauges. Production reads remain the deploy owner's step; no production
  credential is used by this change.

### Must-not-change

- Admission, merge ordering, projection order, delivery, retention and privacy
  behaviour are unchanged. The acknowledge transaction already updates the
  result row; this adds one write to the job row it already reads, carrying a
  first-delivery timestamp and a boolean. No new transaction, retry or fence.
- `enqueued_at`, `stt_route`, `policy` and `projection_binding` are only read.
- No transcript, audio, user id or email is read, stored, printed or exported.
  The sample reads job metadata only and the report prints counts.
- Missing, failed or empty samples never produce a healthy zero. A failed page
  clears the counts and ratio; counts expire at scrape time after 600 s.
- The SQL/Postgres batch store is untouched: this is a monitoring-only read of
  the Firestore job namespace the serving leader already owns.

### New state and its readers

| Field | Writer | Readers |
| --- | --- | --- |
| `jobs.delivered_at` | `ProjectionStore.acknowledge` (same transaction as `projection_state=completed`) | `utils/batch_pipeline/delivered_share`, the report script |
| `jobs.delivered_in_target` | same | same; only `True` is a positive delivery signal |

Both fields are additive. Rows written before this change carry neither, so
the live share reads zero delivery for one cohort after deploy and then
recovers. No older reader selects an unknown field; job copies, dual-store
parity and pipeline-sim goldens preserve arbitrary fields. Rollback is a
revert: the fields become inert.

`ProjectionSession.job_ref` is a reference to the job document the session
already reads in `prepare`; the acknowledge write adds no read.

## Sampling

`database/batch_pipeline_delivered_share.delivered_share_page` walks
`{namespace}_jobs` for states in the census vocabulary minus `record_pending`
(a reservation, not an admitted unit), admitted in
`[now − 900 − 300, now − 300]`, ordered by `enqueued_at`, capped at 5,000 rows.
The query projects only `segment_id`, `enqueued_at`, `state`, `stt_route`,
`policy.stt_route`, `projection_binding.language`, `delivered_in_target` and
`delivered_at`, so owner ids, content ids, conversation ids and audio
references are never materialized.
`utils/batch_pipeline/delivered_share.DeliveredShare` runs that page on the
maintenance leader at most every 300 s and publishes:

- `omi_batch_pipeline_delivered_share_ratio{route,language}`
- `omi_batch_pipeline_delivered_share_admitted_units{route,language}`
- `omi_batch_pipeline_delivered_share_units{route,language}`
- `omi_batch_pipeline_delivered_share_truncated`
- `omi_batch_pipeline_delivered_share_sample_age_seconds`

A cell is *delivered in target* when the unit's first acknowledge is at most
300 s after `enqueued_at`. Language labels are the union of the deployed
Parakeet and Modulate tables; any other code folds to `other`, and an
undeclared code to `unknown`. Neither folded cell is alarmed, and `other`
volume stays exported so a vocabulary gap is visible.

Read cost per sample: at most 5,000 job document reads (metadata only).
At the 2026-11 peak a 20-minute window is about 2,800 units, so a normal
sample is about 2,800 reads every 300 s, roughly 0.8M reads/day per active
leader. A saturated page is reported by the `truncated` gauge and covers the
oldest rows of the window, a lower bound rather than a biased sample.

`BATCH_PIPELINE_DELIVERED_SHARE_ENABLED=off` (also false/0/no) stops the page
and hides every gauge at scrape time. It is on by default, read through the
registered policy kill-switch helper, with a flag-budget entry.

## Dashboard and alarm

Core Features gains the row **Did the user get a transcript?**: a fleet tile, a
per-language time series and a per-cell table.

Grafana rule `omi-batch-delivered-share-language` (agent tier, 30m pending)
fires when a cell's share is below 70% of that cell's 7-day peak while at least
20 units were admitted in the cohort. Using the peak rather than an average
keeps a sustained dip from lowering the baseline under itself for the length of
the outage; after seven days of a total outage the baseline does decay, which
is why the runbook requires a human update.

## Verification

Local unit tests only for the query shape, aggregation, collector, acknowledge
stamp, drill, alert and dashboard contracts. No production read, deployment or
activation was performed by this change.
