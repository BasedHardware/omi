"""Prevent the prod values/live drift that would remove Parakeet HPA metrics."""

import copy
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.diff_prod_adapter import compare, expected_config
from scripts import select_backend_unit_tests as selector

CHARTS = Path(__file__).resolve().parents[2] / 'charts'
ADAPTER = CHARTS / 'monitoring/prometheus-adapter/prod_omi_prometheus_adapter.yaml'


@pytest.mark.parametrize('service', ['parakeet', 'backend-listen', 'pusher', 'vad', 'diarizer', 'deepgram-self-hosted'])
def test_prod_hpa_consumed_metrics_have_adapter_rules(service):
    helm = shutil.which('helm')
    if helm is None:
        pytest.skip('helm is not installed')
    chart = CHARTS / service
    if service == 'deepgram-self-hosted':
        chart /= 'nova-3'
        values = chart / 'prod_omi_values.yaml'
        templates = ['templates/engine/engine.hpa.yaml', 'templates/api/api.hpa.yaml']
    else:
        values = chart / f'prod_omi_{service.replace("-", "_")}_values.yaml'
        templates = ['templates/hpa.yaml']
    command = [
        helm,
        'template',
        f'prod-omi-{service}',
        str(chart),
        '--values',
        str(values),
        '--set-string',
        'image.tag=contract-test',
    ]
    for template in templates:
        command.extend(['--show-only', template])
    rendered = subprocess.run(command, check=True, capture_output=True, text=True).stdout
    hpas = [obj for obj in yaml.safe_load_all(rendered) if obj and obj['kind'] == 'HorizontalPodAutoscaler']
    assert hpas, f'{service}: no prod HPA rendered'
    rules = yaml.safe_load(ADAPTER.read_text())['rules']
    available = {
        'External': {rule['name']['as'] for rule in rules.get('external', [])},
        'Pods': {rule['name']['as'] for rule in rules.get('custom', [])},
    }
    for hpa in hpas:
        for metric in hpa['spec']['metrics']:
            kind = metric['type']
            if kind in available:
                name = metric[kind.lower()]['metric']['name']
                assert name in available[kind], f'{service}: {kind} metric {name} missing from prod adapter'


def test_cluster_adapter_keeps_all_parakeet_rules():
    cluster = yaml.safe_load(ADAPTER.read_text())['rules']
    parakeet = yaml.safe_load((CHARTS / 'parakeet/values.yaml').read_text())['prometheus-adapter']['rules']
    for key in ('custom', 'external'):
        indexed = {rule['name']['as']: rule for rule in cluster[key]}
        for rule in parakeet[key]:
            assert indexed[rule['name']['as']] == rule


def test_hpa_and_adapter_changes_select_this_contract():
    sources = [ADAPTER] + list(CHARTS.glob('*/prod*values.yaml'))
    sources += list(CHARTS.glob('*/templates/hpa.yaml'))
    sources += [CHARTS / 'deepgram-self-hosted/nova-3/prod_omi_values.yaml']
    owned = {'parakeet', 'backend-listen', 'pusher', 'vad', 'diarizer', 'deepgram-self-hosted', 'monitoring'}
    all_tests = selector.discover_all_tests()
    for source in sources:
        if source.relative_to(CHARTS).parts[0] not in owned:
            continue
        path = str(source.relative_to(CHARTS.parents[1]))
        selected, _ = selector.tests_for_changed_paths([path], all_tests)
        assert 'tests/unit/test_monitoring_adapter_hpa_contract.py' in selected, path


def _comparison_inputs():
    values = yaml.safe_load(ADAPTER.read_text())['rules']
    config = {'externalRules': values['external'], 'rules': values['custom']}
    live = copy.deepcopy(config)
    listen = live['externalRules'][0]
    listen['seriesQuery'] = 'backend_listen_active_ws_connections'
    listen['metricsQuery'] = 'avg(backend_listen_active_ws_connections{job="backend-listen-metrics"})'
    deployment = {'kind': 'Deployment', 'spec': {'template': {'spec': {'containers': [{'args': ['--config=x']}]}}}}
    api = {'kind': 'APIService', 'metadata': {'name': 'external'}, 'spec': {'service': {'name': 'adapter'}}}
    rendered = [{'kind': 'ConfigMap', 'data': {'config.yaml': yaml.safe_dump(config)}}, deployment, api]
    live_api = copy.deepcopy(api)
    live_api['spec']['service']['port'] = 443
    return rendered, {'data': {'config.yaml': yaml.safe_dump(live)}}, deployment, {'items': [live_api]}


def test_diff_allows_only_canary_filter_and_api_port_default():
    assert compare(*_comparison_inputs())[1] == []


def test_diff_accepts_reconciled_live_and_rule_reordering():
    rendered, live, deployment, apiservices = _comparison_inputs()
    live['data']['config.yaml'] = rendered[0]['data']['config.yaml']
    config = yaml.safe_load(rendered[0]['data']['config.yaml'])
    config['rules'].reverse()
    config['externalRules'].reverse()
    rendered[0]['data']['config.yaml'] = yaml.safe_dump(config)
    assert compare(rendered, live, deployment, apiservices)[1] == []


@pytest.mark.parametrize('drift', ['missing-rule', 'extra-rule', 'query', 'args', 'apiservice'])
def test_diff_rejects_unreviewed_changes(drift):
    rendered, live, deployment, apiservices = _comparison_inputs()
    rendered = copy.deepcopy(rendered)
    config = yaml.safe_load(rendered[0]['data']['config.yaml'])
    if drift == 'missing-rule':
        config['rules'].pop()
    elif drift == 'extra-rule':
        config['rules'].append({'name': {'as': 'unreviewed'}})
    elif drift == 'query':
        config['externalRules'][1]['metricsQuery'] = 'vector(0)'
    elif drift == 'args':
        rendered[1]['spec']['template']['spec']['containers'][0]['args'].append('--unreviewed')
    else:
        rendered[2]['spec']['service']['name'] = 'different-adapter'
    rendered[0]['data']['config.yaml'] = yaml.safe_dump(config)
    assert compare(rendered, live, deployment, apiservices)[1]


def test_diff_rejects_unexpected_live_listen_query():
    with pytest.raises(ValueError, match='Unexpected live listen'):
        expected_config(
            {
                'externalRules': [
                    {'name': {'as': 'backend_listen_active_ws_connections_per_pod'}, 'seriesQuery': 'unreviewed'}
                ]
            }
        )
