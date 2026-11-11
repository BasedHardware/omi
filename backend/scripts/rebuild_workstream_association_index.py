#!/usr/bin/env python3
"""Rebuild the derived workstream-association index from authoritative rows."""

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from utils.task_intelligence.workstream_index import rebuild_workstream_association_index

MAX_INDEX_REBUILD_UIDS = 100


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--uid', action='append', dest='uids')
    group.add_argument(
        '--all-users',
        action='store_true',
        help='Use WORKSTREAM_ASSOCIATION_UID_INVENTORY (bounded comma-separated UIDs); no unbounded scan is allowed.',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.all_users:
        raw = os.getenv('WORKSTREAM_ASSOCIATION_UID_INVENTORY', '')
        uids = sorted({uid.strip() for uid in raw.split(',') if uid.strip()})
        if not uids:
            raise SystemExit(
                'bounded workstream UID inventory is unavailable; provide WORKSTREAM_ASSOCIATION_UID_INVENTORY '
                'or explicit --uid values'
            )
        if len(uids) > MAX_INDEX_REBUILD_UIDS:
            raise SystemExit(
                f'WORKSTREAM_ASSOCIATION_UID_INVENTORY contains {len(uids)} UIDs, exceeding the '
                f'per-run bound of {MAX_INDEX_REBUILD_UIDS}; page the inventory or provide explicit --uid values'
            )
    else:
        uids = args.uids or []
    reports = [rebuild_workstream_association_index(uid).model_dump(mode='json') for uid in uids]
    print(json.dumps({'reports': reports}, sort_keys=True))
    return 0 if all(not report['failed_workstream_ids'] for report in reports) else 1


if __name__ == '__main__':
    raise SystemExit(main())
