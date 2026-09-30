#!/usr/bin/env python3
"""Admin smart-merge undo. Defaults to a read-only plan; never prints content."""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
from typing import Sequence

from utils.conversations.smart_merge import unmerge_conversation


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uid', required=True)
    parser.add_argument('--donor-id', required=True)
    parser.add_argument('--force', action='store_true', help='Allow survivor title/speaker curation')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true', help='Commit undo and run replayable follow-up')
    mode.add_argument('--dry-run', action='store_true', help='Read-only eligibility check (default)')
    args = parser.parse_args(argv)
    previous_disable = logging.root.manager.disable
    try:
        # The normal processing path has legacy stdout and provider logging.
        # Even an apply may print only our closed ids/counts/reason projection.
        logging.disable(logging.CRITICAL)
        with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            result = unmerge_conversation(args.uid, args.donor_id, force=args.force, dry_run=not args.apply)
        output = {
            'donor_id': args.donor_id,
            'survivor_id': result.survivor_id,
            'donor_ids': list(result.donor_ids),
            'donor_count': len(result.donor_ids),
            'removed_segment_count': result.removed_segments,
            'reason': result.reason,
        }
        status = 2 if result.outcome == 'ineligible' else 0
    except Exception:
        output = {'donor_id': args.donor_id, 'reason': 'error'}
        status = 1
    finally:
        logging.disable(previous_disable)
    print(json.dumps(output, sort_keys=True))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
