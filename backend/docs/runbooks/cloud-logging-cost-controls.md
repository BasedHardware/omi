# Cloud Logging cost controls

Cloud Logging Log Storage was about $90–115/day in October 2026. Most of it
was request logs for traffic that is already counted elsewhere, plus VPC flow
logs at 100% sampling. This page lists what is reduced, where, and how to undo
each control. Retention (`_Default` 365 days) and the BigQuery sinks are out of
scope by owner decision.

## What still gets logged in full

- Every 5xx, and every 4xx other than 429, at the load balancer and at Cloud Run.
- Application stdout/stderr, except Cloud Run Uvicorn access lines, the internal
  load-balancer duplicates on parakeet/diarizer/vad, and the per-call lines
  demoted to DEBUG below.
- User-defined log-based metrics (`gcloud logging metrics list`) count
  **excluded** entries too, so `cloud_armor_policy_denied_requests`,
  `backend_route_5xx` and the others keep full counts.
- `logging.googleapis.com/byte_count`, grouped by `resource.type`, **does**
  reflect exclusions. On 2026-10-15, `l7_lb_rule` fell from about 144 GiB/day
  to about 13 GiB/day after the 90% success-sample exclusion. Byte count per
  resource type is a fine same-day proxy. The billing export remains the
  source of truth for dollars.

## Code: duplicate access lines and per-call chatter

`utils/logging_config.py` installs `CloudRunAccessFilter` on `uvicorn.access`
when `K_SERVICE` is set. Cloud Run already writes one
`run.googleapis.com/requests` entry per request with method, URL, status and
latency, so the stdout line was a copy (about 47 GiB/day on `backend`, 94% of
it `GET /v2/sync-local-files` polls). Listen and pusher keep their Uvicorn
access lines. Parakeet, diarizer, and vad set `uvicorn.access` to WARNING:
each has an internal HTTP load balancer that already logs the request.

`configure_split_stream_logging` sends INFO/DEBUG to stdout and WARNING and
above to stderr. Parakeet and vad call it; backend/listen, pusher and
llm-gateway get the same split from `omi_logging.configure_logging` in text
mode (`structured-logging-rollout.md`), which also drops Cloud Run access
lines and successful probe lines.
Without that split, GKE stores Python INFO written to stderr as severity
ERROR. NeMo does not use the root logger: `nemo_logger` has `propagate=False`
and its own handlers. `quiet_repetitive_nemo_logs` drops only the per-batch
"Timestamps requested" INFO line and the two repetitive Lhotse dataloader
warnings. Other NeMo warnings and errors still emit.

Successful webhook delivery and the per-app audio-bytes HTTP 2xx line are
DEBUG. Failures stay at WARNING or ERROR.

## `_Default` sink exclusions (prod config, not in Git)

Stored entries can carry a different `resource.type` than the byte metrics.
LB request logs are stored as `http_load_balancer` (the metric label is
`l7_lb_rule`); Network Management flow logs are stored as
`vpc_flow_logs_config` (not `global`). Always dry-run a filter with
`gcloud logging read '<filter> AND timestamp>=...' --limit` before applying.

| Exclusion | Keeps | Filter (abridged) |
| --- | --- | --- |
| `cost-audit-cloud-run-success-sample` | 10% | Cloud Run `run.googleapis.com/requests`, INFO, status 200–399 |
| `cost-audit-alb-success-sample` | 10% | `http_load_balancer` `requests`, INFO, status 200–399, not Armor DENY |
| `cost-lb-armor-deny-sample` | 10% | `http_load_balancer` `requests`, `enforcedSecurityPolicy.outcome="DENY"` |
| `cost-request-429-sample` | 10% | LB or Cloud Run request logs with status 429, not Armor DENY |
| `cost-gke-subnet-flow-sample` | 10% | `resource.type="gce_subnetwork"` `vpc_flows` |

Inspect: `gcloud logging sinks describe _Default --project=based-hardware`.
Remove one: `gcloud logging sinks update _Default --project=based-hardware --remove-exclusions=<name>`.
Writing the sink needs `logging.sinks.update`; `agent-prod-operator` does not have it.

## VPC flow log sampling (prod config, not in Git)

Flow logs bill twice: Networking Telemetry on generation and Vended Logs
Storage on ingestion. An exclusion only removes the second. Source sampling
cuts both. `cost-gke-subnet-flow-sample` is an additional `_Default` exclusion
for the GKE subnet flow slice; it does not replace the source sampling.

- All 47 Network Management `vpcFlowLogsConfigs` (location `global`):
  `flowSampling` 1.0 → **0.1** on 2026-10-14. Aggregation stays 1 minute with
  all metadata.
- All classic subnet flow logs (`enableFlowLogs=true`, 46 subnets):
  `logConfig.flowSampling` 0.5 → **0.1** (the GKE subnet was already 0.1).
- `_Default` exclusion `cost-gke-subnet-flow-sample` keeps 10% of stored
  `resource.type="gce_subnetwork"` `vpc_flows` entries. Undo is
  `--remove-exclusions=cost-gke-subnet-flow-sample` on `_Default`.

Undo:

```bash
gcloud network-management vpc-flow-logs-configs update <name> --location=global --project=based-hardware --flow-sampling=1.0
gcloud compute networks subnets update <subnet> --region=<region> --project=based-hardware --logging-flow-sampling=0.5
```

Both need the human tier; `agent-prod-operator` lacks
`networkmanagement.vpcflowlogsconfigs.update` and subnet update.

## Measuring

Billing export, daily:

```sql
SELECT DATE(usage_start_time) d, sku.description, ROUND(SUM(usage.amount_in_pricing_units),1) gib, ROUND(SUM(cost),2) cost
FROM `based-hardware.gcp_billing_export.gcp_billing_export_v1_01B287_9348DC_02D256`
WHERE _PARTITIONTIME >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 10 DAY)
  AND (sku.description LIKE '%Log%' OR sku.description LIKE '%Telemetry%')
GROUP BY 1, 2 ORDER BY 2, 1
```

Spot check that an exclusion works by counting stored entries in a one-second
window with `gcloud logging read ... --format='value(httpRequest.status)'`.
