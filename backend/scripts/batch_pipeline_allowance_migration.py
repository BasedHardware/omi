#!/usr/bin/env python3
# LIFECYCLE: permanent
"""SCA-2195 allowance parking migration. Dry-run is count-only and the default."""

import argparse
import json
import logging
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.batch_pipeline_allowance_migration import RowRateLimiter, apply_page, counts
from database.batch_pipeline_store import FirestoreStore
from utils.executors import shutdown_executors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('prod', 'dev'), required=True)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-reviewed-rollout-go', action='store_true')
    parser.add_argument('--max-pages', type=int, default=1)
    parser.add_argument('--concurrency', type=int, default=1, help='concurrent owners, 1..32 (default: sequential)')
    parser.add_argument('--max-rows-per-second', type=float, help='shared transaction-attempt rate, including retries')
    args = parser.parse_args()
    if args.apply and (args.dry_run or not args.confirm_reviewed_rollout_go):
        parser.error('apply requires reviewed migration and rollout go; cannot combine with dry-run')
    if not 1 <= args.max_pages <= 10000:
        parser.error('max-pages must be 1..10000')
    if not 1 <= args.concurrency <= 32:
        parser.error('concurrency must be 1..32')
    try:
        limiter = RowRateLimiter(args.max_rows_per_second)
    except ValueError as error:
        parser.error(str(error))
    if args.stage == 'prod' and (
        os.getenv('FIRESTORE_EMULATOR_HOST')
        or os.getenv('GCP_AGENT_TIER') != ('prod-operator' if args.apply else 'ro-prod')
    ):
        parser.error('wrong identity for production operation')
    logging.disable(logging.CRITICAL)
    os.environ['OMI_ENV_STAGE'] = args.stage
    store = FirestoreStore(f'batch_pipeline_{args.stage}')
    if not args.apply:
        print(json.dumps(counts(store)))
        return
    try:
        for _ in range(args.max_pages):
            report = apply_page(store, time.time(), concurrency=args.concurrency, rate_limiter=limiter)
            print(json.dumps(report), flush=True)
            if report['complete']:
                break
    finally:
        if args.concurrency > 1:
            shutdown_executors()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print(json.dumps({'errors': 1}))
        sys.exit(1)
