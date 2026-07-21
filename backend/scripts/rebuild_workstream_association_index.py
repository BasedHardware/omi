#!/usr/bin/env python3
"""Rebuild the derived workstream-association index from authoritative rows."""

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from utils.memory.memory_system import list_canonical_cohort_uids
from utils.task_intelligence.workstream_index import rebuild_workstream_association_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--uid', action='append', dest='uids')
    group.add_argument('--all-canonical-users', action='store_true')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    uids = list_canonical_cohort_uids() if args.all_canonical_users else args.uids
    reports = [rebuild_workstream_association_index(uid).model_dump(mode='json') for uid in uids]
    print(json.dumps({'reports': reports}, sort_keys=True))
    return 0 if all(not report['failed_workstream_ids'] for report in reports) else 1


if __name__ == '__main__':
    raise SystemExit(main())
