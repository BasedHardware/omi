# Monitoring Stack

Prometheus + Grafana + Loki observability stack for the Omi backend on GKE.

## Architecture

```
┌───────────────────────────────────────────────────────────────────────────┐
│  GKE Cluster (prod-omi-gke / dev-omi-gke)                               │
│                                                                           │
│  ┌──────────────┐   scrape    ┌─────────────┐   query   ┌────────────┐  │
│  │ Pod metrics   │──────────►│  Prometheus   │◄─────────│  Grafana   │  │
│  │ (app /metrics)│           │  (10d, 50Gi)  │          │ prod: monitor│ │
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

## Components

| Component | Chart | Purpose | Namespace |
|-----------|-------|---------|-----------|
| **Prometheus** | `kube-prometheus-stack` | Metrics collection, 10d retention, 50Gi storage | `{env}-omi-monitoring` |
| **Grafana** | `kube-prometheus-stack` | Dashboards and alerting (prod: `monitor.omi.me`, dev: `monitor.omiapi.com`) | `{env}-omi-monitoring` |
| **Alertmanager** | `kube-prometheus-stack` | Alert routing and notification | `{env}-omi-monitoring` |
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

Prometheus scrapes metrics through two mechanisms:

**1. ServiceMonitor (recommended for new services)**

Used by: parakeet.

The service chart includes a `ServiceMonitor` CRD that Prometheus auto-discovers. This is the preferred approach — no changes to the monitoring chart needed.

**2. Pod annotations + additionalScrapeConfigs**

Used by: backend-listen, pusher, deepgram engine, GPU metrics, Stackdriver.

Pods set annotations (`prometheus.io/scrape: "true"`, `prometheus.io/port`, `prometheus.io/path`) and a matching `additionalScrapeConfigs` entry in `kube-prometheus-stack` values defines the scrape job.

Backend-listen and pusher require bearer token auth via the `metrics-scrape-token` secret.

### Custom Scrape Jobs (prod)

These are the `additionalScrapeConfigs` and ServiceMonitor targets. Built-in kube-prometheus-stack targets (kube-state-metrics, node-exporter, kubelet, Alertmanager, Prometheus itself) are not listed here.

| Job | Target | Interval | Auth |
|-----|--------|----------|------|
| `backend-listen-metrics` | backend-listen pods `/metrics:8080` | 15s | Bearer token |
| `pusher-metrics` | pusher pods `/metrics:8080` | 15s | Bearer token |
| `dg_engine_metrics` | DG engine pods in `prod-omi-dg-self-hosted` | 2s | None |
| `gpu-metrics` | all pods in `gke-managed-system` (includes DCGM exporter) | 1s | None |
| `prometheus-stackdriver-metrics` | Stackdriver exporter in `prod-omi-monitoring` | 1s | None |
| ServiceMonitor: `parakeet` | parakeet pods `/metrics:9091` | 15s | None |

### Log Pipeline

```
Pod stdout/stderr → Alloy (kubernetesApi method) → Loki gateway (basic auth) → GCS
                                                                                 ↓
                                                                    Grafana Explore (LogQL)
