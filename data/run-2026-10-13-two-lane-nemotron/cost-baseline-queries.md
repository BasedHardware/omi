# Exact receipt queries

UTC window: 2026-10-07 inclusive to 2026-10-14 exclusive. Source: `905537e1a30b7fc6c3f64b574ac0d4102a9da7c4`.

Select `ro-prod`; all Kubernetes calls use `--context gke_based-hardware_us-central1_prod-omi-gke`. Prometheus uses the service proxy recorded below; hourly step is 3600 seconds.

## unit_cost

```sql
SELECT date, SUM(tx_sec)/3600 tx_hours, SUM(audio_pipeline_gcp) audio_cost,
SAFE_DIVIDE(SUM(audio_pipeline_gcp),SUM(tx_sec)/3600) cost_per_tx_hour,
LOGICAL_AND(inputs_settled) settled, COUNT(DISTINCT run_id) runs
FROM `based-hardware.omi_finops.unit_cost_user_day`
WHERE date >= DATE('2026-10-07') AND date < DATE('2026-10-14') GROUP BY date ORDER BY date
```

## allocated_components

```sql
SELECT date, component, method, SUM(usd) usd,
LOGICAL_AND(inputs_settled) settled FROM `based-hardware.omi_finops.unit_cost_daily`
WHERE date >= DATE('2026-10-07') AND date < DATE('2026-10-14') AND segment_type='total'
GROUP BY date,component,method ORDER BY date,component
```

## audio_reconciliation

