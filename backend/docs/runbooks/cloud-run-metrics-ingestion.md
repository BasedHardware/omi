# Cloud Run application metrics ingestion

## Decision

Send one scrape from every Cloud Run instance to Google Managed Service for Prometheus (GMP), then bridge the resulting Cloud Monitoring time series into the self-managed Prometheus that Grafana already uses:

```text
backend / desktop-backend process registry
  -> 127.0.0.1:9090/metrics
  -> Cloud Run GMP sidecar (one per instance, 30s + startup/shutdown scrape)
  -> Cloud Monitoring: prometheus.googleapis.com/omi_*
  -> isolated prometheus-stackdriver-exporter on GKE (Cloud Monitoring read every 30s)
  -> kube-prometheus-stack Prometheus (job=cloud-run-application-metrics)
  -> Grafana unified alerting -> Telegram
```

This is the only option considered here that preserves per-instance counters across Cloud Run autoscaling and ends in the existing Prometheus datasource. It cannot be verified end to end until the Cloud Run revisions and the new Helm release are deployed after merge.

## Evidence

Repository evidence:

- `backend/charts/monitoring/README.md` and the prod values define only GKE pod pulls plus the Stackdriver bridge. Before this change the exporter prefixes were only the two `loadbalancing.googleapis.com` metrics.
- `backend/routers/metrics.py` rejects a missing or wrong `METRICS_SECRET`. The main backend deploy currently binds that secret. `desktop_backend.py` did not mount the metrics router, and neither desktop Cloud Run workflow bound the secret.
- `backend/charts/monitoring/kube-prometheus-stack/*_omi_monitoring_values.yaml` scrape the existing Stackdriver exporter every second. Importing per-instance application series through that release would multiply Cloud Monitoring API reads unnecessarily, so this change adds a separate 30-second exporter.

Live evidence collected on 2026-08-21:

- `gcloud container clusters describe` reports `managedPrometheusConfig.enabled: true` for both `dev-omi-gke` and `prod-omi-gke`. Both clusters contain `gmp-system` and `gmp-public`; dev has a running operator and 10 managed collector pods, while prod has a running operator and 26 collectors.
- `gmp-public` contains the GKE-managed DCGM exporter and kube-state-metrics `ClusterPodMonitoring` resources in both environments. This proves the operator and Kubernetes discovery path are active, but those collectors discover Kubernetes targets, not Cloud Run instances.
- `backend` and `desktop-backend` each had one Cloud Run container with max scale 100. Backend had `METRICS_SECRET` and always-allocated CPU; desktop-backend had neither. A public URL scrape therefore cannot enumerate either service's instances.
- The Cloud Monitoring API already contained `prometheus.googleapis.com/*` descriptors from GKE's managed collector, proving GMP storage is active, but it contained zero `prometheus.googleapis.com/omi_*` descriptors.
- The live prod Stackdriver exporter is v0.18.0. Its deployed arguments contain only the two load-balancer prefixes from the repository values, and its GSA has `roles/monitoring.viewer`.
- Live Helm ownership is asymmetric: dev Prometheus is release `dev-kube-prometheus-stack`, while prod is `prod-omi-kube-prometheus-stack`; the existing exporters are `dev/prod-omi-prometheus-stackdriver-exporter`. The deployment workflow encodes these observed names instead of deriving a nonexistent dev release.
- Grafana's GSA has `roles/monitoring.viewer`, but the live provisioned datasource list contains only Prometheus and Alertmanager. A direct Cloud Monitoring datasource is possible but is not the requested Prometheus ingestion path.
- Both projects have the Run, Monitoring, Logging, and Secret Manager APIs enabled. Both Cloud Run services use the Compute Engine default service account; each runtime account has project-level `roles/secretmanager.secretAccessor`, and its current `roles/editor` includes `monitoring.timeSeries.create`. A future least-privilege service account must receive `roles/monitoring.metricWriter`, `roles/logging.logWriter`, and access to `cloud-run-gmp-config` explicitly.
- `cloud-run-gmp-config` does not exist in either project before this rollout. The deployment identity must be able to create the secret, add versions, and update its non-sensitive content-hash label; the helper creates it without printing its content.
- `gcloud run services replace --dry-run` accepted the patched live dev exports for both `backend` and `desktop-backend`, including gen2, 1-vCPU collector resources, probes, secret volume, explicit traffic, and multi-container dependency annotations. No revision or traffic mutation occurred.

