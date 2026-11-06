"""Fail-closed deletion primitive, adapted from jobstore/dual_store.py purge_owner_now.

Enrollment must fence new writes before invoking this primitive (B2).
"""

from database.cells._validation import validate_id
from database.jobstore.connection import Pool

TABLES = ('space_heads', 'cell_docs', 'change_log', 'sync_cursors')


class Purge:
    pool: Pool

    def purge_space(self, space_id: str) -> int:
        validate_id(space_id)
        with self.pool.connection() as conn, conn.transaction():
            conn.execute('SET LOCAL statement_timeout = 30000')
            count = 0
            for table in TABLES:
                count += conn.execute(f'DELETE FROM {table} WHERE space_id=%s', (space_id,)).rowcount
            for table in TABLES:
                if conn.execute(f'SELECT count(*) FROM {table} WHERE space_id=%s', (space_id,)).fetchone()[0]:
                    raise RuntimeError('cell purge left rows behind')
            return count
