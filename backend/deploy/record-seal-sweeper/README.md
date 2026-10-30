# Record seal sweeper operations

The `batch-pipeline-worker` chart owns this CPU-only CronJob so its image digest,
existing worker KSA/GSA and encryption-secret binding stay together. It does not
start inside a GPU worker. No new Google identity, IAM binding or cloud privilege
is needed; the only new permission is namespace-local `pods: list` for the worker
KSA. A label selector scopes inventory, but RBAC permits listing every pod in the
namespace; neither logs nor persisted state contain that response.

Ship-on values: `recordSealSweeper.enabled=true`, `runtimeEnabled=true`,
`mode=apply`. The existing proof accepts only `prod-omi-backend`, so dev/staging
disable the CronJob. Lead ruling f52d5e (2026-10-30) approves hermetic dev fixtures
and a first production **plan** cycle: override `recordSealSweeper.mode=plan`,
observe `outcome=ok`, backlog and dispositions, then restore `apply` in the lead's
chart train. Plan mode performs the same discovery and retained-tail proofs but
never invokes `apply_seals`. No legacy no-job registration occurs in either mode.

The CronJob uses the worker image built **after this change**. A chart-only
upgrade pointing to an old digest lacks the entrypoint. The lead must build and
admit the worker image through its existing workflow, verify image source closure
and dependency smoke, then install the chart at that digest. Verify control-plane
reachability, worker GSA customer-data project, existing bucket access, secret
binding, CPU-node image pull/startup within the 240s deadline, and the first
completed plan Job. No production validation is implied by local Helm/unit checks.

Each run discovers at most 128 `record_pending` jobs using the existing
state/available_at index, inspects unsealed rows, and plans at most 64 token-bearing
repairs. All reads must finish before any apply. Inventory/API/discovery errors or
planning read errors abort the run before writes. The five-minute inventory proof
is checked again after tail reads and by the unchanged repair transaction. The
transaction compares the exact row/job, privacy generation and token map before
clearing proven-dead tokens and sealing. It never clears `record_upload_failed`.
Live, unknown and mixed-sidecar identities stay pending; bare tokens alert for an
explicitly authorized operator. The ordinary admission drainer independently
proves the retained tail before enqueueing any processing.

`backlog` and `oldest_unsealed_seconds` describe the sampled unsealed pending rows,
including tokenless/refused rows. They are lower bounds, not global gauges, when
`discovery_saturated=true`; an unseen older row is possible because available_at
is a retry schedule, not a finish-time index. The ordinary drainer rotates retries.
No-job rows are outside this monitor's scope.

## Logs and alerts

One stdout record uses canonical `omi_logging`: `jsonPayload.message` is a
JSON-encoded string with `event=record_seal_sweep`, outcome, mode, counts and
closed dispositions. Consumers must parse the inner message; there is no
`jsonPayload.event`. Exceptions, plans, pod names, tokens, document IDs, emails
and object paths are never logged. The job persists no inventory or plan.

`log-metrics.json` and `alert-policies.json` are Cloud Logging/Monitoring API
definitions for the cluster's **logging project**, not necessarily the customer
Firestore project. The lead provisions/upserts these through the existing
monitoring operator path and attaches the existing agent notification channel;
this PR neither provisions nor tests notification delivery. Apply each object
individually, matching existing definitions by metric name/policy displayName to
avoid duplicates. Log-match policies require a notification channel. Read back
the definitions and verify an aggregate-only synthetic notification before
declaring alert delivery accepted. No metric labels are extracted from log text.

The backlog alert divides nonempty-cycle counts by successful-cycle counts,
aligned over ten minutes and reduced across ephemeral Job pods. Every observed
cycle must be nonempty for two hours; an empty reading or missing numerator
resets the pending period. A separate absence condition detects no successful
cycle for 30 minutes (after the metric has first produced data). The oldest-age
alert uses an exact `>14400` boolean in the producer, avoiding approximate
histogram percentile thresholds. Any bare-token skip triggers the log-match
policy. Distribution metrics retain sampled counts/ages for charts only.

The metric and naming contracts follow [Cloud Logging log-based metrics](https://docs.cloud.google.com/logging/docs/logs-based-metrics).
Histogram [percentiles are estimates](https://docs.cloud.google.com/monitoring/api/v3/distribution-metrics),
so alert thresholds use exact cycle counters instead.

Kill switch: set `recordSealSweeper.enabled=false` to remove its CronJob/RBAC,
or `runtimeEnabled=false` (`RECORD_SEAL_SWEEPER_ENABLED=false`) for new Jobs.
Runtime/mode changes do not alter an active Job's startup settings; its deadline
still bounds it to 240 seconds. Removing the CronJob can cascade deletion to its
owned Jobs. The lead verifies termination if immediate cessation is required. Neither
switch undoes seals already written. Plan mode is an observation mode, not a
rollback. No backend/listen/pusher or Cloud Run deployment is required; the lead
owns the worker-image/chart train and monitoring provisioning.
