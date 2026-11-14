#!/usr/bin/env python3
# LIFECYCLE: permanent
"""Bounded projection-finish clock backfill. Dry-run by default; counts only."""

import argparse
import json
import logging
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.batch_pipeline_projection_finish_backfill import stamp_page
from database.batch_pipeline_store import FirestoreStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('prod', 'dev'), required=True)
    parser.add_argument('--max-pages', type=int, default=1)
    parser.add_argument('--page-size', type=int, default=200)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-writers-deployed', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.max_pages <= 10000 or not 1 <= args.page_size <= 200:
        parser.error('max-pages must be 1..10000 and page-size 1..200')
    if args.apply and not args.confirm_writers_deployed:
        parser.error('deploy unconditional clock writers everywhere before applying')
    if args.stage == 'prod' and (
        os.getenv('FIRESTORE_EMULATOR_HOST')
        or os.getenv('GCP_AGENT_TIER') != ('prod-operator' if args.apply else 'ro-prod')
    ):
        parser.error('wrong identity for requested production operation')
    if not args.apply and args.max_pages != 1:
        parser.error('dry-run inspects one page at the durable checkpoint')
    logging.disable(logging.CRITICAL)
    os.environ['OMI_ENV_STAGE'] = args.stage
    store = FirestoreStore(f'batch_pipeline_{args.stage}')
    for _ in range(args.max_pages):
        report = stamp_page(store, time.time(), size=args.page_size, apply=args.apply)
        print(json.dumps({**report, 'apply': args.apply}), flush=True)
        if report['complete']:
            break


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print(json.dumps({'operation': 'projection-finish-backfill-v1', 'outcome': 'error'}))
        sys.exit(1)
