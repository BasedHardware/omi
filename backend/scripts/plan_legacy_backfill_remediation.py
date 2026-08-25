"""Build a read-only cleanup plan for canonical rows written by legacy backfill.

This is intentionally not an apply command. It inventories only active
``memory_items`` with explicit ``promotion.source_surface=legacy_backfill``
lineage and returns content-free recommendations for a later reviewed apply run.
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

from utils.memory.legacy_backfill import (
    BackfillCohortGateError,
    assert_canonical_cohort_for_backfill,
    build_legacy_backfill_remediation_plan,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan cleanup for one user's historical legacy backfill")
    parser.add_argument("--uid", required=True, help="Firebase uid to inspect")
    parser.add_argument("--sample-size", type=int, default=5, help="Metadata-only samples per action (default: 5)")
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
    try:
        assert_canonical_cohort_for_backfill(
            args.uid,
            allow_admin_override=args.allow_admin_override,
            acknowledge_non_canonical_uid=args.i_understand_uid_not_whitelisted,
            operator_context=args.operator_context or getpass.getuser(),
        )
    except BackfillCohortGateError as exc:
        print(json.dumps({"uid": args.uid, "cohort_gated": True, "error": str(exc)}, indent=2))
        return 2

    plan = build_legacy_backfill_remediation_plan(args.uid, sample_size=max(0, args.sample_size))
    print(json.dumps(asdict(plan), default=str, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
