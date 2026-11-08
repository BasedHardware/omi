"""Exactly-once application of optimistic space mutations through CellStore."""

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from database.cells.errors import MutationIdReused
from database.cells.feed import read_enrolled_head
from database.cells.store import CellStore, CellTransaction
from database.jobstore.codec import canonical


class SpaceMutationNotFoundError(LookupError):
    pass


class SpaceMutationConflictError(RuntimeError):
    def __init__(self, response: dict[str, Any]):
        super().__init__(response['code'])
        self.response = response


def _current_row(conn: Any, space_id: str, entity: str, entity_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        'SELECT author_id, rev, doc, updated_at FROM cell_docs WHERE space_id=%s AND entity=%s AND entity_id=%s',
        (space_id, entity, entity_id),
    ).fetchone()
    if row is None:
        return None
    return dict(entity=entity, entity_id=entity_id, author_id=row[0], rev=row[1], doc=row[2], updated_at=row[3])


def apply_space_mutation(
    store: CellStore,
    space_id: str,
    *,
    actor_uid: str,
    entity: str,
    entity_id: str,
    client_mutation_id: str,
    base_revision: datetime | int,
    operation: dict[str, Any],
    now: float,
) -> tuple[dict[str, Any], bool]:
    # Canonicalization follows database/conversation_mutations.py:_fingerprint,
    # but uses 'base' instead of 'base_revision'; fingerprints are not identical.
    # Importing that Firestore adapter violates the cell boundary. A6 unifies it.
    token = base_revision.astimezone(timezone.utc).isoformat() if isinstance(base_revision, datetime) else base_revision
    fingerprint = sha256(canonical({'base': token, 'operation': operation}).encode()).hexdigest()
    if operation.get('type') not in {'patch', 'delete'}:
        raise ValueError('unknown space mutation operation')

    def conflict(code: str, row: dict[str, Any] | None) -> SpaceMutationConflictError:
        return SpaceMutationConflictError(
            dict(
                status='conflict',
                code=code,
                client_mutation_id=client_mutation_id,
                entity=entity,
                entity_id=entity_id,
                row=row,
            )
        )

    def buffer(tx: CellTransaction, doc: dict[str, Any], expected_rev: int | None = None) -> None:
        if operation['type'] == 'delete':
            tx.delete(
                entity,
                entity_id,
                feed=True,
                expected_rev=expected_rev,
                client_mutation_id=client_mutation_id,
                fingerprint=fingerprint,
            )
        else:
            tx.put(
                entity,
                entity_id,
                doc,
                feed=True,
                expected_rev=expected_rev,
                client_mutation_id=client_mutation_id,
                fingerprint=fingerprint,
            )

    def body(tx: CellTransaction):
        # Even an absent-entity request must observe the unenrolled/wipe fence.
        read_enrolled_head(tx.conn, space_id)
        if tx.receipt_seq(client_mutation_id) is not None:
            # flush owns address/op/fingerprint validation, including deleted rows.
            # Buffer a replay candidate; flush discards it before checking the base.
            buffer(tx, {})
            return
        row = tx.get_with_rev(entity, entity_id)
        # A concurrent duplicate may have committed while the row lock waited.
        if tx.receipt_seq(client_mutation_id) is not None:
            buffer(tx, {})
            return
        if row is None:
            raise SpaceMutationNotFoundError(entity_id)
        rev, doc = row
        base = (
            tx.seq_as_of(entity, entity_id, base_revision.timestamp())
            if isinstance(base_revision, datetime)
            else base_revision
        )
        if base is None:
            raise conflict('revision_unavailable', _current_row(tx.conn, space_id, entity, entity_id))
        if base != rev:
            raise conflict('base_revision_mismatch', _current_row(tx.conn, space_id, entity, entity_id))
        buffer(tx, {**doc, **operation.get('fields', {})}, rev)

    try:
        result = store.run(space_id, body, actor_uid=actor_uid, now=now)
    except MutationIdReused as error:
        with store.pool.connection() as conn, conn.transaction():
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            read_enrolled_head(conn, space_id)
            row = _current_row(conn, space_id, entity, entity_id)
        raise conflict('mutation_id_reused', row) from error
    replayed = client_mutation_id in result.replayed
    with store.pool.connection() as conn, conn.transaction():
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        read_enrolled_head(conn, space_id)
        seq = CellTransaction(conn, space_id, actor_uid, now).receipt_seq(client_mutation_id)
    return (
        dict(
            status='ok',
            client_mutation_id=client_mutation_id,
            entity=entity,
            entity_id=entity_id,
            seq=seq,
            rev=seq,  # Receipts retain the original applied revision even after later writes.
            replayed=replayed,
        ),
        replayed,
    )
