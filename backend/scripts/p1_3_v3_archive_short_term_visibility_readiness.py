#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from utils.memory.v3.archive_visibility_readiness import evaluate_archive_short_term_visibility_readiness


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Read-only memory /v3 archive unavailable + stale short-term not default-visible readiness proof.'
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Evaluate the local readiness proof. This remains read-only and BLOCKED.',
    )
    args = parser.parse_args()

    report = evaluate_archive_short_term_visibility_readiness()
    if args.execute:
        report['mode'] = 'execute'
    else:
        report['mode'] = 'default'
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
