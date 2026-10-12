"""One-account, metadata-only review expiration. Dry-run is the default.

Run from the backend image/pod with its configured Firestore identity. This
does not accept, reject, or delete memories. Counts describe eligible rows;
apply counts describe successful transitions, not all historical queue rows.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import logging
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database.review_queue import expire_review_conflicts


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse's default error can echo unrecognized argument values.
        super().error('Invalid arguments; see --help for required options and timestamp format.')


def _created_before(value: str) -> datetime:
    try:
        cutoff = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise argparse.ArgumentTypeError('created-before must be an ISO timestamp with a timezone') from None
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise argparse.ArgumentTypeError('created-before must include a timezone')
    return cutoff


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description='Expire old pending memory reviews without changing memories')
    parser.add_argument('--uid', required=True)
    parser.add_argument('--created-before', required=True, type=_created_before)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='Count eligible rows only (default)')
    mode.add_argument('--apply', action='store_true', help='Set eligible review rows to expired')
    args = parser.parse_args(argv)
    # Database/provider diagnostics may contain document paths. The operator
    # output contract permits aggregate counts only, including on failure.
    prior_logging_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        counts = expire_review_conflicts(args.uid, created_before=args.created_before, dry_run=not args.apply)
    except Exception:
        print('Expiration failed; rerun dry-run before retrying apply.', file=sys.stderr)
        return 1
    finally:
        logging.disable(prior_logging_disable)
    print(json.dumps(counts, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
