#!/usr/bin/env python3
"""Add/remove private cohort membership with one merge write and no UID output."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database.rollout_cohorts import COLLECTION, COHORT_ENVS, valid_uid


def main(argv=None, *, client_factory=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uid-file', required=True, type=Path, help='Private file containing one UID; never printed')
    parser.add_argument('--cohort', required=True, action='append', choices=sorted(COHORT_ENVS))
    parser.add_argument('--project', choices=('based-hardware', 'based-hardware-dev'), required=True)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument('--add', action='store_true')
    operation.add_argument('--remove', action='store_true')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        '--dry-run', action='store_true', help='Validate input without credentials, reads or writes (default)'
    )
    mode.add_argument('--apply', action='store_true', help='Perform the merge write using the operator tier')
    args = parser.parse_args(argv)
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
            from google.cloud import firestore

            client_factory = firestore.Client
        client = client_factory(project=args.project)
        # Explicit false is a tombstone: removing a member also revokes legacy-env fallback.
        client.collection(COLLECTION).document(uid).set(
            {'cohorts': {name: args.add for name in set(args.cohort)}}, merge=True, timeout=3.0, retry=None
        )
    except Exception:
        # SDK errors may include the full document path. Never print or re-raise them.
        print('Cohort write failed; no UID or SDK error is logged. Retry the idempotent command.', file=sys.stderr)
        return 1
    print('Membership ' + ('added' if args.add else 'removed') + '; allow 60 seconds for process caches.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
