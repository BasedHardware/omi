# Batch language delivery runbook

## What the signal is

`omi_batch_pipeline_delivered_share_ratio{route,language}` is the share of
units admitted 20 to 5 minutes earlier whose transcript was published within
the 5-minute target. It is counted from the admission side, so a unit still
held at the provider lowers its language's row. The fleet-wide tile on Core
Features can stay near normal while one language is at zero; that is the
2026-11-13 Japanese failure class.

Companions:

- `omi_batch_pipeline_delivered_share_admitted_units{route,language}` — cohort
  volume. A cell under 20 units in the 15-minute cohort is not alarmed, which
  is about 1,920 units/day: a language with real but lower volume is visible on
  the dashboard but cannot page. Lower the floor only with a noise review.
- `omi_batch_pipeline_delivered_share_units{route,language}` — delivered count.
- `omi_batch_pipeline_delivered_share_truncated` — 1 when the page hit 5,000
  rows; the share then covers the oldest rows only.
- `omi_batch_pipeline_delivered_share_sample_age_seconds` — staleness. Counts
  and ratio disappear after 600 s without a successful page.

## When `omi-batch-delivered-share-language` fires

1. Read the firing labels: `route` and `language`.
2. Confirm the cell has real volume: `admitted_units` at or above 20 for that
   route and language. A low-volume cell cannot fire, so a firing cell is real.
3. Check the sample is fresh: `sample_age_seconds` under 600. A stale sample
   removes the ratio, so a firing rule is not reading a stale value.
4. Follow that language's units with the batch census (counts only, ro-prod):
   `vendor_held` by reason, `provider_pending`/`provider_running`, and
   `quarantined`. A provider route at zero delivery is usually a vendor health,
   funding or cap hold, not a projection problem.
5. Check the projection leg only after the units are committed: the fresh guard
   (`omi_batch_pipeline_fresh_unprojected_ratio`) covers commit-to-projection
   globally.
6. Redrive or settle through the batch recovery runbook. Never delete staged
   audio.

## Backfill and drill

```bash
cd backend
python -m scripts.batch_pipeline_delivered_share_report --drill
python -m scripts.batch_pipeline_delivered_share_report --project based-hardware \
  --from 2026-11-13T00:00Z --to 2026-11-14T00:00Z --step 900 \
  --baseline-from 2026-11-06T00:00Z --baseline-to 2026-11-12T00:00Z
```

The backfill derives delivery from the result receipt (`projection.persisted_at`)
for rows that predate the acknowledge stamp, so it works on retained history.
Only `--step 900` and nonempty ranges aligned to UTC quarter hours are supported,
for both the target and baseline. Invalid windows fail before client creation.
Cohorts are counted as `[start, end)`, so an admission exactly on a shared
boundary belongs only to the following cohort.

Result reads select only completion state, summary timestamp and part count.
For legacy completed receipts without a summary timestamp, a second read selects
explicit `projection_parts.<number>.persisted_at` leaves, never whole receipt
maps containing conversation or speaker identifiers. Missing timestamps or part
counts outside 1–5,000 abort the report. This costs at most two result reads per
unstamped job, in addition to the bounded job page. The release operator must
declare the full target and baseline query budget before any production read.

The drill runs the hermetic simulator healthy and with the Japanese provider
route down; it must print `FIRING provider/ja`.

## Baseline

The rule compares a cell with its own 7-day peak, discounted to 70%. A
sustained outage cannot lower the baseline under itself for seven days. After
seven days of a total outage the peak decays and the rule stops firing; a human
must then decide whether the language is permanently retired or the baseline
should be reset. Do not silence a real breach with
`BATCH_PIPELINE_DELIVERED_SHARE_ENABLED=off`; that flag only stops the sample.
