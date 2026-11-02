"""Bound read-only preparation; execution remains one fenced job per owner."""

import os

from config.refactor_switches import default_on as rollout_default_on


def preparation_width() -> int:
    if not rollout_default_on(
        'SYNC_BACKFILL_OWNER_CONCURRENCY_ENABLED',
        os.getenv('SYNC_BACKFILL_OWNER_CONCURRENCY_ENABLED', 'on').strip().lower() == 'on',
    ):
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
