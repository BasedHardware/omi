#!/usr/bin/env python3
"""Reject backend releases below the floor published on origin/main."""

import argparse
import json
import re
import subprocess
import sys
from datetime import date

FLOOR_FILE = 'origin/main:backend/deploy/release_floor.json'
STAMP = 'OMI_BACKEND_RELEASE_SHA'


def is_sha(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{40}', value) and value != '0' * 40


def read_floor():
    try:
        raw = subprocess.check_output(['git', 'show', FLOOR_FILE], stderr=subprocess.PIPE)
        config = json.loads(raw)
        if not (
            isinstance(config, dict)
            and is_sha(config.get('floor'))
            and isinstance(config.get('reason'), str)
            and config['reason'].strip()
            and isinstance(config.get('since'), str)
            and date.fromisoformat(config['since']).isoformat() == config['since']
        ):
            raise ValueError('invalid floor metadata')
        return config['floor']
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        raise ValueError(f'Cannot read a valid backend release floor from {FLOOR_FILE}.') from exc


def revision_sha(revision, project, region):
    try:
        raw = subprocess.check_output(
            [
                'gcloud',
                'run',
                'revisions',
                'describe',
                revision,
                '--project',
                project,
                '--region',
                region,
                '--format=json',
            ]
        )
        containers = json.loads(raw)['spec']['containers']
        stamps = [
            entry.get('value')
            for container in containers
            for entry in container.get('env', [])
            if entry.get('name') == STAMP
        ]
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f'Cannot read release stamp from revision {revision}.') from exc
    if len(stamps) != 1 or not is_sha(stamps[0]):
        raise ValueError(f'Revision {revision} must have exactly one valid {STAMP} stamp.')
    return stamps[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--sha')
    target.add_argument('--revision')
    parser.add_argument('--project')
    parser.add_argument('--region')
    args = parser.parse_args()
    if args.revision and (not args.project or not args.region):
        parser.error('--revision requires --project and --region')
    try:
        floor = read_floor()
        sha = args.sha if args.sha is not None else revision_sha(args.revision, args.project, args.region)
        if not is_sha(sha):
            raise ValueError('Backend release SHA must be a nonzero, lowercase, full commit SHA.')
        object_type = subprocess.check_output(['git', 'cat-file', '-t', sha], stderr=subprocess.PIPE, text=True)
        if object_type.strip() != 'commit':
            raise ValueError(f'Backend release {sha} is not a commit.')
        if subprocess.run(['git', 'merge-base', '--is-ancestor', floor, sha]).returncode:
            raise ValueError(
                f'Backend release {sha} does not satisfy release floor {floor}. '
                'For purge recovery, deploy a floor-qualified release with '
                'CONVERSATION_BATCH_PURGE_COALESCING_ENABLED=false.'
            )
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        print(f'ERROR: Backend release floor rejected the target. {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
