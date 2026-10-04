"""Runtime contract for trimming safety-WAL frames already proven live-received.

A WAL carries every captured frame whenever any frame missed the socket, so
uploaded audio can repeat speech the live path already transcribed. When this
switch is on and the opt-in S1 source-position signal exists on both sides,
``utils/sync/wal_audio_coverage.py`` removes only the frames a bounded lineage
lookup proves the authenticated same-origin/same-device live socket already
received, before VAD/STT. Missing, malformed, conflicting or out-of-bounds
evidence keeps the original audio; today's shipped clients emit no S1 upload
claim and keep the exact previous path — no added lookup and no coverage log.
An upload carrying the claim but no stored live snapshot costs one bounded
lineage lookup before retaining everything.

``SYNC_WAL_AUDIO_COVERAGE_ENABLED`` unset or blank means on. Only an explicit
on-token keeps it on when set; every other value — including a mistyped kill
switch — means off, and off restores the original audio path exactly.

The switch alone does not widen the change: activation additionally requires
``sync_lineage_resolve_active_for(uid)``, so it reaches only users admitted to
lineage binding, and it never enables S1 dark-write itself.

Pure module: stdlib plus the sibling lineage gate, read at the call boundary,
never at import.
"""

from __future__ import annotations

import os

from config.sync_lineage import sync_lineage_resolve_active_for

SYNC_WAL_AUDIO_COVERAGE_ENV = 'SYNC_WAL_AUDIO_COVERAGE_ENABLED'

_ON_VALUES = frozenset({'1', 'true', 'on', 'yes', 'enabled'})


def sync_wal_audio_coverage_enabled() -> bool:
    """Unset or blank is on; only an explicit on-token keeps it on when set."""
    raw = os.getenv(SYNC_WAL_AUDIO_COVERAGE_ENV, '').strip().lower()
    return not raw or raw in _ON_VALUES


def sync_wal_audio_coverage_active_for(uid: object) -> bool:
    """The intake gate: this switch on and the uid admitted to lineage binding."""
    return sync_wal_audio_coverage_enabled() and sync_lineage_resolve_active_for(uid)
