"""Shape-only experiment lease. Missing, corrupt or expired configuration routes control.

This file is a projected ConfigMap, never a subPath mount. The watcher renews
the lease; kubelet propagation delays can reduce admission but cannot extend it.
"""

from dataclasses import dataclass, field
from _thread import LockType
import json
import math
import os
from pathlib import Path
import secrets
import threading
import time

CANDIDATE = 'http://prod-omi-parakeet-g24.prod-omi-backend.svc.cluster.local:8080'


def read_lease() -> dict:
    path = os.getenv('PARAKEET_SHAPE_CANARY_FILE', '')
    if not path:
        return {}
    try:
        with Path(path).open() as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            return {}
        value = json.loads(raw)
        now = time.time()
        if (
            not isinstance(value, dict)
            or value.get('url') != CANDIDATE
            or not isinstance(value.get('identity'), str)
            or len(value['identity']) != 64
            or any(c not in '0123456789abcdef' for c in value['identity'])
            or type(value.get('percent')) not in (int, float)
            or not math.isfinite(value['percent'])
            or not 0 <= value['percent'] <= 5
            or type(value.get('expires')) not in (int, float)
            or not math.isfinite(value['expires'])
            or not now < value['expires'] <= now + 300
        ):
            return {}
        return value
    except (OSError, ValueError, TypeError):
        return {}


@dataclass
class ShapeRoute:
    """Pinned to a listen session, including replacement legs; never re-enters.

    Construction does no IO. resolve() is called on an executor before a POST.
    A rollback changes only the next request, never cancels accepted GPU work.
    """

    selected: bool = False
    initialized: bool = False
    drained: bool = False
    identity: str = ''
    counted: bool = False
    measured: bool = False
    _lock: LockType = field(default_factory=threading.Lock, init=False, repr=False)

    @property
    def arm(self) -> str:
        return 'canary' if self.selected else 'control'

    def resolve(self) -> str | None:
        with self._lock:
            return self._resolve()

    def _resolve(self) -> str | None:
        lease = read_lease()
        if not self.initialized:
            self.initialized = True
            self.identity = lease.get('identity', '')
            self.selected = secrets.randbelow(1_000_000) < lease.get('percent', 0) * 10_000
        if self.selected and (not lease or lease.get('percent', 0) == 0 or lease.get('identity') != self.identity):
            self.drained = True
        self.measured = bool(lease and lease.get('identity') == self.identity and not self.drained)
        return CANDIDATE if self.selected and not self.drained else None