Google documents the Cloud Run GMP sidecar as its recommended Prometheus path. It performs a scrape after startup and at shutdown, which matters for short-lived instances, and writes metrics as `prometheus.googleapis.com/<name>/<type>`. The sidecar's `RunMonitoring` schema does not support authorization headers. Sources:

- [Google: Use the Prometheus sidecar for Cloud Run](https://cloud.google.com/stackdriver/docs/managed-prometheus/cloudrun-sidecar)
- [GoogleCloudPlatform/run-gmp-sidecar RunMonitoring implementation](https://github.com/GoogleCloudPlatform/run-gmp-sidecar/blob/main/confgenerator/config.go)
- [prometheus-community/stackdriver_exporter naming and metric-type behavior](https://github.com/prometheus-community/stackdriver_exporter#readme)
- [Google Cloud Observability pricing](https://cloud.google.com/stackdriver/pricing)
- [Google: Configure Cloud Run CPU limits](https://cloud.google.com/run/docs/configuring/services/cpu)

## Why the sidecar scrapes port 9090

The public port 8080 `/metrics` route stays fail-closed with bearer authentication. The Google sidecar cannot add that bearer token because `RunMonitoring.ScrapeEndpoint` exposes port, scheme, path, params, proxy, interval, timeout, and metric relabeling, but no authorization field.

The application therefore starts a second Prometheus HTTP listener bound specifically to `127.0.0.1:9090` when `PROMETHEUS_SIDECAR_PORT=9090`. Cloud Run containers in one instance share a network namespace, so the collector can reach it. Cloud Run ingress cannot. This avoids weakening the public route or trusting proxy-derived client IPs.

`backend/deploy/cloud_run_gmp_sidecar.yaml` keeps only `omi_.*`, includes only the service metadata label (the per-instance label is mandatory), and sets scrape limits. The deploy helper pins the collector image by digest and the numeric Secret Manager config version by revision, uses 1 vCPU and 512 MiB, preserves existing containers and ingress settings, refuses a service whose traffic follows `latestRevision`, and creates the final sidecar revision at zero traffic. Candidate acceptance still happens before any traffic shift.

## Options considered

### Scrape the public Cloud Run URL from GKE — rejected

Cloud Run load balances each request to one arbitrary instance. A scrape sees one process registry, misses the others, and can jump between instances on successive scrapes. Counter rates and histogram populations become wrong as soon as the service has more than one instance. Authentication does not fix target discovery.

### Use the GKE managed collectors directly — rejected

GMP is enabled in both clusters, but its managed collectors discover GKE workloads through `PodMonitoring`. They cannot discover Cloud Run instance-local targets. GMP is still useful as the remote storage/export API when each Cloud Run instance runs its own sidecar.

### Cloud Run GMP sidecar, query Cloud Monitoring from Grafana — viable fallback

Grafana can provision its built-in Google Cloud Monitoring datasource, and the prod Grafana GSA already has read access. This removes the second exporter and preserves PromQL support in Cloud Monitoring. It does not put the series in the kube-prometheus-stack Prometheus, so existing Prometheus-only alert and recording-rule contracts would split across datasources. Use this fallback if Stackdriver exporter API cost or metric conversion proves unacceptable.

### Pushgateway — rejected

Pushgateway is intended for short-lived batch jobs, not autoscaled services. Instance grouping keys require deletion on shutdown, stale series survive crashes, and pushed cumulative counters do not have the same lifecycle semantics as per-instance Prometheus targets.

### Extend the existing 1-second Stackdriver exporter — rejected on cost, not capability

The exporter accepts `prometheus.googleapis.com/` prefixes and converts Cloud Monitoring cumulative metrics to Prometheus counters and distributions to histograms, reconstructing `_sum` as distribution mean multiplied by count. But it calls Cloud Monitoring on each Prometheus scrape. Adding many per-instance application series to the existing 1-second release would cause roughly 30 times the API reads of a 30-second bridge. The chosen implementation reuses the same chart, GSA, and monitored project in an isolated release.

### Dedicated isolated Stackdriver exporter — selected

The new release imports only `prometheus.googleapis.com/omi_*` and filters monitored resources to `cluster=__run__` with namespace `backend` or `desktop-backend`. The namespace disjunction must be written as `resource.labels.namespace=one_of("backend","desktop-backend")`: Cloud Monitoring rejects a filter that mixes `AND` with `OR` across `resource.labels` restrictions (`AND and OR cannot be mixed for 'resource.labels' restrictions`, HTTP 400), and the exporter absorbs that rejection per descriptor without ever going unready. It reuses the existing exporter Kubernetes service account, so no new Workload Identity binding is required. Prometheus scrapes it every 30 seconds. The original load-balancer exporter and its HPA-sensitive cadence are unchanged.

## Metric names are rewritten back at scrape time

The Stackdriver exporter renames everything it imports to
`stackdriver_<monitored resource>_<metric type>_<value type>`. Left alone,
`omi_journey_accepted_total` would arrive from Cloud Run as
`stackdriver_prometheus_target_prometheus_googleapis_com_omi_journey_accepted_total_counter`,
and every existing alert, recording rule, and dashboard would go on matching nothing while the
metrics were demonstrably flowing.

**Ingested-but-unmatched is the same outage as never-ingested.** It is what kept
`omi-journey-chat-fail` armed and unfirable through a 19-hour incident, and importing metrics under
names nothing queries would reproduce it in a new form.

The `cloud-run-application-metrics` job therefore rewrites `__name__` back to the plain form:

```yaml
metric_relabel_configs:
  - source_labels: [__name__]
    regex: "stackdriver_prometheus_target_prometheus_googleapis_com_(omi_.+?)_(counter|gauge|histogram|summary|untyped|unknown)(_bucket|_sum|_count)?"
    target_label: __name__
    replacement: "${1}${3}"
```

Group 3 preserves the `_bucket` / `_sum` / `_count` suffixes so histograms stay queryable, and the
non-greedy group 1 with full anchoring survives metric names that themselves contain a value-type
word. `test_monitoring_telemetry_contract.py` pins the regex and its recovered names in both
environments.

After the rewrite, a GKE-sourced and a Cloud Run-sourced `omi_journey_accepted_total` are the same
metric, told apart by their `service_name` label. That is deliberate: it means the existing alert
corpus works against Cloud Run traffic with no query changes.

### If the regex is wrong, you will be told

The exact exporter naming cannot be confirmed until the pipeline is live, so the rewrite is a
prediction. `omi-cloud-run-metric-names-unnormalized` fires when any un-normalized `stackdriver_*`
`omi_` series survives on this job:

```promql
count({job="cloud-run-application-metrics", __name__=~"stackdriver_.*_omi_.*"}) or vector(0)
```

Correct the regex and re-upgrade the release. **Do not** write alerts against the mangled names —
that hard-codes the defect into the alert corpus.

## Counter, histogram, and label semantics

Every Cloud Run instance produces a distinct mandatory `instance` series. Counter queries must aggregate rates, never sum raw counters across time:

```promql
sum by (service_name, journey, outcome) (
  rate(omi_client_journey_terminal_total[5m])
)
```

(The name above is the rewritten one. Query the plain `omi_*` names, not the exporter's.)

Confirm the exact normalized name in Prometheus before installing an alert; Stackdriver exporter builds names from `stackdriver`, monitored resource type, Cloud Monitoring metric type, and value type. It retains metric and monitored-resource labels. Cloud Monitoring distributions become Prometheus histograms; the exporter reconstructs `_sum` as distribution mean multiplied by count. Both bucket-based `histogram_quantile` and `_sum / _count` queries are available, but verify the normalized series names after deployment.

Do not add uid, conversation, request, revision, or configuration labels. `service_name`, bounded journey/outcome labels, and the required instance identity are sufficient. Revision/configuration target labels are explicitly disabled in the checked-in `RunMonitoring` config to avoid rollout-driven series churn.

## Cost and cardinality

There are three costs:

1. GMP ingestion: at a 30-second interval, `S` exported series across `I` average active instances produce approximately `86,400 * S * I` samples per 30-day month. At the documented first-tier $0.06/million samples, 100 series across 10 instances is about $5.18/month.
2. Cloud Monitoring reads: the isolated 30-second exporter reduces API series reads by about 30x compared with the existing 1-second exporter. Keep the `omi_` metric relabel and service filter narrow.
3. Cloud Run resources: the sidecar adds 1 vCPU and 512 MiB per active instance. Always-allocated CPU is already enabled for backend. This change enables it for desktop-backend because Google warns request-based CPU can miss low-QPS scrapes. Cloud Run requires at least 1 vCPU when gen2 and instance-based billing are used, so the collector cannot use a fractional 80m allocation. With prod min scale 1, desktop's main container and 1-vCPU sidecar are billed while idle; this reliability cost is material and must be reviewed against the Cloud Run billing report after rollout.

The 10,000-sample and 30-label scrape limits cap accidental explosions. A limit breach fails the scrape and should be treated as an observability incident, not raised without a label review.

## Deploy and verify

Run the focused repository contracts first:

```bash
cd backend
pytest -q tests/unit/test_attach_cloud_run_gmp_sidecar.py \
  tests/unit/test_metrics_sidecar_server.py \
  tests/unit/test_desktop_backend_cors.py \
  tests/unit/test_render_backend_runtime_env.py \
  tests/unit/test_backend_runtime_env_validator.py \
  tests/unit/test_monitoring_telemetry_contract.py \
  tests/unit/test_monitoring_alert_rule_contract.py \
  tests/unit/test_cloud_run_metrics_egress_workflow.py
python3 deploy/compose_runtime_env.py --check
```

After merge, platform deployment is still required; repository changes alone do not mutate Cloud Run or GKE. The repository now owns both halves instead of leaving Helm commands as an undocumented manual release:

- `.github/workflows/gcp_cloud_run_metrics_egress.yml` runs automatically for relevant changes on `main` and atomically installs the dev exporter plus the dev Prometheus scrape configuration. It uses the live release name `dev-kube-prometheus-stack`, not the failed historical `dev-omi-kube-prometheus-stack` release.
- Production is an explicit protected-environment dispatch from `main`. It atomically upgrades `prod-omi-cloud-run-metrics-exporter` and the live `prod-omi-kube-prometheus-stack` release with pinned chart versions.
- Both paths render first, install the isolated exporter before its scrape target, wait for Helm readiness, and verify the exporter Deployment and Service.

1. Confirm the automatic `Deploy Cloud Run Metrics Egress` development run succeeded after merge. If it must be retried, dispatch it from `main`:

```bash
gh workflow run gcp_cloud_run_metrics_egress.yml --ref main -f environment=development
```

2. Run the normal backend and desktop-backend deployment workflows in dev. They create or version `cloud-run-gmp-config` from the checked-in non-sensitive config, pin that numeric secret version into a two-container no-traffic candidate, and run the existing acceptance gates before promotion.
3. Confirm each Cloud Run revision has two containers without displaying environment values:

```bash
gcloud run services describe desktop-backend --project=based-hardware-dev --region=us-central1 --format='value(spec.template.spec.containers.name)'
gcloud run services describe backend --project=based-hardware-dev --region=us-central1 --format='value(spec.template.spec.containers.name)'
```

4. Confirm the collector has successful scrapes and no export errors:

```bash
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="desktop-backend" AND labels."run.googleapis.com/container_name"="collector"' \
  --project=based-hardware-dev --freshness=30m --limit=50
```

5. In Cloud Monitoring Metrics Explorer, use PromQL and query an idle, zero-initialized metric such as `omi_journey_accepted_total`. Confirm both `service_name="backend"` and `service_name="desktop-backend"` exist and instances are distinct.
6. Confirm data actually crossed the bridge. `up` is not that proof: it reports only that Prometheus reached the exporter's own `/metrics`, and it stayed 1 for 21 hours while every Cloud Monitoring query returned HTTP 400 and not one series was imported. Require all three, in this order:

```promql
up{job="cloud-run-application-metrics"}                                  # exporter reachable  — necessary, not sufficient
stackdriver_monitoring_last_scrape_error{job="cloud-run-application-metrics"}   # MUST be 0: the upstream query was accepted
count({job="cloud-run-application-metrics", __name__=~"omi_.*"})         # MUST be > 0: series arrived, under their plain names
```

Query the plain `omi_*` names, not the `stackdriver_prometheus_target_...` form. The scrape job rewrites `__name__` back to the plain name, so on a healthy deployment the mangled form returns zero — reading it as a health check inverts the signal. The mangled form is what `omi-cloud-run-metric-names-unnormalized` watches for, and it should be empty.

The target stays `coverage_status: declared` until both prod services serve the sidecar and a per-service freshness alert can be written against a real series.

7. Generate one known dev client journey, then confirm the corresponding counter increases in Cloud Monitoring and in kube-prometheus-stack after the one-minute exporter offset. Compare `sum(rate(...[5m]))` by service between both stores.
8. Dispatch the production metrics egress workflow from `main`, then deploy the prod Cloud Run revisions and repeat the checks before enabling any new Grafana alert:

```bash
gh workflow run gcp_cloud_run_metrics_egress.yml --ref main -f environment=prod
```

9. Confirm the public route remains protected without printing the token: unauthenticated and invalid-bearer requests to `/metrics` must return 401; only the loopback listener is unauthenticated.

Rollback Cloud Run traffic with the existing recovery workflows. Rolling back to a pre-sidecar revision removes new ingestion for that service but does not affect request serving. Roll back the monitoring changes with Helm rollback of both environment-specific releases; do not change the original load-balancer exporter.
