#!/usr/bin/env python3
"""Manage private cohorts and migrate live membership without UID output."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from google.cloud import firestore

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.rollout_cohorts import COLLECTION, COHORT_ENVS, valid_uid
from scripts.rollout_cohort_migration import migrate


def main(argv=None, *, client_factory=None, live_reader=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uid-file', type=Path, help='Private file containing one UID; never printed')
    parser.add_argument('--cohort', action='append', choices=sorted(COHORT_ENVS))
    parser.add_argument('--project', choices=('based-hardware', 'based-hardware-dev'), required=True)
    parser.add_argument('--environment', choices=('dev', 'prod'), required=True)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument('--add', action='store_true')
    operation.add_argument('--remove', action='store_true')
    operation.add_argument(
        '--seed-live', action='store_true', help='Copy current Cloud Run/Helm cohorts; default dry run'
    )
    operation.add_argument(
        '--verify-live', action='store_true', help='Read-only comparison of live cohorts and Firestore'
    )
    parser.add_argument('--kube-context', help='Explicit Kubernetes context for live Helm reads')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        '--dry-run', action='store_true', help='No writes (default); --seed-live reads live source counts'
    )
    mode.add_argument('--apply', action='store_true', help='Perform the merge write using the operator tier')
    args = parser.parse_args(argv)
    if args.seed_live or args.verify_live:
        if not args.kube_context or args.uid_file or args.cohort or args.project != 'based-hardware':
            parser.error(
                'live migration requires --kube-context, --project based-hardware, and no UID/cohort arguments'
            )
        if args.verify_live and (args.apply or args.dry_run):
            parser.error('--verify-live is read-only; omit --apply/--dry-run')
        if os.getenv('GCP_AGENT_TIER') != 'prod-operator' or not os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
            print('Select prod-operator for live inventory and the shared customer data plane.', file=sys.stderr)
            return 2
        try:
            kwargs = {'live_reader': live_reader} if live_reader is not None else {}
            return migrate(args, client_factory=client_factory or firestore.Client, **kwargs)
        except Exception:
            print(
                'Live migration failed; no UID, source payload or SDK error is logged. No deploy is safe.',
                file=sys.stderr,
            )
            return 1
    if args.uid_file is None or not args.cohort:
        parser.error('--add/--remove require --uid-file and --cohort')
    try:
        # A bound avoids accidentally reading a large payload. No path or value in errors.
        with args.uid_file.open(encoding='utf-8') as handle:
            uid = handle.read(1024).strip()
        if not valid_uid(uid) or '\n' in uid or '\r' in uid:
            raise ValueError('invalid input')
    except (OSError, UnicodeError, ValueError):
        print('Invalid UID file; expected one private UID.', file=sys.stderr)
        return 2
    if not args.apply:
        print('Dry run: one member, cohorts=' + ','.join(sorted(set(args.cohort))) + '; no reads or writes.')
        return 0
    tier = 'prod-operator' if args.project == 'based-hardware' else 'dev-operator'
    if os.getenv('GCP_AGENT_TIER') != tier or not os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
        print('Select the matching GCP operator tier before applying.', file=sys.stderr)
        return 2
    try:
        if client_factory is None:
            client_factory = firestore.Client
        client = client_factory(project=args.project)
        # Explicit false is a tombstone: removing a member also revokes legacy-env fallback.
        client.collection(COLLECTION).document(uid).set(
            {'cohorts': {args.environment: {name: args.add for name in set(args.cohort)}}},
            merge=True,
            timeout=3.0,
            retry=None,
        )
    except Exception:
        # SDK errors may include the full document path. Never print or re-raise them.
        print('Cohort write failed; no UID or SDK error is logged. Retry the idempotent command.', file=sys.stderr)
        return 1
    print('Membership ' + ('added' if args.add else 'removed') + '; allow 60 seconds for process caches.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
