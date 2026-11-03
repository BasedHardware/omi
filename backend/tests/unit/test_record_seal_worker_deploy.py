"""CPU slot/HPA/metric wiring and reversible cron cutover, rendered offline."""

import json

import pytest
import yaml

from tests.unit.test_record_seal_cluster_repair_deploy import documents
from tests.unit.test_record_seal_sweeper_deploy import CHART, BACKEND, render


def test_cpu_placement_ceiling_and_identity():
    docs = documents()
    pod = docs[('Deployment', 'record-seal-worker')]['spec']['template']['spec']
    cron = docs[('CronJob', 'record-seal-repair')]['spec']
    assert cron['suspend'] is True
    assert docs[('CronJob', 'record-seal-sweeper')]['spec']['schedule'] == '0 * * * *'
    assert pod['serviceAccountName'] == cron['jobTemplate']['spec']['template']['spec']['serviceAccountName']
    assert 'nodeSelector' not in pod and 'tolerations' not in pod
    expressions = pod['affinity']['nodeAffinity']['requiredDuringSchedulingIgnoredDuringExecution'][
        'nodeSelectorTerms'
    ][0]['matchExpressions']
    assert {'key': 'cloud.google.com/gke-accelerator', 'operator': 'DoesNotExist'} in expressions
    container = pod['containers'][0]
    assert container['command'] == ['python', 'scripts/record_seal_worker.py']
    assert container['resources'] == {
        'requests': {'cpu': '62m', 'memory': '128Mi'},
        'limits': {'cpu': '250m', 'memory': '512Mi'},
    }
    assert 'nvidia.com/gpu' not in json.dumps(container['resources'])
    hpa = docs[('HorizontalPodAutoscaler', 'record-seal-worker')]['spec']
    assert hpa['minReplicas'] == 1 and hpa['maxReplicas'] == 16
    metric = hpa['metrics'][0]['external']
    assert metric['metric']['name'] == 'omi_record_seal_backlog'
    assert metric['target'] == {'type': 'AverageValue', 'averageValue': '4'}
    env = {e['name']: e.get('value') for e in container['env']}
    assert env['RECORD_SEAL_WORKER_ENABLED'] == 'true'
    assert env['RECORD_SEAL_OVERLAP_TRIM_ENABLED'] == env['RECORD_SEAL_UPLOAD_FAILED_REPAIR_ENABLED'] == 'true'


def test_rollback_and_overlap_are_explicit_and_preserve_gpu_resources():
    before = documents()
    overlap = documents('--set', 'recordSealRepair.suspend=false')
    after = documents('--set', 'recordSealWorker.runtimeEnabled=false,recordSealRepair.suspend=false')
    assert overlap[('CronJob', 'record-seal-repair')]['spec']['suspend'] is False
    assert {key for key in before if before[key] != after[key]} == {
        ('CronJob', 'record-seal-repair'),
        ('Deployment', 'record-seal-worker'),
    }
    docs = documents('--set', 'recordSealSweeper.enabled=false,recordSealRepair.enabled=false')
    assert ('Role', 'record-seal-sweeper') in docs  # CPU worker alone retains pods.list.


@pytest.mark.parametrize(
    'value',
    ['recordSealWorker.maxReplicas=17', 'recordSealWorker.maxReplicas=0', 'recordSealWorker.targetBacklogPerWorker=0'],
)
def test_invalid_capacity_refused(value):
    assert render('--set', value).returncode != 0


def test_adapter_freshness_dedup_and_prometheus_scrape_path():
    adapter = yaml.safe_load(
        (BACKEND / 'charts/monitoring/prometheus-adapter/prod_omi_prometheus_adapter.yaml').read_text()
    )
    rule = next(rule for rule in adapter['rules']['external'] if rule['name'].get('as') == 'omi_record_seal_backlog')
    example = yaml.safe_load((CHART / 'prometheus-adapter-rules.yaml').read_text())
    assert rule['metricsQuery'] == example['external'][0]['metricsQuery']
    assert 'max by (namespace, worker_release)' in rule['metricsQuery']
    assert 'refreshed_at_seconds < 60' in rule['metricsQuery'] and 'vector(0)' not in rule['metricsQuery']
    monitoring = yaml.safe_load(
        (BACKEND / 'charts/monitoring/kube-prometheus-stack/prod_omi_monitoring_values.yaml').read_text()
    )
    configs = monitoring['prometheus']['prometheusSpec']['additionalScrapeConfigs']
    if isinstance(configs, str):
        configs = yaml.safe_load(configs)
    scrape = next(config for config in configs if config['job_name'] == 'record-seal-worker-metrics')
    assert scrape['scrape_interval'] == '15s'
    assert {entry.get('target_label') for entry in scrape['relabel_configs']} >= {'namespace', 'pod'}


def test_other_stages_never_create_workers():
    for stage in ('dev', 'staging'):
        docs = documents('--set', f'stage={stage}')
        assert ('Deployment', 'record-seal-worker') not in docs
