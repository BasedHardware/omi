"""Explicit partial-record contract; complete seals retain their existing proof."""

import os

WAIT_SECONDS = 1800
MAX_SOURCES = 8192
MAX_UNITS = 8192
UNIT_SECONDS = 300
UNIT_REFERENCES = 256
PAGE_UNITS = 128
INVENTORY_POLL_SECONDS = 3600
INVENTORY_IDLE_SECONDS = 24 * 3600
REASONS = frozenset({'tail_lagging', 'budget_limit', 'tail_lost_or_unproven'})


def enabled():
    return os.getenv('RECORD_AUDIO_PARTIAL_ENABLED', 'true').strip().lower() != 'false'


def partial_barrier(row):
    mark = row.get('record_audio_partial')
    return bool(
        isinstance(mark, dict)
        and type(mark.get('version')) is int
        and mark.get('version') == 1
        and mark.get('reason') in REASONS
        and mark.get('upload_revision') == row.get('record_upload_revision')
        and mark.get('finished_at') == row.get('finished_at')
    )
