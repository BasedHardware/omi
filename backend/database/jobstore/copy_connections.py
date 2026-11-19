"""Process-owned connections for the optional jobstore copy and its erasure.

Namespaces and cold purge calls share two normal connections and one connection
reserved for erasure. These are local ceilings, not a fleet admission policy.
Pools are lazy and live for the process lifetime; a target change requires a
process restart so it cannot manufacture another connection allowance.
"""

from __future__ import annotations

from dataclasses import dataclass
import threading

import database.jobstore.connection as connection


@dataclass(frozen=True)
class CopyPools:
    target: tuple[str, str, str]
    normal: connection.Pool
    erasure: connection.Pool


_pools: CopyPools | None = None
_lock = threading.Lock()


def copy_pools(host: str, database: str, user: str) -> CopyPools:
    """Return one lazy pair for the fixed process target; never dial here."""
    global _pools
    target = (host, database, user)
    with _lock:
        if _pools is None:
            connect = connection.iam_connector(*target)
            _pools = CopyPools(
                target, connection.Pool('', size=2, connect=connect), connection.Pool('', size=1, connect=connect)
            )
        elif _pools.target != target:
            raise RuntimeError('jobstore copy target changed within a process; restart required')
        return _pools
