"""Dry-run or apply an audited target reset using the serving runtime's Redis env.

Run from backend/: python scripts/reset_live_stt_cost_gate.py --help
Never prints Redis coordinates, credentials, state keys or user evidence.
"""

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from redis.asyncio import Redis

from utils.stt.live_cost_reset import reset_cost_target


async def run(args):
    async with Redis(
        host=os.getenv('REDIS_DB_HOST') or 'localhost',
        port=int(os.getenv('REDIS_DB_PORT', '6379')),
        password=os.getenv('REDIS_DB_PASSWORD'),
        socket_connect_timeout=2,
        socket_timeout=2,
        retry_on_timeout=False,
        decode_responses=True,
    ) as redis:
        async with asyncio.timeout(20):
            report = await reset_cost_target(
                redis,
                target=args.target,
                environment=args.environment,
                reason=args.reason,
                stage=args.stage,
                apply=args.apply,
            )
        print(json.dumps(report, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True)
    parser.add_argument('--environment', required=True, choices=('prod', 'dev', 'local', 'offline'))
    parser.add_argument('--reason', required=True, help='Content-free incident/change ID; no user text')
    parser.add_argument('--stage', type=int, choices=(0, 100), default=100)
    parser.add_argument(
        '--apply', action='store_true', help='Write reset and 30-day audit atomically (default: dry run)'
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    try:
        asyncio.run(run(args))
    except Exception as exc:
        # Redis errors can contain connection details; report only the type.
        print(f'cost reset failed: {type(exc).__name__}; inspect runtime configuration or contention', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
