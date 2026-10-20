"""Read-only comparison of a local adapter render with captured production YAML."""

import argparse
import copy
import difflib
import json
from pathlib import Path
from typing import Any

import yaml

NLLB_RULE: dict[str, Any] = {
    'name': {'as': 'nllb_active_requests_total'},
    'seriesQuery': 'nllb_active_requests{namespace!=""}',
    'metricsQuery': 'sum(nllb_active_requests{<<.LabelMatchers>>})',
    'resources': {'overrides': {'namespace': {'resource': 'namespace'}}},
}
DIARIZER_BATCH_RULE: dict[str, Any] = {
    'seriesQuery': 'omi_diarization_v2_queue_depth{namespace="prod-omi-backend",pod!="",job="diarizer-batch-metrics"}',
    'resources': {'overrides': {'namespace': {'resource': 'namespace'}, 'pod': {'resource': 'pod'}}},
    'name': {'as': 'omi_diarization_v2_queue_depth'},
    'metricsQuery': 'max(omi_diarization_v2_queue_depth{<<.LabelMatchers>>,job="diarizer-batch-metrics"}) by (<<.GroupBy>>)',
}
API_SERVICES = {'v1beta1.custom.metrics.k8s.io', 'v1beta1.external.metrics.k8s.io'}
PARAKEET_QUEUE_RULES = [
    {
        'seriesQuery': f'parakeet_batch_lane_oldest_pending_seconds{{namespace!="",pod!="",lane="{lane}"}}',
        'resources': {'overrides': {'namespace': {'resource': 'namespace'}, 'pod': {'resource': 'pod'}}},
        'name': {'as': f'parakeet_{lane}_queue_age_seconds'},
        'metricsQuery': 'max(parakeet_batch_lane_oldest_pending_seconds{<<.LabelMatchers>>,lane="'
        + lane
        + '"}) by (<<.GroupBy>>)',
    }
    for lane in ('live', 'backfill')
]


def normalized_config(config):
    """Rule order and YAML mapping order do not affect adapter behavior."""
    config = copy.deepcopy(config)
    for key in ('rules', 'externalRules'):
        if key in config:
            config[key] = sorted(config[key], key=lambda rule: rule['name']['as'])
    return config


def expected_config(live):
    expected = copy.deepcopy(live)
    rule = next(
        rule
        for rule in expected['externalRules']
        if rule['name']['as'] == 'backend_listen_active_ws_connections_per_pod'
    )
    changes = {
        'seriesQuery': (
            'backend_listen_active_ws_connections',
            'backend_listen_active_ws_connections{listen_track!="canary"}',
        ),
        'metricsQuery': (
            'avg(backend_listen_active_ws_connections{job="backend-listen-metrics"})',
            'avg(backend_listen_active_ws_connections{job="backend-listen-metrics",listen_track!="canary"})',
        ),
    }
    for field, (before, after) in changes.items():
        if rule[field] not in (before, after):
            raise ValueError(f'Unexpected live listen {field}: reconcile and review first')
        rule[field] = after
    gpu_rules = [rule for rule in expected['externalRules'] if rule['name']['as'] == 'parakeet_gpu_utilization']
    if len(gpu_rules) != 1:
        raise ValueError('Unexpected live Parakeet GPU rule count: reconcile and review first')
    gpu = gpu_rules[0]
    gpu_changes = {
        'seriesQuery': (
            'DCGM_FI_DEV_GPU_UTIL{namespace!=""}',
            'DCGM_FI_DEV_GPU_UTIL{container="parakeet",namespace!=""}',
        ),
        'metricsQuery': (
            'avg(avg_over_time(DCGM_FI_DEV_GPU_UTIL{<<.LabelMatchers>>}[1m]))',
            'avg(avg_over_time(DCGM_FI_DEV_GPU_UTIL{container="parakeet",<<.LabelMatchers>>}[1m]))',
        ),
    }
    for field, (before, after) in gpu_changes.items():
        if gpu.get(field) not in (before, after):
            raise ValueError(f'Unexpected live Parakeet GPU {field}: reconcile and review first')
        gpu[field] = after
    nllb = [rule for rule in expected['externalRules'] if rule['name']['as'] == NLLB_RULE['name']['as']]
    if nllb and nllb != [NLLB_RULE]:
        raise ValueError('Unexpected live NLLB rule: reconcile and review first')
    if not nllb:
        expected['externalRules'].append(copy.deepcopy(NLLB_RULE))
    batch = [rule for rule in expected['rules'] if rule['name']['as'] == DIARIZER_BATCH_RULE['name']['as']]
    if batch and batch != [DIARIZER_BATCH_RULE]:
        raise ValueError('Unexpected live batch queue rule: reconcile and review first')
    if not batch:
        expected['rules'].append(copy.deepcopy(DIARIZER_BATCH_RULE))
    for queue_rule in PARAKEET_QUEUE_RULES:
        existing = [r for r in expected['rules'] if r['name']['as'] == queue_rule['name']['as']]
        if existing and existing != [queue_rule]:
            raise ValueError('Unexpected live Parakeet queue rule: reconcile and review first')
        if not existing:
            expected['rules'].append(copy.deepcopy(queue_rule))
    return normalized_config(expected)