```sql
WITH base AS (SELECT DATE(usage_start_time) date,
IF(project.id='based-hardware','prod','nonprod') scope,
CASE
  ---------------------------------------------------------------- one-off charges
  -- Injected from one_time_events.json by pull_gcp.py. Dated, resource-scoped rules only.
  -- These land in their own `one_time_*` component, are reported with method='one_time',
  -- and are excluded from every per-user allocation pool.
WHEN DATE(usage_start_time) BETWEEN '2026-09-04' AND '2026-09-09' AND sku.description LIKE '%Coldline Class A Operations%' AND IFNULL(resource.global_name,resource.name) LIKE '%private-cloud-sync%' THEN 'one_time_storage_lifecycle'
  ---------------------------------------------------------------- overhead
  WHEN service.description = 'BigQuery' THEN 'bigquery'

  ---------------------------------------------------------------- firestore
  WHEN sku.description = 'Cloud Firestore Read Ops' THEN 'firestore_reads'
  WHEN LOWER(sku.description) LIKE '%firestore%'
    OR service.description = 'Cloud Firestore'                     THEN 'firestore_other'

  ---------------------------------------------------------------- model serving
  -- 5-GSU gemini-flash flat reservation, ~$298/day net, unit = seconds
  WHEN sku.description LIKE 'Vertex AI: Provisioned Throughput%'   THEN 'vertex_pt_reservation'
  WHEN LOWER(sku.description) LIKE '%embedding%'
    OR LOWER(sku.description) LIKE '%embedcontent%'                THEN 'embeddings'
  WHEN service.description IN ('Vertex AI','Gemini API',
                               'Generative Language API',
                               'Vertex AI Search','Vertex AI Agent Builder')
    OR LOWER(sku.description) LIKE '%gemini%'
    OR LOWER(sku.description) LIKE '%generative%'                  THEN 'vertex_paygo'

  ---------------------------------------------------------------- simple service buckets
  WHEN service.description IN ('Translate','Cloud Translation')    THEN 'translate'
  WHEN service.description IN ('Cloud Logging','Cloud Monitoring','Cloud Trace',
                               'Stackdriver Logging','Stackdriver Monitoring',
                               'Cloud Profiler','Error Reporting')  THEN 'logging_monitoring'
  WHEN service.description = 'Cloud Pub/Sub'                        THEN 'pubsub'

  ---------------------------------------------------------------- storage (before network rule)
  WHEN service.description IN ('Cloud Storage','Storage Insights')
       AND ( IFNULL(resource.global_name, resource.name) LIKE '%/buckets/omi-private-cloud-sync%'
          OR IFNULL(resource.global_name, resource.name) LIKE '%/buckets/omi-dev-private-cloud-sync%'
          OR IFNULL(resource.global_name, resource.name) LIKE '%/buckets/syncing-local%' )
                                                                    THEN 'storage_audio'
  WHEN service.description IN ('Cloud Storage','Storage Insights')  THEN 'storage_other'

  ---------------------------------------------------------------- Cloud Run (before Compute Engine)
  WHEN IFNULL(resource.global_name, resource.name) LIKE '//run.googleapis.com/%/services/desktop-backend'
                                                                    THEN 'cloud_run_desktop_backend'
  WHEN IFNULL(resource.global_name, resource.name) LIKE '//run.googleapis.com/%'
    OR IFNULL(resource.global_name, resource.name) LIKE '//cloudfunctions.googleapis.com/%'
    OR service.description IN ('Cloud Run','Cloud Run Functions','Cloud Functions')
                                                                    THEN 'cloud_run_other'

  ---------------------------------------------------------------- network
  WHEN service.description IN ('Networking','Network Security','Cloud DNS',
                               'Network Topology','Cloud Load Balancing','Network Intelligence Center')
                                                                    THEN 'network'
  WHEN service.description = 'Compute Engine'
       AND ( sku.description LIKE 'Network%'
          OR sku.description LIKE '%Data Transfer%'
          OR sku.description LIKE '%External IP%'
          OR sku.description LIKE '%Forwarding Rule%'
          OR sku.description LIKE '%Load Balanc%' )                 THEN 'network'

  ---------------------------------------------------------------- ASR / STT GPU fleet
  WHEN REGEXP_CONTAINS(
         IFNULL((SELECT l.value FROM UNNEST(labels) l
                  WHERE l.key='goog-k8s-node-pool-name' LIMIT 1),''),
         r'(?i)parakeet|nllb|diariz|vad|(^|-)asr|hpfasr|deepgram|whisper|stt')
                                                                    THEN 'asr_gpu_fleet'
  WHEN service.description IN ('Compute Engine','Kubernetes Engine')
       AND ( LOWER(sku.description) LIKE '%gpu%'
          OR LOWER(sku.description) LIKE '%nvidia%'
          OR sku.description LIKE 'G2 Instance%' )                  THEN 'asr_gpu_fleet'

  ---------------------------------------------------------------- remaining compute
  WHEN service.description IN ('Compute Engine','Kubernetes Engine',
                               'Deep Learning VM','Container Registry Vulnerability Scanning')
                                                                    THEN 'gke_other_compute'

  ELSE 'other_gcp'
END component,
(SELECT l.value FROM UNNEST(labels) l WHERE l.key='goog-k8s-node-pool-name' LIMIT 1) pool,
cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c),0) net
FROM `based-hardware.gcp_billing_export.gcp_billing_export_resource_v1_01B287_9348DC_02D256` WHERE usage_start_time >= TIMESTAMP('2026-10-07') AND usage_start_time < TIMESTAMP('2026-10-14'))
SELECT date,scope,CASE WHEN REGEXP_CONTAINS(pool,r'^(backend-listen-pool|pusher-pool)')
AND component='gke_other_compute' THEN 'listen_pipeline_compute' ELSE component END component,
SUM(net) net FROM base WHERE component IN ('asr_gpu_fleet','storage_audio')
OR (component='gke_other_compute' AND REGEXP_CONTAINS(pool,r'^(backend-listen-pool|pusher-pool)'))
GROUP BY date,scope,component ORDER BY date,scope,component
```

## billing

```sql
WITH base AS (SELECT TIMESTAMP_TRUNC(usage_start_time,HOUR) hour,
service.description service, sku.description sku,
(SELECT l.value FROM UNNEST(labels) l WHERE l.key='goog-k8s-node-pool-name' LIMIT 1) pool,
IFNULL(resource.global_name,resource.name) resource,
cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c),0) net
FROM `based-hardware.gcp_billing_export.gcp_billing_export_resource_v1_01B287_9348DC_02D256` WHERE usage_start_time >= TIMESTAMP('2026-10-07')
AND usage_start_time < TIMESTAMP('2026-10-14') AND project.id='based-hardware')
SELECT hour, CASE
WHEN pool IS NOT NULL THEN CONCAT('pool:',pool)
WHEN REGEXP_CONTAINS(resource,r'//run.googleapis.com/.*/services/(backend-listen|backend-sync|pusher)$')
THEN CONCAT('run:',REGEXP_EXTRACT(resource,r'/services/([^/]+)$'))
WHEN service IN ('Cloud Storage','Storage Insights') AND REGEXP_CONTAINS(resource,r'/buckets/(omi-private-cloud-sync|syncing-local)') THEN 'gcs:audio'
WHEN service IN ('Cloud Storage','Storage Insights') THEN 'gcs:other'
ELSE CONCAT('unallocated:',service) END component,
SUM(net) net_cost FROM base GROUP BY hour,component ORDER BY hour,component
```

