#!/usr/bin/env python3
"""Offline repair-only prepare/check/rollback packets. Never calls Kubernetes.

Private packets contain effective policy. Every output is mode0600. A packet
binds one object UID, before/after spec hashes and an exact reversible delta.
"""

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

import yaml

NAME = 'record-seal-repair'
POOL = 'cloud.google.com/gke-nodepool'
FRESH = 'RECORD_SEAL_REPAIR_FRESH_ENABLED'
COMMAND = ['python', 'scripts/record_seal_repair_job.py']
IMAGE = re.compile(r'[^\s@]+@sha256:[0-9a-f]{64}')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def target(doc):
    require(
        (doc.get('kind'), doc.get('metadata', {}).get('name'), doc.get('metadata', {}).get('namespace'))
        == ('CronJob', NAME, 'prod-omi-backend'),
        'wrong repair target',
    )
    require(bool(doc['metadata'].get('resourceVersion')) and bool(doc['metadata'].get('uid')), 'identity required')
    job = doc['spec']['jobTemplate']['spec']
    pod = job['template']['spec']
    require(len(pod['containers']) == 1 and pod['containers'][0]['name'] == 'repair', 'unexpected containers')
    return job, pod, pod['containers'][0]


def node_affinity(pool) -> dict[str, Any]:
    return {
        'nodeAffinity': {
            'requiredDuringSchedulingIgnoredDuringExecution': {
                'nodeSelectorTerms': [{'matchExpressions': [{'key': POOL, 'operator': 'In', 'values': [pool]}]}]
            }
        }
    }


def validate_before(live, expected_image):
    job, pod, container = target(live)
    require(IMAGE.fullmatch(expected_image) and container['image'] == expected_image, 'before image changed')
    require(
        live['spec']['schedule'] in ('*/5 * * * *', '* * * * *') and live['spec']['concurrencyPolicy'] == 'Forbid',
        'unexpected cadence',
    )
    require(job.get('activeDeadlineSeconds') == 1680 and job.get('backoffLimit') == 0, 'unexpected job budget')
    require(
        job.get('completionMode', 'NonIndexed') in ('NonIndexed', 'Indexed')
        and job.get('completions', 1) == 1
        and job.get('parallelism', 1) == 1,
        'expected one shard',
    )
    require('backoffLimitPerIndex' not in job and 'maxFailedIndexes' not in job, 'unexpected index failure policy')
    require(container.get('command') == COMMAND and not container.get('args'), 'unexpected entrypoint')
    require(
        container.get('resources')
        == {'requests': {'cpu': '4', 'memory': '4Gi'}, 'limits': {'cpu': '4', 'memory': '8Gi'}},
        'unexpected resources',
    )
    require(not pod.get('nodeSelector') and not pod.get('hostname'), 'incompatible pod selector/hostname')
    require(pod.get('affinity') == node_affinity('batch-pipeline-pool'), 'unexpected original affinity')
    tolerations = [
        {'effect': 'NoSchedule', 'key': 'omi.ai/batch-pipeline', 'operator': 'Equal', 'value': 'true'},
        {'effect': 'NoSchedule', 'key': 'nvidia.com/gpu', 'operator': 'Equal', 'value': 'present'},
    ]
    require(pod.get('tolerations') == tolerations, 'unexpected tolerations')
    require(
        pod.get('volumes') == [{'name': 'tmp', 'emptyDir': {'sizeLimit': '64Mi'}}]
        and container.get('volumeMounts') == [{'name': 'tmp', 'mountPath': '/tmp'}],
        'unexpected mounts',
    )
    env = container.get('env', [])
    names = [e['name'] for e in env]
    require(len(names) == len(set(names)), 'duplicate env names')
    by_name = {e['name']: e for e in env}
    require(
        by_name.get('RECORD_SEAL_REPAIR_WORKERS') == {'name': 'RECORD_SEAL_REPAIR_WORKERS', 'value': '8'},
        'unexpected worker count',
    )
    require(by_name.get('RECORD_SEAL_REPAIR_JOBS', {}).get('value') == 'on', 'job discovery required')
    require(FRESH not in by_name or by_name[FRESH] == {'name': FRESH, 'value': 'true'}, 'fresh kill switch is off')


