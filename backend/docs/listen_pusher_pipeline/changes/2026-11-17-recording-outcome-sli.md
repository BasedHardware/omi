# Recording-outcome SLI and blocked-head pages (2026-11-17)

Measurement and alerting only. No admission, merge, projection, notes or release
behavior changes.

## Why

From 2026-11-16 18:50Z, summaries for finished batch-live recordings fell from
about 60% to about 10% for 21 hours with nothing paged. A merger on an older build
committed protocol-2 results without the source marker. The projector refused each
one as an owner-chain head (`immutable result binding mismatch`), and every later
result for that owner waited behind it. The existing signals stayed silent:

- `omi-batch-delivered-share-language` was never provisioned.
- The delivered-share family is not in the in-cluster Prometheus that rule reads.
- The obligation-age gauge is pinned at about 29 days by held receipts.
- The projection-drain log metrics were never created in Cloud Logging.

## What

- **Recording-outcome gauges.** `omi_batch_pipeline_recording_outcome_*` gauges
  come from the serving maintenance leader on backend-integration (see the batch
  CONTRACT). Each sample is three count aggregations on declared collection-group
  indexes. That is normally 3 reads per minute.
- **Walk-stop counter.** `omi_batch_projection_walk_stops_total{stop,progress}`
  counts owner-drain turns by closed stop class. The turn log line is unchanged.
- **GMP keep list.** `backend/deploy/cloud_run_gmp_sync.yaml` keeps the counter.
  The gauges already match `batch_pipeline_.*`.
- **Kill switch.** `BATCH_PIPELINE_RECORDING_OUTCOME_ENABLED` is default on.
  Turning it off stops the queries and hides the gauges.
- **Alerts.** Five rules in `charts/monitoring/alerts/recording-outcome.json`,
  plus tiles on the first screen of Core Features. Thresholds and backtests are
  in `docs/runbooks/recording-outcome.md`.

## Rollout

1. Create the indexes `recording_outcome_summarized` and
   `recording_outcome_transcribed` through the index workflow.
2. Deploy backend-integration.
3. Confirm the gauges in GMP.
4. Provision the alerts.

The fresh-unprojected and marker-skew rules read families that already serve. To
roll back, revert; the gauges carry no state.
