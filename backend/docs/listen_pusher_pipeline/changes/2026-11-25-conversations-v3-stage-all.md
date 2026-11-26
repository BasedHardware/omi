# Conversations v3 stage all

SCA-2918 moves the shared runtime stage from `beta` to `all`. New recording-derived
conversations are admitted for owners with a current v3-capable client marker,
including owners outside the beta channel. Owners without the marker stay on
legacy intake. See the [pipeline contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3)
and the [activation runbook](../../runbooks/conversations-v3.md).

## Rollout

- [PR #26307](https://github.com/BasedHardware/omi/pull/26307) adds pending-age
  telemetry to the backend-sync collector allowlist. The metric exports only
  after Release applies that collector config (SCA-4499). Before widening, run
  the pending-age query below and require a finite p95. An empty result or NaN
  blocks the flip.
- The Home v3 lead owns the operator watch with Release. This watch is manual.
  After the first full hour at `all`, check each one-hour window. If reconcile
  5xx exceeds 5% or pending-age p95 exceeds 3,600 seconds, move the shared stage
  to `beta` across the full deploy set.
- On 2026-11-25, David approved the flip at about 06:00 UTC on 2026-11-26 and
  accepted rollout variance.

### Operator queries

For reconcile 5xx, set `START_UTC` and `END_UTC` to the RFC 3339 bounds of the
hour being evaluated. Read the production Cloud Run request logs with the
read-only tier. The output estimates the percentage as
`100 × logged 5xx / (10 × logged 2xx/3xx + logged 4xx + logged 5xx)`.
This assumes prod retains 10% of 2xx/3xx request logs and all 5xx and
non-429 4xx. The denominator counts retained 429s as observed. An empty
window yields no reading. See the [Cloud Logging sampling policy](../../runbooks/cloud-logging-cost-controls.md#_default-sink-exclusions-prod-config-not-in-git).

```bash
set -o pipefail
source ~/.local/bin/gcp-agent-env.sh ro-prod
filter=$(cat <<EOF
  resource.type="cloud_run_revision"
  resource.labels.service_name="backend-sync"
  log_id("run.googleapis.com/requests")
  httpRequest.requestMethod="POST"
  httpRequest.requestUrl =~ "/v1/conversations-v3/reconcile([?].*)?$"
  timestamp >= "${START_UTC:?set the UTC window start}"
  timestamp < "${END_UTC:?set the UTC window end}"
EOF
)
gcloud logging read "$filter" --project=based-hardware --format='json(httpRequest.status)' |
  jq '
    map(.httpRequest.status) as $statuses |
    ($statuses | map(select(. >= 200 and . < 400)) | length) as $ok |
    ($statuses | map(select(. >= 400 and . < 500)) | length) as $client |
    ($statuses | map(select(. >= 500 and . < 600)) | length) as $server |
    (10 * $ok + $client + $server) as $total |
    if $total > 0 then 100 * $server / $total else empty end
  '
```

Cross-check at the end of the same hour with the unsampled Cloud Run
[`run.googleapis.com/request_count` metric](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/sli-metrics/req-resp-metrics#cloud-run).
Divide the `5xx` count by the sum of all response classes. This covers all
backend-sync routes. The route-log estimate drives the reconcile rollback threshold.

```promql
sum by (response_code_class) (
  increase({"run.googleapis.com/request_count", monitored_resource="cloud_run_revision",
            project_id="based-hardware", service_name="backend-sync"}[1h])
)
```

For pending age, evaluate this GMP PromQL at the end of the same hour in the
production monitoring project. The result is in seconds. If backend-sync has no
finite p95 for the window, keep the flip blocked.

```promql
histogram_quantile(
  0.95,
  sum by (le) (rate(omi_conversations_v3_pending_age_seconds_bucket{project_id="based-hardware", cluster="__run__", namespace="backend-sync"}[1h]))
)
```

### Deploy order

Follow the [activation manifest](../../../deploy/activation/conversations-v3.yaml)
and check readiness before each step.

1. Verify `llm-gateway` serves the required v3 lanes.
2. Deploy `backend`, `backend-sync`, `backend-sync-backfill`, and
   `backend-integration`. Run the
   [desktop-backend production workflow](../../../../.github/workflows/desktop_backend_prod.yml)
   after those services, before pusher. Desktop-backend does not mount the v3
   admission routes. Its deploy changes no behavior and does not gate the writer
   stage flip. It completes the manifest parity check.
3. Apply the shared listen/pusher ConfigMap and roll `pusher` to load it.
4. Roll `backend-listen` to load the same ConfigMap.

Also deploy `backend-projection-pump` and redeploy the manifest-managed jobs:
`notifications-job` in full mode, `x-connector-sync-job`, and
`frame-request-retention-job`. These are outside the activation manifest's
ordered checks and carry the same shared stage.

## Rollback

Set `conversations_v3_stage: beta` in the shared source, regenerate the runtime
manifest, and redeploy the same set, including a separate desktop-backend run.
For a hard stop on new v3 admission, set `conversations_v3: 'off'` under
`overlay` in `backend/deploy/runtime_env/prod.overlay.yaml`, regenerate the
manifest, and redeploy the same set. Previously marked recordings continue
draining.

### Desktop-backend recovery while stage is `all`

Traffic rollback or recovery can route desktop-backend to a retained revision
with its original `beta` environment. After any desktop traffic rollback or
recovery, take one of these actions.

- Forward-redeploy desktop-backend through its production workflow with the
  admitted image needed for recovery and the current manifest's v3 environment.
- Restore the shared stage to `beta` and redeploy the full set listed above,
  including a separate desktop-backend production run.

Collect fresh serving state and rerun the
[activation parity check](../../runbooks/conversations-v3.md#desktop-backend-recovery-while-stage-is-all).
Confirm stage equality and a `READY` verdict before closing recovery.
