"""Free-allowance watch counters must reach GMP from every service that emits them.

The sync/integration Cloud Run keep rule lists metric families explicitly and
omitted ``omi_free_allowance_*``, and the batch worker serves a private registry
that never registered them, so upload, sync and batch observations were emitted
and silently dropped (SCA-1750; FC-metric-dropped-by-scrape-allowlist).
"""

import re
from pathlib import Path

import pytest
import yaml
from prometheus_client import CollectorRegistry

from utils.stt import allowance_metrics as allowance_watch

BACKEND = Path(__file__).resolve().parents[2]
FAMILIES = (
    'omi_free_allowance_watch_decisions_total',
    'omi_free_allowance_watch_seconds_total',
    'omi_free_allowance_lease_decisions_total',
    'omi_free_allowance_settled_seconds_total',
)


def _keep_regex(profile):
    config = yaml.safe_load((BACKEND / 'deploy' / profile).read_text(encoding='utf-8'))
    keep = [rule for rule in config['spec']['endpoints'][0]['metricRelabeling'] if rule['action'] == 'keep']
    assert len(keep) == 1, profile
    return keep[0]['regex']


@pytest.mark.parametrize('profile', ('cloud_run_gmp_sidecar.yaml', 'cloud_run_gmp_sync.yaml'))
@pytest.mark.parametrize('name', FAMILIES)
def test_allowance_families_survive_the_keep_rule(profile, name):
    assert re.fullmatch(_keep_regex(profile), name), (profile, name)


def test_worker_registry_can_carry_every_allowance_collector():
    registry = CollectorRegistry()
    for collector in allowance_watch.COLLECTORS:
        registry.register(collector)
    allowance_watch.DECISIONS.labels('batch_gpu', 'parakeet', 'would_allow').inc()
    names = {metric.name for metric in registry.collect()}
    assert {
        'omi_free_allowance_watch_decisions',
        'omi_free_allowance_watch_seconds',
        'omi_free_allowance_lease_decisions',
        'omi_free_allowance_settled_seconds',
    } <= names


def test_batch_worker_health_server_registers_allowance_collectors():
    source = (BACKEND / 'diarizer' / 'batch_pipeline_runtime.py').read_text(encoding='utf-8')
    assert 'ALLOWANCE_WATCH_COLLECTORS' in source.split('def health_server', 1)[1]


@pytest.mark.parametrize(
    'profile', ('cloud_run_gmp_sidecar.yaml', 'cloud_run_gmp_sync.yaml', 'cloud_run_gmp_projection_pump.yaml')
)
def test_month_shadow_survives_cloud_run_keep_rules(profile):
    assert re.fullmatch(_keep_regex(profile), 'omi_usage_month_total_shadow_total')


@pytest.mark.parametrize('service,file_name', [('backend-listen', 'backend_listen'), ('pusher', 'pusher')])
def test_month_shadow_survives_gke_keep_rules(service, file_name):
    chart = BACKEND / 'charts' / service / f'prod_omi_{file_name}_values.yaml'
    fast = yaml.safe_load(chart.read_text())['podMonitoring']['fastMetrics']
    assert re.fullmatch(fast, 'omi_usage_month_total_shadow_total')
