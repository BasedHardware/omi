"""Classify legacy memory_items that carry no belief_class for one uid.

Flag-gated writes: set MEMORY_BELIEF_MODEL_ENABLED=true before --apply.
Dry-run is the default and prints class/scope distribution without writing.
Rows that already have belief_class are skipped. Status, tier, expires_at, and
content are never changed.

Usage:
    cd backend
    python scripts/backfill_belief_classes.py --uid YOUR_UID
    python scripts/backfill_belief_classes.py --uid YOUR_UID --dry-run
    MEMORY_BELIEF_MODEL_ENABLED=true python scripts/backfill_belief_classes.py --uid YOUR_UID --apply
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database._client import get_firestore_client
from utils.memory.belief_backfill import BELIEF_BACKFILL_BATCH_SIZE, backfill_belief_classes

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Classify belief_class on existing memory_items for one uid")
    parser.add_argument("--uid", required=True, help="Firebase uid")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Write classifications (default is dry-run)")
    mode.add_argument("--dry-run", action="store_true", help="Print class/scope distribution without writing")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BELIEF_BACKFILL_BATCH_SIZE,
        help=f"Rows per cheap LLM call (default: {BELIEF_BACKFILL_BATCH_SIZE})",
    )
    parser.add_argument("--user-name", default=None, help="Account owner name for subject classification")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    args = _build_parser().parse_args(argv)
    dry_run = not args.apply
    report = backfill_belief_classes(
        args.uid,
        db_client=get_firestore_client(),
        dry_run=dry_run,
        batch_size=max(1, args.batch_size),
        user_name=args.user_name,
    )
    payload = {
        "uid": report.uid,
        "dry_run": report.dry_run,
        "classified": report.classified,
        "written": report.written,
        "skipped": report.skipped,
        "class_counts": report.class_counts,
        "scope_counts": report.scope_counts,
    }
    print(json.dumps(payload, sort_keys=True, indent=2))
    logger.info(
        "belief backfill uid=%s dry_run=%s classified=%d written=%d skipped=%d",
        report.uid,
        report.dry_run,
        report.classified,
        report.written,
        report.skipped,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
