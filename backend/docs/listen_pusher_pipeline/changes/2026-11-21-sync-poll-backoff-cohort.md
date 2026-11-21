# Sync poll backoff 5% UID canary (SCA-3504)

## Serving change

`SYNC_POLL_BACKOFF_ENABLED` remains the independent kill switch. The new
`SYNC_POLL_BACKOFF_PERCENT` selects a nested, stable per-UID cohort using SHA-256
with the dedicated `sync-poll-backoff` salt. Expansion from 5 to 25 and 100 does
not reshuffle users already admitted. A partial rollout requires the authenticated
UID; missing UIDs and invalid percentages fail closed. With no percent setting,
`true` retains the legacy all-users behavior for existing non-manifest installs.

Dev stays `false` / `0`. Production backend, backend-integration, backend-sync,
backend-sync-backfill, backend-projection-pump, backend-listen and pusher move to `true` / `5`, starting
David's approved 5/25/100 canary. Custody-held responses retain their independent
300-second hint regardless of either setting.

The status response schema, client polling behavior and rate ceilings are unchanged.
Released Flutter polling honors `poll_after_ms`; older clients ignore the additive
field and retain their current cadence.

## Ramp and rollback

Hold each step for 24 hours. Before advancing, compare the cohort's sync job-status
request rate per active uploader and require completion-to-first-terminal-read p50
to rise by no more than 60 seconds. Sync 5xx and 429 rates plus support and
upload-retry signals must stay flat. Advance to 25%, then 100%, only with that
readback; otherwise roll back immediately with percent 0 or the boolean false.

This change starts only the 5% step. It does not authorize skipping either soak or
its guard readback.
