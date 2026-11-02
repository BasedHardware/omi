#!/usr/bin/env python3
"""Reject non-additive GMP frontend Helm overlays without displaying object payloads."""

import argparse
import copy
import re
from pathlib import Path

import yaml

FRONTEND = 'prod-omi-gmp-query-frontend'
DATASOURCE_UID = 'gmp-cloud-run'
EXISTING_KSA = 'prod-omi-prometheus-stackdriver-exporter'
IMAGE = (
    'gke.gcr.io/prometheus-engine/frontend:v0.15.3-gke.0@'
    'sha256:615ba6fcb89717b7346de2746e18fd6d31979cf89eb7b3583c7cea05be827664'
)
NAMESPACE = 'prod-omi-monitoring'
FRONTEND_LABELS = {
    'app.kubernetes.io/name': 'gmp-query-frontend',
    'app.kubernetes.io/instance': FRONTEND,
}


class UniqueKeyLoader(yaml.SafeLoader):
    """Fail closed on YAML mappings whose earlier values would be discarded."""


def _unique_mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f'duplicate YAML key: {key}')
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def load_objects(text):
    return [obj for obj in yaml.load_all(text, Loader=UniqueKeyLoader) if obj]


def identity(obj):
    return obj['kind'], obj.get('metadata', {}).get('namespace', ''), obj['metadata']['name']


def _index(objects):
    result = {}
    for obj in objects:
        key = identity(obj)
        if key in result:
            raise ValueError(f'duplicate rendered object identity: {key}')
        result[key] = obj
    return result


