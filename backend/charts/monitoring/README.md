# Monitoring Stack

Prometheus + Grafana + Loki observability stack for the Omi backend on GKE. [Private Business dashboards](grafana/README.md).

## Production telemetry contract (#9587)

Repo-enforceable inventory of expected prod scrape targets, routing labels, and
no-data semantics lives in [`expected-targets.prod.yaml`](./expected-targets.prod.yaml).

- **Enforced in CI** by `backend/tests/unit/test_monitoring_telemetry_contract.py`.
- Jobs marked `coverage_status: enforced` must appear in `omi-journey-scrape-missing`.
- Jobs marked `coverage_status: declared` are wired in values/ServiceMonitors but
  do not yet have a dedicated coverage alert (follow-up to expand the scrape-missing rule).
- Managed GKE control-plane exclusions (`kubeProxy` / `kubeScheduler` /
  `kubeControllerManager`) are documented here and owned by #9138 / PR #11093 —
  do not page `TargetDown` for those endpoints.
- Live Instatus delivery verification and notification-policy rework remain
  maintainer-approved Phase 2 work (not claimed by the inventory).

## Telemetry cost cuts

The 2026-10-13 audit measured 527,780 head series. Production kubelet
`metricRelabelings` drop `kubernetes_feature_enabled` and the
`rest_client_{request,response}_size_bytes_{bucket,sum,count}` families;
`probesMetricRelabelings` drop `prober_probe_duration_seconds_{bucket,sum,count}`.
No committed consumer or live Prometheus rule referenced these families.
The main ServiceMonitor contributed 16,526 active series (about 3.1% of head).
The chart's existing storage-operation bucket drop is preserved because Helm
replaces relabeling lists. Probe-result counters, used latency histograms,
HPA inputs, scrape intervals, resource requests and 10-day retention stay intact.

`backend/tests/unit/test_monitoring_cost_contract.py` guards these cuts against
committed alerts, dashboards (including vendored defaults), recording rules,
adapter queries and Prometheus-reading code. Generate the conservative usage map
with `python3 backend/scripts/monitoring_metric_usage.py --metrics-file <names.json>`;
the input is a JSON name array or `/api/v1/label/__name__/values` response.
A missing committed reference is a candidate for review, not proof that an
operator never uses a metric in Explore. Before deploying, check live rules and
operator-managed dashboards again; after deploying compare post-relabel samples
and head series after compaction. Removed history ages out over the existing
retention window. Series reductions only save dollars when capacity can be reduced.

## Grafana storage

