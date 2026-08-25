# Daily memory sweep job lifecycle

`daily-memory-sweep-job` is the retained Cloud Run owner for the bounded daily
memory replacement. It has its own image (`Dockerfile.daily_memory_sweep_job`),
workflow pair, Scheduler trigger (`daily-memory-sweep-hourly`), and runtime-env
contract. The entrypoint imports `daily_memory_sweep_inventory`, not the legacy
canonical short-term maintenance cron.

The daily inventory owns `daily_memory_sweep_registry` and
`daily_memory_sweep_control/canonical_inventory_cursor`; retiring or cleaning
the legacy `canonical_memory_maintenance_registry` or its cursor must not
delete, reset, or rewrite these records.

The entrypoint resolves the backend-owned sweep authority before opening the
inventory. A disabled, killed, malformed, or unavailable authority returns
without reading or writing the UID registry, advancing inventory cursors,
running lifecycle cleanup, invoking the scheduler/model, or committing page
state. Inventory and lifecycle work are reachable only after the authority is
explicitly open; the default remains closed.

Per-account failures are durable retry documents under
`daily_memory_sweep_control_retries/{uid}`. Retry state is written before a
fair page cursor advances. A cursor write failure can duplicate a page, but
cannot skip an account whose retry write failed. Each retry UID has its own
document, so outage volume is not silently truncated by one bounded array.

The legacy `memory-maintenance-job` and `memory-maintenance-hourly` resources
remain covered by `legacy_memory_retirement_readiness.py`; that readiness check
must not be used as evidence that the daily replacement is retired or absent.
Manual deployment is main-only and requires an exact merged-main SHA with a
successful same-repository Release Eligibility run. The admitted checkout
builds the image and runs `provision_daily_memory_sweep_scheduler.py`, which
creates or updates (and enables) the hourly trigger before the read-only
contract validation. The trigger uses the retained scheduler service identity
and the v2 Cloud Run Jobs execution URI.
