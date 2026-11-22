# Sync poll backoff 5% UID canary (SCA-3504)

## Serving change

`SYNC_POLL_BACKOFF_ENABLED` remains the independent kill switch. The new
`SYNC_POLL_BACKOFF_PERCENT` selects a nested, stable per-UID cohort using SHA-256
with the dedicated `sync-poll-backoff` salt. Expansion from 5 to 25 and 100 does
not reshuffle users already admitted. A partial rollout requires the authenticated
UID; missing UIDs and invalid percentages fail closed. An unset percentage defaults
to 0, so enabling the kill switch without an explicit cohort does not serve hints.

Dev stays `false` / `0`. Production backend, backend-integration, backend-sync,
backend-sync-backfill, backend-projection-pump, backend-listen and pusher move to `true` / `5`, starting
David's approved 5/25/100 canary. Custody-held responses retain their independent
300-second hint regardless of either setting.

The status response schema, client polling behavior and rate ceilings are unchanged.
Released Flutter polling honors `poll_after_ms`; older clients ignore the additive
field and retain their current cadence.

The API exports low-cardinality cohort telemetry without an extra Redis or Firestore
operation. `omi_sync_job_poll_cohort_requests_total{cohort="in"|"out"}` counts
status requests; `omi_sync_job_poll_active_uploaders{cohort=...}` tracks distinct
authenticated UIDs with a nonterminal status in the last five minutes on each
process, capped at 50,000 hashed UIDs. Compare request rate per active pod-UID with
`sum by (cohort) (rate(omi_sync_job_poll_cohort_requests_total[5m])) /
sum by (cohort) (omi_sync_job_poll_active_uploaders)`. UIDs are never metric
labels. Because one UID can poll through multiple processes, the denominator is
process-local and is an approximation when aggregating replicas.

omi_sync_job_completion_to_first_terminal_read_seconds{cohort=...} records the
delay from the stored completion timestamp to the first terminal read observed by
each process. The completion timestamp is added to the existing durable completion
transaction and passed through the already-read status data; polling adds no store
read or write. Older terminal rows without that timestamp are not sampled. It uses a
bounded, process-salted job-ID cache. Compare its cohort p50 from
`histogram_quantile(0.5, sum by (le, cohort) (rate(omi_sync_job_completion_to_first_terminal_read_seconds_bucket[5m])))`
with the 60-second guard, and corroborate the poll ratio with the rollout's 5xx,
429, support, and upload-retry signals.

## Ramp and rollback

Hold each step for 24 hours. Before advancing, compare the cohort's sync job-status
request rate per active uploader and require completion-to-first-terminal-read p50
to rise by no more than 60 seconds. Sync 5xx and 429 rates plus support and
upload-retry signals must stay flat. Advance to 25%, then 100%, only with that
readback; otherwise roll back immediately with percent 0 or the boolean false.

This change starts only the 5% step. It does not authorize skipping either soak or
its guard readback.
