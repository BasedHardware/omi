#!/usr/bin/env python3
"""Read-only by default; bounded, digest-bound operator re-wake of a private key-only plan."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--plan-sha256')
    parser.add_argument('--run-id', required=True, help='Reuse this id after an enqueue error; do not mint another.')
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--limit', type=int, default=1)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    raw = args.plan.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    keys = json.loads(raw)
    if (
        not isinstance(keys, list)
        or not keys
        or any(not isinstance(k, str) or not re.fullmatch('[0-9a-f]{64}', k) for k in keys)
    ):
        parser.error('plan must be a nonempty list of outbox keys, without account content')
    if len(keys) != len(set(keys)) or not 1 <= args.limit <= 25 or not 0 <= args.offset < len(keys):
        parser.error('unique keys, a valid offset and a limit between 1 and 25 are required')
    if args.apply and (args.plan_sha256 != digest or os.getenv('GCP_AGENT_TIER') != 'prod-operator'):
        parser.error('apply requires the exact plan digest and the prod-operator tier')
    if os.getenv('GCP_AGENT_TIER') not in {'ro-prod', 'prod-operator'}:
        parser.error('select ro-prod for inspection or prod-operator for apply')
    if os.getenv('FIRESTORE_EMULATOR_HOST') or os.getenv('SERVICE_ACCOUNT_JSON'):
        parser.error('operator tool requires the selected agent tier, without runtime/emulator credential overrides')
    from google.cloud import firestore
    from utils.enrichment.redrive import redrive

    os.environ['OMI_ENV_STAGE'] = 'prod'
    os.environ['SYNC_TASKS_PROJECT'] = 'based-hardware'
    os.environ['SYNC_TASKS_LOCATION'] = 'us-central1'
    os.environ['DEMAND_PROCESSING_ENABLED'] = 'false'
    client = firestore.Client(project='based-hardware')
    counts: Counter[str] = Counter()
    selected = keys[args.offset : args.offset + args.limit]
    for key in selected:
        try:
            counts[redrive(client, key, args.run_id, now=time.time(), apply=args.apply)] += 1
        except Exception as error:
            # Stop on first failure. Rerunning the same page/id keeps the repair names stable.
            print(json.dumps({'counts': dict(counts), 'failure_class': type(error).__name__, 'offset': args.offset}))
            return 1
    print(
        json.dumps(
            {
                'apply': args.apply,
                'plan_sha256': digest,
                'offset': args.offset,
                'next_offset': args.offset + len(selected),
                'total': len(keys),
                'counts': dict(counts),
            }
        )
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