## hpa

```text
kubectl --context gke_based-hardware_us-central1_prod-omi-gke get hpa -n prod-omi-backend -o json (project spec only)
```

## pools

```text
gcloud container node-pools list --cluster=prod-omi-gke --region=us-central1 --format=json(name,locations,config.machineType,config.accelerators,config.spot,autoscaling)
```

## listen

```json
{
  "promql": "sum(max by(pod)(backend_listen_active_ws_connections{namespace=\"prod-omi-backend\"}))",
  "start": "2026-10-07",
  "end_exclusive": "2026-10-14",
  "step": 3600,
  "context": "gke_based-hardware_us-central1_prod-omi-gke",
  "proxy": "/api/v1/namespaces/prod-omi-monitoring/services/prod-omi-kube-prometheus-s-prometheus:9090/proxy/api/v1/"
}
```

## pusher

```json
{
  "promql": "sum(max by(pod)(pusher_active_ws_connections{namespace=\"prod-omi-backend\"}))",
  "start": "2026-10-07",
  "end_exclusive": "2026-10-14",
  "step": 3600,
  "context": "gke_based-hardware_us-central1_prod-omi-gke",
  "proxy": "/api/v1/namespaces/prod-omi-monitoring/services/prod-omi-kube-prometheus-s-prometheus:9090/proxy/api/v1/"
}
```

## nodes

```json
{
  "promql": "count by(pool)(max by(node,pool)(label_replace(kube_node_info,\"pool\",\"$1\",\"node\",\"gke-prod-omi-gke-(.*)-[a-z0-9]{8}-[a-z0-9]{4}\")))",
  "start": "2026-10-07",
  "end_exclusive": "2026-10-14",
  "step": 3600,
  "context": "gke_based-hardware_us-central1_prod-omi-gke",
  "proxy": "/api/v1/namespaces/prod-omi-monitoring/services/prod-omi-kube-prometheus-s-prometheus:9090/proxy/api/v1/"
}
```

## gpu_util

```json
{
  "promql": "avg by(pool)(max by(Hostname,UUID,pool)(label_replace(avg_over_time(DCGM_FI_DEV_GPU_UTIL[1h]),\"pool\",\"$1\",\"Hostname\",\"gke-prod-omi-gke-(.*)-[a-z0-9]{8}-[a-z0-9]{4}\")))",
  "start": "2026-10-07",
  "end_exclusive": "2026-10-14",
  "step": 3600,
  "context": "gke_based-hardware_us-central1_prod-omi-gke",
  "proxy": "/api/v1/namespaces/prod-omi-monitoring/services/prod-omi-kube-prometheus-s-prometheus:9090/proxy/api/v1/"
}
```

## gpu_memory_mib

```json
{
  "promql": "avg by(pool)(max by(Hostname,UUID,pool)(label_replace(avg_over_time(DCGM_FI_DEV_FB_USED[1h]),\"pool\",\"$1\",\"Hostname\",\"gke-prod-omi-gke-(.*)-[a-z0-9]{8}-[a-z0-9]{4}\")))",
  "start": "2026-10-07",
  "end_exclusive": "2026-10-14",
  "step": 3600,
  "context": "gke_based-hardware_us-central1_prod-omi-gke",
  "proxy": "/api/v1/namespaces/prod-omi-monitoring/services/prod-omi-kube-prometheus-s-prometheus:9090/proxy/api/v1/"
}
```

## gpu_coverage

