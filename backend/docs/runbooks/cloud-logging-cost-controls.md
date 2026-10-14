# Cloud Logging cost controls

Cloud Logging Log Storage was about $90–115/day in October 2026. Most of it
was request logs for traffic that is already counted elsewhere, plus VPC flow
logs at 100% sampling. This page lists what is reduced, where, and how to undo
each control. Retention (`_Default` 365 days) and the BigQuery sinks are out of
scope by owner decision.

## What still gets logged in full

- Every 5xx, and every 4xx other than 429, at the load balancer and at Cloud Run.
- All application stdout/stderr except the Cloud Run Uvicorn access line.
- User-defined log-based metrics (`gcloud logging metrics list`) count
  **excluded** entries too, so `cloud_armor_policy_denied_requests`,
  `backend_route_5xx` and the others keep full counts. System metrics such as
  `logging.googleapis.com/byte_count` and `billing/bytes_ingested` do **not**
  reflect exclusions; measure savings from the billing export.

## Code: no duplicate access line on Cloud Run

`utils/logging_config.py` installs `CloudRunAccessFilter` on `uvicorn.access`
when `K_SERVICE` is set. Cloud Run already writes one
`run.googleapis.com/requests` entry per request with method, URL, status and
latency, so the stdout line was a copy (about 47 GiB/day on `backend`, 94% of
it `GET /v2/sync-local-files` polls). GKE services (listen, pusher) have no
platform request log and keep their access lines.

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

Inspect: `gcloud logging sinks describe _Default --project=based-hardware`.
Remove one: `gcloud logging sinks update _Default --project=based-hardware --remove-exclusions=<name>`.
Writing the sink needs `logging.sinks.update`; `agent-prod-operator` does not have it.

## VPC flow log sampling (prod config, not in Git)

Flow logs bill twice: Networking Telemetry on generation and Vended Logs
Storage on ingestion. An exclusion only removes the second, so sampling is set
at the source instead, and there is no flow-log exclusion.

- All 47 Network Management `vpcFlowLogsConfigs` (location `global`):
  `flowSampling` 1.0 → **0.1** on 2026-10-14. Aggregation stays 1 minute with
  all metadata.
- All classic subnet flow logs (`enableFlowLogs=true`, 46 subnets):
  `logConfig.flowSampling` 0.5 → **0.1** (the GKE subnet was already 0.1).

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
