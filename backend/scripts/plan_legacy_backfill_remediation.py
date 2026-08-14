"""Build a read-only cleanup plan for canonical rows written by legacy backfill.

This is intentionally not an apply command. It inventories only active
``memory_items`` with explicit ``promotion.source_surface=legacy_backfill``
lineage and returns content-free recommendations for a later reviewed apply run.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from utils.memory.legacy_backfill import build_legacy_backfill_remediation_plan


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan cleanup for one user's historical legacy backfill")
    parser.add_argument("--uid", required=True, help="Firebase uid to inspect")
    parser.add_argument("--sample-size", type=int, default=5, help="Metadata-only samples per action (default: 5)")
    parser.add_argument(
        "--operator-context",
        default=None,
        help="Operator identity for audit logs (default: current OS user)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    del args.operator_context  # Reserved for wrapper-side audit logs.
    plan = build_legacy_backfill_remediation_plan(args.uid, sample_size=max(0, args.sample_size))
    print(json.dumps(asdict(plan), default=str, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