def repair_patch(live, documents, *, expected_image):
    validate_before(live, expected_image)
    matches = [d for d in documents if d and d.get('kind') == 'CronJob' and d.get('metadata', {}).get('name') == NAME]
    require(len(matches) == 1, 'exactly one rendered repair target required')
    wanted = matches[0]
    job, pod, after = (
        wanted['spec']['jobTemplate']['spec'],
        wanted['spec']['jobTemplate']['spec']['template']['spec'],
        wanted['spec']['jobTemplate']['spec']['template']['spec']['containers'][0],
    )
    count = job.get('completions')
    require(
        type(count) is int
        and 2 <= count <= 8
        and job.get('parallelism') == count
        and job.get('completionMode') == 'Indexed',
        'unexpected desired shard shape',
    )
    require(
        job.get('activeDeadlineSeconds') == 1680
        and job.get('backoffLimit') == count
        and job.get('backoffLimitPerIndex') == 0
        and job.get('maxFailedIndexes') == count,
        'unexpected desired failure/deadline policy',
    )
    require(
        IMAGE.fullmatch(after['image'])
        and after.get('command') == COMMAND
        and after.get('args') == ['--shards', str(count), '--shard-index-file', '/etc/repair-partition/index'],
        'unexpected desired entrypoint/image',
    )
    require(
        after.get('resources') == {'requests': {'cpu': '3', 'memory': '4Gi'}, 'limits': {'cpu': '4', 'memory': '8Gi'}},
        'unexpected desired resources',
    )
    require(
        wanted['spec']['schedule'] == '* * * * *' and not pod.get('tolerations') and not pod.get('nodeSelector'),
        'unexpected desired scheduling',
    )
    expected_affinity = node_affinity('api-pool')
    expected_affinity['podAntiAffinity'] = {
        'requiredDuringSchedulingIgnoredDuringExecution': [
            {
                'labelSelector': {'matchLabels': {'app.kubernetes.io/name': NAME}},
                'topologyKey': 'kubernetes.io/hostname',
            }
        ]
    }
    require(pod.get('affinity') == expected_affinity, 'unexpected desired affinity')
    partition = {
        'name': 'partition',
        'downwardAPI': {
            'defaultMode': 420,
            'items': [
                {
                    'path': 'index',
                    'fieldRef': {
                        'apiVersion': 'v1',
                        'fieldPath': "metadata.annotations['batch.kubernetes.io/job-completion-index']",
                    },
                }
            ],
        },
    }
    mounts = {'name': 'partition', 'mountPath': '/etc/repair-partition', 'readOnly': True}
    # CronJob nested defaulting in Kubernetes v1.35 supplies these two fields.
    # Accept either Helm spelling, but always receipt the server's exact shape.
    # Conflicting defaults and all other unexpected fields remain forbidden.
    partition_volumes = deepcopy([v for v in pod.get('volumes', []) if v['name'] == 'partition'])
    for volume in partition_volumes:
        downward = volume.get('downwardAPI')
        if isinstance(downward, dict):
            downward.setdefault('defaultMode', 420)
            for item in downward.get('items', []):
                field = item.get('fieldRef')
                if isinstance(field, dict):
                    field.setdefault('apiVersion', 'v1')
    require(
        partition_volumes == [partition]
        and [v for v in after.get('volumeMounts', []) if v['name'] == 'partition'] == [mounts],
        'unexpected partition volume',
    )
    desired = deepcopy(live)
    dj, dp, dc = target(desired)
    desired['spec']['schedule'] = wanted['spec']['schedule']
    for key in (
        'completionMode',
        'completions',
        'parallelism',
        'backoffLimit',
        'backoffLimitPerIndex',
        'maxFailedIndexes',
    ):
        dj[key] = job[key]
    # No policy map, secret refs, KSA, labels, other env or other resources copied.
    for key in ('image', 'args', 'resources'):
        dc[key] = deepcopy(after[key])
    dp['affinity'] = deepcopy(pod['affinity'])
    dp.pop('tolerations', None)
    dp['volumes'].append(deepcopy(partition))
    dc['volumeMounts'].append(deepcopy(mounts))
    if not any(e['name'] == FRESH for e in dc['env']):
        dc['env'].append({'name': FRESH, 'value': 'true'})
    return patches(live, desired['spec']), desired


