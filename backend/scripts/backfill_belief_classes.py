"""Classify legacy memory_items that carry no belief_class for one uid.

Flag-gated writes: set MEMORY_BELIEF_MODEL_ENABLED=true before --apply.
Dry-run is the default and prints classification-only results without writing.
Rows that already have belief_class are counted as already classified. The
checkpoint is an operator-owned JSON artifact; it caches classifier results and
the deterministic cursor so an interrupted apply does not pay to classify a
committed row again. Status, tier, expires_at, subject_scope, valid_to, and
content are never changed.

Usage:
    cd backend
    python scripts/backfill_belief_classes.py --uid YOUR_UID
    python scripts/backfill_belief_classes.py --uid YOUR_UID --dry-run
    python scripts/backfill_belief_classes.py --uid YOUR_UID --page-size 25 --limit 25 \
        --checkpoint /path/to/operator-artifact.json
    MEMORY_BELIEF_MODEL_ENABLED=true python scripts/backfill_belief_classes.py --uid YOUR_UID --apply \
        --checkpoint /path/to/operator-artifact.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
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
    parser.add_argument(
        "--page-size",
        type=int,
        default=BELIEF_BACKFILL_BATCH_SIZE,
        help=f"Maximum rows read in this bounded invocation (default: {BELIEF_BACKFILL_BATCH_SIZE})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum rows read in this invocation; use a small value for rehearsal",
    )
    parser.add_argument(
        "--start-after",
        default=None,
        help="Resume after this deterministic memory id when no checkpoint cursor is available",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        help="Operator-owned JSON checkpoint artifact for cursor and cached classification results",
    )
    parser.add_argument("--user-name", default=None, help="Account owner name for subject classification")
    return parser


def _load_checkpoint(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("checkpoint must contain a JSON object")
    return payload


def _write_checkpoint(path: Path | None, state: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, sort_keys=True, indent=2, default=str)
        handle.write("\n")
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    args = _build_parser().parse_args(argv)
    dry_run = not args.apply
    checkpoint = _load_checkpoint(args.checkpoint)
    report = backfill_belief_classes(
        args.uid,
        db_client=get_firestore_client(),
        dry_run=dry_run,
        batch_size=max(1, args.batch_size),
        user_name=args.user_name,
        page_size=max(1, args.page_size),
        limit=args.limit,
        start_after=args.start_after,
        checkpoint=checkpoint,
        checkpoint_writer=lambda state: _write_checkpoint(args.checkpoint, state),
    )
    payload = report.__dict__.copy()
    print(json.dumps(payload, sort_keys=True, indent=2))
    logger.info(
        "belief backfill uid=%s dry_run=%s classified=%d written=%d already=%d unknown=%d skipped=%d errors=%d partial=%s",
        report.uid,
        report.dry_run,
        report.classified,
        report.written,
        report.already_classified,
        report.unknown,
        report.skipped,
        report.errors,
        report.partial,
    )
    if report.errors:
        return 1
    if report.partial:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
