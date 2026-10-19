#!/usr/bin/env python3
"""Operator-only one-owner real Dream session replay; product storage is read-only."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.dream_agent import enabled
from utils.rollout_cohorts import configure_rollout_runtime
from utils.dream_agent import run_pass


def main():
    configure_rollout_runtime()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uid', required=True, help='Authorized owner in the operator isolated pod')
    args = parser.parse_args()
    if not enabled():
        parser.error('DREAM_AGENT_ENABLED must be true; the global kill switch also stops replays')
    report = asyncio.run(run_pass(args.uid, dry_run=True))
    # Deliberate operator stdout, never a service metric or shared log. Gateway
    # provider accounting still runs; no admission, Review, notes or reports write.
    print(
        json.dumps(
            {
                key: report.get(key)
                for key in (
                    'status',
                    'stop_reason',
                    'size_bucket',
                    'turns',
                    'tool_counts',
                    'records_read',
                    'tokens',
                    'accounted_tokens',
                    'cost_usd_upper_bound',
                    'cached_tokens',
                    'cache_unreported_tokens',
                    'rejected',
                    'resubmits_succeeded',
                    'verifier_outcomes',
                    'proposed',
                    'outcomes',
                )
            },
            default=str,
            ensure_ascii=False,
        )
    )


if __name__ == '__main__':
    main()
