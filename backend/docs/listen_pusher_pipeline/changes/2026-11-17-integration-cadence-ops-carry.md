# Preserve restored integration cadence and admitted classification

The current production ops source pins a 200-row sweep every 10 seconds and
finish classification limit 16. The margin-40 lead ordered this O1 cadence
inverse on 2026-11-17 at 04:12:20Z after projection backlog and useful throughput
regressed under 100/20. Release reports the inverse serving at 04:14:14Z on the
same artifact with the full privacy map unchanged. This owner receipt is not an
independent recovery, old-instance cessation or cost-window acceptance.

This supersedes the earlier 2026-11-16 admission of 100/20. PR25539's former
forward cadence is held: removing it from source does not by itself lift the
hold. Explicit current source admission from Release is required before merge
or config-train apply. Hold expiry, green CI and source merge do not authorize
restoring 100/20. The separate privacy persistence and classification16 remain.

The staging ops file mirrors these keys under the existing parity contract;
staging application remains separately authorized. Both prod and staging
runtime overlays also pin these three integration-only values, so their full
environment replacement deploys preserve 200/10/classification16 instead of
dropping ops-only keys and reverting to the superseded code defaults. Tests
pin both ops files and both composed deploy environments and reject declaration
on any other service. No staging privacy admission or runtime code default changes.

Release owns production and any later inverse, serialized with config trains.
Reconcile source after a new ruling before another train can reassert stale
values. The legacy `RESTORED_DEFAULTS` in `runtime_env_canary_ops.py` and
`integration_canary_controller.py` belong to their separately gated canary
packet. Its historical classification8 must not be mistaken for the current
200/10/classification16 state or invoked without fresh admission.

Use `backend/scripts/ops/drift_check.py` for source-aware ops comparison.
The manifest-only `check_cloud_run_env_drift.py` can still list ops-only keys as
extra bindings elsewhere; the cadence keys now have matching canonical runtime
bindings. This carry adds no broad allowlist.
Runtime defaults, controller logic, capacity and enforcement behavior are unchanged.

The margin-40 lead owns projection recovery and matched safety/cost readouts.
No savings claim survives merely because the former cadence reduced reads;
useful throughput and projection age must qualify independently. Follow the
[serving contract](../../batch-pipeline-serving.md) and
[classification runbook](../../runbooks/projection-finish-async-skip.md).
