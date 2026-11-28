#!/usr/bin/env python3
"""Refuse a prod image-only roll unless the target's live record token lease env serves.

SCA-3748: once the non-lease path is deleted, any lease mode other than unset or
``serve`` is the runtime kill. An image-only roll keeps the live env and swaps
only the image, so rolling new code over a live ``off`` or ``shadow`` config
would engage the kill. Before any write, this guard reads the target workload
and the ConfigMaps its lease env references, and refuses unless the live vector
is ``serve`` at 100 percent, a 1800-7200 s lease and a positive release epoch.

Reads only: ``kubectl get`` of the named workloads and of the ConfigMaps they
reference. It never reads a Secret. It prints a non-secret JSON receipt.

``--require KIND/NAME`` must carry all four keys in its container ``env``, as the
runtime manifest renders them for Listen and Pusher. ``--allow-unset KIND/NAME``
may carry none of them (the runtime then serves, its unset default); any key it
does carry, directly or through an ``envFrom`` ConfigMap, must form the same
serving vector.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from typing import Any, Callable

KEYS = (
    'RECORD_TOKEN_LEASE_MODE',
    'RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT',
    'RECORD_TOKEN_LEASE_SECONDS',
    'RECORD_TOKEN_LEASE_DEPLOYED_AT',
)
KINDS = {'deployment', 'statefulset', 'daemonset', 'cronjob'}


class Refused(ValueError):
    """The live lease env does not prove serve; no write may follow."""


def kubectl(namespace: str, *args: str) -> dict[str, Any]:
    command = ['kubectl', '-n', namespace, 'get', *args, '-o', 'json']
    done = subprocess.run(command, check=True, capture_output=True, text=True, timeout=60)
    return json.loads(done.stdout)


def pod_spec(workload: dict[str, Any]) -> dict[str, Any]:
    spec = workload.get('spec') or {}
    if (workload.get('kind') or '').lower() == 'cronjob':
        spec = ((spec.get('jobTemplate') or {}).get('spec')) or {}
    return ((spec.get('template') or {}).get('spec')) or {}


def validate(vector: dict[str, str], where: str) -> dict[str, Any]:
    missing = [key for key in KEYS if key not in vector]
    if missing:
        raise Refused(f'{where}: live lease env is missing {", ".join(missing)}')
    mode = vector['RECORD_TOKEN_LEASE_MODE'].strip().lower()
    if mode != 'serve':
        raise Refused(f'{where}: live RECORD_TOKEN_LEASE_MODE is {mode!r}; the new image would engage the kill')
    try:
        percent = float(vector['RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT'])
        seconds = float(vector['RECORD_TOKEN_LEASE_SECONDS'])
        epoch = float(vector['RECORD_TOKEN_LEASE_DEPLOYED_AT'])
    except ValueError as error:
        raise Refused(f'{where}: live lease vector is not numeric') from error
    if percent != 100:
        raise Refused(f'{where}: live serve percent is not 100')
    if not (math.isfinite(seconds) and 1800 <= seconds <= 7200):
        raise Refused(f'{where}: live lease seconds are outside 1800-7200')
    if not (math.isfinite(epoch) and epoch > 0):
        raise Refused(f'{where}: live serve requires a positive release epoch')
    return {'mode': 'serve', 'serve_percent': 100, 'seconds': seconds, 'deployed_at': epoch}


def check(
    namespace: str,
    required: list[str],
    allow_unset: list[str],
    read: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    read = read or kubectl
    if not required and not allow_unset:
        raise Refused('name at least one target workload')
    maps: dict[str, dict[str, str]] = {}

    def config_map(name: str, where: str) -> dict[str, str]:
        if name not in maps:
            body = read(namespace, 'configmap', name)
            maps[name] = {str(k): str(v) for k, v in (body.get('data') or {}).items()}
        return maps[name]

    receipt: dict[str, Any] = {'namespace': namespace, 'workloads': {}}
    for target, strict in [(name, True) for name in required] + [(name, False) for name in allow_unset]:
        kind, _, name = target.partition('/')
        if kind.lower() not in KINDS or not name:
            raise Refused(f'unsupported target {target!r}')
        workload = read(namespace, f'{kind.lower()}/{name}')
        containers = pod_spec(workload).get('containers') or []
        if not containers:
            raise Refused(f'{target}: no containers in the live pod template')
        vectors = {}
        for container in containers:
            where = f'{target}/{container.get("name")}'
            vector: dict[str, str] = {}
            for entry in container.get('env') or []:
                key = entry.get('name')
                if key not in KEYS:
                    continue
                if 'value' in entry:
                    vector[key] = str(entry['value'])
                    continue
                ref = (entry.get('valueFrom') or {}).get('configMapKeyRef')
                if not isinstance(ref, dict) or set((entry.get('valueFrom') or {})) != {'configMapKeyRef'}:
                    raise Refused(f'{where}: {key} must be a literal or a ConfigMap key reference')
                data = config_map(ref.get('name', ''), where)
                if ref.get('key') in data:
                    vector[key] = data[ref['key']]
                elif not ref.get('optional'):
                    raise Refused(f'{where}: {key} references a missing ConfigMap key')
            if strict:
                vectors[container.get('name')] = validate(vector, where)
                continue
            # envFrom applies only to keys env does not set (env wins).
            for source in container.get('envFrom') or []:
                ref = source.get('configMapRef')
                if isinstance(ref, dict):
                    data = config_map(ref.get('name', ''), where)
                    prefix = source.get('prefix') or ''
                    for key in KEYS:
                        if key not in vector and prefix + key in data:
                            vector[key] = data[prefix + key]
                # A Secret is never read; lease rollout config is not a credential.
            vectors[container.get('name')] = validate(vector, where) if vector else 'unset (runtime serves)'
        receipt['workloads'][target] = vectors
    receipt['verdict'] = 'serve'
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n', 1)[0])
    parser.add_argument('--namespace', required=True)
    parser.add_argument('--require', action='append', default=[])
    parser.add_argument('--allow-unset', action='append', default=[])
    args = parser.parse_args(argv)
    try:
        receipt = check(args.namespace, args.require, args.allow_unset)
    except (Refused, subprocess.SubprocessError, OSError, json.JSONDecodeError) as error:
        print(f'::error title=Record token lease live guard::{error}', file=sys.stderr)
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
