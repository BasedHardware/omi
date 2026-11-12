#!/usr/bin/env python3
"""One-user, one-page operator tool. Dry-run unless --apply is explicit."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.action_item_completion_backfill import backfill_completion_page


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uid', required=True)
    parser.add_argument('--cursor')
    parser.add_argument('--limit', type=int, default=400)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    print(json.dumps(backfill_completion_page(args.uid, apply=args.apply, cursor=args.cursor, limit=args.limit)))


if __name__ == '__main__':
    main()
