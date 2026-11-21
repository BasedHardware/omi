"""Serving directory authority: sticky enrollment and bounded, IO-free probe cache.

Every routing flip must call invalidate, including W6's operator ceremony. The
process cache transports sync-dependency resolution to handlers across contexts.
"""

import os
from contextlib import suppress
import threading
import time
import uuid
from typing import Literal

from config import directory_routing, rollout_cohorts
from config.policy.batch import cohort_bucket
from database import redis_db, users as users_db
from database.cells.serving import cell_store
from database.directory.store import DirectoryStore, Space
from database.jobstore.connection import Pool, iam_connector
from utils.rollout.runtime_percent import ramp_snapshot

Plane = Literal['firestore', 'cell']
PROCESS_TTL_SECONDS = 300
PROCESS_MAX_ENTRIES = 10000
REDIS_TTL_SECONDS = 3600
_cache: dict[str, tuple[float, Plane, str | None]] = {}
_store: DirectoryStore | None = None
_lock = threading.Lock()


class DirectoryRoutingUnavailable(RuntimeError):
    """No authoritative route; callers must retry rather than fork an account."""


routing_active = directory_routing.routing_active


def directory_store(*, for_wipe: bool = False) -> DirectoryStore:
    global _store
    if not for_wipe and not routing_active():
        raise RuntimeError('directory routing is off')
    with _lock:
        if _store is None:
            dsn = os.getenv('DIRECTORY_PG_DSN', '')
            connect = (
                None
                if dsn
                else iam_connector(
                    os.environ['DIRECTORY_PG_HOST'],
                    os.environ['DIRECTORY_PG_DATABASE'],
                    os.environ['DIRECTORY_PG_USER'],
                )
            )
            _store = DirectoryStore(Pool(dsn, size=directory_routing.directory_pool_size(), connect=connect))
        return _store


def _cached(uid: str) -> Plane | None:
    entry = _cache.get(uid)
    return entry[1] if entry is not None and entry[0] > time.monotonic() else None


def cached_plane(uid: str) -> Plane:
    """No IO, locks or exceptions: safe inside the Firestore probes."""
    if os.getenv('DIRECTORY_ROUTING_MODE', 'off') == 'off':
        return 'firestore'
    return _cached(uid) or 'firestore'


def _remember(uid: str, plane: Plane, epoch: str | None = None) -> None:
    with _lock:
        # Insertion-order eviction bounds expired entries too (10,000 owners).
        if uid not in _cache and len(_cache) >= PROCESS_MAX_ENTRIES:
            _cache.pop(next(iter(_cache)))
        _cache[uid] = (time.monotonic() + PROCESS_TTL_SECONDS, plane, epoch)


def _plane_of(space: Space) -> Plane:
    cell = getattr(space, 'cell', None)  # Validate the driver result at the routing boundary.
    if not isinstance(cell, str) or not cell:
        raise DirectoryRoutingUnavailable('malformed directory route')
    if cell == 'disabled':
        raise DirectoryRoutingUnavailable('directory route is fenced')
    return 'firestore' if cell == 'firestore' else 'cell'


def _epoch_key(uid: str) -> str:
    return f'plane:epoch:v1:{uid}'


def _route_epoch(uid: str) -> str:
    # Raw Redis operations deliberately bypass the generic cache's fail-open
    # decorators. Missing/evicted epochs get fresh identities, never a reused 0.
    raw = redis_db.r.get(_epoch_key(uid))
    if raw is None:
        epoch = uuid.uuid4().hex
        if redis_db.r.set(_epoch_key(uid), epoch, nx=True):
            return epoch
        raw = redis_db.r.get(_epoch_key(uid))
    if isinstance(raw, bytes):
        raw = raw.decode('ascii')
    if not isinstance(raw, str) or not raw:
        raise DirectoryRoutingUnavailable('directory route epoch unavailable')
    return raw


def invalidate(uid: str) -> None:
    """Publish a new epoch after every routing flip/purge; failures must retry.

    A flip is not complete until this succeeds. Already-admitted requests still
    need the cutover writer drain; all subsequent resolutions check this epoch.
    """
    _cache.pop(uid, None)
    if not routing_active():
        return
    try:
        if not redis_db.r.set(_epoch_key(uid), uuid.uuid4().hex):
            raise DirectoryRoutingUnavailable('directory route epoch publication failed')
    except Exception as exc:
        raise DirectoryRoutingUnavailable('directory route invalidation unavailable') from exc
    with suppress(Exception):
        redis_db.delete_generic_cache(f'plane:v1:{uid}')


def resolve(uid: str, *, signup_platform: str | None = None, signup_os: str | None = None) -> Plane:
    if not routing_active():
        return 'firestore'
    try:
        epoch = _route_epoch(uid)  # One GET even on a process-cache hit.
        entry = _cache.get(uid)
        if entry is not None and entry[0] > time.monotonic() and entry[2] == epoch:
            return entry[1]
        _cache.pop(uid, None)
        cached = redis_db.get_generic_cache(f'plane:v1:{uid}')
        if isinstance(cached, dict) and cached.get('epoch') == epoch and cached.get('plane') in ('firestore', 'cell'):
            plane = cached['plane']
            _remember(uid, plane, epoch)
            return plane
        store = directory_store()
        space = store.get_space(uid)
        if space is None:
            if not rollout_cohorts.valid_uid(uid):
                return 'firestore'
            # Must precede record_user_platform, which merge-creates users/{uid}.
            existing = users_db.is_exists_user(uid)
            bucket = cohort_bucket(uid, 'new-owner-cell1')
            percent = rollout_cohorts.runtime_percent(
                'new-owner-cell1', env_default=directory_routing.new_owner_percent_env()
            )
            # B2 shares the existing signup wire contract; do not duplicate its mapping.
            platform, os_value = users_db._normalize_platform(signup_platform)  # pyright: ignore[reportPrivateUsage]
            now = time.time()
            space = store.get_or_create_personal_space(
                uid,
                cell='cell1' if not existing and bucket < percent else 'firestore',
                ramp_bucket=bucket,
                ramp_revision=ramp_snapshot().revision,
                signup_platform=platform,
                signup_os=signup_os or os_value,
                signup_platform_at=now if platform else None,
                now=now,
            )
        plane = _plane_of(space)
        if plane == 'cell':
            # Explicit enrollment only. The durable cell tombstone rejects a
            # resolver that read the old directory row before a wipe fence.
            store.enroll_cell(uid, lambda: cell_store().enroll_space(uid, now=time.time()))
        _remember(uid, plane, epoch)
        with suppress(Exception):
            redis_db.set_generic_cache(f'plane:v1:{uid}', {'plane': plane, 'epoch': epoch}, REDIS_TTL_SECONDS)
        return plane
    except DirectoryRoutingUnavailable:
        raise
    except Exception as exc:
        raise DirectoryRoutingUnavailable('directory resolution unavailable') from exc
