"""Bound read-only preparation; execution remains one fenced job per owner."""

import os


def preparation_width() -> int:
    if os.getenv('SYNC_BACKFILL_OWNER_CONCURRENCY_ENABLED', 'on').strip().lower() != 'on':
        return 1
    try:
        return max(1, min(4, int(os.getenv('SYNC_BACKFILL_OWNER_CONCURRENCY', '2'))))
    except ValueError:
        return 1


def backlog_threshold() -> int:
    try:
        return max(4, min(100, int(os.getenv('SYNC_BACKFILL_OWNER_CONCURRENCY_THRESHOLD', '8'))))
    except ValueError:
        return 8