def api_spec(api):
    spec = copy.deepcopy(api['spec'])
    # The API server defaults an omitted service port to 443.
    spec['service'].setdefault('port', 443)
    return spec


def diff(label, before, after):
    return ''.join(
        difflib.unified_diff(
            (json.dumps(before, sort_keys=True, indent=2) + '\n').splitlines(keepends=True),
            (json.dumps(after, sort_keys=True, indent=2) + '\n').splitlines(keepends=True),
            fromfile=f'live/{label}',
            tofile=f'rendered/{label}',
        )
    )


def compare(rendered, configmap, deployment, apiservices, allow_reviewed_changes=True):
    config = yaml.safe_load(next(obj for obj in rendered if obj['kind'] == 'ConfigMap')['data']['config.yaml'])
    live = yaml.safe_load(configmap['data']['config.yaml'])
    actual = normalized_config(config)
    reports = [diff('config.yaml', normalized_config(live), actual)]
    errors = []
    expected = expected_config(live) if allow_reviewed_changes else normalized_config(live)
    if expected != actual:
        errors.append('Rules differ from the reviewed expectation')

    rendered_deployment = next(obj for obj in rendered if obj['kind'] == 'Deployment')
    live_args = deployment['spec']['template']['spec']['containers'][0]['args']
    rendered_args = rendered_deployment['spec']['template']['spec']['containers'][0]['args']
    if live_args != rendered_args:
        reports.append(diff('Deployment.args', live_args, rendered_args))
        errors.append('Deployment arguments differ')

    actual_apis = {obj['metadata']['name']: api_spec(obj) for obj in rendered if obj['kind'] == 'APIService'}
    live_apis = {obj['metadata']['name']: api_spec(obj) for obj in apiservices['items']}
    if set(actual_apis) != API_SERVICES or set(live_apis) != API_SERVICES:
        errors.append('Both custom and external APIService specs are required; HOLD the upgrade')
    if actual_apis != live_apis:
        reports.append(diff('APIService.spec', live_apis, actual_apis))
        errors.append('APIService specs differ')
    # Rollback review checks stored specs/rules before adopting live ownership.
    for api in apiservices['items'] if allow_reviewed_changes else []:
        metadata = api['metadata']
        annotations = metadata.get('annotations', {})
        if (
            metadata.get('labels', {}).get('app.kubernetes.io/managed-by') != 'Helm'
            or annotations.get('meta.helm.sh/release-name') != 'prod-omi-prometheus-adapter'
            or annotations.get('meta.helm.sh/release-namespace') != 'prod-omi-monitoring'
        ):
            errors.append(f'APIService {metadata["name"]} lacks this release\'s Helm ownership; HOLD the upgrade')
    return reports, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('rendered', 'configmap', 'deployment', 'apiservices'):
        parser.add_argument(f'--{name}', required=True, type=Path)
    parser.add_argument(
        '--require-live-config', action='store_true', help='require exact live rules for rollback review'
    )
    args = parser.parse_args()
    rendered = [obj for obj in yaml.safe_load_all(args.rendered.read_text()) if obj]
    reports, errors = compare(
        rendered,
        yaml.safe_load(args.configmap.read_text()),
        yaml.safe_load(args.deployment.read_text()),
        yaml.safe_load(args.apiservices.read_text()),
        allow_reviewed_changes=not args.require_live_config,
    )
    for report in reports:
        print(report, end='')
    for error in errors:
        print(f'DRIFT: {error}')
    if not errors:
        print('PASS: rules match the reviewed expectation; Deployment args and APIService specs match.')
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
