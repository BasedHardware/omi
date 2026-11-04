"""Render shared Gateway contracts without contacting a cluster."""

from functools import lru_cache
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
CHARTS = ROOT / 'backend/charts'
SERVICES = ('diarizer', 'parakeet', 'vad', 'nllb-translation')
PREFIXES = {'diarizer': '/diarizer', 'parakeet': '/parakeet', 'vad': '/vad', 'nllb-translation': '/nllb'}
GATEWAY_KINDS = {'HTTPRoute', 'HealthCheckPolicy', 'GCPBackendPolicy'}


@lru_cache(maxsize=None)
def render(environment, chart, enabled=None, batch=False):
    directory = CHARTS / chart
    release = f'{environment}-omi-{chart}' + ('-batch' if batch else '')
    args = ['helm', 'template', release, str(directory), '--namespace', f'{environment}-omi-backend']
    args += ['-f', str(directory / f'{environment}_omi_{chart.replace("-", "_")}_values.yaml')]
    if chart != 'internal-gateway':
        args += ['--set-string', 'image.tag=gateway-contract-test']
    if batch:
        args += ['-f', str(directory / f'{environment}_omi_diarizer_batch_values.yaml')]
    if enabled is not None:
        args += ['--set', f'gateway.enabled={str(enabled).lower()}']
    output = subprocess.check_output(args, text=True)
    return {
        (obj['kind'], obj['metadata']['name']): (obj, raw)
        for raw in output.split('---\n')
        if (obj := yaml.safe_load(raw))
    }


def object_for(objects, kind):
    return next(obj for (k, _), (obj, _) in objects.items() if k == kind)


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_shared_gateway_uses_named_internal_address_and_namespace_listener(environment):
    gateway = object_for(render(environment, 'internal-gateway'), 'Gateway')
    assert gateway['metadata']['name'] == f'{environment}-omi-internal-gateway'
    assert gateway['spec'] == {
        'gatewayClassName': 'gke-l7-rilb',
        'addresses': [{'type': 'NamedAddress', 'value': f'{environment}-ml-gateway-ilb-ip'}],
        'listeners': [
            {
                'name': 'http',
                'port': 80,
                'protocol': 'HTTP',
                'allowedRoutes': {
                    'namespaces': {'from': 'Same'},
                    'kinds': [{'group': 'gateway.networking.k8s.io', 'kind': 'HTTPRoute'}],
                },
            }
        ],
    }


