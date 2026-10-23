"""Prevent the prod values/live drift that would remove Parakeet HPA metrics."""

import copy
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.diff_prod_adapter import (
    API_SERVICES,
    NLLB_RULE,
    DIARIZER_BATCH_RULE,
    PARAKEET_QUEUE_RULES,
    compare,
    expected_config,
)
from scripts import select_backend_unit_tests as selector

CHARTS = Path(__file__).resolve().parents[2] / 'charts'
ADAPTER = CHARTS / 'monitoring/prometheus-adapter/prod_omi_prometheus_adapter.yaml'


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_queue_rules_live_under_adapter_rules_and_keep_both_lanes(environment):
    values = yaml.safe_load(
        (CHARTS / f'monitoring/prometheus-adapter/{environment}_omi_prometheus_adapter.yaml').read_text()
    )
    rules = {rule['name']['as']: rule for rule in values['rules']['custom']}
    for rule in PARAKEET_QUEUE_RULES:
        assert rules[rule['name']['as']] == rule
    assert 'parakeet_active_requests_total' in rules
    assert isinstance(values['extraArguments'], list)


def test_diff_accepts_only_exact_new_parakeet_queue_rules():
    rules = yaml.safe_load(ADAPTER.read_text())['rules']
    live = {'rules': rules['custom'], 'externalRules': rules['external']}
    old = copy.deepcopy(live)
    old['rules'] = [r for r in old['rules'] if r['name']['as'] not in {q['name']['as'] for q in PARAKEET_QUEUE_RULES}]
    assert expected_config(old) == expected_config(live)
    broken = copy.deepcopy(live)
    next(r for r in broken['rules'] if r['name']['as'] == 'parakeet_live_queue_age_seconds')[
        'metricsQuery'
    ] = 'vector(0)'
    with pytest.raises(ValueError, match='Unexpected live Parakeet queue rule'):
        expected_config(broken)


@pytest.mark.parametrize('service', ['parakeet', 'backend-listen', 'pusher', 'vad', 'diarizer', 'nllb-translation'])
def test_prod_hpa_consumed_metrics_have_adapter_rules(service):
    helm = shutil.which('helm')
    if helm is None:
        pytest.skip('helm is not installed')
    chart = CHARTS / service
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
    owned = {
        'parakeet',
        'backend-listen',
        'pusher',
        'vad',
        'diarizer',
        'nllb-translation',
        'monitoring',
    }
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
    live['externalRules'].remove(NLLB_RULE)
    listen = live['externalRules'][0]
    listen['seriesQuery'] = 'backend_listen_active_ws_connections'
    listen['metricsQuery'] = 'avg(backend_listen_active_ws_connections{job="backend-listen-metrics"})'
    # Captured pre-upgrade queries, independent of the candidate values above.
    gpu = next(rule for rule in live['externalRules'] if rule['name']['as'] == 'parakeet_gpu_utilization')
    gpu['seriesQuery'] = 'DCGM_FI_DEV_GPU_UTIL{namespace!=""}'
    gpu['metricsQuery'] = 'avg(avg_over_time(DCGM_FI_DEV_GPU_UTIL{<<.LabelMatchers>>}[1m]))'
    deployment = {'kind': 'Deployment', 'spec': {'template': {'spec': {'containers': [{'args': ['--config=x']}]}}}}
    api = {
        'kind': 'APIService',
        'metadata': {
            'name': 'v1beta1.external.metrics.k8s.io',
            'labels': {'app.kubernetes.io/managed-by': 'Helm'},
            'annotations': {
                'meta.helm.sh/release-name': 'prod-omi-prometheus-adapter',
                'meta.helm.sh/release-namespace': 'prod-omi-monitoring',
            },
        },
        'spec': {'service': {'name': 'adapter'}},
    }
    custom_api = copy.deepcopy(api)
    custom_api['metadata']['name'] = 'v1beta1.custom.metrics.k8s.io'
    rendered = [{'kind': 'ConfigMap', 'data': {'config.yaml': yaml.safe_dump(config)}}, deployment, api, custom_api]
    live_apis = copy.deepcopy([api, custom_api])
    for live_api in live_apis:
        live_api['spec']['service']['port'] = 443
    return rendered, {'data': {'config.yaml': yaml.safe_dump(live)}}, deployment, {'items': live_apis}


def test_diff_allows_only_canary_filter_nllb_rule_and_api_port_default():
    assert compare(*_comparison_inputs())[1] == []


def test_diff_accepts_reviewed_unscoped_to_parakeet_gpu_queries():
    inputs = _comparison_inputs()
    live = yaml.safe_load(inputs[1]['data']['config.yaml'])
    gpu = next(rule for rule in live['externalRules'] if rule['name']['as'] == 'parakeet_gpu_utilization')
    assert gpu['seriesQuery'] == 'DCGM_FI_DEV_GPU_UTIL{namespace!=""}'
    assert gpu['metricsQuery'] == 'avg(avg_over_time(DCGM_FI_DEV_GPU_UTIL{<<.LabelMatchers>>}[1m]))'
    assert compare(*inputs)[1] == []
    # The reviewed upgrade must never be admitted as an exact-live rollback.
    assert compare(*inputs, allow_reviewed_changes=False)[1]


