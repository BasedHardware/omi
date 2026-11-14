"""Estimated-clock runs for Offline Sync uploads.

A sync filename's trailing timestamp is the only recording time the backend
sees. When the device could not supply a trustworthy recording time (no RTC
marker, an unsynced RTC, or a clock restored stale after a power loss), the
app estimates it, usually as ``now - duration``. Those estimates lay audio from
different days end to end, so temporal adjacency between them proves nothing.

The app marks such a file with a ``_clke<run>_`` token before the timestamp.
``<run>`` names one stretch of audio the device recorded contiguously. Pieces
of one run really are adjacent; pieces of different runs, or an estimated
piece and a device-clocked one, never are. ``SYNC_CLOCK_RUN_FIELD`` carries
the run on the conversation row, where ``compatible_capture`` treats it as a
partition: rows without the field (every device-clocked and historical row)
keep today's behaviour.

Older backends ignore the token: they parse only ``_fs<n>`` and the last
``_``-separated part of the name.
"""

from __future__ import annotations

import os
import re
from typing import Optional

SYNC_CLOCK_RUN_FIELD = 'sync_clock_run'

# Lowercase alphanumeric, bounded: the run is a client nonce, never user text.
# Only the part directly before the trailing timestamp counts, so a device name
# can never be read as a run.
_TOKEN = re.compile(r'(?:^|_)clke([0-9a-z]{1,32})_[0-9.]+\.(?:bin|wav)$')


def clock_run_partition_enabled() -> bool:
    """Kill switch; on unless explicitly turned off."""
    return os.getenv('SYNC_CLOCK_RUN_PARTITION_ENABLED', 'true').strip().lower() not in ('0', 'false', 'off', 'no')


def clock_run_from_path(path: str) -> Optional[str]:
    """The estimated-clock run named in a sync upload or VAD segment filename."""
    if not clock_run_partition_enabled():
        return None
    match = _TOKEN.search(os.path.basename(path))
    return match.group(1) if match else None


def segment_name_prefix(source_path: str) -> str:
    """Prefix carrying the source file's run onto its derived VAD segment files."""
    run = clock_run_from_path(source_path)
    return f'clke{run}_' if run else ''