```

Alloy collects from `{env}-omi-backend` namespace only. Labels kept: `app_kubernetes_io_name`, `container`, `instance`, `job`, `level`, `namespace`, `service_name`, `pod` (structured metadata).

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

Parakeet adapter rules are defined in the parakeet chart's `values.yaml` but must be merged into the cluster-wide adapter (see below).

### Stackdriver Exporter

Bridges GCP Cloud Monitoring (load balancer metrics) into Prometheus. Currently exports:
- `loadbalancing.googleapis.com/https/backend_request_count` — filtered to backend-listen NEG
- `loadbalancing.googleapis.com/https/internal/backend_latencies` — internal LB latency histograms

Uses Workload Identity (`prod-omi-prom-stackdriver-gsa`).

## Values Files

Each component has dev and prod values:

| Component | Dev | Prod |
|-----------|-----|------|
| kube-prometheus-stack | `kube-prometheus-stack/dev_omi_monitoring_values.yaml` | `kube-prometheus-stack/prod_omi_monitoring_values.yaml` |
| prometheus-adapter | `prometheus-adapter/dev_omi_prometheus_adapter.yaml` | `prometheus-adapter/prod_omi_prometheus_adapter.yaml` |
| Alloy | `alloy/dev_omi_k8s_monitoring_values.yml` | `alloy/prod_omi_k8s_monitoring_values.yml` |
| Loki | `loki/dev_omi_loki_values.yaml` | `loki/prod_omi_loki_values.yaml` |
| Stackdriver exporter | `prometheus-stackdriver-exporter/dev_omi_stackdriver_exporter.yaml` | `prometheus-stackdriver-exporter/prod_omi_stackdriver_exporter.yaml` |
| Grafana ALB cert | `kube-prometheus-stack/dev_omi_grafana_alb_cert.yaml` | `kube-prometheus-stack/prod_omi_grafana_alb_cert.yaml` |

## Current Dashboards

45 dashboards on prod Grafana (`monitor.omi.me`), organized by folder.

### General (32) — kube-prometheus-stack defaults + custom

Most are bundled with kube-prometheus-stack and auto-provisioned. Custom dashboards are noted.

| Dashboard | UID | Tags | Notes |
|-----------|-----|------|-------|
| Alertmanager / Overview | `alertmanager-overview` | `alertmanager-mixin` | Bundled |
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

### Omi Services (4) — cross-cutting dashboards

Folder: `Omi Services` (folder UID: `betdycdziadc0e`)

| Dashboard | UID | Notes |
|-----------|-----|-------|
| Cloud Armor denied requests | `5feac510-b391-48fc-9c4b-1b8dde4ab32a` | WAF/security denied traffic |
| Cloud Run Services - Logs | `d2d782ef-f537-46b8-969d-f73561ec7d07` | Aggregated Cloud Run logs view |
| Global External ALB | `59aa0de7-15c6-413f-acba-b7e99296ad75` | External load balancer metrics |
| Omi Kubernetes Events | `3714dbfa-114b-47a0-99ca-1a26354e792a` | K8s event stream (OOM kills, pod evictions) |

### Dashboard Summary

| Category | Count | Source | Version-controlled |
|----------|------:|--------|--------------------|
| Bundled (kube-prometheus-stack) | 28 | Helm chart sidecar | Yes (via chart defaults) |
| Custom (Omi-specific) | 16 | Exported from Grafana UI | Yes — `dashboards/` directory |

All 16 custom dashboards are exported to `dashboards/` as provisioning-ready JSON (`.id` and `.version` stripped). The K8s Node Metrics dashboard (`your_custom_uid_X0dfg`) is a community import bundled with the chart and not separately exported.

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
      targetPort: {{ .Values.service.port }}
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

2. Apply with Helm:
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

**Parakeet adapter rules:** The parakeet chart defines adapter rules in its own `values.yaml` under `prometheus-adapter.rules`, but these are NOT yet present in the cluster-wide adapter config (`prometheus-adapter/` values in this directory). They must be manually merged into `prometheus-adapter/{env}_omi_prometheus_adapter.yaml` before parakeet HPA can use them. The parakeet sub-chart adapter is disabled (`prometheus-adapter.enabled: false`) to avoid deploying a second adapter that would conflict with the cluster-scoped APIService.

### Grafana Dashboards

Grafana: prod at `https://monitor.omi.me/`, dev at `https://monitor.omiapi.com/`. See "Current Dashboards" above for the full inventory.

#### Creating a New Dashboard

1. **Create in Grafana UI first** — build the dashboard in dev (`monitor.omiapi.com`), iterate until it works.

2. **Export the dashboard JSON:**
```bash
# Get a Grafana API token (Settings → API Keys → Add, role=Viewer)
export GRAFANA_TOKEN="your-token"
export GRAFANA_HOST="https://monitor.omiapi.com"  # dev first

# List dashboards to find the UID
curl -s -H "Authorization: Bearer $GRAFANA_TOKEN" \
  "$GRAFANA_HOST/api/search?type=dash-db" | jq '.[] | {title, uid}'

# Export a specific dashboard (strips runtime fields)
curl -s -H "Authorization: Bearer $GRAFANA_TOKEN" \
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
# Import via Grafana API
curl -s -X POST -H "Authorization: Bearer $GRAFANA_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"dashboard\": $(cat dashboards/<folder>/<name>.json), \"overwrite\": true}" \
  "$GRAFANA_HOST/api/dashboards/db"
```

5. **Commit the JSON** and open a PR.

#### Updating an Existing Dashboard

1. Edit the dashboard in Grafana UI (dev first, then prod)
2. Sync back to the repo using the workflow below

#### Sync-Back Workflow: Grafana UI → Repo

When a dashboard is edited via the Grafana UI (emergency fixes, quick iterations), export it back to the repo:

