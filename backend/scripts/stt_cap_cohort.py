#!/usr/bin/env python3
"""Write the runtime STT cohort without printing private tokens. Dry run by default."""

import argparse
import os
from pathlib import Path
import sys

from google.cloud import firestore

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.rollout_cohorts import COLLECTION, parse_cohort
from database.rollout_cohorts import STT_CAP_DOCUMENT


def main(argv=None, *, client_factory=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', choices=('based-hardware', 'based-hardware-dev'), required=True)
    parser.add_argument('--environment', choices=('prod', 'dev'), required=True)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--pct', type=int, choices=range(101), metavar='0..100')
    choice.add_argument('--all', action='store_true')
    choice.add_argument('--deny', action='store_true')
    choice.add_argument('--tokens-file', type=Path, help='Private UTF-8 token file, never printed')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    if (args.environment == 'prod') != (args.project == 'based-hardware'):
        # A mismatched pair would overwrite the other environment's control doc and deny its cohort.
        parser.error('environment must match project: prod=based-hardware, dev=based-hardware-dev')
    try:
        if args.tokens_file:
            with args.tokens_file.open(encoding='utf-8') as handle:
                tokens = handle.read(65537).strip()
            if len(tokens) > 65536:
                raise ValueError('oversized tokens')
        else:
            tokens = 'all' if args.all else '' if args.deny else f'pct:{args.pct}'
        if tokens and parse_cohort(tokens) is None:
            raise ValueError('invalid tokens')
    except (OSError, UnicodeError, ValueError):
        print('Invalid token input; no tokens or file path are logged.', file=sys.stderr)
        return 2
    if not args.apply:
        print('Dry run: valid cohort; no reads or writes.')
        return 0
    tier = 'prod-operator' if args.project == 'based-hardware' else 'dev-operator'
    if os.getenv('GCP_AGENT_TIER') != tier or not os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
        print('Select the matching GCP operator tier before applying.', file=sys.stderr)
        return 2
    try:
        client = (client_factory or firestore.Client)(project=args.project)
        client.collection(COLLECTION).document(STT_CAP_DOCUMENT).set(
            {'environment': args.environment, 'tokens': tokens}, timeout=3.0, retry=None
        )
    except Exception:
        print('Cohort write failed; no tokens or SDK error are logged. Retry the idempotent command.', file=sys.stderr)
        return 1
    print('Cohort written; allow about 60 seconds for healthy process caches. Verify all pod metrics.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
