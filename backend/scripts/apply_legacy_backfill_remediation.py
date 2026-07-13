"""Archive deterministic legacy-backfill noise for one canonical-memory account.

Default mode is metadata-only dry-run. ``--apply`` requires a fresh exact count
and an explicit acknowledgement; it archives records through the canonical
apply ledger and never deletes their evidence or source memory rows.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import getpass
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from utils.memory.legacy_backfill import apply_legacy_backfill_remediation_archives


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Archive deterministic legacy-backfill noise for one account")
    parser.add_argument("--uid", required=True, help="Firebase uid to remediate")
    parser.add_argument("--apply", action="store_true", help="Apply the archive transition (default is dry-run)")
    parser.add_argument(
        "--expected-archive-count",
        type=int,
        default=None,
        help="Fresh exact archive candidate count; required with --apply",
    )
    parser.add_argument(
        "--i-understand-archives-exclude-default-read",
        action="store_true",
        help="Required with --apply; archive stays available only through explicit archive access",
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
    parser.add_argument("--operator-context", default=None, help="Operator identity for audit logs")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.apply and args.expected_archive_count is None:
        print("--apply requires --expected-archive-count", file=sys.stderr)
        return 2
    if args.apply and not args.i_understand_archives_exclude_default_read:
        print("--apply requires --i-understand-archives-exclude-default-read", file=sys.stderr)
        return 2
    report = apply_legacy_backfill_remediation_archives(
        args.uid,
        expected_archive_count=args.expected_archive_count,
        dry_run=not args.apply,
        allow_admin_override=args.allow_admin_override,
        acknowledge_non_canonical_uid=args.i_understand_uid_not_whitelisted,
        operator_context=args.operator_context or getpass.getuser(),
    )
    print(json.dumps(asdict(report), default=str, indent=2, sort_keys=True))
    return 1 if report.cohort_gated or report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
