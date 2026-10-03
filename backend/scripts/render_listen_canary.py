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
    container = pod['spec']['containers'][0]
    container['image'] = image
    current_env = {entry['name']: entry for entry in container.get('env', [])}
    current_env.update({name: {'name': name, 'value': value} for name, value in env.items()})
    container['env'] = list(current_env.values())
    return result


def render(environment: str, image: str, replicas: int, env: dict[str, str]) -> dict:
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
    return detach(deployment, image, replicas, env)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', choices=('dev', 'prod'), required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--replicas', type=int, default=2)
    parser.add_argument('--env', action='append', default=[], metavar='NAME=VALUE')
    args = parser.parse_args()
    env = {}
    for item in args.env:
        name, sep, value = item.partition('=')
        if not sep or not re.fullmatch(r'[A-Z][A-Z0-9_]*', name):
            parser.error('--env requires NAME=VALUE')
        env[name] = value
    print(yaml.safe_dump(render(args.environment, args.image, args.replicas, env), sort_keys=False), end='')


if __name__ == '__main__':
    main()