def patches(current, desired_spec):
    return [
        {'op': 'test', 'path': '/metadata/uid', 'value': current['metadata']['uid']},
        {'op': 'test', 'path': '/metadata/resourceVersion', 'value': current['metadata']['resourceVersion']},
        {'op': 'test', 'path': '/spec', 'value': current['spec']},
        {'op': 'replace', 'path': '/spec/schedule', 'value': desired_spec['schedule']},
        {'op': 'replace', 'path': '/spec/jobTemplate', 'value': desired_spec['jobTemplate']},
    ]


def delta(before, after, prefix=''):
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(set(before) | set(after)):
            path = prefix + '/' + key.replace('~', '~0').replace('/', '~1')
            if key not in before or key not in after:
                result.append(
                    {
                        'path': path,
                        'beforePresent': key in before,
                        'afterPresent': key in after,
                        'before': before.get(key),
                        'after': after.get(key),
                    }
                )
            else:
                result.extend(delta(before[key], after[key], path))
        return result
    return [] if before == after else [{'path': prefix, 'before': before, 'after': after}]


def prepare(live, documents, expected_image):
    patch, desired = repair_patch(live, documents, expected_image=expected_image)
    receipt = {
        'version': 1,
        'uid': live['metadata']['uid'],
        'beforeSpec': live['spec'],
        'afterSpec': desired['spec'],
        'beforeSpecSha256': sha(live['spec']),
        'afterSpecSha256': sha(desired['spec']),
        'approvedDelta': delta(live['spec'], desired['spec'], '/spec'),
    }
    reverse = patches(desired, live['spec'])
    reverse[1]['value'] = '__FRESH_READBACK_RESOURCE_VERSION_REQUIRED__'
    return patch, receipt, reverse


def check(doc, receipt, state):
    target(doc)
    require(doc['metadata']['uid'] == receipt['uid'], 'object replaced')
    for name in ('before', 'after'):
        require(sha(receipt[name + 'Spec']) == receipt[name + 'SpecSha256'], 'receipt hash mismatch')
    require(delta(receipt['beforeSpec'], receipt['afterSpec'], '/spec') == receipt['approvedDelta'], 'delta changed')
    require(sha(doc['spec']) == receipt[state + 'SpecSha256'], 'unapproved server spec delta')


def rollback(current, receipt):
    check(current, receipt, 'after')
    return patches(current, receipt['beforeSpec'])


def dump(path, value):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as out:
        os.fchmod(out.fileno(), 0o600)
        json.dump(value, out, indent=2)
        out.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--live-json', type=Path, required=True)
    p.add_argument('--rendered-yaml', type=Path, required=True)
    p.add_argument('--expected-image', required=True)
    p.add_argument('--out', type=Path, required=True)
    for action in ('check-object', 'verify', 'rollback'):
        p = sub.add_parser(action)
        p.add_argument('--receipt', type=Path, required=True)
        p.add_argument('--object', type=Path, required=True)
        if action != 'rollback':
            p.add_argument('--state', choices=('before', 'after'), default='after')
        else:
            p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'prepare':
        patch, receipt, inverse = prepare(
            json.loads(args.live_json.read_text()),
            list(yaml.safe_load_all(args.rendered_yaml.read_text())),
            args.expected_image,
        )
        args.out.mkdir(mode=0o700, parents=True, exist_ok=True)
        dump(args.out / 'forward.json', patch)
        dump(args.out / 'receipt.json', receipt)
        dump(args.out / 'rollback.template.json', inverse)
    else:
        receipt = json.loads(args.receipt.read_text())
        current = json.loads(args.object.read_text())
        if args.mode == 'rollback':
            dump(args.output, rollback(current, receipt))
        else:
            check(current, receipt, args.state)


if __name__ == '__main__':
    main()
