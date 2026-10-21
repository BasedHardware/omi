"""Typed intake outcomes: user authority is terminal, corrupt lineage is loud."""

from enum import StrEnum


class SyncAssignmentConflictReason(StrEnum):
    """One bounded token per raise site; ``other`` is only the unlabeled fallback."""

    OTHER = 'other'
    PROVENANCE_MISMATCH = 'provenance_mismatch'
    REDIRECT_CYCLE = 'redirect_cycle'
    REDIRECT_CHAIN_TOO_LONG = 'redirect_chain_too_long'
    DONOR_TOMBSTONE_NO_REDIRECT = 'donor_tombstone_no_redirect'
    ANCESTRY_FLATTEN_REJECTED = 'ancestry_flatten_rejected'
    CORRECTED_SPEECH_CHANGED = 'corrected_speech_changed'
    BRIDGE_SOURCE_NOT_TOMBSTONE = 'bridge_source_not_tombstone'
    LIVE_TARGET_NOT_PERSISTED = 'live_target_not_persisted'
    LINEAGE_OWNERSHIP_AMBIGUOUS = 'lineage_ownership_ambiguous'
    RECORD_TARGET_MISSING = 'record_target_missing'
    RECORD_TARGET_RETIRED = 'record_target_retired'
    RECORD_TARGET_DISCARDED = 'record_target_discarded'
    RECORD_FINALIZE_PENDING = 'record_finalize_pending'
    RECORD_ROUTE_OWNER_CHANGED = 'record_route_owner_changed'
    RECORD_PRIVACY_CHANGED = 'record_privacy_changed'


SYNC_ASSIGNMENT_CONFLICT_SUBTYPES = frozenset(reason.value for reason in SyncAssignmentConflictReason)

# Retrying the same content cannot change these: each failure is a strike
# toward the ledger's bounded repeat-failure pause, on every lane.
SYNC_ASSIGNMENT_CONFLICT_STRUCTURAL = frozenset(
    {
        SyncAssignmentConflictReason.PROVENANCE_MISMATCH.value,
        SyncAssignmentConflictReason.REDIRECT_CYCLE.value,
        SyncAssignmentConflictReason.REDIRECT_CHAIN_TOO_LONG.value,
        SyncAssignmentConflictReason.DONOR_TOMBSTONE_NO_REDIRECT.value,
        SyncAssignmentConflictReason.ANCESTRY_FLATTEN_REJECTED.value,
        SyncAssignmentConflictReason.CORRECTED_SPEECH_CHANGED.value,
        SyncAssignmentConflictReason.RECORD_TARGET_RETIRED.value,
        SyncAssignmentConflictReason.RECORD_ROUTE_OWNER_CHANGED.value,
        SyncAssignmentConflictReason.RECORD_PRIVACY_CHANGED.value,
    }
)

# These wait on another writer (listen persisting its row, a record finishing or
# being restored from discard, a lineage binding settling). A fresh retry keeps
# waiting; backfill content is hours old, so a writer that still has not landed
# is treated as structural.
SYNC_ASSIGNMENT_CONFLICT_AWAITING_WRITER = frozenset(
    {
        SyncAssignmentConflictReason.LIVE_TARGET_NOT_PERSISTED.value,
        SyncAssignmentConflictReason.LINEAGE_OWNERSHIP_AMBIGUOUS.value,
        SyncAssignmentConflictReason.RECORD_TARGET_MISSING.value,
        SyncAssignmentConflictReason.RECORD_FINALIZE_PENDING.value,
        SyncAssignmentConflictReason.RECORD_TARGET_DISCARDED.value,
    }
)


def bounded_sync_assignment_subtype(subtype: object) -> str:
    """Return a low-cardinality assignment-conflict subtype for diagnostics."""
    if subtype is None or (isinstance(subtype, str) and subtype == 'none'):
        return 'none'
    return str(subtype) if isinstance(subtype, str) and subtype in SYNC_ASSIGNMENT_CONFLICT_SUBTYPES else 'other'


def sync_assignment_conflict_strikes(subtype: object, lane: str) -> bool:
    """Whether this conflict counts toward the bounded pause instead of retrying forever."""
    reason = bounded_sync_assignment_subtype(subtype)
    return reason in SYNC_ASSIGNMENT_CONFLICT_STRUCTURAL or (
        lane == 'backfill' and reason in SYNC_ASSIGNMENT_CONFLICT_AWAITING_WRITER
    )


class SyncAssignmentSuperseded(RuntimeError):
    """Deleted or user-managed lineage must not be recreated by WAL retries."""


class SyncAssignmentConflict(RuntimeError):
    """A provenance mismatch or corrupt redirect requires visible investigation."""

    def __init__(self, message: str, *, subtype: str = SyncAssignmentConflictReason.OTHER) -> None:
        self.subtype = bounded_sync_assignment_subtype(subtype)
        super().__init__(message)
