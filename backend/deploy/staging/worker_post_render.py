#!/usr/bin/env python3
"""Helm post-renderer for the staging batch worker: add staging identity and fence env.

The shared worker chart (frozen for the prod track) has no extra-env hook. Staging needs the
worker's Firestore client on the `staging` database in based-hardware-dev, and the boot fence
needs the deployment identity. This reads rendered manifests on stdin, appends env to the
Deployment container named `worker`, and writes them to stdout.

Env sources, in order (a later source may not redefine an earlier name):
1. STAGING_ENV below: fixed staging identifiers, never secrets.
2. ``--env-file``: committed staging worker config (``worker_env.yaml``): plain ``NAME: value``
   entries, or ``NAME: {secretKeyRef: {name, key}}`` for a k8s Secret (never inline secrets).
3. ``--set NAME=VALUE``: a deploy-time rehearsal override (deploy.sh --worker-set), not committed.

``--replicas N`` (deploy.sh --worker-replicas, default 0) sets the Deployment's replica count. The
shared chart refuses replicaCount < 1 because prod's queue sampling runs in workers; staging has no
HPA and its GPUs are on demand (2026-10-20), so the worker idles at 0 and is scaled up for replays.

``--probe-configmap NAME`` (deploy.sh --worker-probe) runs the worker through a staging-only
measurement wrapper mounted from that ConfigMap; the worker module and its arguments are
otherwise unchanged.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

STAGING_ENV = {
    'OMI_DEPLOYMENT': 'staging',
    'GOOGLE_CLOUD_PROJECT': 'based-hardware-dev',
    'OMI_CUSTOMER_DATA_PROJECT': 'based-hardware-dev',
    'FIRESTORE_DATABASE_ID': 'staging',
    'FIREBASE_AUTH_PROJECT_ID': 'based-hardware-dev',
    # Code default is the prod bucket; the staging fence requires an explicit staging value.
    'BUCKET_PRIVATE_CLOUD_SYNC': 'based-hardware-dev-staging-sync',
    'MCP_AUTHORIZATION_SERVER_URL': 'https://staging.invalid',  # worker serves no MCP; fence-required
    'LIFECYCLE_EMAIL_FROM_ADDRESS': 'staging-no-send@based-hardware-dev.invalid',
    'SHARE_EMAIL_FROM_ADDRESS': 'staging-no-send@based-hardware-dev.invalid',
}
_NAME = re.compile(r'[A-Z][A-Z0-9_]*')
PROBE_MOUNT = '/asrctx-probe'


def _env_entries(env_file: Path | None, overrides: list[str]) -> list[dict]:
    entries = [{'name': name, 'value': value} for name, value in STAGING_ENV.items()]
    if env_file is not None and env_file.exists():
        for name, spec in (yaml.safe_load(env_file.read_text(encoding='utf-8')) or {}).items():
            if not _NAME.fullmatch(str(name)):
                raise SystemExit(f'invalid worker env name in {env_file.name}')
            if isinstance(spec, dict):
                ref = spec.get('secretKeyRef') or {}
                if set(spec) != {'secretKeyRef'} or not ref.get('name') or not ref.get('key'):
                    raise SystemExit(f'worker env {name}: only secretKeyRef mappings are allowed')
                entries.append({'name': name, 'valueFrom': {'secretKeyRef': {'name': ref['name'], 'key': ref['key']}}})
            else:
                entries.append({'name': name, 'value': str(spec)})
    for item in overrides:
        name, _, value = item.partition('=')
        if not _NAME.fullmatch(name):
            raise SystemExit('invalid --set name')
        entries.append({'name': name, 'value': value})
    return entries


def patch(docs: list, env_entries: list[dict], probe_configmap: str | None = None, replicas: int | None = None) -> list:
    patched = 0
    if replicas is not None:
        if replicas < 0:
            raise SystemExit('--replicas must be >= 0')
        if any(isinstance(doc, dict) and doc.get('kind') == 'HorizontalPodAutoscaler' for doc in docs):
            raise SystemExit('--replicas with an HPA rendered; refusing (staging runs autoscaling.enabled false)')
    for doc in docs:
        if not isinstance(doc, dict) or doc.get('kind') != 'Deployment':
            continue
        if replicas is not None:
            doc['spec']['replicas'] = replicas
        pod = doc['spec']['template']['spec']
        for container in pod['containers']:
            if container.get('name') != 'worker':
                continue
            env = container.setdefault('env', [])
            names = {entry['name'] for entry in env}
            for entry in env_entries:
                if entry['name'] in names:
                    raise SystemExit(f'worker already sets {entry["name"]}; refusing to override')
                names.add(entry['name'])
                env.append(entry)
            if probe_configmap:
                command = container.get('command') or []
                if command[-2:] != ['-m', 'diarizer.batch_pipeline_runtime']:
                    raise SystemExit('unexpected worker command; refusing to wrap it')
                container['command'] = [*command[:-2], f'{PROBE_MOUNT}/asrctx_probe.py']
                container.setdefault('volumeMounts', []).append({'name': 'asrctx-probe', 'mountPath': PROBE_MOUNT})
                pod.setdefault('volumes', []).append({'name': 'asrctx-probe', 'configMap': {'name': probe_configmap}})
                if 'PYTHONPATH' not in names:
                    # The wrapper runs as a script, so put the worker's /app tree on the path.
                    env.append({'name': 'PYTHONPATH', 'value': '/app'})
            patched += 1
    if patched != 1:
        raise SystemExit(f'expected exactly one worker container, patched {patched}')
    return docs


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or '').split('\n\n')[0])
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--set', action='append', default=[], dest='overrides')
    parser.add_argument('--probe-configmap')
    parser.add_argument('--replicas', type=int)
    args = parser.parse_args()
    docs = [doc for doc in yaml.safe_load_all(sys.stdin) if doc is not None]
    entries = _env_entries(args.env_file, args.overrides)
    yaml.safe_dump_all(patch(docs, entries, args.probe_configmap, args.replicas), sys.stdout, sort_keys=False)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
