"""The candidate GMP overlay must not remove the warm-up pin or existing sources."""

import copy
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts.verify_gmp_frontend_render import NAMESPACE, load_objects, validate_render

MONITORING = Path(__file__).resolve().parents[2] / 'charts/monitoring'


def _renders():
    overlay = yaml.safe_load((MONITORING / 'gmp/frontend-values.prod.yaml').read_text())
    sources = [
        {'uid': 'prometheus', 'type': 'prometheus', 'isDefault': True, 'url': 'http://existing-prometheus'},
        {'uid': 'alertmanager', 'type': 'alertmanager', 'url': 'http://existing-alertmanager'},
        # Protect against a later base change: Helm replaces additionalDataSources lists.
        {'uid': 'future-other-source', 'type': 'test', 'url': 'http://existing-other'},
    ]
    datasource = {
        'kind': 'ConfigMap',
        'metadata': {'name': 'existing-datasource', 'namespace': NAMESPACE},
        'data': {'datasource.yaml': yaml.safe_dump({'apiVersion': 1, 'datasources': sources})},
    }
    warm_service = {
        'kind': 'Service',
        'metadata': {'name': 'existing-query-service', 'namespace': NAMESPACE},
        'spec': {'selector': {'statefulset.kubernetes.io/pod-name': 'existing-prometheus-0'}},
    }
    baseline = [datasource, warm_service]
    candidate = copy.deepcopy(baseline)
    candidate[0]['data']['datasource.yaml'] = yaml.safe_dump(
        {'apiVersion': 1, 'datasources': sources + overlay['grafana']['additionalDataSources']}
    )
    candidate.extend(copy.deepcopy(list(overlay['extraManifests'].values())))
    return baseline, candidate


def test_supported_additive_resources_and_datasource_preserve_existing_state():
    baseline, candidate = _renders()
    assert validate_render(baseline, candidate) == []
    base = yaml.safe_load((MONITORING / 'kube-prometheus-stack/prod_omi_monitoring_values.yaml').read_text())
    overlay = yaml.safe_load((MONITORING / 'gmp/frontend-values.prod.yaml').read_text())
    # Mappings merge in Helm; a list here would silently replace the staged Service.
    assert isinstance(base['extraManifests'], dict) and 'prometheusWarmupService' in base['extraManifests']
    assert isinstance(overlay['extraManifests'], dict)
    assert not (set(base['extraManifests']) & set(overlay['extraManifests']))


def test_dropping_an_existing_datasource_is_rejected():
    baseline, candidate = _renders()
    provision = yaml.safe_load(candidate[0]['data']['datasource.yaml'])
    provision['datasources'] = [source for source in provision['datasources'] if source['uid'] != 'future-other-source']
    candidate[0]['data']['datasource.yaml'] = yaml.safe_dump(provision)
    assert 'existing datasource removed or modified' in validate_render(baseline, candidate)


def test_dropping_or_unpinning_the_existing_query_service_is_rejected():
    baseline, candidate = _renders()
    del candidate[1]['spec']['selector']['statefulset.kubernetes.io/pod-name']
    assert any('existing object changed' in error for error in validate_render(baseline, candidate))
    del candidate[1]
    assert any('existing objects removed' in error for error in validate_render(baseline, candidate))


def test_default_source_change_and_explicit_credential_mount_are_rejected():
    baseline, candidate = _renders()
    document = yaml.safe_load(candidate[0]['data']['datasource.yaml'])
    document['datasources'][-1]['isDefault'] = True
    candidate[0]['data']['datasource.yaml'] = yaml.safe_dump(document)
    deployment = next(obj for obj in candidate if obj['kind'] == 'Deployment')
    deployment['spec']['template']['spec']['containers'][0]['envFrom'] = [{'secretRef': {'name': 'unexpected'}}]
    findings = validate_render(baseline, candidate)
    assert any('non-default' in error for error in findings)
    assert any('secret mounts' in error for error in findings)


def test_duplicate_yaml_keys_and_resource_identities_fail_closed():
    with pytest.raises(ValueError, match='duplicate YAML key'):
        load_objects('extraManifests: {}\nextraManifests: []\n')
    baseline, candidate = _renders()
    candidate.append(copy.deepcopy(candidate[-1]))
    with pytest.raises(ValueError, match='duplicate rendered object identity'):
        validate_render(baseline, candidate)


@pytest.mark.parametrize(
    'kind,path,value,expected',
    [
        ('Service', ('selector',), {'unmatched': 'pod'}, 'Service must select'),
        ('Service', ('ports', 0, 'targetPort'), 'missing-port', 'Service must route'),
        ('Service', ('ports', 0, 'port'), 8080, 'Service must route'),
        ('Service', ('type',), 'LoadBalancer', 'internal ClusterIP'),
        ('PodDisruptionBudget', ('selector', 'matchLabels'), {'unmatched': 'pod'}, 'PDB must select'),
        ('PodDisruptionBudget', ('minAvailable',), 0, 'one available replica'),
        ('Deployment', ('template', 'metadata', 'labels'), {'unmatched': 'pod'}, 'Deployment selector'),
        ('Deployment', ('selector', 'matchLabels'), {'unmatched': 'pod'}, 'Deployment selector'),
        (
            'Deployment',
            ('template', 'spec', 'containers', 0, 'readinessProbe'),
            {},
            'readinessProbe must check',
        ),
        (
            'Deployment',
            ('template', 'spec', 'containers', 0, 'livenessProbe', 'httpGet', 'path'),
            '/incorrect-health',
            'livenessProbe must check',
        ),
        (
            'Deployment',
            ('template', 'spec', 'containers', 0, 'readinessProbe', 'httpGet', 'port'),
            'missing-port',
            'readinessProbe must check',
        ),
    ],
)
def test_broken_frontend_query_path_or_availability_wiring_is_rejected(kind, path, value, expected):
    baseline, candidate = _renders()
    resource = next(
        obj for obj in candidate if obj['kind'] == kind and obj['metadata']['name'] == 'prod-omi-gmp-query-frontend'
    )
    target = resource['spec']
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert any(expected in error for error in validate_render(baseline, candidate))


@pytest.mark.parametrize('malformed', ['yaml', 'scalar', 'datasource-shape', 'missing-file'])
def test_cli_invalid_inputs_never_print_source_lines_or_tracebacks(tmp_path, malformed):
    baseline, candidate = _renders()
    baseline_path, candidate_path = tmp_path / 'baseline.yaml', tmp_path / 'candidate.yaml'
    baseline_path.write_text(yaml.safe_dump_all(baseline))
    marker = 'NON_SECRET_REVIEW_MARKER'
    if malformed == 'yaml':
        candidate_path.write_text('broken: [' + marker + '\n')
    elif malformed == 'scalar':
        candidate_path.write_text(marker)
    elif malformed == 'datasource-shape':
        candidate[0]['data']['datasource.yaml'] = yaml.safe_dump({'datasources': [marker]})
        candidate_path.write_text(yaml.safe_dump_all(candidate))
    # missing-file deliberately leaves the candidate path absent.
    result = subprocess.run(
        [
            sys.executable,
            str(MONITORING.parents[1] / 'scripts/verify_gmp_frontend_render.py'),
            '--baseline',
            str(baseline_path),
            '--candidate',
            str(candidate_path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert result.stdout.strip() == 'FAIL: invalid or unreadable rendered Kubernetes documents'
    assert result.stderr == ''
    assert marker not in result.stdout + result.stderr