@pytest.mark.parametrize('environment', ['dev', 'prod'])
@pytest.mark.parametrize('chart', SERVICES)
def test_routes_policies_and_separate_services_preserve_all_old_resources(environment, chart):
    enabled, disabled = render(environment, chart), render(environment, chart, False)
    # Compare raw document content; Helm may add separator newlines between kinds.
    # The enabled chart must only add resources; it cannot alter rollback paths
    # or caller env, Deployments, HPA, or pod selectors.
    for key, (_, old_bytes) in disabled.items():
        assert enabled[key][1].rstrip('\n') == old_bytes.rstrip('\n'), key
    added = {key: obj for key, (obj, _) in enabled.items() if key not in disabled}
    assert {kind for kind, _ in added} == GATEWAY_KINDS | {'Service'}
    legacy_service = disabled[('Service', f'{environment}-omi-{chart}')][0]
    gateway_service = object_for({k: (v, '') for k, v in added.items()}, 'Service')
    name = gateway_service['metadata']['name']
    assert name == legacy_service['metadata']['name'] + '-gw'
    assert 'annotations' not in gateway_service['metadata']
    assert gateway_service['spec']['type'] == 'ClusterIP'
    assert gateway_service['spec']['selector'] == legacy_service['spec']['selector']
    port = legacy_service['spec']['ports'][0]['port']
    assert gateway_service['spec']['ports'] == [{'name': 'http', 'port': port, 'targetPort': port, 'protocol': 'TCP'}]
    route = object_for(enabled, 'HTTPRoute')
    assert 'hostnames' not in route['spec']  # IP-literal callers have no service Host header.
    assert route['spec']['parentRefs'] == [{'name': f'{environment}-omi-internal-gateway', 'sectionName': 'http'}]
    assert route['spec']['rules'] == [
        {
            'matches': [{'path': {'type': 'PathPrefix', 'value': PREFIXES[chart]}}],
            'filters': [
                {
                    'type': 'URLRewrite',
                    'urlRewrite': {'path': {'type': 'ReplacePrefixMatch', 'replacePrefixMatch': '/'}},
                }
            ],
            'backendRefs': [{'name': name, 'port': port}],
        }
    ]
    for kind in ('HealthCheckPolicy', 'GCPBackendPolicy'):
        policy = object_for(enabled, kind)
        assert policy['spec']['targetRef'] == {'group': '', 'kind': 'Service', 'name': name}
    health = object_for(enabled, 'HealthCheckPolicy')['spec']['default']
    assert health == {
        'checkIntervalSec': 10,
        'timeoutSec': 5,
        'config': {
            'type': 'HTTP',
            'httpHealthCheck': {'portSpecification': 'USE_FIXED_PORT', 'port': port, 'requestPath': '/health'},
        },
    }
    backend = object_for(enabled, 'GCPBackendPolicy')['spec']['default']
    assert backend == (
        {'timeoutSec': 120, 'connectionDraining': {'drainingTimeoutSec': 130}}
        if chart == 'parakeet'
        else {'timeoutSec': 30}
    )


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_batch_has_an_isolated_route_and_preserves_900_second_timeout(environment):
    objects = render(environment, 'diarizer', batch=True)
    assert not any(kind == 'Ingress' for kind, _ in objects)
    route = object_for(objects, 'HTTPRoute')
    assert route['spec']['rules'][0]['matches'] == [{'path': {'type': 'PathPrefix', 'value': '/diarizer-batch'}}]
    assert route['spec']['rules'][0]['filters'][0]['urlRewrite']['path']['replacePrefixMatch'] == '/'
    assert route['spec']['rules'][0]['backendRefs'] == [{'name': f'{environment}-omi-diarizer-batch-gw', 'port': 8080}]
    assert object_for(objects, 'GCPBackendPolicy')['spec']['default'] == {'timeoutSec': 900}
    pod = object_for(objects, 'Deployment')['spec']['template']['spec']
    assert pod['nodeSelector']['env'] == environment
    if environment == 'prod':
        # Spot-ready prod: no pool pin, so the Spot sibling (same service/env
        # labels and omi.ai taints) shares placement with the on-demand pool.
        assert 'cloud.google.com/gke-nodepool' not in pod['nodeSelector']
    else:
        assert pod['nodeSelector']['cloud.google.com/gke-nodepool'] == 'diarizer-batch-pool'
    if environment == 'prod':
        preference = pod['affinity']['nodeAffinity']['preferredDuringSchedulingIgnoredDuringExecution']
        assert preference == [
            {
                'weight': 100,
                'preference': {
                    'matchExpressions': [{'key': 'cloud.google.com/gke-spot', 'operator': 'In', 'values': ['true']}]
                },
            }
        ]
    else:
        assert 'affinity' not in pod
    assert (
        object_for(objects, 'HealthCheckPolicy')['spec']['default']['config']['httpHealthCheck']['requestPath']
        == '/health'
    )


@pytest.mark.parametrize('chart', SERVICES)
def test_default_service_charts_do_not_require_gateway_crds(chart):
    args = ['helm', 'template', f'test-{chart}', str(CHARTS / chart), '--set-string', 'image.tag=contract-test']
    objects = list(yaml.safe_load_all(subprocess.check_output(args, text=True)))
    assert not any(obj and obj['kind'] in GATEWAY_KINDS for obj in objects)
    failure = subprocess.run(args + ['--set', 'gateway.enabled=true'], capture_output=True, text=True)
    assert failure.returncode != 0
    assert 'gateway.name is required' in failure.stderr


def test_gateway_requires_reserved_address():
    result = subprocess.run(
        ['helm', 'template', 'test', str(CHARTS / 'internal-gateway')], capture_output=True, text=True
    )
    assert result.returncode != 0
    assert 'addressName must name a reserved regional internal address' in result.stderr


