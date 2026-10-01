"""Typed intake outcomes: user authority is terminal, corrupt lineage is loud."""

SYNC_ASSIGNMENT_CONFLICT_SUBTYPES = frozenset({'provenance_mismatch', 'redirect_cycle', 'other'})


def bounded_sync_assignment_subtype(subtype: object) -> str:
    """Return a low-cardinality assignment-conflict subtype for diagnostics."""
    if subtype is None or (isinstance(subtype, str) and subtype == 'none'):
        return 'none'
    return subtype if isinstance(subtype, str) and subtype in SYNC_ASSIGNMENT_CONFLICT_SUBTYPES else 'other'


class SyncAssignmentSuperseded(RuntimeError):
    """Deleted or user-managed lineage must not be recreated by WAL retries."""


class SyncAssignmentConflict(RuntimeError):
    """A provenance mismatch or corrupt redirect requires visible investigation."""

    def __init__(self, message: str, *, subtype: str = 'other') -> None:
        self.subtype = bounded_sync_assignment_subtype(subtype)
        super().__init__(message)
