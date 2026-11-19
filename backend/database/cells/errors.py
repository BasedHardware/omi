"""Typed cell failures shared by writes and the device feed."""

from database.firestore_transaction_retry import FirestoreContentionExhausted


class CellWriteError(RuntimeError):
    def __init__(self, space_id: str, message: str):
        super().__init__(message)
        self.space_id = space_id


class CellContentionExhausted(FirestoreContentionExhausted):
    def __init__(self, space_id: str):
        super().__init__('cell transaction kept conflicting')
        self.space_id = space_id


class CellSpaceUnavailable(CellWriteError):
    """Retryable admission failure: missing enrollment or a durable wipe fence."""

    code = 'cell_space_unavailable'
    retryable = True

    def __init__(self, space_id: str):
        super().__init__(space_id, 'cell space is not writable')


class BaseRevisionMismatch(CellWriteError):
    def __init__(self, space_id: str, current_rev: int | None):
        super().__init__(space_id, 'base revision mismatch')
        self.current_rev = current_rev


class MutationIdReused(CellWriteError):
    def __init__(self, space_id: str, client_mutation_id: str):
        super().__init__(space_id, 'client mutation id reused')
        self.client_mutation_id = client_mutation_id
