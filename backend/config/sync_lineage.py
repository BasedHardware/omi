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

``SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST`` stages the rollout: comma-separated uids,
whitespace-trimmed; empty or unset admits every user. It gates every behavior
that changes a sync append into, or a live write onto, a user's rows (per-segment
binding, the pinned live origin, the live revision fence, the open-live enrichment
deferral), so a uid outside it behaves exactly as with the kill switch off. The
metadata-only origin stamp stays under the kill switch alone: widening later
needs lineage that was already stamped. The kill switch wins over the allowlist.

Pure module: stdlib only, the flags are read at the call boundary, never at import.
"""

from __future__ import annotations

import os

SYNC_LINEAGE_RESOLVE_ENV = 'SYNC_LINEAGE_RESOLVE_ENABLED'
SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST_ENV = 'SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST'

_ON_VALUES = frozenset({'1', 'true', 'on', 'yes', 'enabled'})


def sync_lineage_resolve_enabled() -> bool:
    """Unset or blank is on; only an explicit on-token keeps it on when set."""
    raw = os.getenv(SYNC_LINEAGE_RESOLVE_ENV, '').strip().lower()
    return not raw or raw in _ON_VALUES


def sync_lineage_resolve_uid_allowed(uid: object) -> bool:
    """An empty allowlist admits every user; a non-empty one admits only its members."""
    allowlist = {item.strip() for item in os.getenv(SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST_ENV, '').split(',')}
    allowlist.discard('')
    return not allowlist or (isinstance(uid, str) and uid in allowlist)


def sync_lineage_resolve_active_for(uid: object) -> bool:
    """The sync-side gate: the kill switch is on and the uid is admitted."""
    return sync_lineage_resolve_enabled() and sync_lineage_resolve_uid_allowed(uid)


def sync_lineage_s1_required() -> bool:
    raw = os.getenv('SYNC_LINEAGE_S1_REQUIRED', '').strip().lower()
    return not raw or raw in _ON_VALUES
