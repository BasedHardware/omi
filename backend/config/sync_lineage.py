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
whitespace-trimmed; empty or absent retains legacy enable-all when the
Firestore field is missing. Explicit Firestore booleans override that fallback.
It gates per-segment binding. Live-target revision fencing and origin stability
on sync appends are unconditional: once sync and live share a row, late speech
must fence older processors and keep the listener's cached origin regardless
of rollout membership. The
metadata-only origin stamp stays under the kill switch alone: widening later
needs lineage that was already stamped. The kill switch wins over the allowlist.

Flags are read at the call boundary; membership uses the bounded Firestore cache.
"""

from __future__ import annotations

import os

from config.refactor_switches import default_on as rollout_default_on

from config.rollout_cohorts import in_rollout_cohort

SYNC_LINEAGE_RESOLVE_ENV = 'SYNC_LINEAGE_RESOLVE_ENABLED'
SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST_ENV = 'SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST'

_ON_VALUES = frozenset({'1', 'true', 'on', 'yes', 'enabled'})


def sync_lineage_resolve_enabled() -> bool:
    """Unset or blank is on; only an explicit on-token keeps it on when set."""
    raw = os.getenv(SYNC_LINEAGE_RESOLVE_ENV, '').strip().lower()
    return rollout_default_on(SYNC_LINEAGE_RESOLVE_ENV, not raw or raw in _ON_VALUES)


def sync_lineage_resolve_uid_allowed(uid: object) -> bool:
    """Missing Firestore fields preserve empty AND absent legacy enable-all."""
    allowlist = {item.strip() for item in os.getenv(SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST_ENV, '').split(',')}
    allowlist.discard('')
    legacy_all = not allowlist
    return isinstance(uid, str) and in_rollout_cohort(uid, 'sync-lineage-resolve', legacy_all=legacy_all)


def sync_lineage_resolve_active_for(uid: object) -> bool:
    """The sync-side gate: the kill switch is on and the uid is admitted."""
    return sync_lineage_resolve_enabled() and sync_lineage_resolve_uid_allowed(uid)
