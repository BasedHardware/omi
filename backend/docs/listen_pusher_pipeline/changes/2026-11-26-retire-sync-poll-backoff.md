# Retire sync poll backoff

SCA-4464 retires the SCA-3504 cohort experiment. Authenticated
GET `/v2/sync-local-files/{job_id}` uses the legacy flag-off response. The
five-minute custody-hold hint, exact-bundle repair protocol, and per-account
poll ceiling still apply. The existing `surface_open` query parameter is
accepted for compatibility.

The runtime manifest and Helm values remove the enable and percentage
bindings. Cohort metrics are retired with the experiment. The aggregate
request and throttle counters remain.
