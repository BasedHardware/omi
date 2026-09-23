"""Typed intake outcomes: user authority is terminal, corrupt lineage is loud."""


class SyncAssignmentSuperseded(RuntimeError):
    """Deleted or user-managed lineage must not be recreated by WAL retries."""


class SyncAssignmentConflict(RuntimeError):
    """A provenance mismatch or corrupt redirect requires visible investigation."""
