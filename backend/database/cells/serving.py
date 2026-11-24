"""Lazy serving pool, bounded to two connections until the pooler gate clears."""

import os
import threading

from config import directory_routing
from database.cells.store import CellStore
from database.jobstore.connection import Pool, iam_connector

_store: CellStore | None = None
_lock = threading.Lock()
# The singleton pool serves this label only; additional cells require dispatch.
CELL_LABEL = 'cell1'


def cell_store(*, for_wipe: bool = False) -> CellStore:
    global _store
    if not for_wipe and not directory_routing.routing_active():
        raise RuntimeError('directory routing is off')
    with _lock:
        if _store is None:
            dsn = os.getenv('CELLS_PG_DSN', '')
            connect = (
                None
                if dsn
                else iam_connector(
                    os.environ['CELLS_PG_HOST'], os.environ['CELLS_PG_DATABASE'], os.environ['CELLS_PG_USER']
                )
            )
            _store = CellStore(Pool(dsn, size=directory_routing.cell_pool_size(), connect=connect))
        return _store