Grafana 12.1.0 uses SQLite on the existing 20Gi `standard-rwo` PVC. Prod and
dev enable `[database] wal=true`, `query_retries=10`, and
`transaction_retries=10` without changing the database type, path or persistence.
These options are defined in [v12.1.0 defaults.ini](https://github.com/grafana/grafana/blob/v12.1.0/conf/defaults.ini)
and parsed in [database_config.go](https://github.com/grafana/grafana/blob/v12.1.0/pkg/services/sqlstore/database_config.go);
their defaults are false, 0 and 5. There is no dedicated SQLite busy-timeout INI
option in that version. Retry counts are not a wall-clock timeout guarantee.

On 2026-10-12, prod logged 11 locked-database lines at 03:02Z and 67 at 09:02Z:
alert evaluation ticks dropped, Alertmanager configuration failed, a provisioning
GET returned 500 after 32.7 seconds, and health probes failed. WAL allows readers
alongside a writer; retries help transient contention but do not remove SQLite's
single-writer limit. Migrating Grafana to PostgreSQL is the proper follow-up.

The values change rolls the single Grafana pod, briefly interrupting dashboards,
alert evaluation and Grafana notifications until it is ready; the PVC is retained.
Probe settings are unchanged. Review rendered chart probe timeout/period/failure
threshold and measured restart evidence before tuning them.

12.1.0 also defines `[unified_alerting] state_periodic_save_interval` (default 5m),
but it only applies with `alertingSaveStatePeriodic`. Evaluate its crash/restart
state recovery trade-off separately. `[unified_alerting.state_history] backend=loki`
exists, but needs an authenticated writer, retention/query validation and a plan
for existing SQL annotation history before migration. Neither is enabled here;
alert history is retained.

## Dead-man

Cloud Monitoring owns **Prod Grafana external health** and **Prod Grafana dead-man:
health failing for 5 minutes** (stable legacy resource name), declared in
[`grafana-deadman.json`](../../deploy/monitoring/grafana-deadman.json). It GETs
`https://monitor.omi.me/api/health` over validated HTTPS every 60 seconds from
USA, Europe and Asia Pacific, with a 10-second request timeout and exactly HTTP
200 accepted. The policy scopes `uptime_check/check_passed` to the assigned check
ID; more than one failing checker location for 120 seconds pages (60-second
next-older alignment, count-false reduction grouped by check ID, count > 1).
Detection also includes Monitoring ingestion/evaluation latency. This tests endpoint health, not end-to-end notification delivery or all
rule evaluations, and no samples are not treated as a failed HTTP check. The legacy
display name remains unchanged so reconciliation updates the existing policy instead of creating a second one.

Before merge/deployment, create the repo or `prod` Environment variable
`MONITORING_DEADMAN_NOTIFICATION_CHANNELS` containing comma-separated full
`projects/based-hardware/notificationChannels/<id>` names of approved external
channels. Unset, blank, malformed or duplicate entries fail closed. The
monitoring workflow's prod WIF identity needs Monitoring uptime-check and
alert-policy list/get/create/update permissions (for example Monitoring Editor);
verify that grant through the normal IAM ownership process. No IAM is changed here.

After merge, `workflow_dispatch` **Deploy Cloud Run Metrics Egress**
(`gcp_cloud_run_metrics_egress.yml`) on `main` with `environment=prod`; it requires
`prod` Environment approval. The ensure step runs before Helm, independently of
Grafana, reconciles unique display names, preserves assigned check/policy and
condition IDs, verifies writes, and fails on duplicates/API errors. Unchanged
runs do not write. Updates patch only supported drifted uptime-check fields;
immutable drift (resource, period, checker type or disabled state) fails with a
manual delete-and-recreate instruction. Rerun afterward to bind the policy to
the new check ID. After rollout, operators should confirm Grafana readiness,
healthy multi-region samples and approved channel delivery; this change has only
local validation, not a live acceptance receipt.

## Source provisioning and GMP shadow datasource

The existing `grafana_dashboard_provisioning.yml` validates dashboard JSON and
split/combined alert equality. Main updates provision development dashboards;
production requires explicit `environment=prod` dispatch from main. The job binds
the protected `prod` Environment or `development`; production uses its existing
`MONITOR_GRAFANA_TOKEN`, while development may inherit the repository's dev token.
PR #21686 restored legacy dashboard provisioning through monitoring-specific
Environments; the broader alert writer requires protected production authority
and a permission probe. Rotate only failed credentials. Never use a credential belonging to the retired TV Grafana instance.

The production path upserts `alert-rules.json` by stable UID, backs up live rules
before writes, preserves UI/API provenance and notification timing, retains
unknown live UIDs, and fails on definition drift after readback. File-provisioned
rules require their owner; the API script refuses takeover. Both existing Grafana
writers share an environment lock. Contact points and notification policies are
read-only dependencies, not managed by the importer. Paused source rules stay
paused. Removing source entries does not silently delete live rules.

Parent/operator commands, after loading the authorized token in the environment:

```bash
python3 backend/scripts/provision_monitoring_alerts.py --lint
python3 backend/scripts/provision_monitoring_alerts.py --probe-datasources
python3 backend/scripts/provision_monitoring_alerts.py  # read-only UID/definition drift
# After reviewing drift and query probes:
gh workflow run grafana_dashboard_provisioning.yml --repo BasedHardware/omi \
  --ref main -f environment=prod
```

The workflow retains pre-write alert and dashboard snapshots for 15 days.
Canaries are installed, read back and queried successfully before any business
rule can switch to `KeepLast`; a failed probe blocks those business updates.
Preserve it before a reviewed rollback; it includes prior rule definitions and
new UIDs, never token/contact settings. The direct parent API equivalent is
`--apply --backup-file <new-file>`; backups use exclusive creation and mode0600.
Dashboard imports require an exclusive `--backup-file`, preserve the existing
folder, verify desired fields on readback and never follow credentialed redirects. Only the reviewed dashboard allowlist is imported; the overview board
is production-only because it uses production datasource UIDs. Query/visible
acceptance remains required; POST success and a version are not rendering proof.

The protected production metrics-egress workflow additionally layers
[`gmp/frontend-values.prod.yaml`](gmp/frontend-values.prod.yaml) onto the pinned
stack. This adds Google's digest-pinned frontend, two node-separated replicas,
PDB, internal Service and non-default datasource `gmp-cloud-run`. Existing local
Prometheus, adapter URLs, recording rules and warm-up Service remain intact.
`verify_gmp_frontend_render.py` compares base/candidate renders without printing
Secret payloads. The rollout probes the actual Grafana query path; readiness
alone cannot prove Google API authorization or credential renewal.

The frontend uses the verified existing exporter KSA's Monitoring Viewer Workload
Identity. No new token or IAM change is required. It is accessible inside the
trusted cluster under that identity's metrics scope, not limited to Cloud Run by
its name. All migration queries must scope project/location/resource labels.
Before retiring the LB exporter, preserve/transfer its Helm-owned KSA; the separate
`gmp/exporter-identity-retention-values.prod.yaml` targets that exporter release,
not the stack. Verify the stored Helm manifest contains the retention annotation.

No business query, panel or HPA is cut over by adding this datasource. Require
accepted consumer-specific shadow comparisons for at least24h, full long-query
warm-up, label/rate/histogram equivalence, and notification receipts before any
exporter removal. An unsuccessful family comparison is a hold, never evidence
that tolerances should be relaxed. Removing the overlay preserves the primary
sources; with pruning disabled the unused shadow UID may remain in Grafana until
an explicit datasource cleanup. Do not enable global datasource pruning.

The read-only migration tools inventory source consumers and compare exact metric
families without changing any datasource or rule. Regenerate the inventory after
source changes, then run only reviewed mappings over at least24h:

```bash
python3 backend/scripts/monitoring_gmp_shadow.py --inventory \
  --output backend/charts/monitoring/gmp-query-migration-inventory.json
source ~/.local/bin/gcp-agent-env.sh ro-prod
python3 backend/scripts/monitoring_gmp_shadow.py \
  --kube-context gke_based-hardware_us-central1_prod-omi-gke --gcloud-token \
  --hours 24 --step 300 --ids omi_fallback_total,omi_journey_accepted_total,omi_journey_terminal_total \
  --output /tmp/gmp-shadow.json
```

For frontend acceptance, compare through Grafana's documented
[datasource UID proxy](https://grafana.com/docs/grafana/latest/developer-resources/api-reference/http-api/api-legacy/data_source/#data-source-proxy-calls),
using the parent's token loader instead of `--gcloud-token`:

```bash
python3 backend/scripts/monitoring_gmp_shadow.py \
  --kube-context gke_based-hardware_us-central1_prod-omi-gke \
  --managed-url https://monitor.omi.me/api/datasources/proxy/uid/gmp-cloud-run \
  --managed-token-env MONITOR_GRAFANA_TOKEN --hours 24 --step 300 \
  --ids omi_fallback_total,omi_journey_accepted_total,omi_journey_terminal_total \
  --output /tmp/gmp-frontend-shadow.json
```

Credentialed URLs are fixed to the production Grafana GMP/Prometheus proxy UIDs;
`--gcloud-token` is fixed to Google's project endpoint. Custom URLs accept no token.

Keep the GMP canary healthy over the observation window, including credential
renewal. Direct Google API comparisons alone do not prove the frontend path.

An empty/partial response, mismatched labels or values, shared gaps, or an
unsupported custom metric cannot pass. Family aggregates do not prove every
consumer's threshold or label semantics; complete per-consumer rewrites and
Grafana evaluation comparisons remain a separate admission gate. The report
always records `cutover_authorized=false`, including a matched comparison.

## Architecture

```
┌───────────────────────────────────────────────────────────────────────────┐
│  GKE Cluster (prod-omi-gke / dev-omi-gke)                               │
│                                                                           │
│  ┌──────────────┐   scrape    ┌─────────────┐   query   ┌────────────┐  │
│  │ Pod metrics   │──────────►│  Prometheus   │◄─────────│  Grafana   │  │
│  │ (app /metrics)│           │  (10d, prod  │          │ prod: monitor│ │
│  │               │           │  100Gi; dev  │          │              │ │
│  │               │           │   50Gi)       │          │              │ │
│  └──────────────┘           └───────┬───────┘          │   .omi.me   │ │
│                                      │                   │ dev: monitor│ │
│  ┌──────────────┐   scrape          │                   │  .omiapi.com│ │
│  │ DCGM exporter │──────────►       │                   └─────┬──────┘  │
│  │ (GKE addon)   │                  │                          │         │
│  └──────────────┘                   │ query                   │ query   │
│                                      ▼                         │         │
│  ┌──────────────┐   scrape  ┌───────────────┐                │         │
│  │ Stackdriver   │────────►│  prometheus-   │                │         │
│  │ exporter      │  (via    │  adapter       │                │         │
│  │ (GCP metrics) │  Prom)   │  (HPA metrics) │                │         │
│  └──────────────┘          └───────┬────────┘                │         │
│                                     │                         │         │
│                          ┌──────────┴──────────┐             │         │
│                          │ external.metrics     │             │         │
│                          │ custom.metrics.k8s.io│             │         │
│                          └──────────┬──────────┘             │         │
│                                     ▼                         │         │
│                             ┌──────────────┐                 │         │
│                             │  HPA          │                 │         │
│                             │  controllers  │                 │         │
│                             └──────────────┘                 │         │
│                                                               │         │
│  ┌──────────────┐   collect  ┌──────────┐   query            │         │
│  │ Pod logs      │──────────►│  Loki     │◄──────────────────┘         │
│  │ (stdout/err)  │ (k8s API) │ (GCS,15d) │                             │
│  └──────────────┘           └──────────┘                              │
│         ▲                        ▲                                      │
│         │                        │                                      │
│     Alloy                    basic auth                                 │
│    (DaemonSet)        (alloy-basic-auth → loki-basic-auth)             │
└───────────────────────────────────────────────────────────────────────────┘
```

Note: Stackdriver exporter is scraped by Prometheus (job `prometheus-stackdriver-metrics`), then prometheus-adapter queries Prometheus for those metrics. The exporter does not feed the adapter directly.

Cloud Run application metrics take a push-then-pull bridge because a public URL scrape reaches only one random autoscaled instance. Each `backend` and `desktop-backend` instance exposes its registry on loopback port 9090 to Google's Managed Service for Prometheus sidecar. The sidecar writes `prometheus.googleapis.com/omi_*` to Cloud Monitoring. A separate, rate-limited Stackdriver exporter imports Cloud Run backend, desktop-backend, sync services, and notifications-job, and Prometheus scrapes it as `cloud-run-application-metrics`. The checked-in namespace allowlist includes those services and `notifications-job`; deployed ingestion still requires each sidecar and the matching metrics-egress release (see below). Sync intake and sync conversation shape are readable today through Cloud Logging of `omi_sync_intake` and `omi_conversation_shape`. See [`../../docs/runbooks/cloud-run-metrics-ingestion.md`](../../docs/runbooks/cloud-run-metrics-ingestion.md).

## Components

| Component | Chart | Purpose | Namespace |
|-----------|-------|---------|-----------|
| **Prometheus** | `kube-prometheus-stack` | Metrics collection, 10d retention; prod 100Gi PVC, dev 50Gi | `{env}-omi-monitoring` |
| **Grafana** | `kube-prometheus-stack` | Dashboards and alerting (prod: `monitor.omi.me`, dev: `monitor.omiapi.com`) | `{env}-omi-monitoring` |
| **Alertmanager** | `kube-prometheus-stack` | Development only; production retired with native alerts | `dev-omi-monitoring` |
| **Grafana Image Renderer** | `kube-prometheus-stack` | Alert screenshot capture | `{env}-omi-monitoring` |
| **Loki** | `loki` | Log aggregation, distributed mode, GCS backend, 15d retention | `{env}-omi-monitoring` |
| **Alloy** | `alloy` (k8s-monitoring) | Pod log collection via Kubernetes API | `{env}-omi-monitoring` |
| **prometheus-adapter** | `prometheus-adapter` | Translates Prometheus metrics → K8s custom metrics API for HPA | `{env}-omi-monitoring` |
| **Stackdriver exporter** | `prometheus-stackdriver-exporter` | Bridges GCP load balancer metrics into Prometheus | `{env}-omi-monitoring` |
| **DCGM exporter** | GKE-managed addon | GPU metrics (utilization, memory, temperature) | `gke-managed-system` |
| **kube-state-metrics** | `kube-prometheus-stack` | K8s object state (pod count, deployment replicas) | `{env}-omi-monitoring` |
| **node-exporter** | `kube-prometheus-stack` | Node-level CPU, memory, disk, network | `{env}-omi-monitoring` |

## Data Flows

### Metrics Scraping

GKE application metrics use two pull mechanisms. Cloud Run uses a third, per-instance push bridge because its public URL is load balanced.

**1. ServiceMonitor (recommended for new GKE services)**

Used by: parakeet.

The service chart includes a `ServiceMonitor` CRD that Prometheus auto-discovers. This is the preferred approach — no changes to the monitoring chart needed.

**2. Pod annotations + additionalScrapeConfigs**

Used by: backend-listen, pusher, llm-gateway, deepgram engine, GPU metrics, Stackdriver.

Pods set annotations (`prometheus.io/scrape: "true"`, `prometheus.io/port`, `prometheus.io/path`) and a matching `additionalScrapeConfigs` entry in `kube-prometheus-stack` values defines the scrape job.

Backend-listen, pusher, and llm-gateway require bearer token auth via the `metrics-scrape-token` secret.

**3. Cloud Run GMP sidecar -> Cloud Monitoring -> isolated Stackdriver exporter**

Used by: Cloud Run `backend`, `desktop-backend`, sync services, and `notifications-job` (after their deployments). The sidecar scrapes loopback port 9090; public `/metrics` remains bearer protected. The exporter bridge is temporary: Cloud Run metrics will be queried directly from GMP after at least 24 hours of accepted shadow comparisons.

### Custom Scrape Jobs (prod)

These are the `additionalScrapeConfigs` and ServiceMonitor targets. Built-in kube-prometheus-stack targets (kube-state-metrics, node-exporter, kubelet, development Alertmanager, Prometheus itself) are not listed here.

| Job | Target | Interval | Auth |
|-----|--------|----------|------|
| `backend-listen-metrics` | backend-listen pods `/metrics:8080` | 15s | Bearer token |
| `pusher-metrics` | pusher pods `/metrics:8080` | 15s | Bearer token |
| `llm-gateway-metrics` | llm-gateway pods `/metrics:8080` | 15s | Bearer token |
| `dg_engine_metrics` | DG engine pods in `prod-omi-dg-self-hosted` | 2s | None |
| `gpu-metrics` | all pods in `gke-managed-system` (includes DCGM exporter) | 1s | None |
| `prometheus-stackdriver-metrics` | Load-balancer/Firestore Stackdriver exporter in `prod-omi-monitoring` | 60s | None |
| `cloud-run-application-metrics` | `prometheus.googleapis.com/omi_*` for Cloud Run `backend`, `desktop-backend`, sync services, and `notifications-job` via isolated exporter | 60s | None |
| ServiceMonitor: `parakeet` | parakeet pods `/metrics:9091` | 15s | None |

For llm-gateway streams, `llm_gateway_requests_total{outcome="success"}` is emitted only after the provider's
terminal SSE marker (`data: [DONE]` or Anthropic `event: message_stop`) is observed. EOF without that marker,
transport failure after first output, and client cancellation have separate bounded `outcome`, `phase`, and
`error_class` values. This proves provider completion, not guaranteed delivery of the terminal chunk to the client.
`credential_source` separates Omi-managed traffic from service-forwarded BYOK without putting key material or user
identity in labels. `llm_gateway_stream_ttfb_seconds` records time to the first non-empty provider chunk.

### Log Pipeline

```
Pod stdout/stderr → Alloy (kubernetesApi method) → Loki gateway (basic auth) → GCS
                                                                                 ↓
                                                                    Grafana Explore (LogQL)
```

Collector values stay enabled pending the valid teardown review in [LOG_CONSOLIDATION.md](LOG_CONSOLIDATION.md). Held route/error and storm preparations live in [route-errors/](route-errors/README.md). Alloy collects from `{env}-omi-backend` namespace only. Labels kept: `app_kubernetes_io_name`, `container`, `instance`, `job`, `level`, `namespace`, `service_name`, `pod` (structured metadata).

Loki runs in distributed mode: 2x ingester, 2x querier, 2x query-frontend, 2x query-scheduler, 2x distributor, 1x compactor, 2x index-gateway, 1x ruler. Storage on GCS (`prod-omi-loki-chunks`). Retention: 15 days (360h).

### GPU Metrics

DCGM exporter is a GKE-managed addon (not in this repo). It runs in `gke-managed-system` and exposes metrics like:
- `DCGM_FI_DEV_GPU_UTIL` — GPU utilization %
- `DCGM_FI_DEV_FB_USED` / `DCGM_FI_DEV_FB_FREE` — GPU memory
- `DCGM_FI_DEV_GPU_TEMP` — GPU temperature

Prometheus scrapes these via the `gpu-metrics` job. GPU node pools:
- `parakeet-pool` — NVIDIA L4 (parakeet ASR)
- `diarizer-pool` — NVIDIA T4 (speaker diarization)
- `vad-pool-v2` — NVIDIA T4 (voice activity detection)

### HPA Custom Metrics (prometheus-adapter)

The adapter translates Prometheus queries into K8s metrics APIs so HPAs can scale on custom metrics. It serves two APIs:
- `external.metrics.k8s.io` — namespace-scoped metrics (most HPA metrics use this)
- `custom.metrics.k8s.io` — pod-scoped metrics (parakeet uses this for `parakeet_active_streams` and `parakeet_active_requests_total`)

| Metric | Source | Used by |
|--------|--------|---------|
| `backend_listen_active_ws_connections_per_pod` | backend-listen gauge | backend-listen HPA |
| `pusher_active_ws_connections_per_pod` | pusher gauge | pusher HPA |
| `vad_request_latency_p99` | Stackdriver ILB histogram | vad HPA |
| `diarizer_request_latency_p99` | Stackdriver ILB histogram | diarizer HPA |
| `backend_listen_response_code_500` | Stackdriver LB counter | backend-listen HPA |
| `backend_listen_requests_per_pod` | Stackdriver LB counter / replica count | backend-listen HPA |
| `engine_active_requests_stt_streaming` | DG engine gauge | DG engine HPA |
| `engine_active_requests_stt_batch` | DG engine gauge | DG engine HPA |
| `engine_active_requests_tts_batch` | DG engine gauge | DG engine HPA |
| `engine_estimated_stream_capacity` | DG engine gauge | DG engine HPA |
| `engine_requests_active_to_max_ratio` | DG engine derived | DG engine HPA |
| `engine_to_api_pod_ratio` | kube-state-metrics | DG scaling |
| `engine_avg_gpu_utilization` | DCGM via Prometheus | DG engine HPA |
| `parakeet_active_streams` | parakeet gauge | parakeet HPA |
| `parakeet_active_batch_requests` | parakeet gauge | parakeet HPA |
| `parakeet_active_requests_total` | parakeet derived (streams + batch) | parakeet HPA |
| `parakeet_gpu_utilization` | DCGM via Prometheus | parakeet HPA |
| `parakeet_request_latency_p99` | parakeet histogram | parakeet HPA |

Parakeet adapter rules are defined in the parakeet chart's `values.yaml` and are mirrored in the production cluster-wide adapter (see below).

### Stackdriver Exporter

Bridges GCP Cloud Monitoring into Prometheus. Two releases share the existing Workload Identity service account (`prod-omi-prom-stackdriver-gsa`):

- `prod-omi-prometheus-stackdriver-exporter` exposes LB and Firestore metrics sampled by Google every 60 seconds; the production scrape is 60 seconds. HPA rate windows remain five minutes.
- `prod-omi-cloud-run-metrics-exporter` reads only `prometheus.googleapis.com/omi_*`, filtered to the Cloud Run monitored-resource namespaces `backend`, `desktop-backend`, and `notifications-job`; Prometheus scrapes this release every 60 seconds.
- `prod-omi-cloud-run-sync-metrics-exporter` (`prometheus-stackdriver-exporter/<env>_sync_omi_cloud_run_metrics_exporter.yaml`) reads only the consumed families from `backend-sync`, `backend-sync-backfill`, and `backend-integration`: `omi_sync_*`, `omi_journey_*`, `omi_client_journey_*`, `omi_capture_finalization_*`, `omi_queue_oldest_ready_*`, `omi_owner_recognition_conversations_total`, `omi_conversation_duration_seconds`, `omi_conversation_summary_vector_upserts_total`, and `omi_firestore_documents_per_operation`. Those services run the full backend codebase, so importing every family from them took a collection from ~52k to ~187k series and OOMKilled the exporter at 2Gi (2026-10-16). It is a separate release because the exporter ANDs every matching filter and Cloud Monitoring rejects `OR` across `resource.labels` (HTTP 400), so one filter cannot select "all families here, some families there". Add a family only together with the alert or dashboard that reads it from those services. Both releases are scraped as `cloud-run-application-metrics`.

The application exporter is separate to prevent Cloud Monitoring API read cost from multiplying every per-instance application series by the legacy 1-second scrape rate. Stackdriver exporter exposes normalized names such as `stackdriver_prometheus_target_prometheus_googleapis_com_<metric>_<type>`; retain the `service_name` and `instance` labels and aggregate counters across instances in PromQL.

### Deployment verification: scrape Cloud Run `backend-sync`

The sync exporter release imports `omi_sync_*` and `omi_conversation_duration_seconds` from the sync services (not `omi_conversation_{speech_seconds,segments}` or `omi_fallback_total`, which no alert reads from them); until it deploys, `omi_sync_intake_total`, `omi_sync_lane_jobs_total`, and `omi_conversation_duration_seconds{source="sync"}` are empty in Prometheus. Alerts and the Core Features sync panel use Cloud Logging of `omi_sync_intake` / `omi_conversation_shape` instead.

Concrete change, cost, verify:

1. **Exporter filter** — `backend/charts/monitoring/prometheus-stackdriver-exporter/{dev,prod}_sync_omi_cloud_run_metrics_exporter.yaml` restricts Cloud Monitoring reads to the listed family prefixes with `resource.labels.namespace=one_of("backend-sync","backend-sync-backfill","backend-integration")`; `{dev,prod}_omi_cloud_run_metrics_exporter.yaml` covers `backend`, `desktop-backend`, and `notifications-job`. Apply those values through the metrics-egress workflow. Keep the `prometheus.googleapis.com/omi_*` prefix. Do **not** fold this into the 1-second load-balancer exporter.
2. **Sidecar on the service** — `.github/workflows` that deploy `backend-sync` must attach the same GMP sidecar + `PROMETHEUS_SIDECAR_PORT=9090` loopback listener used by `backend` / `desktop-backend` (`backend/docs/runbooks/cloud-run-metrics-ingestion.md`). Without the sidecar there is nothing for Cloud Monitoring to ingest.
3. **Cost** — GMP samples scale with `series × instances × 30s`. Shape histograms are 342 children per process (6 sources × 3 families); sync only populates `source="sync"` plus the existing `omi_sync_*` families. Sidecar adds 1 vCPU + 512 MiB per active `backend-sync` instance (same as backend). Isolated exporter API reads grow by one namespace, still at 30s.
4. **Verify** — after deploy, `count({job="cloud-run-application-metrics", __name__=~"omi_.*", service_name="backend-sync"})` must be > 0, and `omi-cloud-run-metric-names-unnormalized` stays at 0. Then `sum(rate(omi_conversation_duration_seconds_count{source="sync"}[5m]))` and `sum(rate(omi_sync_intake_total[5m]))` should match Cloud Logging counts of `omi_conversation_shape source=sync` and `omi_sync_intake` within the 30s exporter offset. Do not enable a Prometheus alert on those series before this proof.

## Values Files

Each component has dev and prod values:

`.github/workflows/gcp_cloud_run_metrics_egress.yml` owns the Cloud Run application exporter and its kube-prometheus-stack scrape configuration: relevant merges auto-deploy development, while production requires a protected-environment dispatch from `main`.

| Component | Dev | Prod |
|-----------|-----|------|
| kube-prometheus-stack | `kube-prometheus-stack/dev_omi_monitoring_values.yaml` | `kube-prometheus-stack/prod_omi_monitoring_values.yaml` |
| prometheus-adapter | `prometheus-adapter/dev_omi_prometheus_adapter.yaml` | `prometheus-adapter/prod_omi_prometheus_adapter.yaml` |
| Alloy | `alloy/dev_omi_k8s_monitoring_values.yml` | `alloy/prod_omi_k8s_monitoring_values.yml` |
| Loki | `loki/dev_omi_loki_values.yaml` | `loki/prod_omi_loki_values.yaml` |
| Stackdriver exporter | `prometheus-stackdriver-exporter/dev_omi_stackdriver_exporter.yaml` | `prometheus-stackdriver-exporter/prod_omi_stackdriver_exporter.yaml` |
| Cloud Run metrics exporter | `prometheus-stackdriver-exporter/dev_omi_cloud_run_metrics_exporter.yaml` | `prometheus-stackdriver-exporter/prod_omi_cloud_run_metrics_exporter.yaml` |
| Cloud Run sync metrics exporter | `prometheus-stackdriver-exporter/dev_sync_omi_cloud_run_metrics_exporter.yaml` | `prometheus-stackdriver-exporter/prod_sync_omi_cloud_run_metrics_exporter.yaml` |
| Grafana ALB cert | `kube-prometheus-stack/dev_omi_grafana_alb_cert.yaml` | `kube-prometheus-stack/prod_omi_grafana_alb_cert.yaml` |

## Current Dashboards

45 dashboards on prod Grafana (`monitor.omi.me`), organized by folder.

### General (33) — kube-prometheus-stack defaults + custom

Most are bundled with kube-prometheus-stack and auto-provisioned. Custom dashboards are noted.

| Dashboard | UID | Tags | Notes |
|-----------|-----|------|-------|
| Alertmanager / Overview | `alertmanager-overview` | `alertmanager-mixin` | Development bundled |
| Backend API Monitoring | `57c2a5ea-c310-4401-ac72-54dbc6da4c7e` | `api, backend, monitoring, omi` | **Custom** |
| Backend API Monitoring | `3e7c5f57-a1be-4175-81e6-1f0c7c28b9dd` | `api, backend, monitoring, omi` | **Custom** (duplicate — consolidate) |
| CoreDNS | `vkQ0UHxik` | `coredns, dns` | Bundled |
| etcd | `c2f4e12cdf69feb95caa41a5a1b423d9` | `etcd-mixin` | Bundled |
| Grafana Overview | `6be0s85Mk` | — | Bundled |
| K8s Node Metrics / Multi Clusters | `your_custom_uid_X0dfg` | `Prometheus, node_exporter` | **Custom** (community import) |
| Kubernetes / API server | `09ec8aa1e996d6ffcd6817bbaff4db1b` | `kubernetes-mixin` | Bundled |
| Kubernetes / Compute Resources / Multi-Cluster | `b59e6c9f2fcbe2e16d77fc492374cc4f` | `kubernetes-mixin` | Bundled |
| Kubernetes / Compute Resources / Cluster | `efa86fd1d0c121a26444b636a3f509a8` | `kubernetes-mixin` | Bundled |
| Kubernetes / Compute Resources / Namespace (Pods) | `85a562078cdf77779eaa1add43ccec1e` | `kubernetes-mixin` | Bundled |
| Kubernetes / Compute Resources / Namespace (Workloads) | `a87fb0d919ec0ea5f6543124e16c42a5` | `kubernetes-mixin` | Bundled |
| Kubernetes / Compute Resources / Node (Pods) | `200ac8fdbfbb74b39aff88118e4d1c2c` | `kubernetes-mixin` | Bundled |
| Kubernetes / Compute Resources / Pod | `6581e46e4e5c7ba40a07646395ef7b23` | `kubernetes-mixin` | Bundled |
| Kubernetes / Compute Resources / Workload | `a164a7f0339f99e89cea5cb47e9be617` | `kubernetes-mixin` | Bundled |
| Kubernetes / Controller Manager | `72e0e05bef5099e5f049b05fdc429ed4` | `kubernetes-mixin` | Bundled |
| Kubernetes / Kubelet | `3138fa155d5915769fbded898ac09fd9` | `kubernetes-mixin` | Bundled |
| Kubernetes / Networking / Cluster | `ff635a025bcfea7bc3dd4f508990a3e9` | `kubernetes-mixin` | Bundled |
| Kubernetes / Networking / Namespace (Pods) | `8b7a8b326d7a6f1f04244066368c67af` | `kubernetes-mixin` | Bundled |
| Kubernetes / Networking / Namespace (Workload) | `bbb2a765a623ae38130206c7d94a160f` | `kubernetes-mixin` | Bundled |
| Kubernetes / Networking / Pod | `7a18067ce943a40ae25454675c19ff5c` | `kubernetes-mixin` | Bundled |
| Kubernetes / Networking / Workload | `728bf77cc1166d2f3133bf25846876cc` | `kubernetes-mixin` | Bundled |
| Kubernetes / Persistent Volumes | `919b92a8e8041bd567af9edab12c840c` | `kubernetes-mixin` | Bundled |
| Kubernetes / Proxy | `632e265de029684c40b21cb76bca4f94` | `kubernetes-mixin` | Bundled |
| Kubernetes / Scheduler | `2e6b6a3b4bddf1427b3a55aa1311c656` | `kubernetes-mixin` | Bundled |
| Node Exporter / AIX | `7e0a61e486f727d763fb1d86fdd629c2` | `node-exporter-mixin` | Bundled |
| Node Exporter / MacOS | `629701ea43bf69291922ea45f4a87d37` | `node-exporter-mixin` | Bundled |
| Omi Core Features | `omi-core-features` | — | **Custom** — user-outcome view: journeys, subscriptions, LLM gateway, capture pipeline, PTT transport (realtime_voice client journey), conversation shape (length p10/p50/p90 and <2min share by source), and conversation search freshness (summary-vector writes and retrieval degradation). Conversation-shape histograms for `source="sync"` and `omi_sync_intake_total` are empty in Prometheus until backend-sync is scraped; the collapsed row's third panel reads Cloud Logging of `omi_sync_intake` instead. The finalization gauges it reads are one global value republished by every backend-listen replica: aggregate with `max()`, never `sum()`. |
| Node Exporter / Nodes | `7d57716318ee0dddbac5a7f451fb7753` | `node-exporter-mixin` | Bundled |
| Node Exporter / USE Method / Cluster | `3e97d1d02672cdd0861f4c97c64f89b2` | `node-exporter-mixin` | Bundled |
| Node Exporter / USE Method / Node | `fac67cfbe174d3ef53eb473d73d9212f` | `node-exporter-mixin` | Bundled |
| Parakeet ASR Monitoring | `07e4c65f-ae79-414d-bf05-99468267d199` | `asr, gke, gpu, parakeet` | **Custom** — GPU ASR service metrics |
| Prometheus / Overview | `9fa0d141-d019-4ad7-8bc5-42196ee308bd` | `prometheus-mixin` | Bundled |

### Cloud Run (4) — per-service dashboards

Folder: `Cloud Run` (folder UID: `aev9if48326f4e`)

| Dashboard | UID | Notes |
|-----------|-----|-------|
| Backend | `0253019b-c68a-4aef-a27d-6bb3408727fb` | Cloud Run backend (main API) |
| Backend-integration | `5be48038-a72b-4938-99ed-7a8747655294` | Cloud Run backend-integration |
| Backend-sync | `8bf7bd3f-8dbc-4f86-a532-557bfac0d7ac` | Cloud Run backend-sync |
| Plugins | `e736ab7d-d3e8-444f-a743-369b054def9e` | Cloud Run plugins service |

### GKE (5) — per-service dashboards

Folder: `GKE` (folder UID: `aev9igt5fwgsgc`)

| Dashboard | UID | Notes |
|-----------|-----|-------|
| Backend-listen | `855b2e16-c098-407a-85dc-dc9ce87698a9` | GKE WebSocket listener |
| Deepgram self-hosted | `fedizdcosu1oga` | Self-hosted STT engine |
| Diarizer | `303b7396-ce6e-48ee-be24-9c157a710adf` | Speaker diarization GPU service |
| Pusher | `c758b698-01a0-4b5c-b58c-e81e4ff33ccd` | Audio pusher service |
| VAD | `72cfe240-ae8c-4076-845e-c58e28f12d87` | Voice activity detection GPU service |

### Omi Services (5) — cross-cutting dashboards

Folder: `Omi Services` (folder UID: `betdycdziadc0e`)

| Dashboard | UID | Notes |
|-----------|-----|-------|
| Cloud Armor denied requests | `5feac510-b391-48fc-9c4b-1b8dde4ab32a` | WAF/security denied traffic |
| Cloud Run Services - Logs | `d2d782ef-f537-46b8-969d-f73561ec7d07` | Aggregated Cloud Run logs view |
| Global External ALB | `59aa0de7-15c6-413f-acba-b7e99296ad75` | External load balancer metrics |
| Omi Kubernetes Events | `3714dbfa-114b-47a0-99ca-1a26354e792a` | K8s event stream (OOM kills, pod evictions) |
| Resilience / Fallbacks | `omi-resilience-fallbacks` | Fallback rates, sync/pusher SLOs, gateway ticket tier — see `backend/docs/runbooks/resilience-dashboards.md` |

### Dashboard Summary

| Category | Count | Source | Version-controlled |
|----------|------:|--------|--------------------|
| Bundled (kube-prometheus-stack) | 28 | Helm chart sidecar | Yes (via chart defaults) |
| Custom (Omi-specific) | 18 | Exported from Grafana UI | Yes — `dashboards/` directory |

All 18 custom dashboards are exported to `dashboards/` as provisioning-ready JSON (`.id` and `.version` stripped). The K8s Node Metrics dashboard (`your_custom_uid_X0dfg`) is a community import bundled with the chart and not separately exported.

## Developer Guide

### Adding Metrics to a New Service

**Option A: ServiceMonitor (preferred)**

Add to your service's Helm chart:

1. A metrics `Service` exposing the metrics port:
```yaml
# templates/service-metrics.yaml
{{- if .Values.metrics.enabled }}
apiVersion: v1
kind: Service
metadata:
  name: {{ include "myservice.fullname" . }}-metrics
  labels:
    {{- include "myservice.labels" . | nindent 4 }}
spec:
  type: ClusterIP
  ports:
    - port: {{ .Values.metrics.port }}
      targetPort: {{ .Values.metrics.port }}
      protocol: TCP
      name: metrics
  selector:
    {{- include "myservice.selectorLabels" . | nindent 4 }}
{{- end }}
```

2. A `ServiceMonitor`:
```yaml
# templates/servicemonitor.yaml
{{- if and .Values.metrics.enabled .Values.metrics.serviceMonitor.enabled }}
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: {{ include "myservice.fullname" . }}
  labels:
    {{- include "myservice.labels" . | nindent 4 }}
    {{- with .Values.metrics.serviceMonitor.labels }}
    {{- toYaml . | nindent 4 }}
    {{- end }}
spec:
  selector:
    matchLabels:
      {{- include "myservice.selectorLabels" . | nindent 6 }}
  endpoints:
    - port: metrics
      path: /metrics
      interval: {{ .Values.metrics.serviceMonitor.interval | default "15s" }}
{{- end }}
```

3. Values:
```yaml
metrics:
  enabled: true
  port: 9091
  serviceMonitor:
    enabled: true
    interval: "15s"
    labels:
      release: prod-omi-kube-prometheus-stack  # must match Prometheus serviceMonitorSelector
```

The `release` label must match the Prometheus instance's `serviceMonitorSelector`. Use `prod-omi-kube-prometheus-stack` for prod, `dev-kube-prometheus-stack` for dev.

**Option B: Pod annotations**

Add to your chart's values:
```yaml
podAnnotations:
  prometheus.io/scrape: "true"
  prometheus.io/port: "8080"
  prometheus.io/path: "/metrics"
```

Then add a scrape job to `kube-prometheus-stack/{env}_omi_monitoring_values.yaml` under `prometheus.prometheusSpec.additionalScrapeConfigs`. Use backend-listen or pusher as a template. If the metrics endpoint requires auth, mount the `metrics-scrape-token` secret.

### Adding HPA Custom Metrics

To scale a deployment on a custom Prometheus metric:

1. Add the metric rule to `prometheus-adapter/{env}_omi_prometheus_adapter.yaml`:
```yaml
rules:
  external:
    - name:
        as: "myservice_custom_metric"
      seriesQuery: 'my_prometheus_metric{namespace!=""}'
      metricsQuery: 'avg(my_prometheus_metric{<<.LabelMatchers>>})'
      resources:
        overrides:
          namespace: { resource: "namespace" }
```

2. Apply with Helm (prod requires the reconciliation/render review below first):
```bash
helm -n {env}-omi-monitoring upgrade --install {env}-omi-prometheus-adapter \
  prometheus-community/prometheus-adapter \
  -f prometheus-adapter/{env}_omi_prometheus_adapter.yaml
```

3. Verify the metric is exposed:
```bash
# For External metrics (namespace-scoped, most common):
kubectl get --raw "/apis/external.metrics.k8s.io/v1beta1/namespaces/{env}-omi-backend/myservice_custom_metric"

# For Pods metrics (pod-scoped, used by parakeet):
kubectl get --raw "/apis/custom.metrics.k8s.io/v1beta1/namespaces/{env}-omi-backend/pods/*/myservice_pod_metric"
```

4. Reference in your HPA:
```yaml
# External metric (namespace-scoped):
metrics:
  - type: External
    external:
      metric:
        name: myservice_custom_metric
      target:
        type: Value
        value: "70"

# Pods metric (per-pod average):
metrics:
  - type: Pods
    pods:
      metric:
        name: myservice_pod_metric
      target:
        type: AverageValue
        averageValue: "25"
```

**Parakeet adapter rules:** The five rules in the parakeet chart's
`values.yaml` under `prometheus-adapter.rules` are mirrored in the cluster-wide
**production** adapter values (three custom/Pods rules and two external rules).
Keep both sources in sync; dev values need their own reconciliation before
using these metrics. The parakeet sub-chart adapter is disabled
(`prometheus-adapter.enabled: false`) to avoid a second adapter conflicting
with the cluster-scoped APIService. The hermetic
`backend/tests/unit/test_monitoring_adapter_hpa_contract.py` renders prod
Parakeet, listen, pusher, VAD, diarizer and Deepgram HPAs and checks every
consumed Pods/External metric against the correct prod adapter rule list.

**Before any prod adapter upgrade**, follow the
[monitoring prerequisite](../../docs/runbooks/listen-stt-careful-rollout.md#monitoring-prerequisite-coordinator-only):
capture live config, Deployment and APIService objects read-only, render chart
4.14.2 locally and run `backend/scripts/diff_prod_adapter.py`. Reconcile any
missing live rules in a reviewed PR first. The only intended config difference
for #20418 is `listen_track!="canary"` in both listen connection queries. Review
all other object drift, including the manually created custom APIService's
missing Helm ownership, and verify the deployed Helm rollback manifest retains
all live rules. The linked prerequisite documents these remaining live HOLDs.
The prod NLLB external rule is intentionally absent: the live NLLB HPA uses CPU,
and adding a metric should be a separate reviewed change.

### Grafana Dashboards

Grafana: prod at `https://monitor.omi.me/`, dev at `https://monitor.omiapi.com/`. See "Current Dashboards" above for the full inventory.

#### Creating a New Dashboard

1. **Create in Grafana UI first** — build the dashboard in dev (`monitor.omiapi.com`), iterate until it works.

2. **Export the dashboard JSON:**
```bash
# Get a Grafana API token (Settings → API Keys → Add, role=Viewer)
export MONITOR_GRAFANA_TOKEN="your-token"
export GRAFANA_HOST="https://monitor.omiapi.com"  # dev first

# List dashboards to find the UID
curl -s -H "Authorization: Bearer $MONITOR_GRAFANA_TOKEN" \
  "$GRAFANA_HOST/api/search?type=dash-db" | jq '.[] | {title, uid}'

# Export a specific dashboard (strips runtime fields)
curl -s -H "Authorization: Bearer $MONITOR_GRAFANA_TOKEN" \
  "$GRAFANA_HOST/api/dashboards/uid/<UID>" | \
  jq '.dashboard | del(.id, .version)' > dashboards/<name>.json
```

3. **Add to version control:**
   - Save the JSON to `backend/charts/monitoring/dashboards/<name>.json`
   - Use a descriptive filename matching the dashboard title (e.g. `parakeet-asr-monitoring.json`)
   - Strip runtime fields: `.id`, `.version` (done by the `jq` command above)
   - Keep the `.uid` field — it links the repo copy to the live dashboard

4. **Import to Grafana** (if creating on a new/different instance):
```bash
# First, get or create the target folder (returns folderUid)
FOLDER_UID=$(curl -s -H "Authorization: Bearer $MONITOR_GRAFANA_TOKEN" \
  "$GRAFANA_HOST/api/folders" | jq -r '.[] | select(.title=="GKE") | .uid')

# Import with folder placement
curl -s -X POST -H "Authorization: Bearer $MONITOR_GRAFANA_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"dashboard\": $(cat dashboards/<folder>/<name>.json), \"folderUid\": \"$FOLDER_UID\", \"overwrite\": true}" \
  "$GRAFANA_HOST/api/dashboards/db"
```
   Without `folderUid`, the dashboard lands in General. See the folder UIDs in the "Current Dashboards" section above.

5. **Commit the JSON** and open a PR.

#### Updating an Existing Dashboard

1. Edit the dashboard in Grafana UI (dev first, then prod)
2. Sync back to the repo using the workflow below

#### Sync-Back Workflow: Grafana UI → Repo

When a dashboard is edited via the Grafana UI (emergency fixes, quick iterations), export it back to the repo:

```bash
# 1. Set up
export MONITOR_GRAFANA_TOKEN="your-token"
export GRAFANA_HOST="https://monitor.omi.me"  # or monitor.omiapi.com

# 2. Export the updated dashboard
DASHBOARD_UID="07e4c65f-ae79-414d-bf05-99468267d199"  # example: Parakeet ASR
curl -s -H "Authorization: Bearer $MONITOR_GRAFANA_TOKEN" \
  "$GRAFANA_HOST/api/dashboards/uid/$DASHBOARD_UID" | \
  jq '.dashboard | del(.id, .version)' > dashboards/parakeet-asr-monitoring.json

# 3. Review the diff
git diff dashboards/parakeet-asr-monitoring.json

# 4. Commit and PR
git add dashboards/parakeet-asr-monitoring.json
git commit -m "sync(monitoring): export parakeet dashboard from Grafana UI"
```

**Bulk sync (all 17 custom dashboards):**
```bash
export MONITOR_GRAFANA_TOKEN="your-token"
export GRAFANA_HOST="https://monitor.omi.me"

# UID → folder mapping (mirrors repo directory structure)
declare -A DASHBOARDS=(
  # general/
  ["57c2a5ea-c310-4401-ac72-54dbc6da4c7e"]="general"
  ["3e7c5f57-a1be-4175-81e6-1f0c7c28b9dd"]="general"
  ["07e4c65f-ae79-414d-bf05-99468267d199"]="general"
  # cloud-run/
  ["0253019b-c68a-4aef-a27d-6bb3408727fb"]="cloud-run"
  ["5be48038-a72b-4938-99ed-7a8747655294"]="cloud-run"
  ["8bf7bd3f-8dbc-4f86-a532-557bfac0d7ac"]="cloud-run"
  ["e736ab7d-d3e8-444f-a743-369b054def9e"]="cloud-run"
  # gke/
  ["855b2e16-c098-407a-85dc-dc9ce87698a9"]="gke"
  ["fedizdcosu1oga"]="gke"
  ["303b7396-ce6e-48ee-be24-9c157a710adf"]="gke"
  ["c758b698-01a0-4b5c-b58c-e81e4ff33ccd"]="gke"
  ["72cfe240-ae8c-4076-845e-c58e28f12d87"]="gke"
  # omi-services/
  ["5feac510-b391-48fc-9c4b-1b8dde4ab32a"]="omi-services"
  ["d2d782ef-f537-46b8-969d-f73561ec7d07"]="omi-services"
  ["59aa0de7-15c6-413f-acba-b7e99296ad75"]="omi-services"
  ["3714dbfa-114b-47a0-99ca-1a26354e792a"]="omi-services"
  ["omi-resilience-fallbacks"]="omi-services"
)

for uid in "${!DASHBOARDS[@]}"; do
  folder="${DASHBOARDS[$uid]}"
  mkdir -p "dashboards/$folder"
  slug=$(curl -s -H "Authorization: Bearer $MONITOR_GRAFANA_TOKEN" \
    "$GRAFANA_HOST/api/dashboards/uid/$uid" | \
    jq -r '.meta.slug // .dashboard.title' | tr ' /' '-' | tr '[:upper:]' '[:lower:]')
  curl -s -H "Authorization: Bearer $MONITOR_GRAFANA_TOKEN" \
    "$GRAFANA_HOST/api/dashboards/uid/$uid" | \
    jq '.dashboard | del(.id, .version)' > "dashboards/$folder/${slug}.json"
  echo "Exported: $folder/$slug ($uid)"
done
```

**Dev → Prod promotion:**
```bash
# Export from dev
export GRAFANA_HOST="https://monitor.omiapi.com"
curl -s -H "Authorization: Bearer $MONITOR_GRAFANA_TOKEN" \
  "$GRAFANA_HOST/api/dashboards/uid/<uid>" | \
  jq '.dashboard | del(.id, .version)' > dashboards/<folder>/<name>.json

# Import to prod with correct folder
FOLDER_UID="aev9igt5fwgsgc"  # example: GKE folder
curl -s -X POST -H "Authorization: Bearer $MONITOR_GRAFANA_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"dashboard\": $(cat dashboards/<folder>/<name>.json), \"folderUid\": \"$FOLDER_UID\", \"overwrite\": true}" \
  "https://monitor.omi.me/api/dashboards/db"
```

**Rules:**
- Export emergency production UI edits back to the repo before the next import
- Strip `.id` and `.version` — they are instance-specific
- Keep `.uid` — it prevents duplicate dashboards on import
- Emergency UI edits must be synced back to repo within the same day
- When syncing, check `git diff` to ensure only intended panels changed (Grafana may reorder JSON keys)

### Alert Rules

Alerting is configured through Grafana unified alerting (not Prometheus AlertManager rules directly). Alert screenshots are disabled: renders call back into Grafana and stalled it under load (2026-10-13). Notifications link to the dashboard panel instead.

Alert rules never query a log datasource (Cloud Logging or Loki) for raw lines. Each 60s tick re-scans raw lines, exceeds the 30s datasource timeout, drops evaluation ticks, and has twice loaded the alerting plane into 502s: 2026-10-13 via Cloud Logging (#21390) and 2026-10-14 via Loki (`{namespace="prod-omi-backend"}` regex scans; one rule alone failed 196 times in 3h). `test_live_alert_rules_never_query_log_datasources` rejects any unpaused rule that tries. Held rules stay paused via `metric-inventory.prod.json` `admission_holds`; re-admit only on a bounded counter (a Cloud Monitoring log-based metric or an exported Prometheus counter). The paused corrupted-stream rule's signal lives on `omi_listen_audio_decode_failures_total`, replaced by `omi-listen-audio-decode-failures`; the listen-429, ASGI-handshake and direct-OpenAI-quota signals have no counter yet — tracked in #21461.

The Loki values contain a legacy Alertmanager URL, but live Loki3.5.2 has no
configured notifier destination. Its empty URL has no discovery fallback; it
does not feed the retired in-cluster Alertmanager.

### Telegram notification quality

See [template, severity timing, examples and supervisor rollout](notifications/README.md).
Rules own direct notification timing; Helm does not provision the contact or template.

### Human-Impact Alert Contract

Grafana rules are operational runbook entries, not raw metric dumps. The split files in `alerts/*.json` are the
maintained sources; `alert-rules.json` is the canonical combined Grafana import. They must contain the same rules
with byte-for-byte equal objects when indexed by stable Grafana UID. The deterministic monitoring contract test checks
both exports, including duplicate UIDs, before a change can land.

Pusher release workflows additionally call `verify_pusher_live_alert_route.py`
before publishing or promoting an image. The protected `MONITOR_GRAFANA_TOKEN`
secret (repo-scoped for dest `monitor.omiapi.com`, `prod` environment-scoped
for `monitor.omi.me`) must be able to read provisioned alert rules, datasource
health and queries, and contact points. Do not reuse the retired TV-instance
credential here. The default invocation is the
Pusher release gate: it fails closed unless the committed memory-admission
and capture-outcome pager set is live and unpaused, Prometheus reports healthy,
both Pusher and backend-listen have a non-terminating scrape target and every such target is up, and the
exact Telegram receiver exists with resolve notifications enabled. A target is terminating only when
`kube_pod_deletion_timestamp` matches its namespace and pod; pusher and backend-listen share that join
because both scrape jobs label `namespace`/`pod` and both Deployments drain for 120s plus a 15s preStop.
A missing job, or a down pod whose deletion timestamp is absent or unconfirmed, still fails the gate.
When every required target is already up, unconfirmed kube-state-metrics data does not fail the gate.
The check does not use `max(up)` and does not treat phase Running as terminating. After each
rollout it additionally requires all three finalization telemetry families from
both jobs; zero-valued labeled failure children are initialized at process
startup so absence is unambiguously a source failure. Production repeats this
check after rollout so an hours-long release cannot finish on stale evidence.
It never prints contact-point settings or token material.

The same script can classify every committed rule in `alerts/*.json` against
live Grafana provisioning (`--mode fleet`). That run prints committed-but-absent,
live-but-uncommitted, present-but-paused, and present-but-divergent UIDs. Default
`--fail-on none` reports drift without failing; `--fail-on gated` fails only on
UIDs listed in `live-alert-gate.json`. The monitoring workflow uses `--mode
import` to upsert, by stable UID (POST when absent, PUT when present), the
committed live-STT allowlist, the two Redis cache connection rules
(`omi-redis-cache-conn-warn`/`page` from `resilience.json`), and every UID in
`live-alert-gate.json`, including the finalization rules in `alerts/resilience.json`.
Production upserts the datasource canaries and reads them back before any
KeepLast business rule is written. Development writes the same gated UIDs with
`execErrState` Error and does not install canaries. Grafana-assigned query
defaults (`queryType` `""`, `model.intervalMs` `1000`, `model.maxDataPoints`
`43200`) do not count as drift when the committed node omits them; a different
value still fails. The import verifies each rule's `alert_identity` and Telegram
receiver and confirms that receiver exists with resolve notifications enabled;
it never deletes or pauses other rules. It then runs `--mode fleet --alert-set live-stt
--fail-on gated`, which covers the canaries and every gated UID. The `live-stt` verification scope includes those Redis rules and the gated finalization rules, and fails closed
when any of them is absent, paused, or divergent. They are Grafana-managed alerts,
not PrometheusRule CRDs. Their `component="other"` selector matches the shared
fallback bucket for `redis_cache`; cache-write children are initialized at zero.
The token is read from a mode-0600 file and
neither token material nor contact-point settings are logged. Split-vs-combined
equality in unit tests is not evidence a rule is live; only the workflow's
token-backed fleet verification proves that.

Every rule carries these notification fields:

| Field | Purpose |
|---|---|
| `labels.alert_identity` | Stable Grafana rule UID for deduplication and cross-export matching. |
| `labels.component` | Static affected Omi component. |
| `labels.impact` | One of `infrastructure`, `product`, or `user-experience`. |
| `annotations.summary` | A short human description of the condition. |
| `annotations.user_impact` | What an Omi user may experience; state uncertainty when impact is only potential. |
| `annotations.scope` | The bounded service or user path covered by the signal. |
| `annotations.verification` | The next evidence to confirm before intervention. |
| `annotations.safe_next_action` | The reversible, documented operator action after verification. |

The tiers describe evidence, not paging severity:

- `infrastructure`: capacity, readiness, resource, or scrape signals. They may warn before a user is affected.
- `product`: evidence that an Omi service capability may fail, be delayed, or be unavailable.
- `user-experience`: observed degradation of a real Omi user path.

Product and user-experience rules must use production, real-traffic evidence. Do not treat synthetic checks, load tests,
staging traffic, or an inferred proxy metric as proof of user impact. Infrastructure rules may use service-health metrics,
but their `user_impact` annotation must make potential impact clear rather than claim a confirmed user outage.

Never place raw provider responses, exception text, stack traces, or dynamic Grafana error output in these annotations.
Keep the message human-readable and direct the operator to the linked dashboard for bounded verification. Do not change
Grafana credentials, contact points, or routing configuration while adding a rule.

### Silent-Failure Alerts

Status codes and request counts cannot express every production failure. Four rules exist
specifically for failures that stay green on every other signal, and are documented together in
[`silent-failure-detection.md`](../../docs/runbooks/silent-failure-detection.md):

| Rule | Catches |
|---|---|
| `omi-capture-finalization-memory-fence` | The first real finalization rejected by a missing, disabled, or invalid canonical-memory runtime fence; zero is the only safe rate. |
| `omi-llm-gateway-invalid-requests` | Requests rejected during validation, **before** a route is selected. These are counted by `llm_gateway_request_rejections_total` and never reach `llm_gateway_requests_total`, so the affected lane keeps reporting 100% success. |
| `omi-llm-gateway-lane-failure-ratio` | A lane failing more than a quarter of its real requests over an hour. |
| `omi-llm-gateway-lane-zero-success` | A lane with attempts but no successful request in six hours. The `or ... * 0` zero-fill is required: a lane that has never succeeded has no `outcome="success"` series, so a plain ratio produces no series and no alert. |
| `omi-journey-signal-dead` | A journey counter that stopped reporting while the platform is demonstrably serving traffic. Every real-traffic journey rule assumes its counter is scraped; when that breaks, the rule goes quiet rather than failing loudly. |

Thresholds on these rules are set from measured production distributions, not intuition, and the
measurement belongs in the rule's `threshold` annotation and in the runbook.

A rule must not be added for a signal that is not yet ingested. The Cloud Run bridge now ingests
`journey="chat_response"`; `omi-journey-signal-dead` covers it with a chat-agent traffic gate.
[Proposed journey SLOs](./SLOS.md) record measured ingestion, targets and backtests; sync/upload
remains withheld until a valid terminal-outcome pair is ingested.

Parakeet stream-capacity alerts use the existing `parakeet_active_streams` gauge divided by ready Parakeet replicas:

```promql
sum(parakeet_active_streams{container="parakeet", namespace="prod-omi-backend"})
  / clamp_min(sum(kube_deployment_status_replicas_ready{
      deployment="prod-omi-parakeet", namespace="prod-omi-backend"}), 1)
```

This avoids a cluster-total threshold that would become misleading as HPA replica count changes. The warning threshold is
15 streams per ready replica for five minutes and the critical threshold is 20 for two minutes, both below the known
approximately 25–30 stream per-replica capability. No-data is healthy for these capacity rules: absent metrics are not
evidence of saturation. Operator response is in
[`parakeet-stream-capacity.md`](../../docs/runbooks/parakeet-stream-capacity.md).

## Dashboard & Metrics Lifecycle

### Approach: repo definitions with explicit production apply

Prototype dashboards in the development UI, export reviewed JSON, and merge it before production apply. Split alert files and the combined export must match. Emergency production UI changes must be exported before the next import; source equality is checked locally and live definition drift is checked through the API.

```
Create/edit dashboard in Grafana UI
        ↓
    Export JSON via API
        ↓
    Commit to dashboards/<folder>/<name>.json
        ↓
    PR review + merge
```

**Restore flow** (new cluster, disaster recovery, dev→prod promotion):
```
Read JSON from repo → Import via Grafana API → Dashboard is live
```

### Directory Structure

```
backend/charts/monitoring/
├── dashboards/                          # Grafana dashboard JSON (source of truth)
│   ├── general/                         # Matches Grafana "General" folder
│   │   ├── backend-api-monitoring-v1.json
│   │   ├── backend-api-monitoring-v2.json
│   │   └── parakeet-asr-monitoring.json
│   ├── cloud-run/                       # Matches Grafana "Cloud Run" folder
│   │   ├── backend.json
│   │   ├── backend-integration.json
│   │   ├── backend-sync.json
│   │   └── plugins.json
│   ├── gke/                             # Matches Grafana "GKE" folder
│   │   ├── backend-listen.json
│   │   ├── diarizer.json
│   │   ├── pusher.json
│   │   └── vad.json
│   └── omi-services/                    # Matches Grafana "Omi Services" folder
│       ├── cloud-armor-denied-requests.json
│       ├── cloud-run-services-logs.json
│       ├── global-external-alb.json
│       ├── omi-kubernetes-events.json
│       └── resilience-fallbacks.json
├── alerts/                              # (proposed) PrometheusRule or Grafana alert YAML
│   └── ...
├── kube-prometheus-stack/               # existing
├── prometheus-adapter/                  # existing
├── alloy/                               # existing
├── loki/                                # existing
├── prometheus-stackdriver-exporter/     # existing
└── README.md                            # this file
```

### When to Update

**Same-PR rule:** When a PR adds, renames, or removes Prometheus metrics from application code, the PR should also update:
1. The prometheus-adapter rules (if the metric drives HPA)
2. The service's metrics contract (see below)
3. Update the Grafana dashboard in the UI, then export and commit the JSON in the same PR (or a follow-up PR filed as an issue before merging)

### Sync Cadence

- After any dashboard edit in Grafana UI: export and commit within the same day
- Periodic bulk sync: run the bulk export script (see "Sync-Back Workflow" in Developer Guide) to catch any missed UI edits
- Before major infra changes (cluster migration, Helm upgrades): verify repo JSONs match live dashboards

### Alert Rules as Code

Grafana is the production alert plane. Maintain `alerts/*.json` and the identical
combined `alert-rules.json`; do not add native Prometheus alerts. Production Helm
values disable chart alerting groups while preserving all 81 recording rules.
The in-cluster Alertmanager is disabled: its only proven producer was the native
Prometheus alert path removed here, and Loki has no notifier destination. It had
no PVC or silences at the2026-10-15 audit. Grafana's embedded notification manager
and Telegram/Instatus routes remain independent. Generated external-Alertmanager
datasource provisioning is disabled; an existing unused SQLite entry is retained
until its exact live organization and ownership are checked. No datasource pruning
or persistent-store deletion occurs.

Three datasource canaries cover local Prometheus, Cloud Monitoring and GMP, with
`execErrState=Alerting` and `noDataState=Alerting`, routed directly to Telegram.
Business rules use `KeepLast` on query errors, preserving existing no-data policy
and any firing state. Four active rules retain their fingerprinted admission debt
and `Error` policy; these still produce extra datasource-error alerts until their
missing/unsupported metrics and pending-period debt are resolved. No claim of
exactly one page per outage is made while those exceptions remain.

The Cloud Logging plugin does not support Grafana-managed alerting. A synthetic
raw-log alert would be a permanent error, not a health canary; use bounded
log-based metrics through Cloud Monitoring for alert signals. Four paused Loki definitions are retired from source; manual live retirement and
Cloud Logging presentation acceptance follow [LOG_CONSOLIDATION.md](LOG_CONSOLIDATION.md). The external deadman covers
Grafana availability independently; it cannot prove query-path or delivery health.

### Metrics Contract

`omi_stt_stream_close_total{provider,reason}` pre-creates 55 zero-valued children:
the four bounded providers plus the `unknown` fallback, crossed with the eleven
bounded close reasons in `utils/stt/stream_close.py`. Initialization runs on that
module's import (including direct Soniox users) and beside the connect initializer
in `utils/stt/streaming.py`. It is idempotent and never resets a count. A zero
must be scraped before a close for `increase()` to observe the first event;
events before the first scrape still cannot be recovered by this initialization.

`tests/unit/test_monitoring_stt_metric_zero_init.py` checks every Prometheus
expression in `alerts/*.json` against the metrics defined in `utils/metrics.py`
and `llm_gateway/gateway/metrics.py`. Gauges and unlabelled metrics qualify;
labelled counters and histograms must expose startup children or have an explicit
one-line reason in `DECLARED_SPARSE`. The allowlist records existing debt and
must shrink as initialization is added. Exporter/GPU/other service registries and
full selector coverage are outside this family-level contract; stream-close
selector coverage has its own unit test.

The backend-listen fleet-health write counters use closed labels:
`omi_stt_fleet_health_write_attempted_total{write_path,kind}` counts each logical
write passed to the scheduler, including writes dropped by its bounds;
`omi_stt_fleet_health_write_written_total` counts only after Redis acknowledges
a commit, and
`omi_stt_fleet_health_write_dropped_total{write_path,kind,reason}` records bounded
drop reasons. `write_path` is `transcript_result`, `cost_routing_result`, or
`cost_bench`; `kind` is `result` or `bench`; `reason` is `redis_backoff`,
`identity_changed`, `identity_changed_after_commit`, `redis_error`,
`loop_unavailable`, `in_flight_limit`, `background_schedule_error`, or
`cross_thread_schedule_error`. The finalization
`listen_finalization_summary_last_success_timestamp_seconds` gauge is registered
only after a successful Firestore summary, so absence means this process has not
yet confirmed the summary.

Each service that exposes Prometheus metrics should document them alongside its ServiceMonitor or in its chart's values comments. Minimum contract:

| Field | Example |
|-------|---------|
| Metric name | `parakeet_active_streams` |
| Type | Gauge |
| Labels | `namespace`, `pod` |
| Unit | connections |
| Used by | parakeet HPA, GPU dashboard |

This ensures dashboard authors and HPA configs stay in sync with the application. When a metric is renamed or removed, the contract makes it clear what downstream consumers need updating.

### Staleness Detection

Periodically audit dashboards for references to metrics that no longer exist:

1. Export all dashboard JSON from Grafana
2. Extract all PromQL metric names from the JSON
3. Query Prometheus for each metric: `count({__name__="metric_name"})` — zero means the metric is gone
4. Flag dashboards with dead metrics for cleanup

This can be scripted and run as a periodic check or pre-merge CI step once dashboards are in the repo.

## Helm Upgrade Commands

Run from `backend/charts/monitoring/`. Ensure repos are added first:
```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update
```

```bash
PROD_CONTEXT=gke_based-hardware_us-central1_prod-omi-gke
DEV_CONTEXT=gke_based-hardware-dev_us-central1_dev-omi-gke
```

**Prod** (release names use `prod-omi-` prefix):
```bash
# kube-prometheus-stack. The stats-proxy hash is not in the values file; leaving it
# out drops Grafana's annotation and restarts Grafana. The grafana-stats-proxy
# ConfigMap must already match stats_proxy.py (see grafana/README.md).
helm upgrade prod-omi-kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --version 75.15.1 \
  --namespace prod-omi-monitoring \
  --kube-context gke_based-hardware_us-central1_prod-omi-gke \
  --reset-values --skip-crds \
  --values kube-prometheus-stack/prod_omi_monitoring_values.yaml \
  --set-string "grafana.podAnnotations.omi-stats-proxy-sha256=$(shasum -a 256 grafana/stats_proxy.py | cut -d' ' -f1)" \
  --wait --timeout 10m

# prometheus-adapter: complete the linked reconciliation/render review first.
helm upgrade prod-omi-prometheus-adapter prometheus-community/prometheus-adapter \
  --version 4.14.2 --namespace prod-omi-monitoring --kube-context "$PROD_CONTEXT" \
  --values prometheus-adapter/prod_omi_prometheus_adapter.yaml \
  --atomic --wait --timeout 10m

# Loki
helm -n prod-omi-monitoring --kube-context "$PROD_CONTEXT" upgrade --install prod-omi-loki \
  grafana/loki \
  -f loki/prod_omi_loki_values.yaml

# Alloy (k8s-monitoring) — release name is prod-omi-alloy (not prod-omi-k8s-monitoring)
helm -n prod-omi-monitoring --kube-context "$PROD_CONTEXT" upgrade --install prod-omi-alloy \
  grafana/k8s-monitoring \
  -f alloy/prod_omi_k8s_monitoring_values.yml

# Stackdriver exporter
helm -n prod-omi-monitoring --kube-context "$PROD_CONTEXT" upgrade --install prod-omi-prometheus-stackdriver-exporter \
  prometheus-community/prometheus-stackdriver-exporter \
  -f prometheus-stackdriver-exporter/prod_omi_stackdriver_exporter.yaml

# Isolated Cloud Run application-metrics bridge
helm -n prod-omi-monitoring --kube-context "$PROD_CONTEXT" upgrade --install prod-omi-cloud-run-metrics-exporter \
  prometheus-community/prometheus-stackdriver-exporter \
  -f prometheus-stackdriver-exporter/prod_omi_cloud_run_metrics_exporter.yaml

# Consumed families from the Cloud Run sync services (same job, same service account)
helm -n prod-omi-monitoring --kube-context "$PROD_CONTEXT" upgrade --install prod-omi-cloud-run-sync-metrics-exporter \
  prometheus-community/prometheus-stackdriver-exporter \
  -f prometheus-stackdriver-exporter/prod_sync_omi_cloud_run_metrics_exporter.yaml
```

**Apply monitoring-stack changes off-peak.** A stack rollout restarts the
Prometheus pod, which replays its WAL (~700k–980k head series) before serving;
during replay the adapter serves stale custom metrics and the
pusher/listen/parakeet/VAD/diarizer HPAs freeze (2026-10-14: pusher deploys
also failed Grafana alert provisioning while evaluation was backed up). The
rollout also carries whatever main carries beyond the values change: the
2026-10-14 rollout ships #21448's `diarizer-batch-metrics` scrape job and
adapter rule, which are inert until batch pods exist (no
`prod-omi-diarizer-batch` pods run yet), and the Loki values change rolls the
Loki read path onto its new requests.

### Production kube-prometheus-stack review and rollback

The production values file is the source for the Prometheus CR: 10d retention,
1 CPU / 2Gi memory requests, 2 CPU / 8Gi memory limits, and a 100Gi
`standard-rwo` claim. The CPU limit stays at 2 deliberately (2026-10-14
review): Prometheus load is sustained, not bursty — 1.5–2.2 cores across 14h
with the node pinned near its 1930m allocatable, 0% CFS throttling, and the
apparent ~2.9-core spikes were an artifact of kubelet scrapes timing out
mid-sample. A lower cap would throttle evaluation of the already
timeout-prone Prometheus-backed rules (`omi-stt-fallback-leg-dead`,
`omi-stt-leg-lifecycle-gap`) and stall the adapter's custom-metrics reads
behind every HPA. The 2026-10-14 starvation fix is requests, not a lower
limit: Grafana (250m), the operator (50m) and the adapter (100m, adapter
values file) carry explicit requests, and the Loki read path carries modest
requests in `loki/prod_omi_loki_values.yaml` (ingester/querier 50m,
index-gateway/ruler 20m each) with the node arithmetic in that file. The
2-vCPU pool itself is undersized for ~592k head series — the durable fix is
the pool resize runbook below. The values file does not drop `app_build`; the
backend now emits the fixed `unknown` value, so that extra label does not help
bound cardinality and dropping it would blank the fixed value.

Before an upgrade, render the pinned chart with the same API capabilities as
the cluster, then diff the normal (non-hook) resources. The EndpointSlice API
capability matters: the chart conditionally adds its operator RBAC rule for
that API. This command supplies the current cluster's server version and that
resource capability explicitly:

```bash
PROD_CONTEXT=gke_based-hardware_us-central1_prod-omi-gke
DEV_CONTEXT=gke_based-hardware-dev_us-central1_dev-omi-gke
PROD_NAMESPACE=prod-omi-monitoring
PROD_RELEASE=prod-omi-kube-prometheus-stack
SERVER_VERSION=$(kubectl --context "$PROD_CONTEXT" version -o json | jq -r '.serverVersion.gitVersion')

helm template "$PROD_RELEASE" prometheus-community/kube-prometheus-stack \
  --version 75.15.1 \
  --namespace "$PROD_NAMESPACE" \
  --kube-context "$PROD_CONTEXT" \
  --kube-version "$SERVER_VERSION" \
  --api-versions discovery.k8s.io/v1/EndpointSlice \
  --skip-crds --no-hooks \
  --values kube-prometheus-stack/prod_omi_monitoring_values.yaml \
  | kubectl diff --context "$PROD_CONTEXT" -f -
```

This is a read-only preflight: `helm template` renders locally and
`kubectl diff` compares the rendered objects without applying them. Re-run it
against live state before every release and inspect anything it prints: the
diff must contain exactly the object changes the values change intended
(after the 2026-10-14 requests change: the Grafana/operator resource requests,
and nothing else). An empty diff means there is no Kubernetes manifest change
to apply; do not create a Helm revision just to sync already-matching values.

`--skip-crds` is required for upgrades. The chart's ten Prometheus Operator
CRDs are not updated by Helm during an upgrade; review a CRD migration as a
separate operation. `--no-hooks` excludes the admission create/patch Jobs and
their hook-only RBAC objects from `kubectl diff`. Helm runs those Jobs as
pre/post-upgrade hooks and removes successful Jobs per their hook delete
policy. Do not apply rendered CRDs or manage those Jobs with `kubectl apply`.

Helm rollback creates a new revision. Never roll back to a hard-coded
revision number: immediately before an apply, record the revision the release
is on (`helm history "$PROD_RELEASE" --namespace "$PROD_NAMESPACE"
--kube-context "$PROD_CONTEXT"` — the highest deployed revision), and roll
back to that recorded revision. The 2026-10-14 baseline (revision 14 at the
time) is already several intentional changes behind live: rolling back to it
would also revert #21306, #21389, #21358 and #21409. #21389 is the
screenshots-off fix — reverting it turns alert screenshots back on and
recreates the 2026-10-13 Grafana 502s.

```bash
helm rollback "$PROD_RELEASE" <pre-apply-revision> \
  --namespace "$PROD_NAMESPACE" \
  --kube-context "$PROD_CONTEXT" \
  --wait --timeout 10m
```

#### Prometheus replica placement and acceptance

The 2026-10-15 read-only inventory found two `e2-highmem-4` monitoring nodes,
both in `us-central1-a`. Each has about 28Gi allocatable memory; observed usage
was about 4Gi/8Gi and Prometheus used about 3.6Gi with an 8Gi limit. Values request
two replicas, require different hostnames, prefer different zones, and keep one
replica available during voluntary evictions. The existing 100Gi `standard-rwo`
PVC is zonal to `us-central1-a`; replica 1 gets its own retained claim. Existing
80GB retention-size and 10-day retention are preserved.

Stage 1 pins the existing Service to replica 0 while the new TSDB warms.
A separate unpinned self-monitor Service exposes both replicas and both ports.
When restoring the native query Service, remove both temporary Service entries
(`prometheusWarmupService` and `prometheusSelfMonitorService`) while preserving
all other extra manifests. The workflow waits for operator reconciliation and
checks both Ready pods, node separation and independent Bound PVCs; Helm wait
alone cannot establish these conditions. Start the warm-up clock only after
both replicas are ready and their self-scrape targets are healthy.
Current alert sources include seven-day lookbacks; readiness alone is not
query parity. After at least seven days and accepted per-replica alert-query
comparisons, a separate change restores the native Service selector. Full
10-day dashboard history requires ten days. Only after unpinning does this
tolerate one pod/node loss. It does not survive loss of zone a. Required zone separation needs an eligible monitoring
node in another zone before changing the preference to a requirement. No PVC
migration/deletion or pool expansion is included. Recheck node capacity and
placement before apply; these are dated measurements, not deployment receipts.

Decide zone capacity before replica1's first claim binding. With only zone-a
nodes, its standard-rwo claim will also bind in a; adding zone-b nodes later
cannot move that disk. Cross-zone adoption then requires a separately reviewed
retained-claim migration/replacement. Prefer zone-b capacity and required zone
anti-affinity before the first replica1 rollout if zone HA is required.

Grafana and the HPA adapter retain the existing Prometheus ClusterIP. After
unpinning it selects ready replicas and balances TCP connections; keep-alive can pin a client to one
replica, and a failed in-flight request is not retried by the Service. No query
fans out to both replicas, so no Thanos deduplication is needed for this setup.
The replicas scrape independently and do not share a TSDB.

Both exporters collect inline on each scrape. Two Prometheus replicas mean two
Cloud Monitoring reads per scrape interval: the Stackdriver change reduces the
aggregate request cadence from 1/s to 2/min, while Cloud Run bridge reads double
at unchanged 60s cadence. Measure actual ListTimeSeries units before claiming
savings; the GMP cutover removes that remaining bridge cost.

Before apply, record the live Helm revision with a parent identity allowed to
read Helm release Secrets and compare the complete pinned-chart manifest with
live objects. The read-only lane cannot inspect Helm release history. Existing
default-value drift must be reconciled or explicitly preserved before applying
`--reset-values`; a values-only diff is insufficient. After both replicas are
ready and query history accepted, parent must authorize any single-replica restart exercise, observe rule
health and HPA API responses throughout it, and retain the new PVC on rollback.

**Dev** (note: kube-prometheus-stack release name is `dev-kube-prometheus-stack`, not `dev-omi-kube-prometheus-stack`):
```bash
helm -n dev-omi-monitoring --kube-context "$DEV_CONTEXT" upgrade --install dev-kube-prometheus-stack \
  prometheus-community/kube-prometheus-stack \
  -f kube-prometheus-stack/dev_omi_monitoring_values.yaml

helm -n dev-omi-monitoring --kube-context "$DEV_CONTEXT" upgrade --install dev-omi-prometheus-adapter \
  prometheus-community/prometheus-adapter \
  -f prometheus-adapter/dev_omi_prometheus_adapter.yaml

helm -n dev-omi-monitoring --kube-context "$DEV_CONTEXT" upgrade --install dev-omi-loki \
  grafana/loki \
  -f loki/dev_omi_loki_values.yaml

helm -n dev-omi-monitoring --kube-context "$DEV_CONTEXT" upgrade --install dev-omi-alloy \
  grafana/k8s-monitoring \
  -f alloy/dev_omi_k8s_monitoring_values.yml

helm -n dev-omi-monitoring --kube-context "$DEV_CONTEXT" upgrade --install dev-omi-prometheus-stackdriver-exporter \
  prometheus-community/prometheus-stackdriver-exporter \
  -f prometheus-stackdriver-exporter/dev_omi_stackdriver_exporter.yaml

helm -n dev-omi-monitoring --kube-context "$DEV_CONTEXT" upgrade --install dev-omi-cloud-run-metrics-exporter \
  prometheus-community/prometheus-stackdriver-exporter \
  -f prometheus-stackdriver-exporter/dev_omi_cloud_run_metrics_exporter.yaml

helm -n dev-omi-monitoring --kube-context "$DEV_CONTEXT" upgrade --install dev-omi-cloud-run-sync-metrics-exporter \
  prometheus-community/prometheus-stackdriver-exporter \
  -f prometheus-stackdriver-exporter/dev_sync_omi_cloud_run_metrics_exporter.yaml
```

## Troubleshooting

**Many scrape targets down at once (2026-10-14: 109 of 286, including 34 stale kubelet endpoints):**
while the prometheus operator crash-loops it cannot reconcile ServiceMonitor/PodMonitor
objects, so their targets go stale faster than they age out. Expected to clear on its own
once the operator stays running; verify `up` converges upward before chasing individual targets.

**Metric not appearing in Prometheus:**
1. Check the pod exposes `/metrics` and returns valid Prometheus format
2. For ServiceMonitor: verify the `release` label matches Prometheus's `serviceMonitorSelector`
3. For annotations: verify the scrape job exists in `additionalScrapeConfigs`
4. Check Prometheus targets: access Prometheus UI → Status → Targets to see scrape status. To query the metric: Grafana → Explore → Prometheus datasource → metric name

**HPA shows `<unknown>` for custom metric:**
1. Verify the metric exists: `kubectl get --raw "/apis/external.metrics.k8s.io/v1beta1/namespaces/{ns}/{metric}"`
2. Check prometheus-adapter logs: `kubectl logs -n {env}-omi-monitoring -l app.kubernetes.io/name=prometheus-adapter`
3. Verify the adapter rule's `seriesQuery` matches actual Prometheus series
4. Only ONE prometheus-adapter can own the `v1beta1.custom.metrics.k8s.io` APIService — never deploy a second instance

**Logs not appearing in Loki:**
1. Verify Alloy is running: `kubectl get pods -n {env}-omi-monitoring -l app.kubernetes.io/name=alloy-logs`
2. Check Alloy collects from the right namespace (configured in Alloy values)
3. Verify Loki gateway is reachable and basic auth secret exists
4. Query in Grafana Explore with Loki datasource: `{namespace="{env}-omi-backend"}`

## Alert admission backtest

`backend/scripts/alert_backtest.py` is read-only and uses only the Python standard
library. `--lint` runs offline in the existing local/CI checks manifest and the
monitoring unit suite. Regenerate the committed metric-name snapshot with:

```bash
source ~/.local/bin/gcp-agent-env.sh ro-prod
python3 backend/scripts/alert_backtest.py \
  --kube-context gke_based-hardware_us-central1_prod-omi-gke --refresh-inventory
python3 backend/scripts/alert_backtest.py --lint
python3 backend/scripts/alert_backtest.py \
  --kube-context gke_based-hardware_us-central1_prod-omi-gke \
  --uids omi-parakeet-stream-capacity-warning --json-output /tmp/backtest.json \
  --markdown-output /tmp/backtest.md
```

Direct Prometheus access uses `--prom-url`. `--rules` accepts exported JSON files;
without it all `alerts/*.json` are loaded. The replay uses retained history up to
10 days, with the rule's `interval` or five minutes. `--step` must be at least a
minute. Sampling can miss shorter incidents, and the initial pending state is
unknown; episodes at the window edges are censored. No deployment is authorized
by a quiet replay alone: inspect current raw selector counts and traffic gates.

The evaluator preserves series labels, reduces each range frame separately,
interprets math without Python `eval`, and implements threshold/classic nodes.
Range datasource queries use their declared frame resolution and one bounded
request per evaluation (potentially slow); resample, ambiguous joins and unknown
nodes fail closed as `needs-human`. Non-Prometheus rules require separate evidence.
`NoData` and `KeepLast` intervals are reported as unknown, requiring human review;
DatasourceNoData routing is not simulated. Long lookbacks near the retention edge
are flagged as incomplete; review the warmed portion separately. Pages/week counts instance starts,
not Telegram messages or repeat notifications. Noise means over 5% firing time;
flapping means at least ten episodes no longer than two steps or ten minutes.

Lint checks inventory names, dependency/condition structure, finite thresholds,
boolean threshold units, reduction/math support and pending periods on rate,
ratio or average queries. `legacy_debt` pins unchanged pre-existing findings to
a rule hash; any rule edit invalidates the exception. It is debt, never deployment
approval. The snapshot is historical presence, not proof of current ingestion.
`declared_metrics` records source-backed metric names that are not yet in that
historical snapshot; offline lint accepts them, while a live replay still checks
the actual Prometheus series and fails if they have not been deployed or scraped.
Explicit `admission_holds` require a rule to stay paused until its reviewed hold
is removed. Live replay exits nonzero on dead, noisy or unproven results.
The CI gate catches structural regressions; live threshold calibration remains
a required admission review before an operator sends a rule to Telegram.

## Fleet telemetry

`dashboards/omi-services/fleet-telemetry.json` uses plain job-agnostic PromQL
for client summary deltas, rejection rates, startup p95, and server upload
admission. The [fleet contract](../../telemetry/README.md) owns schema, label
bounds, cardinality and deploy acceptance. The shared backend deploy attaches
GMP to sync, backfill and integration final candidates before readiness and
promotion; all retain `omi_.*` and rendered runtime-env verification. Empty
client panels are expected until the client emitters ship; this is not a
PostHog parity or reader-cutover receipt.
