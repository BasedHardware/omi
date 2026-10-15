#!/usr/bin/env python3
"""Count or repair orphan backfill owners; dry-run is the default.

Run from backend with PYTHONPATH=. and OMI_ENV_STAGE=prod. Select credentials
outside this script. No Redis/Cloud Tasks access or dispatch occurs here.
Only aggregate counts are printed, including on failure.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from typing import Any

from google.cloud import firestore

from database import sync_backfill_sequencer as registry


def repair(
    client: Any,
    *,
    apply: bool = False,
    limit: int = 1_000_000,
    page_size: int = 500,
    rate_per_second: float = 5,
    repair_window: int | None = None,
) -> dict[str, int]:
    """Page by document ID; transactionally revalidate the queue per UID.

    Memory, reads and writes are bounded by limit. Reruns start from the
    beginning and are idempotent. Dry-run never writes a cursor or an owner.
    """
    if limit < 1 or not 1 <= page_size <= 500 or not math.isfinite(rate_per_second) or not 0 < rate_per_second <= 20:
        raise ValueError('invalid repair bounds')
    repair_window = registry.repair_window_seconds(repair_window)
    counts = {'scanned_entries': 0, 'scanned_uids': 0, 'missing_owners': 0, 'repaired_owners': 0, 'errors': 0}
    seen: set[str] = set()
    cursor = None
    next_probe_at = time.monotonic()
    while counts['scanned_entries'] < limit:
        query = (
            client.collection(registry.PENDING_COLLECTION)
            .select(['uid'])
            .order_by('__name__')
            .limit(min(page_size, limit - counts['scanned_entries']))
        )
        if cursor is not None:
            query = query.start_after(cursor)
        docs = list(query.stream())
        if not docs:
            break
        for doc in docs:
            counts['scanned_entries'] += 1
            uid = (doc.to_dict() or {}).get('uid')
            if not isinstance(uid, str) or not uid or '/' in uid:
                counts['errors'] += 1
                continue
            if uid in seen:
                continue
            # Only mark successful probes seen; a later sample can retry a
            # UID if a read failed.
            delay = next_probe_at - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            try:
                needed = registry.repair_owner(
                    uid, dry_run=not apply, repair_window=repair_window, firestore_client=client
                )
            except Exception:
                counts['errors'] += 1
            else:
                seen.add(uid)
                counts['scanned_uids'] += 1
                counts['missing_owners'] += int(needed)
                counts['repaired_owners'] += int(needed and apply)
            next_probe_at = time.monotonic() + 1 / rate_per_second
        cursor = docs[-1]
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='Read only (default)')
    mode.add_argument('--apply', action='store_true', help='Recreate missing owners; does not dispatch jobs')
    parser.add_argument('--limit', type=int, default=1_000_000, help='Maximum pending documents to scan')
    parser.add_argument('--page-size', type=int, default=500)
    parser.add_argument('--rate-per-second', type=float, default=5, help='Maximum UID probes/second (up to 20)')
    parser.add_argument(
        '--repair-window-seconds',
        type=int,
        default=None,
        help='Spread repairs over this window (default 1800s; SYNC_BACKFILL_OWNER_REPAIR_WINDOW_SECONDS overrides)',
    )
    args = parser.parse_args(argv)
    try:
        registry._require_production()
        client = firestore.Client(project=args.project)
        try:
            counts = repair(
                client,
                apply=args.apply,
                limit=args.limit,
                page_size=args.page_size,
                rate_per_second=args.rate_per_second,
                repair_window=args.repair_window_seconds,
            )
        finally:
            client.close()
    except Exception:
        # Firestore exceptions can embed document paths; never print them.
        print(json.dumps({'errors': 1}))
        return 1
    print(json.dumps(counts, sort_keys=True))
    return int(counts['errors'] > 0)


if __name__ == '__main__':
    sys.exit(main())
