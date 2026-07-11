"""Admin entrypoint for WS-C legacy → canonical memory backfill (single uid).

Non-destructive: reads legacy ``users/{uid}/memories`` only; writes canonical ``memory_items``.
Requires ``uid`` in ``CANONICAL_MEMORY_USERS`` unless ``--allow-admin-override`` and
``--i-understand-uid-not-whitelisted`` are both passed.

Usage:
    cd backend
    python scripts/backfill_legacy_memories.py --uid YOUR_UID --dry-run
    python scripts/backfill_legacy_memories.py --uid YOUR_UID
    python scripts/backfill_legacy_memories.py --uid YOUR_UID --no-resume
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
    parser.add_argument("--dry-run", action="store_true", help="Report intended writes without persisting")
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
        "--allow-admin-override",
        action="store_true",
        help="Bypass CANONICAL_MEMORY_USERS gate (requires --i-understand-uid-not-whitelisted)",
    )
    parser.add_argument(
        "--i-understand-uid-not-whitelisted",
        action="store_true",
        help="Confirm uid may be outside CANONICAL_MEMORY_USERS (required with --allow-admin-override)",
    )
    parser.add_argument(
        "--operator-context",
        default=None,
        help="Operator identity for audit logs (default: current OS user)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    operator_context = args.operator_context or getpass.getuser()
    if args.strategy == "bucketed":
        if args.bucket is None and not args.dry_run:
            print(
                "--strategy bucketed without --bucket is inventory-only; pass --dry-run or choose a bucket",
                file=sys.stderr,
            )
            return 2
        report = backfill_user_bucketed(
            args.uid,
            bucket=args.bucket,
            dry_run=args.dry_run,
            allow_admin_override=args.allow_admin_override,
            acknowledge_non_canonical_uid=args.i_understand_uid_not_whitelisted,
            operator_context=operator_context,
        )
    else:
        if args.bucket is not None:
            print("--bucket requires --strategy bucketed", file=sys.stderr)
            return 2
        report = backfill_user(
            args.uid,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            resume=not args.no_resume,
            allow_admin_override=args.allow_admin_override,
            acknowledge_non_canonical_uid=args.i_understand_uid_not_whitelisted,
            operator_context=operator_context,
        )
    print(json.dumps(report.__dict__, default=str, indent=2))
    if report.cohort_gated:
        return 2
    if report.errors:
        return 1
    if not report.dry_run and not report.completed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
