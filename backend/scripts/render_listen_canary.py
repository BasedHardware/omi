#!/usr/bin/env python3
"""Render an independently owned listen Deployment; never contact a cluster."""

from __future__ import annotations

import argparse
import copy
import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / 'backend/charts/backend-listen'
IMAGE = re.compile(r'^gcr\.io/(based-hardware|based-hardware-dev)/backend@sha256:[0-9a-f]{64}$')


def detach(deployment: dict, image: str, replicas: int, env: dict[str, str]) -> dict:
    if not IMAGE.fullmatch(image):
        raise ValueError('use a backend image digest from the prod or dev registry')
    if not 1 <= replicas <= 60:
        raise ValueError('replicas must be 1..60')
    result = copy.deepcopy(deployment)
    metadata = result['metadata']
    metadata['name'] += '-canary'
    metadata.pop('annotations', None)
    metadata['labels'].pop('app.kubernetes.io/managed-by', None)
    metadata['labels']['track'] = 'canary'
    spec = result['spec']
    spec['replicas'] = replicas
    # Keep the Service's two labels, but narrow the canary controller to its
    # own pods. Never orphan its ReplicaSets: the historical main selector is
    # broader and cannot be changed in place on an existing Deployment.
    spec['selector']['matchLabels']['track'] = 'canary'
    pod = spec['template']
    pod['metadata']['labels'].pop('app.kubernetes.io/managed-by', None)
    pod['metadata']['labels']['track'] = 'canary'
    container = next(c for c in pod['spec']['containers'] if c['name'] == 'backend-listen')
    container['image'] = image
    current_env = {entry['name']: entry for entry in container.get('env', [])}
    current_env.update({name: {'name': name, 'value': value} for name, value in env.items()})
    container['env'] = list(current_env.values())
    return result


def render(environment: str, image: str, replicas: int, env: dict[str, str], control: dict | None = None) -> dict:
    release = f'{environment}-omi-backend-listen'
    rendered = subprocess.run(
        [
            'helm',
            'template',
            release,
            str(CHART),
            '-n',
            f'{environment}-omi-backend',
            '-f',
            str(CHART / f'{environment}_omi_backend_listen_values.yaml'),
            '--set-string',
            'image.tag=render-only',
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    deployment = next(doc for doc in yaml.safe_load_all(rendered) if doc and doc.get('kind') == 'Deployment')
    deployment['metadata']['namespace'] = f'{environment}-omi-backend'
    if control is not None:
        if (
            control.get('kind') != 'Deployment'
            or control.get('apiVersion') != 'apps/v1'
            or control.get('metadata', {}).get('name') != release
            or control.get('metadata', {}).get('namespace') != f'{environment}-omi-backend'
        ):
            raise ValueError('control snapshot must be the main listen Deployment in the selected namespace')
        selector = control['spec']['selector']
        labels = control['spec']['template']['metadata']['labels']
        expected = deployment['spec']['selector']['matchLabels']
        if (
            selector.get('matchExpressions')
            or any(labels.get(key) != value for key, value in expected.items())
            or any(labels.get(key) != value for key, value in selector.get('matchLabels', {}).items())
        ):
            raise ValueError('control pod labels do not match the chart Service selector')
        if len([c for c in control['spec']['template']['spec']['containers'] if c['name'] == 'backend-listen']) != 1:
            raise ValueError('control must contain exactly one backend-listen container')
        # The chart owns object shape; the explicit live snapshot owns actual
        # runtime settings, including manual Helm env overrides and scheduling.
        # Do not copy server metadata/status or Helm ownership annotations.
        deployment['spec']['template'] = copy.deepcopy(control['spec']['template'])
        deployment['spec']['selector'] = copy.deepcopy(selector)
        for key in ('strategy', 'progressDeadlineSeconds'):
            if key in control['spec']:
                deployment['spec'][key] = copy.deepcopy(control['spec'][key])
    return detach(deployment, image, replicas, env)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', choices=('dev', 'prod'), required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--replicas', type=int, default=2)
    parser.add_argument('--env', action='append', default=[], metavar='NAME=VALUE')
    parser.add_argument('--control-deployment', type=Path, help='coordinator-captured main Deployment YAML or JSON')
    args = parser.parse_args()
    env = {}
    for item in args.env:
        name, sep, value = item.partition('=')
        if not sep or not re.fullmatch(r'[A-Z][A-Z0-9_]*', name):
            parser.error('--env requires NAME=VALUE')
        env[name] = value
    if args.environment == 'prod' and args.control_deployment is None:
        parser.error('prod requires --control-deployment to preserve live configuration')
    control = yaml.safe_load(args.control_deployment.read_text()) if args.control_deployment else None
    if args.control_deployment and not isinstance(control, dict):
        parser.error('control snapshot must be a Deployment object')
    print(yaml.safe_dump(render(args.environment, args.image, args.replicas, env, control), sort_keys=False), end='')


if __name__ == '__main__':
    main()
