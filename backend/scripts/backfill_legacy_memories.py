"""Admin entrypoint for WS-C legacy → canonical memory backfill (single uid).

Non-destructive: reads legacy ``users/{uid}/memories`` only; writes canonical ``memory_items``.
The operator must name one UID explicitly; this command never discovers accounts.

Usage:
    cd backend
    python scripts/backfill_legacy_memories.py --uid YOUR_UID
    python scripts/backfill_legacy_memories.py --uid YOUR_UID --apply
    python scripts/backfill_legacy_memories.py --uid YOUR_UID --apply --no-resume
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from utils.memory.legacy_backfill import LegacyBackfillBucket, backfill_user, backfill_user_bucketed

BUCKET_CHOICES = [bucket.value for bucket in LegacyBackfillBucket]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill one user's legacy memories into canonical store")
    parser.add_argument("--uid", required=True, help="Firebase uid to backfill")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Persist the repair (default is dry-run)")
    mode.add_argument("--dry-run", action="store_true", help="Explicitly select the default non-mutating mode")
    parser.add_argument("--batch-size", type=int, default=50, help="Checkpoint interval (default: 50)")
    parser.add_argument("--no-resume", action="store_true", help="Ignore prior checkpoint and start from 0")
    parser.add_argument(
        "--strategy",
        choices=["stage-all-for-admission", "bucketed"],
        default="stage-all-for-admission",
        help="Migration strategy (default: all rows enter canonical admission staging)",
    )
    parser.add_argument(
        "--bucket",
        choices=BUCKET_CHOICES,
        default=None,
        help="Bucket to dry-run/apply when --strategy bucketed. Omit for inventory-only dry-run.",
    )
    parser.add_argument(
        "--operator-context",
        default=None,
        help="Operator identity for audit logs (default: current OS user)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    dry_run = not args.apply
    operator_context = args.operator_context or getpass.getuser()
    if args.strategy == "bucketed":
        if args.bucket is None and not dry_run:
            print(
                "--strategy bucketed without --bucket is inventory-only; pass --dry-run or choose a bucket",
                file=sys.stderr,
            )
            return 2
        report = backfill_user_bucketed(
            args.uid,
            bucket=args.bucket,
            dry_run=dry_run,
            operator_context=operator_context,
        )
    else:
        if args.bucket is not None:
            print("--bucket requires --strategy bucketed", file=sys.stderr)
            return 2
        report = backfill_user(
            args.uid,
            dry_run=dry_run,
            batch_size=args.batch_size,
            resume=not args.no_resume,
            operator_context=operator_context,
        )
    print(json.dumps(report.__dict__, default=str, indent=2))
    if report.errors:
        return 1
    if not report.dry_run and not report.completed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