def validate_render(baseline, candidate):
    """Return bounded findings; never expose Secret data or arbitrary config values."""
    old, new = _index(baseline), _index(candidate)
    errors = []
    expected = {(kind, NAMESPACE, FRONTEND) for kind in ('Deployment', 'Service', 'PodDisruptionBudget')}
    if set(old) - set(new):
        errors.append('existing objects removed (including possible warm-up Service)')
    if set(new) - set(old) != expected:
        errors.append('added resources must be exactly frontend Deployment, Service and PDB')
    datasource_changes = 0
    for key, before in old.items():
        after = new.get(key)
        if before == after or after is None:
            continue
        if key[0] != 'ConfigMap' or 'datasource.yaml' not in before.get('data', {}):
            errors.append(f'existing object changed: {key[0]}/{key[2]}')
            continue
        datasource_changes += 1
        left, right = copy.deepcopy(before), copy.deepcopy(after)
        try:
            original = yaml.load(left['data'].pop('datasource.yaml'), Loader=UniqueKeyLoader)
            updated = yaml.load(right['data'].pop('datasource.yaml'), Loader=UniqueKeyLoader)
            existing = original.pop('datasources')
            sources = updated.pop('datasources')
        except (KeyError, TypeError, ValueError, yaml.YAMLError):
            errors.append('invalid datasource provisioning document')
            continue
        if left != right or original != updated:
            errors.append('datasource ConfigMap changed beyond datasource addition')
        if updated.get('prune') or updated.get('deleteDatasources'):
            errors.append('datasource deletion/pruning configured')
        by_uid = {ds.get('uid'): ds for ds in sources}
        if len(by_uid) != len(sources):
            errors.append('duplicate datasource UID')
        if any(by_uid.get(ds.get('uid')) != ds for ds in existing):
            errors.append('existing datasource removed or modified')
        if set(by_uid) - {ds.get('uid') for ds in existing} != {DATASOURCE_UID}:
            errors.append('datasource additions differ from gmp-cloud-run')
        ds = by_uid.get(DATASOURCE_UID, {})
        if (
            ds.get('isDefault') is not False
            or ds.get('type') != 'prometheus'
            or ds.get('access') != 'proxy'
            or ds.get('url') != f'http://{FRONTEND}.{NAMESPACE}.svc:9090'
            or ds.get('secureJsonData')
            or ds.get('jsonData', {}).get('httpMethod') != 'GET'
        ):
            errors.append('GMP datasource must be non-default, internal, GET and credential-free')
    if datasource_changes != 1:
        errors.append('expected exactly one additive datasource ConfigMap change')
    deployment = new.get(('Deployment', NAMESPACE, FRONTEND), {}).get('spec', {})
    pod = deployment.get('template', {}).get('spec', {})
    containers = pod.get('containers', [])
    labels = deployment.get('template', {}).get('metadata', {}).get('labels', {})
    if deployment.get('selector', {}).get('matchLabels') != FRONTEND_LABELS or any(
        labels.get(key) != value for key, value in FRONTEND_LABELS.items()
    ):
        errors.append('frontend Deployment selector and pod labels must match the frontend identity')
    if deployment.get('replicas') != 2 or len(containers) != 1:
        errors.append('frontend must have two replicas and one bounded container')
    if pod.get('serviceAccountName') != EXISTING_KSA:
        errors.append('frontend must reuse the verified read-only KSA')
    if containers:
        container = containers[0]
        if container.get('image') != IMAGE or not re.search(r'@sha256:[0-9a-f]{64}$', container.get('image', '')):
            errors.append('frontend image differs from verified public digest')
        if container.get('args') != ['--web.listen-address=:9090', '--query.project-id=based-hardware']:
            errors.append('frontend flags differ from verified ADC/project configuration')
        if container.get('env') or container.get('envFrom') or container.get('volumeMounts') or pod.get('volumes'):
            errors.append('frontend must not introduce token files, secret mounts or explicit credentials')
        if not container.get('resources', {}).get('limits', {}).get('memory'):
            errors.append('frontend memory must be bounded')
        ports = {port.get('name'): port.get('containerPort') for port in container.get('ports', [])}
        if ports.get('web') != 9090:
            errors.append('frontend must expose its web listener on container port 9090')
        for key, path in [('readinessProbe', '/-/ready'), ('livenessProbe', '/-/healthy')]:
            probe = container.get(key, {}).get('httpGet', {})
            if probe.get('path') != path or probe.get('port') not in ['web', 9090]:
                errors.append(f'frontend {key} must check the documented health endpoint on its web listener')
    required = (
        pod.get('affinity', {}).get('podAntiAffinity', {}).get('requiredDuringSchedulingIgnoredDuringExecution', [])
    )
    if not any(
        term.get('topologyKey') == 'kubernetes.io/hostname'
        and term.get('labelSelector', {}).get('matchLabels') == FRONTEND_LABELS
        for term in required
    ):
        errors.append('frontend replicas require hostname separation')
    service = new.get(('Service', NAMESPACE, FRONTEND), {}).get('spec', {})
    if service.get('type') != 'ClusterIP' or service.get('externalIPs') or service.get('loadBalancerIP'):
        errors.append('frontend Service must remain internal ClusterIP')
    if service.get('selector') != FRONTEND_LABELS:
        errors.append('frontend Service must select the frontend pods')
    service_ports = service.get('ports', [])
    if len(service_ports) != 1 or any(
        port.get('name') != 'web'
        or port.get('port') != 9090
        or port.get('targetPort') not in ['web', 9090]
        or port.get('protocol', 'TCP') != 'TCP'
        for port in service_ports
    ):
        errors.append('frontend Service must route TCP port 9090 to the frontend web listener')
    pdb = new.get(('PodDisruptionBudget', NAMESPACE, FRONTEND), {}).get('spec', {})
    if pdb.get('minAvailable') != 1 or pdb.get('maxUnavailable') is not None:
        errors.append('frontend PDB must preserve one available replica')
    if pdb.get('selector', {}).get('matchLabels') != FRONTEND_LABELS:
        errors.append('frontend PDB must select the frontend pods')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    args = parser.parse_args()
    try:
        findings = validate_render(load_objects(args.baseline.read_text()), load_objects(args.candidate.read_text()))
    except (OSError, yaml.YAMLError, ValueError, KeyError, TypeError, AttributeError):
        # Helm renders can include Secrets: parser exceptions can quote their
        # source lines, so neither exception text nor tracebacks may escape.
        print('FAIL: invalid or unreadable rendered Kubernetes documents')
        return 1
    for finding in findings:
        print(f'FAIL: {finding}')
    if not findings:
        print('PASS: existing resources/datasources preserved; only frontend and non-default GMP datasource added')
    return bool(findings)


if __name__ == '__main__':
    raise SystemExit(main())
