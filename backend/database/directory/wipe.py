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
    if users_db.get_user_deletion_wipe_status(uid) != 'running':
        raise RuntimeError('cell purge requires a running account wipe')
    store = router.directory_store()
    if store.get_space(uid) is None:
        router.invalidate(uid)
        return {'status': 'absent'}
    now = time.time() if now is None else now
    store.set_routing(uid, cell='disabled', bump_epoch=True, now=now)
    router.invalidate(uid)
    cells = cell_store()
    cells.tombstone_space(uid)
    time.sleep(directory_routing.wipe_writer_drain_seconds())
    cells.purge_space(uid)
    store.purge_owner(uid, now=now)
    router.invalidate(uid)
    return {'status': 'purged'}
