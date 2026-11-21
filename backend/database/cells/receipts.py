"""Bounded mutation-receipt maintenance, independent of device-feed retention."""

from database.cells._validation import validate_id
from database.jobstore.connection import Pool

MUTATION_RECEIPT_RETENTION_SECONDS = 90 * 24 * 3600.0
MUTATION_RECEIPT_PURGE_LIMIT_MAX = 500


class Receipts:
    pool: Pool

    def purge_mutation_receipts(self, space_id: str, *, now: float, limit: int = 500) -> int:
        """Delete at most one bounded batch; replay protection ends after receipt expiry."""
        validate_id(space_id)
        with self.pool.connection() as conn, conn.transaction():
            conn.execute('SET LOCAL statement_timeout = 30000')
            return conn.execute(
                'WITH expired AS ('
                'SELECT space_id, client_mutation_id FROM mutation_receipts '
                'WHERE space_id=%s AND created_at<%s ORDER BY created_at, client_mutation_id '
                'LIMIT %s FOR UPDATE SKIP LOCKED) '
                'DELETE FROM mutation_receipts r USING expired e '
                'WHERE r.space_id=e.space_id AND r.client_mutation_id=e.client_mutation_id',
                (
                    space_id,
                    now - MUTATION_RECEIPT_RETENTION_SECONDS,
                    max(1, min(limit, MUTATION_RECEIPT_PURGE_LIMIT_MAX)),
                ),
            ).rowcount
