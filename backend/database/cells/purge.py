"""Fail-closed deletion primitive, adapted from jobstore/dual_store.py purge_owner_now.

The space head lock serializes the fence, writes and purge across processes.
"""

from database.cells._validation import validate_id
from database.cells.errors import CellSpaceUnavailable
from database.jobstore.connection import Pool

TABLES = ('cell_docs', 'change_log', 'sync_cursors', 'mutation_receipts')


def lock_writable_space(conn, space_id: str) -> None:
    row = conn.execute('SELECT tombstoned FROM space_heads WHERE space_id=%s FOR UPDATE', (space_id,)).fetchone()
    if row is None or row[0]:
        raise CellSpaceUnavailable(space_id)


def _tombstone(conn, space_id: str) -> None:
    # Upsert a tombstone even for an empty/missing cell. A resolver with an old
    # directory row can otherwise enroll the head after purge.
    conn.execute(
        'INSERT INTO space_heads (space_id, next_seq, epoch, updated_at, tombstoned) VALUES (%s,0,1,0,true) '
        'ON CONFLICT (space_id) DO UPDATE SET tombstoned=true',
        (space_id,),
    )


class Purge:
    pool: Pool

    def tombstone_space(self, space_id: str) -> None:
        validate_id(space_id)
        with self.pool.connection() as conn, conn.transaction():
            conn.execute('SET LOCAL statement_timeout = 30000')
            _tombstone(conn, space_id)

    def purge_space(self, space_id: str) -> int:
        validate_id(space_id)
        with self.pool.connection() as conn, conn.transaction():
            conn.execute('SET LOCAL statement_timeout = 30000')
            _tombstone(conn, space_id)
            count = 0
            for table in TABLES:
                count += conn.execute(f'DELETE FROM {table} WHERE space_id=%s', (space_id,)).rowcount
            for table in TABLES:
                if conn.execute(f'SELECT count(*) FROM {table} WHERE space_id=%s', (space_id,)).fetchone()[0]:
                    raise RuntimeError('cell purge left rows behind')
            return count
