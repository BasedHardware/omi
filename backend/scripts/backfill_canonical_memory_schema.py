"""Backfill WS-O schema defaults for canonical cohort users (O-W3)."""

from __future__ import annotations

import argparse
import logging

from database._client import db
from database.memory_collections import MemoryCollections
from utils.memory.memory_system import list_canonical_cohort_uids

logger = logging.getLogger(__name__)

DEFAULTS = {
    "corroboration_count": 0,
    "kg_extracted": False,
    "arguments": {},
}


def backfill_user(uid: str, *, dry_run: bool = True) -> int:
    items_ref = db.collection(MemoryCollections(uid=uid).memory_items)
    updated = 0
    for snapshot in items_ref.stream():
        data = snapshot.to_dict() or {}
        patch = {key: value for key, value in DEFAULTS.items() if key not in data}
        if not patch:
            continue
        updated += 1
        if dry_run:
            logger.info("dry_run uid=%s memory_id=%s patch=%s", uid, snapshot.id, patch)
        else:
            snapshot.reference.set(patch, merge=True)
    return updated


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Backfill WS-O MemoryItem schema defaults")
    parser.add_argument("--apply", action="store_true", help="Write changes (default is dry-run)")
    args = parser.parse_args()
    dry_run = not args.apply
    total = 0
    for uid in list_canonical_cohort_uids():
        count = backfill_user(uid, dry_run=dry_run)
        logger.info("uid=%s updated=%d dry_run=%s", uid, count, dry_run)
        total += count
    logger.info("done total_updated=%d dry_run=%s", total, dry_run)


if __name__ == "__main__":
    main()
