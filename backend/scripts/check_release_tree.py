#!/usr/bin/env python3
"""Promotion identity (contract (i)): prod qualifies tree equality, not digest identity.

Staging serves an integration SHA stamped with `OMI_RELEASE_TREE=<git tree hash>`.
The M3 squash merge to main is made when integration already contains the latest
main, so the merge commit's tree must equal that staging-qualified tree. This
check runs as the train pre-check; a mismatch means main moved after
qualification, and the captain re-syncs, redeploys staging and re-runs the
parity smoke before the train (swarm-plan §5).

    check_release_tree.py tree <rev>
    check_release_tree.py verify --sha <main-merge-sha> --qualified-tree <tree>
    check_release_tree.py verify --sha <main-merge-sha> --from-staging [--project based-hardware-dev]

`--from-staging` reads OMI_RELEASE_TREE from the revision each staging Cloud Run
service actually serves (status.traffic), never from spec.template, and requires
every service to agree. Exit codes: 0 equal, 1 mismatch or not on main, 2 the
qualified tree could not be read.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from typing import Any

TREE = re.compile(r'^[0-9a-f]{40}$')
STAGING_SERVICES = (
    'backend-staging',
    'backend-sync-staging',
    'backend-sync-backfill-staging',
    'backend-integration-staging',
)
RELEASE_TREE_KEY = 'OMI_RELEASE_TREE'

Runner = Callable[[Sequence[str]], str]


class TreeCheckError(RuntimeError):
    pass


def run(args: Sequence[str]) -> str:
    proc = subprocess.run(list(args), capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise TreeCheckError(f'{args[0]} {args[1] if len(args) > 1 else ""} failed: {proc.stderr.strip()[:300]}')
    return proc.stdout


def tree_of(rev: str, runner: Runner = run) -> str:
    tree = runner(['git', 'rev-parse', f'{rev}^{{tree}}']).strip()
    if not TREE.match(tree):
        raise TreeCheckError(f'not a tree hash for {rev}: {tree!r}')
    return tree


def on_main(sha: str, runner: Runner = run, main_ref: str = 'origin/main') -> bool:
    try:
        runner(['git', 'merge-base', '--is-ancestor', sha, main_ref])
    except TreeCheckError:
        return False
    return True


def _serving_env(service: dict[str, Any], revision: dict[str, Any]) -> dict[str, Any]:
    containers = (revision.get('spec') or {}).get('containers') or []
    ingress = next((c for c in containers if c.get('ports')), containers[0] if containers else {})
    return {e.get('name'): e.get('value') for e in ingress.get('env') or [] if isinstance(e, dict)}


def staging_release_tree(project: str, region: str, runner: Runner = run) -> str:
    trees: dict[str, str | None] = {}
    for name in STAGING_SERVICES:
        location = [f'--project={project}', f'--region={region}', '--format=json']
        service = json.loads(runner(['gcloud', 'run', 'services', 'describe', name, *location]))
        serving = [t for t in (service.get('status') or {}).get('traffic') or [] if (t.get('percent') or 0) > 0]
        if len(serving) != 1 or serving[0].get('percent') != 100:
            raise TreeCheckError(f'{name}: traffic is not 100% on one revision')
        revision = json.loads(runner(['gcloud', 'run', 'revisions', 'describe', serving[0]['revisionName'], *location]))
        trees[name] = _serving_env(service, revision).get(RELEASE_TREE_KEY)
    values = set(trees.values())
    if len(values) != 1 or None in values:
        raise TreeCheckError(f'staging services disagree on {RELEASE_TREE_KEY}: {trees}')
    tree = values.pop()
    if not isinstance(tree, str) or not TREE.match(tree):
        raise TreeCheckError(f'staging {RELEASE_TREE_KEY} is not a tree hash: {tree!r}')
    return tree


def main(argv: Sequence[str] | None = None, *, runner: Runner = run) -> int:
    parser = argparse.ArgumentParser(description='Promotion identity: main merge tree == staging-qualified tree.')
    sub = parser.add_subparsers(dest='command', required=True)
    tree_cmd = sub.add_parser('tree')
    tree_cmd.add_argument('rev')
    verify = sub.add_parser('verify')
    verify.add_argument('--sha', required=True)
    source = verify.add_mutually_exclusive_group(required=True)
    source.add_argument('--qualified-tree')
    source.add_argument('--from-staging', action='store_true')
    verify.add_argument('--project', default='based-hardware-dev')
    verify.add_argument('--region', default='us-central1')
    verify.add_argument('--main-ref', default='origin/main')
    args = parser.parse_args(argv)

    try:
        if args.command == 'tree':
            print(tree_of(args.rev, runner))
            return 0
        if args.from_staging:
            qualified = staging_release_tree(args.project, args.region, runner)
        else:
            qualified = args.qualified_tree.strip().lower()
            if not TREE.match(qualified):
                raise TreeCheckError('--qualified-tree must be a 40-hex git tree hash')
    except TreeCheckError as exc:
        print(f'UNREADABLE: {exc}', file=sys.stderr)
        return 2
    try:
        actual = tree_of(args.sha, runner)
    except TreeCheckError as exc:
        print(f'UNREADABLE: {exc}', file=sys.stderr)
        return 2
    if not on_main(args.sha, runner, args.main_ref):
        print(f'MISMATCH: {args.sha} is not on {args.main_ref}', file=sys.stderr)
        return 1
    if actual != qualified:
        print(
            f'MISMATCH: {args.sha} tree {actual} != staging-qualified {qualified}. '
            'Main moved after qualification: re-sync integration, redeploy staging, re-run the parity smoke.',
            file=sys.stderr,
        )
        return 1
    print(f'TREE_EQUAL {args.sha} {actual}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
