#!/usr/bin/env python3
"""Render a CAS-protected repair-only patch, preserving live policy and secrets.

This offline operator tool never calls Kubernetes. Its output contains the live
CronJob's private env references/policy, so write only to an operator-private file.
It cannot target a Deployment or change serving-role policy/producer-lease gates.
"""

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import re

import yaml


def repair_patch(live, documents):
    if (live.get('kind'), live.get('metadata', {}).get('name'), live.get('metadata', {}).get('namespace')) != (
        'CronJob',
        'record-seal-repair',
        'prod-omi-backend',
    ):
        raise ValueError('live target must be prod-omi-backend/CronJob/record-seal-repair')
    version = live['metadata'].get('resourceVersion')
    if not version:
        raise ValueError('live resource version required')
    matches = [
        d
        for d in documents
        if d and d.get('kind') == 'CronJob' and d.get('metadata', {}).get('name') == 'record-seal-repair'
    ]
    if len(matches) != 1:
        raise ValueError('exactly one rendered repair CronJob required')
    desired = matches[0]['spec']
    template = deepcopy(live['spec']['jobTemplate'])
    job, target = template['spec'], desired['jobTemplate']['spec']
    for key in ('completionMode', 'completions', 'parallelism', 'activeDeadlineSeconds', 'backoffLimit'):
        job[key] = target[key]
    pod, new = job['template']['spec'], target['template']['spec']
    if len(pod['containers']) != 1 or pod['containers'][0]['name'] != 'repair':
        raise ValueError('unexpected live repair containers')
    before, after = pod['containers'][0], new['containers'][0]
    if not re.fullmatch(r'[^\s@]+@sha256:[0-9a-f]{64}', after['image']):
        raise ValueError('immutable repair image digest required')
    for key in ('image', 'command', 'resources'):
        before[key] = deepcopy(after[key])
    if 'args' in after:
        before['args'] = after['args']
    else:
        before.pop('args', None)
    env = {entry['name']: entry for entry in before['env']}
    if env.get('RECORD_SEAL_REPAIR_JOBS', {}).get('value', 'on') == 'off' and job['parallelism'] > 1:
        raise ValueError('parallel repair requires live job discovery')
    # Preserve every existing gate and the complete effective serving-role policy.
    wanted = {entry['name']: entry for entry in after['env']}
    env['RECORD_SEAL_REPAIR_WORKERS'] = wanted['RECORD_SEAL_REPAIR_WORKERS']
    for name in ('RECORD_SEAL_REPAIR_FRESH_ENABLED',):
        if name not in env:
            env[name] = wanted[name]
    before['env'] = list(env.values())
    pod['affinity'] = deepcopy(new['affinity'])
    if new.get('tolerations'):
        pod['tolerations'] = deepcopy(new['tolerations'])
    else:
        pod.pop('tolerations', None)
    for key, left, right in [('volumes', pod, new), ('volumeMounts', before, after)]:
        kept = [entry for entry in left.get(key, []) if entry['name'] != 'partition']
        left[key] = kept + [deepcopy(entry) for entry in right.get(key, []) if entry['name'] == 'partition']
    job['template'].setdefault('metadata', {}).setdefault('labels', {}).update(target['template']['metadata']['labels'])
    return [
        {'op': 'test', 'path': '/metadata/resourceVersion', 'value': version},
        {'op': 'replace', 'path': '/spec/schedule', 'value': desired['schedule']},
        {'op': 'replace', 'path': '/spec/jobTemplate', 'value': template},
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-json', type=Path, required=True)
    parser.add_argument('--rendered-yaml', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    patch = repair_patch(
        json.loads(args.live_json.read_text()), list(yaml.safe_load_all(args.rendered_yaml.read_text()))
    )
    with os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as output:
        os.fchmod(output.fileno(), 0o600)
        json.dump(patch, output)
        output.write('\n')


if __name__ == '__main__':
    main()