```bash
# 1. Set up
export GRAFANA_TOKEN="your-token"
export GRAFANA_HOST="https://monitor.omi.me"  # or monitor.omiapi.com

# 2. Export the updated dashboard
DASHBOARD_UID="07e4c65f-ae79-414d-bf05-99468267d199"  # example: Parakeet ASR
curl -s -H "Authorization: Bearer $GRAFANA_TOKEN" \
  "$GRAFANA_HOST/api/dashboards/uid/$DASHBOARD_UID" | \
  jq '.dashboard | del(.id, .version)' > dashboards/parakeet-asr-monitoring.json

# 3. Review the diff
git diff dashboards/parakeet-asr-monitoring.json

# 4. Commit and PR
git add dashboards/parakeet-asr-monitoring.json
git commit -m "sync(monitoring): export parakeet dashboard from Grafana UI"
```

**Bulk sync (all custom dashboards):**
```bash
export GRAFANA_TOKEN="your-token"
export GRAFANA_HOST="https://monitor.omi.me"

# Custom dashboard UIDs (from Current Dashboards section)
CUSTOM_UIDS=(
  "57c2a5ea-c310-4401-ac72-54dbc6da4c7e"  # Backend API Monitoring
  "3e7c5f57-a1be-4175-81e6-1f0c7c28b9dd"  # Backend API Monitoring (dup)
  "07e4c65f-ae79-414d-bf05-99468267d199"  # Parakeet ASR Monitoring
  "your_custom_uid_X0dfg"                  # K8s Node Metrics
  "0253019b-c68a-4aef-a27d-6bb3408727fb"  # Cloud Run: Backend
  "5be48038-a72b-4938-99ed-7a8747655294"  # Cloud Run: Backend-integration
  "8bf7bd3f-8dbc-4f86-a532-557bfac0d7ac"  # Cloud Run: Backend-sync
  "e736ab7d-d3e8-444f-a743-369b054def9e"  # Cloud Run: Plugins
  "855b2e16-c098-407a-85dc-dc9ce87698a9"  # GKE: Backend-listen
  "fedizdcosu1oga"                         # GKE: Deepgram self-hosted
  "303b7396-ce6e-48ee-be24-9c157a710adf"  # GKE: Diarizer
  "c758b698-01a0-4b5c-b58c-e81e4ff33ccd"  # GKE: Pusher
  "72cfe240-ae8c-4076-845e-c58e28f12d87"  # GKE: VAD
  "5feac510-b391-48fc-9c4b-1b8dde4ab32a"  # Omi: Cloud Armor
  "d2d782ef-f537-46b8-969d-f73561ec7d07"  # Omi: Cloud Run Logs
  "59aa0de7-15c6-413f-acba-b7e99296ad75"  # Omi: Global External ALB
  "3714dbfa-114b-47a0-99ca-1a26354e792a"  # Omi: K8s Events
)

mkdir -p dashboards
for uid in "${CUSTOM_UIDS[@]}"; do
  slug=$(curl -s -H "Authorization: Bearer $GRAFANA_TOKEN" \
    "$GRAFANA_HOST/api/dashboards/uid/$uid" | \
    jq -r '.meta.slug // .dashboard.title' | tr ' /' '-' | tr '[:upper:]' '[:lower:]')
  curl -s -H "Authorization: Bearer $GRAFANA_TOKEN" \
    "$GRAFANA_HOST/api/dashboards/uid/$uid" | \
    jq '.dashboard | del(.id, .version)' > "dashboards/${slug}.json"
  echo "Exported: $slug ($uid)"
done
```

**Dev → Prod promotion:**
```bash
# Export from dev
GRAFANA_HOST="https://monitor.omiapi.com" DASHBOARD_UID="<uid>" \
  # ... export as above ...

# Import to prod (update UID + datasource references if needed)
curl -s -X POST -H "Authorization: Bearer $GRAFANA_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"dashboard\": $(cat dashboards/<name>.json), \"overwrite\": true}" \
  "https://monitor.omi.me/api/dashboards/db"
```

**Rules:**
- Always export from prod to repo (prod is the live source until full provisioning is in place)
- Strip `.id` and `.version` — they are instance-specific
- Keep `.uid` — it prevents duplicate dashboards on import
- Emergency UI edits must be synced back to repo within the same day
- When syncing, check `git diff` to ensure only intended panels changed (Grafana may reorder JSON keys)

### Alert Rules

Alerting is configured through Grafana unified alerting (not Prometheus AlertManager rules directly). Alert screenshots are enabled via the Grafana image renderer.

