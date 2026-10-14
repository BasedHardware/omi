#!/usr/bin/env python3
"""Read-only aggregate receipt. Source gcp-agent-env.sh ro-prod before running.

python3 cost-baseline-receipt.py --start 2026-10-07 --end 2026-10-14
No customer identifiers, audio, pod environment, or pod YAML are fetched.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import urllib.parse

CONTEXT = 'gke_based-hardware_us-central1_prod-omi-gke'
PROXY = '/api/v1/namespaces/prod-omi-monitoring/services/prod-omi-kube-prometheus-s-prometheus:9090/proxy/api/v1/'
TABLE = 'based-hardware.gcp_billing_export.gcp_billing_export_resource_v1_01B287_9348DC_02D256'


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if p.returncode:
        raise RuntimeError(p.stderr[:1500])
    return json.loads(p.stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', required=True)
    ap.add_argument('--end', required=True, help='exclusive UTC date')
    ap.add_argument('--out', type=Path, default=Path(__file__).with_name('cost-baseline-raw.json'))
    ap.add_argument('--source-repo', default='/Users/dazheng/workspace/omi/upstream-keep-clean', help='Git reference store; files read only through git show')
    a = ap.parse_args()
    if os.environ.get('GCP_AGENT_TIER') != 'ro-prod':
        ap.error('source ~/.local/bin/gcp-agent-env.sh ro-prod first')
    start, end = [dt.datetime.fromisoformat(x).replace(tzinfo=dt.timezone.utc) for x in (a.start, a.end)]
    if end <= start:
        ap.error('end must follow start')
    out = {'start': a.start, 'end_exclusive': a.end, 'captured_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'queries': {}, 'results': {}}
    def save(name, query, result):
        out['queries'][name] = query
        out['results'][name] = result
        a.out.write_text(json.dumps(out, indent=2) + '\n')
    def bq(name, sql):
        save(name, sql, run(['bq', 'query', '--use_legacy_sql=false', '--maximum_bytes_billed=50000000000', '--max_rows=10000', '--format=json', sql]))
    bq('unit_cost', f'''SELECT date, SUM(tx_sec)/3600 tx_hours, SUM(audio_pipeline_gcp) audio_cost,
SAFE_DIVIDE(SUM(audio_pipeline_gcp),SUM(tx_sec)/3600) cost_per_tx_hour,
LOGICAL_AND(inputs_settled) settled, COUNT(DISTINCT run_id) runs
FROM `based-hardware.omi_finops.unit_cost_user_day`
WHERE date >= DATE('{a.start}') AND date < DATE('{a.end}') GROUP BY date ORDER BY date''')
    bq('allocated_components', f'''SELECT date, component, method, SUM(usd) usd,
LOGICAL_AND(inputs_settled) settled FROM `based-hardware.omi_finops.unit_cost_daily`
WHERE date >= DATE('{a.start}') AND date < DATE('{a.end}') AND segment_type='total'
GROUP BY date,component,method ORDER BY date,component''')
    repo = a.source_repo
    classifier = subprocess.run(['git', '-C', repo, 'show', 'origin/main:backend/scripts/finops/gcp_component_classifier.sql'], check=True, text=True, capture_output=True).stdout
    events = json.loads(subprocess.run(['git', '-C', repo, 'show', 'origin/main:backend/scripts/finops/one_time_events.json'], check=True, text=True, capture_output=True).stdout)['events']
    def literal(value):
        return "'" + value.replace('\\', '\\\\').replace("'", "\\'") + "'"
    rules = []
    for event in events:
        conditions = [f"DATE(usage_start_time) BETWEEN {literal(event['date_from'])} AND {literal(event['date_to'])}"]
        for key, expr in [('sku_like', 'sku.description LIKE'), ('resource_like', 'IFNULL(resource.global_name,resource.name) LIKE'), ('service', 'service.description =')]:
            if event.get(key): conditions.append(expr + ' ' + literal(event[key]))
        rules.append('WHEN ' + ' AND '.join(conditions) + ' THEN ' + literal(event['component']))
    classifier = classifier[classifier.index('CASE'):classifier.index('END AS component,') + 3].replace('{{ONE_TIME_RULES}}', '\n'.join(rules))
    out['source_sha'] = subprocess.run(['git', '-C', repo, 'rev-parse', 'origin/main'], check=True, text=True, capture_output=True).stdout.strip()
    # Preserve source classifier and dated event exclusions in every receipt.
    bq('audio_reconciliation', f'''WITH base AS (SELECT DATE(usage_start_time) date,
IF(project.id='based-hardware','prod','nonprod') scope,
{classifier} component,
(SELECT l.value FROM UNNEST(labels) l WHERE l.key='goog-k8s-node-pool-name' LIMIT 1) pool,
cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c),0) net
FROM `{TABLE}` WHERE usage_start_time >= TIMESTAMP('{a.start}') AND usage_start_time < TIMESTAMP('{a.end}'))
SELECT date,scope,CASE WHEN REGEXP_CONTAINS(pool,r'^(backend-listen-pool|pusher-pool)')
AND component='gke_other_compute' THEN 'listen_pipeline_compute' ELSE component END component,
SUM(net) net FROM base WHERE component IN ('asr_gpu_fleet','storage_audio')
OR (component='gke_other_compute' AND REGEXP_CONTAINS(pool,r'^(backend-listen-pool|pusher-pool)'))
GROUP BY date,scope,component ORDER BY date,scope,component''')
    bq('billing', f'''WITH base AS (SELECT TIMESTAMP_TRUNC(usage_start_time,HOUR) hour,
service.description service, sku.description sku,
(SELECT l.value FROM UNNEST(labels) l WHERE l.key='goog-k8s-node-pool-name' LIMIT 1) pool,
IFNULL(resource.global_name,resource.name) resource,
cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c),0) net
FROM `{TABLE}` WHERE usage_start_time >= TIMESTAMP('{a.start}')
AND usage_start_time < TIMESTAMP('{a.end}') AND project.id='based-hardware')
SELECT hour, CASE
WHEN pool IS NOT NULL THEN CONCAT('pool:',pool)
WHEN REGEXP_CONTAINS(resource,r'//run.googleapis.com/.*/services/(backend-listen|backend-sync|pusher)$')
THEN CONCAT('run:',REGEXP_EXTRACT(resource,r'/services/([^/]+)$'))
WHEN service IN ('Cloud Storage','Storage Insights') AND REGEXP_CONTAINS(resource,r'/buckets/(omi-private-cloud-sync|syncing-local)') THEN 'gcs:audio'
WHEN service IN ('Cloud Storage','Storage Insights') THEN 'gcs:other'
ELSE CONCAT('unallocated:',service) END component,
SUM(net) net_cost FROM base GROUP BY hour,component ORDER BY hour,component''')
    k = ['kubectl', '--context', CONTEXT]
    hpas = run(k + ['get', 'hpa', '-n', 'prod-omi-backend', '-o', 'json'])
    save('hpa', 'kubectl --context '+CONTEXT+' get hpa -n prod-omi-backend -o json (project spec only)',
         [{'name': x['metadata']['name'], 'spec': x['spec'], 'currentReplicas': x.get('status', {}).get('currentReplicas')} for x in hpas['items']])
    save('pools', 'gcloud container node-pools list --cluster=prod-omi-gke --region=us-central1 --format=json(name,locations,config.machineType,config.accelerators,config.spot,autoscaling)',
         run(['gcloud', 'container', 'node-pools', 'list', '--cluster=prod-omi-gke', '--region=us-central1', '--format=json(name,locations,config.machineType,config.accelerators,config.spot,autoscaling)']))
    # kube_node_labels is not exported. GKE node-name prefixes retain historical
    # pool identity, including deleted nodes. Long pool names are truncated by GKE.
    pattern = 'gke-prod-omi-gke-(.*)-[a-z0-9]{8}-[a-z0-9]{4}'
    gpu = 'max by(Hostname,UUID,pool)(label_replace({metric},"pool","$1","Hostname","' + pattern + '"))'
    queries = {
        'listen': 'sum(max by(pod)(backend_listen_active_ws_connections{namespace="prod-omi-backend"}))',
        'pusher': 'sum(max by(pod)(pusher_active_ws_connections{namespace="prod-omi-backend"}))',
        'nodes': 'count by(pool)(max by(node,pool)(label_replace(kube_node_info,"pool","$1","node","' + pattern + '")))',
        'gpu_util': 'avg by(pool)(' + gpu.replace('{metric}', 'avg_over_time(DCGM_FI_DEV_GPU_UTIL[1h])') + ')',
        'gpu_memory_mib': 'avg by(pool)(' + gpu.replace('{metric}', 'avg_over_time(DCGM_FI_DEV_FB_USED[1h])') + ')',
        'gpu_coverage': 'count by(pool)(' + gpu.replace('{metric}', 'DCGM_FI_DEV_GPU_UTIL') + ')',
        'parakeet_streams': 'sum(max by(pod)(parakeet_active_streams{namespace="prod-omi-backend"}))',
        'parakeet_p95': 'histogram_quantile(0.95,sum by(le)(rate(parakeet_request_duration_seconds_bucket{namespace="prod-omi-backend"}[5m])))',
        'metric_names': 'count by(__name__)({__name__=~"parakeet_.*(duration|queue|latency).*"})',
        'asr_service_rtf': 'sum(increase(parakeet_request_duration_seconds_sum{namespace="prod-omi-backend",exported_endpoint=~"v1_transcribe|v2_transcribe"}[7d])) / sum(increase(parakeet_audio_duration_seconds_sum{namespace="prod-omi-backend"}[7d]))',
        'asr_audio_seconds': 'sum(increase(parakeet_audio_duration_seconds_sum{namespace="prod-omi-backend"}[7d]))',
        'window_post_p95': 'histogram_quantile(0.95,sum by(le)(rate(omi_stt_window_post_seconds_bucket{namespace="prod-omi-backend"}[1h])))',
        'window_first_text_p95': 'histogram_quantile(0.95,sum by(le)(rate(omi_stt_window_first_text_seconds_bucket{namespace="prod-omi-backend"}[1h])))',
    }
    for name, q in queries.items():
        params = {'query': q, 'start': int(start.timestamp()), 'end': int(end.timestamp())-1, 'step': 3600}
        url = PROXY + 'query_range?' + urllib.parse.urlencode(params)
        result = run(k + ['get', '--raw', url])
        save(name, {'promql': q, 'start': a.start, 'end_exclusive': a.end, 'step': 3600, 'context': CONTEXT, 'proxy': PROXY}, result)
        if result.get('status') != 'success':
            raise RuntimeError(f'Prometheus query {name} failed; see local receipt')
    print(f'Wrote aggregate receipt: {a.out}')


if __name__ == '__main__':
    main()