@pytest.mark.parametrize('field', ['seriesQuery', 'metricsQuery'])
def test_diff_rejects_unreviewed_live_parakeet_gpu_query(field):
    _, cm, _, _ = _comparison_inputs()
    live = yaml.safe_load(cm['data']['config.yaml'])
    gpu = next(rule for rule in live['externalRules'] if rule['name']['as'] == 'parakeet_gpu_utilization')
    gpu[field] = 'unreviewed'
    with pytest.raises(ValueError, match='Unexpected live Parakeet GPU'):
        expected_config(live)


@pytest.mark.parametrize('change', ['missing', 'duplicate'])
def test_diff_rejects_ambiguous_live_parakeet_gpu_rule(change):
    _, cm, _, _ = _comparison_inputs()
    live = yaml.safe_load(cm['data']['config.yaml'])
    gpu = next(rule for rule in live['externalRules'] if rule['name']['as'] == 'parakeet_gpu_utilization')
    if change == 'missing':
        live['externalRules'].remove(gpu)
    else:
        live['externalRules'].append(copy.deepcopy(gpu))
    with pytest.raises(ValueError, match='Unexpected live Parakeet GPU rule count'):
        expected_config(live)


def test_diff_accepts_reconciled_live_and_rule_reordering():
    rendered, live, deployment, apiservices = _comparison_inputs()
    live['data']['config.yaml'] = rendered[0]['data']['config.yaml']
    config = yaml.safe_load(rendered[0]['data']['config.yaml'])
    config['rules'].reverse()
    config['externalRules'].reverse()
    rendered[0]['data']['config.yaml'] = yaml.safe_dump(config)
    assert compare(rendered, live, deployment, apiservices)[1] == []


def test_rollback_manifest_must_preserve_exact_live_rules():
    rendered, live, deployment, apiservices = _comparison_inputs()
    assert compare(rendered, live, deployment, apiservices, allow_reviewed_changes=False)[1]
    rendered[0]['data']['config.yaml'] = live['data']['config.yaml']
    assert compare(rendered, live, deployment, apiservices, allow_reviewed_changes=False)[1] == []


def test_diff_rejects_api_service_without_release_ownership():
    rendered, live, deployment, apiservices = _comparison_inputs()
    apiservices['items'][0]['metadata'] = {'name': 'external'}
    assert any('Helm ownership' in error for error in compare(rendered, live, deployment, apiservices)[1])


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


@pytest.mark.parametrize('missing', sorted(API_SERVICES))
def test_rollback_requires_both_api_service_specs(missing):
    rendered, live, deployment, apiservices = _comparison_inputs()
    rendered[0]['data']['config.yaml'] = live['data']['config.yaml']
    rendered = [obj for obj in rendered if obj.get('metadata', {}).get('name') != missing]
    assert any(
        'APIService specs' in error
        for error in compare(rendered, live, deployment, apiservices, allow_reviewed_changes=False)[1]
    )


def test_rollback_review_before_live_ownership_adoption():
    rendered, live, deployment, apiservices = _comparison_inputs()
    rendered[0]['data']['config.yaml'] = live['data']['config.yaml']
    apiservices['items'][1]['metadata'].pop('annotations')
    assert compare(rendered, live, deployment, apiservices, allow_reviewed_changes=False)[1] == []


def test_diff_rejects_modified_nllb_addition():
    rendered, live, deployment, apiservices = _comparison_inputs()
    config = yaml.safe_load(rendered[0]['data']['config.yaml'])
    next(rule for rule in config['externalRules'] if rule['name']['as'] == NLLB_RULE['name']['as'])[
        'metricsQuery'
    ] = 'vector(0)'
    rendered[0]['data']['config.yaml'] = yaml.safe_dump(config)
    assert compare(rendered, live, deployment, apiservices)[1]


def test_diff_rejects_unexpected_live_nllb_query():
    _, live, _, _ = _comparison_inputs()
    config = yaml.safe_load(live['data']['config.yaml'])
    config['externalRules'].append(dict(NLLB_RULE, metricsQuery='vector(0)'))
    with pytest.raises(ValueError, match='Unexpected live NLLB'):
        expected_config(config)


def test_diff_allows_only_exact_batch_queue_rule_addition():
    rendered, cm, deployment, apis = _comparison_inputs()
    live = yaml.safe_load(cm['data']['config.yaml'])
    live['rules'].remove(DIARIZER_BATCH_RULE)
    cm['data']['config.yaml'] = yaml.safe_dump(live)
    assert compare(rendered, cm, deployment, apis)[1] == []


@pytest.mark.parametrize('change', ['query', 'duplicate'])
def test_diff_rejects_unreviewed_live_batch_queue_rule(change):
    _, cm, _, _ = _comparison_inputs()
    live = yaml.safe_load(cm['data']['config.yaml'])
    rule = next(r for r in live['rules'] if r['name']['as'] == DIARIZER_BATCH_RULE['name']['as'])
    if change == 'query':
        rule['metricsQuery'] = 'sum(omi_diarization_v2_queue_depth)'
    else:
        live['rules'].append(copy.deepcopy(rule))
    with pytest.raises(ValueError, match='Unexpected live batch queue rule'):
        expected_config(live)
