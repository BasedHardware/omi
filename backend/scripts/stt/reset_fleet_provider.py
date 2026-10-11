#!/usr/bin/env python3
"""Reset one fleet-wide STT provider bench and recent score after operator repair.

Dry-run is the default. Run in the intended environment with REDIS_DB_HOST,
REDIS_DB_PORT and REDIS_DB_PASSWORD already supplied; never print credentials.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import redis

from config import live_stt_state

PROVIDERS = ('modulate', 'soniox', 'deepgram', 'parakeet')
MAX_SCORE_KEYS = 1000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('provider', choices=PROVIDERS)
    parser.add_argument('--execute', action='store_true', help='delete only the named provider state after review')
    args = parser.parse_args()
    if live_stt_state.stage() == 'unknown':
        parser.error('OMI_ENV_STAGE must be one of local, offline, dev, prod')
    if args.provider == 'parakeet':
        if not live_stt_state.family_endpoint('parakeet'):
            parser.error('HOSTED_PARAKEET_API_URL is required for parakeet')
    elif not live_stt_state.family_credential(args.provider):
        parser.error(f'credential env is required for {args.provider}')
    if not os.getenv('REDIS_DB_HOST'):
        parser.error('REDIS_DB_HOST is required')
    client = redis.Redis(
        host=os.environ['REDIS_DB_HOST'],
        port=int(os.getenv('REDIS_DB_PORT', '6379')),
        password=os.getenv('REDIS_DB_PASSWORD'),
        socket_connect_timeout=0.075,
        socket_timeout=0.075,
        retry_on_timeout=False,
    )
    prefix = live_stt_state.fleet_prefix(args.provider)
    keys: list[bytes | str] = [
        live_stt_state.fleet_state_key(args.provider),
        live_stt_state.fleet_probe_key(args.provider),
        live_stt_state.fleet_state_key(args.provider, account=True),
        live_stt_state.fleet_probe_key(args.provider, account=True),
    ]
    # The score prefix is provider-anchored; collect before deleting so an
    # unexpected cardinality cannot cause a partial reset.
    for key in client.scan_iter(match=f'{prefix}:score:{args.provider}:*', count=100):
        keys.append(key)
        if len(keys) > MAX_SCORE_KEYS:
            raise RuntimeError('score key cap exceeded; no keys deleted')
    print(f'provider={args.provider} matching_keys={len(keys)} execute={args.execute}')
    if args.execute:
        client.delete(*keys)
        print('fleet provider state reset')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
