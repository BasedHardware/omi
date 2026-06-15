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

Grafana: prod at `https://monitor.omi.me/`, dev at `https://monitor.omiapi.com/`. Dashboards are currently managed via the Grafana UI (not version-controlled).

**To export a dashboard as JSON:**
```bash
# List all dashboards
curl -s -H "Authorization: Bearer $GRAFANA_TOKEN" \
  https://monitor.omi.me/api/search?type=dash-db | jq '.[].uid'

# Export a specific dashboard
curl -s -H "Authorization: Bearer $GRAFANA_TOKEN" \
  https://monitor.omi.me/api/dashboards/uid/<UID> | jq '.dashboard' > dashboard.json
```

**To provision a dashboard from JSON**, add it to a ConfigMap and reference it in the Grafana sidecar config within `kube-prometheus-stack` values.

### Alert Rules

Alerting is configured through Grafana unified alerting (not Prometheus AlertManager rules directly). Alert screenshots are enabled via the Grafana image renderer.

Loki ruler is configured to send alerts to AlertManager at `http://prod-kube-prometheus-stack-alertmanager:9093`.

## Dashboard & Metrics Lifecycle

### Source of Truth: Repo-First

Dashboards, alert rules, and metrics definitions should live in the repo and deploy to Grafana via provisioning. This makes changes reviewable, auditable, and reproducible.

```
Developer edits dashboard JSON in repo
        ↓
    PR review
        ↓
    Merge to main
        ↓
    Helm upgrade deploys to Grafana (sidecar provisioning)
```

Emergency edits in the Grafana UI are acceptable but must be exported back to the repo within the same day.

### Directory Structure

```
backend/charts/monitoring/
├── dashboards/                          # (proposed) Grafana dashboard JSON files
│   ├── backend-listen-overview.json
│   ├── pusher-overview.json
│   ├── parakeet-gpu.json
│   └── ...
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
1. The relevant dashboard JSON (if the metric is visualized)
2. The prometheus-adapter rules (if the metric drives HPA)
3. The service's metrics contract (see below)

If the dashboard update is complex, a follow-up PR is acceptable but must be filed as an issue before merging the metrics PR.

### Review Process

- Dashboard and alert changes go through PR review like any other code change
- No silent Grafana UI edits for permanent changes
- Reviewer checks: metric names match app code, PromQL is correct, thresholds are reasonable

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

# Alloy (k8s-monitoring)
helm -n prod-omi-monitoring upgrade --install prod-omi-k8s-monitoring \
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

helm -n dev-omi-monitoring upgrade --install dev-omi-k8s-monitoring \
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
