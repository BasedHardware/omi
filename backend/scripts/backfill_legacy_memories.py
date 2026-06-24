"""Admin entrypoint for WS-C legacy → canonical memory backfill (single uid).

Non-destructive: reads legacy ``users/{uid}/memories`` only; writes canonical ``memory_items``.
Requires ``uid`` in ``MEMORY_CANONICAL_USERS`` unless ``--allow-admin-override`` is passed.

Usage:
    cd backend
    python scripts/backfill_legacy_memories.py --uid YOUR_UID --dry-run
    python scripts/backfill_legacy_memories.py --uid YOUR_UID
    python scripts/backfill_legacy_memories.py --uid YOUR_UID --no-resume
"""

from __future__ import annotations

import argparse
import json
import sys

from utils.memory.legacy_backfill import backfill_user


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill one user's legacy memories into canonical store")
    parser.add_argument("--uid", required=True, help="Firebase uid to backfill")
    parser.add_argument("--dry-run", action="store_true", help="Report intended writes without persisting")
    parser.add_argument("--batch-size", type=int, default=50, help="Checkpoint interval (default: 50)")
    parser.add_argument("--no-resume", action="store_true", help="Ignore prior checkpoint and start from 0")
    parser.add_argument(
        "--allow-admin-override",
        action="store_true",
        help="Bypass MEMORY_CANONICAL_USERS gate (emergency only)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = backfill_user(
        args.uid,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
        resume=not args.no_resume,
        allow_admin_override=args.allow_admin_override,
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