```json
{
  "promql": "count by(pool)(max by(Hostname,UUID,pool)(label_replace(DCGM_FI_DEV_GPU_UTIL,\"pool\",\"$1\",\"Hostname\",\"gke-prod-omi-gke-(.*)-[a-z0-9]{8}-[a-z0-9]{4}\")))",
  "start": "2026-10-07",
  "end_exclusive": "2026-10-14",
  "step": 3600,
  "context": "gke_based-hardware_us-central1_prod-omi-gke",
  "proxy": "/api/v1/namespaces/prod-omi-monitoring/services/prod-omi-kube-prometheus-s-prometheus:9090/proxy/api/v1/"
}
```

## parakeet_streams

```json
{
  "promql": "sum(max by(pod)(parakeet_active_streams{namespace=\"prod-omi-backend\"}))",
  "start": "2026-10-07",
  "end_exclusive": "2026-10-14",
  "step": 3600,
  "context": "gke_based-hardware_us-central1_prod-omi-gke",
  "proxy": "/api/v1/namespaces/prod-omi-monitoring/services/prod-omi-kube-prometheus-s-prometheus:9090/proxy/api/v1/"
}
```

## parakeet_p95

```json
{
  "promql": "histogram_quantile(0.95,sum by(le)(rate(parakeet_request_duration_seconds_bucket{namespace=\"prod-omi-backend\"}[5m])))",
  "start": "2026-10-07",
  "end_exclusive": "2026-10-14",
  "step": 3600,
  "context": "gke_based-hardware_us-central1_prod-omi-gke",
  "proxy": "/api/v1/namespaces/prod-omi-monitoring/services/prod-omi-kube-prometheus-s-prometheus:9090/proxy/api/v1/"
}
```

## metric_names

```json
{
  "promql": "count by(__name__)({__name__=~\"parakeet_.*(duration|queue|latency).*\"})",
  "start": "2026-10-07",
  "end_exclusive": "2026-10-14",
  "step": 3600,
  "context": "gke_based-hardware_us-central1_prod-omi-gke",
  "proxy": "/api/v1/namespaces/prod-omi-monitoring/services/prod-omi-kube-prometheus-s-prometheus:9090/proxy/api/v1/"
}
```

## asr_service_rtf

```json
{
  "promql": "sum(increase(parakeet_request_duration_seconds_sum{namespace=\"prod-omi-backend\",exported_endpoint=~\"v1_transcribe|v2_transcribe\"}[7d])) / sum(increase(parakeet_audio_duration_seconds_sum{namespace=\"prod-omi-backend\"}[7d]))",
  "start": "2026-10-07",
  "end_exclusive": "2026-10-14",
  "step": 3600,
  "context": "gke_based-hardware_us-central1_prod-omi-gke",
  "proxy": "/api/v1/namespaces/prod-omi-monitoring/services/prod-omi-kube-prometheus-s-prometheus:9090/proxy/api/v1/"
}
```

## asr_audio_seconds

```json
{
  "promql": "sum(increase(parakeet_audio_duration_seconds_sum{namespace=\"prod-omi-backend\"}[7d]))",
  "start": "2026-10-07",
  "end_exclusive": "2026-10-14",
  "step": 3600,
  "context": "gke_based-hardware_us-central1_prod-omi-gke",
  "proxy": "/api/v1/namespaces/prod-omi-monitoring/services/prod-omi-kube-prometheus-s-prometheus:9090/proxy/api/v1/"
}
```

## window_post_p95

```json
{
  "promql": "histogram_quantile(0.95,sum by(le)(rate(omi_stt_window_post_seconds_bucket{namespace=\"prod-omi-backend\"}[1h])))",
  "start": "2026-10-07",
  "end_exclusive": "2026-10-14",
  "step": 3600,
  "context": "gke_based-hardware_us-central1_prod-omi-gke",
  "proxy": "/api/v1/namespaces/prod-omi-monitoring/services/prod-omi-kube-prometheus-s-prometheus:9090/proxy/api/v1/"
}
```

## window_first_text_p95

```json
{
  "promql": "histogram_quantile(0.95,sum by(le)(rate(omi_stt_window_first_text_seconds_bucket{namespace=\"prod-omi-backend\"}[1h])))",
  "start": "2026-10-07",
  "end_exclusive": "2026-10-14",
  "step": 3600,
  "context": "gke_based-hardware_us-central1_prod-omi-gke",
  "proxy": "/api/v1/namespaces/prod-omi-monitoring/services/prod-omi-kube-prometheus-s-prometheus:9090/proxy/api/v1/"
}
```
