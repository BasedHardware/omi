# Held-expiry supervisor lease ownership

The legacy batch-pipeline `/metrics` fallback still runs periodic maintenance
when both read-only metrics and the projection pump are disabled. That process
now uses the separate `serving_legacy_metrics` lease for this work, leaving
`serving_maintenance` available to the serving supervisor. Cleanup, enrichment,
queue recovery and the other fallback maintenance continue under the fallback
lease. Repeated metrics scrapes therefore cannot retain the supervisor's lease
or starve its held dead-letter expiry tick.

## Required serving configuration

The process that owns the held-expiry supervisor must run with
`BATCH_PIPELINE_SERVING_ENABLED=true`,
`BATCH_PIPELINE_PROJECTION_PUMP_ENABLED=false`, and
`BATCH_HELD_DEAD_LETTER_ENABLED=true`. The first two settings start the serving
supervisor rather than the projection-pump-only loops; the last enables held
dead-letter expiry. No new environment variable or data migration is introduced.

## Rollout and rollback

Roll out through the normal backend release while keeping the serving settings
above enabled on the supervisor. During rollback, keep the supervisor enabled
and set `BATCH_PIPELINE_READ_ONLY_METRICS_ENABLED=true` on legacy metrics
processes so their `/metrics` route refreshes gauges without entering periodic
maintenance. Re-enable the normal fallback only after restoring this change.

## Verification

The regression performs four legacy `/metrics` requests with serving and the
projection pump disabled, checks that cleanup and enrichment still run, and
proves the serving supervisor acquires `serving_maintenance` and ticks held
expiry. Lease election coverage also passes.

- [PR #26511](https://github.com/BasedHardware/omi/pull/26511)
- M1 Studio, Python 3.11.15:
  `omi-heavy run -- bash -c 'cd backend && BACKEND_PYTEST_WORKERS=1 bash test.sh tests/unit/test_batch_pipeline_serving.py tests/unit/test_batch_pipeline_leader.py'`
- Result: 71 serving tests and 16 lease tests passed.
