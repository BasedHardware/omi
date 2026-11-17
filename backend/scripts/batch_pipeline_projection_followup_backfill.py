#!/usr/bin/env python3
# LIFECYCLE: permanent
"""Bounded projection-followup clock backfill. Dry-run by default; counts only."""

import argparse
import json
import logging
import math
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.batch_pipeline_projection_followup_backfill import stamp_page
from database.batch_pipeline_store import FirestoreStore


class PageRateLimiter:
    """Pace admitted page rows with one page of burst, before any store access.

    This bounds newly admitted candidate rows, not physical RPCs or SDK retries.
    An operator uses one driver; another invocation has an independent budget.
    """

    def __init__(self, rate: float, size: int, *, clock=None, sleep=None):
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError('max-rows-per-second must be finite and positive')
        self.interval = size / rate
        if not math.isfinite(self.interval):
            raise ValueError('max-rows-per-second is too small for the page size')
        self.clock = clock or time.monotonic
        self.sleep = sleep or time.sleep
        self.next_page_at = self.clock()

    def acquire(self):
        now = self.clock()
        while now < self.next_page_at:
            # A finite but very low rate must not overflow the platform sleep
            # or look like a hung operator. No customer values are printed.
            remaining = self.next_page_at - now
            print(
                json.dumps(
                    {'operation': 'projection-followup-backfill-v1', 'outcome': 'pacing', 'wait_seconds': remaining}
                ),
                file=sys.stderr,
                flush=True,
            )
            self.sleep(min(60.0, remaining))
            now = self.clock()
        # Slow IO earns no catch-up burst. Keep one limiter across all pages.
        self.next_page_at = now + self.interval
        if not math.isfinite(self.next_page_at):
            raise ValueError('page-rate deadline overflow')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('prod', 'dev'), required=True)
    parser.add_argument('--max-pages', type=int, default=1)
    parser.add_argument('--page-size', type=int, default=200)
    parser.add_argument(
        '--max-rows-per-second',
        type=float,
        default=10.0,
        help='new candidate rows/s (default: 10); page-size burst; SDK retries are not separately paced',
    )
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-writers-deployed', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.max_pages <= 10000 or not 1 <= args.page_size <= 200:
        parser.error('max-pages must be 1..10000 and page-size 1..200')
    try:
        limiter = PageRateLimiter(args.max_rows_per_second, args.page_size)
    except ValueError as error:
        parser.error(str(error))
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
        if args.apply:
            limiter.acquire()
        report = stamp_page(store, time.time(), size=args.page_size, apply=args.apply)
        print(json.dumps({**report, 'apply': args.apply}), flush=True)
        if report['complete']:
            break


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print(json.dumps({'operation': 'projection-followup-backfill-v1', 'outcome': 'error'}))
        sys.exit(1)
