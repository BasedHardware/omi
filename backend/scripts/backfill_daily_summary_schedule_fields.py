#!/usr/bin/env python3
# LIFECYCLE: one-time
# DELETE-AFTER: https://github.com/BasedHardware/omi/issues/13210
"""Materialize daily-summary schedule fields on existing ``users`` documents.

``daily_summary_enabled`` and ``daily_summary_hour_local`` must be present for
Firestore equality filters to match the Python defaults (True, 22). This
script writes only absent fields via ``set(..., merge=True)``; explicit
``False`` and hour ``0`` are left alone. Dry-run is the default.

Usage:
    python scripts/backfill_daily_summary_schedule_fields.py
    python scripts/backfill_daily_summary_schedule_fields.py --limit 50
    python scripts/backfill_daily_summary_schedule_fields.py --apply
    python scripts/backfill_daily_summary_schedule_fields.py --apply --start-after <uid>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from database.notifications import daily_summary_schedule_defaults

_PROJECTED_FIELDS = ('time_zone', 'daily_summary_enabled', 'daily_summary_hour_local')
_BATCH_LIMIT = 500
_DEFAULT_PAGE_SIZE = 500


def run_backfill(
    client: Any,
    *,
    apply: bool,
    page_size: int,
    start_after: str | None,
    limit: int | None,
) -> dict[str, Any]:
    """Page ``users`` and fill absent daily-summary schedule fields.

    ``client`` is a Firestore-like object (``collection`` / ``batch``). Writes
    happen only when ``apply`` is true. Returns the summary counters printed by
    the CLI.
    """
    page_size = min(max(int(page_size), 1), _DEFAULT_PAGE_SIZE)
    remaining = None if limit is None or limit <= 0 else int(limit)

    scanned = 0
    with_time_zone = 0
    missing_enabled = 0
    missing_hour = 0
    written = 0
    last_uid: str | None = None
    # The SDK only accepts a dict or a snapshot as a cursor; a bare uid string is
    # rejected against ``order_by('__name__')``. Later pages cursor on the last snapshot.
    cursor: Any = {'__name__': start_after} if start_after else None

    batch = client.batch() if apply else None
    pending = 0

    while remaining is None or remaining > 0:
        take = page_size if remaining is None else min(page_size, remaining)
        query = client.collection('users').select(list(_PROJECTED_FIELDS)).order_by('__name__').limit(take)
        if cursor is not None:
            query = query.start_after(cursor)
        page = list(query.stream())
        if not page:
            break

        for snapshot in page:
            last_uid = str(snapshot.id)
            scanned += 1
            data = snapshot.to_dict() or {}
            if not isinstance(data, dict):
                data = {}
            if data.get('time_zone'):
                with_time_zone += 1
            if 'daily_summary_enabled' not in data:
                missing_enabled += 1
            if 'daily_summary_hour_local' not in data:
                missing_hour += 1
            patch = daily_summary_schedule_defaults(data)
            if not patch:
                continue
            written += 1
            if apply and batch is not None:
                batch.set(snapshot.reference, patch, merge=True)
                pending += 1
                if pending >= _BATCH_LIMIT:
                    batch.commit()
                    batch = client.batch()
                    pending = 0

        if remaining is not None:
            remaining -= len(page)
        cursor = page[-1]
        if len(page) < take:
            break

    if apply and batch is not None and pending > 0:
        batch.commit()

    return {
        'scanned': scanned,
        'with_time_zone': with_time_zone,
        'missing_enabled': missing_enabled,
        'missing_hour': missing_hour,
        'written': written,
        'last_uid': last_uid,
        'apply': apply,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Write missing fields. Default is dry-run.')
    parser.add_argument(
        '--page-size',
        type=int,
        default=_DEFAULT_PAGE_SIZE,
        help=f'Users per page (default {_DEFAULT_PAGE_SIZE}, max {_DEFAULT_PAGE_SIZE}).',
    )
    parser.add_argument('--start-after', default=None, metavar='UID', help='Resume after this user document id.')
    parser.add_argument('--limit', type=int, default=None, help='Optional max users to scan (smoke runs).')
    args = parser.parse_args()

    from database._client import get_firestore_client

    summary = run_backfill(
        get_firestore_client(),
        apply=args.apply,
        page_size=args.page_size,
        start_after=args.start_after,
        limit=args.limit,
    )
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