Loki ruler is configured to send alerts to AlertManager at `http://prod-kube-prometheus-stack-alertmanager:9093`.

## Dashboard & Metrics Lifecycle

### Approach: UI-First, Git-Backed

Dashboards are created and edited directly in the Grafana UI — it's purpose-built for visual iteration. Git serves as backup, version control, and the restore source for disaster recovery or new cluster setup.

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
│   │   ├── deepgram-self-hosted.json
│   │   ├── diarizer.json
│   │   ├── pusher.json
│   │   └── vad.json
│   └── omi-services/                    # Matches Grafana "Omi Services" folder
│       ├── cloud-armor-denied-requests.json
│       ├── cloud-run-services-logs.json
│       ├── global-external-alb.json
│       └── omi-kubernetes-events.json
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

Move alert rules from Grafana UI into version-controlled config. Two options:

**Option A: PrometheusRule CRDs (recommended for metric-based alerts)**
```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: parakeet-alerts
  labels:
    release: prod-omi-kube-prometheus-stack
spec:
  groups:
    - name: parakeet
      rules:
        - alert: ParakeetHighGPUUtil
          expr: avg(DCGM_FI_DEV_GPU_UTIL{container="parakeet"}) > 90
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "Parakeet GPU utilization above 90% for 5m"
```

**Option B: Grafana provisioning YAML (for log-based or multi-datasource alerts)**

Place alert YAML in the `alerts/` directory and configure Grafana sidecar to load from it.

### Metrics Contract

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

**Prod** (release names use `prod-omi-` prefix):
```bash
# kube-prometheus-stack
helm -n prod-omi-monitoring upgrade --install prod-omi-kube-prometheus-stack \
  prometheus-community/kube-prometheus-stack \
  -f kube-prometheus-stack/prod_omi_monitoring_values.yaml

# prometheus-adapter
helm -n prod-omi-monitoring upgrade --install prod-omi-prometheus-adapter \
  prometheus-community/prometheus-adapter \
  -f prometheus-adapter/prod_omi_prometheus_adapter.yaml

# Loki
helm -n prod-omi-monitoring upgrade --install prod-omi-loki \
  grafana/loki \
  -f loki/prod_omi_loki_values.yaml

# Alloy (k8s-monitoring) — release name is prod-omi-alloy (not prod-omi-k8s-monitoring)
helm -n prod-omi-monitoring upgrade --install prod-omi-alloy \
  grafana/k8s-monitoring \
  -f alloy/prod_omi_k8s_monitoring_values.yml

# Stackdriver exporter
helm -n prod-omi-monitoring upgrade --install prod-omi-prometheus-stackdriver-exporter \
  prometheus-community/prometheus-stackdriver-exporter \
  -f prometheus-stackdriver-exporter/prod_omi_stackdriver_exporter.yaml
```

**Dev** (note: kube-prometheus-stack release name is `dev-kube-prometheus-stack`, not `dev-omi-kube-prometheus-stack`):
```bash
helm -n dev-omi-monitoring upgrade --install dev-kube-prometheus-stack \
  prometheus-community/kube-prometheus-stack \
  -f kube-prometheus-stack/dev_omi_monitoring_values.yaml

helm -n dev-omi-monitoring upgrade --install dev-omi-prometheus-adapter \
  prometheus-community/prometheus-adapter \
  -f prometheus-adapter/dev_omi_prometheus_adapter.yaml

helm -n dev-omi-monitoring upgrade --install dev-omi-loki \
  grafana/loki \
  -f loki/dev_omi_loki_values.yaml

helm -n dev-omi-monitoring upgrade --install dev-omi-alloy \
  grafana/k8s-monitoring \
  -f alloy/dev_omi_k8s_monitoring_values.yml

helm -n dev-omi-monitoring upgrade --install dev-omi-prometheus-stackdriver-exporter \
  prometheus-community/prometheus-stackdriver-exporter \
  -f prometheus-stackdriver-exporter/dev_omi_stackdriver_exporter.yaml
```

## Troubleshooting

**Metric not appearing in Prometheus:**
1. Check the pod exposes `/metrics` and returns valid Prometheus format
2. For ServiceMonitor: verify the `release` label matches Prometheus's `serviceMonitorSelector`
3. For annotations: verify the scrape job exists in `additionalScrapeConfigs`
4. Check Prometheus targets: `https://monitor.omi.me/` → Explore → Prometheus datasource → metric name

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
