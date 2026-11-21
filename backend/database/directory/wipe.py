"""Required, retry-safe owner purge with admission fencing and writer drain."""

import time

from config import directory_routing
from database import users as users_db
from database.cells.serving import cell_store
from database.directory import router


def purge_owner_planes(uid: str, *, now: float | None = None) -> dict:
    """Zero IO without a directory binding; required erasure in every routing mode."""
    if not directory_routing.directory_configured():
        return {'status': 'noop'}
    if not directory_routing.cell_wipe_enabled():
        raise RuntimeError('cell directory wipe is disabled')
    if users_db.get_user_deletion_wipe_status(uid) != 'running':
        raise RuntimeError('cell purge requires a running account wipe')
    store = router.directory_store(for_wipe=True)
    now = time.time() if now is None else now
    # This serializes with both row creation and cell enrollment. Retaining the
    # original route makes retries safe after the space row itself is removed.
    fence = store.tombstone_owner(uid, now=now)
    router.invalidate(uid)
    cell = fence.cell
    if cell is None or cell == 'firestore':
        # No cell authority ever existed for this owner. Still fence delayed
        # directory creates, and remove tokens/memberships for absent owners.
        time.sleep(directory_routing.wipe_writer_drain_seconds())
        store.purge_owner(uid, now=now)
        router.invalidate(uid)
        return {'status': 'absent' if cell is None else 'purged'}
    if not cell:
        raise RuntimeError('cell purge requires explicit directory cell enrollment')
    cells = cell_store(for_wipe=True)
    if cell == 'disabled':
        # An interrupted earlier wipe disabled the route before this fence row
        # existed. Its retained cell-head tombstone is the durable proof to resume.
        with cells.pool.connection() as conn:
            head = conn.execute('SELECT tombstoned FROM space_heads WHERE space_id=%s', (uid,)).fetchone()
        if head is None or not head[0]:
            raise RuntimeError('cell purge requires explicit directory cell enrollment or wipe tombstone')
    # A directory enrollment may have committed before its first cell head.
    # The directory fence now excludes that delayed enrollment; tombstone the
    # head even when missing, so old cell writers also remain fenced forever.
    cells.tombstone_space(uid)
    time.sleep(directory_routing.wipe_writer_drain_seconds())
    cells.purge_space(uid)
    store.purge_owner(uid, now=now)
    router.invalidate(uid)
    return {'status': 'purged'}
