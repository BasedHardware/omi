#!/usr/bin/env python3
"""Prepare or check the primary worker CAS using private Kubernetes captures."""

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import sys

import yaml

PRIMARY = 'prod-omi-batch-pipeline-worker'
NAMESPACE = 'prod-omi-backend'
TARGETS = {PRIMARY: 'worker', PRIMARY + '-t4': 'worker', 'record-seal-worker': 'seal'}
ALLOWLIST = 'BATCH_PIPELINE_UID_ALLOWLIST'
DEPTH = 'BATCH_PIPELINE_WORKER_PIPELINE_DEPTH'
PINNED_IMAGE = re.compile(r'[^@\s]+@sha256:[0-9a-f]{64}')


def deployments(capture):
    result = {}
    for item in capture['items']:
        metadata = item['metadata']
        name = metadata['name']
        if item['kind'] != 'Deployment' or metadata['namespace'] != NAMESPACE or name not in TARGETS or name in result:
            raise ValueError('unexpected Deployment in capture')
        result[name] = item
    if result.keys() != TARGETS.keys():
        raise ValueError('all three Deployment captures are required')
    return result


def preview(document):
    metadata = document['metadata']
    if (
        document['kind'] != 'ConfigMap'
        or metadata['name'] != PRIMARY + '-preview'
        or metadata['namespace'] != NAMESPACE
    ):
        raise ValueError('expected the redacted primary-only preview')
    summary = json.loads(document['data']['comparison.json'])
    if summary.keys() != TARGETS.keys():
        raise ValueError('preview must cover all three Deployments')
    return summary


def target_container(deployment):
    name = deployment['metadata']['name']
    containers = deployment['spec']['template']['spec']['containers']
    [(index, target)] = [(i, item) for i, item in enumerate(containers) if item['name'] == TARGETS[name]]
    return index, target


def binding(container):
    entries = [item for item in container.get('env', []) if item['name'] == ALLOWLIST]
    if not entries:
        return 'absent', None
    [entry] = entries
    if entry.get('valueFrom'):
        return 'reference', entry['valueFrom']
    if entry.get('value'):
        return 'literal', entry['value']
    return 'empty', None


def plan(live, summary):
    expected = deepcopy(live)
    for name, entry in summary.items():
        _, target = target_container(live[name])
        if entry['liveImage'] != target['image'] or entry['allowlist'] != {
            'name': ALLOWLIST,
            'kind': binding(target)[0],
        }:
            raise ValueError('preview and capture disagree')
        if name != PRIMARY and entry['image'] != target['image']:
            raise ValueError('preview would change a sibling image')

    primary = expected[PRIMARY]
    metadata = primary['metadata']
    uid, revision = metadata['uid'], metadata['resourceVersion']
    if not uid or not revision:
        raise ValueError('missing primary object identity')
    index, worker = target_container(primary)
    [(env_index, depth)] = [(i, env) for i, env in enumerate(worker['env']) if env['name'] == DEPTH]
    target = summary[PRIMARY]
    old_depth, new_depth = depth['value'], target['depth']
    if (
        depth.get('valueFrom')
        or old_depth not in ('3', '4')
        or new_depth not in ('3', '4')
        or target['liveDepth'] != old_depth
    ):
        raise ValueError('expected a literal primary depth of 3 or 4')
    old_image, new_image = worker['image'], target['image']
    if not all(PINNED_IMAGE.fullmatch(image) for image in (old_image, new_image)):
        raise ValueError('both primary images must be pinned by digest')

    prefix = f'/spec/template/spec/containers/{index}'
    patch = [
        {'op': 'test', 'path': '/metadata/uid', 'value': uid},
        {'op': 'test', 'path': '/metadata/resourceVersion', 'value': revision},
    ]
    for path, before, after in (
        (prefix + '/image', old_image, new_image),
        (f'{prefix}/env/{env_index}/value', old_depth, new_depth),
    ):
        if before != after:
            patch.extend(
                [
                    {'op': 'test', 'path': path, 'value': before},
                    {'op': 'replace', 'path': path, 'value': after},
                ]
            )
    worker['image'], depth['value'] = new_image, new_depth
    return patch, expected


def compare(live, expected, observed):
    passed = True
    for name in TARGETS:
        _, before = target_container(live[name])
        _, after = target_container(observed[name])
        old_binding, new_binding = binding(before), binding(after)
        old_uid = expected[name]['metadata']['uid']
        spec_equal = old_uid == observed[name]['metadata']['uid'] and {
            key: value for key, value in expected[name]['spec'].items() if key != 'replicas'
        } == {key: value for key, value in observed[name]['spec'].items() if key != 'replicas'}
        allowlist_equal = old_binding == new_binding
        print(
            f'{name}: {ALLOWLIST} ({old_binding[0]}) equal={str(allowlist_equal).lower()}; '
            f'Deployment spec and identity equal={str(spec_equal).lower()}'
        )
        passed &= spec_equal and allowlist_equal
    return passed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-json', type=Path, required=True)
    parser.add_argument('--preview-yaml', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--patch-output', type=Path, help='write a new mode-0600 patch file')
    mode.add_argument('--observed-json', type=Path, help='check dry-run or post-update observations')
    args = parser.parse_args()
    try:
        live = deployments(json.loads(args.live_json.read_text()))
        patch, expected = plan(live, preview(yaml.safe_load(args.preview_yaml.read_text())))
        if args.observed_json:
            observed = deployments(json.loads(args.observed_json.read_text()))
            return 0 if compare(live, expected, observed) else 1
        with os.fdopen(os.open(args.patch_output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as handle:
            json.dump(patch, handle)
    except (OSError, AttributeError, KeyError, IndexError, TypeError, ValueError, yaml.YAMLError):
        print('Carrier check failed. Inspect the captures privately.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
