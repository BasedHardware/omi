"""Required, retry-safe owner purge with admission fencing and writer drain."""

import time

from config import directory_routing
from database import users as users_db
from database.cells.serving import cell_store
from database.directory import router


def purge_owner_planes(uid: str, *, now: float | None = None) -> dict:
    """Required wipe step for the cell+directory planes. No-op when routing is off."""
    if directory_routing.mode() == 'off':
        return {'status': 'noop'}
    if not directory_routing.cell_wipe_enabled():
        raise RuntimeError('cell directory wipe is disabled')
    if users_db.get_user_deletion_wipe_status(uid) != 'running':
        raise RuntimeError('cell purge requires a running account wipe')
    store = router.directory_store()
    space = store.get_space(uid)
    if space is None:
        router.invalidate(uid)
        return {'status': 'absent'}
    cell = getattr(space, 'cell', None)  # Validate malformed driver results at this boundary.
    if not isinstance(cell, str) or not cell or cell == 'firestore':
        raise RuntimeError('cell purge requires explicit directory cell enrollment')
    cells = cell_store()
    # A cell head is created only by explicit enrollment/backfill. Its retained
    # tombstone is durable proof on retries after fencing or purge. Never create
    # enrollment as a side effect of wiping a directory-only owner.
    with cells.pool.connection() as conn:
        enrollment = conn.execute('SELECT tombstoned FROM space_heads WHERE space_id=%s', (uid,)).fetchone()
    if enrollment is None or (cell == 'disabled' and not enrollment[0]):
        raise RuntimeError('cell purge requires durable cell enrollment or wipe tombstone')
    now = time.time() if now is None else now
    cells.tombstone_space(uid)
    store.set_routing(uid, cell='disabled', bump_epoch=True, now=now)
    router.invalidate(uid)
    time.sleep(directory_routing.wipe_writer_drain_seconds())
    cells.purge_space(uid)
    store.purge_owner(uid, now=now)
    router.invalidate(uid)
    return {'status': 'purged'}
