"""Runtime contract for binding safety-WAL uploads to a live recording's rollover lineage.

``/v4/listen`` mints a new server recording id (and conversation) at every
silence rollover, while the phone tags every WAL with the recording id it
minted when capture started. With this switch on, the live path also stamps
each generation with that origin id (``external_data.recording_origin_id``)
and sync binds each VAD segment of an upload to the generation whose interval
covers it (``utils/sync/recording_lineage.py``).

``SYNC_LINEAGE_RESOLVE_ENABLED`` unset or blank means on. ``false``/``off``/``0``
is the kill switch, and any unrecognized value also means off, so a mistyped
kill switch can never leave the feature running. Off restores the previous
whole-batch ``recording_session_target`` resolution and writes no origin stamp.

Pure module: stdlib only, the flag is read at the call boundary, never at import.
"""

from __future__ import annotations

import os

SYNC_LINEAGE_RESOLVE_ENV = 'SYNC_LINEAGE_RESOLVE_ENABLED'

_ON_VALUES = frozenset({'1', 'true', 'on', 'yes', 'enabled'})


def sync_lineage_resolve_enabled() -> bool:
    """Unset or blank is on; only an explicit on-token keeps it on when set."""
    raw = os.getenv(SYNC_LINEAGE_RESOLVE_ENV, '').strip().lower()
    return not raw or raw in _ON_VALUES
