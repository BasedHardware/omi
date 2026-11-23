# Sync poll backoff 5% UID canary (SCA-3504)

## Serving change

`SYNC_POLL_BACKOFF_ENABLED` remains the independent kill switch. The new
`SYNC_POLL_BACKOFF_PERCENT` selects a nested, stable per-UID cohort using SHA-256
with the dedicated `sync-poll-backoff` salt. Expansion from 5 to 25 and 100 does
not reshuffle users already admitted. A partial rollout requires the authenticated
UID; missing UIDs and invalid percentages fail closed. An unset percentage defaults
to 0, so enabling the kill switch without an explicit cohort does not serve hints.

Dev stays `false` / `0`. The production overlay renders `true` / `5` for Cloud Run
`backend`, which serves the client status GET. Production `backend-sync-backfill` keeps its
`false` / `0` preservation pins. Count only traffic on `backend` toward the canary.
Custody-held responses retain their independent 300-second hint regardless of either setting.

The status response schema, client polling behavior and rate ceilings are unchanged.
Released Flutter polling honors `poll_after_ms`; older clients ignore the additive
field and retain their current cadence.

The API exports low-cardinality cohort telemetry without an extra Redis or Firestore
operation. `omi_sync_job_poll_cohort_requests_total{cohort="in"|"out"}` counts
status requests; `omi_sync_job_poll_active_uploaders{cohort=...}` tracks distinct
authenticated UIDs with a nonterminal status in the last five minutes on each
process, capped at 50,000 hashed UIDs. Compare request rate per active pod-UID with
`sum by (cohort) (rate(omi_sync_job_poll_cohort_requests_total{service_name="backend"}[5m])) /
sum by (cohort) (omi_sync_job_poll_active_uploaders{service_name="backend"})`. UIDs are never metric
labels. Because one UID can poll through multiple processes, the denominator is
process-local and is an approximation when aggregating replicas.

`omi_sync_job_completion_to_first_terminal_read_seconds` records the delay from
the stored completion timestamp to the first terminal GET observed by each
process. The GET records either cohort regardless of the kill switch and exposes
histogram series before their first sample. It uses the already-loaded completion
timestamp and a bounded, process-salted job-ID cache. A terminal row needs an
authoritative completion timestamp to contribute. Compare its cohort p50 from
`histogram_quantile(0.5, sum by (le, cohort) (rate(omi_sync_job_completion_to_first_terminal_read_seconds_bucket{service_name="backend"}[5m])))`
with the 60-second guard, and corroborate the poll ratio with the rollout's 5xx,
429, support, and upload-retry signals.

## Ramp and rollback

Release activates 5% on the next production backend code roll at main head after
the traffic gate, SHA-bound Shipping GO, and a rendered backend env diff showing
only the intended flag and percent changes. Before dispatch, render the backend
inverse with `SYNC_POLL_BACKOFF_ENABLED=false` and verify it leaves the percent at
`5`. Apply that inverse if a guard trips.

Start the 24-hour soak once production `backend` serves the 5% configuration and
the authenticated job-status route reports measurable in-cohort traffic. Before
advancing, require lower polls per active uploader in-cohort and an in-cohort terminal-read
p50 at most 60 seconds above out-of-cohort, with observation counts in both
cohorts. Sync 5xx and 429 rates plus support and upload-retry signals must stay
flat. Require the same readback after the 25% soak before advancing to 100%.