@pytest.mark.parametrize('digest', ['a' * 64, 'b' * 64])
def test_batch_warm_fallback_rolls_with_primary_image_in_the_same_release(digest):
    directory = CHARTS / 'diarizer'
    output = subprocess.check_output(
        [
            'helm',
            'template',
            'prod-omi-diarizer-batch',
            str(directory),
            '--namespace',
            'prod-omi-backend',
            '-f',
            str(directory / 'prod_omi_diarizer_values.yaml'),
            '-f',
            str(directory / 'prod_omi_diarizer_batch_values.yaml'),
            '--set-string',
            'image.digest=sha256:' + digest,
        ],
        text=True,
    )
    documents = [obj for obj in yaml.safe_load_all(output) if obj]
    burst = {(obj['kind'], obj['metadata']['name']): (obj, '') for obj in documents}
    assert len(documents) == len(burst)  # No duplicate Helm resource identities.
    warm_deploy = burst[('Deployment', 'prod-omi-diarizer-batch-fallback')][0]
    warm = warm_deploy['spec']['template']
    primary = object_for(burst, 'Deployment')
    assert warm_deploy['spec']['replicas'] == 1
    assert len([kind for kind, _ in burst if kind == 'HorizontalPodAutoscaler']) == 1
    assert len([kind for kind, _ in burst if kind == 'HTTPRoute']) == 1
    assert not any(kind == 'Ingress' for kind, _ in burst)
    assert warm['spec']['nodeSelector'] == {
        'service': 'diarizer-batch',
        'env': 'prod',
        'cloud.google.com/gke-nodepool': 'diarizer-batch-pool',
        'cloud.google.com/gke-provisioning': 'standard',
    }
    assert 'affinity' not in warm['spec']
    # One Helm upgrade renders both workloads from the same image/runtime spec.
    assert len([kind for kind, _ in burst if kind == 'Deployment']) == 2
    for deploy, other in [(warm_deploy, primary), (primary, warm_deploy)]:
        selector = deploy['spec']['selector']['matchLabels']
        assert not all(other['spec']['template']['metadata']['labels'].get(k) == v for k, v in selector.items())
    warm_container = warm['spec']['containers'][0]
    primary_pod = primary['spec']['template']
    assert warm['spec']['serviceAccountName'] == primary_pod['spec']['serviceAccountName']
    for key in ('image', 'command', 'env', 'resources', 'tolerations', 'startupProbe', 'readinessProbe'):
        if key == 'tolerations':
            assert warm['spec'][key] == primary_pod['spec'][key]
        else:
            assert warm_container[key] == primary_pod['spec']['containers'][0][key]
    assert warm_container['image'].endswith('@sha256:' + digest)
    for (kind, _), (service, _) in burst.items():
        if kind != 'Service':
            continue
        selector = service['spec']['selector']
        assert selector == {'app.kubernetes.io/name': 'diarizer', 'omi.ai/diarizer-batch-route': 'prod'}
        for template in (warm, primary_pod):
            assert all(template['metadata']['labels'].get(k) == v for k, v in selector.items())
        embedding = object_for(render('prod', 'diarizer'), 'Deployment')['spec']['template']
        assert not all(embedding['metadata']['labels'].get(k) == v for k, v in selector.items())
    assert object_for(burst, 'HorizontalPodAutoscaler')['spec']['maxReplicas'] + warm_deploy['spec']['replicas'] == 18


def test_batch_bootstrap_keeps_old_service_selectors_until_warm_floor_is_ready():
    directory = CHARTS / 'diarizer'
    args = ['helm', 'template', 'prod-omi-diarizer-batch', str(directory)]
    for filename in (
        'prod_omi_diarizer_values.yaml',
        'prod_omi_diarizer_batch_values.yaml',
        'prod_omi_diarizer_batch_bootstrap_values.yaml',
    ):
        args += ['-f', str(directory / filename)]
    args += ['--set-string', 'image.tag=bootstrap-contract']
    objects = [obj for obj in yaml.safe_load_all(subprocess.check_output(args, text=True)) if obj]
    deployments = [obj for obj in objects if obj['kind'] == 'Deployment']
    assert len(deployments) == 2
    for deploy in deployments:
        assert (
            deploy['spec']['template']['spec']['nodeSelector']['cloud.google.com/gke-nodepool'] == 'diarizer-batch-pool'
        )
    for service in (obj for obj in objects if obj['kind'] == 'Service'):
        assert service['spec']['selector'] == {
            'app.kubernetes.io/name': 'diarizer',
            'app.kubernetes.io/instance': 'prod-omi-diarizer-batch',
        }
    # Drain stage retains 17 primary + 1 warm. Only the final rollback upgrade
    # removes the drained warm Deployment and restores 18 primary replicas.
    hpa = next(obj for obj in objects if obj['kind'] == 'HorizontalPodAutoscaler')
    assert hpa['spec']['maxReplicas'] == 17
    unsafe = subprocess.run(args + ['--set', 'autoscaling.maxReplicas=18'], capture_output=True, text=True)
    assert unsafe.returncode != 0
    assert 'primary replicas plus the warm fallback exceed' in unsafe.stderr
    rollback = list(
        yaml.safe_load_all(
            subprocess.check_output(
                args + ['--set', 'warmFallback.enabled=false', '--set', 'autoscaling.maxReplicas=18'], text=True
            )
        )
    )
    rollback_deployments = [obj for obj in rollback if obj and obj['kind'] == 'Deployment']
    assert len(rollback_deployments) == 1
    assert (
        rollback_deployments[0]['spec']['template']['spec']['nodeSelector']['cloud.google.com/gke-nodepool']
        == 'diarizer-batch-pool'
    )
    assert (
        next(obj for obj in rollback if obj and obj['kind'] == 'HorizontalPodAutoscaler')['spec']['maxReplicas'] == 18
    )
